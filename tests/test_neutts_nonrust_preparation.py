"""Host-only contracts for the six source preparations and native evidence gates.

These checks do not import target extensions, emulate Android, authenticate an
APT index, install dependencies, or claim native compilation/speech synthesis.
The native component workflow must produce its own independent receipts.
"""
from __future__ import annotations

import base64
import copy
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREP = load_module("_test_nonrust_preparation", "scripts/prepare_neutts_nonrust_runtime.py")
NATIVE = load_module("_test_nonrust_native", "scripts/compatibility_probe_neutts_nonrust.py")
LOCK, _ = PREP.load_lock(ROOT / "scripts/neutts_nonrust_runtime_lock.json")
SENTENCEPIECE = next(s for s in LOCK["sources"] if s["name"] == "sentencepiece")
BASELINE = ROOT / "tests/fixtures/neutts_nonrust/sentencepiece_build_bundled.sh"
PATCH = ROOT / "patches/next-stable/sentencepiece-bounded-build.patch"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def test_entire_subset_is_unchanged_in_the_frozen_parent_graph():
    path = ROOT / "scripts/neutts_runtime_closure_design.json"
    raw = path.read_bytes()
    assert digest(raw) == "d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68"
    parent = json.loads(raw)
    fields = ("name", "version", "requires_dist", "requires_python", "active_extras")
    expected = [{key: node[key] for key in fields} for node in parent["nodes"] if node["name"] in LOCK["names"]]
    assert LOCK["nodes"] == expected
    assert LOCK["edges"] == [e for e in parent["edges"] if e["from"] in LOCK["names"]]
    assert len(LOCK["names"]) == 14
    assert len(LOCK["edges"]) == 10


@pytest.mark.parametrize("root,count,expected", [
    ("audioop-lts", 1, {"audioop-lts"}),
    ("pyyaml", 1, {"pyyaml"}),
    ("pycryptodomex", 1, {"pycryptodomex"}),
    ("sentencepiece", 1, {"sentencepiece"}),
    ("pandas", 4, {"pandas", "numpy", "python-dateutil", "six"}),
    ("scikit-learn", 7, {"scikit-learn", "numpy", "scipy", "joblib", "cloudpickle", "narwhals", "threadpoolctl"}),
])
def test_complete_independent_runtime_subsets(root, count, expected):
    actual = NATIVE.closure_names(LOCK, [root])
    assert actual == expected and len(actual) == count


def test_combined_runtime_is_exactly_fourteen():
    assert NATIVE.closure_names(LOCK, NATIVE.ORDER) == set(LOCK["names"])


def test_an_unreviewed_component_is_rejected():
    with pytest.raises(NATIVE.ProbeError, match="Unreviewed component"):
        NATIVE.closure_names(LOCK, ["different-package"])


def test_all_declared_build_dependencies_have_the_frozen_versions():
    versions = {p["name"]: p["version"] for p in LOCK["build_packages"] + LOCK["apt_python"]}
    assert len(versions) == 11
    assert versions["cython"] == "3.2.5"
    for source in LOCK["sources"]:
        rows = NATIVE.validate_build_requirements(source["build_requires"], versions, LOCK["environment"])
        assert rows
        assert all(r["selected_version"] for r in rows if r["active"])
    for package in LOCK["build_packages"]:
        extras = ("toml",) if package["name"] == "versioneer" else ("",)
        rows = NATIVE.validate_build_requirements(package["requires_dist"], versions, LOCK["environment"], extras)
        assert all(r["selected_version"] for r in rows if r["active"])


@pytest.mark.parametrize("requirement,versions", [
    ("absent>=1", {}),
    ("cython<3", {"cython": "3.2.5"}),
    ("thing @ https://example.invalid/package.whl", {"thing": "1"}),
])
def test_build_closure_never_silently_drops_an_active_dependency(requirement, versions):
    with pytest.raises(NATIVE.ProbeError):
        NATIVE.validate_build_requirements([requirement], versions, LOCK["environment"])


def test_marker_and_extra_activation_preserves_declared_requirements():
    rows = NATIVE.validate_build_requirements(
        ['tomli; python_version < "3.11"', 'setuptools>=61; extra == "toml"'],
        {"setuptools": "83.0.0"}, LOCK["environment"], ("toml",))
    assert [r["active"] for r in rows] == [False, True]
    assert [r["requirement"] for r in rows] == [
        'tomli; python_version < "3.11"', 'setuptools>=61; extra == "toml"']


