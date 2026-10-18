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


def catalog_pair(*, sounddevice_patched=True):
    before = {"wheels": [{"file": f"wheelhouse/item{i}-1-py3-none-any.whl",
                          "name": f"item{i}", "version": "1", "size": 1, "sha256": f"{i:064x}",
                          "source": {"kind": "registry-sdist"}} for i in range(100)]}
    after = copy.deepcopy(before)
    for name in prep.NEW_WHEELS:
        pin = prep.AUDIO_MEMBERS["wheelhouse/" + name]
        size, digest = (prep.SOUNDDEVICE_WHEEL_AFTER if name == prep.SOUNDDEVICE_FILE and sounddevice_patched
                        else (pin["bytes"], pin["sha256"]))
        row = {"file": "wheelhouse/" + name, "name": name.split("-")[0],
               "version": name.split("-")[1], "size": size, "sha256": digest}
        if name == prep.SOUNDDEVICE_FILE:
            row["source"] = copy.deepcopy(prep.SOUNDDEVICE_ORIGIN)
            row["source_fingerprint"] = hashlib.sha256(
                json.dumps(row["source"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        after["wheels"].append(row)
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
    assert set(prep.AUDIO_SOURCE_FILES) == set(sections)
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


@pytest.fixture
def canonical_packaged_tools(tmp_path, monkeypatch):
    """Exercise the actual pinned PM classes when its source checkout is supplied."""
    import os
    from types import SimpleNamespace

    source_text = os.environ.get("HERMES_AUDIO_CANONICAL_PM_SOURCE")
    if not source_text:
        pytest.skip("Canonical PM source checkout is required for the packaged-tool source gate")
    source = Path(source_text).resolve()
    monkeypatch.syspath_prepend(str(source))
    import pm
    import pm.build_operations as build_operations
    import pm.registry as registry
    from pm.install import _identity, _lockfile
    from pm.lock import Facts
    from pm.package import InstallError
    from pm.store import tree_digest

    assert Path(pm.__file__).resolve() == source / "pm/__init__.py"
    lock = _lockfile()
    packages = registry.walk(["python", "uv"], target=prep.TARGET)
    assert {package.name for package in packages} == {"python", "uv"}
    store = tmp_path / "tools"
    store.mkdir()
    facts_path = store / "facts.json"

    def record(package):
        entry = store / package.name
        identity = _identity(lock, package.name, prep.TARGET)
        assert identity is not None
        Facts(facts_path, strict=True).record(
            package.name, lock.version(package.name), package.name,
            package.env(entry, prep.TARGET), store,
            target=identity[0], artifacts=list(identity[1]), digest=tree_digest(entry),
        )

    for package in packages:
        entry = store / package.name
        entry.mkdir()
        binary = package.binary(entry, prep.TARGET)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes((package.name + " fixture; never execute\n").encode())
        record(package)
    return SimpleNamespace(
        store=store, facts_path=facts_path, packages=packages, lock=lock,
        Facts=Facts, InstallError=InstallError, build_operations=build_operations,
        registry=registry, record=record,
    )


def packaged_store_snapshot(store):
    import os
    result = {}
    for directory, dirs, files in os.walk(store):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(store).as_posix()
            result[relative] = (
                path.lstat().st_mode,
                os.readlink(path) if path.is_symlink()
                else path.read_bytes() if path.is_file() else None,
            )
    return result


def test_canonical_build_cache_verifier_rejects_published_flat_entries(canonical_packaged_tools):
    fixture = canonical_packaged_tools
    before = packaged_store_snapshot(fixture.store)
    with pytest.raises(fixture.InstallError, match="tool source failed verification"):
        fixture.build_operations.verified_tools(
            ["python", "uv"], source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
        )
    assert packaged_store_snapshot(fixture.store) == before


def test_published_flat_tools_keep_canonical_contract_without_writes_or_execution(
    canonical_packaged_tools, monkeypatch,
):
    import subprocess
    fixture = canonical_packaged_tools
    before = packaged_store_snapshot(fixture.store)

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only packaged admission must not write or execute")

    with monkeypatch.context() as guard:
        guard.setattr(subprocess, "run", forbidden)
        guard.setattr(Path, "chmod", forbidden)
        guard.setattr(fixture.Facts, "_merge_and_write", forbidden)
        result = prep.verified_packaged_tools(
            source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
        )
    assert isinstance(result, fixture.build_operations.VerifiedTools)
    assert set(result.entries) == {"python", "uv"}
    for name, item in result.entries.items():
        assert item.path.resolve() == (fixture.store / name).resolve()
        assert item.version == fixture.lock.version(name)
        assert item.binary.resolve().is_relative_to((fixture.store / name).resolve())
    assert isinstance(result.environment({}), dict)
    assert packaged_store_snapshot(fixture.store) == before


@pytest.mark.parametrize("mutation", [
    "missing-fact", "version", "target", "artifact", "digest", "entry",
    "tree-byte", "missing-binary", "environment", "extra-file",
])
def test_published_flat_tool_admission_rejects_tampering(canonical_packaged_tools, mutation):
    fixture = canonical_packaged_tools
    package = next(package for package in fixture.packages if package.name == "python")
    binary = package.binary(fixture.store / "python", prep.TARGET)
    document = json.loads(fixture.facts_path.read_text())
    fact = document["packages"]["python"]
    if mutation == "missing-fact":
        del document["packages"]["python"]
    elif mutation == "version":
        fact["version"] = "0.0.0"
    elif mutation == "target":
        fact["target"] = "linux-arm64"
    elif mutation == "artifact":
        fact["artifacts"][0] = "f" * 64
    elif mutation == "digest":
        fact["digest"] = "f" * 64
    elif mutation == "entry":
        fact["entry"] = package.store_entry(fixture.lock.version("python"), prep.TARGET)
    elif mutation == "tree-byte":
        binary.write_bytes(b"changed tool")
    elif mutation == "missing-binary":
        binary.unlink()
    elif mutation == "environment":
        fact["env"]["HERMES_UNDECLARED_TEST_VALUE"] = "changed"
    elif mutation == "extra-file":
        (fixture.store / "python/unrecorded").write_bytes(b"extra")
    fixture.facts_path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    before = packaged_store_snapshot(fixture.store)
    with pytest.raises(fixture.InstallError, match="packaged tool source failed"):
        prep.verified_packaged_tools(
            source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
        )
    assert packaged_store_snapshot(fixture.store) == before


def test_published_flat_admission_refuses_a_changed_canonical_closure(canonical_packaged_tools, monkeypatch):
    fixture = canonical_packaged_tools
    monkeypatch.setattr(fixture.registry, "walk", lambda *args, **kwargs: fixture.packages + [fixture.packages[0]])
    with pytest.raises(fixture.InstallError, match="closure changed"):
        prep.verified_packaged_tools(
            source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
        )


@pytest.mark.parametrize("link_kind", ["absolute-internal", "relative-escape", "broken", "relative-internal"])
def test_published_flat_admission_keeps_canonical_link_policy(canonical_packaged_tools, link_kind):
    fixture = canonical_packaged_tools
    package = next(package for package in fixture.packages if package.name == "python")
    entry = fixture.store / "python"
    binary = package.binary(entry, prep.TARGET)
    link = entry / "test-link"
    if link_kind == "absolute-internal":
        target = binary.resolve()
    elif link_kind == "relative-escape":
        target = Path("../outside")
        (fixture.store / "outside").write_bytes(b"outside")
    elif link_kind == "broken":
        target = Path("missing")
    else:
        target = binary.relative_to(entry)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Host cannot create the canonical link fixture: {exc}")
    fixture.record(package)
    before = packaged_store_snapshot(fixture.store)
    if link_kind == "relative-internal":
        prep.verified_packaged_tools(
            source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
        )
    else:
        with pytest.raises(fixture.InstallError, match="tool copy link escapes entry"):
            prep.verified_packaged_tools(
                source_store=fixture.store, target=prep.TARGET, lock=fixture.lock,
            )
    assert packaged_store_snapshot(fixture.store) == before


def test_marker_patch_has_one_reviewed_source_and_preserves_audio_contract():
    patch = ROOT / prep.MARKER_PATCH_RELATIVE
    prep.pinned(patch, prep.MARKER_PATCH_BYTES, prep.MARKER_PATCH_SHA)
    assert set(prep.patch_sections(patch.read_bytes())) == {prep.MARKER_SOURCE_FILE}
    assert set(prep.SOURCE_FILES) == prep.PATCH_PATHS | {prep.MARKER_SOURCE_FILE}
    assert set(prep.AUDIO_SOURCE_FILES) == prep.PATCH_PATHS


def test_actual_canonical_marker_probe_keeps_markers_without_writing_bytecode(
    canonical_packaged_tools, tmp_path, monkeypatch, record_property,
):
    import os
    import subprocess
    import pm.bundled_wheels as original

    baseline = Path(original.__file__)
    prep.pinned(baseline, *prep.MARKER_SOURCE_BEFORE)
    app = tmp_path / "owned-app"
    source = app / prep.MARKER_SOURCE_FILE
    source.parent.mkdir(parents=True)
    source.write_bytes(baseline.read_bytes())
    result = prep.patch_marker_probe(app, ROOT / prep.MARKER_PATCH_RELATIVE)
    assert result == {prep.MARKER_SOURCE_FILE: {
        "bytes": prep.MARKER_SOURCE_AFTER[0], "sha256": prep.MARKER_SOURCE_AFTER[1],
    }}
    spec = importlib.util.spec_from_file_location("audio_patched_canonical_markers_test", source)
    patched = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = patched
    spec.loader.exec_module(patched)
    original_run = subprocess.run

    def inspect(module, cache):
        calls = []

        def owned_cache_run(command, *args, **kwargs):
            # Redirect the actual child's caches away from the host's stdlib.
            # Keep the canonical helper's own isolation/bytecode switches intact.
            assert Path(command[0]).resolve() == Path(sys.executable).resolve()
            calls.append(list(command))
            return original_run(
                [command[0], "-X", "pycache_prefix=" + str(cache), *command[1:]],
                *args, **kwargs,
            )

        with monkeypatch.context() as guard:
            guard.setattr(subprocess, "run", owned_cache_run)
            markers = module.interpreter_markers(
                Path(sys.executable), {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        assert len(calls) == 1
        assert "-I" in calls[0] and "-S" in calls[0]
        return markers, sorted(cache.rglob("*.pyc"))

    original_markers, old_cache_files = inspect(original, tmp_path / "original-cache")
    patched_markers, new_cache_files = inspect(patched, tmp_path / "patched-cache")
    assert old_cache_files, "The baseline must demonstrate -I ignoring the environment bytecode flag"
    assert not new_cache_files
    assert original_markers == patched_markers
    record_property("original_bytecode_files", len(old_cache_files))
    record_property("patched_bytecode_files", len(new_cache_files))
    record_property("marker_values_equal", original_markers == patched_markers)
    record_property("marker_facts", json.dumps(patched_markers, sort_keys=True))
    assert patched_markers["sys_platform"] == sys.platform
    assert patched_markers["python_full_version"] == ".".join(map(str, sys.version_info[:3]))
    prep.pinned(baseline, *prep.MARKER_SOURCE_BEFORE)


@pytest.mark.parametrize("mutation", ["source-byte", "patch-byte"])
def test_marker_patch_rejects_unknown_source_or_patch_without_writing(
    canonical_packaged_tools, tmp_path, mutation,
):
    import pm.bundled_wheels as original
    app = tmp_path / "owned-app"
    source = app / prep.MARKER_SOURCE_FILE
    source.parent.mkdir(parents=True)
    source.write_bytes(Path(original.__file__).read_bytes())
    patch = tmp_path / "marker.patch"
    patch.write_bytes((ROOT / prep.MARKER_PATCH_RELATIVE).read_bytes())
    target = source if mutation == "source-byte" else patch
    target.write_bytes(target.read_bytes() + b"\n")
    before = source.read_bytes()
    with pytest.raises(prep.PreparationError, match="identity differs"):
        prep.patch_marker_probe(app, patch)
    assert source.read_bytes() == before


@pytest.mark.parametrize("suffix", ["__pycache__", "__pycache__/platform.cpython-314.pyc"])
def test_payload_oracle_still_refuses_generated_tool_bytecode(suffix):
    original = {"tools/python/lib/platform.py": {"kind": "file", "sha256": "abc", "mode": 420}}
    changed = copy.deepcopy(original)
    changed["tools/python/lib/" + suffix] = {"kind": "file", "sha256": "generated", "mode": 420}
    with pytest.raises(prep.PreparationError, match="unreviewed staged payload change"):
        prep.allowed_changes(original, changed)


@pytest.fixture
def generated_tool_cache(tmp_path):
    import py_compile
    from types import SimpleNamespace
    payload, evidence = tmp_path / "payload", tmp_path / "evidence"
    evidence.mkdir()
    source = payload / prep.TOOL_STDLIB_PREFIX / "example.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(
        b'"""Original stdlib fixture; compile without executing."""\n'
        b'def operation(value):\n'
        b'    assert value is not None\n'
        b'    return value + 7\n'
        b'raise AssertionError("cache validation must never execute source")\n'
    )
    baseline = prep.inventory(payload)

    def create(*, optimization=0, invalidation="TIMESTAMP"):
        return Path(py_compile.compile(
            str(source), doraise=True, optimize=optimization,
            invalidation_mode=getattr(py_compile.PycInvalidationMode, invalidation),
        ))

    return SimpleNamespace(payload=payload, evidence=evidence, source=source,
                           baseline=baseline, create=create)


@pytest.mark.parametrize("invalidation", ["TIMESTAMP", "CHECKED_HASH", "UNCHECKED_HASH"])
@pytest.mark.parametrize("optimization", [0, 1, 2])
def test_generated_cache_is_recompiled_archived_and_removed_without_source_execution(
    generated_tool_cache, invalidation, optimization,
):
    f = generated_tool_cache
    path = f.create(optimization=optimization, invalidation=invalidation)
    cache = path.read_bytes()
    assert path.exists()
    result = prep.normalize_generated_tool_bytecode(f.payload, f.baseline, f.evidence)
    assert result["status"] == "normalized"
    assert result["removed_files"] == result["removed_directories"] == 1
    assert result["exact_original_python_inventory_restored"] is True
    assert result["source_files_changed"] == result["baseline_entries_removed"] == 0
    assert result["original_python_inventory_sha256"] == result["final_python_inventory_sha256"]
    assert result["files"][0]["optimization"] == optimization
    assert result["files"][0]["fresh_compile_equal"] is True
    assert prep.inventory(f.payload) == f.baseline
    saved = f.evidence / "generated-tool-bytecode" / path.relative_to(f.payload)
    assert saved.read_bytes() == cache


@pytest.mark.parametrize("mutation", [
    "magic", "flags", "timestamp", "size", "source-hash", "trailing-data",
    "foreign-code", "foreign-filename", "foreign-nested-filename", "cache-tag",
    "source-byte", "extra-nonpyc", "new-empty-directory", "nonstdlib-output",
])
def test_generated_cache_validation_refuses_mutation_before_any_removal(generated_tool_cache, mutation):
    import marshal
    import struct
    import types
    f = generated_tool_cache
    path = f.create(invalidation="CHECKED_HASH" if mutation == "source-hash" else "TIMESTAMP")
    raw = path.read_bytes()
    if mutation == "magic":
        raw = b"BAD!" + raw[4:]
    elif mutation == "flags":
        raw = raw[:4] + struct.pack("<I", 2) + raw[8:]
    elif mutation == "timestamp":
        raw = raw[:8] + b"\0\0\0\0" + raw[12:]
    elif mutation == "size":
        raw = raw[:12] + b"\0\0\0\0" + raw[16:]
    elif mutation == "source-hash":
        raw = raw[:8] + b"\0" * 8 + raw[16:]
    elif mutation == "trailing-data":
        raw += b"unreviewed appended payload"
    elif mutation == "foreign-code":
        raw = raw[:16] + marshal.dumps(compile("x = 1000", str(f.source), "exec", dont_inherit=True))
    elif mutation in ("foreign-filename", "foreign-nested-filename"):
        code = marshal.loads(raw[16:])
        if mutation == "foreign-filename":
            code = code.replace(co_filename="unowned-source.py")
        else:
            constants = tuple(value.replace(co_filename="unowned-nested.py")
                              if type(value) is types.CodeType else value for value in code.co_consts)
            code = code.replace(co_consts=constants)
        raw = raw[:16] + marshal.dumps(code)
    elif mutation == "cache-tag":
        path = path.rename(path.with_name(path.name.replace("cpython-314", "cpython-313")))
    elif mutation == "source-byte":
        f.source.write_bytes(f.source.read_bytes() + b"\n# changed source\n")
    elif mutation == "extra-nonpyc":
        (path.parent / "unreviewed.txt").write_bytes(b"not bytecode")
    elif mutation == "new-empty-directory":
        (f.source.parent / "new-unreviewed-directory").mkdir()
    elif mutation == "nonstdlib-output":
        (f.payload / "tools/python/foreign-output").write_bytes(b"outside stdlib")
    path.write_bytes(raw)
    before = prep.inventory(f.payload)
    with pytest.raises(prep.PreparationError):
        prep.normalize_generated_tool_bytecode(f.payload, f.baseline, f.evidence)
    assert prep.inventory(f.payload) == before
    assert not (f.evidence / "generated-tool-bytecode").exists()


def test_baseline_cache_is_preserved_when_a_new_cache_is_normalized(generated_tool_cache):
    import py_compile
    f = generated_tool_cache
    old_path = f.create()
    baseline = prep.inventory(f.payload)
    old_bytes = old_path.read_bytes()
    second = f.source.with_name("second.py")
    second.write_bytes(b"value = 2\n")
    baseline = prep.inventory(f.payload)
    second_cache = Path(py_compile.compile(str(second), doraise=True))
    result = prep.normalize_generated_tool_bytecode(f.payload, baseline, f.evidence)
    assert result["removed_files"] == 1 and result["removed_directories"] == 0
    assert old_path.read_bytes() == old_bytes and not second_cache.exists()
    assert prep.inventory(f.payload) == baseline


def test_changed_baseline_cache_is_not_removed_or_reclassified(generated_tool_cache):
    f = generated_tool_cache
    path = f.create()
    baseline = prep.inventory(f.payload)
    path.write_bytes(path.read_bytes() + b"changed")
    before = prep.inventory(f.payload)
    with pytest.raises(prep.PreparationError, match="baseline Python"):
        prep.normalize_generated_tool_bytecode(f.payload, baseline, f.evidence)
    assert prep.inventory(f.payload) == before


def test_generated_cache_symlink_is_refused_without_touching_target(generated_tool_cache, tmp_path):
    f = generated_tool_cache
    path = f.create()
    target = tmp_path / "outside.pyc"
    target.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Host cannot create the derived-cache symlink fixture: {exc}")
    raw = target.read_bytes()
    with pytest.raises(prep.PreparationError, match="cache file or symlink"):
        prep.normalize_generated_tool_bytecode(f.payload, f.baseline, f.evidence)
    assert path.is_symlink() and target.read_bytes() == raw


def test_cache_stage_inventory_retains_names_headers_and_provenance(generated_tool_cache):
    f = generated_tool_cache
    before = prep.record_tool_caches(f.payload, f.evidence, "00-before-test")
    path = f.create()
    after = prep.record_tool_caches(f.payload, f.evidence, "01-after-test")
    assert before["cache_files"] == 0 and after["cache_files"] == 1
    row = after["cache_entries"][path.relative_to(f.payload / "tools/python").as_posix()]
    assert row["header_hex"] == path.read_bytes()[:16].hex()
    assert row["sha256"] == prep.sha256(path)
    assert (f.evidence / "tool-cache-00-before-test.json").is_file()
    assert (f.evidence / "tool-cache-01-after-test.json").is_file()


def test_actual_canonical_uv_environment_strips_the_ambient_bytecode_flag(
    canonical_packaged_tools, record_property,
):
    import pm.environment as environment
    from pm.store import tree_digest
    assert "uv venv/uv sync" in tree_digest.__doc__
    actual = environment._base_environment(
        {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PATH": "selected-tools"},
    )
    assert actual == {"PATH": "selected-tools"}
    record_property("canonical_uv_base_environment_removes_python_flags", True)
    record_property("canonical_environment_source", str(Path(environment.__file__).resolve()))


@pytest.fixture
def baseline_documentation_payload(tmp_path, monkeypatch):
    """Small real filesystem fixture; native input pins are replayed separately."""
    from types import SimpleNamespace

    payload = tmp_path / "payload"
    pin = copy.deepcopy(prep.BASELINE_MISSING_DOCUMENTATION_LINK)
    link = payload / pin["path"]
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(pin["target"])
    except OSError as exc:
        pytest.skip(f"Host cannot create the documentation link fixture: {exc}")

    license_file = payload / pin["preserved_license"]["path"]
    license_file.parent.mkdir(parents=True)
    license_raw = b"unchanged license bytes for the filesystem policy fixture\n"
    license_file.write_bytes(license_raw)
    pin["preserved_license"].update(
        bytes=len(license_raw), sha256=hashlib.sha256(license_raw).hexdigest(),
    )
    for directory, filename, target in [
        ("bin", "program", "runner"),
        ("runtime-libs/lib", "libdemo.so.1", "libdemo.so"),
    ]:
        real = payload / directory / filename
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_bytes(b"unexecuted filesystem fixture\n")
        (real.parent / target).symlink_to(filename)
    (payload / "bin/runner-chain").symlink_to("runner")
    original = prep.inventory(payload)
    # The real source pin is deliberately replaced only for this small host
    # fixture. Production accepts the complete, verified native inventory hash.
    pin["original_inventory_sha256"] = prep.inventory_sha(original)
    monkeypatch.setattr(prep, "BASELINE_MISSING_DOCUMENTATION_LINK", pin)
    return SimpleNamespace(
        payload=payload, pin=pin, link=link, original=original,
        license_file=license_file, license_raw=license_raw,
    )


def test_baseline_documentation_gap_is_reported_without_changing_payload(baseline_documentation_payload):
    fixture = baseline_documentation_payload
    before = prep.inventory(fixture.payload)
    report = prep.verify_links(fixture.payload, fixture.original)
    assert report["contained_links"] == {
        "bin/runner": "program",
        "bin/runner-chain": "runner",
        "runtime-libs/lib/libdemo.so": "libdemo.so.1",
    }
    assert set(report["baseline_missing_documentation_links"]) == {fixture.pin["path"]}
    gap = report["baseline_missing_documentation_links"][fixture.pin["path"]]
    assert gap["status"] == "preexisting-missing-documentation-target"
    assert gap["working"] is False and gap["original_link_preserved"] is True
    assert gap["target"] == fixture.pin["target"]
    assert gap["missing_destination"] == fixture.pin["missing_destination"]
    assert gap["preserved_license"] == fixture.pin["preserved_license"]
    assert gap["original_inventory_sha256"] == prep.inventory_sha(fixture.original)
    assert fixture.pin["path"] not in report["contained_links"]
    assert not fixture.link.exists() and fixture.link.is_symlink()
    assert fixture.license_file.read_bytes() == fixture.license_raw
    assert prep.inventory(fixture.payload) == before


def test_baseline_documentation_exception_requires_verified_original_inventory(baseline_documentation_payload):
    fixture = baseline_documentation_payload
    with pytest.raises(prep.PreparationError, match="target is missing"):
        prep.verify_links(fixture.payload)
    with pytest.raises(prep.PreparationError, match="source inventory differs"):
        prep.verify_links(fixture.payload, {})


@pytest.mark.parametrize("mutation", ["unrelated-byte", "unrelated-mode", "missing-link", "link-target", "license"])
def test_baseline_documentation_exception_is_bound_to_entire_source_inventory(
    baseline_documentation_payload, mutation,
):
    fixture = baseline_documentation_payload
    original = copy.deepcopy(fixture.original)
    if mutation == "unrelated-byte":
        original["bin/program"]["sha256"] = "0" * 64
    elif mutation == "unrelated-mode":
        original["bin/program"]["mode"] ^= 0o100
    elif mutation == "missing-link":
        del original[fixture.pin["path"]]
    elif mutation == "link-target":
        original[fixture.pin["path"]]["target"] = "another-missing-document"
    else:
        del original[fixture.pin["preserved_license"]["path"]]
    with pytest.raises(prep.PreparationError, match="source inventory differs"):
        prep.verify_links(fixture.payload, original)


@pytest.mark.parametrize("relative", [
    "bin/missing-executable",
    "runtime-libs/lib/libmissing.so",
    "tools/python/missing-link",
    "tools/ffmpeg/another-missing-link",
    "tools/ffmpeg/data/data/com.termux/files/usr/share/doc/other/copyright",
    "runtime-libs/share/doc/other/copyright",
])
def test_only_the_exact_baseline_documentation_gap_can_be_recorded(
    baseline_documentation_payload, relative,
):
    fixture = baseline_documentation_payload
    extra = fixture.payload / relative
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.symlink_to("absent")
    with pytest.raises(prep.PreparationError, match="target is missing"):
        prep.verify_links(fixture.payload, fixture.original)


@pytest.mark.parametrize("mutation", ["target", "mode"])
def test_baseline_documentation_link_row_must_be_unchanged(
    baseline_documentation_payload, monkeypatch, mutation,
):
    fixture = baseline_documentation_payload
    if mutation == "target":
        fixture.link.unlink()
        fixture.link.symlink_to("../../LICENSES/another-missing-document")
    else:
        # Windows does not expose POSIX symlink chmod. Exercise the native
        # inventory row comparison without pretending to have changed an ABI.
        rows = prep.inventory(fixture.payload)
        rows[fixture.pin["path"]]["mode"] ^= 0o100
        monkeypatch.setattr(prep, "inventory", lambda path: rows)
    with pytest.raises(prep.PreparationError, match="documentation link changed"):
        prep.verify_links(fixture.payload, fixture.original)


@pytest.mark.parametrize("mutation", ["removed", "byte", "mode", "symlink"])
def test_baseline_gap_requires_the_original_unchanged_license(
    baseline_documentation_payload, monkeypatch, mutation,
):
    fixture = baseline_documentation_payload
    if mutation == "removed":
        fixture.license_file.unlink()
    elif mutation == "byte":
        fixture.license_file.write_bytes(fixture.license_raw + b"changed")
    elif mutation == "mode":
        rows = prep.inventory(fixture.payload)
        rows[fixture.pin["preserved_license"]["path"]]["mode"] ^= 0o100
        monkeypatch.setattr(prep, "inventory", lambda path: rows)
    else:
        sibling = fixture.license_file.with_name("copied-license")
        sibling.write_bytes(fixture.license_raw)
        fixture.license_file.unlink()
        fixture.license_file.symlink_to(sibling.name)
    with pytest.raises(prep.PreparationError, match="preserved license differs"):
        prep.verify_links(fixture.payload, fixture.original)


def test_preserved_license_bytes_are_rechecked_against_stale_inventory(
    baseline_documentation_payload, monkeypatch,
):
    fixture = baseline_documentation_payload
    rows = prep.inventory(fixture.payload)
    fixture.license_file.write_bytes(b"x" * len(fixture.license_raw))
    monkeypatch.setattr(prep, "inventory", lambda path: rows)
    with pytest.raises(prep.PreparationError, match="input identity differs"):
        prep.verify_links(fixture.payload, fixture.original)


@pytest.mark.parametrize("kind", ["absolute-internal", "relative-escape", "ancestor-escape", "loop"])
def test_documentation_exception_keeps_runtime_link_containment_strict(
    baseline_documentation_payload, tmp_path, kind,
):
    fixture = baseline_documentation_payload
    link = fixture.payload / "runtime-libs/lib/invalid-link"
    if kind == "absolute-internal":
        link.symlink_to(fixture.payload / "bin/program")
    elif kind == "relative-escape":
        outside = tmp_path / "outside"
        outside.write_bytes(b"outside")
        link.symlink_to(Path("../../../outside"))
    elif kind == "ancestor-escape":
        outside = tmp_path / "outside-dir"
        outside.mkdir()
        (outside / "library").write_bytes(b"outside")
        ancestor = fixture.payload / "escape-dir"
        ancestor.symlink_to(Path("../outside-dir"), target_is_directory=True)
        link.symlink_to(Path("../../escape-dir/library"))
    else:
        link.symlink_to(link.name)
    with pytest.raises(prep.PreparationError):
        prep.verify_links(fixture.payload, fixture.original)


def test_missing_documentation_destination_cannot_be_redirected_inside_payload(
    baseline_documentation_payload,
):
    fixture = baseline_documentation_payload
    destination = fixture.payload / fixture.pin["missing_destination"]
    destination.parent.mkdir(parents=True)
    redirected = destination.parent.with_name("other-license-dir")
    redirected.mkdir()
    # Keep it missing, but redirect the lexical destination's parent elsewhere.
    destination.parent.rmdir()
    destination.parent.symlink_to(redirected.name, target_is_directory=True)
    with pytest.raises(prep.PreparationError, match="documentation destination differs"):
        prep.verify_links(fixture.payload, fixture.original)


@pytest.mark.parametrize("mutation", ["new-target", "retargeted-link", "replaced-link"])
def test_original_payload_oracle_still_rejects_documentation_repairs(
    baseline_documentation_payload, mutation,
):
    fixture = baseline_documentation_payload
    if mutation == "new-target":
        destination = fixture.payload / fixture.pin["missing_destination"]
        destination.parent.mkdir(parents=True)
        destination.write_bytes(fixture.license_raw)
    elif mutation == "retargeted-link":
        fixture.link.unlink()
        fixture.link.symlink_to(fixture.license_file)
    else:
        fixture.link.unlink()
        fixture.link.write_bytes(fixture.license_raw)
    with pytest.raises(prep.PreparationError, match="unreviewed staged payload change"):
        prep.allowed_changes(fixture.original, prep.inventory(fixture.payload))


@pytest.mark.parametrize("error_type", [ModuleNotFoundError, OSError, RuntimeError])
def test_runtime_probe_retains_original_import_exception_and_failure_status(
    tmp_path, monkeypatch, capsys, error_type,
):
    """Real Python exception chaining; no native or audio success is simulated."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    success = evidence / "audio-readiness-probe.json"
    request = evidence / "request.json"
    request.write_text(json.dumps({"payload": str(tmp_path / "payload"), "out": str(success)}))
    original = error_type("original import diagnosis retained exactly")
    predicate_message = "audio import failed for a reason other than PortAudio initialization"

    def failed_worker(_request):
        try:
            raise original
        except Exception:
            prep.require(False, predicate_message)

    monkeypatch.setattr(probe, "runtime_worker", failed_worker)
    assert probe.main(["--runtime-worker", str(request)]) == 1
    assert not success.exists()
    failure = json.loads((evidence / "audio-readiness-failure.json").read_bytes())
    assert failure["status"] == "failed"
    assert failure["stage"] == "runtime-worker"
    assert failure["dependency_readiness"] == "not-completed"
    assert failure["physical_vad"] == "not-tested"
    assert failure["microphone_accessed"] is False
    assert failure["audio_stream_opened"] is False
    assert failure["published"] is False
    assert failure["error"]["type"] == "PreparationError"
    assert failure["error"]["message"] == predicate_message
    assert [entry["type"] for entry in failure["error"]["chain"]] == [
        "PreparationError", error_type.__name__,
    ]
    assert failure["error"]["chain"][1] == {
        "type": error_type.__name__, "module": "builtins",
        "message": str(original), "args": repr(original.args),
    }
    trace = failure["error"]["traceback"]
    assert error_type.__name__ + ": " + str(original) in trace
    assert "During handling of the above exception" in trace
    assert "PreparationError: " + predicate_message in trace
    captured = capsys.readouterr()
    assert captured.out == ""
    assert trace in captured.err


@pytest.mark.parametrize("suppress", [False, True])
def test_probe_exception_receipt_obeys_explicit_cause_and_suppressed_context(suppress):
    try:
        try:
            raise OSError("original diagnostic")
        except OSError as original:
            if suppress:
                raise RuntimeError("outer failure") from None
            raise RuntimeError("outer failure") from original
    except RuntimeError as outer:
        detail = probe.exception_details(outer)
    assert detail["type"] == "RuntimeError"
    assert detail["message"] == "outer failure"
    if suppress:
        assert [row["type"] for row in detail["chain"]] == ["RuntimeError"]
        assert "original diagnostic" not in detail["traceback"]
    else:
        assert [row["type"] for row in detail["chain"]] == ["RuntimeError", "OSError"]
        assert "original diagnostic" in detail["traceback"]
        assert "direct cause" in detail["traceback"]


def test_runtime_probe_still_retains_raw_trace_if_failure_receipt_cannot_be_written(
    tmp_path, monkeypatch, capsys,
):
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"preserved non-directory")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "payload": str(tmp_path / "payload"),
        "out": str(blocked / "audio-readiness-probe.json"),
    }))

    def failed_worker(_request):
        raise OSError("original runtime failure survives receipt I/O failure")

    monkeypatch.setattr(probe, "runtime_worker", failed_worker)
    assert probe.main(["--runtime-worker", str(request)]) == 1
    stderr = capsys.readouterr().err
    assert "Could not retain audio failure receipt:" in stderr
    assert "Traceback (most recent call last):" in stderr
    assert "OSError: original runtime failure survives receipt I/O failure" in stderr
    assert blocked.read_bytes() == b"preserved non-directory"


def test_orchestrator_failure_keeps_full_trace_and_nonzero_exit(tmp_path, monkeypatch, capsys):
    def failed_run(_options):
        raise RuntimeError("child failed; original raw logs remain authoritative")

    monkeypatch.setattr(probe, "run", failed_run)
    assert probe.main(["--environment", str(tmp_path)]) == 1
    stderr = capsys.readouterr().err
    assert "Traceback (most recent call last):" in stderr
    assert "RuntimeError: child failed; original raw logs remain authoritative" in stderr
    assert not list(tmp_path.iterdir())

# The unchanged 32 KiB original wheel is a self-contained, pinned input fixture.
# These tests read code/data and control loader calls; they do not run PortAudio.
SOUNDDEVICE_FIXTURE = ROOT / "tests/fixtures/audio_sounddevice" / prep.SOUNDDEVICE_FILE
SOUNDDEVICE_PATCH = ROOT / prep.SOUNDDEVICE_PATCH_RELATIVE


def sounddevice_members(raw=None):
    source = io.BytesIO(raw) if raw is not None else SOUNDDEVICE_FIXTURE
    with zipfile.ZipFile(source) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def test_actual_sounddevice_derivative_preserves_original_members_and_full_record():
    import base64
    import csv

    original_wheel = SOUNDDEVICE_FIXTURE.read_bytes()
    original_patch = SOUNDDEVICE_PATCH.read_bytes()
    first, proof = prep.patched_sounddevice_wheel(SOUNDDEVICE_FIXTURE, SOUNDDEVICE_PATCH)
    second, repeated = prep.patched_sounddevice_wheel(SOUNDDEVICE_FIXTURE, SOUNDDEVICE_PATCH)
    assert first == second and proof == repeated
    assert SOUNDDEVICE_FIXTURE.read_bytes() == original_wheel
    assert SOUNDDEVICE_PATCH.read_bytes() == original_patch
    before, after = sounddevice_members(), sounddevice_members(first)
    assert set(before) == set(after)
    assert {name for name in before if before[name] != after[name]} == {
        "sounddevice.py", "sounddevice-0.5.5.dist-info/RECORD",
    }
    assert proof["unchanged_member_count"] == 6
    rows = list(csv.reader(io.StringIO(after["sounddevice-0.5.5.dist-info/RECORD"].decode())))
    assert len(rows) == len(after) == 8
    for name, digest, size in rows:
        if name.endswith("/RECORD"):
            assert digest == size == ""
        else:
            assert int(size) == len(after[name])
            assert base64.urlsafe_b64decode(digest.removeprefix("sha256=") + "=") == hashlib.sha256(after[name]).digest()
    assert (len(first), hashlib.sha256(first).hexdigest()) == prep.SOUNDDEVICE_WHEEL_AFTER


def test_actual_sounddevice_patch_independently_applies_with_git(tmp_path):
    import subprocess

    (tmp_path / "sounddevice.py").write_bytes(sounddevice_members()["sounddevice.py"])
    result = subprocess.run(["git", "apply", "--check", str(SOUNDDEVICE_PATCH)],
                            cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    result = subprocess.run(["git", "apply", str(SOUNDDEVICE_PATCH)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    body, _ = prep.patched_sounddevice_wheel(SOUNDDEVICE_FIXTURE, SOUNDDEVICE_PATCH)
    assert (tmp_path / "sounddevice.py").read_bytes() == sounddevice_members(body)["sounddevice.py"]


def loader_observation(source, *, platform="android", system="Android", answers=(None, None, None),
                       load_error=None, find_error=None):
    """Execute the real module's complete top-level loading try/except only."""
    import ast
    import os
    from types import SimpleNamespace

    tree = ast.parse(source)
    block = next(node for node in tree.body
                 if isinstance(node, ast.Try) and any(
                     isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                     and isinstance(call.func.value, ast.Name) and call.func.value.id == "_ffi"
                     and call.func.attr == "dlopen" for call in ast.walk(node)))
    calls, loads = [], []
    answer_iter = iter(answers)
    handle = object()

    def find_library(name):
        calls.append(name)
        if find_error is not None:
            raise find_error
        return next(answer_iter)

    def dlopen(name):
        loads.append(name)
        if load_error is not None:
            raise load_error
        return handle

    namespace = {
        "_sys": SimpleNamespace(platform=platform),
        "_platform": SimpleNamespace(system=lambda: system, machine=lambda: "AMD64"),
        "_os": os, "_find_library": find_library, "_ffi": SimpleNamespace(dlopen=dlopen),
    }
    result = {"find": calls, "dlopen": loads}
    try:
        exec(compile(ast.Module(body=[block], type_ignores=[]), "<actual-sounddevice-loader>", "exec"), namespace)
    except Exception as exc:
        result["error"] = exc
    else:
        result["handle_is_loader_result"] = namespace["_lib"] is handle
    return result


def patched_sounddevice_source():
    body, _ = prep.patched_sounddevice_wheel(SOUNDDEVICE_FIXTURE, SOUNDDEVICE_PATCH)
    return sounddevice_members(body)["sounddevice.py"]


def test_android_resolves_packaged_soname_after_all_original_lookups_fail():
    result = loader_observation(patched_sounddevice_source())
    assert len(result["find"]) == 3
    assert result["find"][0] == "portaudio"
    assert result["dlopen"] == ["libportaudio.so"]
    assert result["handle_is_loader_result"] is True
    original = loader_observation(sounddevice_members()["sounddevice.py"])
    assert result["find"] == original["find"]
    assert original["dlopen"] == []
    assert type(original["error"]) is OSError
    assert str(original["error"]) == "PortAudio library not found"


@pytest.mark.parametrize("found_index", [0, 1, 2])
@pytest.mark.parametrize("platform,system", [("android", "Android"), ("linux", "Linux"), ("darwin", "Darwin"), ("win32", "Windows")])
def test_existing_successful_library_discovery_keeps_its_exact_result(found_index, platform, system):
    answers = [None] * found_index + ["/original/found-portaudio"]
    before = loader_observation(sounddevice_members()["sounddevice.py"],
                                platform=platform, system=system, answers=answers)
    after = loader_observation(patched_sounddevice_source(),
                               platform=platform, system=system, answers=answers)
    assert before == after
    assert after["dlopen"] == ["/original/found-portaudio"]
    assert after["handle_is_loader_result"] is True


@pytest.mark.parametrize("platform", ["linux", "freebsd14", "android-other"])
def test_unsuccessful_non_android_lookup_retains_original_exception(platform):
    results = [loader_observation(source, platform=platform, system="Linux")
               for source in [sounddevice_members()["sounddevice.py"], patched_sounddevice_source()]]
    assert results[0]["find"] == results[1]["find"]
    for result in results:
        assert result["dlopen"] == []
        assert type(result["error"]) is OSError
        assert str(result["error"]) == "PortAudio library not found"


@pytest.mark.parametrize("where", ["discovery", "loading"])
def test_android_fallback_preserves_the_actual_failure_object(where):
    failure = OSError("original native operation failure")
    kw = {"find_error": failure} if where == "discovery" else {"load_error": failure}
    result = loader_observation(patched_sounddevice_source(), **kw)
    assert result["error"] is failure
    assert result["dlopen"] == ([] if where == "discovery" else ["libportaudio.so"])


def test_android_patch_does_not_change_initialization_or_other_module_code():
    import ast

    trees = [ast.parse(s) for s in [sounddevice_members()["sounddevice.py"], patched_sounddevice_source()]]
    for tree in trees:
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.Try) and any(
                isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name) and call.func.value.id == "_ffi"
                and call.func.attr == "dlopen" for call in ast.walk(node)))]
    assert ast.dump(trees[0], include_attributes=False) == ast.dump(trees[1], include_attributes=False)


@pytest.mark.parametrize("mutation", ["member-missing", "member-extra", "body", "record-duplicate", "record-self", "record-hash"])
def test_sounddevice_record_rejects_missing_extra_or_changed_content(mutation):
    import csv

    members = sounddevice_members()
    record = "sounddevice-0.5.5.dist-info/RECORD"
    rows = list(csv.reader(io.StringIO(members[record].decode())))
    if mutation == "member-missing":
        members.pop("_sounddevice.py")
    elif mutation == "member-extra":
        members["unreviewed_native.so"] = b"extra"
    elif mutation == "body":
        members["_sounddevice.py"] += b"# changed\n"
    else:
        if mutation == "record-duplicate":
            rows.append(rows[0])
        elif mutation == "record-self":
            rows[-1][1] = "sha256=" + "0" * 43
        else:
            rows[0][1] = "sha256=" + "0" * 43
        stream = io.StringIO()
        csv.writer(stream, lineterminator="\n").writerows(rows)
        members[record] = stream.getvalue().encode()
    with pytest.raises(prep.PreparationError):
        prep.verify_sounddevice_record(members)


@pytest.mark.parametrize("changed", ["wheel", "patch"])
def test_sounddevice_derivation_refuses_changed_inputs_without_mutating_them(tmp_path, changed):
    wheel = tmp_path / prep.SOUNDDEVICE_FILE
    patch = tmp_path / "patch"
    wheel.write_bytes(SOUNDDEVICE_FIXTURE.read_bytes())
    patch.write_bytes(SOUNDDEVICE_PATCH.read_bytes())
    target = wheel if changed == "wheel" else patch
    target.write_bytes(target.read_bytes() + b"x")
    before = (wheel.read_bytes(), patch.read_bytes())
    with pytest.raises(prep.PreparationError, match="identity differs"):
        prep.patched_sounddevice_wheel(wheel, patch)
    assert before == (wheel.read_bytes(), patch.read_bytes())


def original_audio_catalog_payload(tmp_path):
    before, after = catalog_pair(sounddevice_patched=False)
    payload = tmp_path / "payload"
    (payload / "wheelhouse").mkdir(parents=True)
    (payload / "wheelhouse" / prep.SOUNDDEVICE_FILE).write_bytes(SOUNDDEVICE_FIXTURE.read_bytes())
    raw = (json.dumps(after, sort_keys=True, indent=2) + "\n").encode()
    (payload / "bundled-wheels.json").write_bytes(raw)
    descriptor = {"path": "bundled-wheels.json", "sha256": hashlib.sha256(raw).hexdigest()}
    return payload, before, after, descriptor


def test_sounddevice_catalog_changes_only_new_wheel_bytes_and_preserves_origin(tmp_path):
    payload, original, canonical, descriptor = original_audio_catalog_payload(tmp_path)
    new_descriptor, after, proof = prep.patch_catalogued_sounddevice(
        payload, original, SOUNDDEVICE_PATCH, descriptor)
    before_rows = {row["file"]: row for row in canonical["wheels"]}
    after_rows = {row["file"]: row for row in after["wheels"]}
    filename = "wheelhouse/" + prep.SOUNDDEVICE_FILE
    assert {name for name in before_rows if before_rows[name] != after_rows[name]} == {filename}
    assert {k for k in before_rows[filename] if before_rows[filename][k] != after_rows[filename][k]} == {"size", "sha256"}
    assert proof["original_registry_wheel_source_and_fingerprint_preserved"] is True
    assert proof["original_100_catalog_rows_preserved"] is True
    assert proof["catalog_original_row"]["source"]["sha256"] == hashlib.sha256(SOUNDDEVICE_FIXTURE.read_bytes()).hexdigest()
    assert new_descriptor["sha256"] == hashlib.sha256((payload / "bundled-wheels.json").read_bytes()).hexdigest()
    assert new_descriptor["sha256"] == proof["catalog_after_sha256"]
    prep.verify_catalog_union(original, after)


@pytest.mark.parametrize("mutation", ["sdist", "url", "origin-sha", "fingerprint", "name", "version", "descriptor", "already-patched"])
def test_sounddevice_catalog_rejects_false_provenance_and_stale_inputs_without_writes(tmp_path, mutation):
    payload, original, canonical, descriptor = original_audio_catalog_payload(tmp_path)
    row = canonical["wheels"][-1]
    if mutation == "sdist":
        row["source"]["kind"] = "registry-sdist"
    elif mutation == "url":
        row["source"]["url"] = "https://wrong.invalid/sounddevice.whl"
    elif mutation == "origin-sha":
        row["source"]["sha256"] = "0" * 64
    elif mutation == "fingerprint":
        row["source_fingerprint"] = "0" * 64
    elif mutation == "name":
        row["name"] = "other"
    elif mutation == "version":
        row["version"] = "0.5.6"
    elif mutation == "already-patched":
        row["size"], row["sha256"] = prep.SOUNDDEVICE_WHEEL_AFTER
    raw = (json.dumps(canonical, sort_keys=True, indent=2) + "\n").encode()
    (payload / "bundled-wheels.json").write_bytes(raw)
    descriptor["sha256"] = "0" * 64 if mutation == "descriptor" else hashlib.sha256(raw).hexdigest()
    before_files = {p.relative_to(payload): p.read_bytes() for p in payload.rglob("*") if p.is_file()}
    with pytest.raises(prep.PreparationError):
        prep.patch_catalogued_sounddevice(payload, original, SOUNDDEVICE_PATCH, descriptor)
    assert before_files == {p.relative_to(payload): p.read_bytes() for p in payload.rglob("*") if p.is_file()}


def test_canonical_pm_selects_derived_bytes_against_original_locked_wheel_source(
    canonical_packaged_tools, tmp_path,
):
    import pm
    import pm.bundled_wheels as bundled

    source = Path(pm.__file__).resolve().parent.parent
    assert prep.sha256(source / "uv.lock") == prep.UV_LOCK_SHA
    payload = tmp_path / "canonical-wheel"
    wheelhouse = payload / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    path = wheelhouse / prep.SOUNDDEVICE_FILE
    path.write_bytes(SOUNDDEVICE_FIXTURE.read_bytes())
    original_descriptor = bundled.write_catalog(payload, wheelhouse=wheelhouse, lock_paths=(source / "uv.lock",))
    catalog = json.loads((payload / "bundled-wheels.json").read_bytes())
    assert len(catalog["wheels"]) == 1
    row = catalog["wheels"][0]
    assert row["source"] == prep.SOUNDDEVICE_ORIGIN
    original_origin = copy.deepcopy(row["source"])
    original_fingerprint = row["source_fingerprint"]
    derived, _ = prep.patched_sounddevice_wheel(path, SOUNDDEVICE_PATCH)
    path.write_bytes(derived)
    row.update(sha256=hashlib.sha256(derived).hexdigest(), size=len(derived))
    selected = bundled.Catalog(original_descriptor["sha256"], payload, tuple(catalog["wheels"])).select(
        "sounddevice==0.5.5\n", source / "uv.lock",
        {"sys_platform": "android", "python_version": "3.14", "python_full_version": "3.14.6",
         "platform_machine": "aarch64", "platform_system": "Android", "extra": ""},
    )
    assert len(selected) == 1 and selected[0].path == path
    assert selected[0].sha256 == prep.SOUNDDEVICE_WHEEL_AFTER[1]
    assert row["source"] == original_origin and row["source_fingerprint"] == original_fingerprint


def original_audio_wrapper_members():
    """Read two real archive members without running dpkg or native code."""
    import tarfile

    archive = ROOT / "tests/fixtures/audio_namespace" / prep.STUB_FILE
    raw = archive.read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (prep.STUB_BYTES, prep.STUB_SHA)
    assert raw[:8] == b"!<arch>\n"
    offset, parts = 8, {}
    while offset < len(raw):
        header = raw[offset:offset + 60]
        assert len(header) == 60 and header[-2:] == bytes((96, 10))
        size = int(header[48:58])
        name = header[:16].decode().strip().rstrip("/")
        assert name not in parts and offset + 60 + size <= len(raw)
        parts[name] = raw[offset + 60:offset + 60 + size]
        offset += 60 + size + size % 2
    assert offset == len(raw) and parts["debian-binary"] == b"2.0\n"
    name = next(n for n in parts if n.startswith("data.tar."))
    result = {}
    with tarfile.open(fileobj=io.BytesIO(parts[name]), mode="r:*") as tar:
        for member in tar:
            leaf = Path(member.name).name
            if leaf in ("libOpenSLES.so", prep.PLATFORM_NAMESPACE_FILE):
                assert member.isfile() and leaf not in result
                result[leaf] = tar.extractfile(member).read()
    assert set(result) == {"libOpenSLES.so", prep.PLATFORM_NAMESPACE_FILE}
    return archive, result


def emulate_wrapper_extraction(monkeypatch, members):
    """The host test replaces only the external dpkg extraction boundary."""
    calls = []

    def extract(command, work, name, **kwargs):
        assert command[:2] == ["dpkg-deb", "--extract"]
        assert name == "extract-opensles" and not kwargs
        source = Path(command[3]) / prep.PREFIX.relative_to("/") / "lib"
        source.mkdir(parents=True)
        for leaf, raw in members.items():
            (source / leaf).write_bytes(raw)
        calls.append(command)

    monkeypatch.setattr(prep, "run_logged", extract)
    return calls


def test_owned_opensles_extraction_includes_original_namespace_dependency(tmp_path, monkeypatch):
    import ast
    import struct

    archive, members = original_audio_wrapper_members()
    calls = emulate_wrapper_extraction(monkeypatch, members)
    destination = tmp_path / "libOpenSLES.so"
    receipt = prep.extract_opensles(archive, destination, tmp_path)
    assert len(calls) == 1
    assert destination.read_bytes() == members["libOpenSLES.so"]
    namespace = tmp_path / prep.PLATFORM_NAMESPACE_FILE
    assert namespace.read_bytes() == members[prep.PLATFORM_NAMESPACE_FILE]
    assert len(namespace.read_bytes()) == prep.PLATFORM_NAMESPACE_BYTES
    assert hashlib.sha256(namespace.read_bytes()).hexdigest() == prep.PLATFORM_NAMESPACE_SHA
    assert receipt["namespace_library"]["needed"] == ["libc.so", "libdl.so"]
    assert receipt["wrapper_needed"] == ["libc.so", "libdl.so", prep.PLATFORM_NAMESPACE_FILE]
    assert receipt["archive_sha256"] == prep.STUB_SHA
    # Interpret the actual original ELF bytes with the independent packaging
    # parser; this does not import either foreign-architecture library.
    tree = ast.parse((ROOT / "scripts/build_wheels.py").read_text())
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "_elf_needed_libraries")
    scope = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<original ELF parser>", "exec"), scope)
    for name, raw in members.items():
        assert raw[:6] == b"\x7fELF\x02\x01"
        assert struct.unpack_from("<H", raw, 18)[0] == 183
        expected = {"libc.so", "libdl.so"}
        if name == "libOpenSLES.so":
            expected.add(prep.PLATFORM_NAMESPACE_FILE)
        assert scope["_elf_needed_libraries"](raw) == expected
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "libOpenSLES.so", prep.PLATFORM_NAMESPACE_FILE,
    ]


