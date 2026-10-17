#!/usr/bin/env python3
"""Freeze exact Rust component inputs without executing Cargo or source backends.

The locked stage keeps all three runtime Cargo.lock files and Maturin's lock
unchanged. Every crate is an exact original registry archive, exported as Cargo's
documented directory source. Tiktoken's missing lock is an explicit later native
resolution stage; this preparer never invents or silently resolves that lock.
"""
from __future__ import annotations

import argparse
import base64
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tarfile
import time
import tomllib
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_FILENAME = "neutts_rust_sources_lock.json"
LOCK_SHA256 = "c72d8bfa5f9ae86205443b2c7c19892be77a2879ec7604ccd77aeda2a94775af"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
LOCKED_NAMES = ("maturin", "hf-xet", "safetensors", "tokenizers")
ALL_NAMES = (*LOCKED_NAMES, "tiktoken")
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_SOURCE_FILES = 40000
MAX_DOWNLOAD_SECONDS = 1200


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Expected a regular file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_regular(path, limit=MAX_ARCHIVE_BYTES):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
            "Missing, linked, or oversized input")
    raw = path.read_bytes()
    require(len(raw) == info.st_size, "Input size changed while reading")
    return raw


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value
            and all(ord(c) >= 32 for c in value), "Invalid relative path")
    parts = PurePosixPath(value).parts
    require(not value.startswith("/") and value == "/".join(parts)
            and all(p not in ("", ".", "..") for p in parts), "Unsafe relative path")
    return value


def apt_archive_filename(pin):
    """Map an original APT index identity to a portable owned cache basename.

    Only a Debian version epoch colon is encoded. The original index Filename,
    Version, URL, size and SHA remain authoritative and are never rewritten.
    """
    name, version, architecture = pin["name"], pin["version"], pin["architecture"]
    require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name)
            and isinstance(version, str)
            and re.fullmatch(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+~-]*", version)
            and version.count(":") <= 1
            and (":" not in version or re.match(r"^[0-9]+:", version))
            and architecture in ("aarch64", "all"), "Invalid APT archive identity")
    original = pin["filename"]
    basename = name + "_" + version + "_" + architecture + ".deb"
    require(isinstance(original, str) and original.startswith("pool/main/")
            and "%" not in original and PurePosixPath(original).name == basename
            and pin["url"] == "https://packages.termux.dev/apt/termux-main/" + original,
            "APT original filename or URL differs")
    encoded = original.replace(":", "%3A")
    safe_relative(encoded)
    local = basename.replace(":", "%3A")
    safe_relative(local)
    require(local.replace("%3A", ":") == basename, "APT local name is not reversible")
    return local


def apt_archive_names(pins):
    names = {p["filename"]: apt_archive_filename(p) for p in pins}
    values = list(names.values())
    require(len(names) == len(pins) and len(set(values)) == len(values)
            and len({v.casefold() for v in values}) == len(values),
            "Duplicate or aliased APT cache filenames")
    return names


def write_new(path, raw, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(mode)


def verified_bytes(path, artifact):
    raw = read_regular(path, artifact.get("bytes") or MAX_ARCHIVE_BYTES)
    require((not artifact.get("bytes") or len(raw) == artifact["bytes"])
            and sha(raw) == artifact["sha256"], "Artifact bytes differ: " + path.name)
    return raw


def artifact_identity(path):
    raw = read_regular(path)
    return {"filename": path.name, "bytes": len(raw), "sha256": sha(raw)}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def download(pin, destination, caches, deadline):
    safe_relative(pin["filename"])
    require("/" not in pin["filename"] and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]),
            "Invalid frozen artifact")
    if destination.exists():
        raise PrepareError("Fresh output contains an existing artifact")
    for cache in caches:
        source = cache / pin["filename"]
        if source.exists() or source.is_symlink():
            raw = verified_bytes(source, pin)
            write_new(destination, raw)
            return artifact_identity(destination)
    require(pin["url"].startswith((
        "https://files.pythonhosted.org/packages/", "https://static.crates.io/crates/",
        "https://packages.termux.dev/apt/termux-main/",
    )), "Unreviewed artifact origin")
    opener = build_opener(NoRedirect())
    limit = pin.get("bytes") or MAX_ARCHIVE_BYTES
    request = Request(pin["url"], headers={"User-Agent": "termux-hermes-rust-preparation",
                                          "Accept-Encoding": "identity"})
    try:
        with opener.open(request, timeout=30) as response, destination.open("xb") as stream:
            require(response.status == 200, "Artifact server did not return 200")
            digest, total = hashlib.sha256(), 0
            while chunk := response.read(256 * 1024):
                require(time.monotonic() < deadline, "Exact input download deadline expired")
                total += len(chunk)
                require(total <= limit, "Artifact exceeded its reviewed size bound")
                digest.update(chunk)
                stream.write(chunk)
        require((not pin.get("bytes") or total == pin["bytes"])
                and digest.hexdigest() == pin["sha256"], "Downloaded artifact hash/size differs")
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise PrepareError("Artifact download returned HTTP " + str(code)) from None
    destination.chmod(0o644)
    return artifact_identity(destination)


