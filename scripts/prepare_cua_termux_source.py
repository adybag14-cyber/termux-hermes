#!/usr/bin/env python3
"""Prepare only the pinned CUA 0.21.0 native-Termux experiment; never install it.

The original Git tree and Cargo registry checksums remain the source authority.
Two reviewed local crate adapters replace only their own source identities in
Cargo.lock; every other locked package row must remain byte-semantically equal.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
import tomllib

COMMIT = "70db98d1bcd92890d778f4978e0eb107a4b66c1b"
LOCK_SHA256 = "27b025bc4fd81074cf18ae614597bec5b7c9d8ea99b2a7aaf45072aec72c64ce"
WORKSPACE = Path("libs/cua-driver/rust")
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
CRATES = {
    "clipboard-rs": ("0.3.5", "d1c988a897ea030e32f0668c90b0192800e0c561b3d941fc366f9ad5a1bf26ba"),
    "x11rb-protocol": ("0.13.2", "ea6fc2961e4ef194dcbfe56bb845534d0dc8098940c7e5c012a258bfec6701bd"),
}
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNPACKED_BYTES = 80 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args], check=True,
        capture_output=True, text=True, encoding="utf-8", timeout=45,
    )
    return result.stdout.strip()


def safe_unpack(data: bytes, destination: Path, expected_root: str) -> None:
    """Extract verified crate bytes; reject links, traversal and duplicate paths."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        total = 0
        seen: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute() or not path.parts or path.parts[0] != expected_root
                or ".." in path.parts or "\\" in member.name or ":" in member.name
                or not (member.isdir() or member.isfile()) or member.name in seen
            ):
                raise ValueError(f"Unsafe crate member: {member.name}")
            seen.add(member.name)
            total += member.size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("Crate extraction exceeds the reviewed bound")
        for member in members:
            path = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing crate member bytes: {member.name}")
            path.write_bytes(stream.read())
            path.chmod(0o644)


def tree_digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Vendored source contains a symlink")
        if path.is_file():
            rows.append([path.relative_to(root).as_posix(), sha(path.read_bytes())])
    return sha(json.dumps(rows, separators=(",", ":")).encode())


def replace_exact(path: Path, old: str, new: str, count: int) -> dict[str, str]:
    original = path.read_bytes()
    text = original.decode("utf-8")
    if text.count(old) != count:
        raise ValueError(f"Reviewed edit mismatch in {path.name}: expected {count}")
    changed = text.replace(old, new)
    path.write_text(changed, encoding="utf-8", newline="\n")
    return {"path": path.as_posix(), "before_sha256": sha(original), "after_sha256": sha(path.read_bytes())}


def adapt_crate(name: str, root: Path) -> list[dict[str, str]]:
    if name == "clipboard-rs":
        # The selected implementation remains the existing Unix X11 backend.
        # No Android phone clipboard/JNI implementation is implied or created.
        return [
            replace_exact(
                root / "Cargo.toml", 'target_os="android",', "", 2,
            ),
            replace_exact(
                root / "src/lib.rs", '\t\ttarget_os = "android",\n', "", 1,
            ),
            replace_exact(
                root / "src/platform/mod.rs", '\t\ttarget_os = "android",\n', "", 5,
            ),
        ]
    if name == "x11rb-protocol":
        old = '            let file_name = format!("/tmp/.X11-unix/X{display}");'
        new = """            // Termux's Xlib and Xvnc use PREFIX/tmp. Keep DISPLAY unchanged
            // so Rust, clipboard-rs and native Xlib address the same X server.
            #[cfg(target_os = "android")]
            let file_name = format!(
                "{}/tmp/.X11-unix/X{display}",
                std::env::var("PREFIX")
                    .unwrap_or_else(|_| "/data/data/com.termux/files/usr".into())
            );
            #[cfg(not(target_os = "android"))]
            let file_name = format!("/tmp/.X11-unix/X{display}");"""
        return [replace_exact(root / "src/parse_display/connect_instruction.rs", old, new, 1)]
    raise ValueError(f"Unreviewed crate: {name}")


def localize_lock(original: str) -> str:
    before = tomllib.loads(original)
    parts = original.split("[[package]]")
    changed: set[str] = set()
    for index in range(1, len(parts)):
        block = "[[package]]" + parts[index]
        # Cargo.lock package sections have no nested [[package]] records.
        row = tomllib.loads(block)["package"][0]
        name = row["name"]
        if name not in CRATES:
            continue
        version, digest = CRATES[name]
        if (
            name in changed or row["version"] != version
            or row.get("source") != REGISTRY or row.get("checksum") != digest
        ):
            raise ValueError(f"Unexpected original locked identity for {name}")
        block = re.sub(r'^source = "[^"]+"\n', "", block, count=1, flags=re.M)
        block = re.sub(r'^checksum = "[a-f0-9]+"\n', "", block, count=1, flags=re.M)
        parts[index] = block[len("[[package]]"):]
        changed.add(name)
    if changed != set(CRATES):
        raise ValueError("A reviewed source is absent from Cargo.lock")
    result = "[[package]]".join(parts)
    after = tomllib.loads(result)
    expected = json.loads(json.dumps(before))
    for row in expected["package"]:
        if row["name"] in CRATES:
            row.pop("source")
            row.pop("checksum")
    if after != expected:
        raise ValueError("An unrelated locked package changed")
    return result


