#!/usr/bin/env python3
"""Verify and stage the complete 23-distribution Phonemizer input closure.

Host-only preparation: no installation, native compilation, model access or
production admission. Exact source archives and the reviewed dlinfo patch are
staged with all 21 prebuilt runtime wheels and separate two-wheel build inputs.
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
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

LOCK_SHA256 = "48d43784778817bd4a907b63f11738ff910cafc6aac2eed6bc27349b6d5d8c82"
LOCK_FILENAME = "phonemizer-runtime-lock.json"
RECEIPT_FILENAME = "PHONEMIZER-PREPARED-INPUTS.json"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 300
READ_TIMEOUT_SECONDS = 20
CHUNK_BYTES = 256 * 1024
EXPECTED_NAMES = (
    "attrs", "babel", "cloudpickle", "csvw", "dlinfo", "isodate", "joblib",
    "jsonschema", "jsonschema-specifications", "language-tags", "phonemizer",
    "pyparsing", "python-dateutil", "rdflib", "referencing", "regex", "rfc3986",
    "rpds-py", "segments", "six", "termcolor", "typing-extensions", "uritemplate",
)


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


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or len(value) > 1024 or str(path) != value or path.is_absolute()
            or "\\" in value or ":" in value
            or any(part in (".", "..") for part in path.parts)
            or any(ord(char) < 32 for char in value)):
        raise PrepareError("Unsafe relative source path")
    return value


def validate_artifact(artifact: dict) -> None:
    filename = artifact["filename"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:\.whl|\.tar\.gz)", filename):
        raise PrepareError("Unsafe artifact filename")
    if (type(artifact["bytes"]) is not int or not 0 < artifact["bytes"] <= MAX_ARCHIVE_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])):
        raise PrepareError("Invalid artifact size or digest")
    if "url" in artifact:
        pattern = (r"https://files\.pythonhosted\.org/packages/"
                   r"[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/" + re.escape(filename))
        if not re.fullmatch(pattern, artifact["url"]):
            raise PrepareError("Artifact URL is not its exact immutable official endpoint")


def load_lock(path: Path) -> tuple[dict, bytes]:
    raw = read_regular(path, 128 * 1024)
    if sha256(raw) != LOCK_SHA256:
        raise PrepareError("Lock bytes differ from the reviewed frozen identity")
    lock = json.loads(raw)
    if (lock["schema_version"] != 1 or tuple(lock["names"]) != EXPECTED_NAMES
            or lock["node_count"] != 23 or lock["edge_count"] != 26
            or len(lock["edges"]) != 26
            or lock["target"] != {
                "python": "3.14.6", "implementation": "cpython",
                "platform": "android_24_arm64_v8a", "abi": "cp314",
                "prefix": "/data/data/com.termux/files/usr",
            }):
        raise PrepareError("Unexpected frozen scope")
    wheels = lock["packages"] + lock["build_packages"]
    if (len(lock["packages"]) != 21 or len(lock["build_packages"]) != 2
            or {p["name"] for p in lock["packages"]} | {"phonemizer", "regex"}
            != set(EXPECTED_NAMES)
            or [p["name"] for p in lock["sources"]] != ["phonemizer", "regex"]):
        raise PrepareError("Incomplete runtime or build input set")
    artifacts = [p["artifact"] for p in wheels + lock["sources"]]
    for artifact in artifacts:
        validate_artifact(artifact)
    if (len({a["filename"] for a in artifacts}) != len(artifacts)
            or sum(a["bytes"] for a in artifacts) > MAX_TOTAL_BYTES):
        raise PrepareError("Duplicate or oversized input set")
    return lock, raw


def verified_bytes(path: Path, artifact: dict) -> bytes:
    raw = read_regular(path, artifact["bytes"])
    if len(raw) != artifact["bytes"] or sha256(raw) != artifact["sha256"]:
        raise PrepareError("Artifact size or SHA-256 mismatch: " + artifact["filename"])
    return raw


def verify_catalog(path: Path, lock: dict) -> bytes:
    expected = lock["main_catalog"]
    raw = read_regular(path, expected["bytes"])
    if len(raw) != expected["bytes"] or sha256(raw) != expected["sha256"]:
        raise PrepareError("Original main catalog identity differs")
    catalog = json.loads(raw)
    if catalog.get("schema_version") != 1 or len(catalog.get("wheels", [])) != 100:
        raise PrepareError("Original main catalog is incomplete")
    rows = {canonical_name(p["name"]): p for p in catalog["wheels"]}
    if len(rows) != 100:
        raise PrepareError("Duplicate main catalog distribution")
    for package in lock["packages"]:
        if package["origin"]["kind"] == "main_catalog":
            if rows.get(package["name"]) != package["origin"]["catalog_record"]:
                raise PrepareError("Main catalog source record changed")
    return raw


def extract_source(raw: bytes, source: dict, destination: Path) -> list[dict]:
    artifact = source["artifact"]
    if len(raw) != artifact["bytes"] or sha256(raw) != artifact["sha256"]:
        raise PrepareError("Source archive identity differs")
    expected = {row["path"]: row for row in source["files"]}
    files = {}
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            value = member.name.rstrip("/")
            safe_relative(value)
            if value in seen:
                raise PrepareError("Duplicate source member")
            seen.add(value)
            parts = PurePosixPath(value).parts
            if parts[0] != source["archive_root"]:
                raise PrepareError("Unexpected source archive root")
            if not member.isdir() and not member.isfile():
                raise PrepareError("Source symlinks and special files are not accepted")
            if member.isdir():
                continue
            relative = "/".join(parts[1:])
            safe_relative(relative)
            if relative not in expected or not 0 <= member.size <= MAX_MEMBER_BYTES:
                raise PrepareError("Unexpected source file or size")
            total += member.size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise PrepareError("Expanded source exceeds bound")
            raw_file = archive.extractfile(member).read()
            row = {"path": relative, "bytes": len(raw_file), "sha256": sha256(raw_file),
                   "mode": "100755" if member.mode & 0o111 else "100644"}
            if row != expected[relative]:
                raise PrepareError("Source member differs from frozen manifest")
            files[relative] = raw_file
    if set(files) != set(expected):
        raise PrepareError("Source archive omits frozen files")
    destination.mkdir()
    for name, contents in files.items():
        path = destination.joinpath(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new(path, contents)
        path.chmod(0o755 if expected[name]["mode"] == "100755" else 0o644)
    return source["files"]


def apply_patch_files(root: Path, patch: bytes, source: dict) -> list[dict]:
    """Apply exact unified hunks, checking every context line and output digest."""
    frozen = source["patch"]
    if len(patch) != frozen["bytes"] or sha256(patch) != frozen["sha256"]:
        raise PrepareError("Phonemizer patch identity differs")
    lines = patch.decode("utf-8").splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts or starts[0] != 0:
        raise PrepareError("Malformed patch header")
    starts.append(len(lines))
    expected_names = {frozen["production_path"], frozen["added_test_path"]}
    changed = []
    for lo, hi in zip(starts, starts[1:]):
        block = lines[lo:hi]
        match = re.fullmatch(r"diff --git a/(.+) b/(.+)\n", block[0])
        if not match or match[1] != match[2]:
            raise PrepareError("Unexpected patch rename or header")
        relative = safe_relative(match[1])
        if relative not in expected_names or relative in changed:
            raise PrepareError("Unexpected or duplicate patch target")
        path = root.joinpath(*PurePosixPath(relative).parts)
        old = read_regular(path, MAX_MEMBER_BYTES).decode("utf-8").splitlines(keepends=True) if path.exists() else []
        if relative == frozen["production_path"]:
            if sha256("".join(old).encode()) != frozen["before_sha256"]:
                raise PrepareError("Patch production preimage differs")
        elif path.exists():
            raise PrepareError("New patch test target already exists")
        hunks = [i for i, line in enumerate(block) if line.startswith("@@ ")]
        if not hunks:
            raise PrepareError("Patch target has no hunks")
        result, cursor = [], 0
        for index, start in enumerate(hunks):
            stop = hunks[index + 1] if index + 1 < len(hunks) else len(block)
            header = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", block[start])
            if not header:
                raise PrepareError("Malformed unified hunk")
            old_start, old_count = int(header[1]), int(header[2] or "1")
            new_start, new_count = int(header[3]), int(header[4] or "1")
            offset = old_start - 1 if old_count else old_start
            if not cursor <= offset <= len(old):
                raise PrepareError("Overlapping or out-of-range patch hunk")
            result.extend(old[cursor:offset])
            cursor = offset
            if len(result) != (new_start - 1 if new_count else new_start):
                raise PrepareError("Patch new-file offset differs")
            consumed = emitted = 0
            for line in block[start + 1:stop]:
                if not line or line[0] not in " +-":
                    raise PrepareError("Unsupported unified patch line")
                if line[0] in " -":
                    if cursor >= len(old) or old[cursor] != line[1:]:
                        raise PrepareError("Patch hunk context differs")
                    cursor += 1
                    consumed += 1
                if line[0] in " +":
                    result.append(line[1:])
                    emitted += 1
            if (consumed, emitted) != (old_count, new_count):
                raise PrepareError("Patch hunk counts differ")
        result.extend(old[cursor:])
        content = "".join(result).encode("utf-8")
        expected_hash = (frozen["after_sha256"] if relative == frozen["production_path"]
                         else frozen["added_test_sha256"])
        if sha256(content) != expected_hash:
            raise PrepareError("Patched file does not match reviewed output")
        if relative == frozen["added_test_path"] and len(content) != frozen["added_test_bytes"]:
            raise PrepareError("Patched test size differs")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.write_bytes(content)
        else:
            write_new(path, content)
        changed.append(relative)
    if set(changed) != expected_names:
        raise PrepareError("Patch omits a reviewed change")
    return source_tree(root, source, patched=True)


def source_tree(root: Path, source: dict, *, patched: bool) -> list[dict]:
    expected = {row["path"]: dict(row) for row in source["files"]}
    if source["name"] == "phonemizer" and patched:
        patch = source["patch"]
        expected[patch["production_path"]]["sha256"] = patch["after_sha256"]
        expected[patch["production_path"]]["bytes"] = 10136
        expected[patch["added_test_path"]] = {
            "path": patch["added_test_path"], "bytes": patch["added_test_bytes"],
            "sha256": patch["added_test_sha256"], "mode": "100644",
        }
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PrepareError("Symlink in staged source tree")
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        safe_relative(relative)
        if relative not in expected:
            raise PrepareError("Unexpected source tree file")
        row = expected[relative]
        raw = read_regular(path, row["bytes"])
        if len(raw) != row["bytes"] or sha256(raw) != row["sha256"]:
            raise PrepareError("Source tree bytes differ")
        if os.name != "nt" and (path.stat().st_mode & 0o111) != (0o111 if row["mode"] == "100755" else 0):
            raise PrepareError("Source tree executable mode differs")
        actual[relative] = row
    if set(actual) != set(expected):
        raise PrepareError("Source tree is incomplete")
    return [actual[name] for name in sorted(actual)]


def requirement_text(packages: list[dict]) -> bytes:
    return "".join(
        f"{p['name']}=={p['version']} --hash=sha256:{p['artifact']['sha256']}\n"
        for p in packages
    ).encode("utf-8")


def verify_inputs(directory: Path) -> tuple[dict, dict]:
    lock, raw = load_lock(directory / LOCK_FILENAME)
    catalog = verify_catalog(directory / "main-bundled-wheels.json", lock)
    wheels = lock["packages"] + lock["build_packages"]
    check_file_set(directory / "wheels", {p["artifact"]["filename"] for p in wheels})
    facts = [verify_wheel(directory / "wheels" / p["artifact"]["filename"], p) for p in wheels]
    check_file_set(directory / "archives", {s["artifact"]["filename"] for s in lock["sources"]})
    for source in lock["sources"]:
        verified_bytes(directory / "archives" / source["artifact"]["filename"], source["artifact"])
    patch = read_regular(directory / "phonemizer-lazy-dlinfo.patch", 20_000)
    frozen = lock["sources"][0]["patch"]
    if len(patch) != frozen["bytes"] or sha256(patch) != frozen["sha256"]:
        raise PrepareError("Staged patch bytes differ")
    source_roots = {s["archive_root"] for s in lock["sources"]}
    if {p.name for p in (directory / "sources").iterdir()} != source_roots:
        raise PrepareError("Unexpected staged source roots")
    trees = {s["name"]: source_tree(directory / "sources" / s["archive_root"], s, patched=True)
             for s in lock["sources"]}
    for filename, packages in (("runtime-prebuilt-requirements.txt", lock["packages"]),
                               ("build-requirements.txt", lock["build_packages"])):
        if read_regular(directory / filename, 20_000) != requirement_text(packages):
            raise PrepareError("Staged requirements differ")
    receipt = json.loads(read_regular(directory / RECEIPT_FILENAME, 256_000))
    if (receipt.get("schema_version") != 1 or receipt.get("status") != "verified-inputs"
            or receipt.get("lock_sha256") != sha256(raw)
            or receipt.get("source_trees") != trees
            or receipt.get("wheels") != facts
            or receipt.get("native_build_performed") is not False):
        raise PrepareError("Staged receipt differs from verified inputs")
    expected_top = {LOCK_FILENAME, RECEIPT_FILENAME, "main-bundled-wheels.json",
                    "phonemizer-lazy-dlinfo.patch", "runtime-prebuilt-requirements.txt",
                    "build-requirements.txt", "wheels", "archives", "sources"}
    if {p.name for p in directory.iterdir()} != expected_top or any(p.is_symlink() for p in directory.iterdir()):
        raise PrepareError("Unexpected staged top-level entry")
    return lock, receipt


def prepare(lock_path: Path, main_wheelhouse: Path, main_catalog: Path,
            patch_path: Path, output: Path, *, cache: Path | None = None, opener=None) -> dict:
    lock, raw_lock = load_lock(lock_path)
    catalog = verify_catalog(main_catalog, lock)
    patch = read_regular(patch_path, 20_000)
    frozen = lock["sources"][0]["patch"]
    if len(patch) != frozen["bytes"] or sha256(patch) != frozen["sha256"]:
        raise PrepareError("Patch differs from the reviewed input")
    output = Path(os.path.abspath(output))
    if os.path.lexists(output) or not output.parent.is_dir():
        raise PrepareError("A fresh output under an existing parent is required")
    if any(parent.is_symlink() for parent in (output.parent, *output.parent.parents)):
        raise PrepareError("Output parent must not traverse a symlink")
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".staging-", dir=output.parent))
    deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
    try:
        for name in ("wheels", "archives", "sources"):
            (staging / name).mkdir()
        facts = []
        for package in lock["packages"] + lock["build_packages"]:
            artifact = package["artifact"]
            dest = staging / "wheels" / artifact["filename"]
            is_main = package["origin"]["kind"] == "main_catalog"
            cached = (main_wheelhouse if is_main else cache)
            cached = cached / artifact["filename"] if cached is not None else None
            if cached is not None and cached.exists():
                write_new(dest, verified_bytes(cached, artifact))
            elif is_main:
                raise PrepareError("Required original catalog wheel is unavailable")
            else:
                download_file(artifact, dest, opener, deadline)
            facts.append(verify_wheel(dest, package))
        trees = {}
        for source in lock["sources"]:
            artifact = source["artifact"]
            dest = staging / "archives" / artifact["filename"]
            cached = cache / artifact["filename"] if cache is not None else None
            if cached is not None and cached.exists():
                write_new(dest, verified_bytes(cached, artifact))
            else:
                download_file(artifact, dest, opener, deadline)
            raw_source = verified_bytes(dest, artifact)
            root = staging / "sources" / source["archive_root"]
            extract_source(raw_source, source, root)
            if source["name"] == "phonemizer":
                apply_patch_files(root, patch, source)
            trees[source["name"]] = source_tree(root, source, patched=True)
        write_new(staging / LOCK_FILENAME, raw_lock)
        write_new(staging / "main-bundled-wheels.json", catalog)
        write_new(staging / "phonemizer-lazy-dlinfo.patch", patch)
        write_new(staging / "runtime-prebuilt-requirements.txt", requirement_text(lock["packages"]))
        write_new(staging / "build-requirements.txt", requirement_text(lock["build_packages"]))
        receipt = {
            "schema_version": 1, "status": "verified-inputs",
            "scope": "21 runtime wheels, two separate build wheels, two exact sources; no native execution.",
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "lock_sha256": sha256(raw_lock), "node_count": 23, "edge_count": 26,
            "catalog_sha256": sha256(catalog), "wheels": facts, "source_trees": trees,
            "native_build_performed": False, "installed": False, "model_downloaded": False,
            "production_admission_changed": False,
        }
        write_new(staging / RECEIPT_FILENAME, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        verify_inputs(staging)
        if os.path.lexists(output):
            raise PrepareError("Output appeared during preparation")
        for directory in [staging, *(p for p in staging.rglob("*") if p.is_dir())]:
            directory.chmod(0o755)
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--main-wheelhouse", type=Path, required=True)
    parser.add_argument("--main-catalog", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = prepare(args.lock, args.main_wheelhouse, args.main_catalog,
                          args.patch, args.out, cache=args.cache)
    except (PrepareError, OSError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "runtime_distributions": 23,
                      "native_build_performed": False, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
