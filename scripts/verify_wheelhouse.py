#!/usr/bin/env python3
"""Verify a released Termux wheelhouse and optionally install it without sdists."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from packaging.utils import canonicalize_name, parse_wheel_filename


class VerificationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text("utf-8").splitlines():
        if not raw.strip():
            continue
        digest, filename = raw.split(maxsplit=1)
        filename = filename.strip().lstrip("*")
        if len(digest) != 64 or filename in result:
            raise VerificationError(f"invalid checksum line: {raw!r}")
        result[filename] = digest
    return result


def verify_files(manifest: dict, wheelhouse: Path) -> dict:
    index_path = wheelhouse / "index.json"
    sums_path = wheelhouse / "SHA256SUMS"
    if not index_path.is_file() or not sums_path.is_file():
        raise VerificationError("wheelhouse lacks index.json or SHA256SUMS")
    index = json.loads(index_path.read_text("utf-8"))
    checksums = load_checksums(sums_path)
    expected = {canonicalize_name(p["name"]): str(p["version"]) for p in manifest["packages"]}
    actual: dict[str, str] = {}
    platform_tag = manifest["target"]["wheel_platform"]
    for record in index.get("wheels", []):
        filename = record["filename"]
        path = wheelhouse / filename
        if not path.is_file():
            raise VerificationError(f"missing wheel: {filename}")
        digest = sha256_file(path)
        if digest != record["sha256"] or digest != checksums.get(filename):
            raise VerificationError(f"checksum mismatch: {filename}")
        distribution, version, _, tags = parse_wheel_filename(filename)
        name = canonicalize_name(distribution)
        if name in actual:
            raise VerificationError(f"duplicate distribution: {name}")
        actual[name] = str(version)
        if not any(tag.platform == platform_tag for tag in tags):
            raise VerificationError(f"wrong platform tag: {filename}")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise VerificationError(f"corrupt wheel: {filename}")
            if not any(member.endswith((".so", ".pyd")) for member in archive.namelist()):
                raise VerificationError(f"wheel contains no native extension: {filename}")
    if actual != expected:
        raise VerificationError(f"wheel set mismatch: expected {expected}, got {actual}")
    if checksums.get("index.json") != sha256_file(index_path):
        raise VerificationError("index.json checksum mismatch")
    extra = sorted(path.name for path in wheelhouse.glob("*.whl") if path.name not in checksums)
    if extra:
        raise VerificationError(f"unchecksummed wheels: {extra}")
    return index


def install_test(manifest: dict, wheelhouse: Path, resolved: Path, uv: str, python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="termux-wheelhouse-test-") as temp:
        venv = Path(temp) / "venv"
        subprocess.run([uv, "venv", "--python", python, str(venv)], check=True)
        venv_python = venv / "bin" / "python"
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(venv_python),
                "--only-binary",
                ":all:",
                "--find-links",
                str(wheelhouse),
                "--requirements",
                str(resolved),
            ],
            check=True,
        )
        imports = [module for package in manifest["packages"] for module in package["imports"]]
        code = "import importlib\n" + "\n".join(
            f"importlib.import_module({module!r})" for module in imports
        ) + "\nprint('native imports ok')\n"
        subprocess.run([str(venv_python), "-c", code], check=True)
        subprocess.run([uv, "pip", "check", "--python", str(venv_python)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--resolved", type=Path)
    parser.add_argument("--uv", default=shutil.which("uv"))
    parser.add_argument("--python", default=shutil.which("python3.13") or shutil.which("python3"))
    parser.add_argument("--install-test", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text("utf-8"))
    index = verify_files(manifest, args.wheelhouse)
    print(f"verified {len(index['wheels'])} immutable wheels")
    if args.install_test:
        if not args.resolved or not args.uv or not args.python:
            raise VerificationError("install test requires --resolved, uv, and Python")
        install_test(manifest, args.wheelhouse, args.resolved, args.uv, args.python)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VerificationError, subprocess.CalledProcessError) as exc:
        print(f"verification failed: {exc}")
        raise SystemExit(1)