def test_clean_environment_removes_cross_target_and_unsafe_feature_overrides(monkeypatch):
    for key in ("_PYTHON_HOST_PLATFORM", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD",
                "SKLEARN_NO_OPENMP", "CMAKE_TOOLCHAIN_FILE", "MESON_CROSS_FILE",
                "LDSHARED", "PIP_INDEX_URL"):
        monkeypatch.setenv(key, "unreviewed")
    monkeypatch.setenv("OMP_NUM_THREADS", "128")
    monkeypatch.setenv("CXXFLAGS", "-march=native")
    environment = NATIVE.clean_environment(LOCK, Path("/isolated/bin/python"))
    for key in ("_PYTHON_HOST_PLATFORM", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD",
                "SKLEARN_NO_OPENMP", "CMAKE_TOOLCHAIN_FILE", "MESON_CROSS_FILE", "LDSHARED", "PIP_INDEX_URL"):
        assert key not in environment
    assert environment["CXXFLAGS"] == LOCK["build"]["cflags"]
    assert environment["CMAKE_BUILD_PARALLEL_LEVEL"] == environment["OMP_NUM_THREADS"] == "2"
    assert environment["OMP_DYNAMIC"] == "FALSE"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["PIP_NO_INDEX"] == "1"


def test_only_two_archives_are_new_and_original_compiler_pins_have_no_drift():
    original = json.loads((ROOT / "scripts/neutts_native_sources_lock.json").read_bytes())
    expected = {p["name"]: p for p in original["build_apt"]["packages"]}
    current = {p["name"]: p for p in LOCK["build_apt"]["packages"]}
    assert len(expected) == 44 and len(current) == 51
    for name, old in expected.items():
        for field in ("version", "architecture", "sha256", "bytes", "filename"):
            assert current[name][field] == old[field]
    assert {p["name"] for p in LOCK["build_apt"]["additional_to_141"]} == {"libyaml", "patchelf"}
    assert sum(p["bytes"] for p in LOCK["build_apt"]["additional_to_141"]) == 129424
    assert sum(p["additional"] for p in current.values()) == 21


def test_complete_copied_apt_python_payloads_preserve_original_metadata():
    wanted = {"numpy": (924, 18943738), "scipy": (1429, 56745210)}
    for package in LOCK["apt_python"]:
        assert (package["file_count"], package["bytes"]) == wanted[package["name"]]
        files = {row["path"]: row for row in package["files"]}
        assert len(files) == package["file_count"]
        assert sum(row["bytes"] for row in files.values()) == package["bytes"]
        metadata_dir = package["metadata_member"].rsplit("/", 1)[0]
        for filename in ("METADATA", "WHEEL", "RECORD"):
            assert metadata_dir + "/" + filename in files
        assert files[package["metadata_member"]]["sha256"] == package["metadata_sha256"]
        assert package["original_apt_ledger"]["wheel"]["tags"] == ["cp314-cp314-android_aarch64"]


def test_real_snapshot_metadata_matches_all_fifty_one_archives():
    frozen, raw = NATIVE.snapshot_metadata(ROOT / "audit/neutts-runtime-index-20261017", LOCK)
    assert frozen["Packages.gz"]["sha256"] == "dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6"
    assert b"Package: patchelf\n" in raw and b"Package: libyaml\n" in raw
    # This checks the signed-message/hash binding only. Native APT must separately authenticate it.


def test_modified_snapshot_bytes_fail_before_any_native_apt_call(tmp_path):
    source = ROOT / "audit/neutts-runtime-index-20261017"
    for name in ("InRelease", "Packages.gz"):
        shutil.copyfile(source / name, tmp_path / name)
    path = tmp_path / "Packages.gz"
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(NATIVE.ProbeError, match="signed index bytes differ"):
        NATIVE.snapshot_metadata(tmp_path, LOCK)


def test_changed_inrelease_binding_is_rejected_even_with_locally_changed_manifest(tmp_path):
    altered = copy.deepcopy(LOCK)
    source = ROOT / "audit/neutts-runtime-index-20261017"
    shutil.copyfile(source / "Packages.gz", tmp_path / "Packages.gz")
    original = (source / "InRelease").read_bytes()
    changed = original.replace(
        b"dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6",
        b"0" * 64)
    assert changed != original
    (tmp_path / "InRelease").write_bytes(changed)
    pin = next(p for p in altered["build_apt"]["snapshot"] if p["filename"] == "InRelease")
    pin["sha256"] = digest(changed)
    with pytest.raises(NATIVE.ProbeError, match="does not bind"):
        NATIVE.snapshot_metadata(tmp_path, altered)



