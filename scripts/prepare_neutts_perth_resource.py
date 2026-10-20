#!/usr/bin/env python3
"""Prepare Perth's exact expanded-wheel resource lookup fix without admission."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "neutts_perth_resource_lock.json"
LOCK_SHA256 = "d7add801a9b2e2b384af032108e73a104cd85b0ccd4565c69b9ec7d5117762b6"
RECEIPT = "PERTH-RESOURCE-PREPARED.json"


class PreparationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise PreparationError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
            "Missing, linked, nonregular or oversized input: " + str(path))
    raw = path.read_bytes()
    require(len(raw) == info.st_size, "Input changed while reading")
    return raw


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def load_lock(path=None):
    raw = read_regular(path or ROOT / "scripts" / LOCK_NAME, 100_000)
    require(digest(raw) == LOCK_SHA256, "Reviewed Perth resource lock changed")
    lock = json.loads(raw)
    source = lock["source_catalog"]
    require(digest(read_regular(ROOT / source["path"], 1_000_000)) == source["sha256"],
            "Original public wheel catalog changed")
    return lock


def verify_wheel(path, lock, *, upstream):
    pin = lock["upstream_package"]["artifact"] if upstream else lock["derived_artifact"]
    ledger = lock["original_members"] if upstream else lock["derived_members"]
    raw = read_regular(path, pin["bytes"])
    require(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"], "Wheel identity changed")
    expected = {row["path"]: row for row in ledger}
    require(len(expected) == 28, "Reviewed wheel inventory changed")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) == len(expected) and {i.filename for i in infos} == set(expected),
                "Wheel has missing, duplicate or unexpected members")
        content = {}
        for item in infos:
            pin = expected[item.filename]
            require(not item.is_dir() and item.orig_filename == item.filename
                    and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                    and not item.flag_bits & 1
                    and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and item.file_size == pin["bytes"], "Invalid wheel member")
            body = archive.read(item)
            require(len(body) == pin["bytes"] and digest(body) == pin["sha256"],
                    "Wheel member differs from original or reviewed derivative: " + item.filename)
            content[item.filename] = body
    record = lock["upstream_package"]["wheel"]["record_member"]
    rows = list(csv.reader(io.StringIO(content[record].decode("utf-8"))))
    require(len(rows) == len(content) and all(len(row) == 3 for row in rows)
            and len({row[0] for row in rows}) == len(rows)
            and {row[0] for row in rows} == set(content), "Incomplete or ambiguous RECORD")
    for name, hashed, size in rows:
        if name == record:
            require(hashed == size == "", "Invalid RECORD self-entry")
        else:
            body = content[name]
            expected_hash = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip("=")
            require(hashed == expected_hash and size == str(len(body)), "Untruthful RECORD")
    return {"bytes": len(raw), "sha256": digest(raw), "members_verified": len(content)}


def apply_patch(before, patch, lock):
    pin = lock["patch"]
    require(len(before) == pin["before_bytes"] and digest(before) == pin["before_sha256"],
            "Original resource module changed")
    require(len(patch) == pin["bytes"] and digest(patch) == pin["sha256"], "Reviewed patch changed")
    lines = patch.splitlines(keepends=True)
    member = pin["member"].encode()
    require(lines[0] == b"--- a/" + member + b"\n"
            and lines[1] == b"+++ b/" + member + b"\n", "Patch target changed")
    match = re.fullmatch(rb"@@ -1,([0-9]+) \+1,([0-9]+) @@\n", lines[2])
    require(match is not None and all(line[:1] in (b" ", b"+", b"-") and line.endswith(b"\n")
                                      for line in lines[3:]), "Expected one complete source hunk")
    old = [line[1:] for line in lines[3:] if line[:1] in (b" ", b"-")]
    new = [line[1:] for line in lines[3:] if line[:1] in (b" ", b"+")]
    require(len(old) == int(match[1]) and len(new) == int(match[2]) and b"".join(old) == before,
            "Patch context differs")
    after = b"".join(new)
    require(len(after) == pin["after_bytes"] and digest(after) == pin["after_sha256"],
            "Patched resource module changed")
    return after


def derived_bytes(upstream, patch, lock):
    verify_wheel(upstream, lock, upstream=True)
    with zipfile.ZipFile(upstream) as archive:
        infos = archive.infolist()
        before = {i.filename: archive.read(i) for i in infos}
    content = dict(before)
    target = lock["patch"]["member"]
    record = lock["upstream_package"]["wheel"]["record_member"]
    content[target] = apply_patch(before[target], patch, lock)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name, _, _ in csv.reader(io.StringIO(before[record].decode())):
        if name == record:
            writer.writerow((name, "", ""))
        else:
            body = content[name]
            writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()).decode().rstrip("="), len(body)))
    content[record] = buffer.getvalue().encode()
    require(sorted(n for n in content if content[n] != before[n])
            == sorted(lock["patch"]["changed_members"]) == sorted((target, record)),
            "Unrelated original wheel member changed")
    output = io.BytesIO()
    # Stored members and fixed ZIP fields make the complete derivative repeatable.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for old in infos:
            item = zipfile.ZipInfo(old.filename, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.create_version = item.extract_version = 20
            item.external_attr = old.external_attr
            item.internal_attr = 0
            item.compress_type = zipfile.ZIP_STORED
            archive.writestr(item, content[old.filename])
    raw = output.getvalue()
    pin = lock["derived_artifact"]
    require(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"], "Derivative is not reproducible")
    return raw


def receipt_for(lock, original, derived):
    return {"schema": "neutts-perth-resource-prepared/v1", "status": "verified-inputs",
            "lock_sha256": LOCK_SHA256, "original_wheel": original, "derived_wheel": derived,
            "changed_members": lock["patch"]["changed_members"], "unchanged_original_members": 26,
            "metadata_and_dependency_declarations_unchanged": True,
            "embedded_public_checkpoint_preserved": True, "installed": False,
            "native_runtime_admitted": False, "model_execution": False, "release_output": False}


def verify_inputs(directory):
    require(directory.is_dir() and not directory.is_symlink(), "Invalid input directory")
    lock = load_lock(directory / LOCK_NAME)
    filename = lock["derived_artifact"]["filename"]
    expected = {LOCK_NAME, RECEIPT, "perth-resource-path.patch", filename, "upstream/" + filename}
    paths = list(directory.rglob("*"))
    require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in paths)
            and {p.relative_to(directory).as_posix() for p in paths if p.is_file()} == expected
            and {p.relative_to(directory).as_posix() for p in paths if p.is_dir()} == {"upstream"},
            "Prepared input inventory changed")
    original = verify_wheel(directory / "upstream" / filename, lock, upstream=True)
    derived = verify_wheel(directory / filename, lock, upstream=False)
    patch = read_regular(directory / "perth-resource-path.patch", lock["patch"]["bytes"])
    require((directory / filename).read_bytes() == derived_bytes(directory / "upstream" / filename, patch, lock),
            "Prepared wheel differs from the one-member patch")
    receipt = json.loads(read_regular(directory / RECEIPT, 100_000))
    require(receipt == receipt_for(lock, original, derived), "Preparation receipt changed")
    return receipt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PreparationError("Unexpected original-wheel redirect")


def prepare(out, wheel=None):
    lock = load_lock()
    require(not os.path.lexists(out) and out.absolute() == out.resolve(), "Use a fresh unlinked output path")
    patch = read_regular(ROOT / lock["patch"]["path"], lock["patch"]["bytes"])
    require(digest(patch) == lock["patch"]["sha256"], "Reviewed patch changed")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="perth-resource-", dir=out.parent) as temporary:
        staged = Path(temporary) / "inputs"
        (staged / "upstream").mkdir(parents=True)
        pin = lock["upstream_package"]["artifact"]
        original = staged / "upstream" / pin["filename"]
        if wheel is not None:
            verify_wheel(wheel, lock, upstream=True)
            shutil.copyfile(wheel, original)
        else:
            started = time.monotonic()
            with urllib.request.build_opener(NoRedirect()).open(pin["url"], timeout=30) as response:
                require(response.status == 200, "Unexpected original-wheel response")
                total = 0
                with original.open("xb") as stream:
                    while block := response.read(min(1024 * 1024, pin["bytes"] + 1 - total)):
                        total += len(block)
                        require(total <= pin["bytes"] and time.monotonic() - started < 120,
                                "Original-wheel download exceeded bound")
                        stream.write(block)
        original_proof = verify_wheel(original, lock, upstream=True)
        derived = staged / lock["derived_artifact"]["filename"]
        derived.write_bytes(derived_bytes(original, patch, lock))
        derived_proof = verify_wheel(derived, lock, upstream=False)
        (staged / "perth-resource-path.patch").write_bytes(patch)
        (staged / LOCK_NAME).write_bytes((ROOT / "scripts" / LOCK_NAME).read_bytes())
        (staged / RECEIPT).write_bytes(encoded(receipt_for(lock, original_proof, derived_proof)))
        verify_inputs(staged)
        staged.rename(out)
    return verify_inputs(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="Exact original public Perth wheel cache")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    result = verify_inputs(args.verify) if args.verify else prepare(args.out, args.wheel)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