@pytest.mark.parametrize("leaf", ["libOpenSLES.so", prep.PLATFORM_NAMESPACE_FILE])
@pytest.mark.parametrize("mutation", ["changed-byte", "missing"])
def test_wrapper_extraction_rejects_missing_or_changed_member_before_copying(
    tmp_path, monkeypatch, leaf, mutation,
):
    archive, members = original_audio_wrapper_members()
    if mutation == "missing":
        members.pop(leaf)
    else:
        raw = members[leaf]
        members[leaf] = raw[:-1] + bytes([raw[-1] ^ 1])
    emulate_wrapper_extraction(monkeypatch, members)
    with pytest.raises(prep.PreparationError):
        prep.extract_opensles(archive, tmp_path / "libOpenSLES.so", tmp_path)
    assert not (tmp_path / "libOpenSLES.so").exists()
    assert not (tmp_path / prep.PLATFORM_NAMESPACE_FILE).exists()


@pytest.mark.parametrize("leaf", ["libOpenSLES.so", prep.PLATFORM_NAMESPACE_FILE])
def test_wrapper_extraction_preserves_existing_destination_before_any_copy(tmp_path, monkeypatch, leaf):
    archive, members = original_audio_wrapper_members()
    emulate_wrapper_extraction(monkeypatch, members)
    existing = tmp_path / leaf
    existing.write_bytes(b"pre-existing owned content")
    with pytest.raises(prep.PreparationError, match="destination already exists"):
        prep.extract_opensles(archive, tmp_path / "libOpenSLES.so", tmp_path)
    assert existing.read_bytes() == b"pre-existing owned content"
    assert sorted(p.name for p in tmp_path.iterdir()) == [leaf]