def test_runtime_edges_recompute_from_all_original_active_declarations():
    from packaging.requirements import Requirement
    versions = {node["name"]: node["version"] for node in LOCK["nodes"]}
    expected = []
    for node in LOCK["nodes"]:
        extras = ("", *node["active_extras"])
        for declared in node["requires_dist"]:
            requirement = Requirement(declared)
            if not any(not requirement.marker or requirement.marker.evaluate({**LOCK["environment"], "extra": extra})
                       for extra in extras):
                continue
            name = PREP.canonical_name(requirement.name)
            assert name in versions and requirement.specifier.contains(versions[name])
            expected.append((node["name"], name, declared))
    assert len(expected) == 10
    assert sorted(expected) == sorted((edge["from"], edge["to"], edge["requirement"]) for edge in LOCK["edges"])


def test_snapshot_requires_the_exact_selected_package_version():
    altered = copy.deepcopy(LOCK)
    altered["build_apt"]["packages"][0]["version"] += "-unreviewed"
    with pytest.raises(NATIVE.ProbeError, match="APT source index pin differs"):
        NATIVE.snapshot_metadata(ROOT / "audit/neutts-runtime-index-20261017", altered)


def wheel_fixture(directory, data=None, *, bad_record=False, unsafe=None):
    entries = {
        "fixture.py": b"VALUE = 42\n",
        "fixture-1.0.dist-info/METADATA": b"Metadata-Version: 2.4\nName: fixture\nVersion: 1.0\n\n",
        "fixture-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n",
    }
    if data:
        entries.update(data)
    if unsafe:
        entries[unsafe] = b"unexpected\n"
    record = "fixture-1.0.dist-info/RECORD"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name, raw in entries.items():
        sha = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        writer.writerow((name, "sha256=" + sha, str(len(raw))))
    writer.writerow((record, "", ""))
    entries[record] = stream.getvalue().encode()
    if bad_record:
        entries["fixture.py"] = b"VALUE = 43\n"
    path = directory / "fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
    return path


def test_wheel_fixture_is_verified_without_importing_its_code(tmp_path):
    path = wheel_fixture(tmp_path)
    facts = PREP.wheel_facts(path)
    assert facts["name"] == "fixture" and facts["wheel"]["file_count"] == 4
    assert facts["native_members"] == []


def test_wheel_record_hash_tampering_is_rejected(tmp_path):
    with pytest.raises(PREP.PrepareError, match="RECORD hash/size"):
        PREP.wheel_facts(wheel_fixture(tmp_path, bad_record=True))


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "x\\y", "drive:c"])
def test_wheel_member_paths_cannot_escape_the_destination(tmp_path, unsafe):
    with pytest.raises(PREP.PrepareError):
        PREP.wheel_facts(wheel_fixture(tmp_path, unsafe=unsafe))


def test_real_zip_crc_corruption_is_rejected(tmp_path):
    path = wheel_fixture(tmp_path)
    with zipfile.ZipFile(path) as archive:
        item = archive.getinfo("fixture.py")
        offset = item.header_offset
    raw = bytearray(path.read_bytes())
    size, extra = struct.unpack_from("<HH", raw, offset + 26)
    raw[offset + 30 + size + extra] ^= 1
    path.write_bytes(raw)
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        PREP.wheel_facts(path)


def install_wheel_fixture(path, site):
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            parts = item.filename.split("/")
            target = site.joinpath(*parts)
            if parts[0].endswith(".data"):
                assert parts[1] == "data"
                target = site.parents[2].joinpath(*parts[2:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))


def test_verified_data_scheme_files_are_mapped_to_the_isolated_prefix(tmp_path):
    path = wheel_fixture(tmp_path, {"fixture-1.0.data/data/share/man/man1/fixture.1": b"manual\n",
                                     "fixture-1.0.data/data/share/polkit-1/actions/example.policy": b"policy\n"})
    facts = PREP.wheel_facts(path)
    site = tmp_path / "venv/lib/python3.14/site-packages"
    site.mkdir(parents=True)
    install_wheel_fixture(path, site)
    record = NATIVE.installed_wheel_bytes(path, facts, site, PREP)
    assert len(record["verified_external_data"]) == 2
    assert record["owned_paths"] == {
        "fixture.py", "fixture-1.0.dist-info/METADATA", "fixture-1.0.dist-info/WHEEL",
        "fixture-1.0.dist-info/RECORD"}
    assert {Path(row["path"]).name for row in record["verified_external_data"]} == {"fixture.1", "example.policy"}


