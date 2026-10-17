#!/usr/bin/env python3
"""Stage the frozen nine-wheel dependency closure for the APT scientific probe.

This stdlib-only host tool downloads and verifies artifacts. It does not invoke
pip, install packages, resolve dependencies, or alter the managed Hermes graph.
The explicit --lock input must have the reviewed byte identity below.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

LOCK_SHA256 = "ba927bae7ec87c331e23136ba883da86876ca24044485288d9866649130fab38"
LOCK_FILENAME = "neutts_core_python_lock.json"
RECEIPT_FILENAME = "python-wheelhouse-receipt.json"
EXPECTED_NAMES = (
    "filelock", "typing-extensions", "setuptools", "sympy", "mpmath",
    "networkx", "jinja2", "fsspec", "markupsafe",
)
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 180
READ_TIMEOUT_SECONDS = 20
CHUNK_BYTES = 256 * 1024


class PrepareError(RuntimeError):
    """A frozen input or its downloaded bytes failed verification."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The exact immutable files.pythonhosted.org endpoints return 200.
        # A redirect is neither required nor an accepted replacement source.
        return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lines_sha256(values: list[str]) -> str:
    return sha256(("\n".join(values) + ("\n" if values else "")).encode("utf-8"))


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def read_regular(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise PrepareError("Input must be a regular file, not a symlink")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise PrepareError("Input exceeds its bounded size")
    return data


def validate_artifact(artifact: dict) -> None:
    filename = artifact["filename"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", filename):
        raise PrepareError("Unsafe wheel filename")
    url_pattern = (
        r"https://files\.pythonhosted\.org/packages/"
        r"[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/" + re.escape(filename)
    )
    if not re.fullmatch(url_pattern, artifact["url"]):
        raise PrepareError("Wheel URL is not its exact official immutable endpoint")
    if (type(artifact["bytes"]) is not int
            or not 0 < artifact["bytes"] <= MAX_ARCHIVE_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])):
        raise PrepareError("Invalid wheel size or digest")


def load_lock(path: Path) -> tuple[dict, bytes]:
    raw = read_regular(path, 64 * 1024)
    if sha256(raw) != LOCK_SHA256:
        raise PrepareError("Lock bytes differ from the reviewed frozen identity")
    lock = json.loads(raw)
    if (lock["schema_version"] != 1 or lock["selected_extras"] != []
            or tuple(p["name"] for p in lock["packages"]) != EXPECTED_NAMES
            or lock["target"] != {
                "python": "3.14.6", "implementation": "cpython",
                "abi": "cp314", "platform": "android_24_arm64_v8a",
            }):
        raise PrepareError("Unexpected frozen lock scope")
    filenames = set()
    for package in lock["packages"]:
        validate_artifact(package["artifact"])
        filename = package["artifact"]["filename"]
        if filename in filenames:
            raise PrepareError("Duplicate wheel artifact")
        filenames.add(filename)
    if sum(p["artifact"]["bytes"] for p in lock["packages"]) > MAX_TOTAL_BYTES:
        raise PrepareError("Wheel set exceeds its bounded size")
    return lock, raw


