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


def test_only_the_reviewed_sentencepiece_build_script_and_abseil_guard_change():
    for source in LOCK["sources"]:
        before = {row["path"]: row for row in source["files"]}
        after = {row["path"]: row for row in source["prepared_files"]}
        assert set(before) == set(after)
        changed = {name for name in before if before[name] != after[name]}
        assert changed == ({"build_bundled.sh", "sentencepiece/CMakeLists.txt"} if source["name"] == "sentencepiece" else set())
    assert sum(len(s["files"]) for s in LOCK["sources"]) == 7787
    assert digest(PATCH.read_bytes()) == SENTENCEPIECE["patch"]["sha256"]


def test_patch_applies_independently_with_git_and_matches_prepared_bytes(tmp_path):
    git = shutil.which("git")
    assert git, "Git is required for the independent patch replay"
    target = tmp_path / "build_bundled.sh"
    target.write_bytes(BASELINE.read_bytes())
    cmake_target = tmp_path / "sentencepiece/CMakeLists.txt"
    cmake_target.parent.mkdir()
    cmake_target.write_bytes((BASELINE.parent / "sentencepiece_CMakeLists.txt").read_bytes())
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run([git, "-C", str(tmp_path), "apply", "--check", str(PATCH)], check=True, capture_output=True)
    subprocess.run([git, "-C", str(tmp_path), "apply", str(PATCH)], check=True, capture_output=True)
    assert target.read_bytes() == patched_text().encode()
    pin = SENTENCEPIECE["patch"]["files"][1]
    assert digest(cmake_target.read_bytes()) == pin["after_sha256"]


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


# These are structural/evidence-contract tests. The small ELF fixtures are never
# imported or executed, and substituting host tag discovery is not Android proof.
def elf_header(*, machine=183, elf_class=2, endian=1, length=64):
    value = bytearray(max(length, 20))
    value[:6] = b"\x7fELF" + bytes((elf_class, endian))
    struct.pack_into("<H", value, 18, machine)
    return bytes(value[:length])


def audioop_wheel_fixture(directory, members):
    source = next(p for p in LOCK["sources"] if p["name"] == "audioop-lts")
    dist = "audioop_lts-" + source["version"] + ".dist-info"
    meta = "\n".join(("Metadata-Version: 2.4", "Name: audioop-lts",
                      "Version: " + source["version"], "Requires-Python: " + source["requires_python"],
                      *("Requires-Dist: " + r for r in source["requires_dist"]))) + "\n\n"
    entries = {**members, dist + "/METADATA": meta.encode(),
               dist + "/WHEEL": ("Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: "
                                  + source["expected_tag"] + "\n\n").encode()}
    record = dist + "/RECORD"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name, raw in entries.items():
        writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("="),
                         str(len(raw))))
    writer.writerow((record, "", ""))
    entries[record] = stream.getvalue().encode()
    path = directory / ("audioop_lts-" + source["version"] + "-" + source["expected_tag"] + ".whl")
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
    return path, source


def host_accepts_only_the_locked_audioop_tag(monkeypatch, source):
    from pip._vendor.packaging import tags
    monkeypatch.setattr(tags, "sys_tags", lambda: iter(tags.parse_tag(source["expected_tag"])))


def test_actual_audioop_package_namespace_passes_structural_wheel_checks(tmp_path, monkeypatch):
    path, source = audioop_wheel_fixture(tmp_path, {"audioop/_audioop.abi3.so": elf_header()})
    host_accepts_only_the_locked_audioop_tag(monkeypatch, source)
    facts = NATIVE.built_wheel(path, source, PREP)
    assert [item["member"] for item in facts["native_members"]] == ["audioop/_audioop.abi3.so"]
    assert facts["requires_python"] == source["requires_python"]
    assert facts["requires_dist"] == source["requires_dist"]


