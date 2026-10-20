"""Source/provenance and dependency regressions; no native compatibility claim."""
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest
from pip._internal.metadata import get_environment
from pip._internal.operations import check as pip_check
from pip._vendor.packaging import markers, requirements, specifiers, tags, utils, version

from scripts import validate_neutts_apt_python as validator

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "scripts/neutts_apt_python_metadata.json"


@pytest.fixture
def ledger():
    return validator.load_manifest(LEDGER)


def target_environment():
    return {
        **markers.default_environment(), "python_full_version": "3.14.6",
        "python_version": "3.14", "sys_platform": "android",
        "platform_system": "Android", "platform_machine": "aarch64",
    }


def distribution(site, name, ver="1.0", requires=(), requires_python=None, *, directory=None):
    folder = site / (directory or (name.replace("-", "_") + "-" + ver + ".dist-info"))
    folder.mkdir(parents=True)
    text = f"Metadata-Version: 2.4\nName: {name}\nVersion: {ver}\n"
    if requires_python:
        text += f"Requires-Python: {requires_python}\n"
    text += "".join(f"Requires-Dist: {r}\n" for r in requires)
    (folder / "METADATA").write_text(text + "\n", encoding="utf-8")
    (folder / "WHEEL").write_text("Wheel-Version: 1.0\nTag: py3-none-any\n", encoding="utf-8")
    return folder


def inventory(site):
    return validator.read_metadata_inventory(
        importlib.metadata.distributions(path=[str(site)]), site,
        requirements, specifiers, version, utils, target_environment(),
    )


def native_tag_fixtures(ledger):
    supported = set(tags.cpython_tags((3, 14), ["cp314"], ["android_arm64_v8a", "android_24_arm64_v8a"]))
    fixtures, installed = [], {}
    for row in ledger["apt_distributions"]:
        text = "Wheel-Version: 1.0\n" + "".join(f"Tag: {t}\n" for t in row["wheel"]["tags"])
        fixtures.append(SimpleNamespace(
            canonical_name=row["name"], raw_name=row["name"],
            version=version.Version(row["version"]),
            info_location=str(Path(row["metadata"]["path"]).parent),
            read_text=lambda name, text=text: text,
        ))
        installed[row["name"]] = {"metadata_path": row["metadata"]["path"]}
    return fixtures, supported, installed


def tar_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as stream:
        for name, raw in files:
            member = tarfile.TarInfo(name)
            if raw is None:
                member.type = tarfile.SYMTYPE
                member.linkname = "elsewhere"
                stream.addfile(member)
            else:
                member.size = len(raw)
                stream.addfile(member, io.BytesIO(raw))
    return buffer.getvalue()


def ar_entry(name, raw):
    header = (f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(raw):<10}" + "\x60\n").encode()
    assert len(header) == 60
    return header + raw + (b"\n" if len(raw) % 2 else b"")


def apt_fixture(tmp_path, *, control_extra="", files=None):
    control = (
        "Package: python-fixture\nVersion: 1.0-1\nArchitecture: aarch64\n"
        "Depends: python\n" + control_extra
    ).encode()
    desired = "/data/data/com.termux/files/usr/lib/python3.14/site-packages/fixture-1.0.dist-info/WHEEL"
    raw_wheel = b"Wheel-Version: 1.0\nTag: cp314-cp314-android_aarch64\n"
    if files is None:
        files = [("." + desired, raw_wheel)]
    raw = b"!<arch>\n" + ar_entry("debian-binary", b"2.0\n")
    raw += ar_entry("control.tar.gz", tar_bytes([("./control", control)]))
    raw += ar_entry("data.tar.gz", tar_bytes(files))
    path = tmp_path / "python-fixture_1.0-1_aarch64.deb"
    path.write_bytes(raw)
    pin = {
        "package": "python-fixture", "bytes": len(raw), "sha256": validator.digest(raw),
        "control": {"Package": "python-fixture", "Version": "1.0-1", "Architecture": "aarch64",
                    "Depends": "python", "Pre-Depends": None},
    }
    return path, pin, desired, raw_wheel


