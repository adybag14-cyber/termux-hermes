#!/usr/bin/env python3
"""Prepare one exact TorchAO wheel for an unpublished native CPU experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import urllib.request
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_NAME = "neutts_torchao_component_lock.json"
LOCK_SHA256 = "8c3303018c326f63540c59855df19d7fc3cef139040c90d64b4e7f4cbc264c22"
RECEIPT_NAME = "TORCHAO-PREPARED-INPUTS.json"


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected a regular owned file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, limit=1_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            "Missing, nonregular or oversized JSON input")
    return json.loads(path.read_bytes())


def save_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def load_lock(path=None):
    path = path or SCRIPT_DIR / LOCK_NAME
    require(sha(path) == LOCK_SHA256, "Frozen TorchAO component lock changed")
    return read_json(path)


def helper(name, lock):
    path = SCRIPT_DIR / name
    require(sha(path) == lock["foundation"]["helpers"][name],
            "Reviewed component helper changed: " + name)
    spec = importlib.util.spec_from_file_location("_torchao_" + path.stem, path)
    require(spec is not None and spec.loader is not None, "Cannot load reviewed helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_wheel(path, lock):
    core = helper("prepare_neutts_core_python.py", lock)
    proof = core.verify_wheel(path, lock["package"])
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            require(".data/" not in item.filename
                    and not item.filename.endswith((".pyc", ".pth")),
                    "Unexpected installation scheme or executable import hook")
            require(not archive.read(item).startswith(b"\x7fELF"),
                    "Pure TorchAO experiment cannot contain an ELF payload")
        for source in lock["source_members"]:
            raw = archive.read(source["path"])
            require(len(raw) == source["bytes"]
                    and hashlib.sha256(raw).hexdigest() == source["sha256"],
                    "Reviewed TorchAO source member changed")
    return proof


def verify_inputs(inputs):
    lock = load_lock(inputs / LOCK_NAME)
    expected = {LOCK_NAME, RECEIPT_NAME, lock["package"]["artifact"]["filename"]}
    require(inputs.is_dir() and not inputs.is_symlink()
            and {p.name for p in inputs.iterdir()} == expected,
            "Prepared directory must contain exactly the one wheel, lock and receipt")
    wheel = inputs / lock["package"]["artifact"]["filename"]
    proof = verify_wheel(wheel, lock)
    receipt = read_json(inputs / RECEIPT_NAME)
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "verified-inputs"
            and receipt.get("lock_sha256") == LOCK_SHA256
            and receipt.get("wheel") == proof
            and receipt.get("source_members") == lock["source_members"]
            and receipt.get("installed") is False
            and receipt.get("model_downloaded") is False
            and receipt.get("release_output") is False,
            "Prepared input receipt differs from its verified wheel")
    return lock, wheel, proof


def prepare(out, wheel=None):
    lock = load_lock()
    require(not out.exists() and not out.is_symlink(), "Use a new input directory")
    if wheel is not None:
        verify_wheel(wheel, lock)
    out.mkdir(parents=True)
    destination = out / lock["package"]["artifact"]["filename"]
    if wheel is None:
        core = helper("prepare_neutts_core_python.py", lock)
        opener = urllib.request.build_opener(core.NoRedirect())
        core.download_file(lock["package"]["artifact"], destination, opener,
                           time.monotonic() + 120)
    else:
        with destination.open("xb") as stream:
            stream.write(wheel.read_bytes())
    proof = verify_wheel(destination, lock)
    with (out / LOCK_NAME).open("xb") as stream:
        stream.write((SCRIPT_DIR / LOCK_NAME).read_bytes())
    receipt = {"schema_version": 1, "status": "verified-inputs",
               "captured_utc": datetime.now(timezone.utc).isoformat(),
               "lock_sha256": LOCK_SHA256, "wheel": proof,
               "source_members": lock["source_members"],
               "installed": False, "model_downloaded": False, "release_output": False}
    save_new(out / RECEIPT_NAME, receipt)
    verify_inputs(out)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, help="Optional already verified local exact wheel")
    args = parser.parse_args(argv)
    receipt = prepare(args.out, args.wheel)
    print(json.dumps({"status": receipt["status"], "lock_sha256": LOCK_SHA256,
                      "wheel_sha256": receipt["wheel"]["artifact"]["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