@pytest.mark.parametrize("member", [
    "audioop.abi3.so", "audioop/foreign.abi3.so", "audioop/_audioop_bad.abi3.so",
    "audioop/_audioop.other.abi3.so", "foreign/_audioop.abi3.so",
])
def test_audioop_rejects_foreign_or_obsolete_native_names(tmp_path, monkeypatch, member):
    path, source = audioop_wheel_fixture(tmp_path, {member: elf_header()})
    host_accepts_only_the_locked_audioop_tag(monkeypatch, source)
    with pytest.raises(NATIVE.ProbeError, match="namespace differs"):
        NATIVE.built_wheel(path, source, PREP)


@pytest.mark.parametrize("header", [
    elf_header(machine=62), elf_header(elf_class=1), elf_header(endian=2),
    elf_header(length=19), b"not an ELF" + b"x" * 80,
])
def test_audioop_native_abi_checks_remain_strict(tmp_path, monkeypatch, header):
    path, source = audioop_wheel_fixture(tmp_path, {"audioop/_audioop.abi3.so": header})
    host_accepts_only_the_locked_audioop_tag(monkeypatch, source)
    with pytest.raises(NATIVE.ProbeError, match="foreign namespace or ABI"):
        NATIVE.built_wheel(path, source, PREP)


def test_audioop_cannot_smuggle_a_second_native_member(tmp_path, monkeypatch):
    path, source = audioop_wheel_fixture(tmp_path, {
        "audioop/_audioop.abi3.so": elf_header(), "audioop/_other.abi3.so": elf_header()})
    host_accepts_only_the_locked_audioop_tag(monkeypatch, source)
    with pytest.raises(NATIVE.ProbeError, match="namespace differs"):
        NATIVE.built_wheel(path, source, PREP)


def test_audioop_does_not_retag_for_an_unsupported_host(tmp_path, monkeypatch):
    from pip._vendor.packaging import tags
    path, source = audioop_wheel_fixture(tmp_path, {"audioop/_audioop.abi3.so": elf_header()})
    monkeypatch.setattr(tags, "sys_tags", lambda: iter(tags.parse_tag("cp314-cp314-win_amd64")))
    with pytest.raises(NATIVE.ProbeError, match="native wheel tag"):
        NATIVE.built_wheel(path, source, PREP)


def test_image_member_pins_keep_exact_same_run_and_owner_provenance():
    platform = LOCK["platform_runtime"]
    assert platform["native_image"] == "termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303"
    assert platform["package"] == {"name": "aosp-libs", "version": "9.0.0-r76-4",
                                  "architecture": "aarch64", "status": "installed"}
    assert {Path(row["path"]).name for row in platform["files"]} == {
        "libc++.so", "libc.so", "libdl.so", "liblog.so", "libm.so"}
    assert all(row["path"].startswith("/data/data/com.termux/files/usr/opt/aosp/lib64/")
               and row["elf_class"] == 64 and row["machine"] == 183 for row in platform["files"])
    proof = platform["provenance"]
    assert proof["run_id"] == "39073990223"
    assert proof["head_sha"] == "c3584d6348948063c442195c6e3f25ecd3cebc08"
    assert proof["artifact_sha256"] == "6d31dda2133f6fdda39c8e297917a75b20a46df2130f59ea7ef7602f74e5fbe9"
    assert len(proof["foundation_receipts"]) == 7
    assert len({row["path"] for row in proof["foundation_receipts"]}) == 7


def platform_fixture(tmp_path):
    from types import SimpleNamespace
    lock = copy.deepcopy(LOCK)
    paths = set()
    for index, pin in enumerate(lock["platform_runtime"]["files"]):
        path = tmp_path / "image/opt/aosp/lib64" / Path(pin["path"]).name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = elf_header() + bytes((index,))
        path.write_bytes(raw)
        pin.update(path=str(path), bytes=len(raw), sha256=digest(raw))
        paths.add(path)
    package = lock["platform_runtime"]["package"]
    snapshot = {package["name"]: {key: package[key] for key in ("version", "architecture", "status")}}
    owners = {path.as_posix(): ["aosp-libs"] for path in paths}
    # The unchanged reader really checks the fixture header. No target loader or
    # dynamic linker is called by this host-only owner/byte/ELF-header contract.
    common = NATIVE.module_at("_test_image_platform_elf", ROOT / "scripts/compatibility_probe_phonemizer.py",
                              NATIVE.COMPONENT_HELPER_SHA256)
    methods = SimpleNamespace(package_snapshot=lambda names: snapshot,
                              elf=lambda path, dynamic: common.elf(path, dynamic=False))
    return lock, paths, methods, SimpleNamespace(collect_owners=lambda wanted: owners), snapshot, owners