def download_file(artifact: dict, destination: Path, opener, deadline: float) -> None:
    validate_artifact(artifact)
    request = urllib.request.Request(
        artifact["url"],
        headers={"User-Agent": "termux-hermes-native-probe/1", "Accept-Encoding": "identity"},
    )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PrepareError("Wheel download deadline exceeded")
    try:
        with opener.open(request, timeout=min(READ_TIMEOUT_SECONDS, remaining)) as response:
            if response.status != 200 or response.geturl() != artifact["url"]:
                raise PrepareError("Wheel endpoint did not return the exact requested artifact")
            length = response.headers.get("Content-Length")
            if length is not None and length != str(artifact["bytes"]):
                raise PrepareError("Wheel HTTP size differs from the frozen size")
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise PrepareError("Unexpected HTTP content encoding")
            digest = hashlib.sha256()
            total = 0
            with destination.open("xb") as output:
                while True:
                    if time.monotonic() > deadline:
                        raise PrepareError("Wheel download deadline exceeded")
                    # read1 returns after one underlying read; a slow trickle
                    # cannot hide the wall deadline inside read(CHUNK_BYTES).
                    chunk = response.read1(min(CHUNK_BYTES, artifact["bytes"] - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > artifact["bytes"]:
                        raise PrepareError("Wheel exceeded its frozen size")
                    output.write(chunk)
                    digest.update(chunk)
            if total != artifact["bytes"] or digest.hexdigest() != artifact["sha256"]:
                raise PrepareError("Downloaded wheel size or SHA-256 mismatch")
    except urllib.error.HTTPError as exc:
        raise PrepareError(f"Wheel download failed with HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PrepareError("Wheel download failed or timed out") from None


def safe_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    plain = name[:-1] if info.is_dir() else name
    parts = PurePosixPath(plain).parts
    if (info.orig_filename != name or not plain or len(name) > 1024
            or "\\" in name or ":" in name
            or any(ord(char) < 32 for char in name) or name.startswith("/")
            or any(part in (".", "..") for part in parts)
            or str(PurePosixPath(plain)) != plain):
        raise PrepareError("Unsafe path in wheel")
    kind = stat.S_IFMT(info.external_attr >> 16)
    if info.is_dir():
        if info.file_size != 0 or kind not in (0, stat.S_IFDIR):
            raise PrepareError("Invalid directory entry in wheel")
    elif kind not in (0, stat.S_IFREG):
        raise PrepareError("Symlink or nonregular entry in wheel")
    if info.flag_bits & 1:
        raise PrepareError("Encrypted wheel members are not accepted")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise PrepareError("Unexpected wheel compression")
    if not 0 <= info.file_size <= MAX_MEMBER_BYTES:
        raise PrepareError("Wheel member exceeds its bounded size")


def one_header(message, key: str, *, optional: bool = False) -> str:
    values = message.get_all(key, [])
    if not values and optional:
        return ""
    if len(values) != 1:
        raise PrepareError(f"Missing or duplicate wheel {key} field")
    return values[0]


def verify_wheel(path: Path, package: dict) -> dict:
    artifact, expected = package["artifact"], package["wheel"]
    raw = read_regular(path, artifact["bytes"])
    if len(raw) != artifact["bytes"] or sha256(raw) != artifact["sha256"]:
        raise PrepareError("Wheel size or SHA-256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise PrepareError("Duplicate ZIP member")
            for entry in entries:
                safe_member(entry)
            file_entries = [entry for entry in entries if not entry.is_dir()]
            uncompressed = sum(entry.file_size for entry in entries)
            if (len(entries) != expected["entry_count"]
                    or len(file_entries) != expected["file_count"]
                    or uncompressed != expected["uncompressed_bytes"]
                    or uncompressed > MAX_UNCOMPRESSED_BYTES
                    or max(entry.file_size for entry in entries) != expected["max_member_bytes"]
                    or lines_sha256(sorted(names)) != expected["members_sha256"]):
                raise PrepareError("Wheel member inventory differs from the frozen inventory")

            # No member is extracted. Reading every member verifies its CRC.
            content_hashes = {}
            metadata_bytes = {}
            important = {
                expected["metadata_member"]: expected["metadata_sha256"],
                expected["wheel_member"]: expected["wheel_sha256"],
                expected["record_member"]: expected["record_sha256"],
            }
            sizes = {}
            for entry in file_entries:
                contents = archive.read(entry)
                digest = sha256(contents)
                content_hashes[entry.filename] = digest
                sizes[entry.filename] = len(contents)
                if entry.filename in important:
                    if digest != important[entry.filename]:
                        raise PrepareError("Wheel metadata byte digest mismatch")
                    metadata_bytes[entry.filename] = contents
            if set(metadata_bytes) != set(important):
                raise PrepareError("Missing exact top-level wheel metadata")

            metadata = BytesParser(policy=compat32).parsebytes(
                metadata_bytes[expected["metadata_member"]]
            )
            if (canonical_name(one_header(metadata, "Name")) != package["name"]
                    or one_header(metadata, "Version") != package["version"]
                    or one_header(metadata, "Requires-Python", optional=True)
                    != package["requires_python"]):
                raise PrepareError("Wheel distribution identity or Python requirement mismatch")
            requirements = metadata.get_all("Requires-Dist", [])
            if (len(requirements) != expected["declared_requires_dist_count"]
                    or lines_sha256(requirements) != expected["declared_requires_dist_sha256"]
                    or [value for value in requirements if ";" not in value]
                    != package["base_requires_dist"]):
                raise PrepareError("Wheel declared requirements differ from the frozen metadata")
            wheel = BytesParser(policy=compat32).parsebytes(
                metadata_bytes[expected["wheel_member"]]
            )
            if (one_header(wheel, "Wheel-Version") != "1.0"
                    or wheel.get_all("Tag", []) != expected["tags"]
                    or one_header(wheel, "Root-Is-Purelib")
                    != str(expected["root_is_purelib"]).lower()):
                raise PrepareError("Wheel tags or purelib declaration mismatch")

            rows = list(csv.reader(io.StringIO(
                metadata_bytes[expected["record_member"]].decode("utf-8")
            )))
            if (any(len(row) != 3 for row in rows)
                    or len(rows) != len(content_hashes)
                    or len({row[0] for row in rows}) != len(rows)
                    or {row[0] for row in rows} != set(content_hashes)):
                raise PrepareError("Wheel RECORD does not cover each file exactly once")
            for name, digest, size in rows:
                if name == expected["record_member"]:
                    if digest or size:
                        raise PrepareError("Wheel RECORD self-entry must be unhashed")
                    continue
                actual = base64.urlsafe_b64encode(
                    bytes.fromhex(content_hashes[name])
                ).decode("ascii").rstrip("=")
                if digest != "sha256=" + actual or size != str(sizes[name]):
                    raise PrepareError("Wheel RECORD member digest or size mismatch")

            native = {
                name for name in content_hashes
                if name.endswith((".so", ".pyd", ".dylib", ".dll")) or ".so." in name
            }
            if native != {item["member"] for item in package["native_members"]}:
                raise PrepareError("Unexpected native extension member")
            for item in package["native_members"]:
                if (content_hashes[item["member"]] != item["sha256"]
                        or sizes[item["member"]] != item["bytes"]):
                    raise PrepareError("Native extension digest or size mismatch")
    except (zipfile.BadZipFile, UnicodeError, csv.Error) as exc:
        raise PrepareError("Invalid wheel archive or metadata") from None
    return {
        "name": package["name"], "version": package["version"],
        "artifact": artifact, "wheel": expected,
        "native_members": package["native_members"],
        "checks": {
            "archive_size_sha256": "passed", "safe_exact_member_inventory": "passed",
            "all_member_crcs_and_record_hashes": "passed",
            "metadata_identity_requirements": "passed", "wheel_tags": "passed",
            "native_member_hashes": "passed",
        },
    }


def write_new(path: Path, contents: bytes) -> None:
    with path.open("xb") as output:
        output.write(contents)
    path.chmod(0o644)


def check_file_set(directory: Path, expected: set[str]) -> None:
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != expected:
        raise PrepareError("Unexpected file in staged wheelhouse")
    if any(not stat.S_ISREG(entry.lstat().st_mode) for entry in entries):
        raise PrepareError("Staged wheelhouse contains a symlink or nonregular file")


def prepare(lock_path: Path, output: Path, *, opener=None) -> dict:
    lock, raw_lock = load_lock(lock_path)
    output = Path(os.path.abspath(output))
    if os.path.lexists(output):
        raise PrepareError("Output already exists; a fresh directory is required")
    if not output.parent.is_dir():
        raise PrepareError("Output parent must already exist")
    if any(parent.is_symlink() for parent in (output.parent, *output.parent.parents)):
        raise PrepareError("Output parent must not traverse a symlink")
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
        )
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".staging-", dir=output.parent))
    deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
    try:
        verified = []
        for package in lock["packages"]:
            path = staging / package["artifact"]["filename"]
            download_file(package["artifact"], path, opener, deadline)
            verified.append(verify_wheel(path, package))
            path.chmod(0o644)
        requirements = "".join(
            f"{package['name']}=={package['version']} --hash=sha256:{package['artifact']['sha256']}\n"
            for package in lock["packages"]
        ).encode("utf-8")
        write_new(staging / "requirements.txt", requirements)
        write_new(staging / LOCK_FILENAME, raw_lock)
        receipt = {
            "schema_version": 1,
            "scope": "Verified wheel files only; no installation or native execution.",
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "target": lock["target"], "selected_extras": [],
            "lock": {"filename": LOCK_FILENAME, "bytes": len(raw_lock), "sha256": sha256(raw_lock)},
            "requirements": {
                "filename": "requirements.txt", "bytes": len(requirements),
                "sha256": sha256(requirements),
            },
            "packages": verified,
        }
        write_new(
            staging / RECEIPT_FILENAME,
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        check_file_set(staging, {
            *(p["artifact"]["filename"] for p in lock["packages"]),
            "requirements.txt", LOCK_FILENAME, RECEIPT_FILENAME,
        })
        if os.path.lexists(output):
            raise PrepareError("Output appeared during verification; refusing to replace it")
        staging.chmod(0o755)
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = prepare(args.lock, args.out)
    except (PrepareError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {len(receipt['packages'])} verified wheels in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