def archive_files(raw, root, *, output=None, max_files=MAX_SOURCE_FILES):
    """Export only regular original members, retaining all source bytes."""
    safe_relative(root)
    require("/" not in root, "Archive root must be one directory")
    rows, seen, folded, total = [], set(), set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            safe_relative(name)
            require(name == root or name.startswith(root + "/"), "Archive member escaped its one root")
            require(name not in seen and name.casefold() not in folded, "Duplicate/aliased archive path")
            seen.add(name)
            folded.add(name.casefold())
            require(len(seen) <= max_files and (member.isfile() or member.isdir()),
                    "Archive contains a link, special member, or excessive entries")
            if member.isdir():
                continue
            relative = safe_relative(name[len(root) + 1:])
            require(0 <= member.size <= MAX_MEMBER_BYTES, "Archive member exceeds bound")
            total += member.size
            require(total <= MAX_EXPANDED_BYTES, "Expanded archive exceeds bound")
            value = archive.extractfile(member).read()
            require(len(value) == member.size, "Truncated source member")
            row = {"path": relative, "bytes": len(value), "sha256": sha(value),
                   "executable": bool(member.mode & 0o111)}
            rows.append(row)
            if output is not None:
                write_new(output / relative, value, 0o755 if row["executable"] else 0o644)
    rows.sort(key=lambda row: row["path"])
    require(rows, "Archive has no original source files")
    return rows


def tree_files(root):
    require(root.is_dir() and not root.is_symlink(), "Missing source tree")
    rows = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Exported tree contains a symlink")
        if path.is_dir():
            continue
        raw = read_regular(path, MAX_MEMBER_BYTES)
        rows.append({"path": safe_relative(path.relative_to(root).as_posix()),
                     "bytes": len(raw), "sha256": sha(raw),
                     "executable": bool(path.stat().st_mode & 0o111)})
    rows.sort(key=lambda row: row["path"])
    return rows


def same_files(actual, expected):
    def key(row):
        return {k: v for k, v in row.items() if k != "executable" or os.name != "nt"}
    require([key(row) for row in actual] == [key(row) for row in expected],
            "Exported source inventory differs from the exact archive")


def verify_source(root, source, *, allow_new_lock=False):
    rows = tree_files(root)
    if allow_new_lock:
        rows = [row for row in rows if row["path"] != "Cargo.lock"]
    same_files(rows, source["files"])
    return {"files": len(rows), "bytes": sum(row["bytes"] for row in rows)}


def export_crate(path, pin, destination):
    raw = verified_bytes(path, pin)
    root = pin["name"] + "-" + pin["version"]
    rows = archive_files(raw, root, output=destination)
    require(not any(row["path"] == ".cargo-checksum.json" for row in rows),
            "Registry archive unexpectedly supplied directory-source checksum metadata")
    cargo = tomllib.loads((destination / "Cargo.toml").read_text())["package"]
    require((cargo["name"], cargo["version"]) == (pin["name"], pin["version"]),
            "Registry archive manifest identity differs")
    checksum = {"package": pin["sha256"], "files": {r["path"]: r["sha256"] for r in rows}}
    raw_checksum = (json.dumps(checksum, sort_keys=True, separators=(",", ":")) + "\n").encode()
    write_new(destination / ".cargo-checksum.json", raw_checksum)
    return {"name": pin["name"], "version": pin["version"], "archive": artifact_identity(path),
            "files": rows, "checksum_sha256": sha(raw_checksum)}