def test_frozen_ledger_binds_all_seven_original_tags_and_python_pip_sources(ledger):
    assert {r["name"] for r in ledger["apt_distributions"]} == validator.APT_NAMES
    for row in ledger["apt_distributions"]:
        assert row["apt"]["control"]["Architecture"] == "aarch64"
        assert row["wheel"]["tags"] == [
            "cp312-abi3-android_aarch64" if row["name"] == "soxr" else "cp314-cp314-android_aarch64"
        ]
    assert {p["package"] for p in ledger["runtime"]["archives"]} == {"python", "python-pip"}
    changed = LEDGER.read_bytes() + b" "
    assert validator.digest(changed) != validator.MANIFEST_SHA256


def test_modified_ledger_cannot_expand_the_allowed_platform_exception(tmp_path, ledger):
    ledger["apt_distributions"][0]["wheel"]["tags"] = ["cp314-cp314-linux_aarch64"]
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="ledger differs"):
        validator.load_manifest(path)


def test_exact_archive_reads_original_metadata_without_extracting(tmp_path):
    path, pin, desired, original = apt_fixture(tmp_path)
    before = path.read_bytes()
    assert validator.inspect_archive(path, pin, {desired}) == {desired: original}
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_archive_byte_corruption_fails_before_metadata_is_used(tmp_path):
    path, pin, desired, _ = apt_fixture(tmp_path)
    raw = bytearray(path.read_bytes())
    raw[-5] ^= 1
    path.write_bytes(raw)
    with pytest.raises(validator.ValidationError, match="archive bytes differ"):
        validator.inspect_archive(path, pin, {desired})


def test_control_identity_is_checked_even_with_a_matching_archive_digest(tmp_path):
    path, pin, desired, _ = apt_fixture(tmp_path, control_extra="Pre-Depends: unreviewed\n")
    with pytest.raises(validator.ValidationError, match="control identity differs"):
        validator.inspect_archive(path, pin, {desired})


@pytest.mark.parametrize("kind", ["missing", "symlink", "duplicate", "traversal"])
def test_unusable_or_ambiguous_metadata_members_are_rejected(tmp_path, kind):
    wanted = "/data/data/com.termux/files/usr/lib/python3.14/site-packages/fixture-1.0.dist-info/WHEEL"
    files = {
        "missing": [("./unrelated", b"fixture")],
        "symlink": [("." + wanted, None)],
        "duplicate": [("." + wanted, b"first"), ("." + wanted, b"second")],
        "traversal": [("./../outside", b"fixture"), ("." + wanted, b"fixture")],
    }[kind]
    path, pin, desired, _ = apt_fixture(tmp_path, files=files)
    with pytest.raises(validator.ValidationError):
        validator.inspect_archive(path, pin, {desired})


@pytest.mark.parametrize("owners", [[], ["pip"], ["python-fixture", "python-other"]])
def test_installer_text_does_not_substitute_for_unique_apt_ownership(tmp_path, owners):
    original = b"Name: fixture\nVersion: 1.0\n"
    path = tmp_path / "fixture" / "METADATA"
    path.parent.mkdir()
    path.write_bytes(original)
    (path.parent / "INSTALLER").write_bytes(b"pip\n")
    expected = {"/fixture/METADATA": {"bytes": len(original), "sha256": validator.digest(original),
                                      "package": "python-fixture"}}
    with pytest.raises(validator.ValidationError, match="ownership differs"):
        validator.verify_installed_files(expected, {"/fixture/METADATA": owners}, root=tmp_path)
    assert path.read_bytes() == original


def test_installed_metadata_must_match_archive_bytes_not_only_dpkg_owner(tmp_path):
    path = tmp_path / "METADATA"
    path.write_bytes(b"Name: changed\n")
    expected = {"/METADATA": {"bytes": len(b"Name: fixture\n"), "sha256": validator.digest(b"Name: fixture\n"),
                              "package": "python-fixture"}}
    with pytest.raises(validator.ValidationError, match="bytes differ"):
        validator.verify_installed_files(expected, {"/METADATA": ["python-fixture"]}, root=tmp_path)


