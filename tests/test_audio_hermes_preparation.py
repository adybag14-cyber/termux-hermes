"""Integrity regressions for full Hermes audio preparation; no native/audio execution."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prep = load("audio_preparation_test", "prepare_audio_hermes_environment.py")
probe = load("audio_probe_test", "compatibility_probe_audio_hermes.py")


def catalog_pair():
    before = {"wheels": [{"file": f"wheelhouse/item{i}-1-py3-none-any.whl",
                          "name": f"item{i}", "version": "1", "size": 1, "sha256": f"{i:064x}",
                          "source": {"kind": "registry-sdist"}} for i in range(100)]}
    after = copy.deepcopy(before)
    for name in prep.NEW_WHEELS:
        pin = prep.AUDIO_MEMBERS["wheelhouse/" + name]
        after["wheels"].append({"file": "wheelhouse/" + name, "name": name.split("-")[0],
                                 "version": name.split("-")[1], "size": pin["bytes"], "sha256": pin["sha256"]})
    return before, after


def test_catalog_union_keeps_all_original_rows():
    before, after = catalog_pair()
    result = prep.verify_catalog_union(before, after)
    assert result == {"original_rows": 100, "additional_rows": 2, "total_rows": 102,
                      "original_rows_preserved": True}


@pytest.mark.parametrize("mutation", ["hash", "source", "duplicate", "missing", "third-wheel", "new-sha"])
def test_catalog_rejects_altered_or_ambiguous_closure(mutation):
    before, after = catalog_pair()
    if mutation == "hash":
        after["wheels"][0]["sha256"] = "f" * 64
    elif mutation == "source":
        after["wheels"][0]["source"] = {"kind": "another-source"}
    elif mutation == "duplicate":
        after["wheels"].append(copy.deepcopy(after["wheels"][0]))
    elif mutation == "missing":
        after["wheels"].pop(0)
    elif mutation == "third-wheel":
        after["wheels"].append({"file": "wheelhouse/extra.whl"})
    else:
        after["wheels"][-1]["sha256"] = "0" * 64
    with pytest.raises(prep.PreparationError):
        prep.verify_catalog_union(before, after)


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "a/../../escape", "a//b", "a\\b", "C:escape"])
def test_owned_paths_reject_escape(tmp_path, relative):
    with pytest.raises(prep.PreparationError):
        prep.contained(tmp_path, relative)


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_preparation_refuses_existing_output_without_touching_it(tmp_path, kind):
    out = tmp_path / "keep"
    if kind == "directory":
        out.mkdir()
        (out / "marker").write_text("keep")
    else:
        out.write_text("keep")
    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(prep.PreparationError, match="new directory"):
        prep.fresh_output(out)
    assert sorted(tmp_path.rglob("*")) == before
    assert (out / "marker" if out.is_dir() else out).read_text() == "keep"


def test_preparation_refuses_overlap_with_inputs(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    with pytest.raises(prep.PreparationError, match="overlaps"):
        prep.fresh_output(source / "new", (source,))
    assert not (source / "new").exists()


def test_pinned_file_rejects_one_changed_byte(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"abc")
    digest = hashlib.sha256(b"abc").hexdigest()
    assert prep.pinned(path, 3, digest)["sha256"] == digest
    path.write_bytes(b"abd")
    with pytest.raises(prep.PreparationError, match="identity"):
        prep.pinned(path, 3, digest)


def archive_fixture(tmp_path, members):
    archive = tmp_path / "audio.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as stream:
        for name, body in members.items():
            stream.writestr(name, body)
    pins = {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                   "crc32": zlib.crc32(body)} for name, body in members.items()}
    return archive, pins, (archive.stat().st_size, prep.sha256(archive))


def test_audio_archive_verifies_excluded_raw_evidence(tmp_path):
    archive, pins, pin = archive_fixture(tmp_path, {"wheelhouse/numpy.whl": b"wheel",
                                                  "unused-evidence.log": b"proof"})
    output = tmp_path / "out"
    output.mkdir()
    result = prep.verify_audio_archive(archive, output, expected_members=pins, archive_pin=pin)
    assert (output / "wheelhouse/numpy.whl").read_bytes() == b"wheel"
    assert not (output / "unused-evidence.log").exists()
    assert set(result) == {"wheelhouse/numpy.whl"}
    pins["unused-evidence.log"]["sha256"] = "f" * 64
    with pytest.raises(prep.PreparationError, match="bytes"):
        prep.verify_audio_archive(archive, expected_members=pins, archive_pin=pin)


def test_audio_archive_rejects_traversal_even_with_matching_hash(tmp_path):
    archive, pins, pin = archive_fixture(tmp_path, {"../escape": b"x"})
    with pytest.raises(prep.PreparationError, match="unsafe"):
        prep.verify_audio_archive(archive, expected_members=pins, archive_pin=pin)
    assert not (tmp_path.parent / "escape").exists()


def test_audio_archive_rejects_wrong_crc_pin(tmp_path):
    archive, pins, pin = archive_fixture(tmp_path, {"safe.log": b"proof"})
    pins["safe.log"]["crc32"] ^= 1
    with pytest.raises(prep.PreparationError, match="metadata"):
        prep.verify_audio_archive(archive, expected_members=pins, archive_pin=pin)


def test_audio_archive_rejects_new_member(tmp_path):
    archive, pins, pin = archive_fixture(tmp_path, {"safe.log": b"proof", "extra": b"not pinned"})
    pins.pop("extra")
    with pytest.raises(prep.PreparationError, match="member set"):
        prep.verify_audio_archive(archive, expected_members=pins, archive_pin=pin)


def test_download_reader_refuses_truncation_and_surplus():
    assert prep.read_limited(io.BytesIO(b"abc"), 3) == b"abc"
    with pytest.raises(prep.PreparationError, match="incomplete"):
        prep.read_limited(io.BytesIO(b"ab"), 3)
    with pytest.raises(prep.PreparationError, match="exceeds"):
        prep.read_limited(io.BytesIO(b"abcd"), 3)


PATCH = b"""diff --git a/tools/a.py b/tools/a.py
index 1234567..7654321 100644
--- a/tools/a.py
+++ b/tools/a.py
@@ -1,3 +1,4 @@
 a