def test_changed_data_scheme_file_is_rejected(tmp_path):
    path = wheel_fixture(tmp_path, {"fixture-1.0.data/data/share/man/man1/fixture.1": b"manual\n"})
    facts = PREP.wheel_facts(path)
    site = tmp_path / "venv/lib/python3.14/site-packages"
    site.mkdir(parents=True)
    install_wheel_fixture(path, site)
    (site.parents[2] / "share/man/man1/fixture.1").write_bytes(b"changed\n")
    with pytest.raises(NATIVE.ProbeError, match="file bytes changed"):
        NATIVE.installed_wheel_bytes(path, facts, site, PREP)


def tar_bytes(entries):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz") as archive:
        for name, raw in entries:
            info = tarfile.TarInfo(name)
            if raw is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            else:
                info.size = len(raw)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(raw))
    return result.getvalue()


def apt_fixture(directory, *, roots=(".",), unsafe=None):
    prefix = "./data/data/com.termux/files/usr/lib/python3.14/site-packages/"
    members = [(name, None) for name in roots]
    members += [(prefix + "fixture.py", b"VALUE = 42\n"),
                (prefix + "fixture-1.0.dist-info/METADATA", b"Name: fixture\nVersion: 1.0\n\n"),
                (prefix + "fixture-1.0.dist-info/WHEEL", b"Wheel-Version: 1.0\nTag: cp314-cp314-android_aarch64\n\n"),
                (prefix + "fixture-1.0.dist-info/RECORD", b"")]
    if unsafe:
        members.append((unsafe, b"no\n"))
    parts = [
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", tar_bytes([("./control", b"Package: fixture\nVersion: 1.0\nArchitecture: aarch64\n\n")])),
        ("data.tar.gz", tar_bytes(members)),
    ]
    result = bytearray(b"!<arch>\n")
    for name, raw in parts:
        result += (f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(raw):<10}").encode() + b"\x60\n"
        result += raw + (b"\n" if len(raw) % 2 else b"")
    path = directory / "fixture_1.0_aarch64.deb"
    path.write_bytes(result)
    pin = {"name": "fixture", "version": "1.0", "architecture": "aarch64",
           "filename": path.name, "bytes": len(result), "sha256": digest(result)}
    return path, pin


@pytest.mark.parametrize("root", [".", "./"])
def test_debian_archive_root_directory_is_valid(root, tmp_path):
    path, pin = apt_fixture(tmp_path, roots=(root,))
    facts, content = PREP.apt_python_payload(path, pin, include_bytes=True)
    assert facts["file_count"] == 4
    assert content["fixture-1.0.dist-info/RECORD"] == b""
    assert facts["metadata_sha256"] == digest(content["fixture-1.0.dist-info/METADATA"])


def test_duplicate_debian_root_is_rejected(tmp_path):
    path, pin = apt_fixture(tmp_path, roots=(".", "./"))
    with pytest.raises(PREP.PrepareError, match="duplicate APT root"):
        PREP.apt_python_payload(path, pin)


def test_unsafe_debian_member_is_rejected_even_outside_the_selected_payload(tmp_path):
    path, pin = apt_fixture(tmp_path, unsafe="./../outside")
    with pytest.raises(PREP.PrepareError, match="Unsafe relative"):
        PREP.apt_python_payload(path, pin)


def patched_text():
    original = BASELINE.read_bytes()
    file = SENTENCEPIECE["patch"]["files"][0]
    assert len(original) == file["before_bytes"] and digest(original) == file["before_sha256"]
    text = original.decode()
    for edit in file["edits"]:
        assert text.count(edit["old"]) == 1
        text = text.replace(edit["old"], edit["new"], 1)
    assert digest(text.encode()) == file["after_sha256"]
    return text


def test_only_the_reviewed_sentencepiece_build_script_changes():
    for source in LOCK["sources"]:
        before = {row["path"]: row for row in source["files"]}
        after = {row["path"]: row for row in source["prepared_files"]}
        assert set(before) == set(after)
        changed = {name for name in before if before[name] != after[name]}
        assert changed == ({"build_bundled.sh"} if source["name"] == "sentencepiece" else set())
    assert sum(len(s["files"]) for s in LOCK["sources"]) == 7787
    assert digest(PATCH.read_bytes()) == SENTENCEPIECE["patch"]["sha256"]


def test_patch_applies_independently_with_git_and_matches_prepared_bytes(tmp_path):
    git = shutil.which("git")
    assert git, "Git is required for the independent patch replay"
    target = tmp_path / "build_bundled.sh"
    target.write_bytes(BASELINE.read_bytes())
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run([git, "-C", str(tmp_path), "apply", "--check", str(PATCH)], check=True, capture_output=True)
    subprocess.run([git, "-C", str(tmp_path), "apply", str(PATCH)], check=True, capture_output=True)
    assert target.read_bytes() == patched_text().encode()