def test_same_name_in_multiple_dist_info_directories_is_not_silently_overwritten(tmp_path):
    distribution(tmp_path, "typing-extensions", "4.16.0")
    distribution(tmp_path, "typing_extensions", "4.10.0", directory="shadow-1.0.dist-info")
    with pytest.raises(validator.ValidationError, match="Duplicate distribution"):
        inventory(tmp_path)


def test_actual_requires_python_exclusion_is_enforced_independently_of_pip_check(tmp_path):
    distribution(tmp_path, "fixture", requires_python=">=3.10,<3.14")
    with pytest.raises(validator.ValidationError, match="Requires-Python is incompatible"):
        inventory(tmp_path)


def test_invalid_requirement_is_not_ignored(tmp_path):
    distribution(tmp_path, "fixture", requires=("typing-extensions=>4",))
    with pytest.raises(requirements.InvalidRequirement):
        inventory(tmp_path)


def test_base_only_scope_evaluates_native_markers_without_admitting_extra_dependencies(tmp_path):
    distribution(tmp_path, "fixture", requires=(
        'missing-docs; extra == "docs"',
        'typing-extensions>=4.10; sys_platform == "android"',
    ))
    result = inventory(tmp_path)
    assert result["fixture"]["active_requires_dist"] == ['typing-extensions>=4.10; sys_platform == "android"']


def test_active_extra_dependency_requires_an_explicit_new_reviewed_scope(tmp_path):
    distribution(tmp_path, "fixture", requires=("dependency[unreviewed]>=1",))
    with pytest.raises(validator.ValidationError, match="base-only scope"):
        inventory(tmp_path)


def test_real_pip_dependency_api_detects_missing_then_accepts_complete_closure(tmp_path, monkeypatch):
    distribution(tmp_path, "native-fixture", requires=("typing-extensions>=4.10.0",))
    monkeypatch.setattr(pip_check, "get_default_environment", lambda: get_environment([str(tmp_path)]))
    with pytest.raises(validator.ValidationError, match="requirements are inconsistent") as missing:
        validator.check_dependency_graph(pip_check, inventory(tmp_path))
    assert "native-fixture" in missing.value.details["missing"]
    distribution(tmp_path, "typing-extensions", "4.16.0")
    result = validator.check_dependency_graph(pip_check, inventory(tmp_path))
    assert result["status"] == "passed"
    assert result["missing"] == result["conflicting"] == {}
    assert result["ignore_callback_used"] is False


def test_real_pip_dependency_api_rejects_a_present_but_conflicting_version(tmp_path, monkeypatch):
    distribution(tmp_path, "native-fixture", requires=("typing-extensions>=4.10.0",))
    distribution(tmp_path, "typing-extensions", "4.9.0")
    monkeypatch.setattr(pip_check, "get_default_environment", lambda: get_environment([str(tmp_path)]))
    with pytest.raises(validator.ValidationError) as conflict:
        validator.check_dependency_graph(pip_check, inventory(tmp_path))
    assert "native-fixture" in conflict.value.details["conflicting"]


def test_pip_metadata_read_failure_is_a_failure_even_without_missing_or_conflicting(tmp_path, monkeypatch):
    distribution(tmp_path, "native-fixture")
    real_environment = get_environment([str(tmp_path)])
    real_distributions = list(real_environment.iter_installed_distributions(local_only=False, skip=()))
    bad = real_distributions[0]

    def unreadable_dependencies(extras=()):
        raise OSError("unreadable METADATA fixture")

    monkeypatch.setattr(bad, "iter_dependencies", unreadable_dependencies)
    monkeypatch.setattr(pip_check, "get_default_environment", lambda: SimpleNamespace(
        iter_installed_distributions=lambda **kwargs: iter([bad])
    ))
    with pytest.raises(validator.ValidationError) as failure:
        validator.check_dependency_graph(pip_check, inventory(tmp_path))
    assert failure.value.details["parsing_problems"] is True