def test_exact_image_platform_members_require_bytes_headers_and_owner(tmp_path):
    lock, paths, common, apt, _, _ = platform_fixture(tmp_path)
    result = NATIVE.verify_image_platform_members(paths, lock, common, apt)
    assert result["status"] == "verified-image-members"
    assert len(result["members"]) == 5
    assert all(row["package"] == "aosp-libs" and row["class"] == 64 for row in result["members"])


@pytest.mark.parametrize("change", ["version", "architecture", "status"])
def test_image_owner_snapshot_cannot_drift(tmp_path, change):
    lock, paths, common, apt, snapshot, _ = platform_fixture(tmp_path)
    snapshot["aosp-libs"][change] = "unreviewed"
    with pytest.raises(NATIVE.ProbeError, match="owner version differs"):
        NATIVE.verify_image_platform_members(paths, lock, common, apt)


@pytest.mark.parametrize("owners_value", [[], ["other"], ["aosp-libs", "other"]])
def test_image_member_requires_one_exact_owner(tmp_path, owners_value):
    lock, paths, common, apt, _, owners = platform_fixture(tmp_path)
    owners[next(iter(paths)).as_posix()] = owners_value
    with pytest.raises(NATIVE.ProbeError, match="owner differs"):
        NATIVE.verify_image_platform_members(paths, lock, common, apt)


def test_changed_image_bytes_are_rejected(tmp_path):
    lock, paths, common, apt, _, _ = platform_fixture(tmp_path)
    path = next(iter(paths))
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + bytes((raw[-1] ^ 1,)))
    with pytest.raises(NATIVE.ProbeError, match="member bytes differ"):
        NATIVE.verify_image_platform_members(paths, lock, common, apt)


def test_image_directory_cannot_substitute_for_a_regular_member(tmp_path):
    lock, paths, common, apt, _, _ = platform_fixture(tmp_path)
    path = next(iter(paths))
    path.unlink()
    path.mkdir()
    with pytest.raises(NATIVE.ProbeError, match="exact regular path"):
        NATIVE.verify_image_platform_members(paths, lock, common, apt)


def test_another_file_inside_the_aosp_directory_is_not_admitted(tmp_path):
    lock, paths, common, apt, _, _ = platform_fixture(tmp_path)
    extra = next(iter(paths)).parent / "unreviewed.so"
    extra.write_bytes(elf_header())
    with pytest.raises(NATIVE.ProbeError, match="Unreviewed image platform member"):
        NATIVE.verify_image_platform_members(paths | {extra}, lock, common, apt)


def test_even_locally_rehashed_foreign_elf_is_rejected(tmp_path):
    lock, paths, common, apt, _, _ = platform_fixture(tmp_path)
    path = next(iter(paths))
    raw = elf_header(machine=62)
    path.write_bytes(raw)
    pin = next(row for row in lock["platform_runtime"]["files"] if row["path"] == str(path))
    pin.update(bytes=len(raw), sha256=digest(raw))
    with pytest.raises(RuntimeError, match="little-endian AArch64 ELF"):
        NATIVE.verify_image_platform_members(paths, lock, common, apt)


def maps_line(path, *, deleted=False):
    value = path.absolute().as_posix()
    # Windows controls resolve drive-rooted /Users/... using the current drive;
    # the production parser is unchanged and consumes genuine Android maps.
    if os.name == "nt":
        value = value[2:]
    return ("1000-2000 r-xp 00000000 00:00 1 " + value + (" (deleted)" if deleted else "") + "\n").encode()


