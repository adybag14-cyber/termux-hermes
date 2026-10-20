#!/usr/bin/env python3
"""Freeze the reviewed Tiktoken lock and its complete original base runtime.

This never invokes a compiler, resolves a new Cargo lock, changes original source
or metadata, or installs the engine. Native execution belongs to the separate
component probe.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import time

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY = SCRIPT_DIR.parent
LOCK_FILENAME = "neutts_tiktoken_lock.json"
LOCK_SHA256 = "6d7e2d5f10f35547eea573ec1d38cbfb88ed2f09ff58fe86cb56f1be134e7f21"
RUST_PREPARER_SHA256 = "db8ce00daaece15f69b4f7b1de415accd207f13e256b2097d4efcb2d0894c428"
RUNTIME_NAMES = {"tiktoken", "regex", "requests", "certifi", "charset-normalizer", "idna", "urllib3"}
DIRECTORIES = {"archives", "sources", "wheels", "crates", "vendor", "snapshot", "apt-archives"}


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def helper():
    path = SCRIPT_DIR / "prepare_neutts_rust_sources.py"
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == RUST_PREPARER_SHA256,
            "Original Rust archive verifier changed; review it explicitly")
    spec = importlib.util.spec_from_file_location("_tiktoken_original_input_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lock(path=None):
    prep = helper()
    raw = prep.read_regular(path or SCRIPT_DIR / LOCK_FILENAME, 1_000_000)
    require(prep.sha(raw) == LOCK_SHA256, "Tiktoken standalone lock changed")
    lock = json.loads(raw)
    references = {}
    for name, pin in lock["references"].items():
        prep.safe_relative(pin["path"])
        references[name] = prep.verified_bytes(REPOSITORY / pin["path"], pin)
    rust, _ = prep.load_lock(SCRIPT_DIR / "neutts_rust_sources_lock.json")
    capture = json.loads(references["capture"])
    review = json.loads(references["root_review"])
    require(review.get("approved_for_subsequent_separately_pinned_build") is True
            and lock["reviewed_capture_commit"] == "c1ea01d2f06b77dfab14e2f50daf7d72b5ad18d8",
            "The captured lock lacks the saved root approval")
    require(lock["source"] == capture["original_source"]
            == next(s for s in rust["sources"] if s["name"] == "tiktoken")
            and lock["registry"] == capture["registry"]
            and lock["target_filtered_packages"] == capture["target_filtered_packages"],
            "Original reviewed Tiktoken source, crates or graph changed")
    require(lock["regex_source"] == next(s for s in json.loads(references["regex_source_lock"])["sources"]
                                        if s["name"] == "regex"),
            "The previously reviewed Regex source changed")
    require(lock["python_build_packages"] == rust["python_build_packages"]
            and lock["target"] == rust["target"]
            and set(lock["runtime_names"]) == RUNTIME_NAMES
            and len(lock["runtime_names"]) == 7 and len(lock["runtime_edges"]) == 6
            and len(lock["registry"]) == 27 and len(lock["target_filtered_packages"]) == 25,
            "Original build or runtime selection changed")
    pin = lock["captured_cargo_lock"]
    require(len(references["cargo_lock"]) == pin["bytes"]
            and prep.sha(references["cargo_lock"]) == pin["sha256"],
            "Approved captured Cargo.lock changed")
    for name in ("tiktoken", "regex"):
        source = source_record(lock, name)
        generated = lock["allowed_generated_source_manifests"][name]
        original = next(p for p in source["files"] if p["path"] == generated["path"])
        require(original["sha256"] == generated["original_sha256"]
                and original["bytes"] == generated["original_bytes"],
                "Generated manifest is not bound to the original source")
        prep.safe_relative(generated["replay_evidence"])
        prep.verified_bytes(REPOSITORY / generated["replay_evidence"], generated)
    return lock, rust, raw


def source_record(lock, name):
    if name == "tiktoken":
        return lock["source"]
    require(name == "regex", "Unreviewed source component")
    value = lock["regex_source"]
    require(all(row["mode"] == "100644" for row in value["files"]),
            "Unreviewed Regex source mode")
    return {**value, "backend_path": [], "native_extension_prefix": "regex/",
            "files": [{k: row[k] for k in ("path", "bytes", "sha256")} | {"executable": False}
                      for row in value["files"]]}


def verify_source_tree(root, name, lock, prep):
    source = source_record(lock, name)
    result = prep.verify_source(root, source, allow_new_lock=name == "tiktoken")
    if name == "tiktoken":
        prep.verified_bytes(root / "Cargo.lock", lock["captured_cargo_lock"])
        result["approved_additional_cargo_lock_sha256"] = lock["captured_cargo_lock"]["sha256"]
    return result


def verify_build_tree(root, name, lock, prep):
    """Accept only the measured Setuptools SOURCES.txt working-copy rewrite."""
    source = source_record(lock, name)
    original = {row["path"]: row for row in source["files"]}
    permitted = lock["allowed_generated_source_manifests"][name]
    expected = dict(original)
    actual = prep.tree_files(root)
    by_name = {row["path"]: row for row in actual}
    require(permitted["path"] in original and permitted["path"] in by_name,
            "Missing original generated source manifest")
    rewritten = []
    manifest = by_name[permitted["path"]]
    if manifest != original[permitted["path"]]:
        expected[permitted["path"]] = {
            "path": permitted["path"], "bytes": permitted["bytes"],
            "sha256": permitted["sha256"], "executable": False}
        require(manifest == expected[permitted["path"]],
                "Unreviewed change to generated Setuptools source manifest")
        rewritten.append({"path": permitted["path"], "before_sha256": permitted["original_sha256"],
                          "after_sha256": permitted["sha256"], "bytes": permitted["bytes"],
                          "reason": permitted["reason"]})
    selected = [row for row in actual if row["path"] in original]
    prep.same_files(selected, list(expected.values()))
    if name == "tiktoken":
        prep.verified_bytes(root / "Cargo.lock", lock["captured_cargo_lock"])
    return {"original_files_byte_identical": len(original) - len(rewritten),
            "allowed_generated_source_manifests": rewritten,
            "original_source_code_backend_and_dependency_metadata_unchanged": True,
            "derived_files": [row for row in actual if row["path"] not in original]}


def exact_children(path, expected):
    require(path.is_dir() and not path.is_symlink(), "Missing or linked owned input directory")
    children = list(path.iterdir())
    require({p.name for p in children} == set(expected)
            and not any(p.is_symlink() for p in children), "Unexpected or linked input selection")


def verify_inputs(directory):
    prep = helper()
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Invalid prepared input root")
    lock, rust, raw = load_lock(directory / LOCK_FILENAME)
    receipt = json.loads(prep.read_regular(directory / "TIKTOKEN-PREPARED-INPUTS.json", 2_000_000))
    require(receipt.get("status") == "verified-inputs" and receipt.get("lock_sha256") == prep.sha(raw)
            and receipt.get("cargo_executed") is False and receipt.get("source_backend_executed") is False
            and all(receipt.get(key) is False for key in ("new_cargo_resolution", "original_sources_modified",
                "original_metadata_modified", "engine_installed", "model_downloaded", "release_output")),
            "Invalid input preparation receipt")
    exact_children(directory, DIRECTORIES | {LOCK_FILENAME, "TIKTOKEN-PREPARED-INPUTS.json"})
    sources = [source_record(lock, name) for name in ("tiktoken", "regex")]
    exact_children(directory / "archives", [s["artifact"]["filename"] for s in sources])
    exact_children(directory / "sources", [s["archive_root"] for s in sources])
    for source in sources:
        source_raw = prep.verified_bytes(directory / "archives" / source["artifact"]["filename"], source["artifact"])
        prep.same_files(prep.archive_files(source_raw, source["archive_root"]), source["files"])
        verify_source_tree(directory / "sources" / source["archive_root"], source["name"], lock, prep)
    packages = lock["python_build_packages"] + lock["runtime_wheels"]
    exact_children(directory / "wheels", [p["artifact"]["filename"] for p in packages])
    for package in packages:
        prep.verify_wheel(directory / "wheels" / package["artifact"]["filename"], package)
    registry = lock["registry"]
    exact_children(directory / "crates", [p["filename"] for p in registry])
    exact_children(directory / "vendor", [p["name"] + "-" + p["version"] for p in registry])
    verified_files = 0
    for pin in registry:
        destination = directory / "vendor" / (pin["name"] + "-" + pin["version"])
        count = prep.verify_crate(directory / "crates" / pin["filename"], pin, destination)
        require(count == pin["files"]
                and prep.sha_file(destination / ".cargo-checksum.json") == pin["checksum_sha256"],
                "Captured original crate inventory changed")
        verified_files += count
    apt_names = prep.apt_archive_names(rust["build_apt"]["packages"])
    exact_children(directory / "apt-archives", apt_names.values())
    require(receipt.get("apt_owned_cache_filenames") == apt_names, "APT cache filename receipt changed")
    for pin in rust["build_apt"]["packages"]:
        prep.verified_bytes(directory / "apt-archives" / apt_names[pin["filename"]], pin)
    exact_children(directory / "snapshot", [p["filename"] for p in rust["build_apt"]["snapshot"]])
    for pin in rust["build_apt"]["snapshot"]:
        prep.verified_bytes(directory / "snapshot" / pin["filename"], pin)
    prep.snapshot_binding(directory / "snapshot", rust["build_apt"]["snapshot"])
    require(verified_files == 1863, "Original frozen crate file census changed")
    return lock, rust, receipt, {"original_registry_archives": 27, "original_registry_files": verified_files,
                                "generated_directory_checksums": 27, "original_source_files": 58,
                                "build_wheels": 5, "runtime_prebuilt_wheels": 5, "apt_archives": 47}


def prepare(out, snapshot, caches=()):
    prep = helper()
    lock, rust, raw = load_lock()
    out = Path(out).absolute()
    snapshot = Path(snapshot).resolve()
    caches = [Path(p).resolve() for p in caches]
    require(not out.exists() and not out.is_symlink(), "Use a fresh input directory")
    for source in [SCRIPT_DIR.resolve(), snapshot, *caches]:
        require(not out.is_relative_to(source) and not source.is_relative_to(out),
                "Output overlaps an input or cache")
    out.mkdir(parents=True)
    for name in sorted(DIRECTORIES):
        (out / name).mkdir()
    prep.write_new(out / LOCK_FILENAME, raw)
    for pin in rust["build_apt"]["snapshot"]:
        prep.write_new(out / "snapshot" / pin["filename"],
                       prep.verified_bytes(snapshot / pin["filename"], pin))
    prep.snapshot_binding(out / "snapshot", rust["build_apt"]["snapshot"])
    sources = [source_record(lock, name) for name in ("tiktoken", "regex")]
    packages = lock["python_build_packages"] + lock["runtime_wheels"]
    apt_names = prep.apt_archive_names(rust["build_apt"]["packages"])
    jobs = [(s["artifact"], out / "archives" / s["artifact"]["filename"]) for s in sources]
    jobs += [(p["artifact"], out / "wheels" / p["artifact"]["filename"]) for p in packages]
    jobs += [(p, out / "crates" / p["filename"]) for p in lock["registry"]]
    jobs += [({**p, "filename": apt_names[p["filename"]]}, out / "apt-archives" / apt_names[p["filename"]])
             for p in rust["build_apt"]["packages"]]
    deadline = time.monotonic() + 1200
    def acquire(job):
        pin, destination = job
        return {"path": destination.relative_to(out).as_posix(),
                **prep.download(pin, destination, caches, deadline)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloads = list(pool.map(acquire, jobs))
    for source in sources:
        rows = prep.archive_files(prep.verified_bytes(out / "archives" / source["artifact"]["filename"],
                                                      source["artifact"]), source["archive_root"],
                                  output=out / "sources" / source["archive_root"])
        prep.same_files(rows, source["files"])
    captured = lock["references"]["cargo_lock"]
    prep.write_new(out / "sources" / lock["source"]["archive_root"] / "Cargo.lock",
                   prep.verified_bytes(REPOSITORY / captured["path"], captured))
    for package in packages:
        prep.verify_wheel(out / "wheels" / package["artifact"]["filename"], package)
    for pin in lock["registry"]:
        row = prep.export_crate(out / "crates" / pin["filename"], pin,
                                out / "vendor" / (pin["name"] + "-" + pin["version"]))
        require(len(row["files"]) == pin["files"] and row["checksum_sha256"] == pin["checksum_sha256"],
                "Original captured crate reconstruction differs")
    receipt = {"schema_version": 1, "status": "verified-inputs",
               "recorded_at": datetime.now(timezone.utc).isoformat(), "lock_sha256": prep.sha(raw),
               "approved_cargo_lock_sha256": lock["captured_cargo_lock"]["sha256"],
               "reviewed_capture_commit": lock["reviewed_capture_commit"],
               "downloads": downloads, "apt_owned_cache_filenames": apt_names,
               "cargo_executed": False, "new_cargo_resolution": False, "source_backend_executed": False,
               "original_sources_modified": False, "original_metadata_modified": False,
               "engine_installed": False, "model_downloaded": False, "release_output": False}
    prep.save_json(out / "TIKTOKEN-PREPARED-INPUTS.json", receipt)
    _, _, _, checks = verify_inputs(out)
    return {"status": receipt["status"], "lock_sha256": prep.sha(raw), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--snapshot", type=Path,
                        default=REPOSITORY / "audit/neutts-runtime-index-20261017")
    parser.add_argument("--cache", type=Path, action="append", default=[])
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        require(args.out is None and not args.cache, "Verification must not acquire or write inputs")
        _, _, _, checks = verify_inputs(args.verify)
        print(json.dumps({"status": "verified-inputs", "checks": checks}, sort_keys=True))
    else:
        require(args.out is not None, "--out or --verify is required")
        print(json.dumps(prepare(args.out, args.snapshot, args.cache), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
