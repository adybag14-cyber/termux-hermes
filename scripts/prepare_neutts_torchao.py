#!/usr/bin/env python3
"""Prepare an exact TorchAO wheel with one reviewed lazy optional SDPA import."""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import time
import urllib.request
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_NAME = "neutts_torchao_component_lock.json"
LOCK_SHA256 = "10017cbb4992011143a6928b1beb09a647d6c14c9ec479d0c89e9a6f35d40de4"
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


def verify_wheel(path, lock, *, upstream=False):
    package = lock["upstream_package"] if upstream else lock["package"]
    sources = lock["upstream_source_members"] if upstream else lock["source_members"]
    core = helper("prepare_neutts_core_python.py", lock)
    proof = core.verify_wheel(path, package)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            require(".data/" not in item.filename
                    and not item.filename.endswith((".pyc", ".pth")),
                    "Unexpected installation scheme or executable import hook")
            require(not archive.read(item).startswith(b"\x7fELF"),
                    "Pure TorchAO experiment cannot contain an ELF payload")
        for source in sources:
            raw = archive.read(source["path"])
            require(len(raw) == source["bytes"]
                    and hashlib.sha256(raw).hexdigest() == source["sha256"],
                    "Reviewed TorchAO source member changed")
    return proof


def read_patch(path, lock):
    pin = lock["patch"]
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"],
            "Reviewed TorchAO patch changed")
    return path.read_bytes()


def apply_member_patch(before, patch, lock):
    """Apply the pinned single-file, full-context hunk without invoking a shell."""
    pin = lock["patch"]
    require(len(patch) == pin["bytes"] and hashlib.sha256(patch).hexdigest() == pin["sha256"],
            "Reviewed TorchAO patch changed")
    require(len(before) == pin["before_bytes"]
            and hashlib.sha256(before).hexdigest() == pin["before_sha256"],
            "Original TorchAO patch target changed")
    lines = patch.splitlines(keepends=True)
    member = pin["member"].encode("utf-8")
    require(len(lines) >= 4 and lines[0] == b"--- a/" + member + b"\n"
            and lines[1] == b"+++ b/" + member + b"\n",
            "Patch must target the one reviewed source member")
    match = re.fullmatch(rb"@@ -1,([0-9]+) \+1,([0-9]+) @@\n", lines[2])
    require(match is not None, "Patch must contain one full-context hunk")
    body = lines[3:]
    require(all(line[:1] in (b" ", b"+", b"-") and line.endswith(b"\n") for line in body),
            "Patch has additional hunks or unsupported lines")
    old_lines = [line[1:] for line in body if line[:1] in (b" ", b"-")]
    new_lines = [line[1:] for line in body if line[:1] in (b" ", b"+")]
    require(len(old_lines) == int(match.group(1)) and len(new_lines) == int(match.group(2))
            and b"".join(old_lines) == before, "Patch context differs from the original member")
    after = b"".join(new_lines)
    require(len(after) == pin["after_bytes"]
            and hashlib.sha256(after).hexdigest() == pin["after_sha256"],
            "Patched TorchAO member differs from its reviewed bytes")
    return after


