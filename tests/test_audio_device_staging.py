"""Boundary checks for the isolated, frozen audio-device staging experiment."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

import pytest

from scripts import prepare_audio_device_bundle as staging


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_entry(root: Path, relative: str, data: bytes) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": relative,
        "kind": "file",
        "mode": stat.S_IMODE(path.stat().st_mode),
        "size": len(data),
        "sha256": digest(data),
    }


@pytest.fixture
def manifest_tree(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "app").mkdir()
    entries = [
        {
            "path": "app",
            "kind": "directory",
            "mode": stat.S_IMODE((root / "app").stat().st_mode),
        },
        file_entry(root, "app/program.py", b"VALUE = 23\n"),
        file_entry(root, "requirements.txt", b"demo==1.0\n"),
    ]
    return root, {"schema_version": 1, "entries": entries, "generated_roots": ["venv", "pm-runtime", "state", "bin"]}


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../escape",
        "app/../../escape",
        "/absolute",
        "//server/share",
        "C:/Windows/escape",
        "C:\\Windows\\escape",
        "app\\..\\escape",
        "app/\x00payload",
    ],
)
def test_member_paths_reject_escape_and_host_path_aliases(name):
    with pytest.raises(staging.StagingError):
        staging.safe_relative_path(name)


@pytest.mark.parametrize("name", ["app/program.py", "app/quiet room.txt", "wheelhouse/demo-1.0-py3-none-any.whl"])
def test_member_paths_preserve_regular_nested_names(name):
    assert staging.safe_relative_path(name) == PurePosixPath(name)


def test_new_destination_validation_creates_nothing(tmp_path):
    destination = tmp_path / "new destination"
    assert staging.validate_destination(destination) == destination.resolve()
    assert not destination.exists()


@pytest.mark.parametrize("existing_kind", ["directory", "file"])
def test_existing_destination_is_not_overwritten(tmp_path, existing_kind):
    destination = tmp_path / "owned"
    if existing_kind == "directory":
        destination.mkdir()
        marker = destination / "keep.txt"
    else:
        marker = destination
    marker.write_bytes(b"owner data")
    with pytest.raises(staging.StagingError):
        staging.validate_destination(destination)
    assert marker.read_bytes() == b"owner data"


@pytest.mark.parametrize("relationship", ["inside_input", "contains_input", "same_input"])
def test_destination_cannot_overlap_a_forbidden_input(tmp_path, relationship):
    source = tmp_path / "source"
    destination = {
        "inside_input": source / "new",
        "contains_input": tmp_path / "destination",
        "same_input": source,
    }[relationship]
    forbidden = destination / "input" if relationship == "contains_input" else source
    with pytest.raises(staging.StagingError):
        staging.validate_destination(destination, forbidden_roots=(forbidden,))
    assert not destination.exists()


def make_symlink(target: Path, link: Path, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"This host cannot create filesystem symlinks: {exc}")


def test_destination_rejects_a_symlink_parent(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    make_symlink(real, alias, directory=True)
    with pytest.raises(staging.StagingError):
        staging.validate_destination(alias / "new")
    assert not (real / "new").exists()


def test_exact_file_verification_is_read_only(tmp_path):
    path = tmp_path / "wheel.whl"
    data = b"exact pinned wheel bytes"
    path.write_bytes(data)
    staging.verify_file(path, {"size": len(data), "sha256": digest(data)})
    assert path.read_bytes() == data


@pytest.mark.parametrize("corruption", [b"same!", b"truncated", b"longer replacement"])
def test_file_corruption_is_rejected_even_when_size_matches(tmp_path, corruption):
    path = tmp_path / "wheel.whl"
    original = b"valid"
    path.write_bytes(corruption)
    with pytest.raises(staging.StagingError):
        staging.verify_file(path, {"size": len(original), "sha256": digest(original)})
    assert path.read_bytes() == corruption


def test_file_verification_does_not_accept_a_symlink(tmp_path):
    target = tmp_path / "outside.whl"
    data = b"expected bytes"
    target.write_bytes(data)
    link = tmp_path / "wheel.whl"
    make_symlink(target, link)
    with pytest.raises(staging.StagingError):
        staging.verify_file(link, {"size": len(data), "sha256": digest(data)})


def test_complete_manifest_accepts_its_exact_tree(manifest_tree):
    root, manifest = manifest_tree
    result = staging.verify_manifest_tree(root, manifest)
    assert isinstance(result, dict)
    assert (root / "app/program.py").read_bytes() == b"VALUE = 23\n"


@pytest.mark.parametrize("change", ["same_size_corruption", "missing_file", "unexpected_file"])
def test_manifest_rejects_corrupt_incomplete_or_expanded_trees(manifest_tree, change):
    root, manifest = manifest_tree
    path = root / "app/program.py"
    if change == "same_size_corruption":
        path.write_bytes(b"VALUE = 99\n")
    elif change == "missing_file":
        path.unlink()
    else:
        (root / "app/unreviewed.py").write_bytes(b"print('unreviewed')\n")
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest)


def test_manifest_cannot_describe_the_same_path_twice(manifest_tree):
    root, manifest = manifest_tree
    manifest["entries"].append(dict(manifest["entries"][1]))
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest)


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:/outside", "app\\..\\outside"])
def test_manifest_path_escape_is_rejected_before_external_access(manifest_tree, path):
    root, manifest = manifest_tree
    outside = root.parent / "outside"
    outside.write_bytes(b"owner data")
    manifest["entries"].append({"path": path, "kind": "file", "mode": 0o644, "size": 10, "sha256": digest(b"owner data")})
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest)
    assert outside.read_bytes() == b"owner data"


def test_allow_generated_never_allows_tampering_with_verified_app(manifest_tree):
    root, manifest = manifest_tree
    (root / "app/program.py").write_bytes(b"VALUE = 99\n")
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest, allow_generated=True)


def test_allow_generated_never_allows_an_unlisted_app_module(manifest_tree):
    root, manifest = manifest_tree
    (root / "app/unreviewed.py").write_bytes(b"VALUE = 0\n")
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest, allow_generated=True)


def test_manifest_rejects_symlink_escape(manifest_tree):
    root, manifest = manifest_tree
    outside = root.parent / "private"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"owner data")
    link = root / "app/external"
    make_symlink(outside, link, directory=True)
    manifest["entries"].append(
        {"path": "app/external", "kind": "symlink", "mode": 0o777, "target": "../../private"}
    )
    with pytest.raises(staging.StagingError):
        staging.verify_manifest_tree(root, manifest)
    assert (outside / "keep.txt").read_bytes() == b"owner data"


@pytest.fixture
def wheel_union():
    candidate_cffi = "196cd52f8b5ac753e947e1267381ddf9616a41033f310a05993b96c6262b52e1"
    audio_cffi = "36977e26001a7f4da546fda9fd8715ff6e81e6661d02eb28bc5f2ee0f235f9b2"

    def row(name, version, *, checksum=None, abi="py3-none-any"):
        file = f"wheelhouse/{name}-{version}-{abi}.whl"
        return {"file": file, "name": name, "version": version, "size": 23, "sha256": checksum or digest(file.encode())}

    candidate = [
        row("basepkg", "7.0"),
        row("cffi", "2.1.1", checksum=candidate_cffi, abi="cp314-cp314-android_24_arm64_v8a"),
        row("pycparser", "3.0"),
        row("setuptools", "83.0.0"),
    ]
    audio = [
        row("cffi", "2.1.1", checksum=audio_cffi, abi="cp314-cp314-android_24_arm64_v8a"),
        dict(candidate[2]),
        dict(candidate[3]),
        row("numpy", "2.4.3", abi="cp314-cp314-android_24_arm64_v8a"),
        row("sounddevice", "0.5.5"),
    ]
    policy = {
        "additions": ["numpy", "sounddevice"],
        "candidate_wins": {
            "cffi": {"candidate_sha256": candidate_cffi, "audio_sha256": audio_cffi}
        },
    }
    return candidate, audio, policy


def test_audio_union_preserves_candidate_cffi_and_every_base_row(wheel_union):
    candidate, audio, policy = wheel_union
    before_candidate = [dict(row) for row in candidate]
    before_audio = [dict(row) for row in audio]
    selected = staging.select_audio_wheels(candidate, audio, policy)
    actual = {row["name"]: row for row in selected}
    assert len(selected) == len(actual) == 6
    assert set(actual) == {"basepkg", "cffi", "pycparser", "setuptools", "numpy", "sounddevice"}
    for row in candidate:
        for field in ("file", "name", "version", "size", "sha256"):
            assert actual[row["name"]][field] == row[field]
    assert actual["cffi"]["sha256"] != audio[0]["sha256"]
    assert candidate == before_candidate and audio == before_audio


@pytest.mark.parametrize("side", ["candidate", "audio"])
def test_cffi_collision_exception_requires_both_exact_frozen_digests(wheel_union, side):
    candidate, audio, policy = wheel_union
    rows = candidate if side == "candidate" else audio
    next(row for row in rows if row["name"] == "cffi")["sha256"] = "f" * 64
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


def test_audio_union_rejects_same_name_with_a_different_version(wheel_union):
    candidate, audio, policy = wheel_union
    audio[0]["version"] = "9.0"
    audio[0]["file"] = "wheelhouse/cffi-9.0-cp314-cp314-android_24_arm64_v8a.whl"
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


def test_audio_union_rejects_unapproved_byte_replacement(wheel_union):
    candidate, audio, policy = wheel_union
    next(row for row in audio if row["name"] == "pycparser")["sha256"] = "e" * 64
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


def test_audio_union_rejects_an_unrequested_extra_package(wheel_union):
    candidate, audio, policy = wheel_union
    audio.append({"file": "wheelhouse/torch-9.0-py3-none-any.whl", "name": "torch", "version": "9.0", "size": 1, "sha256": "d" * 64})
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


@pytest.mark.parametrize("missing", ["numpy", "sounddevice"])
def test_audio_union_requires_the_complete_requested_audio_additions(wheel_union, missing):
    candidate, audio, policy = wheel_union
    audio = [row for row in audio if row["name"] != missing]
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


def test_audio_union_rejects_duplicate_candidate_catalog_identity(wheel_union):
    candidate, audio, policy = wheel_union
    candidate.append(dict(candidate[0]))
    with pytest.raises(staging.StagingError):
        staging.select_audio_wheels(candidate, audio, policy)


def test_audio_helper_import_keeps_the_existing_cua_candidate_pin():
    from scripts import fetch_compatibility_candidate as fetch

    preserved = "e271e922a2e71fd18591c45e9b98b8c7f9fffe02"
    assert fetch.PIN.head_sha == preserved
    assert fetch.IDENTITY["packaging_commit"] == preserved


def zip_fixture(entries):
    import io
    import warnings
    import zipfile
    import zlib

    stream = io.BytesIO()
    members = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data, mode in entries:
                info = zipfile.ZipInfo(name)
                info.filename = info.orig_filename = name
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
                members.append({"name": name, "size": len(data), "sha256": digest(data), "crc32": zlib.crc32(data)})
    raw = stream.getvalue()
    return raw, {"archive": {"size": len(raw), "sha256": digest(raw)}, "members": members}


@pytest.fixture
def pinned_zip(tmp_path):
    entries = [
        ("wheelhouse/array.whl", b"pinned array wheel", stat.S_IFREG | 0o644),
        ("runtime-libs/libportaudio.so.2", b"pinned native library", stat.S_IFREG | 0o644),
    ]
    raw, pin = zip_fixture(entries)
    path = tmp_path / "audio.zip"
    path.write_bytes(raw)
    return path, pin, entries


def test_original_archive_checks_all_members_without_extracting(pinned_zip):
    path, pin, _ = pinned_zip
    before = {p.name for p in path.parent.iterdir()}
    staging.verify_archive(path, pin)
    assert {p.name for p in path.parent.iterdir()} == before


def test_changed_archive_fails_its_frozen_outer_digest(pinned_zip):
    path, pin, _ = pinned_zip
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 1
    path.write_bytes(raw)
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)


@pytest.mark.parametrize("field", ["sha256", "crc32", "size"])
def test_archive_member_claims_are_independently_checked(pinned_zip, field):
    path, pin, _ = pinned_zip
    row = pin["members"][0]
    row[field] = {"sha256": "0" * 64, "crc32": 0, "size": row["size"] + 1}[field]
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)


def test_archive_cannot_add_an_unreviewed_member(pinned_zip):
    path, pin, entries = pinned_zip
    raw, expanded = zip_fixture([*entries, ("app/unreviewed.py", b"bad", stat.S_IFREG | 0o644)])
    path.write_bytes(raw)
    pin["archive"] = expanded["archive"]
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "app\\..\\outside"])
def test_archive_rejects_unsafe_names_even_with_matching_hashes(tmp_path, name):
    raw, pin = zip_fixture([(name, b"owner data", stat.S_IFREG | 0o644)])
    path = tmp_path / "unsafe.zip"
    path.write_bytes(raw)
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["unsafe.zip"]


def test_archive_rejects_duplicate_frozen_member_identity(tmp_path):
    entry = ("wheelhouse/array.whl", b"pinned", stat.S_IFREG | 0o644)
    raw, pin = zip_fixture([entry, entry])
    path = tmp_path / "duplicate.zip"
    path.write_bytes(raw)
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)


def test_archive_rejects_symlinks_even_with_matching_hashes(tmp_path):
    raw, pin = zip_fixture([("wheelhouse/array.whl", b"../../outside", stat.S_IFLNK | 0o777)])
    path = tmp_path / "symlink.zip"
    path.write_bytes(raw)
    with pytest.raises(staging.StagingError):
        staging.verify_archive(path, pin)


def test_duplicate_json_claims_are_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{"schema_version": 1, "entries": [], "entries": [{"path": "../escape"}]}')
    with pytest.raises(staging.StagingError, match="duplicate JSON"):
        staging.read_json(path)

# Destination recreation and provenance checks use tiny synthetic environments.
from scripts import prepare_audio_device_environment as native


def test_runtime_environment_preserves_home_and_scopes_all_runtime_state(tmp_path):
    root = tmp_path / "Hermes audio with spaces"
    before = {"HOME": "/home/original-user", "PYTHONPATH": "/ambient/modules", "PYTHONHOME": "/ambient/python",
              "LD_LIBRARY_PATH": "/ambient/lib", "LD_PRELOAD": "/ambient/inject.so",
              "UV_INDEX_URL": "https://unreviewed.invalid/simple", "PIP_CONFIG_FILE": "/ambient/pip.conf",
              "HERMES_HOME": "/home/original-user/.hermes", "HERMES_RUNTIME_DIR": "/installed/tools",
              "VIRTUAL_ENV": "/active/venv", "PATH": "/ambient/bin", "LANG": "C.UTF-8",
              "BASH_ENV": "/ambient/start.sh", "ENV": "/ambient/sh.conf"}
    env = native.runtime_environment(root, before)
    assert before["HERMES_HOME"] == "/home/original-user/.hermes"
    assert env["HOME"] == before["HOME"] and env["LANG"] == "C.UTF-8"
    assert env["HERMES_HOME"] == str(root / "state/profile")
    assert env["HERMES_RUNTIME_DIR"] == str(root / "tools")
    assert env["HERMES_DISABLE_LAZY_INSTALLS"] == "1"
    assert env["LD_LIBRARY_PATH"] == os.pathsep.join(str(root / name) for name in native.LIB_DIRS)
    for key in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "VIRTUAL_ENV", "UV_INDEX_URL",
                "PIP_CONFIG_FILE", "BASH_ENV", "ENV"):
        assert key not in env
    for key in ("TMPDIR", "TMP", "TEMP", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME", "UV_CACHE_DIR", "PYTHONPYCACHEPREFIX"):
        assert Path(env[key]).is_relative_to(root / "state")
    assert not root.exists()


@pytest.mark.parametrize("key", ["_PYTHON_HOST_PLATFORM", "_PYTHON_SYSCONFIGDATA_NAME",
                                 "_PYTHON_SYSCONFIGDATA_PATH"])
def test_runtime_rejects_architecture_override_before_state_changes(tmp_path, key):
    root = tmp_path / "destination"
    with pytest.raises(staging.StagingError, match="platform override"):
        native.runtime_environment(root, {"HOME": "/user", key: "pretend-android"})
    assert not root.exists()


def test_exact_app_inventory_preserves_all_baseline_versions_without_build_setuptools():
    lock = staging.read_json(Path(__file__).resolve().parents[1] / "scripts/audio_device_bundle_lock.json")
    expected = native.expected_versions(lock)
    assert len(expected) == 102 and "setuptools" not in expected
    assert expected["hermes-agent"] == "0.0.0"
    assert {name: expected[name] for name in lock["candidate"]["baseline_versions"]} == lock["candidate"]["baseline_versions"]
    assert {name: expected[name] for name in ("numpy", "sounddevice")} == {"numpy": "2.4.3", "sounddevice": "0.5.5"}


def test_source_pth_recreated_at_each_final_destination_with_spaces(tmp_path):
    for name in ("environment-a", "environment b with spaces"):
        root = tmp_path / name
        site = root / "venv" / native.SITE
        site.mkdir(parents=True)
        (root / "app/hermes_agent-0.0.0.dist-info").mkdir(parents=True)
        (root / "app/hermes_agent-0.0.0.dist-info/METADATA").write_text("Name: hermes-agent\nVersion: 0.0.0\n")
        native.add_source(root)
        relative = (site / "hermes-agent.pth").read_text().strip()
        assert not Path(relative).is_absolute()
        assert (site / relative).resolve() == root / "app"
        with pytest.raises(staging.StagingError, match="PTH already"):
            native.add_source(root)


@pytest.fixture
def generated_environment(tmp_path):
    root = tmp_path / "prepared environment"
    for name in ("venv", "pm-runtime", "tools", "state/cache"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "venv/module.py").write_bytes(b"PINNED = 17\n")
    (root / "pm-runtime/module.py").write_bytes(b"PINNED_PM = 23\n")
    (root / "tools/facts.json").write_bytes(b'{"packages": {}}\n')
    return root, native.environment_inventory(root)


def test_generated_environments_verified_separately_from_mutable_state(generated_environment):
    root, snapshot = generated_environment
    (root / "state/cache/new-cache-entry").write_text("mutable state")
    assert native.verify_generated_tree(root, snapshot)["mutable_state_path_guards"] == "passed"
    assert {row["path"] for row in snapshot["entries"]} == {
        "venv", "venv/module.py", "pm-runtime", "pm-runtime/module.py", "tools/facts.json"}


@pytest.mark.parametrize("damage", ["changed", "missing", "unexpected", "moved", "policy"])
def test_generated_environment_snapshot_rejects_mutation_and_relocation(generated_environment, damage):
    root, snapshot = generated_environment
    if damage == "changed":
        (root / "venv/module.py").write_bytes(b"CHANGED = 99\n")
    elif damage == "missing":
        (root / "pm-runtime/module.py").unlink()
    elif damage == "unexpected":
        (root / "venv/injected.pth").write_text("/ambient")
    elif damage == "moved":
        snapshot["root"] = str(root.parent / "another destination")
    else:
        snapshot["sealed_roots"].append("state")
    with pytest.raises(staging.StagingError):
        native.verify_generated_tree(root, snapshot)


def test_mutable_state_cannot_redirect_profile_outside_destination(generated_environment, tmp_path):
    root, snapshot = generated_environment
    outside = tmp_path / "real-user-profile"
    outside.mkdir()
    (root / "state/profile").symlink_to(outside, target_is_directory=True)
    with pytest.raises(staging.StagingError, match="state symlink escapes"):
        native.verify_generated_tree(root, snapshot)
    assert list(outside.iterdir()) == []


def test_environment_symlink_cannot_point_to_installed_candidate(generated_environment, tmp_path):
    root, _ = generated_environment
    outside = tmp_path / "installed-candidate"
    outside.mkdir()
    (outside / "module.py").write_text("original")
    (root / "venv/borrowed.py").symlink_to(outside / "module.py")
    with pytest.raises(staging.StagingError):
        native.environment_inventory(root)
    assert (outside / "module.py").read_text() == "original"


def csv_bytes(rows):
    import csv
    import io
    text = io.StringIO(newline="")
    csv.writer(text, lineterminator="\n").writerows(rows)
    return text.getvalue().encode()


def record_row(name, data):
    import base64
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return [name, "sha256=" + encoded, str(len(data))]


@pytest.fixture
def installed_audio_wheel(tmp_path):
    import zipfile
    root = tmp_path / "destination with spaces"
    site = root / "venv" / native.SITE
    bindir = root / "venv/bin"
    site.mkdir(parents=True)
    bindir.mkdir()
    (root / "wheelhouse").mkdir()
    prefix = "example-1.0.dist-info"
    contents = {
        "example.py": b"PINNED_VALUE = 7\n",
        prefix + "/METADATA": b"Metadata-Version: 2.4\nName: example\nVersion: 1.0\nRequires-Python: >=3.10\n",
        prefix + "/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        "example-1.0.data/scripts/example-command": b"#!python\nprint('pinned command')\n",
    }
    records = [record_row(name, data) for name, data in contents.items()]
    records.append([prefix + "/RECORD", "", ""])
    contents[prefix + "/RECORD"] = csv_bytes(records)
    wheel = root / "wheelhouse/example-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    installed_records = []
    for name, data in contents.items():
        if name.endswith("/RECORD"):
            continue
        if ".data/scripts/" in name:
            target = bindir / "example-command"
            data = b"#!/isolated/python\n" + data.split(b"\n", 1)[1]
            record_name = "../../../bin/example-command"
        else:
            target = site / name
            record_name = name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        installed_records.append(record_row(record_name, data))
    installer = site / prefix / "INSTALLER"
    installer.write_bytes(b"uv\n")
    installed_records.append(record_row(prefix + "/INSTALLER", b"uv\n"))
    installed_records.append([prefix + "/RECORD", "", ""])
    record = site / prefix / "RECORD"
    record.write_bytes(csv_bytes(installed_records))
    row = {"file": wheel.relative_to(root).as_posix(), "name": "example", "version": "1.0",
           "size": wheel.stat().st_size, "sha256": staging.file_digest(wheel)}
    return root, row, record, installed_records


def test_installed_wheel_checks_original_and_generated_record_members(installed_audio_wheel):
    root, row, record, _ = installed_audio_wheel
    before = record.read_bytes()
    result = native.installed_wheel(root, row)
    assert result["installed_member_count"] == 4
    assert result["installed_record_count"] == 6
    assert result["installed_record_sha256"] == digest(before)
    assert record.read_bytes() == before


@pytest.mark.parametrize("omission", ["all", "self", "module", "data-script"])
def test_installed_record_must_cover_every_original_target(installed_audio_wheel, omission):
    root, row, record, records = installed_audio_wheel
    if omission == "all":
        records = []
    elif omission == "self":
        records = [r for r in records if not r[0].endswith("/RECORD")]
    elif omission == "module":
        records = [r for r in records if r[0] != "example.py"]
    else:
        records = [r for r in records if r[0] != "../../../bin/example-command"]
    record.write_bytes(csv_bytes(records))
    with pytest.raises(staging.StagingError, match="RECORD omits"):
        native.installed_wheel(root, row)


def test_installed_record_rejects_duplicate_resolved_target(installed_audio_wheel):
    root, row, record, records = installed_audio_wheel
    alias = list(records[0])
    alias[0] = "./" + alias[0]
    record.write_bytes(csv_bytes(records + [alias]))
    with pytest.raises(staging.StagingError, match="duplicate resolved"):
        native.installed_wheel(root, row)


def test_installed_record_cannot_escape_venv(installed_audio_wheel, tmp_path):
    root, row, record, records = installed_audio_wheel
    outside = root / "outside.py"
    outside.write_bytes(b"DO_NOT_LOAD = True\n")
    records.append(record_row("../../../../outside.py", outside.read_bytes()))
    record.write_bytes(csv_bytes(records))
    with pytest.raises(staging.StagingError, match="escapes"):
        native.installed_wheel(root, row)


@pytest.mark.parametrize("relative", ["example.py", "example-1.0.dist-info/WHEEL", "example-1.0.dist-info/METADATA"])
def test_installed_original_bytes_cannot_be_changed_even_with_new_record(installed_audio_wheel, relative):
    root, row, record, records = installed_audio_wheel
    changed = b"replaced installed original member"
    (root / "venv" / native.SITE / relative).write_bytes(changed)
    records = [record_row(relative, changed) if item[0] == relative else item for item in records]
    record.write_bytes(csv_bytes(records))
    with pytest.raises(staging.StagingError, match="installed wheel bytes differ"):
        native.installed_wheel(root, row)


def test_installed_generated_member_hash_is_checked(installed_audio_wheel):
    root, row, _, _ = installed_audio_wheel
    (root / "venv" / native.SITE / "example-1.0.dist-info/INSTALLER").write_bytes(b"xy\n")
    with pytest.raises(staging.StagingError, match="RECORD content differs"):
        native.installed_wheel(root, row)


def test_active_graph_checks_requires_python_and_propagated_extras(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(native.platform, "python_version", lambda: "3.14.6")
    distributions = {
        "hermes-agent": SimpleNamespace(metadata={"Requires-Python": ">=3.11"}, requires=['middle[audio]>=1; extra == "audio-io"']),
        "middle": SimpleNamespace(metadata={"Requires-Python": ">=3.10"}, requires=['leaf>=2; extra == "audio"']),
        "leaf": SimpleNamespace(metadata={"Requires-Python": ">=3.10"}, requires=[]),
    }
    versions = {"hermes-agent": "0.0.0", "middle": "1.0", "leaf": "2.0"}
    graph = native.dependency_graph(distributions, versions, ["audio-io"])
    assert [(row["parent"], row["selected"]) for row in graph] == [("hermes-agent", "1.0"), ("middle", "2.0")]
    distributions["leaf"].metadata["Requires-Python"] = "<3.14"
    with pytest.raises(staging.StagingError, match="Requires-Python conflict"):
        native.dependency_graph(distributions, versions, ["audio-io"])


class FakeSoundDevice:
    def __init__(self, rows, default):
        from types import SimpleNamespace
        self.rows = rows
        self.default = SimpleNamespace(device=(default, -1))
        self.format_queries = []

    def query_devices(self):
        return self.rows

    def check_input_settings(self, **kwargs):
        self.format_queries.append(kwargs)

    def InputStream(self, **kwargs):
        raise AssertionError("readiness inventory must not open a microphone stream")


def test_audio_inventory_queries_formats_without_opening_streams():
    sd = FakeSoundDevice([{"name": "test input", "max_input_channels": 1, "default_samplerate": 48000.0}], 0)
    result = native.audio_input_inventory(sd)
    assert result["input_device_status"] == "available"
    assert result["default_input_device"] == 0
    assert [row["samplerate"] for row in result["supported_input_formats"]] == [16000.0, 48000.0]
    assert all(query["channels"] == 1 and query["dtype"] == "int16" for query in sd.format_queries)


def test_audio_inventory_can_truthfully_report_no_default_input():
    sd = FakeSoundDevice([], -1)
    result = native.audio_input_inventory(sd)
    assert result["input_device_status"] == "unavailable" and sd.format_queries == []


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), -1.0, 0.0])
def test_audio_inventory_rejects_invalid_or_nonfinite_rates(rate):
    sd = FakeSoundDevice([{"name": "test", "max_input_channels": 1, "default_samplerate": rate}], 0)
    with pytest.raises(staging.StagingError, match="sample rate"):
        native.audio_input_inventory(sd)


def test_audio_inventory_does_not_swallow_unknown_driver_errors():
    sd = FakeSoundDevice([{"name": "test", "max_input_channels": 1, "default_samplerate": 48000.0}], 0)
    def broken(**kwargs):
        raise RuntimeError("unclassified driver failure")
    sd.check_input_settings = broken
    with pytest.raises(staging.StagingError, match="unexpected input-format"):
        native.audio_input_inventory(sd)


def test_tar_manifest_rejects_symlink_parent_before_extraction():
    entries = {
        "app": {"path": "app", "kind": "directory", "mode": 0o755},
        "outside": {"path": "outside", "kind": "directory", "mode": 0o755},
        "app/link": {"path": "app/link", "kind": "symlink", "mode": 0o777, "target": "../outside"},
        "app/link/injected.py": {"path": "app/link/injected.py", "kind": "file", "mode": 0o644, "size": 1, "sha256": digest(b"x")},
    }
    with pytest.raises(staging.StagingError):
        staging.validate_entry_relationships(entries)


def test_tar_manifest_rejects_cyclic_relative_links():
    entries = {
        "app": {"path": "app", "kind": "directory", "mode": 0o755},
        "app/first": {"path": "app/first", "kind": "symlink", "mode": 0o777, "target": "second"},
        "app/second": {"path": "app/second", "kind": "symlink", "mode": 0o777, "target": "first"},
    }
    with pytest.raises(staging.StagingError):
        staging.validate_entry_relationships(entries)


def test_portaudio_resolver_binds_exact_library_and_delegates_every_other_name(tmp_path, monkeypatch):
    import ctypes.util
    root = tmp_path / "destination with spaces"
    library = root / "runtime-libs/lib/libportaudio.so.2"
    library.parent.mkdir(parents=True)
    raw = b"verified test PortAudio bytes"
    library.write_bytes(raw)
    pin = {"size": len(raw), "sha256": digest(raw)}
    delegated = []
    def original(name):
        delegated.append(name)
        return "existing-result:" + name
    monkeypatch.setattr(ctypes.util, "find_library", original)
    namespace = {"__name__": "sitecustomize"}
    before = set(__import__("sys").modules)
    exec(compile(native.audio_resolver_source(root, pin), "<owned resolver>", "exec"), namespace)
    assert ctypes.util.find_library("portaudio") == str(library)
    assert ctypes.util.find_library("m") == "existing-result:m"
    assert ctypes.util.find_library("portaudio_other") == "existing-result:portaudio_other"
    assert delegated == ["m", "portaudio_other"]
    assert "sounddevice" not in set(__import__("sys").modules) - before
    library.write_bytes(b"changed test PortAudio bytes")
    with pytest.raises(OSError, match="failed verification"):
        ctypes.util.find_library("portaudio")


def test_audio_resolver_refuses_symlinked_library_even_with_correct_bytes(tmp_path, monkeypatch):
    import ctypes.util
    root = tmp_path / "isolated"
    library = root / "runtime-libs/lib/libportaudio.so.2"
    library.parent.mkdir(parents=True)
    target = tmp_path / "ambient-library"
    raw = b"same bytes are not same ownership"
    target.write_bytes(raw)
    library.symlink_to(target)
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "original")
    with pytest.raises(OSError, match="failed verification"):
        exec(native.audio_resolver_source(root, {"size": len(raw), "sha256": digest(raw)}), {"__name__": "sitecustomize"})
    assert target.read_bytes() == raw


def test_audio_resolver_is_recreated_for_each_final_root(tmp_path):
    pin = {"size": 1, "sha256": "a" * 64}
    first, second = tmp_path / "one", tmp_path / "two with spaces"
    one, two = native.audio_resolver_source(first, pin), native.audio_resolver_source(second, pin)
    assert one != two
    assert repr(str(first)).encode() in one and repr(str(first)).encode() not in two
    assert repr(str(second)).encode() in two and repr(str(second)).encode() not in one


@pytest.fixture
def assembled_receipts(generated_environment, monkeypatch):
    root, snapshot = generated_environment
    (root / "staging").mkdir()
    (root / "bin").mkdir()
    (root / native.MANIFEST).write_bytes(b'{"test": "frozen bundle"}\n')
    native.write_json(root / native.ENVIRONMENT, snapshot)
    native.write_json(root / native.VALIDATION, {"status": "passed", "test": "original"})
    expected = {"example": "1.0"}
    monkeypatch.setattr(native, "load_bundle", lambda root: {"lock": {}})
    monkeypatch.setattr(native, "expected_versions", lambda lock: expected)
    receipt = {"schema_version": 1, "status": "passed", "root": str(root),
               "bundle_manifest_sha256": staging.file_digest(root / native.MANIFEST),
               "environment_manifest_sha256": staging.file_digest(root / native.ENVIRONMENT),
               "native_validation_sha256": staging.file_digest(root / native.VALIDATION),
               "versions": expected, "claims": native.claims()}
    native.write_json(root / native.RECEIPT, receipt)
    manifest_sha, receipt_sha = staging.file_digest(root / native.MANIFEST), staging.file_digest(root / native.RECEIPT)
    launcher = root / "bin/audio-python"
    launcher.write_bytes(native.launcher_bytes(root, manifest_sha, receipt_sha))
    launcher.chmod(0o755)
    return root, manifest_sha, receipt_sha


def test_launcher_receipts_bind_complete_generated_environment(assembled_receipts):
    root, manifest_sha, receipt_sha = assembled_receipts
    _, receipt = native.verify_receipts(root, manifest_sha=manifest_sha, receipt_sha=receipt_sha)
    assert receipt["status"] == "passed"


@pytest.mark.parametrize("member", [native.MANIFEST, native.RECEIPT, native.ENVIRONMENT,
                                    native.VALIDATION, "bin/audio-python"])
def test_launcher_refuses_corrupted_binding_or_receipt(assembled_receipts, member):
    root, manifest_sha, receipt_sha = assembled_receipts
    path = root / member
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(staging.StagingError):
        native.verify_receipts(root, manifest_sha=manifest_sha, receipt_sha=receipt_sha)


def test_launcher_refuses_unreviewed_generated_executable(assembled_receipts):
    root, manifest_sha, receipt_sha = assembled_receipts
    (root / "bin/other-command").write_text("unreviewed")
    with pytest.raises(staging.StagingError, match="unexpected generated launcher"):
        native.verify_receipts(root, manifest_sha=manifest_sha, receipt_sha=receipt_sha)


def test_assembly_native_guard_runs_before_creating_state(tmp_path, monkeypatch):
    root = tmp_path / "fresh destination"
    python = root / "tools/python/bin/python"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"frozen executable test input")
    lock = {"runtime": {"python": {"file": "tools/python/bin/python", "size": python.stat().st_size,
                                   "sha256": staging.file_digest(python)}, "sys_platform": "android",
                        "machine": ["aarch64", "arm64"], "python_version": [3, 14, 6],
                        "sysconfig_platform": "android-24-arm64_v8a"}}
    monkeypatch.setattr(native, "load_bundle", lambda path: {"lock": lock})
    monkeypatch.setattr(native.sys, "platform", "host-test")
    with pytest.raises(staging.StagingError, match="native Android"):
        native.assemble(root)
    assert not (root / "state").exists() and not (root / "venv").exists()
    assert python.read_bytes() == b"frozen executable test input"


@pytest.mark.parametrize("code", [-9998, -9997, -9994])
def test_audio_inventory_classifies_exact_portaudio_format_rejections(code):
    class PortAudioError(Exception):
        pass
    sd = FakeSoundDevice([{"name": "test", "max_input_channels": 1, "default_samplerate": 48000.0}], 0)
    def unsupported(**kwargs):
        raise PortAudioError("unsupported requested format", code)
    sd.check_input_settings = unsupported
    result = native.audio_input_inventory(sd)
    assert result["input_device_status"] == "unsupported"
    assert all(row["status"] == "unsupported" and row["portaudio_code"] == code
               for row in result["supported_input_formats"])
