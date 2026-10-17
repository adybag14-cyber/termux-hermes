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
