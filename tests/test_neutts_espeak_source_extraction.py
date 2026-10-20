"""Regression for eSpeak's sole symlink-only source directory."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import types
import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "prepare_neutts_espeak_source.py"
spec = importlib.util.spec_from_file_location("_espeak_extract_current", PATH)
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
ORIGINAL_SHA256 = "6ae148eeefdea830908d14c3db9431678c5b382303f0e5ca6a2f33c41214c25a"


def test_exact_archive_rejects_changed_bytes_before_creating_source(tmp_path):
    lock, _ = prep.load_lock()
    archive = tmp_path / "unverified.tar.gz"
    archive.write_bytes(b"not the pinned archive")
    destination = tmp_path / "source"
    with pytest.raises(RuntimeError, match="archive differs"):
        prep.inspect_archive(archive, lock, destination)
    assert not destination.exists()


def test_exact_source_extracts_the_verified_symlink_only_directory(tmp_path, record_property):
    directory = os.environ.get("HERMES_ESPEAK_SOURCE_INPUTS")
    if not directory:
        pytest.skip("Exact eSpeak source inputs were not supplied")
    lock, _ = prep.load_lock()
    archive = Path(directory) / lock["source"]["artifact"]["filename"]
    if not archive.is_file():
        pytest.fail("Configured exact eSpeak source archive is missing")
    original_source = PATH.read_bytes().replace(
        b"        path.parent.mkdir(parents=True, exist_ok=True)\n", b"", 1)
    assert hashlib.sha256(original_source).hexdigest() == ORIGINAL_SHA256
    original = types.ModuleType("_espeak_extract_original")
    original.__file__ = str(PATH)
    exec(compile(original_source, str(PATH), "exec"), original.__dict__)
    baseline = tmp_path / "original-extraction"
    with pytest.raises(FileNotFoundError):
        original.inspect_archive(archive, lock, baseline)
    link_pin = lock["source"]["exact_symlink"]
    assert not (baseline / link_pin["path"]).parent.exists()
    destination = tmp_path / "corrected-extraction"
    before, after = prep.inspect_archive(archive, lock, destination)
    link = destination / link_pin["path"]
    assert link.is_symlink()
    assert os.readlink(link) == link_pin["target"]
    # Windows can store the exact POSIX link text but cannot follow its forward
    # slashes through NTFS. Resolve that literal target as a host Path here;
    # real link following remains required on the Linux/Android build host.
    target = (link.parent / os.readlink(link)).resolve(strict=True)
    if os.name != "nt":
        assert link.resolve(strict=True) == target
        assert link.read_bytes() == target.read_bytes()
    assert target.is_relative_to(destination.resolve())
    assert target.is_file()
    assert {p.name for p in link.parent.iterdir()} == {"speak_lib.h"}
    observed = {p.relative_to(destination).as_posix() for p in destination.rglob("*")
                if p.is_file() or p.is_symlink()}
    assert observed == {r["path"] for r in after}
    for row in after:
        path = destination / row["path"]
        data = os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
        assert len(data) == row["size"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
    assert len(before) == len(after) == 2606
    assert sum(r["mode"] == "120000" for r in after) == 1
    record_property("all_source_entries_verified", len(after))
    record_property("regular_source_files", len(after) - 1)
    record_property("symlinks", 1)
    record_property("exact_link_bytes", len(os.readlink(link).encode("utf-8")))
    record_property("symlink_target_contained", True)
    record_property("native_posix_symlink_follow_checked", os.name != "nt")
    record_property("baseline_failure", "FileNotFoundError: missing symlink-only parent directory")