def test_exact_legacy_apt_tags_are_reported_without_changing_metadata_or_native_tags(ledger):
    fixtures, supported, installed = native_tag_fixtures(ledger)
    before = set(supported)
    originals = [d.read_text("WHEEL") for d in fixtures]
    rejected = list(pip_check.check_unsupported(fixtures, list(supported)))
    result = validator.check_tag_convention(rejected, supported, ledger, tags, installed)
    assert len(result["distributions"]) == 7
    assert supported == before
    assert [d.read_text("WHEEL") for d in fixtures] == originals
    assert all(not d["metadata_modified"] and not d["supported_tags_modified"]
               for d in result["distributions"])
    soxr = next(d for d in result["distributions"] if d["distribution"] == "soxr")
    assert soxr["native_convention_tags"] == ["cp312-abi3-android_arm64_v8a"]


def test_unknown_unsupported_distribution_cannot_use_the_apt_exception(ledger):
    fixtures, supported, installed = native_tag_fixtures(ledger)
    unknown = SimpleNamespace(canonical_name="unreviewed", raw_name="unreviewed", version=version.Version("1"),
                              read_text=lambda name: "Tag: cp314-cp314-android_aarch64\n")
    with pytest.raises(validator.ValidationError, match="Unknown"):
        validator.check_tag_convention([*fixtures, unknown], supported, ledger, tags, installed)


def test_architecture_alias_cannot_hide_a_cpython_abi_mismatch(ledger):
    fixtures, _, installed = native_tag_fixtures(ledger)
    wrong_abi = set(tags.cpython_tags((3, 13), ["cp313"], ["android_arm64_v8a"]))
    with pytest.raises(validator.ValidationError, match="interpreter/ABI"):
        validator.check_tag_convention(fixtures, wrong_abi, ledger, tags, installed)


def test_version_drift_and_missing_convention_rows_fail_closed(ledger):
    fixtures, supported, installed = native_tag_fixtures(ledger)
    fixtures[0].version = version.Version("999")
    with pytest.raises(validator.ValidationError, match="identity differs"):
        validator.check_tag_convention(fixtures, supported, ledger, tags, installed)
    fixtures, supported, installed = native_tag_fixtures(ledger)
    with pytest.raises(validator.ValidationError, match="exact seven"):
        validator.check_tag_convention(fixtures[:-1], supported, ledger, tags, installed)


def test_retained_pip_failure_is_never_relabelled_as_a_pip_pass(tmp_path, ledger):
    path = tmp_path / "pip.log"
    original = "".join(f"{r['name']} {r['version']} is not supported on this platform\n"
                       for r in ledger["apt_distributions"])
    path.write_bytes(original.encode())
    result = validator.raw_pip_record(path, 1, ledger)
    assert result["exit_code"] == 1 and result["passed"] is False
    assert result["text"] == original
    assert path.read_bytes() == original.encode()


@pytest.mark.parametrize("extra", ["native-fixture requires missing, which is not installed.\n", "\n"])
def test_extra_pip_diagnostics_are_not_discarded(tmp_path, ledger, extra):
    path = tmp_path / "pip.log"
    path.write_text("".join(f"{r['name']} {r['version']} is not supported on this platform\n"
                           for r in ledger["apt_distributions"]) + extra, encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="Raw pip check differs"):
        validator.raw_pip_record(path, 1, ledger)