@pytest.mark.parametrize("kind,expected", [
    ("source", "source-extension"), ("apt", "apt-library"), ("image", "image-platform"),
    ("unknown_site", "rejected-isolated-site"), ("unknown_aosp", "rejected-foreign"),
    ("arbitrary_prefix", "rejected-foreign"), ("foreign", "rejected-foreign"),
    ("deleted", "rejected-deleted"),
])
def test_native_map_classification_never_broadens_prefix_admission(tmp_path, monkeypatch, kind, expected):
    prefix = tmp_path / "prefix"
    site = tmp_path / "venv/lib/python3.14/site-packages"
    source = site / "yaml/_yaml.so"
    image = prefix / "opt/aosp/lib64/libc.so"
    choices = {"source": source, "apt": prefix / "lib/libyaml.so", "image": image,
               "unknown_site": site / "foreign.so", "unknown_aosp": image.parent / "foreign.so",
               "arbitrary_prefix": prefix / "tmp/foreign.so", "foreign": tmp_path / "foreign.so",
               "deleted": source}
    monkeypatch.setattr(NATIVE, "PREFIX", prefix)
    raw = maps_line(choices[kind], deleted=kind == "deleted")
    rows = NATIVE.native_mapping_rows(raw, site, {source: {}}, {image})
    assert len(rows) == 1 and rows[0]["classification"] == expected
    assert rows[0]["mapped_path"] in raw.decode()
    assert rows[0]["resolved_path"] == str(choices[kind].resolve())


def test_unknown_mapping_failure_preserves_full_raw_and_exact_path(tmp_path, monkeypatch):
    from types import SimpleNamespace
    out = tmp_path / "evidence"
    out.mkdir()
    unexpected = tmp_path / "outside-prefix/unreviewed.so"
    raw = maps_line(unexpected)
    monkeypatch.setattr(NATIVE, "read_native_maps", lambda: raw)
    args = SimpleNamespace(out=out)
    with pytest.raises(NATIVE.ProbeError, match="unreviewed.so"):
        NATIVE.verify_native_mappings({"wheels": [], "apt_python": []}, None, None, None, args, LOCK)
    assert (out / "NATIVE-MAPPINGS.raw.txt").read_bytes() == raw
    report = json.loads((out / "NATIVE-MAPPINGS.json").read_bytes())
    assert report["raw_sha256"] == digest(raw)
    assert report["mappings"][0]["resolved_path"] == str(unexpected.resolve())
    assert report["mappings"][0]["classification"] == "rejected-foreign"


def test_raw_map_bound_is_explicit(tmp_path):
    with pytest.raises(NATIVE.ProbeError, match="evidence exceeds"):
        NATIVE.native_mapping_rows(b"x" * (4 * 1024 * 1024 + 1), tmp_path, {}, set())


def image_receipts_fixture(tmp_path):
    from types import SimpleNamespace
    image = LOCK["platform_runtime"]["native_image"]
    receipt = tmp_path / "NONRUST-PROBE-INPUTS.json"
    inputs = {
        "schema_version": 1, "native_image": image,
        "inputs": {
            "scripts/compatibility_probe_neutts_nonrust.py": digest((ROOT / "scripts/compatibility_probe_neutts_nonrust.py").read_bytes()),
            "scripts/compatibility_probe_neutts_nonrust.sh": digest((ROOT / "scripts/compatibility_probe_neutts_nonrust.sh").read_bytes()),
            "scripts/prepare_neutts_nonrust_runtime.py": NATIVE.PREPARER_SHA256,
            "scripts/neutts_nonrust_runtime_lock.json": digest((ROOT / "scripts/neutts_nonrust_runtime_lock.json").read_bytes()),
        },
    }
    inspection = [{"Architecture": "arm64", "Os": "linux", "RepoDigests": [image], "Id": "sha256:" + "1" * 64}]
    receipt.write_text(json.dumps(inputs))
    (tmp_path / "NONRUST-SOURCE-IMAGE.json").write_text(json.dumps(inspection))
    return SimpleNamespace(image_receipt=receipt, inputs=ROOT / "scripts"), inputs, inspection