def verify_crate(path, pin, destination):
    rows = archive_files(verified_bytes(path, pin), pin["name"] + "-" + pin["version"])
    checksum = {"package": pin["sha256"], "files": {r["path"]: r["sha256"] for r in rows}}
    raw_checksum = (json.dumps(checksum, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(read_regular(destination / ".cargo-checksum.json", 8_000_000) == raw_checksum,
            "Directory-source checksum file differs from independent archive verification")
    actual = [r for r in tree_files(destination) if r["path"] != ".cargo-checksum.json"]
    same_files(actual, rows)
    return len(rows)


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_facts(path, *, artifact=None):
    """Read every CRC/RECORD entry and freeze actual metadata; execute no code."""
    path = Path(path)
    raw = read_regular(path, MAX_ARCHIVE_BYTES)
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



def requirement_text(packages):
    return "".join(p["name"] + "==" + p["version"] + " --hash=sha256:"
                   + p["artifact"]["sha256"] + "\n" for p in sorted(packages, key=lambda p: p["name"])).encode()


def load_lock(path):
    raw = read_regular(path, 8_000_000)
    require(sha(raw) == LOCK_SHA256, "Reviewed Rust source/input lock changed")
    lock = json.loads(raw)
    require(lock["schema_version"] == 1 and len(lock["sources"]) == 5
            and {s["name"] for s in lock["sources"]} == set(ALL_NAMES)
            and len(lock["registry"]) == 804 and lock["registry_lock_union_count"] == 804
            and len({(p["name"], p["version"]) for p in lock["registry"]}) == 804,
            "Incomplete Rust source or registry lock union")
    require({p["name"] for p in lock["python_build_packages"]}
            == {"setuptools", "setuptools-rust", "semantic-version", "wheel", "packaging"}
            and len(lock["python_build_packages"]) == 5
            and len(lock["build_apt"]["packages"]) == 46,
            "Incomplete Python/compiler preparation closure")
    require(next(s for s in lock["sources"] if s["name"] == "tiktoken")["cargo_lock"] is None,
            "Tiktoken requires its separate reviewed native lock capture")
    require(all(p["source"] == REGISTRY for p in lock["registry"]), "Unreviewed Git/alternate registry")
    return lock, raw


def snapshot_binding(directory, pins):
    require(directory.is_dir() and not directory.is_symlink(), "Invalid snapshot directory")
    require({p.name for p in directory.iterdir()} == {"InRelease", "Packages.gz"}, "Snapshot directory changed")
    expected = {p["filename"]: p for p in pins}
    release = verified_bytes(directory / "InRelease", expected["InRelease"]).decode()
    verified_bytes(directory / "Packages.gz", expected["Packages.gz"])
    active, bindings = False, []
    for line in release.splitlines():
        if line == "SHA256:":
            active = True
            continue
        if active and line and not line[0].isspace():
            active = False
        if active:
            match = re.fullmatch(r"\s+([a-f0-9]{64})\s+([0-9]+)\s+(\S+)", line)
            if match and match[3] == "main/binary-aarch64/Packages.gz":
                bindings.append((match[1], int(match[2])))
    require(bindings == [(expected["Packages.gz"]["sha256"], expected["Packages.gz"]["bytes"])],
            "InRelease did not bind the exact compressed package index")
    return {"compressed_hash_binding_verified": True, "openpgp_verified_by_this_host_step": False}


def verify_inputs(directory):
    require(directory.is_dir() and not directory.is_symlink(), "Invalid prepared input directory")
    for name in ("archives", "sources", "wheels", "crates", "vendor", "snapshot", "apt-archives"):
        require((directory / name).is_dir() and not (directory / name).is_symlink(), "Linked or missing input directory")
    lock, raw = load_lock(directory / LOCK_FILENAME)
    receipt = json.loads(read_regular(directory / "RUST-PREPARED-INPUTS.json", 8_000_000))
    require(receipt["status"] == "verified-inputs" and receipt["lock_sha256"] == sha(raw)
            and receipt["cargo_executed"] is False and receipt["source_backend_executed"] is False,
            "Invalid input preparation receipt")
    stage = receipt["stage"]
    require(stage in ("locked-build", "tiktoken-lock"), "Unknown native stage")
    sources = [s for s in lock["sources"] if (s["name"] == "tiktoken") == (stage == "tiktoken-lock")]
    require({p.name for p in directory.iterdir()} ==
            {LOCK_FILENAME, "RUST-PREPARED-INPUTS.json", "archives", "sources", "wheels",
             "crates", "vendor", "snapshot", "apt-archives", "build-requirements.txt"},
            "Prepared input layout changed")
    require({p.name for p in (directory / "archives").iterdir()}
            == {s["artifact"]["filename"] for s in sources}, "Source archive selection changed")
    require({p.name for p in (directory / "sources").iterdir()}
            == {s["archive_root"] for s in sources}, "Source tree selection changed")
    for source in sources:
        raw_source = verified_bytes(directory / "archives" / source["artifact"]["filename"], source["artifact"])
        same_files(archive_files(raw_source, source["archive_root"]), source["files"])
        verify_source(directory / "sources" / source["archive_root"], source)
    packages = lock["python_build_packages"] if stage == "locked-build" else []
    require({p.name for p in (directory / "wheels").iterdir()}
            == {p["artifact"]["filename"] for p in packages}, "Build-wheel selection changed")
    for package in packages:
        verify_wheel(directory / "wheels" / package["artifact"]["filename"], package)
    require(read_regular(directory / "build-requirements.txt") == requirement_text(packages),
            "Hashed build requirements changed")
    registry = lock["registry"] if stage == "locked-build" else []
    require({p.name for p in (directory / "crates").iterdir()}
            == {p["filename"] for p in registry}
            and {p.name for p in (directory / "vendor").iterdir()}
            == {p["name"] + "-" + p["version"] for p in registry}, "Registry union changed")
    verified_count = sum(verify_crate(directory / "crates" / p["filename"], p,
                                     directory / "vendor" / (p["name"] + "-" + p["version"]))
                         for p in registry)
    apt_names = apt_archive_names(lock["build_apt"]["packages"])
    require(receipt.get("apt_owned_cache_filenames") == apt_names,
            "APT owned cache filename receipt changed")
    for p in lock["build_apt"]["packages"]:
        verified_bytes(directory / "apt-archives" / apt_names[p["filename"]], p)
    require({p.name for p in (directory / "apt-archives").iterdir()}
            == set(apt_names.values()), "APT archive set changed")
    snapshot_binding(directory / "snapshot", lock["build_apt"]["snapshot"])
    return lock, receipt, {"registry_archives": len(registry), "registry_source_files": verified_count}


def prepare(lock_path, snapshot_dir, out, stage, caches=()):
    require(stage in ("locked-build", "tiktoken-lock"), "Unknown preparation stage")
    lock, raw = load_lock(lock_path)
    apt_names = apt_archive_names(lock["build_apt"]["packages"])
    out, snapshot_dir = out.absolute(), snapshot_dir.resolve()
    require(not out.exists() and not out.is_symlink(), "Use a fresh preparation directory")
    for source in (lock_path.resolve(), snapshot_dir, *(p.resolve() for p in caches)):
        require(not out.is_relative_to(source) and not source.is_relative_to(out),
                "Fresh output overlaps an input/cache")
    out.mkdir(parents=True)
    for name in ("archives", "sources", "wheels", "crates", "vendor", "snapshot", "apt-archives"):
        (out / name).mkdir()
    write_new(out / LOCK_FILENAME, raw)
    for pin in lock["build_apt"]["snapshot"]:
        write_new(out / "snapshot" / pin["filename"], verified_bytes(snapshot_dir / pin["filename"], pin))
    snapshot_binding(out / "snapshot", lock["build_apt"]["snapshot"])
    sources = [s for s in lock["sources"] if (s["name"] == "tiktoken") == (stage == "tiktoken-lock")]
    packages = lock["python_build_packages"] if stage == "locked-build" else []
    crates = lock["registry"] if stage == "locked-build" else []
    jobs = [(s["artifact"], out / "archives" / s["artifact"]["filename"]) for s in sources]
    jobs += [(p["artifact"], out / "wheels" / p["artifact"]["filename"]) for p in packages]
    jobs += [(p, out / "crates" / p["filename"]) for p in crates]
    for p in lock["build_apt"]["packages"]:
        local = apt_names[p["filename"]]
        jobs.append(({**p, "filename": local}, out / "apt-archives" / local))
    deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
    def acquire(job):
        pin, destination = job
        return {"path": destination.relative_to(out).as_posix(),
                **download(pin, destination, caches, deadline)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloads = list(pool.map(acquire, jobs))
    for source in sources:
        rows = archive_files(verified_bytes(out / "archives" / source["artifact"]["filename"], source["artifact"]),
                             source["archive_root"], output=out / "sources" / source["archive_root"])
        same_files(rows, source["files"])
    for p in packages:
        verify_wheel(out / "wheels" / p["artifact"]["filename"], p)
    registry_rows = [export_crate(out / "crates" / p["filename"], p,
                                 out / "vendor" / (p["name"] + "-" + p["version"])) for p in crates]
    write_new(out / "build-requirements.txt", requirement_text(packages))
    receipt = {"schema_version": 1, "status": "verified-inputs", "stage": stage,
               "recorded_at": datetime.now(timezone.utc).isoformat(), "lock_sha256": sha(raw),
               "sources": [s["name"] for s in sources], "downloads": downloads,
               "apt_owned_cache_filenames": apt_names,
               "registry_archives": len(crates), "registry_source_files": sum(len(p["files"]) for p in registry_rows),
               "registry_full_lock_union_not_target_active_count": True,
               "directory_source": "Unmodified original crates plus generated .cargo-checksum.json; independent archive SHA and full file checks are authoritative.",
               "cargo_executed": False, "source_backend_executed": False, "native_install_performed": False,
               "tiktoken_lock_resolved": False, "complete_four_component_runtime": False,
               "model_downloaded": False, "release_output": False}
    save_json(out / "RUST-PREPARED-INPUTS.json", receipt)
    verify_inputs(out)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=SCRIPT_DIR / LOCK_FILENAME)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--stage", choices=("locked-build", "tiktoken-lock"), default="locked-build")
    parser.add_argument("--cache", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        _, _, result = verify_inputs(args.verify)
    else:
        require(args.snapshot is not None and args.out is not None, "Preparation needs snapshot and new output")
        result = prepare(args.lock, args.snapshot, args.out, args.stage, tuple(args.cache))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
