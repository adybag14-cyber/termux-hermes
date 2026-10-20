#!/usr/bin/env python3
"""Prepare pinned NeuTTS source with an explicit offline eSpeak hook; never install."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_SHA256 = "cbf1bdba474ee75258da9ad5092b9cee4833d8a0776dfd7c22f18c0e08d211ea"
SUPPORT_SHA256 = "7e4abf6794f848d399d15a877e9c8a74db1a44ba5e87ceb898d5d4777169f744"


def support():
    path = SCRIPT_DIR / "prepare_neutts_native_sources.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != SUPPORT_SHA256:
        raise RuntimeError("Reviewed source verification helper changed")
    spec = importlib.util.spec_from_file_location("_neutts_engine_source_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lock():
    helper = support()
    raw = helper.read_regular(SCRIPT_DIR / "neutts_engine_source_lock.json", 20000)
    helper.require(helper.digest(raw) == LOCK_SHA256, "NeuTTS engine source lock differs")
    lock = json.loads(raw)
    helper.require(lock["schema_version"] == 1, "Unsupported engine source schema")
    espeak = lock["espeak_source_lock"]
    espeak_raw = helper.read_regular(SCRIPT_DIR.parent / espeak["path"], 20000)
    helper.require(helper.digest(espeak_raw) == espeak["sha256"], "Pinned eSpeak source lock differs")
    return lock, raw


def extract_source(archive_path, destination, pin):
    helper = support()
    artifact = pin["artifact"]
    raw = helper.read_regular(archive_path, artifact["bytes"])
    helper.require(len(raw) == artifact["bytes"] and helper.digest(raw) == artifact["sha256"],
                   "NeuTTS source archive differs")
    helper.require(not destination.exists() and not destination.is_symlink(), "Fresh source directory required")
    destination.mkdir(parents=True)
    rows, names, total = [], set(), 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for entry in archive:
            helper.require(entry.name not in names, "Duplicate source archive member")
            names.add(entry.name)
            helper.require(entry.isdir() or entry.isfile(), "Unexpected source link or special file")
            root, separator, name = entry.name.partition("/")
            helper.require(root == pin["root"], "Unexpected source archive root")
            if not separator:
                helper.require(entry.isdir(), "Invalid source archive root")
                continue
            relative = helper.safe_path(name)
            if entry.isdir():
                continue
            helper.require(0 <= entry.size <= helper.MAX_FILE_BYTES, "Oversized source member")
            total += entry.size
            helper.require(total <= pin["manifest"]["bytes"], "Oversized source tree")
            stream = archive.extractfile(entry)
            helper.require(stream is not None, "Missing source member")
            data = stream.read(entry.size + 1)
            helper.require(len(data) == entry.size, "Truncated source member")
            mode = "100755" if entry.mode & 0o111 else "100644"
            rows.append(helper.file_row(name, mode, data))
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
            target.chmod(0o755 if mode == "100755" else 0o644)
    rows.sort(key=lambda row: row["path"])
    helper.check_manifest(rows, pin["manifest"])
    helper.verify_source_tree(destination, rows, pin["manifest"])
    return rows


def verify_inputs(inputs):
    helper = support()
    lock, raw = load_lock()
    helper.require(helper.read_regular(inputs / "engine-source-lock.json", len(raw)) == raw,
                   "Prepared engine source lock differs")
    patch = lock["patch"]
    helper.require(helper.digest(helper.read_regular(inputs / "neutts-offline-espeak-source.patch",
                                                    patch["bytes"])) == patch["sha256"],
                   "Prepared engine patch differs")
    original = json.loads(helper.read_regular(inputs / "original-source-manifest.json", 50000))
    patched = json.loads(helper.read_regular(inputs / "patched-source-manifest.json", 50000))
    helper.check_manifest(original, lock["source"]["manifest"])
    result = helper.verify_source_tree(inputs / "source", patched, lock["patched_manifest"])
    helper.require(helper.digest(helper.read_regular(inputs / "source" / "pyproject.toml", 2000))
                   == lock["unchanged_pyproject_sha256"], "NeuTTS dependency metadata changed")
    result.update(source_commit=lock["source"]["commit"], source_tree=lock["source"]["tree"],
                  requires_python_unchanged=lock["unchanged_requires_python"],
                  all_original_assets_preserved=True, native_engine_compatibility_claimed=False)
    return result


def download(artifact, target):
    helper = support()
    opener = urllib.request.build_opener(helper.core_verifier().NoRedirect())
    request = urllib.request.Request(artifact["url"], headers={"Accept-Encoding": "identity"})
    deadline, total = time.monotonic() + 90, 0
    with opener.open(request, timeout=30) as response, target.open("xb") as output:
        helper.require(response.status == 200 and response.geturl() == artifact["url"],
                       "NeuTTS source endpoint changed")
        helper.require(response.headers.get("Content-Encoding", "identity") == "identity",
                       "Unexpected source transfer encoding")
        while True:
            helper.require(time.monotonic() < deadline, "NeuTTS source download timed out")
            chunk = response.read1(min(262144, artifact["bytes"] - total + 1))
            if not chunk:
                break
            total += len(chunk)
            helper.require(total <= artifact["bytes"], "Oversized NeuTTS source download")
            output.write(chunk)


def prepare(output, archive=None):
    helper = support()
    lock, raw = load_lock()
    helper.require(not output.exists() and not output.is_symlink(), "Fresh preparation directory required")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".neutts-engine-source-", dir=output.parent))
    try:
        artifact = lock["source"]["artifact"]
        target = staging / artifact["filename"]
        if archive is None:
            download(artifact, target)
        else:
            helper.require(not archive.is_symlink(), "Archive cache must be a regular file")
            with target.open("xb") as stream:
                stream.write(helper.read_regular(archive, artifact["bytes"]))
        original = extract_source(target, staging / "source", lock["source"])
        patch_path = SCRIPT_DIR.parent / lock["patch"]["path"]
        patch_raw = helper.read_regular(patch_path, lock["patch"]["bytes"])
        helper.require(helper.digest(patch_raw) == lock["patch"]["sha256"], "Reviewed engine source patch differs")
        patched = helper.apply_loader_patch(staging / "source", original, lock,
                                            patch_path, time.monotonic() + 45)
        (staging / "engine-source-lock.json").write_bytes(raw)
        (staging / "neutts-offline-espeak-source.patch").write_bytes(patch_raw)
        (staging / "original-source-manifest.json").write_bytes(helper.canonical(original))
        (staging / "patched-source-manifest.json").write_bytes(helper.canonical(patched))
        receipt = verify_inputs(staging)
        receipt.update(schema_version=1, status="verified-source-preparation",
                       archive_sha256=artifact["sha256"], source_lock_sha256=LOCK_SHA256,
                       patch_sha256=lock["patch"]["sha256"],
                       preparer_sha256=helper.digest(Path(__file__).read_bytes()),
                       support_sha256=SUPPORT_SHA256,
                       espeak_source_lock=lock["espeak_source_lock"],
                       selected_model_weight_downloads=0, wheel_built=False,
                       release_output=False)
        (staging / "PREPARED-NEUTTS-ENGINE-SOURCE.json").write_bytes(helper.canonical(receipt))
        helper.publish_modes(staging)
        helper.require(not output.exists() and not output.is_symlink(), "Output appeared during preparation")
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--archive", type=Path, help="Reuse the exact local archive; all bytes are verified")
    args = parser.parse_args()
    print(json.dumps(prepare(args.out, args.archive), indent=2))
