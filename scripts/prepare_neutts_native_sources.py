#!/usr/bin/env python3
"""Acquire the frozen model-free Numba/llama inputs; never build or install.

The two public Git commits and one immutable sdist are verified before a fresh
output directory is published. llama.cpp's exact 19 GGUF tokenizer fixtures are
intentionally not fetched; every other committed regular source file is bound
by Git blob identity and the frozen SHA-256 source manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request

LOCK_SHA256 = "a06e595179fad6f437ca95210d685beb339baa0867cd527dba5f5083d94b36ce"
CORE_VERIFIER_SHA256 = "b78a252eb1c3d1872b64f7ffe5e16bf16c161057b6579732a7af966317e0b19e"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 150 * 1024 * 1024
DEADLINE_SECONDS = 900
SCRIPT_DIR = Path(__file__).resolve().parent


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def read_regular(path, limit):
    require(stat.S_ISREG(path.lstat().st_mode), "Expected regular file, not a symlink")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Input exceeded its bounded size")
    return data


def safe_path(name):
    require(isinstance(name, str) and 0 < len(name) < 1024, "Invalid source path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name and "\\" not in name
            and ":" not in name and all(ord(c) >= 32 for c in name)
            and not any(p in (".", "..", ".git") for p in path.parts),
            "Unsafe source path")
    return path


def load_lock(path):
    raw = read_regular(path, 100_000)
    require(digest(raw) == LOCK_SHA256, "Native input lock SHA-256 mismatch")
    value = json.loads(raw)
    require(value["schema_version"] == 1, "Unsupported input schema")
    return value, raw


def core_verifier():
    path = SCRIPT_DIR / "prepare_neutts_core_python.py"
    require(digest(read_regular(path, 100_000)) == CORE_VERIFIER_SHA256,
            "Shared immutable wheel verifier changed")
    spec = importlib.util.spec_from_file_location("_neutts_frozen_wheel_verifier", path)
    require(spec is not None and spec.loader is not None, "Cannot load wheel verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_row(name, mode, raw):
    safe_path(name)
    require(mode in ("100644", "100755"), "Nonregular source mode")
    require(len(raw) <= MAX_FILE_BYTES, "Source member too large")
    return {
        "path": name, "mode": mode, "size": len(raw), "sha256": digest(raw),
        "git_blob_sha1": hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest(),
    }


def check_manifest(rows, expected):
    names = [row["path"] for row in rows]
    require(names == sorted(set(names)), "Duplicate or unsorted source inventory")
    for row in rows:
        safe_path(row["path"])
        require(row["mode"] in ("100644", "100755"), "Unexpected source mode")
    raw = canonical(rows)
    require(digest(raw) == expected["sha256"] and len(rows) == expected["file_count"]
            and sum(r["size"] for r in rows) == expected["bytes"],
            "Source inventory differs from the frozen source")
    require(expected["bytes"] <= MAX_SOURCE_BYTES, "Source tree too large")
    return raw


def tree_files(root):
    require(root.is_dir() and not root.is_symlink(), "Invalid source root")
    found = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            require(not (Path(directory) / name).is_symlink(), "Source directory symlink")
        for name in files:
            path = Path(directory) / name
            require(stat.S_ISREG(path.lstat().st_mode), "Nonregular source file")
            relative = path.relative_to(root).as_posix()
            safe_path(relative)
            found.add(relative)
    return found


def verify_source_tree(root, rows, expected):
    check_manifest(rows, expected)
    require(tree_files(root) == {r["path"] for r in rows}, "Missing or extra source file")
    for row in rows:
        path = root.joinpath(*safe_path(row["path"]).parts)
        actual = file_row(row["path"], row["mode"], read_regular(path, row["size"]))
        require(actual == row, "Source file byte identity mismatch: " + row["path"])
    return {"file_count": len(rows), "bytes": expected["bytes"],
            "manifest_sha256": expected["sha256"], "status": "passed"}


def git_environment():
    # Public HTTPS only; ignore global rewrite/filter/hook/credential settings.
    result = dict(os.environ)
    for key in list(result):
        if key.startswith("GIT_"):
            result.pop(key)
    result.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
    })
    return result


def git_run(checkout, args, deadline, data=None):
    remaining = deadline - time.monotonic()
    require(remaining > 0, "Source acquisition deadline exceeded")
    command = ["git", "-c", "core.autocrlf=false", "-c", "core.longpaths=true",
               "-c", "core.hooksPath=" + os.devnull, "-c", "credential.helper=",
               "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never"]
    if checkout is not None:
        command += ["-C", str(checkout)]
    try:
        result = subprocess.run(
            command + args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**git_environment(), **({"GIT_CEILING_DIRECTORIES": str(checkout.parent.resolve())}
                 if checkout is not None else {})}, timeout=min(180, remaining), check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PrepareError("Pinned public Git operation failed or timed out") from None
    require(result.returncode == 0, "Pinned public Git operation failed")
    require(len(result.stdout) <= 4_000_000 and len(result.stderr) <= 1_000_000,
            "Git operation exceeded bounded diagnostic output")
    return result.stdout


def parse_tree(raw):
    rows = []
    seen = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            header, encoded_name = entry.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            name = encoded_name.decode("utf-8")
        except (ValueError, UnicodeError):
            raise PrepareError("Malformed Git tree") from None
        safe_path(name)
        require(name not in seen, "Duplicate Git tree entry")
        seen.add(name)
        require(len(oid) == 40 and all(c in "0123456789abcdef" for c in oid),
                "Invalid Git object identity")
        require((kind == "blob" and mode in ("100644", "100755"))
                or (kind == "commit" and mode == "160000"),
                "Git symlinks or special source objects are not accepted")
        rows.append({"path": name, "mode": mode, "kind": kind, "oid": oid})
    return rows


def require_model_objects_absent(checkout, omitted, deadline):
    if not omitted:
        return
    ids = [omitted[name]["git_blob_sha1"] for name in sorted(omitted)]
    # The global switch prevents an object-existence check from lazily fetching
    # exactly the model bytes that this source-only probe excludes.
    output = git_run(checkout, ["--no-lazy-fetch", "cat-file", "--batch-check"],
                     deadline, ("\n".join(ids) + "\n").encode())
    expected = "".join(oid + " missing\n" for oid in ids).encode()
    require(output == expected, "Excluded model object was fetched into the partial clone")


def acquire_git(pin, checkout, deadline):
    git_run(None, ["init", "--quiet", "--template=", str(checkout)], deadline)
    git_run(checkout, ["remote", "add", "origin", pin["repository"]], deadline)
    git_run(checkout, ["config", "core.autocrlf", "false"], deadline)
    git_run(checkout, ["config", "core.longpaths", "true"], deadline)
    git_run(checkout, ["config", "remote.origin.promisor", "true"], deadline)
    git_run(checkout, ["config", "remote.origin.partialclonefilter", "blob:none"], deadline)
    git_run(checkout, ["fetch", "--quiet", "--depth=1", "--filter=blob:none",
                      "origin", pin["commit"]], deadline)
    require(git_run(checkout, ["rev-parse", "FETCH_HEAD"], deadline).decode().strip()
            == pin["commit"], "Git commit identity mismatch")
    require(git_run(checkout, ["rev-parse", "FETCH_HEAD^{tree}"], deadline).decode().strip()
            == pin["tree"], "Git tree identity mismatch")
    # Do not ask ls-tree for blob sizes: in a partial clone that could fetch the
    # intentionally omitted tokenizer-model blobs.
    entries = parse_tree(git_run(checkout, ["ls-tree", "-r", "-z", "FETCH_HEAD"], deadline))
    omitted = {r["path"]: r for r in pin.get("omitted_model_fixtures", [])}
    by_name = {r["path"]: r for r in entries}
    for name, item in omitted.items():
        require(by_name.get(name) == {"path": name, "mode": item["mode"],
                                     "kind": "blob", "oid": item["git_blob_sha1"]},
                "Omitted model fixture does not match committed tree")
    require_model_objects_absent(checkout, omitted, deadline)
    if omitted:
        patterns = "/*\n" + "".join("!/" + name + "\n" for name in sorted(omitted))
        git_run(checkout, ["sparse-checkout", "init", "--no-cone"], deadline)
        git_run(checkout, ["sparse-checkout", "set", "--no-cone", "--stdin"],
                deadline, patterns.encode())
    git_run(checkout, ["checkout", "--quiet", "--detach", "FETCH_HEAD"], deadline)
    require(git_run(checkout, ["status", "--porcelain", "-uno"], deadline) == b"",
            "Pinned checkout is incomplete or modified")
    require_model_objects_absent(checkout, omitted, deadline)
    for name in omitted:
        require(not checkout.joinpath(*safe_path(name).parts).exists(),
                "Excluded model fixture was materialized")
    return entries


def export_git(checkout, entries, pin, destination):
    omitted = {r["path"] for r in pin.get("omitted_model_fixtures", [])}
    expected_links = {name: value["commit"] for name, value in pin.get("submodules", {}).items()}
    actual_links = {row["path"]: row["oid"] for row in entries if row["kind"] == "commit"}
    require(actual_links == expected_links, "Submodule inventory differs")
    destination.mkdir(parents=True)
    rows = []
    for entry in entries:
        if entry["kind"] == "commit" or entry["path"] in omitted:
            continue
        relative = safe_path(entry["path"])
        raw = read_regular(checkout.joinpath(*relative.parts), MAX_FILE_BYTES)
        row = file_row(entry["path"], entry["mode"], raw)
        require(row["git_blob_sha1"] == entry["oid"], "Checked-out Git blob differs")
        rows.append(row)
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
    rows.sort(key=lambda r: r["path"])
    check_manifest(rows, pin["manifest"])
    return rows


def download_numba(artifact, destination, opener, deadline):
    expected = {
        "filename": "numba-0.67.0.tar.gz", "bytes": 2836515,
        "sha256": "cd75aa535b33fa05d9d930b1ae8af9f97a2881e96d72dfb38ec9b78284d9f851",
        "url": "https://files.pythonhosted.org/packages/7a/90/"
               "2544f4e3a61e501d6c9a5418fd4b905323222693d54a02cab0106a0af865/"
               "numba-0.67.0.tar.gz",
    }
    require(artifact == expected, "Unexpected source archive")
    remaining = deadline - time.monotonic()
    require(remaining > 0, "Source acquisition deadline exceeded")
    request = urllib.request.Request(
        artifact["url"], headers={"User-Agent": "termux-hermes-native-probe/1",
                                  "Accept-Encoding": "identity"}
    )
    with opener.open(request, timeout=min(30, remaining)) as response:
        require(response.status == 200 and response.geturl() == artifact["url"],
                "Source endpoint changed")
        require(response.headers.get("Content-Encoding", "identity") == "identity",
                "Unexpected source encoding")
        length = response.headers.get("Content-Length")
        require(length is None or length == str(artifact["bytes"]), "Source HTTP size mismatch")
        total, checksum = 0, hashlib.sha256()
        with destination.open("xb") as output:
            while True:
                require(time.monotonic() < deadline, "Source acquisition deadline exceeded")
                chunk = response.read1(min(262144, artifact["bytes"] - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                require(total <= artifact["bytes"], "Oversized source download")
                output.write(chunk)
                checksum.update(chunk)
        require(total == artifact["bytes"] and checksum.hexdigest() == artifact["sha256"],
                "Source download size or SHA-256 mismatch")


def extract_numba(path, destination, pin):
    require(digest(read_regular(path, pin["artifact"]["bytes"])) == pin["artifact"]["sha256"],
            "Numba source archive digest mismatch")
    rows, names, total = [], set(), 0
    destination.mkdir(parents=True)
    with tarfile.open(path, "r:gz") as archive:
        for entry in archive:
            require(entry.name not in names, "Duplicate tar member")
            names.add(entry.name)
            require(entry.isdir() or entry.isfile(), "Source links or special tar members")
            root, separator, relative = entry.name.partition("/")
            require(root == pin["root"], "Unexpected source archive root")
            if not separator:
                require(entry.isdir(), "Invalid source archive root entry")
                continue
            safe_path(relative)
            if entry.isdir():
                continue
            require(0 <= entry.size <= MAX_FILE_BYTES, "Oversized source member")
            total += entry.size
            require(total <= MAX_SOURCE_BYTES, "Oversized source archive")
            stream = archive.extractfile(entry)
            require(stream is not None, "Missing source member bytes")
            raw = stream.read(entry.size + 1)
            require(len(raw) == entry.size, "Source member size mismatch")
            row = file_row(relative, "100755" if entry.mode & 0o111 else "100644", raw)
            rows.append(row)
            target = destination.joinpath(*safe_path(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o755 if row["mode"] == "100755" else 0o644)
    rows.sort(key=lambda row: row["path"])
    check_manifest(rows, pin["manifest"])
    return rows


def apply_loader_patch(root, original_rows, pin, patch_path, deadline):
    patch = pin["patch"]
    require(digest(read_regular(patch_path, patch["bytes"])) == patch["sha256"],
            "Reviewed loader patch differs")
    # The exported directory has no .git; --unsafe-paths is never used.
    git_run(root, ["apply", "--check", str(patch_path)], deadline)
    git_run(root, ["apply", str(patch_path)], deadline)
    changed = {row["path"]: row for row in patch["changes"]}
    previous = {row["path"]: row for row in original_rows}
    expected_names = set(previous) | set(changed)
    require(tree_files(root) == expected_names, "Loader patch changed unreviewed paths")
    rows = []
    for name in sorted(expected_names):
        before = previous.get(name)
        raw = read_regular(root.joinpath(*safe_path(name).parts), MAX_FILE_BYTES)
        row = file_row(name, before["mode"] if before else "100644", raw)
        if name in changed:
            require((before["sha256"] if before else None) == changed[name]["before_sha256"]
                    and row["sha256"] == changed[name]["after_sha256"],
                    "Loader patch file identity mismatch")
        else:
            require(row == before, "Loader patch changed an unrelated file")
        rows.append(row)
    check_manifest(rows, pin["patched_manifest"])
    return rows


def write_tsv(path, packages):
    raw = "".join("\t".join((p["name"], p["version"], p["architecture"], p["sha256"],
                              str(p["bytes"]), p["filename"])) + "\n" for p in packages).encode()
    path.write_bytes(raw)
    return digest(raw)


def publish_modes(root):
    for directory, dirs, files in os.walk(root):
        Path(directory).chmod(0o755)
        for name in files:
            path = Path(directory) / name
            mode = path.stat().st_mode
            path.chmod(0o755 if mode & 0o111 else 0o644)


def prepare(lock_path, output):
    lock, lock_raw = load_lock(lock_path)
    require(not output.exists() and not output.is_symlink(), "Output must be a fresh directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + DEADLINE_SECONDS
    wheel = core_verifier()
    opener = urllib.request.build_opener(wheel.NoRedirect())
    staging = Path(tempfile.mkdtemp(prefix=".neutts-native-", dir=output.parent))
    try:
        (staging / "wheels").mkdir()
        (staging / "source-manifests").mkdir()
        (staging / "artifacts").mkdir()
        (staging / "neutts-native-sources-lock.json").write_bytes(lock_raw)
        wheel_checks = []
        for package in lock["additional_python_wheels"]:
            path = staging / "wheels" / package["artifact"]["filename"]
            wheel.download_file(package["artifact"], path, opener, deadline)
            wheel_checks.append(wheel.verify_wheel(path, package))
        requirements = "".join(
            f"{p['name']}=={p['version']} --hash=sha256:{p['artifact']['sha256']}\n"
            for p in lock["additional_python_wheels"]
        ).encode()
        (staging / "requirements.txt").write_bytes(requirements)
        numba = lock["sources"]["numba"]
        archive_path = staging / "artifacts" / numba["artifact"]["filename"]
        download_numba(numba["artifact"], archive_path, opener, deadline)
        numba_root = staging / "sources" / numba["root"]
        numba_rows = extract_numba(archive_path, numba_root, numba)
        (staging / "source-manifests/numba.json").write_bytes(canonical(numba_rows))
        wrapper = lock["sources"]["llama-cpp-python"]
        checkout = staging / ".wrapper-checkout"
        entries = acquire_git(wrapper, checkout, deadline)
        wrapper_root = staging / "sources/llama-cpp-python"
        wrapper_rows = export_git(checkout, entries, wrapper, wrapper_root)
        patch_source = SCRIPT_DIR.parent / wrapper["patch"]["path"]
        patch_path = staging / "llama-cpp-python-android-loader.patch"
        patch_path.write_bytes(read_regular(patch_source, wrapper["patch"]["bytes"]))
        wrapper_rows = apply_loader_patch(wrapper_root, wrapper_rows, wrapper, patch_path, deadline)
        (staging / "source-manifests/llama-cpp-python.json").write_bytes(canonical(wrapper_rows))
        vendor = wrapper["submodules"]["vendor/llama.cpp"]
        vendor_checkout = staging / ".vendor-checkout"
        vendor_entries = acquire_git(vendor, vendor_checkout, deadline)
        vendor_rows = export_git(vendor_checkout, vendor_entries, vendor,
                                 wrapper_root / "vendor/llama.cpp")
        (staging / "source-manifests/llama.cpp.json").write_bytes(canonical(vendor_rows))
        tsv_hash = write_tsv(staging / "build-apt-closure.tsv", lock["build_apt"]["packages"])
        additional_hash = write_tsv(staging / "build-apt-additional.tsv",
                                    [p for p in lock["build_apt"]["packages"] if p["additional"]])
        receipt = {
            "schema_version": 1, "status": "verified", "lock_sha256": LOCK_SHA256,
            "preparer_sha256": digest(read_regular(Path(__file__), 100_000)),
            "wheel_verifier_sha256": CORE_VERIFIER_SHA256,
            "source_checks": {
                "numba": numba["manifest"], "llama-cpp-python": wrapper["patched_manifest"],
                "llama.cpp": vendor["manifest"],
            },
            "source_commits": {"llama-cpp-python": wrapper["commit"], "llama.cpp": vendor["commit"]},
            "loader_patch_sha256": wrapper["patch"]["sha256"],
            "omitted_model_fixtures": vendor["omitted_model_fixtures"],
            "wheel_checks": wheel_checks, "requirements_sha256": digest(requirements),
            "build_apt_closure_tsv_sha256": tsv_hash,
            "build_apt_additional_tsv_sha256": additional_hash,
            "build_apt_index_sha256": lock["build_apt"]["compressed_index_sha256"],
            "models_fetched": False, "build_or_install_performed": False,
            "native_compatibility_claimed": False,
        }
        (staging / "PREPARED-NATIVE-SOURCES.json").write_bytes(canonical(receipt))
        # Only disposable acquisition checkouts are removed. No Git or model
        # data is exposed to the native runner.
        shutil.rmtree(checkout)
        shutil.rmtree(vendor_checkout)
        publish_modes(staging)
        require(not output.exists(), "Output appeared during preparation")
        staging.rename(output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=SCRIPT_DIR / "neutts_native_sources_lock.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.lock, args.out)
    except Exception as exc:
        # Public source errors only; never print a network request object.
        print(json.dumps({"status": "failed", "error": type(exc).__name__,
                          "message": str(exc)}))
        return 1
    print(json.dumps({"status": result["status"], "lock_sha256": LOCK_SHA256,
                      "receipt": str(args.out / "PREPARED-NATIVE-SOURCES.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