def test_image_receipt_binds_the_actual_digest_architecture_and_executing_inputs(tmp_path):
    args, _, _ = image_receipts_fixture(tmp_path)
    result = NATIVE.validate_source_image(args, LOCK)
    assert result["status"] == "verified-pinned-image"
    assert result["input_receipt_sha256"] == digest(args.image_receipt.read_bytes())


@pytest.mark.parametrize("change", ["image", "script", "architecture", "os", "digest", "id", "duplicate"])
def test_image_evidence_mismatches_fail_before_member_admission(tmp_path, change):
    args, inputs, inspection = image_receipts_fixture(tmp_path)
    if change == "image":
        inputs["native_image"] = "unreviewed/image@sha256:" + "0" * 64
    elif change == "script":
        inputs["inputs"]["scripts/compatibility_probe_neutts_nonrust.py"] = "0" * 64
    elif change == "architecture":
        inspection[0]["Architecture"] = "amd64"
    elif change == "os":
        inspection[0]["Os"] = "windows"
    elif change == "digest":
        inspection[0]["RepoDigests"] = ["termux/termux-docker@sha256:" + "0" * 64]
    elif change == "id":
        inspection[0]["Id"] = "not-a-content-id"
    else:
        inspection.append(copy.deepcopy(inspection[0]))
    args.image_receipt.write_text(json.dumps(inputs))
    (tmp_path / "NONRUST-SOURCE-IMAGE.json").write_text(json.dumps(inspection))
    with pytest.raises(NATIVE.ProbeError):
        NATIVE.validate_source_image(args, LOCK)


def cmake_source_text(*, patched):
    raw = (BASELINE.parent / "sentencepiece_CMakeLists.txt").read_bytes()
    pin = SENTENCEPIECE["patch"]["files"][1]
    assert digest(raw) == pin["before_sha256"] and len(raw) == pin["before_bytes"]
    text = raw.decode()
    if patched:
        for edit in pin["edits"]:
            assert text.count(edit["old"]) == 1
            text = text.replace(edit["old"], edit["new"], 1)
        assert digest(text.encode()) == pin["after_sha256"]
    return text


def abseil_cmake_contract(directory, *, patched, tree):
    # Execute the exact provider block with real CMake. The acquisition module is
    # an offline control: it records original fetch arguments, never uses Git or
    # a network, and lets add_subdirectory visit a tiny noncompiling fixture.
    source = directory / "source"
    build = directory / "build"
    modules = source / "cmake"
    modules.mkdir(parents=True)
    (source / "third_party/absl").mkdir(parents=True)
    bundled = source / "third_party/abseil-cpp"
    visit = 'file(WRITE "' + build.as_posix() + '/bundled-visited.txt" "visited\\n")\n'
    if tree == "file":
        bundled.write_text("not a source tree\n")
    elif tree != "absent":
        bundled.mkdir()
        if tree != "no-cmake":
            if tree == "cmake-directory":
                (bundled / "CMakeLists.txt").mkdir()
            else:
                (bundled / "CMakeLists.txt").write_text(visit)
        (bundled / "absl/base").mkdir(parents=True)
        if tree == "config-directory":
            (bundled / "absl/base/config.h").mkdir()
        elif tree != "no-config":
            (bundled / "absl/base/config.h").write_text("// Offline structural fixture.\n")
    fetch = r'''
function(FetchContent_Populate)
  file(WRITE "${CMAKE_BINARY_DIR}/fetch-args.txt" "${ARGV}\n")
  if (EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/third_party/abseil-cpp")
    message(FATAL_ERROR "FETCH_ATTEMPTED_WITH_BUNDLED_TREE")
  endif()
  file(MAKE_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/third_party/abseil-cpp/absl/base")
  file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/third_party/abseil-cpp/absl/base/config.h" "// fixture\n")
  file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/third_party/abseil-cpp/CMakeLists.txt"
       "file(WRITE \"${CMAKE_BINARY_DIR}/bundled-visited.txt\" \"visited\\n\")\n")
endfunction()
'''
    (modules / "FetchContent.cmake").write_text(fetch)
    full = cmake_source_text(patched=patched)
    start = full.index('if (SPM_ABSL_PROVIDER STREQUAL "module")')
    end = full.index("\nif(SPM_ENABLE_BENCHMARK)", start)
    block = full[start:end]
    project = ('cmake_minimum_required(VERSION 3.14)\nproject(abseil_source_contract LANGUAGES NONE)\n'
               'set(SPM_ABSL_PROVIDER "module")\n'
               'list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")\n' + block)
    (source / "CMakeLists.txt").write_text(project, encoding="utf-8", newline="\n")
    cmake = shutil.which("cmake")
    assert cmake, "A real host CMake is required for the acquisition-branch contract"
    result = subprocess.run([cmake, "-G", "Ninja", "-S", str(source), "-B", str(build)],
                            capture_output=True, timeout=30, check=False)
    fetched = build / "fetch-args.txt"
    arguments = fetched.read_text().strip().split(";") if fetched.exists() else None
    return result, arguments, (build / "bundled-visited.txt").exists(), source