-b
+B
+new
 c
@@ -5,2 +6,2 @@
 e
-f
+F
"""


def test_strict_hunks_apply_multiple_exact_locations():
    sections = prep.patch_sections(PATCH)
    assert prep.apply_text_hunks(b"a\nb\nc\nd\ne\nf\n", sections["tools/a.py"]) == b"a\nB\nnew\nc\nd\ne\nF\n"


@pytest.mark.parametrize("mutation", ["context", "count", "new-offset", "old-offset", "no-hunk"])
def test_strict_hunks_refuse_fuzz_or_malformed_input(mutation):
    patch, before = PATCH, b"a\nb\nc\nd\ne\nf\n"
    if mutation == "context":
        before = b"a\nwrong\nc\nd\ne\nf\n"
    elif mutation == "count":
        patch = patch.replace(b"-1,3", b"-1,4")
    elif mutation == "new-offset":
        patch = patch.replace(b"+6,2", b"+7,2")
    elif mutation == "old-offset":
        patch = patch.replace(b"-5,2", b"-2,2")
    else:
        patch = patch.split(b"@@")[0]
    with pytest.raises(prep.PreparationError):
        prep.apply_text_hunks(before, prep.patch_sections(patch)["tools/a.py"])


def test_patch_rejects_renames():
    with pytest.raises(prep.PreparationError, match="renames"):
        prep.patch_sections(PATCH.replace(b"b/tools/a.py", b"b/tools/other.py", 1))


def test_real_audio_patch_keeps_its_complete_reviewed_path_contract():
    patch = ROOT / "patches/next-stable/audio-readiness.patch"
    prep.pinned(patch, prep.PATCH_BYTES, prep.PATCH_SHA)
    sections = prep.patch_sections(patch.read_bytes())
    assert set(sections) == prep.PATCH_PATHS
    assert set(prep.SOURCE_FILES) == set(sections)
    assert prep.PRODUCTION_FILES < set(sections)
    assert all(name.startswith("tests/") for name in set(sections) - prep.PRODUCTION_FILES)


def test_payload_oracle_allows_fresh_venv_but_protects_original_libraries():
    original = {"runtime-libs/lib/libffi.so": {"kind": "file", "bytes": 3, "sha256": "abc", "mode": 420},
                "tools/python/p": {"kind": "file", "sha256": "def", "mode": 493},
                "wheelhouse/main.whl": {"kind": "file", "sha256": "123", "mode": 420}}
    changed = copy.deepcopy(original)
    changed["venv/lib/module.py"] = {"kind": "file", "sha256": "new", "mode": 420}
    assert set(prep.allowed_changes(original, changed)) == {"venv/lib/module.py"}
    changed["runtime-libs/lib/libffi.so"]["sha256"] = "new"
    with pytest.raises(prep.PreparationError):
        prep.allowed_changes(original, changed)


def test_native_environment_does_not_inherit_cross_build_or_user_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("_PYTHON_HOST_PLATFORM", "android-24-arm64_v8a")
    monkeypatch.setenv("PYTHONHOME", "/wrong")
    monkeypatch.setenv("PYTHONPATH", "/wrong")
    monkeypatch.setenv("HERMES_HOME", "/someone-else")
    monkeypatch.setenv("UV_INDEX_URL", "https://wrong.invalid")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/builder/lib")
    payload = tmp_path / "payload"
    state = tmp_path / "state"
    result = prep.native_environment(payload, state)
    assert "_PYTHON_HOST_PLATFORM" not in result
    assert "PYTHONHOME" not in result and "PYTHONPATH" not in result
    assert "UV_INDEX_URL" not in result
    assert "/builder/lib" not in result["LD_LIBRARY_PATH"]
    assert result["HERMES_HOME"] == str(state / "home")
    assert result["HERMES_RUNTIME_DIR"] == str(payload / "tools")
    assert all((state / name).is_dir() for name in ("home", "cache", "tmp"))


@pytest.mark.parametrize("error,framework,count,status", [
    ({"message": "PortAudio -9999"}, False, 0, "unavailable"),
    ({"message": "PortAudio -9999"}, True, 0, "unavailable"),
    (None, True, 1, "initialized"),
    (None, False, 0, "initialized"),
])
def test_initialization_inventory_never_claims_vad(error, framework, count, status):
    result = probe.classify_initialization(error=error, framework_present=framework, input_devices=count)
    assert result["status"] == status
    assert result["physical_vad"] == "not-tested"
    assert result["microphone_accessed"] is False
    assert result["initialization_error"] == error


def test_new_test_file_hunk_does_not_replace_an_existing_file():
    section = ["@@ -0,0 +1,2 @@\n", "+first\n", "+second\n"]
    assert prep.apply_text_hunks(b"", section) == b"first\nsecond\n"
    with pytest.raises(prep.PreparationError):
        prep.apply_text_hunks(b"existing\n", ["@@ -1,1 +1,1 @@\n", "-wrong\n", "+new\n"])


def test_runtime_distribution_and_file_gate_rejects_tampering(tmp_path):
    payload = tmp_path / "payload"
    site = payload / "venv/site-packages"
    site.mkdir(parents=True)
    wheel = payload / "wheelhouse/demo-1.0-py3-none-any.whl"
    wheel.parent.mkdir()
    files = {"demo.py": b"value = 7\n",
             "demo-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
             "demo-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n"}
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
            target = site / name
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(data)
    row = {"name": "demo", "version": "1.0", "file": "wheelhouse/" + wheel.name,
           "size": wheel.stat().st_size, "sha256": prep.sha256(wheel)}
    assert prep.verify_installed(site, {"demo": row}, payload)["wheel_owned_files_checked"] == 3
    (site / "demo.py").write_bytes(b"value = 8\n")
    with pytest.raises(prep.PreparationError, match="file differs"):
        prep.verify_installed(site, {"demo": row}, payload)


def test_runtime_gate_rejects_an_unselected_distribution(tmp_path):
    payload = tmp_path / "payload"
    site = payload / "site"
    extra = site / "extra-9.0.dist-info"
    extra.mkdir(parents=True)
    (extra / "METADATA").write_text("Metadata-Version: 2.1\nName: extra\nVersion: 9.0\n")
    with pytest.raises(prep.PreparationError, match="distributions differ"):
        prep.verify_installed(site, {}, payload)
