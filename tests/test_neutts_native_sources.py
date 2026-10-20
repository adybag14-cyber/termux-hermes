"""Host-only source/transport negative controls; no compiler or package install."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_prepare_tested", ROOT / "scripts/prepare_neutts_native_sources.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def expectation(rows):
    return {"sha256": prepare.digest(prepare.canonical(rows)),
            "file_count": len(rows), "bytes": sum(row["size"] for row in rows)}


def test_frozen_lock_and_narrow_source_scope():
    lock, _ = prepare.load_lock(ROOT / "scripts/neutts_native_sources_lock.json")
    assert {p["name"] for p in lock["additional_python_wheels"]} == {
        "scikit-build-core", "packaging", "pathspec", "diskcache"}
    vendor = lock["sources"]["llama-cpp-python"]["submodules"]["vendor/llama.cpp"]
    assert len(vendor["omitted_model_fixtures"]) == 19
    assert sum(p["size"] for p in vendor["omitted_model_fixtures"]) == 77556152
    assert lock["build_apt"]["additional_count"] == 19
    assert lock["sources"]["numba"]["version"] == "0.67.0"


def test_replacement_lock_is_rejected(tmp_path):
    raw = (ROOT / "scripts/neutts_native_sources_lock.json").read_bytes()
    path = tmp_path / "lock.json"
    path.write_bytes(raw.replace(b'"version": "0.67.0"', b'"version": "0.67.1"'))
    with pytest.raises(prepare.PrepareError, match="SHA-256"):
        prepare.load_lock(path)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../b", "a//b",
                                  "C:/drive", "a\\b", ".git/config", "a/\0b"])
def test_unsafe_source_paths_rejected(name):
    with pytest.raises(prepare.PrepareError):
        prepare.safe_path(name)


def test_source_manifest_detects_extra_missing_and_changed_bytes(tmp_path):
    rows = [prepare.file_row("code.py", "100644", b"print('source')\n")]
    expected = expectation(rows)
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_bytes(b"print('source')\n")
    assert prepare.verify_source_tree(source, rows, expected)["status"] == "passed"
    (source / "extra.py").write_bytes(b"extra")
    with pytest.raises(prepare.PrepareError, match="extra source"):
        prepare.verify_source_tree(source, rows, expected)
    (source / "extra.py").unlink()
    (source / "code.py").write_bytes(b"print('edited')\n")
    with pytest.raises(prepare.PrepareError, match="identity mismatch"):
        prepare.verify_source_tree(source, rows, expected)
    (source / "code.py").unlink()
    with pytest.raises(prepare.PrepareError, match="Missing"):
        prepare.verify_source_tree(source, rows, expected)


def source_tar(path, entries):
    with tarfile.open(path, "w:gz") as archive:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = 0o644
            if kind == tarfile.REGTYPE:
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            else:
                info.linkname = payload.decode()
                archive.addfile(info)
    return {"root": "numba-0.67.0", "artifact": {
        "bytes": path.stat().st_size, "sha256": prepare.digest(path.read_bytes())}}


def test_safe_sdist_is_verified_and_extracted(tmp_path):
    archive = tmp_path / "source.tar.gz"
    row = prepare.file_row("setup.py", "100644", b"source\n")
    pin = source_tar(archive, [("numba-0.67.0/setup.py", tarfile.REGTYPE, b"source\n")])
    pin["manifest"] = expectation([row])
    rows = prepare.extract_numba(archive, tmp_path / "source", pin)
    assert rows == [row]
    assert (tmp_path / "source/setup.py").read_bytes() == b"source\n"


@pytest.mark.parametrize("entries", [
    [("numba-0.67.0/../../outside", tarfile.REGTYPE, b"bad")],
    [("numba-0.67.0/link", tarfile.SYMTYPE, b"../../outside")],
    [("numba-0.67.0/link", tarfile.LNKTYPE, b"../../outside")],
    [("numba-0.67.0/code.py", tarfile.REGTYPE, b"one"),
     ("numba-0.67.0/code.py", tarfile.REGTYPE, b"two")],
])
def test_source_archive_rejects_traversal_links_and_duplicates(tmp_path, entries):
    archive = tmp_path / "bad.tar.gz"
    pin = source_tar(archive, entries)
    pin["manifest"] = expectation([])
    with pytest.raises(prepare.PrepareError):
        prepare.extract_numba(archive, tmp_path / "source", pin)
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("tree", [
    b"120000 blob " + b"a" * 40 + b"\tlink\0",
    b"100644 blob " + b"a" * 40 + b"\t../outside\0",
    (b"100644 blob " + b"a" * 40 + b"\tx\0") * 2,
    b"100644 blob not-a-hash\tx\0",
])
def test_git_tree_rejects_unsafe_or_ambiguous_objects(tree):
    with pytest.raises(prepare.PrepareError):
        prepare.parse_tree(tree)


def test_sparse_checkout_omits_pinned_models_before_materializing(monkeypatch, tmp_path):
    calls = []
    commit, tree, blob = "1" * 40, "2" * 40, "3" * 40
    pin = {"repository": "https://github.com/ggml-org/llama.cpp.git",
           "commit": commit, "tree": tree,
           "omitted_model_fixtures": [{"path": "models/fixture.gguf", "mode": "100644",
                                      "git_blob_sha1": blob, "size": 10}]}

    def git_run(checkout, args, deadline, data=None):
        calls.append((args, data))
        if args == ["rev-parse", "FETCH_HEAD"]:
            return (commit + "\n").encode()
        if args == ["rev-parse", "FETCH_HEAD^{tree}"]:
            return (tree + "\n").encode()
        if args[:2] == ["--no-lazy-fetch", "cat-file"]:
            return (blob + " missing\n").encode()
        if args[:1] == ["ls-tree"]:
            return ("100644 blob " + blob + "\tmodels/fixture.gguf\0").encode()
        return b""

    monkeypatch.setattr(prepare, "git_run", git_run)
    prepare.acquire_git(pin, tmp_path, time.monotonic() + 30)
    checkout_index = next(i for i, (args, _) in enumerate(calls) if args[0] == "checkout")
    sparse_index = next(i for i, (args, _) in enumerate(calls) if args[:2] == ["sparse-checkout", "set"])
    assert sparse_index < checkout_index
    assert b"!/models/fixture.gguf\n" in calls[sparse_index][1]
    fetch = next(args for args, _ in calls if args[0] == "fetch")
    assert "--filter=blob:none" in fetch and "--depth=1" in fetch
    assert all("-l" not in args and "--long" not in args for args, _ in calls)


def test_submodule_replacement_and_git_blob_tampering_are_rejected(tmp_path):
    source = tmp_path / "checkout"
    source.mkdir()
    (source / "code").write_bytes(b"unexpected")
    row = prepare.file_row("code", "100644", b"original")
    pin = {"manifest": expectation([row])}
    entries = [{"path": "code", "mode": "100644", "kind": "blob", "oid": row["git_blob_sha1"]}]
    with pytest.raises(prepare.PrepareError, match="Git blob"):
        prepare.export_git(source, entries, pin, tmp_path / "export")
    bad = [{"path": "vendor/llama.cpp", "mode": "160000", "kind": "commit", "oid": "f" * 40}]
    with pytest.raises(prepare.PrepareError, match="Submodule"):
        prepare.export_git(source, bad, pin, tmp_path / "export2")


def test_numba_download_does_not_accept_replacement_artifact(tmp_path):
    lock, _ = prepare.load_lock(ROOT / "scripts/neutts_native_sources_lock.json")
    artifact = copy.deepcopy(lock["sources"]["numba"]["artifact"])
    artifact["url"] = "https://example.invalid/source.tar.gz"
    with pytest.raises(prepare.PrepareError, match="Unexpected source archive"):
        prepare.download_numba(artifact, tmp_path / "source", None, time.monotonic() + 30)


def test_fresh_output_rule_precedes_acquisition(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("owned by caller")
    monkeypatch.setattr(prepare, "core_verifier", lambda: pytest.fail("Acquisition should not start"))
    with pytest.raises(prepare.PrepareError, match="fresh directory"):
        prepare.prepare(ROOT / "scripts/neutts_native_sources_lock.json", output)
    assert sentinel.read_text() == "owned by caller"


def test_materialized_model_object_is_rejected_without_lazy_fetch(monkeypatch, tmp_path):
    called = []
    def git_run(checkout, args, deadline, data=None):
        called.append(args)
        return (("a" * 40) + " blob 10\n").encode()
    monkeypatch.setattr(prepare, "git_run", git_run)
    with pytest.raises(prepare.PrepareError, match="model object"):
        prepare.require_model_objects_absent(
            tmp_path, {"models/x.gguf": {"git_blob_sha1": "a" * 40}}, time.monotonic() + 30)
    assert called[0][0] == "--no-lazy-fetch"
