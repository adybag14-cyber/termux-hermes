#!/usr/bin/env python3
"""Append a relocatable SHA-256 entry for an artifact beside SHA256SUMS."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


class ChecksumError(RuntimeError):
    """Raised when a checksum entry would not be relocatable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_relative_checksum(checksum_file: Path, artifact: Path) -> str:
    checksum_file = checksum_file.resolve()
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise ChecksumError(f"artifact does not exist: {artifact}")
    if checksum_file.parent != artifact.parent:
        raise ChecksumError("artifact must be beside SHA256SUMS so the entry is relocatable")
    entry = f"{sha256_file(artifact)}  {artifact.name}"
    with checksum_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry + "\n")
    return entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("checksum_file", type=Path)
    parser.add_argument("artifact", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    append_relative_checksum(args.checksum_file, args.artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())