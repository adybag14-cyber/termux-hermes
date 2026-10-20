#!/usr/bin/env python3
"""Prepare the reviewed NeuCodec Hub download compatibility wheel; no model execution."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "neucodec_wheel_lock.json"
LOCK_SHA256 = "2bbd9b52fcd5c1c76a8f75d99f63f52ba5773586c55abcdb358949866f248023"
RECEIPT = "NEUCODEC-WHEEL-PREPARED.json"
MAX_ARCHIVE = 1_048_576
MAX_MEMBER = 65_536
MAX_TOTAL = 262_144
MODEL = "neucodec/model.py"
PATCH_TEST = "tests/test_hub_download_compat.py"
RECORD = "neucodec-0.0.4.dist-info/RECORD"


class PreparationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise PreparationError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def read_regular(path, limit):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
            "Missing, linked, nonregular or oversized input: " + str(path))
    raw = path.read_bytes()
    require(len(raw) == info.st_size, "Input changed while reading")
    return raw


def exact_file(path, pin):
    raw = read_regular(path, min(pin["bytes"], MAX_ARCHIVE))
    require(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"],
            "Pinned input identity changed: " + str(path))
    return raw


def safe_relative(name):
    require(isinstance(name, str) and name and "\0" not in name
            and "\\" not in name and ":" not in name,
            "Invalid archive path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name
            and all(part not in ("", ".", "..") for part in path.parts),
            "Unnormalized or escaped archive path")
    return name


def content_manifest(content):
    return [{"path": name, "bytes": len(raw), "sha256": digest(raw)}
            for name, raw in sorted(content.items())]


def load_lock(path=None):
    raw = read_regular(path or ROOT / "scripts" / LOCK_NAME, 100_000)
    require(digest(raw) == LOCK_SHA256, "Reviewed NeuCodec wheel lock changed")
    lock = json.loads(raw)
    catalog = lock["source_catalog"]
    require(digest(read_regular(ROOT / catalog["path"], 1_000_000)) == catalog["sha256"],
            "Original runtime catalog changed")
    metadata = json.loads(exact_file(ROOT / lock["pypi_metadata"]["path"], lock["pypi_metadata"]))
    wheel = lock["upstream_package"]["artifact"]
    rows = [x for x in metadata["urls"] if x["filename"] == wheel["filename"]]
    require(len(rows) == 1 and rows[0]["packagetype"] == "bdist_wheel"
            and not rows[0]["yanked"] and rows[0]["url"] == wheel["url"]
            and rows[0]["size"] == wheel["bytes"]
            and rows[0]["digests"]["sha256"] == wheel["sha256"],
            "Original official wheel identity changed")
    require(lock["schema"] == "neucodec-wheel-lock/v1"
            and lock["patch"]["path"] == "patches/next-stable/neucodec-hub1-download.patch"
            and lock["patch"]["source_targets"] == [MODEL, PATCH_TEST]
            and lock["patch"]["changed_wheel_members"] == [MODEL, RECORD]
            and lock["scope"] == {
                "source_patch_only": True, "metadata_and_dependency_declarations_unchanged": True,
                "backend_build_performed": False, "native_runtime_admitted": False,
                "model_download": False, "model_execution": False, "release_output": False},
            "Reviewed NeuCodec preparation scope changed")
    return lock


def verify_wheel(path, lock, *, upstream):
    pin = lock["upstream_package"]["artifact"] if upstream else lock["derived_artifact"]
    ledger = lock["original_members"] if upstream else lock["derived_members"]
    raw = exact_file(path, pin)
    expected = {safe_relative(row["path"]): row for row in ledger}
    require(len(expected) == len(ledger) == 20
            and all(0 <= row["bytes"] <= MAX_MEMBER for row in ledger)
            and sum(row["bytes"] for row in ledger) <= MAX_TOTAL,
            "Reviewed wheel inventory or finite bounds changed")
    content = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) == len(expected) and {i.filename for i in infos} == set(expected),
                "Wheel has missing, duplicate or unexpected members")
        for item in infos:
            row = expected[item.filename]
            require(not item.is_dir() and item.orig_filename == item.filename
                    and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                    and not item.flag_bits & 1
                    and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and item.file_size == row["bytes"], "Invalid wheel member")
            body = archive.read(item)
            require(len(body) == row["bytes"] and digest(body) == row["sha256"],
                    "Wheel member differs from original or reviewed derivative: " + item.filename)
            content[item.filename] = body
    rows = list(csv.reader(io.StringIO(content[RECORD].decode("utf-8"))))
    require(len(rows) == len(content) and all(len(row) == 3 for row in rows)
            and len({row[0] for row in rows}) == len(rows)
            and {row[0] for row in rows} == set(content),
            "Incomplete or ambiguous RECORD")
    for name, hashed, size in rows:
        if name == RECORD:
            require(hashed == size == "", "Invalid RECORD self-entry")
        else:
            body = content[name]
            expected_hash = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()).decode().rstrip("=")
            require(hashed == expected_hash and size == str(len(body)), "Untruthful RECORD")
    require(content_manifest(content) == ledger, "Wheel content ledger changed")
    return {"bytes": len(raw), "sha256": digest(raw), "members_verified": len(content)}


def source_contents(path, lock):
    raw = exact_file(path, lock["source_archive"])
    ledger = lock["original_source_members"]
    expected = {safe_relative(row["path"]): row for row in ledger}
    require(len(ledger) == len(expected) == 20
            and all(0 <= row["bytes"] <= MAX_MEMBER for row in ledger)
            and sum(row["bytes"] for row in ledger) <= MAX_TOTAL,
            "Original source inventory or bounds changed")
    prefix = "neucodec-0.0.4/"
    result, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for item in archive:
            require(len(result) < 20 and item.name.startswith(prefix), "Unexpected source archive member")
            name = safe_relative(item.name[len(prefix):])
            require(name in expected and name not in result and item.isfile()
                    and not item.linkname and item.mode == 0o644,
                    "Unreviewed, duplicate or nonregular source member")
            row = expected[name]
            require(item.size == row["bytes"] and 0 <= item.size <= MAX_MEMBER,
                    "Source member exceeds its exact finite bound")
            total += item.size
            require(total <= MAX_TOTAL, "Source archive exceeds total bound")
            stream = archive.extractfile(item)
            require(stream is not None, "Missing source payload")
            body = stream.read(item.size + 1)
            require(len(body) == item.size and digest(body) == row["sha256"],
                    "Original source member changed")
            result[name] = body
    require(content_manifest(result) == ledger, "Incomplete original source archive")
    return result


def _apply_block(before, lines, name, new_file):
    require(lines[0] == f"diff --git a/{name} b/{name}\n".encode(), "Patch target changed")
    cursor = 1
    if new_file:
        require(lines[cursor] == b"new file mode 100644\n", "New source mode changed")
        cursor += 1
    require(re.fullmatch(rb"index [0-9a-f]{7,40}\.\.[0-9a-f]{7,40}(?: 100644)?\n",
                         lines[cursor]) is not None, "Patch identity header changed")
    cursor += 1
    old_name = b"/dev/null" if new_file else b"a/" + name.encode()
    require(lines[cursor:cursor + 2] ==
            [b"--- " + old_name + b"\n", b"+++ b/" + name.encode() + b"\n"],
            "Patch original or destination path changed")
    cursor += 2
    original = before.splitlines(keepends=True)
    output, old_cursor, hunk_count = [], 0, 0
    while cursor < len(lines):
        match = re.fullmatch(rb"@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@[^\n]*\n",
                             lines[cursor])
        require(match is not None, "Invalid unified patch hunk")
        old_start, old_count = int(match[1]), int(match[2] or b"1")
        new_start, new_count = int(match[3]), int(match[4] or b"1")
        start = old_start - 1 if old_count else old_start
        require(old_cursor <= start <= len(original) and start + old_count <= len(original),
                "Overlapping or escaped patch source offset")
        output.extend(original[old_cursor:start])
        require(new_start == len(output) + 1, "Patch destination offset changed")
        cursor += 1
        old, new = [], []
        while cursor < len(lines) and not lines[cursor].startswith(b"@@ "):
            line = lines[cursor]
            require(line[:1] in (b" ", b"+", b"-") and line.endswith(b"\n"),
                    "Malformed patch context")
            if line[:1] in (b" ", b"-"):
                old.append(line[1:])
            if line[:1] in (b" ", b"+"):
                new.append(line[1:])
            cursor += 1
        require(len(old) == old_count and len(new) == new_count
                and old == original[start:start + old_count], "Patch context differs from original source")
        output.extend(new)
        old_cursor = start + old_count
        hunk_count += 1
    require(hunk_count == (1 if new_file else 7), "Reviewed patch hunk count changed")
    output.extend(original[old_cursor:])
    return b"".join(output)


def patched_sources(original, patch, lock):
    pin = lock["patch"]
    require(len(patch) == pin["bytes"] and digest(patch) == pin["sha256"], "Reviewed patch changed")
    require(content_manifest(original) == lock["original_source_members"], "Original patch sources changed")
    lines = patch.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(b"diff --git ")]
    require(len(starts) == 2 and starts[0] == 0, "Reviewed two-file patch structure changed")
    result = dict(original)
    result[MODEL] = _apply_block(original[MODEL], lines[:starts[1]], MODEL, False)
    require(PATCH_TEST not in original, "Patch test already exists in original source")
    result[PATCH_TEST] = _apply_block(b"", lines[starts[1]:], PATCH_TEST, True)
    require(content_manifest(result) == lock["patched_source_members"],
            "Patched source or added regression test changed")
    require({n for n in original if result[n] != original[n]} == {MODEL},
            "Unrelated original source changed")
    return result


def bind_original_source(upstream, source, lock):
    verify_wheel(upstream, lock, upstream=True)
    with zipfile.ZipFile(upstream) as archive:
        content = {i.filename: archive.read(i) for i in archive.infolist()}
    require({n for n in content if n.startswith("neucodec/")} ==
            {n for n in source if n.startswith("neucodec/")},
            "Original source and wheel package inventory differ")
    require(all(content[n] == source[n] for n in source if n.startswith("neucodec/")),
            "Original packaged Python source differs from sdist")
    require(content["neucodec-0.0.4.dist-info/METADATA"] == source["PKG-INFO"]
            and content["neucodec-0.0.4.dist-info/licenses/LICENSE"] == source["LICENSE"],
            "Original wheel metadata or license differs from sdist")
    return content


def derived_bytes(upstream, patched, lock):
    verify_wheel(upstream, lock, upstream=True)
    with zipfile.ZipFile(upstream) as archive:
        infos = archive.infolist()
        before = {i.filename: archive.read(i) for i in infos}
    content = dict(before)
    require(content_manifest(patched) == lock["patched_source_members"], "Unverified patched source")
    content[MODEL] = patched[MODEL]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name, _, _ in csv.reader(io.StringIO(before[RECORD].decode())):
        if name == RECORD:
            writer.writerow((name, "", ""))
        else:
            body = content[name]
            writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()).decode().rstrip("="), len(body)))
    content[RECORD] = buffer.getvalue().encode()
    require(sorted(n for n in content if content[n] != before[n]) == sorted((MODEL, RECORD)),
            "Unrelated original wheel member changed")
    output = io.BytesIO()
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
    require(len(raw) == lock["derived_artifact"]["bytes"]
            and digest(raw) == lock["derived_artifact"]["sha256"], "Derivative is not reproducible")
    return raw


def receipt_for(lock, original, derived):
    return {"schema": "neucodec-wheel-prepared/v1", "status": "verified-inputs",
            "lock_sha256": LOCK_SHA256, "original_wheel": original, "derived_wheel": derived,
            "source_archive": lock["source_archive"],
            "original_source_files": 20, "packaged_original_python_files": 16,
            "patched_source_files": 21, "unchanged_original_wheel_members": 18,
            "changed_wheel_members": [MODEL, RECORD],
            "original_source_and_wheel_metadata_identical": True,
            "full_reviewed_patch_and_added_tests_verified": True,
            "metadata_and_dependency_declarations_unchanged": True,
            "backend_build_performed": False, "installed": False,
            "native_runtime_admitted": False, "model_download": False,
            "model_execution": False, "release_output": False}


def verify_inputs(directory):
    require(directory.is_dir() and not directory.is_symlink()
            and directory.absolute() == directory.resolve(), "Invalid input directory")
    lock = load_lock(directory / LOCK_NAME)
    filename = lock["derived_artifact"]["filename"]
    original_filename = lock["source_archive"]["filename"]
    meta_name = Path(lock["pypi_metadata"]["path"]).name
    expected = {LOCK_NAME, RECEIPT, "neucodec-hub1-download.patch", filename,
                "upstream/" + filename, "upstream/" + original_filename, "upstream/" + meta_name}
    expected.update("source/" + row["path"] for row in lock["patched_source_members"])
    dirs = {p.as_posix() for name in expected for p in PurePosixPath(name).parents
            if p.as_posix() != "."}
    paths = list(directory.rglob("*"))
    require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in paths)
            and {p.relative_to(directory).as_posix() for p in paths if p.is_file()} == expected
            and {p.relative_to(directory).as_posix() for p in paths if p.is_dir()} == dirs,
            "Prepared input inventory changed")
    exact_file(directory / "upstream" / meta_name, lock["pypi_metadata"])
    original = verify_wheel(directory / "upstream" / filename, lock, upstream=True)
    source = source_contents(directory / "upstream" / original_filename, lock)
    bind_original_source(directory / "upstream" / filename, source, lock)
    patch = exact_file(directory / "neucodec-hub1-download.patch", lock["patch"])
    patched = patched_sources(source, patch, lock)
    for name, raw in patched.items():
        require(read_regular(directory / "source" / name, MAX_MEMBER) == raw,
                "Prepared patched source differs: " + name)
    derived = verify_wheel(directory / filename, lock, upstream=False)
    require((directory / filename).read_bytes() ==
            derived_bytes(directory / "upstream" / filename, patched, lock),
            "Prepared wheel differs from reviewed source patch")
    receipt = json.loads(read_regular(directory / RECEIPT, 100_000))
    require(receipt == receipt_for(lock, original, derived), "Preparation receipt changed")
    return receipt


def prepare(out, wheel=None):
    lock = load_lock()
    require(not os.path.lexists(out) and out.absolute() == out.resolve(),
            "Use a fresh unlinked output path")
    original_path = wheel if wheel is not None else ROOT / lock["original_wheel_path"]
    original = verify_wheel(original_path, lock, upstream=True)
    source_path = ROOT / lock["source_archive"]["path"]
    source = source_contents(source_path, lock)
    bind_original_source(original_path, source, lock)
    patch = exact_file(ROOT / lock["patch"]["path"], lock["patch"])
    patched = patched_sources(source, patch, lock)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="neucodec-wheel-", dir=out.parent) as temporary:
        staged = Path(temporary) / "inputs"
        (staged / "upstream").mkdir(parents=True)
        shutil.copyfile(original_path, staged / "upstream" / lock["upstream_package"]["artifact"]["filename"])
        shutil.copyfile(source_path, staged / "upstream" / lock["source_archive"]["filename"])
        meta = ROOT / lock["pypi_metadata"]["path"]
        shutil.copyfile(meta, staged / "upstream" / meta.name)
        for name, raw in patched.items():
            target = staged / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        derived = staged / lock["derived_artifact"]["filename"]
        derived.write_bytes(derived_bytes(original_path, patched, lock))
        derived_proof = verify_wheel(derived, lock, upstream=False)
        (staged / "neucodec-hub1-download.patch").write_bytes(patch)
        (staged / LOCK_NAME).write_bytes((ROOT / "scripts" / LOCK_NAME).read_bytes())
        (staged / RECEIPT).write_bytes(encoded(receipt_for(lock, original, derived_proof)))
        verify_inputs(staged)
        staged.rename(out)
    return verify_inputs(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="Optional exact original universal-wheel cache")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    result = verify_inputs(args.verify) if args.verify else prepare(args.out, args.wheel)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
