#!/usr/bin/env python3
"""Build SHA-256-locked native Hermes wheels inside native Termux."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.utils import canonicalize_name, parse_wheel_filename

ABI_BY_MACHINE = {
    "aarch64": "arm64_v8a",
    "arm64": "arm64_v8a",
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "armv7l": "armeabi_v7a",
    "armv8l": "armeabi_v7a",
    "i686": "x86",
    "x86": "x86",
}
PSUTIL_MARKER = 'LINUX = sys.platform.startswith("linux")'
PSUTIL_REPLACEMENT = 'LINUX = sys.platform.startswith(("linux", "android"))'
BDIST_SECTION_RE = re.compile(r"(?ms)^\[bdist_wheel\]\s*\n(?P<body>.*?)(?=^\[|\Z)")
PLAT_NAME_RE = re.compile(r"(?m)^plat_name\s*=.*$")
SOURCE_DATE_EPOCH = 1_700_000_000


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_platform(api_level: int, machine: str | None = None) -> str:
    normalized = (machine or platform.machine()).strip().lower()
    try:
        abi = ABI_BY_MACHINE[normalized]
    except KeyError as exc:
        raise BuildError(f"unsupported Android architecture: {normalized!r}") from exc
    if not 21 <= api_level <= 99:
        raise BuildError(f"Android API must be between 21 and 99, got {api_level}")
    return f"android_{api_level}_{abi}"


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise BuildError("unsupported manifest schema")
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        raise BuildError("manifest packages must be a non-empty list")
    seen: set[str] = set()
    for package in packages:
        name = canonicalize_name(str(package.get("name", "")))
        if not name or name in seen:
            raise BuildError(f"invalid or duplicate package name: {name!r}")
        seen.add(name)
        if package.get("strategy") not in {
            "setuptools",
            "setuptools-psutil-android",
            "maturin",
        }:
            raise BuildError(f"unsupported build strategy for {name}")
        sdist = package.get("sdist") or {}
        checksum = str(sdist.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise BuildError(f"invalid sdist SHA-256 for {name}")
        if not str(sdist.get("url", "")).startswith("https://"):
            raise BuildError(f"non-HTTPS sdist URL for {name}")


def _safe_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if path.is_absolute() or not parts or ".." in parts:
        raise BuildError(f"unsafe archive member: {name!r}")
    return parts


def safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = destination.joinpath(*_safe_parts(member.filename))
                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise BuildError(f"archive symlink rejected: {member.filename}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive, "r:*") as source:
            for member in source.getmembers():
                target = destination.joinpath(*_safe_parts(member.name))
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise BuildError(f"archive link/device rejected: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = source.extractfile(member)
                if extracted is None:
                    raise BuildError(f"cannot read archive member: {member.name}")
                with extracted, target.open("wb") as dst:
                    shutil.copyfileobj(extracted, dst)
                target.chmod(member.mode & 0o777)
    else:
        raise BuildError(f"unsupported source archive: {archive.name}")
    roots = sorted(path for path in destination.iterdir() if path.is_dir())
    if len(roots) != 1:
        raise BuildError(f"expected one source root in {archive.name}, found {len(roots)}")
    return roots[0]


def download_locked(url: str, checksum: str, destination: Path, curl: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            curl,
            "-fL",
            "--retry",
            "6",
            "--retry-all-errors",
            "--connect-timeout",
            "30",
            "--max-time",
            "600",
            url,
            "-o",
            str(destination),
        ],
        check=True,
    )
    actual = sha256_file(destination)
    if actual != checksum:
        destination.unlink(missing_ok=True)
        raise BuildError(
            f"source checksum mismatch for {destination.name}: expected {checksum}, got {actual}"
        )


def configure_setuptools_tag(source_root: Path, platform_tag: str) -> None:
    setup_cfg = source_root / "setup.cfg"
    content = setup_cfg.read_text("utf-8") if setup_cfg.exists() else ""
    section = BDIST_SECTION_RE.search(content)
    if section is None:
        separator = "" if not content else "\n" if content.endswith("\n") else "\n\n"
        updated = f"{content}{separator}[bdist_wheel]\nplat_name = {platform_tag}\n"
    else:
        body = section.group("body")
        if PLAT_NAME_RE.search(body):
            body = PLAT_NAME_RE.sub(f"plat_name = {platform_tag}", body, count=1)
        else:
            body = f"plat_name = {platform_tag}\n{body}"
        updated = content[: section.start("body")] + body + content[section.end("body") :]
    setup_cfg.write_text(updated, "utf-8")


def patch_psutil(source_root: Path) -> None:
    common = source_root / "psutil" / "_common.py"
    content = common.read_text("utf-8")
    if PSUTIL_REPLACEMENT in content:
        return
    if PSUTIL_MARKER not in content:
        raise BuildError("psutil Android patch marker changed")
    common.write_text(content.replace(PSUTIL_MARKER, PSUTIL_REPLACEMENT), "utf-8")


def _record_digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def retag_wheel(wheel: Path, platform_tag: str) -> Path:
    """Rewrite wheel filename, WHEEL tags, and RECORD to an Android platform tag."""
    stem = wheel.name[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        raise BuildError(f"invalid wheel filename: {wheel.name}")
    old_platform = parts[-1]
    if old_platform == platform_tag:
        return wheel
    parts[-1] = platform_tag
    target = wheel.with_name("-".join(parts) + ".whl")
    with tempfile.TemporaryDirectory(prefix="retag-wheel-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        wheel_files = list(root.glob("*.dist-info/WHEEL"))
        record_files = list(root.glob("*.dist-info/RECORD"))
        if len(wheel_files) != 1 or len(record_files) != 1:
            raise BuildError(f"wheel metadata layout is invalid: {wheel.name}")
        wheel_metadata = wheel_files[0]
        lines = []
        tag_count = 0
        for line in wheel_metadata.read_text("utf-8").splitlines():
            if line.startswith("Tag: "):
                tag = line[5:]
                fields = tag.split("-")
                if len(fields) != 3:
                    raise BuildError(f"unexpected wheel tag: {tag}")
                fields[-1] = platform_tag
                line = "Tag: " + "-".join(fields)
                tag_count += 1
            lines.append(line)
        if not tag_count:
            raise BuildError(f"wheel has no Tag metadata: {wheel.name}")
        wheel_metadata.write_text("\n".join(lines) + "\n", "utf-8")
        record = record_files[0]
        rows: list[list[str]] = []
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p != record):
            data = path.read_bytes()
            rows.append([path.relative_to(root).as_posix(), _record_digest(data), str(len(data))])
        rows.append([record.relative_to(root).as_posix(), "", ""])
        with record.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerows(rows)
        timestamp = time.gmtime(int(os.environ.get("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)))[:6]
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                info = zipfile.ZipInfo(path.relative_to(root).as_posix(), timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = path.stat().st_mode & 0o777
                info.external_attr = (stat.S_IFREG | mode) << 16
                output.writestr(info, path.read_bytes())
    wheel.unlink()
    return target


def verify_wheel(wheel: Path, package: dict[str, Any], platform_tag: str) -> None:
    distribution, version, _, tags = parse_wheel_filename(wheel.name)
    if canonicalize_name(distribution) != canonicalize_name(package["name"]):
        raise BuildError(f"wheel distribution mismatch: {wheel.name}")
    if str(version) != str(package["version"]):
        raise BuildError(f"wheel version mismatch: {wheel.name}")
    if not any(tag.platform == platform_tag for tag in tags):
        raise BuildError(f"wheel is not tagged for {platform_tag}: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        if not any(name.endswith((".so", ".pyd")) for name in archive.namelist()):
            raise BuildError(f"expected native extension in {wheel.name}")
        bad = archive.testzip()
        if bad:
            raise BuildError(f"corrupt member {bad} in {wheel.name}")


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print("  $", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def build_package(
    package: dict[str, Any],
    *,
    work_root: Path,
    output: Path,
    python: str,
    uv: str,
    curl: str,
    platform_tag: str,
    env: dict[str, str],
) -> dict[str, Any]:
    name = canonicalize_name(package["name"])
    package_root = work_root / f"{name}-{package['version']}"
    shutil.rmtree(package_root, ignore_errors=True)
    archive = package_root / "download" / package["sdist"]["filename"]
    download_locked(package["sdist"]["url"], package["sdist"]["sha256"], archive, curl)
    source_root = safe_extract(archive, package_root / "source")
    strategy = package["strategy"]
    if strategy.startswith("setuptools"):
        configure_setuptools_tag(source_root, platform_tag)
    if strategy == "setuptools-psutil-android":
        patch_psutil(source_root)
    package_out = package_root / "wheelhouse"
    package_out.mkdir(parents=True)
    run(
        [uv, "build", "--wheel", "--no-build-isolation", "--out-dir", str(package_out), str(source_root)],
        cwd=source_root,
        env=env,
    )
    wheels = sorted(package_out.glob("*.whl"))
    if len(wheels) != 1:
        raise BuildError(f"expected one wheel for {name}, found {len(wheels)}")
    wheel = retag_wheel(wheels[0], platform_tag)
    verify_wheel(wheel, package, platform_tag)
    output.mkdir(parents=True, exist_ok=True)
    final = output / wheel.name
    shutil.copy2(wheel, final)
    run([uv, "pip", "install", "--python", python, "--no-deps", "--reinstall", str(final)], cwd=source_root, env=env)
    return {
        "name": name,
        "version": str(package["version"]),
        "filename": final.name,
        "sha256": sha256_file(final),
        "size": final.stat().st_size,
        "source_filename": package["sdist"]["filename"],
        "source_sha256": package["sdist"]["sha256"],
        "strategy": strategy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default=shutil.which("uv"))
    parser.add_argument("--curl", default=shutil.which("curl"))
    parser.add_argument("--android-api", type=int)
    parser.add_argument("--package", action="append", dest="packages")
    args = parser.parse_args()
    if sys.platform != "android":
        raise BuildError("wheel builds must run inside native Android/Termux")
    if not args.uv or not args.curl:
        raise BuildError("uv and curl are required")
    manifest = json.loads(args.manifest.read_text("utf-8"))
    validate_manifest(manifest)
    api = args.android_api or int(manifest["target"]["android_api"])
    platform_tag = expected_platform(api)
    selected = {canonicalize_name(x) for x in args.packages or []}
    packages = [
        package
        for package in manifest["packages"]
        if not selected or canonicalize_name(package["name"]) in selected
    ]
    if selected - {canonicalize_name(p["name"]) for p in packages}:
        raise BuildError(f"unknown packages requested: {sorted(selected)}")
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    prefix = env.get("PREFIX", "/data/data/com.termux/files/usr")
    env.update(
        {
            "ANDROID_API_LEVEL": str(api),
            "SOURCE_DATE_EPOCH": str(SOURCE_DATE_EPOCH),
            "PYTHONHASHSEED": "0",
            "CARGO_INCREMENTAL": "0",
            "CARGO_BUILD_JOBS": "1",
            "UV_CONCURRENT_BUILDS": "1",
            "UV_CONCURRENT_INSTALLS": "1",
            "UV_LINK_MODE": "copy",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON": args.python,
            "CFLAGS": f"-I{prefix}/include",
            "CPPFLAGS": f"-I{prefix}/include",
            "LDFLAGS": f"-L{prefix}/lib",
            "PKG_CONFIG_PATH": f"{prefix}/lib/pkgconfig",
            "MAKEFLAGS": "-j1",
            "MAX_CONCURRENCY": "1",
            "CMAKE_BUILD_PARALLEL_LEVEL": "1",
            "PYYAML_FORCE_CYTHON": "1",
        }
    )
    records = []
    for index, package in enumerate(packages, 1):
        print(f"[{index}/{len(packages)}] building {package['name']}=={package['version']}", flush=True)
        records.append(
            build_package(
                package,
                work_root=args.work,
                output=args.output,
                python=args.python,
                uv=args.uv,
                curl=args.curl,
                platform_tag=platform_tag,
                env=env,
            )
        )
    index_payload = {
        "schema_version": 1,
        "platform": platform_tag,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "manifest_sha256": sha256_file(args.manifest),
        "wheels": records,
    }
    (args.output / "index.json").write_text(json.dumps(index_payload, indent=2, sort_keys=True) + "\n")
    checksum_lines = [f"{record['sha256']}  {record['filename']}" for record in records]
    checksum_lines.append(f"{sha256_file(args.output / 'index.json')}  index.json")
    (args.output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")
    print(f"built {len(records)} locked wheels for {platform_tag}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, subprocess.CalledProcessError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
