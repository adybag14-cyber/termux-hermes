"""Host input/provenance contract tests; these do not claim a native ABI pass."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import zipfile

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREP = load("_tested_phonemizer_preparation", "prepare_phonemizer_runtime.py")
NATIVE = load("_tested_phonemizer_native", "compatibility_probe_phonemizer.py")
EXTRACT = load("_tested_phonemizer_extractor", "extract_phonemizer_catalog.py")


@pytest.fixture(scope="module")
def lock():
    value, _ = PREP.load_lock(ROOT / "scripts/phonemizer_runtime_lock.json")
    return value


@pytest.fixture(scope="module")
def inputs():
    value = os.environ.get("PHONEMIZER_PREPARED_INPUTS")
    if not value:
        pytest.skip("Set PHONEMIZER_PREPARED_INPUTS for real-artifact replay cases")
    path = Path(value)
    assert path.is_dir()
    return path


def test_complete_graph_is_independently_recomputed(lock):
    packages = {p["name"]: p for p in lock["packages"] + lock["sources"]}
    assert len(packages) == 23 and set(packages) == set(lock["names"])
    derived = []
    for name, package in packages.items():
        assert SpecifierSet(package["requires_python"]).contains("3.14.6")
        for text in package["requires_dist"]:
            req = Requirement(text)
            if req.marker is not None and not req.marker.evaluate(lock["environment"]):
                continue
            target = canonicalize_name(req.name)
            assert not req.extras and req.url is None
            assert target in packages and req.specifier.contains(packages[target]["version"])
            derived.append((name, target, str(req)))
    frozen = [(e["from"], e["to"], str(Requirement(e["requirement"]))) for e in lock["edges"]]
    assert len(derived) == 26 and sorted(derived) == sorted(frozen)
    reached = {"phonemizer"}
    while True:
        added = {target for source, target, _ in derived if source in reached}
        if added <= reached:
            break
        reached |= added
    assert reached == set(packages)


def test_all_declared_build_requirements_are_satisfied_without_version_changes(lock):
    build_versions = {p["name"]: p["version"] for p in lock["build_packages"]}
    assert build_versions == {"setuptools": "83.0.0", "packaging": "26.0"}
    for source in lock["sources"]:
        for text in source["build_requires"]:
            req = Requirement(text)
            assert req.specifier.contains(build_versions[req.name])
    assert lock["build"]["expected_dynamic_build_requirements"] == []


def test_reviewed_helpers_match_actual_bytes():
    assert EXTRACT.sha_file(ROOT / "scripts/prepare_phonemizer_runtime.py") == NATIVE.PREPARER_SHA256
    assert NATIVE.PREPARER_SHA256 == EXTRACT.PREPARER_SHA256
    assert EXTRACT.sha_file(ROOT / "scripts/validate_neutts_apt_python.py") == NATIVE.APT_HELPER_SHA256


def test_original_100_catalog_and_nine_selected_records(lock):
    raw = PREP.verify_catalog(ROOT / lock["main_catalog"]["path"], lock)
    assert len(json.loads(raw)["wheels"]) == 100
    assert sum(p["origin"]["kind"] == "main_catalog" for p in lock["packages"]) == 9


def test_catalog_change_fails_before_preparation(tmp_path, lock):
    path = tmp_path / "catalog.json"
    path.write_bytes((ROOT / lock["main_catalog"]["path"]).read_bytes() + b"\n")
    with pytest.raises(PREP.PrepareError):
        PREP.verify_catalog(path, lock)


def test_lock_change_is_rejected(tmp_path):
    path = tmp_path / "changed-lock.json"
    data = json.loads((ROOT / "scripts/phonemizer_runtime_lock.json").read_text())
    data["nodes"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(PREP.PrepareError, match="frozen identity"):
        PREP.load_lock(path)


@pytest.mark.parametrize("value", [
    "../file.py", "/absolute", "a/../b", "a//b", "a/./b", "a\\b", "C:drive", "nul\0name",
])
def test_source_path_escape_is_rejected(value):
    with pytest.raises(PREP.PrepareError):
        PREP.safe_relative(value)


@pytest.mark.parametrize("field,value", [
    ("filename", "../x.whl"),
    ("filename", "x.whl/other"),
    ("filename", "x.zip"),
    ("filename", "x\n.whl"),
    ("bytes", -1),
    ("bytes", True),
    ("sha256", "0" * 63),
    ("url", "http://files.pythonhosted.org/packages/a/b/x.whl"),
    ("url", "https://example.test/x.whl"),
])
def test_artifact_identity_and_endpoint_are_bounded(field, value):
    artifact = {"filename": "x-1-py3-none-any.whl", "bytes": 12, "sha256": "0" * 64}
    artifact[field] = value
    with pytest.raises(PREP.PrepareError):
        PREP.validate_artifact(artifact)


def test_real_prepared_input_replay(inputs):
    value, receipt = PREP.verify_inputs(inputs)
    assert value["node_count"] == 23 and value["edge_count"] == 26
    assert len(receipt["wheels"]) == 23  # 21 runtime plus two build-only wheels.
    assert receipt["native_build_performed"] is False
    assert len(receipt["source_trees"]["phonemizer"]) == 57
    assert len(receipt["source_trees"]["regex"]) == 22


def test_exact_source_extraction_and_patch_replay(tmp_path, inputs, lock):
    source = lock["sources"][0]
    raw = (inputs / "archives" / source["artifact"]["filename"]).read_bytes()
    root = tmp_path / "source"
    PREP.extract_source(raw, source, root)
    before = {p["path"]: p["sha256"] for p in PREP.source_tree(root, source, patched=False)}
    patch = (inputs / "phonemizer-lazy-dlinfo.patch").read_bytes()
    after = {p["path"]: p["sha256"] for p in PREP.apply_patch_files(root, patch, source)}
    assert len(before) == 56 and len(after) == 57
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"phonemizer/backend/espeak/api.py"}
    assert len([name for name in before if before[name] == after[name]]) == 55
    assert (root / source["patch"]["added_test_path"]).is_file()


def test_patch_rejects_wrong_production_preimage(tmp_path, inputs, lock):
    source = lock["sources"][0]
    root = tmp_path / "source"
    PREP.extract_source((inputs / "archives" / source["artifact"]["filename"]).read_bytes(), source, root)
    production = root / source["patch"]["production_path"]
    production.write_bytes(production.read_bytes().replace(b"import atexit", b"import typing", 1))
    with pytest.raises(PREP.PrepareError, match="preimage"):
        PREP.apply_patch_files(root, (inputs / "phonemizer-lazy-dlinfo.patch").read_bytes(), source)


def test_patch_rejects_changed_patch_bytes(tmp_path, inputs, lock):
    with pytest.raises(PREP.PrepareError, match="patch identity"):
        PREP.apply_patch_files(tmp_path, (inputs / "phonemizer-lazy-dlinfo.patch").read_bytes() + b"\n",
                               lock["sources"][0])


def test_source_rejects_omitted_file(tmp_path, inputs, lock):
    source = lock["sources"][1]
    root = tmp_path / "source"
    PREP.extract_source((inputs / "archives" / source["artifact"]["filename"]).read_bytes(), source, root)
    (root / source["files"][0]["path"]).unlink()
    with pytest.raises(PREP.PrepareError, match="incomplete"):
        PREP.source_tree(root, source, patched=True)


def test_source_rejects_archive_identity_change(tmp_path, inputs, lock):
    source = lock["sources"][1]
    raw = (inputs / "archives" / source["artifact"]["filename"]).read_bytes()
    with pytest.raises(PREP.PrepareError, match="archive identity"):
        PREP.extract_source(raw + b"\n", source, tmp_path / "source")


def rewrite_wheel(tmp_path, inputs, lock, *, change_file=False, duplicate=False):
    package = deepcopy(next(p for p in lock["packages"] if p["name"] == "six"))
    path = inputs / "wheels" / package["artifact"]["filename"]
    memory = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for info in source.infolist():
            raw = source.read(info)
            if change_file and info.filename == "six.py":
                raw = b"# provenance tamper\n" + raw[len(b"# provenance tamper\n"):]
            output.writestr(deepcopy(info), raw)
        if duplicate:
            output.writestr(deepcopy(source.getinfo("six.py")), source.read("six.py"))
    raw = memory.getvalue()
    result = tmp_path / package["artifact"]["filename"]
    result.write_bytes(raw)
    package["artifact"]["bytes"] = len(raw)
    package["artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    return result, package


def test_wheel_record_detects_changed_member_with_rebound_container_hash(tmp_path, inputs, lock):
    path, package = rewrite_wheel(tmp_path, inputs, lock, change_file=True)
    with pytest.raises(PREP.PrepareError, match="RECORD member digest"):
        PREP.verify_wheel(path, package)


def test_duplicate_zip_members_are_rejected(tmp_path, inputs, lock):
    with pytest.warns(UserWarning, match="Duplicate name"):
        path, package = rewrite_wheel(tmp_path, inputs, lock, duplicate=True)
    with pytest.raises(PREP.PrepareError, match="Duplicate ZIP"):
        PREP.verify_wheel(path, package)


def test_mutated_wheel_outer_hash_is_rejected(tmp_path, inputs, lock):
    package = next(p for p in lock["packages"] if p["name"] == "six")
    raw = (inputs / "wheels" / package["artifact"]["filename"]).read_bytes()
    path = tmp_path / package["artifact"]["filename"]
    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(PREP.PrepareError, match="SHA-256"):
        PREP.verify_wheel(path, package)


def test_extra_source_file_is_rejected(tmp_path, inputs, lock):
    source = lock["sources"][1]
    root = tmp_path / "source"
    PREP.extract_source((inputs / "archives" / source["artifact"]["filename"]).read_bytes(), source, root)
    (root / "unexpected.py").write_text("raise RuntimeError('unexpected')\n")
    with pytest.raises(PREP.PrepareError, match="Unexpected source tree"):
        PREP.source_tree(root, source, patched=True)


def test_output_is_never_overwritten(tmp_path, inputs):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "marker"
    marker.write_text("keep")
    with pytest.raises(PREP.PrepareError, match="fresh output"):
        PREP.prepare(inputs / PREP.LOCK_FILENAME, inputs / "wheels", inputs / "main-bundled-wheels.json",
                     inputs / "phonemizer-lazy-dlinfo.patch", output, cache=inputs / "wheels")
    assert marker.read_text() == "keep"


def test_native_entry_rejects_host_environment():
    if os.name != "nt":
        pytest.skip("Host rejection fixture is specifically Windows")
    with pytest.raises(NATIVE.ProbeError, match="Real native Bionic"):
        NATIVE.native_runtime()


def test_build_environment_removes_unreviewed_overrides(monkeypatch, lock):
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                 "LD_PRELOAD", "CMAKE_TOOLCHAIN_FILE", "PIP_INDEX_URL", "ESPEAK_DATA_PATH"):
        monkeypatch.setenv(name, "unreviewed")
    env = NATIVE.clean_environment(lock)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                 "LD_PRELOAD", "CMAKE_TOOLCHAIN_FILE", "PIP_INDEX_URL", "ESPEAK_DATA_PATH"):
        assert name not in env
    assert env["PIP_NO_INDEX"] == "1" and env["CC"].replace("\\", "/").endswith("/bin/clang")
    assert env["CFLAGS"] == lock["build"]["cflags"]


def test_existing_apt_union_is_exactly_141_without_repinning(lock):
    pins, native = NATIVE.all_apt_pins(lock, PREP)
    assert len(pins) == 141
    assert len(native["build_apt"]["packages"]) == 44
    assert pins["python"]["version"] == "3.14.6-1"
    assert pins["clang"]["version"] == "21.1.8-3"


def test_extractor_rejects_wrong_whole_deb_hash_before_any_output(tmp_path):
    path = tmp_path / "candidate.deb"
    path.write_bytes(b"!<arch>\n")
    with pytest.raises(EXTRACT.ExtractError, match="exact frozen identity"):
        EXTRACT.extract(path, 8, "0" * 64, ROOT / "scripts/phonemizer_runtime_lock.json", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_ar_reader_detects_truncated_selected_member():
    stream = EXTRACT.MemberStream(io.BytesIO(b"abc"), 4)
    with pytest.raises(EXTRACT.ExtractError, match="Truncated"):
        stream.read()
