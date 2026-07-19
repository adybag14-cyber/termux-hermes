#!/usr/bin/env python3
"""Audit an exact requirements file against the current Android Python wheel tags."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

REQ_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
NATIVE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".pyx", ".pxd", ".rs", ".go", ".asm", ".s"}
NATIVE_NAMES = {"cargo.toml", "meson.build", "cmakelists.txt"}


def curl_bytes(curl: str, url: str) -> bytes:
    return subprocess.run(
        [curl, "-fsSL", "--retry", "6", "--retry-all-errors", "--connect-timeout", "30", "--max-time", "600", url],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def inspect_sdist(curl: str, item: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="termux-wheel-audit-") as temp:
        archive = Path(temp) / item["filename"]
        archive.write_bytes(curl_bytes(curl, item["url"]))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected = (item.get("digests") or {}).get("sha256")
        if expected and digest != expected:
            raise RuntimeError(f"sdist checksum mismatch: {item['filename']}")
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as source:
                names = source.namelist()
        elif tarfile.is_tarfile(archive):
            with tarfile.open(archive, "r:*") as source:
                names = source.getnames()
        else:
            names = []
        indicators = [
            name
            for name in names
            if Path(name).name.lower() in NATIVE_NAMES or Path(name).suffix.lower() in NATIVE_SUFFIXES
        ]
        return {
            "filename": item["filename"],
            "url": item["url"],
            "sha256": digest,
            "native_indicator_count": len(indicators),
            "native_indicators": sorted(indicators)[:100],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--curl", default="/data/data/com.termux/files/usr/bin/curl")
    args = parser.parse_args()
    if sys.platform != "android":
        raise SystemExit("run this audit inside native Android/Termux Python")
    requirements = []
    for raw in args.resolved.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = REQ_RE.match(line)
        if not match:
            raise SystemExit(f"unparsed requirement: {line}")
        requirements.append(match.groups())
    compatible = set(sys_tags())
    results = []
    for index, (raw_name, version) in enumerate(requirements, 1):
        name = canonicalize_name(raw_name)
        metadata = json.loads(curl_bytes(args.curl, f"https://pypi.org/pypi/{name}/{version}/json"))
        files = metadata.get("urls", [])
        wheels = [item for item in files if item.get("packagetype") == "bdist_wheel"]
        sdists = [item for item in files if item.get("packagetype") == "sdist"]
        compatible_wheels = []
        android_wheels = []
        for wheel in wheels:
            filename = wheel["filename"]
            _, _, _, tags = parse_wheel_filename(filename)
            if any(tag.platform.startswith("android_") for tag in tags):
                android_wheels.append(filename)
            if compatible.intersection(tags):
                compatible_wheels.append(filename)
        source = inspect_sdist(args.curl, sdists[0]) if not compatible_wheels and sdists else None
        result = {
            "name": name,
            "version": version,
            "wheel_count": len(wheels),
            "android_wheels": android_wheels,
            "compatible_wheels": compatible_wheels,
            "needs_build": not bool(compatible_wheels),
            "sdist": source,
            "all_wheel_filenames": [item["filename"] for item in wheels],
        }
        results.append(result)
        print(f"[{index}/{len(requirements)}] {name}=={version}: " + ("compatible" if compatible_wheels else "BUILD"), flush=True)
    payload = {
        "schema_version": 1,
        "python": sys.version,
        "platform": sys.platform,
        "compatible_tags": [str(tag) for tag in compatible],
        "requirements_count": len(requirements),
        "needs_build_count": sum(item["needs_build"] for item in results),
        "results": results,
        "complete": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
