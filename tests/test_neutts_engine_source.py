"""Exact source and real CMake regressions for the offline NeuTTS source hook."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prep = module("prepare_neutts_engine_source.py", "_engine_source_test")


@pytest.fixture
def exact_inputs():
    location = os.environ.get("HERMES_NEUTTS_ENGINE_SOURCE_INPUTS")
    if not location:
        pytest.skip("Exact NeuTTS source inputs were not supplied")
    path = Path(location)
    prep.verify_inputs(path)
    return path


def test_changed_archive_is_rejected_before_creating_source(tmp_path):
    lock, _ = prep.load_lock()
    archive = tmp_path / "changed.tar.gz"
    archive.write_bytes(b"not the exact source archive")
    out = tmp_path / "source"
    with pytest.raises(RuntimeError, match="source archive differs"):
        prep.extract_source(archive, out, lock["source"])
    assert not out.exists()


def test_real_source_replay_retains_git_tree_metadata_and_every_asset(exact_inputs, tmp_path, record_property):
    lock, _ = prep.load_lock()
    archive = exact_inputs / lock["source"]["artifact"]["filename"]
    source_tree = {}
    count = 0
    with tarfile.open(archive, "r:gz") as stream:
        for entry in stream:
            if not entry.isfile():
                continue
            relative = entry.name.removeprefix(lock["source"]["root"] + "/")
            raw = stream.extractfile(entry).read()
            digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).digest()
            node = source_tree
            parts = PurePosixPath(relative).parts
            for name in parts[:-1]:
                node = node.setdefault(name, {})
            assert parts[-1] not in node
            node[parts[-1]] = ("100755" if entry.mode & 0o111 else "100644", digest)
            count += 1

    def git_tree(node):
        contents = []
        for name in sorted(node, key=lambda name: (name + ("/" if isinstance(node[name], dict) else "")).encode()):
            value = node[name]
            mode, digest = ("40000", git_tree(value)) if isinstance(value, dict) else value
            contents.append(mode.encode() + b" " + name.encode() + b"\0" + digest)
        raw = b"".join(contents)
        return hashlib.sha1(b"tree " + str(len(raw)).encode() + b"\0" + raw).digest()

    assert count == 56
    assert git_tree(source_tree).hex() == lock["source"]["tree"]
    out = tmp_path / "fresh-source"
    receipt = prep.prepare(out, archive)
    assert receipt["file_count"] == 56
    assert not receipt["wheel_built"] and not receipt["native_engine_compatibility_claimed"]
    helper = prep.support()
    original = json.loads((out / "original-source-manifest.json").read_text())
    patched = json.loads((out / "patched-source-manifest.json").read_text())
    before = {r["path"]: r for r in original}
    after = {r["path"]: r for r in patched}
    assert before.keys() == after.keys()
    assert [p for p in before if before[p] != after[p]] == ["CMakeLists.txt"]
    project = tomllib.loads((out / "source/pyproject.toml").read_text())
    assert project["project"]["requires-python"] == lock["unchanged_requires_python"]
    assert hashlib.sha256((out / "source/pyproject.toml").read_bytes()).hexdigest() == lock["unchanged_pyproject_sha256"]
    assert "samples/dave.wav" in before and "samples/dave.pt" in before and "output.wav" in before
    record_property("original_git_tree", lock["source"]["tree"])
    record_property("original_source_blobs", count)
    record_property("unchanged_source_files", 55)
    record_property("python_requirement_unchanged", lock["unchanged_requires_python"])


@pytest.mark.parametrize("path", ["pyproject.toml", "samples/dave.wav", "unreviewed.py"])
def test_source_verification_rejects_changed_metadata_assets_or_added_code(exact_inputs, tmp_path, path):
    copied = tmp_path / "inputs"
    shutil.copytree(exact_inputs, copied)
    target = copied / "source" / path
    target.write_bytes((target.read_bytes() if target.exists() else b"") + b"\nchanged\n")
    with pytest.raises(RuntimeError):
        prep.verify_inputs(copied)


def test_real_cmake_retains_default_pin_and_uses_local_source_without_git(exact_inputs, tmp_path):
    if not shutil.which("cmake") or not shutil.which("ninja"):
        pytest.skip("Real CMake and Ninja are required for the source acquisition regression")
    checker = module("check_neutts_engine_cmake.py", "_engine_cmake_test")
    receipt = checker.check(exact_inputs, tmp_path / "cmake-evidence")
    assert receipt["status"] == "passed"
    assert len(receipt["cases"]) == 5
    assert all(case["status"] == "passed" for case in receipt["cases"])
    assert not receipt["native_compilation_performed"] and not receipt["native_engine_compatibility_claimed"]
    offline = next(case for case in receipt["cases"] if case["case"] == "patched-offline")
    assert offline["git_clone_scripts"] == 0
    assert offline["repository"] == offline["revision"] == ""
    assert offline["acquisition_exit_code"] == 0