def patched_wheel_bytes(upstream, lock, patch_path):
    """Preserve member bytes except the one source file and its truthful RECORD."""
    verify_wheel(upstream, lock, upstream=True)
    patch = read_patch(patch_path, lock)
    target = lock["patch"]["member"]
    record_name = lock["upstream_package"]["wheel"]["record_member"]
    with zipfile.ZipFile(upstream) as archive:
        infos = archive.infolist()
        before = {item.filename: archive.read(item) for item in infos}
        content = dict(before)
        content[target] = apply_member_patch(before[target], patch, lock)
        rows = list(csv.reader(io.StringIO(before[record_name].decode("utf-8"))))
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        for name, _, _ in rows:
            if name == record_name:
                writer.writerow((name, "", ""))
            else:
                raw = content[name]
                digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
                writer.writerow((name, "sha256=" + digest, str(len(raw))))
        content[record_name] = buffer.getvalue().encode("utf-8")
        changed = sorted(name for name in content if content[name] != before[name])
        require(changed == sorted(lock["patch"]["changed_members"])
                == sorted((target, record_name)), "Wheel patch changed unrelated member bytes")
        output = io.BytesIO()
        # Stored members and explicit metadata avoid compressor/version/host drift.
        # This changes ZIP container encoding, not the other 346 regular files.
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as rebuilt:
            for old in infos:
                item = zipfile.ZipInfo(old.filename, date_time=(1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.create_version = item.extract_version = 20
                item.external_attr = old.external_attr
                item.internal_attr = 0
                item.compress_type = zipfile.ZIP_STORED
                rebuilt.writestr(item, content[old.filename])
    return output.getvalue()


def verify_inputs(inputs):
    lock = load_lock(inputs / LOCK_NAME)
    original_name = "upstream/" + lock["upstream_package"]["artifact"]["filename"]
    expected = {LOCK_NAME, RECEIPT_NAME, lock["package"]["artifact"]["filename"],
                original_name, lock["patch"]["input_filename"]}
    require(inputs.is_dir() and not inputs.is_symlink(), "Invalid prepared input directory")
    paths = list(inputs.rglob("*"))
    require(all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in paths)
            and {p.relative_to(inputs).as_posix() for p in paths if p.is_file()} == expected
            and {p.relative_to(inputs).as_posix() for p in paths if p.is_dir()} == {"upstream"},
            "Prepared directory must contain exactly the original wheel, patch, output wheel, lock and receipt")
    wheel = inputs / lock["package"]["artifact"]["filename"]
    upstream = inputs / original_name
    upstream_proof = verify_wheel(upstream, lock, upstream=True)
    proof = verify_wheel(wheel, lock)
    reconstructed = patched_wheel_bytes(upstream, lock, inputs / lock["patch"]["input_filename"])
    require(wheel.read_bytes() == reconstructed, "Prepared wheel does not reproduce the reviewed patch")
    receipt = read_json(inputs / RECEIPT_NAME)
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "verified-inputs"
            and receipt.get("lock_sha256") == LOCK_SHA256
            and receipt.get("wheel") == proof and receipt.get("upstream_wheel") == upstream_proof
            and receipt.get("patch") == lock["patch"]
            and receipt.get("source_members") == lock["source_members"]
            and receipt.get("all_other_original_member_bytes_preserved") is True
            and receipt.get("metadata_and_dependency_declarations_unchanged") is True
            and receipt.get("installed") is False
            and receipt.get("model_downloaded") is False
            and receipt.get("production_admission_changed") is False
            and receipt.get("release_output") is False,
            "Prepared input receipt differs from its verified wheel and patch")
    return lock, wheel, proof


def prepare(out, wheel=None, patch=None):
    lock = load_lock()
    require(not out.exists() and not out.is_symlink(), "Use a new input directory")
    patch = patch or SCRIPT_DIR.parent / lock["patch"]["path"]
    patch_raw = read_patch(patch, lock)
    if wheel is not None:
        verify_wheel(wheel, lock, upstream=True)
    out.mkdir(parents=True)
    (out / "upstream").mkdir()
    upstream = out / "upstream" / lock["upstream_package"]["artifact"]["filename"]
    if wheel is None:
        core = helper("prepare_neutts_core_python.py", lock)
        opener = urllib.request.build_opener(core.NoRedirect())
        core.download_file(lock["upstream_package"]["artifact"], upstream, opener,
                           time.monotonic() + 120)
    else:
        with upstream.open("xb") as stream:
            stream.write(wheel.read_bytes())
    patch_copy = out / lock["patch"]["input_filename"]
    with patch_copy.open("xb") as stream:
        stream.write(patch_raw)
    destination = out / lock["package"]["artifact"]["filename"]
    output = patched_wheel_bytes(upstream, lock, patch_copy)
    with destination.open("xb") as stream:
        stream.write(output)
    proof = verify_wheel(destination, lock)
    upstream_proof = verify_wheel(upstream, lock, upstream=True)
    with (out / LOCK_NAME).open("xb") as stream:
        stream.write((SCRIPT_DIR / LOCK_NAME).read_bytes())
    receipt = {"schema_version": 1, "status": "verified-inputs",
               "captured_utc": datetime.now(timezone.utc).isoformat(),
               "lock_sha256": LOCK_SHA256, "wheel": proof, "upstream_wheel": upstream_proof,
               "patch": lock["patch"], "source_members": lock["source_members"],
               "all_other_original_member_bytes_preserved": True,
               "metadata_and_dependency_declarations_unchanged": True,
               "installed": False, "model_downloaded": False,
               "production_admission_changed": False, "release_output": False}
    save_new(out / RECEIPT_NAME, receipt)
    verify_inputs(out)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, help="Optional already verified original upstream wheel")
    parser.add_argument("--patch", type=Path, help="Optional exact reviewed single-member patch")
    args = parser.parse_args(argv)
    receipt = prepare(args.out, args.wheel, args.patch)
    print(json.dumps({"status": receipt["status"], "lock_sha256": LOCK_SHA256,
                      "upstream_wheel_sha256": receipt["upstream_wheel"]["artifact"]["sha256"],
                      "wheel_sha256": receipt["wheel"]["artifact"]["sha256"],
                      "patch_sha256": receipt["patch"]["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