def test_cli_refuses_the_real_host_without_touching_archives_or_claiming_native_success(tmp_path):
    if sys.platform == "android":
        pytest.skip("This rejection is specifically for an actual non-Android host")
    receipt = tmp_path / "receipt.json"
    completed = subprocess.run([
        sys.executable, "-I", "-B", str(ROOT / "scripts/validate_neutts_apt_python.py"),
        "--archives", str(tmp_path / "not-present"), "--metadata", str(LEDGER),
        "--pip-check-log", str(tmp_path / "not-present.log"), "--pip-check-exit-code", "1",
        "--out", str(receipt),
    ], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 1
    result = json.loads(receipt.read_text())
    assert result["status"] == "failed"
    assert "actual native Termux" in result["error"]["message"]
    assert result["overall_compatibility_passed"] is False
    assert result["native_behavior"]["status"] == "required-pending"
    assert list(tmp_path.iterdir()) == [receipt]


def test_existing_receipt_cannot_be_reused_or_overwritten(tmp_path):
    receipt = tmp_path / "receipt.json"
    original = b'{"unrelated": "prior result"}\n'
    receipt.write_bytes(original)
    assert validator.main([
        "--archives", str(tmp_path), "--metadata", str(LEDGER),
        "--pip-check-log", str(tmp_path / "pip.log"), "--pip-check-exit-code", "1",
        "--out", str(receipt),
    ]) == 1
    assert receipt.read_bytes() == original


def test_dependency_api_cannot_silently_drop_a_declared_requirement(tmp_path, monkeypatch):
    distribution(tmp_path, "native-fixture", requires=("typing-extensions>=4.10.0",))
    distribution(tmp_path, "typing-extensions", "4.16.0")
    monkeypatch.setattr(pip_check, "get_default_environment", lambda: get_environment([str(tmp_path)]))
    package_set, errors = pip_check.create_package_set_from_installed()
    package_set["native-fixture"] = pip_check.PackageDetails(version.Version("1.0"), [])
    altered_api = SimpleNamespace(
        create_package_set_from_installed=lambda: (package_set, errors),
        check_package_set=pip_check.check_package_set,
    )
    with pytest.raises(validator.ValidationError, match="different requirement metadata"):
        validator.check_dependency_graph(altered_api, inventory(tmp_path))


def test_original_apt_parser_verifies_unlisted_pip_source_members_too(tmp_path):
    desired = "/data/data/com.termux/files/usr/lib/python3.14/site-packages/fixture-1.0.dist-info/WHEEL"
    pip_source = "/data/data/com.termux/files/usr/lib/python3.14/site-packages/pip/_internal/fixture.py"
    wheel = b"Wheel-Version: 1.0\\n"
    source = b"APT_SOURCE_SENTINEL = True\\n"
    path, pin, _, _ = apt_fixture(tmp_path, files=[("." + desired, wheel), ("." + pip_source, source)])
    result = validator.inspect_archive(path, pin, {desired}, include_pip=True)
    assert result == {desired: wheel, pip_source: source}


def test_apt_dependency_failure_keeps_raw_diagnostics_and_fails_admission(monkeypatch):
    def run(command, **kwargs):
        assert command[-1] == "check" and "--simulate" in command
        assert "Dir::Cache::pkgcache=" in command and "Dir::Cache::srcpkgcache=" in command
        assert kwargs["timeout"] == 30 and kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, 100, b"Checking dependencies\\n",
                                           b"python-torchaudio: Depends: python-torch but it is not installed\\n")
    monkeypatch.setattr(validator.subprocess, "run", run)
    report = {}
    with pytest.raises(validator.ValidationError, match="APT dependency graph") as failure:
        validator.check_apt_dependencies(report)
    assert report["apt_dependencies"]["exit_code"] == 100
    assert "python-torch" in report["apt_dependencies"]["stderr"]
    assert report["apt_dependencies"]["status"] == "failed"
    assert failure.value.details == report["apt_dependencies"]


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("apt-get", 30, output=b"partial apt output", stderr=b"partial error"),
    FileNotFoundError("missing APT executable"),
])
def test_apt_timeout_or_launch_failure_cannot_be_a_dependency_pass(monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(validator.subprocess, "run", run)
    report = {}
    with pytest.raises(validator.ValidationError, match="APT dependency graph"):
        validator.check_apt_dependencies(report)
    assert report["apt_dependencies"]["status"] == "failed"
    assert report["apt_dependencies"]["exit_code"] is None
    if isinstance(failure, subprocess.TimeoutExpired):
        assert report["apt_dependencies"]["timed_out"] is True
        assert report["apt_dependencies"]["stdout"] == "partial apt output"
    else:
        assert report["apt_dependencies"]["launch_error"]["type"] == "FileNotFoundError"


def test_apt_check_success_is_only_an_apt_dependency_result(monkeypatch):
    monkeypatch.setattr(validator.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, b"Reading package lists... Done\\n", b""
    ))
    report = {}
    result = validator.check_apt_dependencies(report)
    assert result["status"] == "passed" and result["exit_code"] == 0
    assert "overall_compatibility_passed" not in result
    assert list(report) == ["apt_dependencies"]
