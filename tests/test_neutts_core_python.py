"""Behavior checks for the download-only, exact scientific-core wheel preparer."""
from __future__ import annotations

import base64
import csv
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import time
import warnings
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_neutts_core_python.py"
spec = importlib.util.spec_from_file_location("prepare_neutts_core_python", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def wheel_fixture(*, additions=(), corrupt_record=False, native=False):
    prefix = "demo-1.0.dist-info"
    metadata = (
        "Metadata-Version: 2.4\nName: Demo\nVersion: 1.0\n"
        "Requires-Python: >=3.9\nRequires-Dist: dependency>=1\n\n"
    ).encode()
    wheel = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n"
    members = [
        ("demo/__init__.py", b"VALUE = 7\n", stat.S_IFREG | 0o644),
        (prefix + "/METADATA", metadata, stat.S_IFREG | 0o644),
        (prefix + "/WHEEL", wheel, stat.S_IFREG | 0o644),
        *additions,
    ]
    if native:
        members.append(("demo/_speedups.so", b"\x7fELF-fixture", stat.S_IFREG | 0o644))
    record = prefix + "/RECORD"
    rows = []
    for name, value, _mode in members:
        if name.endswith("/"):
            continue
        digest = base64.urlsafe_b64encode(bytes.fromhex(probe.sha256(value))).decode().rstrip("=")
        rows.append([name, "sha256=" + digest, str(len(value))])
    if corrupt_record:
        rows[0][1] = "sha256=" + "0" * 43
    rows.append([record, "", ""])
    text = io.StringIO(newline="")
    csv.writer(text, lineterminator="\n").writerows(rows)
    members.append((record, text.getvalue().encode(), stat.S_IFREG | 0o644))
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, value, mode in members:
                info = zipfile.ZipInfo(name)
                # Preserve malicious raw names even when a Windows ZipInfo
                # constructor normalizes backslashes for ordinary archives.
                info.filename = name
                info.orig_filename = name
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, value)
    raw = buffer.getvalue()
    filename = "demo-1.0-py3-none-any.whl"
    package = {
        "name": "demo", "version": "1.0", "requires_python": ">=3.9",
        "base_requires_dist": ["dependency>=1"],
        "artifact": {
            "filename": filename, "bytes": len(raw), "sha256": probe.sha256(raw),
            "url": "https://files.pythonhosted.org/packages/aa/bb/" + "c" * 60 + "/" + filename,
        },
        "wheel": {
            "tags": ["py3-none-any"], "root_is_purelib": True,
            "metadata_member": prefix + "/METADATA", "metadata_sha256": probe.sha256(metadata),
            "wheel_member": prefix + "/WHEEL", "wheel_sha256": probe.sha256(wheel),
            "record_member": record, "record_sha256": probe.sha256(text.getvalue().encode()),
            "entry_count": len(members),
            "file_count": sum(not name.endswith("/") for name, _, _ in members),
            "uncompressed_bytes": sum(len(value) for _, value, _ in members),
            "max_member_bytes": max(len(value) for _, value, _ in members),
            "members_sha256": probe.lines_sha256(sorted(name for name, _, _ in members)),
            "declared_requires_dist_count": 1,
            "declared_requires_dist_sha256": probe.lines_sha256(["dependency>=1"]),
        },
        "native_members": [
            {"member": name, "bytes": len(value), "sha256": probe.sha256(value)}
            for name, value, _mode in members if name.endswith(".so")
        ],
    }
    return raw, package


def save_wheel(tmp_path, raw, package):
    path = tmp_path / package["artifact"]["filename"]
    path.write_bytes(raw)
    return path


def test_frozen_lock_is_exact_closed_scope():
    lock, raw = probe.load_lock(SCRIPT.with_name(probe.LOCK_FILENAME))
    assert probe.sha256(raw) == probe.LOCK_SHA256
    assert len(lock["packages"]) == 9
    assert sum(p["artifact"]["bytes"] for p in lock["packages"]) == 10_411_849
    assert lock["selected_extras"] == []
    by_name = {p["name"]: p for p in lock["packages"]}
    assert by_name["sympy"]["base_requires_dist"] == ["mpmath<1.4,>=1.1.0"]
    assert by_name["jinja2"]["base_requires_dist"] == ["MarkupSafe>=2.0"]
    assert by_name["markupsafe"]["wheel"]["tags"] == ["cp314-cp314-android_24_arm64_v8a"]
    assert len(by_name["markupsafe"]["native_members"]) == 1


def test_modified_lock_cannot_replace_artifacts(tmp_path):
    path = tmp_path / "modified.json"
    path.write_bytes(SCRIPT.with_name(probe.LOCK_FILENAME).read_bytes() + b"\n")
    with pytest.raises(probe.PrepareError, match="frozen identity"):
        probe.load_lock(path)


