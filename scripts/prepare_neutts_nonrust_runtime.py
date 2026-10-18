#!/usr/bin/env python3
"""Prepare exact sources and dependencies for six independent native experiments.

This program downloads/verifies inputs and exports new source trees. It never
installs packages, runs source build backends, downloads gated models, changes a
production admission rule, or writes a release. The separate native runner owns
compilation, isolated installation, and actual operation evidence.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tarfile
import tempfile
import time
import urllib.request
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_FILENAME = "neutts_nonrust_runtime_lock.json"
RECEIPT_FILENAME = "NONRUST-PREPARED-INPUTS.json"
LOCK_SHA256 = "a97d01c1b9c491e0f3e62907df1739a73dab23c4dd80c381b6a445dfa4c0b8a5"
BASE_PREPARER_SHA256 = "b6a358f87fb675f00a9e125b821d94ae81d9341cb9b4ab9fe2953ea1697318eb"
EXPECTED_SOURCES = frozenset(("audioop-lts", "pandas", "pycryptodomex", "pyyaml",
                              "scikit-learn", "sentencepiece"))
MAX_WHEEL_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def base_helper():
    path = SCRIPT_DIR / "prepare_phonemizer_runtime.py"
    require(sha(path.read_bytes()) == BASE_PREPARER_SHA256, "Reviewed artifact verifier changed")
    spec = importlib.util.spec_from_file_location("_nonrust_artifact_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_regular(path, limit):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
            "Expected a bounded, regular, non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == info.st_size, "File size changed during read")
    return raw


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value
            and "\0" not in value and ":" not in value, "Invalid relative path")
    parts = PurePosixPath(value).parts
    require(not value.startswith("/") and value == "/".join(parts)
            and all(p not in ("", ".", "..") for p in parts), "Unsafe relative path")
    return value


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def wheel_facts(path, *, artifact=None):
    """Read every CRC/RECORD entry and freeze actual metadata; execute no code."""
    path = Path(path)
    raw = read_regular(path, MAX_WHEEL_BYTES)
    actual_artifact = {"filename": path.name, "bytes": len(raw), "sha256": sha(raw)}
    if artifact is not None:
        require(all(artifact[k] == actual_artifact[k] for k in actual_artifact),
                "Wheel artifact identity differs")
        actual_artifact = dict(artifact)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        require(len(entries) < 25000 and len(names) == len(set(names))
                and len({n.casefold() for n in names}) == len(names),
                "Duplicate or oversized wheel inventory")
        expanded = sum(i.file_size for i in entries)
        require(0 < expanded <= MAX_EXPANDED_BYTES, "Expanded wheel exceeds bound")
        files, hashes, sizes, native = {}, {}, {}, []
        for item in entries:
            safe_relative(item.filename.rstrip("/"))
            mode = item.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not item.flag_bits & 1
                    and (not stat.S_IFMT(mode) or stat.S_ISREG(mode) or stat.S_ISDIR(mode))
                    and 0 <= item.file_size <= MAX_MEMBER_BYTES,
                    "Unsafe wheel member")
            if item.is_dir():
                continue
            value = archive.read(item)
            require(len(value) == item.file_size, "Truncated wheel member")
            hashes[item.filename], sizes[item.filename] = sha(value), len(value)
            if re.fullmatch(r"[^/]+\.dist-info/(METADATA|WHEEL|RECORD)", item.filename):
                files[item.filename] = value
            if item.filename.endswith((".so", ".pyd", ".dll", ".dylib")) or ".so." in item.filename:
                native.append({"member": item.filename, "bytes": len(value), "sha256": sha(value)})
        metadata_names = [n for n in files if n.endswith("/METADATA")]
        require(len(metadata_names) == 1, "Ambiguous wheel distribution metadata")
        mn = metadata_names[0]
        prefix = mn.rsplit("/", 1)[0]
        wn, rn = prefix + "/WHEEL", prefix + "/RECORD"
        require(set(files) == {mn, wn, rn}, "Missing or foreign top-level wheel metadata")
        metadata = BytesParser(policy=compat32).parsebytes(files[mn])
        wheel = BytesParser(policy=compat32).parsebytes(files[wn])
        def one(message, key, optional=False):
            values = message.get_all(key, [])
            require(len(values) == (0 if optional and not values else 1), "Ambiguous metadata field: " + key)
            return values[0] if values else ""
        name, version = canonical_name(one(metadata, "Name")), one(metadata, "Version")
        declared = metadata.get_all("Requires-Dist", [])
        require(one(wheel, "Wheel-Version") == "1.0", "Unreviewed wheel format")
        pure = one(wheel, "Root-Is-Purelib")
        require(pure in ("true", "false"), "Invalid purelib marker")
        tags = wheel.get_all("Tag", [])
        require(tags and len(tags) == len(set(tags)), "Missing/duplicate wheel tags")
        rows = list(csv.reader(io.StringIO(files[rn].decode("utf-8"))))
        require(all(len(row) == 3 for row in rows) and len(rows) == len(hashes)
                and len({row[0] for row in rows}) == len(rows)
                and {row[0] for row in rows} == set(hashes), "Incomplete wheel RECORD")
        for member, digest, size in rows:
            if member == rn:
                require(digest == size == "", "RECORD self-entry must be unhashed")
            else:
                actual = base64.urlsafe_b64encode(bytes.fromhex(hashes[member])).decode().rstrip("=")
                require(digest == "sha256=" + actual and size == str(sizes[member]),
                        "Wheel RECORD hash/size mismatch")
        lines_sha = lambda values: sha("\n".join(values).encode())
        return {
            "name": name, "version": version,
            "requires_python": one(metadata, "Requires-Python", True),
            "requires_dist": declared,
            "base_requires_dist": [value for value in declared if ";" not in value],
            "artifact": actual_artifact,
            "wheel": {
                "tags": tags, "root_is_purelib": pure == "true",
                "metadata_member": mn, "metadata_sha256": sha(files[mn]),
                "wheel_member": wn, "wheel_sha256": sha(files[wn]),
                "record_member": rn, "record_sha256": sha(files[rn]),
                "entry_count": len(entries), "file_count": len(hashes),
                "uncompressed_bytes": expanded, "max_member_bytes": max(sizes.values()),
                "members_sha256": lines_sha(sorted(names)),
                "declared_requires_dist_count": len(declared),
                "declared_requires_dist_sha256": lines_sha(declared),
            },
            "native_members": sorted(native, key=lambda x: x["member"]),
        }


def verify_wheel(path, package):
    facts = wheel_facts(path, artifact=package["artifact"])
    expected = {key: value for key, value in package.items()
                if key in facts}
    require(facts == expected, "Wheel metadata or member inventory differs from reviewed inputs")
    return facts


def ar_parts(raw):
    require(raw.startswith(b"!<arch>\n"), "Invalid Debian ar archive")
    at, seen = 8, set()
    while at < len(raw):
        head = raw[at:at + 60]
        require(len(head) == 60 and head[58:60] == b"\x60\n", "Malformed ar header")
        name = head[:16].decode("ascii").strip().rstrip("/")
        require(name and name not in seen, "Duplicate ar member")
        seen.add(name)
        try:
            size = int(head[48:58])
        except ValueError:
            raise PrepareError("Invalid ar size") from None
        require(0 <= size <= len(raw) - at - 60, "Invalid ar member bounds")
        yield name, raw[at + 60:at + 60 + size]
        at += 60 + size + size % 2
    require(at == len(raw), "Trailing ar bytes")


def apt_python_payload(path, pin, *, include_bytes=False):
    """Select the complete Python site payload, preserving its original metadata."""
    raw = read_regular(path, pin["bytes"])
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "APT archive identity differs")
    parts = dict(ar_parts(raw))
    controls = [v for k, v in parts.items() if k.startswith("control.tar.")]
    payloads = [v for k, v in parts.items() if k.startswith("data.tar.")]
    require(len(controls) == len(payloads) == 1, "Ambiguous Debian archive payload")
    with tarfile.open(fileobj=io.BytesIO(controls[0]), mode="r:*") as archive:
        controls = [m for m in archive if m.name.removeprefix("./") == "control"]
        require(len(controls) == 1 and controls[0].isfile() and controls[0].size < 100000,
                "Invalid APT control")
        control_raw = archive.extractfile(controls[0]).read()
        control = BytesParser(policy=compat32).parsebytes(control_raw)
    require(control["Package"] == pin["name"] and control["Version"] == pin["version"]
            and control["Architecture"] == pin["architecture"], "APT control identity changed")
    prefix = "data/data/com.termux/files/usr/lib/python3.14/site-packages/"
    rows, contents, seen = [], {}, set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payloads[0]), mode="r|*") as archive:
        for item in archive:
            name = item.name.removeprefix("./").rstrip("/")
            if item.name in (".", "./"):
                require(item.isdir() and "." not in seen, "Invalid or duplicate APT root member")
                seen.add(".")
                continue
            safe_relative(name)
            require(name not in seen, "Duplicate APT data member")
            seen.add(name)
            if not name.startswith(prefix) or item.isdir():
                continue
            relative = safe_relative(name[len(prefix):])
            require(item.isfile() and 0 <= item.size <= MAX_MEMBER_BYTES,
                    "Unreviewed APT Python symlink or special member")
            total += item.size
            require(total <= MAX_EXPANDED_BYTES, "APT Python payload exceeds bound")
            value = archive.extractfile(item).read()
            require(len(value) == item.size, "Truncated APT Python member")
            rows.append({"path": relative, "bytes": len(value), "sha256": sha(value),
                         "mode": "100755" if item.mode & 0o111 else "100644",
                         "archive_mode": format(item.mode, "04o")})
            if include_bytes:
                contents[relative] = value
    rows.sort(key=lambda row: row["path"])
    require(rows and len({r["path"].casefold() for r in rows}) == len(rows),
            "Empty or aliased APT Python payload")
    metadata = [r for r in rows if re.fullmatch(r"[^/]+\.dist-info/METADATA", r["path"])]
    require(len(metadata) == 1, "APT Python archive does not contain exactly one distribution")
    return {
        "archive": dict(pin), "control_sha256": sha(control_raw),
        "files": rows, "file_count": len(rows), "bytes": total,
        "metadata_member": metadata[0]["path"],
        "metadata_sha256": metadata[0]["sha256"],
    }, contents


def verify_tree(root, files):
    expected = {row["path"]: row for row in files}
    found = set()
    require(root.is_dir() and not root.is_symlink(), "Missing exported tree")
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Source/payload tree contains a symlink")
        if path.is_dir():
            continue
        name = safe_relative(path.relative_to(root).as_posix())
        require(name in expected, "Unreviewed exported file")
        row = expected[name]
        raw = read_regular(path, row["bytes"])
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "Exported file bytes differ")
        if os.name != "nt":
            require(bool(path.stat().st_mode & 0o111) == (row["mode"] == "100755"),
                    "Exported executable mode changed")
        found.add(name)
    require(found == set(expected), "Incomplete exported tree")
    return {"files": len(found), "bytes": sum(row["bytes"] for row in files)}


def apply_source_patch(root, source, patch):
    expected = source.get("patch")
    require(expected and len(patch) == expected["bytes"] and sha(patch) == expected["sha256"],
            "Source patch identity changed")
    for file in expected["files"]:
        path = root / safe_relative(file["path"])
        raw = read_regular(path, file["before_bytes"])
        require(len(raw) == file["before_bytes"] and sha(raw) == file["before_sha256"],
                "Patch target is not the exact original source")
        value = raw.decode("utf-8")
        for edit in file["edits"]:
            require(value.count(edit["old"]) == 1, "Patch hunk does not match exactly once")
            value = value.replace(edit["old"], edit["new"], 1)
        after = value.encode()
        require(len(after) == file["after_bytes"] and sha(after) == file["after_sha256"],
                "Patched source differs from reviewed result")
        path.write_bytes(after)
    return verify_tree(root, source["prepared_files"])


def tsv(packages):
    return "".join("\t".join((p["name"], p["version"], p["architecture"], p["sha256"],
                              str(p["bytes"]), p["filename"])) + "\n" for p in packages).encode()


def load_lock(path):
    raw = read_regular(path, 8_000_000)
    require(sha(raw) == LOCK_SHA256, "Non-Rust preparation lock changed")
    lock = json.loads(raw)
    require(lock["schema_version"] == 1 and lock["node_count"] == 14
            and lock["edge_count"] == 10 and len(lock["names"]) == 14
            and {p["name"] for p in lock["sources"]} == EXPECTED_SOURCES
            and len(lock["sources"]) == 6 and len(lock["packages"]) == 6
            and len(lock["build_packages"]) == 9 and len(lock["apt_python"]) == 2,
            "Incomplete non-Rust runtime/build closure")
    require(len(lock["build_apt"]["packages"]) == 51
            and {p["name"] for p in lock["build_apt"]["additional_to_141"]} == {"libyaml", "patchelf"}
            and lock["build"]["jobs"] == 2, "Unreviewed native dependency/resource scope")
    return lock, raw


def verify_inputs(directory):
    base = base_helper()
    lock, raw = load_lock(directory / LOCK_FILENAME)
    expected_top = {LOCK_FILENAME, RECEIPT_FILENAME, "main-bundled-wheels.json", "sources",
                    "archives", "wheels", "snapshot", "build-apt-closure.tsv",
                    "build-requirements.txt", "runtime-prebuilt-requirements.txt",
                    "sentencepiece-bounded-build.patch"}
    require({p.name for p in directory.iterdir()} == expected_top, "Prepared input layout changed")
    base.verify_catalog(directory / "main-bundled-wheels.json", lock)
    packages = lock["packages"] + lock["build_packages"]
    require({p.name for p in (directory / "wheels").iterdir()}
            == {p["artifact"]["filename"] for p in packages}, "Prepared wheel set changed")
    for package in packages:
        verify_wheel(directory / "wheels" / package["artifact"]["filename"], package)
    require({p.name for p in (directory / "archives").iterdir()}
            == {p["artifact"]["filename"] for p in lock["sources"]}, "Prepared source archive set changed")
    require({p.name for p in (directory / "sources").iterdir()}
            == {p["archive_root"] for p in lock["sources"]}, "Prepared source tree set changed")
    for source in lock["sources"]:
        base.verified_bytes(directory / "archives" / source["artifact"]["filename"], source["artifact"])
        verify_tree(directory / "sources" / source["archive_root"], source["prepared_files"])
    patch = next(s["patch"] for s in lock["sources"] if "patch" in s)
    require(sha(read_regular(directory / patch["filename"], patch["bytes"])) == patch["sha256"],
            "Prepared patch changed")
    for filename, expected in (("build-requirements.txt", base.requirement_text(lock["build_packages"])),
                               ("runtime-prebuilt-requirements.txt", base.requirement_text(lock["packages"])),
                               ("build-apt-closure.tsv", tsv(lock["build_apt"]["packages"]))):
        require(read_regular(directory / filename, len(expected)) == expected, "Prepared selection file changed")
    require({p.name for p in (directory / "snapshot").iterdir()}
            == {p["filename"] for p in lock["build_apt"]["snapshot"]}, "Snapshot file set changed")
    for pin in lock["build_apt"]["snapshot"]:
        base.verified_bytes(directory / "snapshot" / pin["filename"], pin)
    receipt = json.loads(read_regular(directory / RECEIPT_FILENAME, 8_000_000))
    require(receipt.get("status") == "verified-inputs" and receipt.get("lock_sha256") == sha(raw)
            and receipt.get("installed") is False and receipt.get("native_build_performed") is False,
            "Invalid preparation receipt")
    return lock, receipt


def prepare(lock_path, main_wheelhouse, main_catalog, patch_path, snapshot_dir, output, *, caches=()):
    base = base_helper()
    lock, raw_lock = load_lock(lock_path)
    catalog = base.verify_catalog(main_catalog, lock)
    source_patch = next(s["patch"] for s in lock["sources"] if "patch" in s)
    patch = base.verified_bytes(patch_path, source_patch)
    output = Path(os.path.abspath(output))
    require(not os.path.lexists(output) and output.parent.is_dir(), "Use a fresh output under an existing parent")
    require(not any(parent.is_symlink() for parent in (output.parent, *output.parent.parents)),
            "Output parent traverses a symlink")
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".staging-", dir=output.parent))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), base.NoRedirect())
    deadline = time.monotonic() + 600
    try:
        for name in ("wheels", "sources", "archives", "snapshot"):
            (staging / name).mkdir()
        facts = []
        def acquire(artifact, destination, *, main=False):
            roots = [main_wheelhouse] if main else list(caches)
            candidates = [Path(root) / artifact["filename"] for root in roots]
            cached = next((path for path in candidates if path.exists()), None)
            if cached is not None:
                write_new(destination, base.verified_bytes(cached, artifact))
            elif main:
                raise PrepareError("The exact original catalog wheel is unavailable")
            else:
                base.download_file(artifact, destination, opener, deadline)
        for package in lock["packages"] + lock["build_packages"]:
            destination = staging / "wheels" / package["artifact"]["filename"]
            acquire(package["artifact"], destination, main=package["origin"]["kind"] == "main_catalog")
            facts.append(verify_wheel(destination, package))
        trees = {}
        for source in lock["sources"]:
            destination = staging / "archives" / source["artifact"]["filename"]
            acquire(source["artifact"], destination)
            raw = base.verified_bytes(destination, source["artifact"])
            tree = staging / "sources" / source["archive_root"]
            base.extract_source(raw, source, tree)
            if "patch" in source:
                apply_source_patch(tree, source, patch)
            trees[source["name"]] = verify_tree(tree, source["prepared_files"])
        for pin in lock["build_apt"]["snapshot"]:
            write_new(staging / "snapshot" / pin["filename"],
                      base.verified_bytes(snapshot_dir / pin["filename"], pin))
        write_new(staging / LOCK_FILENAME, raw_lock)
        write_new(staging / "main-bundled-wheels.json", catalog)
        write_new(staging / source_patch["filename"], patch)
        write_new(staging / "build-requirements.txt", base.requirement_text(lock["build_packages"]))
        write_new(staging / "runtime-prebuilt-requirements.txt", base.requirement_text(lock["packages"]))
        write_new(staging / "build-apt-closure.tsv", tsv(lock["build_apt"]["packages"]))
        receipt = {
            "schema_version": 1, "status": "verified-inputs",
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Six exact source exports, six runtime wheels, nine separate build wheels; native APT payloads remain a distinct archive gate.",
            "lock_sha256": sha(raw_lock), "node_count": 14, "edge_count": 10,
            "catalog_sha256": sha(catalog), "wheels": facts, "source_trees": trees,
            "native_build_performed": False, "installed": False, "model_downloaded": False,
            "production_admission_changed": False, "release_output": False,
        }
        write_new(staging / RECEIPT_FILENAME, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        verify_inputs(staging)
        require(not os.path.lexists(output), "Output appeared while preparing inputs")
        for path in [staging, *staging.rglob("*")]:
            if path.is_dir():
                path.chmod(0o755)
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=SCRIPT_DIR / LOCK_FILENAME)
    parser.add_argument("--main-wheelhouse", type=Path, required=True)
    parser.add_argument("--main-catalog", type=Path, required=True)
    parser.add_argument("--patch", type=Path, default=SCRIPT_DIR.parent / "patches/next-stable/sentencepiece-bounded-build.patch")
    parser.add_argument("--snapshot-dir", type=Path, default=SCRIPT_DIR.parent / "audit/neutts-runtime-index-20261017")
    parser.add_argument("--cache", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.lock, args.main_wheelhouse, args.main_catalog, args.patch,
                         args.snapshot_dir, args.out, caches=args.cache)
    except (PrepareError, OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(1, type(exc).__name__ + ": " + str(exc) + "\n")
    print(json.dumps({"status": report["status"], "lock_sha256": report["lock_sha256"],
                      "runtime_nodes": 14, "active_edges": 10, "out": str(args.out)}))


if __name__ == "__main__":
    main()