def prepare(source: Path, patch: Path, out: Path) -> None:
    source, patch, out = source.resolve(), patch.resolve(), out.resolve()
    if git(source, "rev-parse", "HEAD") != COMMIT:
        raise ValueError("CUA source must be the exact reviewed commit")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("CUA source must be a clean isolated checkout")
    workspace = source / WORKSPACE
    original_lock = (workspace / "Cargo.lock").read_text(encoding="utf-8")
    if sha(original_lock.encode()) != LOCK_SHA256:
        raise ValueError("Original Cargo.lock does not match the reviewed source")
    locked = tomllib.loads(original_lock)["package"]
    numstat = git(source, "apply", "--numstat", str(patch))
    for line in numstat.splitlines():
        path = line.split("\t", 2)[-1]
        if not path.startswith(WORKSPACE.as_posix() + "/"):
            raise ValueError(f"Patch escapes the reviewed Rust workspace: {path}")
    git(source, "apply", "--check", str(patch))
    vendor = workspace / "termux-vendor"
    if vendor.exists():
        raise ValueError("Refusing an existing vendored source directory")
    artifacts = []
    for name, (version, digest) in CRATES.items():
        matches = [p for p in locked if p["name"] == name]
        if len(matches) != 1 or matches[0].get("checksum") != digest or matches[0]["version"] != version:
            raise ValueError(f"Cargo.lock does not authorize {name}")
        url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES or sha(data) != digest:
            raise ValueError(f"Registry archive integrity failed for {name}")
        safe_unpack(data, vendor, f"{name}-{version}")
        edits = adapt_crate(name, vendor / f"{name}-{version}")
        for edit in edits:
            edit["path"] = str(Path(edit["path"]).relative_to(workspace).as_posix())
        artifacts.append({
            "name": name, "version": version, "registry": REGISTRY,
            "url": url, "archive_sha256": digest, "archive_bytes": len(data), "edits": edits,
            "prepared_tree_sha256": tree_digest(vendor / f"{name}-{version}"),
        })
    git(source, "apply", str(patch))
    localized = localize_lock(original_lock)
    (workspace / "Cargo.lock").write_text(localized, encoding="utf-8", newline="\n")
    git(source, "diff", "--check")
    out.mkdir(parents=True, exist_ok=True)
    changed_paths = git(source, "diff", "--name-only").splitlines()
    receipt = {
        "schema": 1, "purpose": "isolated native Termux X11 experiment; no PM admission",
        "source_repository": "trycua/cua", "source_tag": "cua-driver-rs-v0.21.0",
        "source_commit": COMMIT, "source_lock_sha256": LOCK_SHA256,
        "prepared_lock_sha256": sha(localized.encode()), "source_patch_sha256": sha(patch.read_bytes()),
        "preparer_sha256": sha(Path(__file__).read_bytes()), "registry_adapters": artifacts,
        "changed_source_sha256": {p: sha((source / p).read_bytes()) for p in changed_paths},
        "unchanged_registry_package_rows": len(locked) - len(CRATES),
        "unavailable_claims": [
            "Android phone UI", "TigerVNC parallel uinput pointers",
            "encrypted history without a supported secure credential store",
        ],
    }
    (out / "CUA-SOURCE-RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    (out / "CUA-Cargo.lock").write_text(localized, encoding="utf-8", newline="\n")
    (out / "cua-driver.patch").write_bytes(patch.read_bytes())
    print(json.dumps({"prepared": str(workspace), "registry_adapters": len(artifacts),
                      "unchanged_registry_package_rows": receipt["unchanged_registry_package_rows"],
                      "source_patch_sha256": receipt["source_patch_sha256"]}))


def verify_prepared(source: Path, patch: Path, out: Path) -> None:
    source = source.resolve()
    receipt = json.loads((out / "CUA-SOURCE-RECEIPT.json").read_text())
    if receipt["source_commit"] != COMMIT or git(source, "rev-parse", "HEAD") != COMMIT:
        raise ValueError("Prepared source commit changed")
    if receipt["source_patch_sha256"] != sha(patch.read_bytes()):
        raise ValueError("Reviewed source patch changed after preparation")
    if receipt["preparer_sha256"] != sha(Path(__file__).read_bytes()):
        raise ValueError("Source preparer changed after preparation")
    expected = receipt["changed_source_sha256"]
    if set(git(source, "diff", "--name-only").splitlines()) != set(expected):
        raise ValueError("Unexpected tracked source changes after preparation")
    for name, digest in expected.items():
        if sha((source / name).read_bytes()) != digest:
            raise ValueError(f"Prepared source changed: {name}")
    for row in receipt["registry_adapters"]:
        path = source / WORKSPACE / "termux-vendor" / f"{row['name']}-{row['version']}"
        if tree_digest(path) != row["prepared_tree_sha256"]:
            raise ValueError(f"Prepared registry source changed: {row['name']}")
    print(json.dumps({"verified_prepared_source": COMMIT, "registry_adapters": len(CRATES)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--verify-prepared", action="store_true")
    args = parser.parse_args()
    action = verify_prepared if args.verify_prepared else prepare
    action(args.source, args.patch, args.out)


if __name__ == "__main__":
    main()