def test_verified_archive_directory_entries_and_native_hash(tmp_path):
    raw, package = wheel_fixture(
        additions=(("demo/", b"", stat.S_IFDIR | 0o755),), native=True
    )
    result = probe.verify_wheel(save_wheel(tmp_path, raw, package), package)
    assert result["native_members"] == package["native_members"]
    assert result["checks"]["all_member_crcs_and_record_hashes"] == "passed"


@pytest.mark.parametrize("name", [
    "../escape.py", "/absolute.py", "C:/drive.py", "demo\\escape.py",
    "demo//double.py", "demo/./dot.py", "demo/../escape.py", "demo/\nline.py",
])
def test_unsafe_member_paths_are_rejected(tmp_path, name):
    raw, package = wheel_fixture(additions=((name, b"unsafe", stat.S_IFREG | 0o644),))
    with pytest.raises(probe.PrepareError, match="Unsafe path"):
        probe.verify_wheel(save_wheel(tmp_path, raw, package), package)


def test_nul_truncated_path_is_rejected():
    with pytest.raises(probe.PrepareError, match="Unsafe path"):
        probe.safe_member(zipfile.ZipInfo("demo/\x00hidden"))


def test_zip_symlink_is_rejected_without_extracting(tmp_path):
    raw, package = wheel_fixture(
        additions=(("demo/link.py", b"../../outside", stat.S_IFLNK | 0o777),)
    )
    with pytest.raises(probe.PrepareError, match="Symlink"):
        probe.verify_wheel(save_wheel(tmp_path, raw, package), package)
    assert not (tmp_path / "demo").exists()


def test_duplicate_member_is_rejected(tmp_path):
    raw, package = wheel_fixture(
        additions=(("demo/__init__.py", b"replacement", stat.S_IFREG | 0o644),)
    )
    with pytest.raises(probe.PrepareError, match="Duplicate ZIP"):
        probe.verify_wheel(save_wheel(tmp_path, raw, package), package)


def test_unexpected_member_is_rejected_even_after_archive_hash_update(tmp_path):
    _, original = wheel_fixture()
    raw, changed = wheel_fixture(additions=(("extra.py", b"extra", stat.S_IFREG | 0o644),))
    original["artifact"] = changed["artifact"]
    with pytest.raises(probe.PrepareError, match="member inventory"):
        probe.verify_wheel(save_wheel(tmp_path, raw, changed), original)


@pytest.mark.parametrize(("section", "key", "replacement", "reason"), [
    (None, "name", "other", "identity"),
    (None, "version", "2.0", "identity"),
    (None, "requires_python", ">=3.15", "Python requirement"),
    (None, "base_requires_dist", [], "declared requirements"),
    ("wheel", "declared_requires_dist_sha256", "0" * 64, "declared requirements"),
    ("wheel", "tags", ["cp314-cp314-android_24_arm64_v8a"], "tags"),
    ("wheel", "root_is_purelib", False, "purelib"),
    ("wheel", "metadata_sha256", "0" * 64, "metadata byte digest"),
])
def test_metadata_contract_cannot_drift(tmp_path, section, key, replacement, reason):
    raw, package = wheel_fixture()
    path = save_wheel(tmp_path, raw, package)
    target = package if section is None else package[section]
    target[key] = replacement
    with pytest.raises(probe.PrepareError, match=reason):
        probe.verify_wheel(path, package)


def test_record_hashes_are_actually_checked(tmp_path):
    raw, package = wheel_fixture(corrupt_record=True)
    with pytest.raises(probe.PrepareError, match="RECORD member digest"):
        probe.verify_wheel(save_wheel(tmp_path, raw, package), package)


def test_member_crc_is_actually_checked(tmp_path):
    raw, package = wheel_fixture()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo("demo/__init__.py")
        offset = info.header_offset
        name_len, extra_len = struct.unpack_from("<HH", raw, offset + 26)
        data_offset = offset + 30 + name_len + extra_len
    corrupted = bytearray(raw)
    corrupted[data_offset] ^= 1
    package["artifact"]["sha256"] = probe.sha256(corrupted)
    with pytest.raises(probe.PrepareError, match="Invalid wheel archive"):
        probe.verify_wheel(save_wheel(tmp_path, bytes(corrupted), package), package)


def test_native_member_hash_cannot_drift(tmp_path):
    raw, package = wheel_fixture(native=True)
    package["native_members"][0]["sha256"] = "0" * 64
    with pytest.raises(probe.PrepareError, match="Native extension digest"):
        probe.verify_wheel(save_wheel(tmp_path, raw, package), package)


class Response(io.BytesIO):
    status = 200

    def __init__(self, artifact, data):
        super().__init__(data)
        self.url = artifact["url"]
        self.headers = {"Content-Length": str(artifact["bytes"])}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, artifact, data):
        self.artifact = artifact
        self.data = data
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        assert request.full_url == self.artifact["url"]
        assert 0 < timeout <= probe.READ_TIMEOUT_SECONDS
        assert not any(key.lower() in ("authorization", "cookie") for key in request.headers)
        return Response(self.artifact, self.data)