def test_wrapper_extraction_rejects_changed_archive_without_executing_dpkg(tmp_path, monkeypatch):
    archive, members = original_audio_wrapper_members()
    calls = emulate_wrapper_extraction(monkeypatch, members)
    raw = archive.read_bytes()
    altered = tmp_path / prep.STUB_FILE
    altered.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(prep.PreparationError):
        prep.extract_opensles(altered, tmp_path / "libOpenSLES.so", tmp_path)
    assert calls == []
    assert sorted(p.name for p in tmp_path.iterdir()) == [prep.STUB_FILE]


def test_payload_oracle_allows_only_new_namespace_bytes_and_preserves_existing_libraries():
    new_name = "runtime-libs/lib/" + prep.PLATFORM_NAMESPACE_FILE
    row = {"kind": "file", "bytes": prep.PLATFORM_NAMESPACE_BYTES,
           "sha256": prep.PLATFORM_NAMESPACE_SHA, "mode": 420}
    original = {"runtime-libs/lib/libffi.so": {"kind": "file", "bytes": 1,
                                              "sha256": "a" * 64, "mode": 420}}
    after = copy.deepcopy(original)
    after[new_name] = row
    assert prep.allowed_changes(original, after) == {new_name: {"before": None, "after": row}}
    changed = copy.deepcopy(after)
    changed[new_name]["sha256"] = "f" * 64
    with pytest.raises(prep.PreparationError, match="original runtime library changed"):
        prep.allowed_changes(after, changed)
    escaped = copy.deepcopy(after)
    escaped["runtime-libs/lib/libunreviewed.so"] = row
    with pytest.raises(prep.PreparationError, match="unreviewed staged payload change"):
        prep.allowed_changes(original, escaped)
