#!/usr/bin/env python3
"""Prepare exact retained Termux APT inputs without executing or admitting them.

The original foundation and compiler pins remain authoritative. The retained
InRelease binds the original index; its OpenPGP signature is checked separately
by native APT against the Termux image's trust store.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "https://packages.termux.dev/apt/termux-main/"
FOUNDATION_PATH = "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv"
FOUNDATION_SHA256 = "7ad635d7f1ce1157c7f3b3d7808eaf113c8bb77c4e99a8fe30b6b155faf04c5e"
COMPILER_LOCK_SHA256 = "a06e595179fad6f437ca95210d685beb339baa0867cd527dba5f5083d94b36ce"
COMPILER_TSV_SHA256 = "83e67a558d1322b8ea55c2d3d885e0dde9725e54694faa490f3ea16064978af3"
SNAPSHOT = {
    "InRelease": {"bytes": 14016, "sha256": "249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901"},
    "Packages.gz": {"bytes": 727968, "sha256": "dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6"},
}
PACKAGES_SHA256 = "95cf6e3b7cf347a81aef44e45199724b7a6cd21c29be7611cc1ac5ebaf2640e1"
PACKAGES_BYTES = 1867286
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 900
FIELDS = ("name", "version", "architecture", "sha256", "bytes", "filename")


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular_bytes(path, limit):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
            "Missing, linked, nonregular or oversized input: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == info.st_size and len(raw) <= limit, "Input changed while reading")
    return raw


def verify_file(path, pin):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == pin["bytes"],
            "Archive is linked, nonregular or has the wrong size: " + str(path))
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    require(actual == pin["sha256"] and path.stat().st_size == pin["bytes"],
            "Archive SHA256 differs: " + str(path))
    return actual


def archive_name(pin, *, native=False):
    name, version, arch = (pin[k] for k in FIELDS[:3])
    require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name)
            and isinstance(version, str) and re.fullmatch(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+~-]*", version)
            and arch in ("aarch64", "all"), "Invalid frozen package identity")
    original = name + "_" + version + "_" + arch + ".deb"
    path = pin["filename"]
    require(isinstance(path, str) and path.startswith("pool/main/") and "\\" not in path
            and "%" not in path and PurePosixPath(path).as_posix() == path
            and ".." not in PurePosixPath(path).parts and PurePosixPath(path).name == original,
            "Archive path differs from the signed identity")
    require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_ARCHIVE_BYTES
            and re.fullmatch(r"[a-f0-9]{64}", pin["sha256"]), "Invalid frozen archive size/hash")
    return original.replace(":", "%3a" if native else "%3A")


def parse_tsv(raw):
    require(raw.endswith(b"\n") and b"\r" not in raw and b"\0" not in raw, "Noncanonical package TSV")
    pins = []
    for line in raw.decode("ascii").splitlines():
        cells = line.split("\t")
        require(len(cells) == len(FIELDS), "Invalid package TSV fields")
        pin = dict(zip(FIELDS, cells, strict=True))
        require(re.fullmatch(r"[1-9][0-9]*", pin["bytes"]), "Invalid package size")
        pin["bytes"] = int(pin["bytes"])
        archive_name(pin)
        pins.append(pin)
    require(pins and len({p["name"] for p in pins}) == len(pins), "Duplicate/empty pinned package set")
    names = [archive_name(p) for p in pins]
    require(len({n.casefold() for n in names}) == len(names), "Aliased archive filenames")
    return pins


def pins_tsv(pins):
    return "".join("\t".join(str(p[k]) for k in FIELDS) + "\n" for p in pins).encode("ascii")


def load_pins(root, include_compiler):
    foundation = regular_bytes(root / FOUNDATION_PATH, 100000)
    require(digest(foundation) == FOUNDATION_SHA256, "Original foundation TSV changed")
    pins = parse_tsv(foundation)
    require(len(pins) == 122, "Original foundation count changed")
    # Preserve the original embedded experiment lock as a second exact oracle.
    driver = regular_bytes(root / "scripts/compatibility_probe_neutts.sh", 100000).decode()
    embedded = driver.split("<<'PINS'\n", 1)[1].split("\nPINS", 1)[0].encode() + b"\n"
    require(embedded == foundation, "Embedded foundation pins differ from original evidence")
    compiler = None
    if include_compiler:
        raw = regular_bytes(root / "scripts/neutts_native_sources_lock.json", 100000)
        require(digest(raw) == COMPILER_LOCK_SHA256, "Original compiler lock changed")
        rows = json.loads(raw)["build_apt"]["packages"]
        compiler = pins_tsv(rows)
        require(digest(compiler) == COMPILER_TSV_SHA256, "Original compiler TSV changed")
        compiler_pins = parse_tsv(compiler)
        require(len(compiler_pins) == 44, "Original compiler count changed")
        union = {p["name"]: p for p in pins}
        for pin in compiler_pins:
            require(pin["name"] not in union or union[pin["name"]] == pin, "Compiler/foundation identity conflict")
            union[pin["name"]] = pin
        require(len(union) == 141, "Reviewed compiler addition count changed")
        pins = sorted(union.values(), key=lambda p: p["name"])
    require(sum(p["bytes"] for p in pins) <= MAX_TOTAL_BYTES, "Prepared archive set exceeds bound")
    return pins, foundation, compiler


def parse_packages(raw):
    """Keep multi-version records, rejecting duplicate fields and identities."""
    require(len(raw) <= 32_000_000 and b"\0" not in raw and b"\r" not in raw, "Invalid package index")
    records = {}
    for paragraph in raw.decode("utf-8").split("\n\n"):
        if not paragraph.strip():
            continue
        row, previous = {}, None
        for line in paragraph.splitlines():
            if line.startswith((" ", "\t")):
                require(previous is not None, "Index continuation has no field")
                row[previous] += "\n" + line
                continue
            require(": " in line, "Malformed package index field")
            key, value = line.split(": ", 1)
            require(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key)
                    and key.lower() not in {k.lower() for k in row}, "Duplicate/malformed package index field")
            row[key], previous = value, key
        require(all(row.get(k) for k in ("Package", "Version", "Architecture")), "Incomplete package record")
        identity = (row["Package"], row["Version"], row["Architecture"])
        require(identity not in records, "Duplicate package identity in signed index")
        records[identity] = row
    return records


def verify_selected_index(raw, pins):
    records = parse_packages(raw)
    for pin in pins:
        selected = records.get((pin["name"], pin["version"], pin["architecture"]))
        require(selected is not None, "Original package identity absent from retained signed index: " + pin["name"])
        expected = {"Filename": pin["filename"], "SHA256": pin["sha256"], "Size": str(pin["bytes"])}
        require(all(selected.get(k) == v for k, v in expected.items()),
                "Original archive identity differs from signed index: " + pin["name"])
    return len(pins)


def verify_snapshot(snapshot, pins):
    raw = {}
    for name, pin in SNAPSHOT.items():
        raw[name] = regular_bytes(snapshot / name, pin["bytes"])
        require(len(raw[name]) == pin["bytes"] and digest(raw[name]) == pin["sha256"], "Retained snapshot bytes differ")
    active, bindings = False, []
    for line in raw["InRelease"].decode("ascii").splitlines():
        if line == "SHA256:":
            active = True
            continue
        if active and line and not line[0].isspace():
            active = False
        if active:
            match = re.fullmatch(r"\s+([a-f0-9]{64})\s+([0-9]+)\s+(\S+)", line)
            if match and match[3] == "main/binary-aarch64/Packages.gz":
                bindings.append((match[1], int(match[2])))
    require(bindings == [(SNAPSHOT["Packages.gz"]["sha256"], SNAPSHOT["Packages.gz"]["bytes"])],
            "InRelease does not bind the original compressed index")
    with gzip.GzipFile(fileobj=io.BytesIO(raw["Packages.gz"])) as stream:
        packages = stream.read(PACKAGES_BYTES + 1)
    require(len(packages) == PACKAGES_BYTES and digest(packages) == PACKAGES_SHA256,
            "Expanded retained package index differs")
    verify_selected_index(packages, pins)
    return raw


class HTTPSOnly(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        require(urlsplit(newurl).scheme == "https", "Insecure archive redirect")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def acquire_archive(pin, target, caches, *, opener=None):
    filename = archive_name(pin)
    require(target.name == filename and not target.exists(), "Invalid owned archive destination")
    for cache in caches:
        require(cache.is_dir() and not cache.is_symlink(), "Missing or linked retained archive cache")
        candidate = cache / filename
        # A present invalid cache item is a failure, never a reason to silently
        # substitute current origin bytes or a different version.
        if os.path.lexists(candidate):
            verify_file(candidate, pin)
            shutil.copyfile(candidate, target)
            verify_file(target, pin)
            return {"filename": filename, "origin_url": ORIGIN + pin["filename"],
                    "method": "verified-retained-cache", "cache_path": str(candidate),
                    "bytes": pin["bytes"], "sha256": pin["sha256"]}
    url = ORIGIN + pin["filename"]
    client = opener or build_opener(HTTPSOnly())
    started = time.monotonic()
    with client.open(Request(url, headers={"User-Agent": "Hermes-exact-Termux-preparation/1"}), timeout=45) as response:
        require(response.status == 200 and urlsplit(response.geturl()).scheme == "https", "Unexpected archive response")
        advertised = response.headers.get("Content-Length")
        require(advertised is None or advertised == str(pin["bytes"]), "Archive response length differs")
        total = 0
        with target.open("xb") as stream:
            while block := response.read(min(1024 * 1024, pin["bytes"] + 1 - total)):
                total += len(block)
                require(total <= pin["bytes"], "Archive exceeded pinned byte bound")
                require(time.monotonic() - started <= MAX_DOWNLOAD_SECONDS, "Archive download exceeded deadline")
                stream.write(block)
        require(total == pin["bytes"], "Incomplete original archive download")
        effective_url = response.geturl()
    verify_file(target, pin)
    return {"filename": filename, "origin_url": url, "effective_url": effective_url,
            "method": "original-https-archive", "bytes": pin["bytes"], "sha256": pin["sha256"]}


def prepare(out, caches, include_compiler=False, *, root=ROOT):
    require(not os.path.lexists(out), "Use a new APT preparation directory")
    pins, foundation, compiler = load_pins(root, include_compiler)
    raw_snapshot = verify_snapshot(root / "audit/neutts-runtime-index-20261017", pins)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="neutts-apt-", dir=out.parent) as temporary:
        staged = Path(temporary) / "inputs"
        (staged / "snapshot").mkdir(parents=True)
        (staged / "apt-archives").mkdir()
        for name, raw in raw_snapshot.items():
            (staged / "snapshot" / name).write_bytes(raw)
        (staged / "foundation.tsv").write_bytes(foundation)
        if compiler is not None:
            (staged / "compiler.tsv").write_bytes(compiler)
        (staged / "ARCHIVES.tsv").write_bytes(pins_tsv(pins))
        with ThreadPoolExecutor(max_workers=6) as pool:
            downloads = list(pool.map(
                lambda pin: acquire_archive(pin, staged / "apt-archives" / archive_name(pin), caches), pins))
        receipt = {
            "schema": "neutts-frozen-apt-preparation/v1", "status": "verified-original-inputs",
            "foundation_packages": 122, "compiler_packages": 44 if include_compiler else 0,
            "archive_count": len(pins), "archive_bytes": sum(p["bytes"] for p in pins),
            "foundation_tsv_sha256": FOUNDATION_SHA256,
            "compiler_tsv_sha256": COMPILER_TSV_SHA256 if include_compiler else None,
            "snapshot": SNAPSHOT, "packages_uncompressed_sha256": PACKAGES_SHA256,
            "selected_signed_index_records_verified": len(pins), "downloads": downloads,
            "host_openpgp_verified": False, "native_apt_authentication_required": True,
            "package_install_performed": False, "pin_changes": False, "release_output": False,
        }
        (staged / "APT-PREPARED-INPUTS.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        staged.rename(out)
    verify_inputs(out, root=root)
    return receipt


def verify_receipt(receipt, pins, compiler):
    expected_keys = {
        "schema", "status", "foundation_packages", "compiler_packages", "archive_count", "archive_bytes",
        "foundation_tsv_sha256", "compiler_tsv_sha256", "snapshot", "packages_uncompressed_sha256",
        "selected_signed_index_records_verified", "downloads", "host_openpgp_verified",
        "native_apt_authentication_required", "package_install_performed", "pin_changes", "release_output",
    }
    require(isinstance(receipt, dict) and set(receipt) == expected_keys
            and receipt["schema"] == "neutts-frozen-apt-preparation/v1"
            and receipt["status"] == "verified-original-inputs"
            and receipt["host_openpgp_verified"] is False
            and receipt["native_apt_authentication_required"] is True
            and receipt["package_install_performed"] is False
            and receipt["pin_changes"] is False and receipt["release_output"] is False,
            "Invalid APT preparation receipt")
    require(receipt["foundation_packages"] == 122
            and type(receipt["compiler_packages"]) is int and receipt["compiler_packages"] == (44 if compiler else 0)
            and receipt["archive_count"] == len(pins)
            and receipt["archive_bytes"] == sum(p["bytes"] for p in pins)
            and receipt["foundation_tsv_sha256"] == FOUNDATION_SHA256
            and receipt["compiler_tsv_sha256"] == (COMPILER_TSV_SHA256 if compiler else None)
            and receipt["snapshot"] == SNAPSHOT
            and receipt["packages_uncompressed_sha256"] == PACKAGES_SHA256
            and receipt["selected_signed_index_records_verified"] == len(pins),
            "Prepared archive receipt differs")
    rows = receipt["downloads"]
    require(isinstance(rows, list) and len(rows) == len(pins), "Incomplete/extra download receipt")
    expected = {archive_name(p): p for p in pins}
    seen = set()
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("filename"), str)
                and row["filename"] in expected and row["filename"] not in seen,
                "Missing, duplicate or unreviewed download receipt identity")
        seen.add(row["filename"])
        pin = expected[row["filename"]]
        common = {"filename", "origin_url", "method", "bytes", "sha256"}
        require(row.get("bytes") == pin["bytes"] and row.get("sha256") == pin["sha256"]
                and row.get("origin_url") == ORIGIN + pin["filename"],
                "Download receipt differs from original signed archive")
        if row.get("method") == "verified-retained-cache":
            path = row.get("cache_path")
            require(set(row) == common | {"cache_path"} and isinstance(path, str)
                    and 0 < len(path) <= 4096 and all(ord(c) >= 32 for c in path),
                    "Invalid descriptive retained-cache receipt")
        else:
            require(row.get("method") == "original-https-archive" and set(row) == common | {"effective_url"},
                    "Unreviewed archive acquisition method")
            url = row["effective_url"]
            require(isinstance(url, str) and 0 < len(url) <= 8192 and all(ord(c) >= 32 for c in url),
                    "Invalid descriptive effective URL")
            parsed = urlsplit(url)
            require(parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password,
                    "Download receipt effective URL is not HTTPS")


def verify_inputs(directory, *, root=ROOT):
    require(directory.is_dir() and not directory.is_symlink(), "Missing or linked prepared directory")
    receipt = json.loads(regular_bytes(directory / "APT-PREPARED-INPUTS.json", 1_000_000))
    require(receipt.get("schema") == "neutts-frozen-apt-preparation/v1"
            and receipt.get("status") == "verified-original-inputs"
            and receipt.get("compiler_packages") in (0, 44)
            and receipt.get("host_openpgp_verified") is False
            and receipt.get("native_apt_authentication_required") is True
            and receipt.get("pin_changes") is False, "Invalid APT preparation receipt")
    pins, foundation, compiler = load_pins(root, receipt["compiler_packages"] == 44)
    expected = {"snapshot", "apt-archives", "foundation.tsv", "ARCHIVES.tsv", "APT-PREPARED-INPUTS.json"}
    if compiler is not None:
        expected.add("compiler.tsv")
        require(regular_bytes(directory / "compiler.tsv", 100000) == compiler, "Prepared compiler pins changed")
    require({p.name for p in directory.iterdir()} == expected, "Prepared input layout changed")
    require(regular_bytes(directory / "foundation.tsv", 100000) == foundation
            and regular_bytes(directory / "ARCHIVES.tsv", 100000) == pins_tsv(pins), "Prepared archive pins changed")
    for name in ("snapshot", "apt-archives"):
        require((directory / name).is_dir() and not (directory / name).is_symlink(), "Linked prepared subdirectory")
    require({p.name for p in (directory / "snapshot").iterdir()} == set(SNAPSHOT), "Snapshot inventory changed")
    verify_snapshot(directory / "snapshot", pins)
    require({p.name for p in (directory / "apt-archives").iterdir()} == {archive_name(p) for p in pins},
            "Prepared archive inventory changed")
    verify_receipt(receipt, pins, compiler is not None)
    for pin in pins:
        verify_file(directory / "apt-archives" / archive_name(pin), pin)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, action="append", default=[])
    parser.add_argument("--include-compiler", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    receipt = verify_inputs(args.verify) if args.verify else prepare(args.out, args.cache, args.include_compiler)
    print(json.dumps({k: receipt[k] for k in ("status", "archive_count", "archive_bytes")}, sort_keys=True))


if __name__ == "__main__":
    main()