@pytest.mark.parametrize("change", [
    lambda data: data[:-1],
    lambda data: data + b"extra",
    lambda data: b"x" + data[1:],
])
def test_download_byte_integrity_is_enforced(tmp_path, change):
    raw, package = wheel_fixture()
    opener = Opener(package["artifact"], change(raw))
    with pytest.raises(probe.PrepareError, match="size|SHA"):
        probe.download_file(
            package["artifact"], tmp_path / "wheel.whl", opener, time.monotonic() + 5,
        )


def test_expired_deadline_never_opens_network(tmp_path):
    raw, package = wheel_fixture()
    opener = Opener(package["artifact"], raw)
    with pytest.raises(probe.PrepareError, match="deadline"):
        probe.download_file(package["artifact"], tmp_path / "wheel.whl", opener, 0)
    assert opener.calls == 0


@pytest.mark.parametrize("url", [
    "http://files.pythonhosted.org/a.whl",
    "https://example.com/a.whl",
    "https://user:password@files.pythonhosted.org/a.whl",
    "https://files.pythonhosted.org:443/a.whl",
    "https://files.pythonhosted.org/a.whl?replace=yes",
    "file:///tmp/a.whl",
])
def test_replacement_endpoints_are_not_accepted(url):
    _, package = wheel_fixture()
    package["artifact"]["url"] = url
    with pytest.raises(probe.PrepareError, match="official immutable endpoint"):
        probe.validate_artifact(package["artifact"])


def test_redirect_handler_refuses_automatic_follow():
    assert probe.NoRedirect().redirect_request(
        None, None, 302, "Found", {}, "https://example.com/replacement",
    ) is None


def fake_lock(monkeypatch, package):
    lock = {
        "target": {"python": "3.14.6", "abi": "cp314"},
        "selected_extras": [], "packages": [package],
    }
    raw = (json.dumps(lock) + "\n").encode()
    monkeypatch.setattr(probe, "load_lock", lambda _path: (lock, raw))
    return raw


def test_publish_only_verified_files_with_hashed_requirements(tmp_path, monkeypatch):
    raw, package = wheel_fixture()
    raw_lock = fake_lock(monkeypatch, package)
    output = tmp_path / "wheels"
    receipt = probe.prepare(Path("fixture-lock"), output, opener=Opener(package["artifact"], raw))
    assert {p.name for p in output.iterdir()} == {
        package["artifact"]["filename"], "requirements.txt",
        probe.LOCK_FILENAME, probe.RECEIPT_FILENAME,
    }
    assert (output / probe.LOCK_FILENAME).read_bytes() == raw_lock
    assert (output / "requirements.txt").read_text() == (
        f"demo==1.0 --hash=sha256:{package['artifact']['sha256']}\n"
    )
    assert receipt["requirements"]["sha256"] == probe.sha256(
        (output / "requirements.txt").read_bytes()
    )
    assert receipt["lock"]["sha256"] == probe.sha256(raw_lock)
    assert json.loads((output / probe.RECEIPT_FILENAME).read_bytes()) == receipt
    if sys_platform_is_posix():
        assert stat.S_IMODE(output.stat().st_mode) == 0o755
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o644 for p in output.iterdir())


def sys_platform_is_posix():
    import os
    return os.name == "posix"


def test_failure_cleans_private_stage_and_never_publishes(tmp_path, monkeypatch):
    raw, package = wheel_fixture()
    fake_lock(monkeypatch, package)
    output = tmp_path / "wheels"
    with pytest.raises(probe.PrepareError):
        probe.prepare(Path("fixture-lock"), output, opener=Opener(package["artifact"], raw[:-1]))
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_existing_output_is_preserved_without_network(tmp_path, monkeypatch):
    raw, package = wheel_fixture()
    fake_lock(monkeypatch, package)
    output = tmp_path / "wheels"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserved")
    opener = Opener(package["artifact"], raw)
    with pytest.raises(probe.PrepareError, match="already exists"):
        probe.prepare(Path("fixture-lock"), output, opener=opener)
    assert sentinel.read_text() == "preserved"
    assert opener.calls == 0


def test_unexpected_staged_file_prevents_publication(tmp_path, monkeypatch):
    raw, package = wheel_fixture()
    fake_lock(monkeypatch, package)
    original = probe.write_new

    def inject_file(path, value):
        original(path, value)
        if path.name == probe.RECEIPT_FILENAME:
            (path.parent / "extra.whl").write_bytes(b"unverified")

    monkeypatch.setattr(probe, "write_new", inject_file)
    with pytest.raises(probe.PrepareError, match="Unexpected file"):
        probe.prepare(Path("fixture-lock"), tmp_path / "wheels", opener=Opener(package["artifact"], raw))
    assert list(tmp_path.iterdir()) == []


def test_nonregular_staged_file_is_rejected(tmp_path):
    (tmp_path / "fake.whl").mkdir()
    with pytest.raises(probe.PrepareError, match="nonregular"):
        probe.check_file_set(tmp_path, {"fake.whl"})