def bash_executable():
    if os.name == "nt":
        candidates = [Path(r"C:\Program Files\Git\bin\bash.exe")]
    else:
        candidates = [Path(shutil.which("bash") or "/missing")]
    found = next((str(p) for p in candidates if p.is_file()), None)
    assert found, "A local Bash is required for the argument-only script regression"
    return found


def bash_path(path):
    value = path.resolve().as_posix()
    if os.name == "nt":
        return "/" + value[0].lower() + value[2:]
    return value


def shell_contract(tmp_path, text, *, budget=None):
    script = tmp_path / "build_bundled.sh"
    script.write_bytes(text.encode())
    source = tmp_path / "sentencepiece/src"
    source.mkdir(parents=True)
    (source / "CMakeLists.txt").write_bytes(b"# Existing local source prevents network fallback.\n")
    env = dict(os.environ)
    env.pop("BASH_ENV", None)
    env.pop("ENV", None)
    env.pop("CMAKE_BUILD_PARALLEL_LEVEL", None)
    env.update(CXXFLAGS="--target=aarch64-linux-android24 -march=armv8-a -DKEPT=1",
               CAPTURE=bash_path(tmp_path / "cmake-arguments"), NPROC_CAPTURE=bash_path(tmp_path / "nproc-called"))
    if budget is not None:
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = budget
    stub = r"""
cmake() { printf 'CALL\0' >> "$CAPTURE"; printf '%s\0' "$@" >> "$CAPTURE"; printf '\n' >> "$CAPTURE"; }
nproc() { printf 'called\n' > "$NPROC_CAPTURE"; printf '64\n'; }
git() { printf 'unexpected source download\n' >&2; return 97; }
export -f cmake nproc git
source "$1" 0.2.2
"""
    result = subprocess.run([bash_executable(), "--noprofile", "--norc", "-c", stub,
                             "contract", bash_path(script)], cwd=tmp_path, env=env,
                            capture_output=True, timeout=15, check=False)
    capture = tmp_path / "cmake-arguments"
    calls = [[p.decode() for p in line.split(b"\0")[1:-1]]
             for line in capture.read_bytes().splitlines()] if capture.exists() else []
    return result, calls, (tmp_path / "nproc-called").exists()


def test_baseline_reproduces_unbounded_jobs_and_lost_target_flags(tmp_path):
    result, calls, nproc = shell_contract(tmp_path, BASELINE.read_text(), budget="2")
    assert result.returncode == 0 and len(calls) == 2
    assert calls[1][-2:] == ["--parallel", "64"] and nproc is True
    flags = next(arg for arg in calls[0] if arg.startswith("-DCMAKE_CXX_FLAGS="))
    assert "--target=aarch64-linux-android24" not in flags
    assert "-DKEPT=1" not in flags


@pytest.mark.parametrize("budget,expected", [(None, "2"), ("", "2"), ("1", "1"), ("2", "2")])
def test_patched_script_preserves_flags_and_uses_the_bounded_budget(tmp_path, budget, expected):
    result, calls, nproc = shell_contract(tmp_path, patched_text(), budget=budget)
    assert result.returncode == 0, result.stderr.decode()
    assert len(calls) == 2 and calls[1][-2:] == ["--parallel", expected]
    assert nproc is False
    flags = next(arg for arg in calls[0] if arg.startswith("-DCMAKE_CXX_FLAGS="))
    assert shlex.split(flags.split("=", 1)[1]) == [
        "--target=aarch64-linux-android24", "-march=armv8-a", "-DKEPT=1",
        "-fPIC", "-fvisibility=default", "-ffunction-sections", "-fdata-sections"]
    assert "-DSPM_ENABLE_SHARED=OFF" in calls[0]
    assert "-DSPM_DISABLE_EMBEDDED_DATA=ON" in calls[0]
    assert "-DCMAKE_POSITION_INDEPENDENT_CODE=ON" in calls[0]


@pytest.mark.parametrize("budget", ["0", "00", "-1", "two", "2 3", "1.5"])
def test_invalid_parallel_budgets_fail_before_any_configuration(tmp_path, budget):
    result, calls, nproc = shell_contract(tmp_path, patched_text(), budget=budget)
    assert result.returncode == 2
    assert b"positive integer" in result.stderr
    assert calls == [] and nproc is False
