#!/usr/bin/env python3
"""Prepare the exact 25-distribution Tokenizers/Hub/fsspec subset without installing it."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_NAME = "neutts_tokenizers_runtime_lock.json"
LOCK_SHA256 = "d4aa5a4e30f4a77d04800d8f15dab413457f1ced4b2f4e2369cbde5402692859"
NONRUST_PREPARER_SHA256 = "6540cae859c390bdceed18aac315bf27559425262935d3e015ac99393bddc047"
HANDOFF_SHA256 = "42d47b3fe4f8858d94d69a5216db1253e75d05437c9ffad42651369130252768"
GRAPH_SHA256 = "d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68"
RECEIPT_NAME = "TOKENIZERS-PREPARED-INPUTS.json"
MAX_LOCK_BYTES = 2_000_000


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def helper():
    path = SCRIPT_DIR / "prepare_neutts_nonrust_runtime.py"
    require(sha(path.read_bytes()) == NONRUST_PREPARER_SHA256, "Reviewed wheel verifier changed")
    spec = importlib.util.spec_from_file_location("_tokenizers_wheel_preparer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_new(path, value):
    helper().write_new(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def load_lock(path):
    prep = helper()
    raw = prep.read_regular(path, MAX_LOCK_BYTES)
    require(sha(raw) == LOCK_SHA256, "Reviewed Tokenizers runtime lock changed")
    lock = json.loads(raw)
    require(lock["schema_version"] == 1 and lock["status"] == "reviewed-native-handoffs"
            and lock["node_count"] == 25 and lock["edge_count"] == 29,
            "Unreviewed runtime selection")
    packages = lock["packages"]
    names = [p["name"] for p in packages]
    require(len(names) == 25 and len(set(names)) == 25 and sorted(names) == lock["names"],
            "Duplicate, missing or extra original distribution")
    require(lock["handoff"]["sha256"] == HANDOFF_SHA256
            and lock["frozen_graph"]["sha256"] == GRAPH_SHA256,
            "Original graph/handoff identity changed")
    require(lock["roots"] == ["fsspec", "safetensors", "tokenizers"]
            and {p["name"]: p["active_extras"] for p in packages if p["active_extras"]}
            == {"fsspec": ["http"]}, "Selected original roots/extras changed")
    require(len(lock["edges"]) == 29 and all(e["from"] in names and e["to"] in names
                                            for e in lock["edges"]),
            "Unreviewed dependency edge set")
    require({p["name"] for p in lock["apt_archives"]} == {"libyaml", "libgmp"}
            and lock["apt_install_names"] == ["libyaml"], "Additional APT ownership/install scope changed")
    return lock, raw


def repo_input(root, relative):
    prep = helper()
    relative = prep.safe_relative(relative)
    require(relative.startswith("audit/"), "Retained input is outside the reviewed audit")
    path = Path(root).joinpath(*relative.split("/"))
    require(path.resolve().is_relative_to(Path(root).resolve())
            and not any(p.is_symlink() for p in (path, *path.parents)),
            "Retained input traverses a symlink")
    return path


def verify_apt_archive(path, pin):
    prep = helper()
    raw = prep.read_regular(path, pin["bytes"])
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Original APT archive changed")
    parts = dict(prep.ar_parts(raw))
    controls = [v for k, v in parts.items() if k.startswith("control.tar.")]
    payloads = [v for k, v in parts.items() if k.startswith("data.tar.")]
    require(len(parts) == 3 and parts.get("debian-binary") == b"2.0\n"
            and len(controls) == len(payloads) == 1, "Unexpected Debian archive structure")
    total, seen, control_raw = 0, set(), None
    with tarfile.open(fileobj=io.BytesIO(controls[0]), mode="r|*") as archive:
        for item in archive:
            name = item.name.removeprefix("./").rstrip("/")
            if item.name in (".", "./"):
                require(item.isdir() and "." not in seen, "Invalid control root")
                seen.add(".")
                continue
            prep.safe_relative(name)
            require(name not in seen, "Duplicate APT control member")
            seen.add(name)
            require(item.isdir() or item.isfile(), "APT control contains a link or special entry")
            if item.isdir():
                continue
            total += item.size
            require(0 <= item.size <= 100_000 and total <= 1_000_000,
                    "APT control metadata exceeds bound")
            body = archive.extractfile(item).read()
            require(len(body) == item.size, "Truncated APT control member")
            if name == "control":
                control_raw = body
    require(control_raw is not None, "APT control record is absent")
    control = BytesParser(policy=compat32).parsebytes(control_raw)
    for field, key in (("Package", "name"), ("Version", "version"), ("Architecture", "architecture"),
                       ("Depends", "depends"), ("Pre-Depends", "pre_depends")):
        require(len(control.get_all(field, [])) <= 1 and control.get(field, "") == pin.get(key, ""),
                "Original APT control field changed: " + field)
    return {"name": pin["name"], "version": pin["version"], "bytes": len(raw),
            "sha256": sha(raw), "control_sha256": sha(control_raw)}


def verify_snapshot(root, lock):
    prep = helper()
    directory = Path(root) / "audit/neutts-runtime-index-20261017"
    for pin in lock["snapshot"]:
        raw = prep.read_regular(directory / pin["filename"], pin["bytes"])
        require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Frozen index bytes differ")
    raw = gzip.decompress((directory / "Packages.gz").read_bytes())
    require(len(raw) == 1_867_286
            and sha(raw) == "95cf6e3b7cf347a81aef44e45199724b7a6cd21c29be7611cc1ac5ebaf2640e1",
            "Original uncompressed package index differs")
    rows = {}
    for block in raw.split(b"\n\n"):
        if not block.strip():
            continue
        record = BytesParser(policy=compat32).parsebytes(block)
        key = (record.get("Package"), record.get("Version"), record.get("Architecture"))
        if key in {(p["name"], p["version"], p["architecture"]) for p in lock["apt_archives"]}:
            require(key not in rows, "Ambiguous original selected archive")
            rows[key] = record
    for pin in lock["apt_archives"]:
        record = rows.get((pin["name"], pin["version"], pin["architecture"]))
        require(record is not None and record["Filename"] == pin["filename"]
                and record["SHA256"] == pin["sha256"] and int(record["Size"]) == pin["bytes"],
                "Additional original archive is not in the frozen index")
    return {"index_archive_count": len(rows), "signature": "Native APT must authenticate this index independently"}


def verify_inputs(directory):
    prep = helper()
    directory = Path(directory)
    lock, raw = load_lock(directory / LOCK_NAME)
    require(not directory.is_symlink() and directory.is_dir(), "Prepared directory is not regular")
    expected = {LOCK_NAME, RECEIPT_NAME}
    wheels, archives = [], []
    for package in lock["packages"]:
        name = "wheels/" + package["artifact"]["filename"]
        expected.add(name)
        wheels.append(prep.verify_wheel(directory / name, package))
    for pin in lock["apt_archives"]:
        name = "apt-archives/" + pin["name"] + "_" + pin["version"] + "_" + pin["architecture"] + ".deb"
        require(":" not in name, "Additional archive needs an explicitly reviewed epoch filename")
        expected.add(name)
        archives.append(verify_apt_archive(directory / name, pin))
    actual = set()
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Prepared input contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
        else:
            require(path.is_dir(), "Prepared input contains a special file")
    require(actual == expected, "Prepared input has missing or unowned files")
    receipt = json.loads(prep.read_regular(directory / RECEIPT_NAME, MAX_LOCK_BYTES))
    require(receipt["lock_sha256"] == sha(raw) and receipt["wheels"] == wheels
            and receipt["apt_archives"] == archives and receipt["node_count"] == 25
            and receipt["edge_count"] == 29 and not receipt["installed"],
            "Prepared input receipt differs from actual originals")
    return lock, receipt


def prepare(root, output):
    root = Path(root)
    prep = helper()
    lock, raw_lock = load_lock(root / "scripts" / LOCK_NAME)
    for pin in (lock["handoff"], lock["frozen_graph"]):
        path = root.joinpath(*prep.safe_relative(pin["path"]).split("/"))
        raw = prep.read_regular(path, pin["bytes"])
        require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Original design input differs")
    verify_snapshot(root, lock)
    output = Path(os.path.abspath(output))
    require(not os.path.lexists(output) and output.parent.is_dir()
            and not any(p.is_symlink() for p in (output.parent, *output.parent.parents)),
            "Use a fresh output under a real existing parent")
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".staging-", dir=output.parent))
    try:
        wheels, archives = [], []
        for package in lock["packages"]:
            source = repo_input(root, package["input_path"])
            wheels.append(prep.verify_wheel(source, package))
            prep.write_new(staging / "wheels" / package["artifact"]["filename"], source.read_bytes())
        for pin in lock["apt_archives"]:
            source = repo_input(root, pin["input_path"])
            archives.append(verify_apt_archive(source, pin))
            filename = pin["name"] + "_" + pin["version"] + "_" + pin["architecture"] + ".deb"
            prep.write_new(staging / "apt-archives" / filename, source.read_bytes())
        prep.write_new(staging / LOCK_NAME, raw_lock)
        receipt = {"schema_version": 1, "status": "verified-inputs", "lock_sha256": sha(raw_lock),
                   "node_count": 25, "edge_count": 29, "wheels": wheels, "apt_archives": archives,
                   "installed": False, "models_downloaded": False, "engine_admitted": False,
                   "release_output": False}
        save_new(staging / RECEIPT_NAME, receipt)
        verify_inputs(staging)
        require(not os.path.lexists(output), "Output appeared during preparation")
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=SCRIPT_DIR.parent)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    result = verify_inputs(args.verify)[1] if args.verify else prepare(args.repo, args.out)
    print(json.dumps({"status": result["status"], "node_count": result["node_count"],
                      "edge_count": result["edge_count"], "installed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