def test_unpatched_cmake_reproduces_the_unconditional_bundled_tree_fetch(tmp_path):
    result, arguments, visited, _ = abseil_cmake_contract(tmp_path, patched=False, tree="present")
    assert result.returncode != 0 and b"FETCH_ATTEMPTED_WITH_BUNDLED_TREE" in result.stderr
    assert arguments and visited is False


def test_patched_cmake_uses_the_bundled_tree_without_fetching(tmp_path):
    result, arguments, visited, _ = abseil_cmake_contract(tmp_path, patched=True, tree="present")
    assert result.returncode == 0, result.stderr.decode()
    assert arguments is None and visited is True


def test_absent_tree_preserves_the_exact_upstream_fetch_arguments(tmp_path):
    controls = []
    for patched in (False, True):
        result, arguments, visited, source = abseil_cmake_contract(tmp_path / str(patched),
                                                                 patched=patched, tree="absent")
        assert result.returncode == 0, result.stderr.decode()
        assert visited is True
        controls.append([arg.replace(source.as_posix(), "SOURCE") for arg in arguments])
    assert controls[0] == controls[1] == [
        "abseil-cpp", "GIT_REPOSITORY", "https://github.com/abseil/abseil-cpp.git",
        "SOURCE_DIR", "SOURCE/third_party/abseil-cpp", "GIT_PROGRESS", "TRUE",
        "GIT_TAG", "20260526.0"]


@pytest.mark.parametrize("tree", ["file", "no-cmake", "cmake-directory", "no-config", "config-directory"])
def test_invalid_present_abseil_trees_fail_without_fetch(tmp_path, tree):
    result, arguments, visited, _ = abseil_cmake_contract(tmp_path, patched=True, tree=tree)
    assert result.returncode != 0 and b"Bundled Abseil source tree is incomplete" in result.stderr
    assert arguments is None and visited is False


