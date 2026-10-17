#!/usr/bin/env python3
"""Extract nine exact Phonemizer input wheels and the original 100-wheel catalog.

The caller must supply the .deb size and SHA-256 from the existing frozen
candidate fetch receipt. Only reviewed regular members are written; no Debian
package installation, whole-tree extraction, or wheel metadata change occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile

PREPARER_SHA256 = "b6a358f87fb675f00a9e125b821d94ae81d9341cb9b4ab9fe2953ea1697318eb"
PAYLOAD = "data/data/com.termux/files/usr/lib/hermes-agent/"
MAX_DEB_BYTES = 400 * 1024 * 1024


class ExtractError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ExtractError(message)


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def helper():
    path = Path(__file__).resolve().with_name("prepare_phonemizer_runtime.py")
    require(sha_file(path) == PREPARER_SHA256, "Reviewed preparer changed")
    spec = importlib.util.spec_from_file_location("_phonemizer_extraction_verifier", path)
    require(spec is not None and spec.loader is not None, "Cannot load wheel verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MemberStream:
    def __init__(self, stream, size):
        self.stream = stream
        self.remaining = size

    def read(self, size=-1):
        size = self.remaining if size < 0 else min(size, self.remaining)
        raw = self.stream.read(size)
        require(len(raw) == size, "Truncated ar member data")
        self.remaining -= len(raw)
        return raw


def extract(deb, expected_bytes, expected_sha256, lock_path, output):
    prep = helper()
    lock, _ = prep.load_lock(lock_path)
    require(type(expected_bytes) is int and 0 < expected_bytes <= MAX_DEB_BYTES
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256), "Invalid frozen .deb identity")
    require(stat.S_ISREG(deb.lstat().st_mode) and deb.stat().st_size == expected_bytes
            and sha_file(deb) == expected_sha256, "Fetched .deb differs from exact frozen identity")
    require(not os.path.lexists(output) and output.parent.is_dir(), "Fresh output is required")
    require(not any(p.is_symlink() for p in (output.parent, *output.parent.parents)),
            "Output parent traverses a symlink")
    packages = [p for p in lock["packages"] if p["origin"]["kind"] == "main_catalog"]
    require(len(packages) == 9, "Unexpected selected main wheel count")
    wanted = {PAYLOAD + p["origin"]["catalog_record"]["file"]: p for p in packages}
    catalog_name = PAYLOAD + "bundled-wheels.json"
    selected = {}
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".staging-", dir=output.parent))
    try:
        with deb.open("rb") as stream:
            require(stream.read(8) == b"!<arch>\n", "Invalid .deb ar header")
            data_count = 0
            names = set()
            while stream.tell() < expected_bytes:
                header = stream.read(60)
                require(len(header) == 60 and header[58:60] == b"\x60\n", "Invalid ar member")
                size = int(header[48:58])
                name = header[:16].decode("ascii").strip().rstrip("/")
                require(name not in names and 0 <= size <= expected_bytes - stream.tell(),
                        "Duplicate or oversized ar member")
                names.add(name)
                end = stream.tell() + size + size % 2
                if name.startswith("data.tar."):
                    data_count += 1
                    seen = set()
                    with tarfile.open(fileobj=MemberStream(stream, size), mode="r|*") as archive:
                        for item in archive:
                            relative = item.name.removeprefix("./")
                            if relative in ("", "."):
                                require(item.isdir(), "Invalid root tar entry")
                                continue
                            plain = relative.rstrip("/")
                            path = PurePosixPath(plain)
                            require(str(path) == plain and not path.is_absolute()
                                    and ".." not in path.parts and "\\" not in plain,
                                    "Unsafe .deb tar path")
                            require(plain not in seen and len(seen) < 100_000,
                                    "Duplicate or excessive .deb tar inventory")
                            seen.add(plain)
                            if plain != catalog_name and plain not in wanted:
                                continue
                            require(item.isfile() and plain not in selected, "Selected payload must be unique regular files")
                            limit = lock["main_catalog"]["bytes"] if plain == catalog_name else wanted[plain]["artifact"]["bytes"]
                            require(item.size == limit, "Selected payload size differs")
                            raw = archive.extractfile(item).read()
                            require(len(raw) == limit, "Truncated selected payload")
                            selected[plain] = raw
                stream.seek(end)
            require(stream.tell() == expected_bytes and data_count == 1, "Unexpected .deb member structure")
        require(set(selected) == set(wanted) | {catalog_name}, "Selected main inputs are missing")
        (staging / "wheels").mkdir()
        prep.write_new(staging / "main-bundled-wheels.json", selected[catalog_name])
        prep.verify_catalog(staging / "main-bundled-wheels.json", lock)
        facts = []
        for name, package in wanted.items():
            path = staging / "wheels" / package["artifact"]["filename"]
            prep.write_new(path, selected[name])
            facts.append(prep.verify_wheel(path, package))
        receipt = {
            "schema_version": 1, "status": "verified-selected-inputs",
            "scope": "Nine original catalog wheels and unchanged complete 100-wheel catalog only.",
            "source_deb": {"path": str(deb), "bytes": expected_bytes, "sha256": expected_sha256},
            "lock_sha256": prep.LOCK_SHA256, "main_catalog": lock["main_catalog"],
            "wheels": facts, "installed": False, "whole_payload_extracted": False,
        }
        prep.write_new(staging / "PHONEMIZER-MAIN-INPUTS.json",
                       (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        staging.chmod(0o755)
        (staging / "wheels").chmod(0o755)
        require(not os.path.lexists(output), "Output appeared during verification")
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--deb-bytes", type=int, required=True)
    parser.add_argument("--deb-sha256", required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = extract(args.deb, args.deb_bytes, args.deb_sha256, args.lock, args.out)
    print(json.dumps({"status": receipt["status"], "wheels": 9, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
