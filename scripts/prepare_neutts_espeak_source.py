#!/usr/bin/env python3
"""Prepare the exact NeuTTS eSpeak source and reviewed offline guard; never install."""
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
LOCK_SHA256 = "02e4469a3b7b3e6594d7b1bc9c6816c72adf1ea9eb917256cefefc9c12763baa"
SUPPORT_SHA256 = "7e4abf6794f848d399d15a877e9c8a74db1a44ba5e87ceb898d5d4777169f744"


def support():
    path = SCRIPT_DIR / "prepare_neutts_native_sources.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != SUPPORT_SHA256:
        raise RuntimeError("Reviewed source verification helper changed")
    spec = importlib.util.spec_from_file_location("_espeak_source_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lock():
    helper = support()
    raw = helper.read_regular(SCRIPT_DIR / "neutts_espeak_source_lock.json", 20000)
    helper.require(helper.digest(raw) == LOCK_SHA256, "eSpeak source lock differs")
    return json.loads(raw), raw


def patched_deps(raw, lock):
    helper = support()
    patch = lock["patch"]
    helper.require(helper.digest(raw) == patch["before_sha256"], "eSpeak guard preimage differs")
    old = b"  set(HAVE_LIBSONIC ON)\nelse()\n  FetchContent_Declare(sonic-git"
    new = b"  set(HAVE_LIBSONIC ON)\nelseif(NOT DEFINED USE_LIBSONIC OR USE_LIBSONIC)\n  FetchContent_Declare(sonic-git"
    helper.require(raw.count(old) == 1, "eSpeak Sonic branch is ambiguous")
    result = raw.replace(old, new, 1)
    helper.require(helper.digest(result) == patch["after_sha256"], "eSpeak guard result differs")
    return result


def inspect_archive(path, lock, destination=None):
    helper = support()
    pin = lock["source"]
    artifact = pin["artifact"]
    raw_archive = helper.read_regular(path, artifact["bytes"])
    helper.require(len(raw_archive) == artifact["bytes"]
                   and helper.digest(raw_archive) == artifact["sha256"], "eSpeak archive differs")
    if destination is not None:
        helper.require(not destination.exists() and not destination.is_symlink(), "Fresh source directory required")
        destination.mkdir(parents=True)
    original, patched, names, link = [], [], set(), None
    with tarfile.open(path, "r:gz") as archive:
        for entry in archive:
            root, separator, name = entry.name.partition("/")
            helper.require(root == pin["root"], "Unexpected eSpeak archive root")
            if not separator:
                helper.require(entry.isdir(), "Invalid eSpeak root member")
                continue
            helper.safe_path(name)
            if entry.isdir():
                continue
            helper.require(name not in names, "Duplicate eSpeak member")
            names.add(name)
            if entry.issym():
                allowed = pin["exact_symlink"]
                helper.require(name == allowed["path"] and entry.linkname == allowed["target"],
                               "Unexpected eSpeak source symlink")
                data, mode = entry.linkname.encode("utf-8"), "120000"
                link = (name, entry.linkname)
            else:
                helper.require(entry.isfile() and 0 <= entry.size <= helper.MAX_FILE_BYTES,
                               "Nonregular or oversized eSpeak member")
                stream = archive.extractfile(entry)
                helper.require(stream is not None, "Missing eSpeak member")
                data = stream.read(entry.size + 1)
                helper.require(len(data) == entry.size, "Truncated eSpeak source member")
                mode = "100755" if entry.mode & 0o111 else "100644"
            row = {"path": name, "mode": mode, "size": len(data), "sha256": helper.digest(data),
                   "git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
            original.append(row)
            if name == lock["patch"]["source_path"]:
                data = patched_deps(data, lock)
                changed = helper.file_row(name, mode, data)
            else:
                changed = row
            patched.append(changed)
            if destination is not None and mode != "120000":
                target = destination.joinpath(*helper.safe_path(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(data)
                target.chmod(0o755 if mode == "100755" else 0o644)
    original.sort(key=lambda row: row["path"])
    patched.sort(key=lambda row: row["path"])
    for rows, expected in [(original, pin["manifest"]), (patched, lock["patched_manifest"])]:
        helper.require(len(rows) == expected["file_count"]
                       and sum(row["size"] for row in rows) == expected["bytes"]
                       and helper.digest(helper.canonical(rows)) == expected["sha256"],
                       "Complete eSpeak source manifest differs")
    helper.require(link == (pin["exact_symlink"]["path"], pin["exact_symlink"]["target"]),
                   "eSpeak compatibility header symlink missing")
    if destination is not None:
        path = destination / link[0]
        resolved = (path.parent / link[1]).resolve()
        helper.require(resolved.is_relative_to(destination.resolve()) and resolved.is_file(),
                       "eSpeak source symlink escaped its source")
        path.symlink_to(link[1])
    return original, patched


def verify_inputs(inputs, destination=None):
    helper = support()
    lock, raw = load_lock()
    helper.require(helper.read_regular(inputs / "espeak-source-lock.json", len(raw)) == raw,
                   "Prepared eSpeak lock differs")
    patch = helper.read_regular(inputs / "espeak-explicit-off-sonic.patch", lock["patch"]["bytes"])
    helper.require(helper.digest(patch) == lock["patch"]["sha256"], "Prepared eSpeak patch differs")
    original, patched = inspect_archive(inputs / lock["source"]["artifact"]["filename"], lock, destination)
    for filename, rows in [("original-source-manifest.json", original), ("patched-source-manifest.json", patched)]:
        expected = helper.canonical(rows)
        helper.require(helper.read_regular(inputs / filename, len(expected)) == expected,
                       "Prepared eSpeak inventory differs")
    native_lock, native_raw = helper.load_lock(SCRIPT_DIR / "neutts_native_sources_lock.json")
    helper.require(helper.digest(native_raw) == lock["native_compiler_lock_sha256"], "Compiler lock differs")
    expected_tsv = "".join("\t".join((p["name"], p["version"], p["architecture"], p["sha256"],
                                     str(p["bytes"]), p["filename"])) + "\n"
                           for p in native_lock["build_apt"]["packages"]).encode()
    helper.require(helper.read_regular(inputs / "build-apt-closure.tsv", len(expected_tsv)) == expected_tsv,
                   "Prepared compiler archive closure differs")
    return lock, native_lock


def prepare(output, archive=None):
    helper = support()
    lock, raw = load_lock()
    helper.require(not output.exists() and not output.is_symlink(), "Fresh preparation directory required")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".neutts-espeak-", dir=output.parent))
    try:
        artifact = lock["source"]["artifact"]
        target = staging / artifact["filename"]
        if archive is not None:
            helper.require(archive.resolve() != target.resolve(), "Invalid archive cache path")
            shutil.copyfile(archive, target)
        else:
            opener = urllib.request.build_opener(helper.core_verifier().NoRedirect())
            request = urllib.request.Request(artifact["url"], headers={"Accept-Encoding": "identity"})
            deadline, total = time.monotonic() + 180, 0
            with opener.open(request, timeout=30) as response, target.open("xb") as stream:
                helper.require(response.status == 200 and response.geturl() == artifact["url"],
                               "eSpeak source endpoint changed")
                helper.require(response.headers.get("Content-Encoding", "identity") == "identity",
                               "Unexpected eSpeak transfer encoding")
                while True:
                    helper.require(time.monotonic() < deadline, "eSpeak source download timed out")
                    chunk = response.read1(min(262144, artifact["bytes"] - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    helper.require(total <= artifact["bytes"], "Oversized eSpeak source download")
                    stream.write(chunk)
        original, patched = inspect_archive(target, lock)
        (staging / "espeak-source-lock.json").write_bytes(raw)
        for filename, rows in [("original-source-manifest.json", original), ("patched-source-manifest.json", patched)]:
            (staging / filename).write_bytes(helper.canonical(rows))
        patch_path = SCRIPT_DIR.parent / lock["patch"]["path"]
        patch_raw = helper.read_regular(patch_path, lock["patch"]["bytes"])
        helper.require(helper.digest(patch_raw) == lock["patch"]["sha256"], "Reviewed patch differs")
        (staging / "espeak-explicit-off-sonic.patch").write_bytes(patch_raw)
        native_lock, native_raw = helper.load_lock(SCRIPT_DIR / "neutts_native_sources_lock.json")
        helper.require(helper.digest(native_raw) == lock["native_compiler_lock_sha256"], "Compiler lock differs")
        tsv_sha = helper.write_tsv(staging / "build-apt-closure.tsv", native_lock["build_apt"]["packages"])
        receipt = {"schema_version": 1, "status": "verified", "source": lock["source"],
                   "patched_manifest": lock["patched_manifest"], "lock_sha256": LOCK_SHA256,
                   "patch_sha256": lock["patch"]["sha256"], "build_apt_closure_tsv_sha256": tsv_sha,
                   "preparer_sha256": helper.digest(Path(__file__).read_bytes()),
                   "shared_source_helper_sha256": SUPPORT_SHA256,
                   "build_or_install_performed": False, "native_compatibility_claimed": False,
                   "model_downloaded": False, "audio_io_performed": False}
        (staging / "PREPARED-ESPEAK-SOURCE.json").write_bytes(helper.canonical(receipt))
        verify_inputs(staging)
        helper.publish_modes(staging)
        helper.require(not output.exists(), "Output appeared during preparation")
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Reuse an exact local archive; bytes are always verified")
    args = parser.parse_args()
    print(json.dumps(prepare(args.out, args.archive), indent=2))