def rpath_control_fixture(tmp_path, monkeypatch, scenario):
    from types import ModuleType, SimpleNamespace
    import sys
    fixture = BASELINE.parent / "meson_python_rpath.py"
    assert digest(fixture.read_bytes()) == "cb3aa16e3aea81e69371c3c4340aafef1834446775bb178a5953e047612db882"
    monkeypatch.setattr(NATIVE.sys, "platform", "android")
    spec = importlib.util.spec_from_file_location("mesonpy._rpath", fixture)
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    package = ModuleType("mesonpy")
    package.__path__ = []
    package._rpath = backend
    monkeypatch.setitem(sys.modules, "mesonpy", package)
    monkeypatch.setitem(sys.modules, "mesonpy._rpath", backend)
    prefix = tmp_path / "prefix"
    monkeypatch.setattr(NATIVE, "PREFIX", prefix)
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    library = work / "rpath-control.so"
    before = "$ORIGIN/before:" + str(prefix / "lib")
    state = {"rpath": str(prefix / "lib") + ":" + before,
             "calls": [], "backend_calls": [], "loaded": 0}
    original_elf = NATIVE.module_at("_rpath_control_header", ROOT / "scripts/compatibility_probe_phonemizer.py",
                                   NATIVE.COMPONENT_HELPER_SHA256)

    def binary():
        library.write_bytes(elf_header() + state["rpath"].encode())

    def bounded(command, output, label, timeout, *args, **kwargs):
        state["calls"].append(list(command))
        if "-###" in command:
            return {"exit_code": 0, "label": label, "diagnostic_only": True}
        if "--set-rpath" in command:
            state["rpath"] = command[command.index("--set-rpath") + 1]
            if scenario == "seed-readback":
                state["rpath"] += ":wrong"
        binary()
        return {"exit_code": 0, "label": label}

    def check_output(command, *, text, timeout):
        assert command[1] == "--print-rpath" and text is True
        return state["rpath"] + "\n"

    def backend_run(command, **kwargs):
        state["backend_calls"].append(list(command))
        assert command[0] == "patchelf"
        if command[1] == "--print-rpath":
            return SimpleNamespace(returncode=0, stdout=state["rpath"] + "\n", stderr="")
        assert command[1] == "--set-rpath"
        if scenario != "backend-noop":
            state["rpath"] = command[2]
            binary()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    class Function:
        def __call__(self):
            return 41 if scenario == "native-result" else 42

    def load_library(path):
        assert path == str(library)
        state["loaded"] += 1
        return SimpleNamespace(component_value=Function())

    monkeypatch.setattr(NATIVE.subprocess, "check_output", check_output)
    monkeypatch.setattr(backend.subprocess, "run", backend_run)
    monkeypatch.setattr(NATIVE.ctypes, "CDLL", load_library)
    monkeypatch.setattr(NATIVE.importlib.metadata, "version", lambda name: "0.21.1" if name == "meson-python" else None)
    common = SimpleNamespace(bounded_command=bounded,
                             elf=lambda path, dynamic: original_elf.elf(path, dynamic=False))
    return SimpleNamespace(out=out), work, common, state, before


def test_rpath_control_records_compiler_defaults_then_tests_real_backend_transform(tmp_path, monkeypatch):
    args, work, common, state, before = rpath_control_fixture(tmp_path, monkeypatch, "passed")
    result = NATIVE.patchelf_probe(args, LOCK, common, work)
    assert result["status"] == "passed"
    assert result["compiler_rpath"] != before and result["before"] == before
    assert result["after"] == "$ORIGIN/after:" + str(NATIVE.PREFIX / "lib")
    assert state["calls"][0][-1] == "-###"
    assert "--set-rpath" in state["calls"][2]
    assert state["backend_calls"] == [
        ["patchelf", "--print-rpath", str(work / "rpath-control.so")],
        ["patchelf", "--set-rpath", result["after"], str(work / "rpath-control.so")]]
    assert state["loaded"] == 1 and result["native_function_result"] == 42
    assert json.loads((args.out / "RPATH-CONTROL-RESULT.json").read_bytes()) == result


@pytest.mark.parametrize("scenario,message,loaded", [
    ("seed-readback", "control seed differs", 0),
    ("backend-noop", "backend RPATH repair failed", 0),
    ("native-result", "ELF did not execute", 1),
])
def test_rpath_controls_keep_seed_transform_and_execution_failures(tmp_path, monkeypatch, scenario, message, loaded):
    args, work, common, state, before = rpath_control_fixture(tmp_path, monkeypatch, scenario)
    with pytest.raises(NATIVE.ProbeError, match=message):
        NATIVE.patchelf_probe(args, LOCK, common, work)
    report = json.loads((args.out / "RPATH-CONTROL-RESULT.json").read_bytes())
    assert report["status"] == "failed" and message in report["error"]["message"]
    assert report["compiler_rpath"] != before and state["loaded"] == loaded
    if scenario == "seed-readback":
        assert state["backend_calls"] == []
