#!/usr/bin/env python3
"""Reproduce the published package census without installing or executing it.

Input is the immutable .deb and its published RESOLVED.txt. The hand-reviewed
capability classification remains in audit/compatibility-0.22.2-1.json; this
script verifies that it covers every optional group in the actual package.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tomllib

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

ROOT = "data/data/com.termux/files/usr/lib/hermes-agent"
SITE = "venv/lib/python3.14/site-packages/"
METADATA = {
    "app/pyproject.toml", "app/uv.lock", "app/install-stamp.json",
    "enabled-features.json", "native-wheels.json", "tools/facts.json",
}
MARKERS = {
    "implementation_name": "cpython", "implementation_version": "3.14.6",
    "os_name": "posix", "platform_machine": "aarch64", "platform_release": "",
    "platform_system": "Android", "platform_version": "",
    "platform_python_implementation": "CPython", "python_full_version": "3.14.6",
    "python_version": "3.14", "sys_platform": "android", "extra": "",
}


class MemberReader:
    """A bounded ar member; tar streaming cannot read into a following member."""

    def __init__(self, stream, size: int):
        self.stream, self.remaining = stream, size

    def read(self, size: int = -1) -> bytes:
        size = self.remaining if size < 0 else min(size, self.remaining)
        data = self.stream.read(size)
        self.remaining -= len(data)
        return data


@contextmanager
def ar_member(package: Path, prefix: str):
    with package.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError("not a Debian ar archive")
        while header := stream.read(60):
            if len(header) != 60 or header[58:] != b"\x60\n":
                raise ValueError("truncated or malformed ar header")
            name = header[:16].decode("ascii").strip().removesuffix("/")
            size = int(header[48:58])
            if size < 0:
                raise ValueError("negative archive member size")
            if name.startswith(prefix):
                yield MemberReader(stream, size)
                return
            stream.seek(size + size % 2, 1)
        raise ValueError(f"missing Debian {prefix} archive")


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe archive member: {name}")
    return path.as_posix()


def read_package(package: Path) -> tuple[dict[str, bytes], dict[str, str], set[str], dict]:
    metadata, installed, paths = {}, {}, set()
    with ar_member(package, "data.tar") as stream:
        with tarfile.open(fileobj=stream, mode="r|*") as archive:
            for member in archive:
                name = safe_name(member.name)
                if not name.startswith(ROOT + "/"):
                    continue
                relative = name[len(ROOT) + 1:]
                if relative in paths:
                    raise ValueError(f"duplicate payload member: {relative}")
                paths.add(relative)
                distribution = (
                    relative.startswith(SITE)
                    and relative[len(SITE):].count("/") == 1
                    and relative.endswith(".dist-info/METADATA")
                )
                if relative not in METADATA and not distribution:
                    continue
                if not member.isfile() or member.size > 16 * 1024 * 1024:
                    raise ValueError(f"metadata must be a bounded regular file: {relative}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError(f"unreadable metadata: {relative}")
                body = handle.read()
                if distribution:
                    record = BytesParser().parsebytes(body)
                    name, version = canonicalize_name(record["Name"]), record["Version"]
                    if name in installed:
                        raise ValueError(f"duplicate installed distribution: {name}")
                    installed[name] = version
                else:
                    metadata[relative] = body
    if set(metadata) != METADATA:
        raise ValueError(f"missing package metadata: {sorted(METADATA - set(metadata))}")
    with ar_member(package, "control.tar") as stream:
        with tarfile.open(fileobj=stream, mode="r|*") as archive:
            for member in archive:
                if safe_name(member.name) != "control":
                    continue
                if not member.isfile() or member.size > 1024 * 1024:
                    raise ValueError("invalid Debian control member")
                record = BytesParser().parsebytes(archive.extractfile(member).read())
                control = {key: record[key] for key in ("Package", "Version", "Architecture")}
                break
            else:
                raise ValueError("missing Debian control file")
    return metadata, installed, paths, control


def audit(package: Path, resolved: Path, census: dict) -> dict:
    expected = census["baseline"]
    with package.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected["sha256"]:
        raise ValueError("package bytes do not match the audited published SHA-256")
    metadata, installed, paths, control = read_package(package)
    if control != {"Package": "hermes-agent", "Version": expected["package_version"],
                   "Architecture": "aarch64"}:
        raise ValueError("Debian control does not match the audited package")
    project = tomllib.loads(metadata["app/pyproject.toml"].decode())["project"]
    config = tomllib.loads(metadata["app/pyproject.toml"].decode())
    extras = project["optional-dependencies"]
    classified = [name for group in census["groups"].values() for name in group]
    if len(classified) != len(set(classified)) or set(classified) != set(extras):
        raise ValueError("reviewed census does not cover each actual optional group exactly once")
    selected = json.loads(metadata["enabled-features.json"])["extras"]
    if selected != expected["selected_extras"]:
        raise ValueError("published feature selection differs from the audit")
    categories = {name: category for category, group in census["groups"].items() for name in group}
    gates = config.get("tool", {}).get("hermes", {}).get("extras-platforms", {})
    groups = {}
    for name, requirements in sorted(extras.items()):
        rows = []
        for text in requirements:
            requirement = Requirement(text)
            rows.append({
                "requirement": text,
                "target_marker_admitted": not requirement.marker or requirement.marker.evaluate(MARKERS),
                "installed_distribution": installed.get(canonicalize_name(requirement.name)),
            })
        groups[name] = {"classification": categories[name], "platform_gate": gates.get(name),
                        "requirements": rows}
    admitted, excluded, mismatched = [], [], []
    for row in csv.reader(resolved.read_text(encoding="utf-8-sig").splitlines(), delimiter="\t"):
        if not row or not row[0].strip() or row[0].startswith("#"):
            continue
        if len(row) != 4:
            raise ValueError(f"malformed resolved dependency row: {row}")
        name, specifier, marker, source = row
        name = canonicalize_name(name)
        entry = {"name": name, "specifier": specifier, "marker": marker, "source": source}
        if marker and not Marker(marker).evaluate(MARKERS):
            excluded.append(entry)
            continue
        admitted.append(entry)
        actual = installed.get(name)
        if actual is not None and specifier and not SpecifierSet(specifier).contains(actual):
            mismatched.append({"name": name, "expected": specifier, "installed": actual})
    names = {row["name"] for row in admitted}
    missing = sorted(names - set(installed))
    native = json.loads(metadata["native-wheels.json"])
    facts = json.loads(metadata["tools/facts.json"])
    result = {
        "schema_version": 1,
        "package": package.name, "package_sha256": digest,
        "resolved_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "control": control, "target_marker_environment": MARKERS,
        "installed_distributions": dict(sorted(installed.items())),
        "selected_extras": selected,
        "optional_group_count": len(groups), "groups": groups,
        "admitted_resolved": admitted, "excluded_resolved": excluded,
        "missing_selected": missing, "mismatched_selected": mismatched,
        "installed_not_in_resolved": sorted(set(installed) - names),
        "native_source_build_distributions": native,
        "reusable_wheel_files": sorted(name for name in paths if name.endswith(".whl")),
        "shipped_uv_cache": any(name == "uv-cache" or name.startswith("uv-cache/") for name in paths),
        "shipped_wheelhouse": any(name == "wheelhouse" or name.startswith("wheelhouse/") for name in paths),
        "pm_facts": facts,
        "recorded_venv_state": "venv" in facts.get("packages", {}),
        "packaged_source_sha256": {
            name: hashlib.sha256(metadata[name]).hexdigest()
            for name in ("app/pyproject.toml", "app/uv.lock")
        },
        "method": "Read-only archive census; product capability classification remains hand-reviewed.",
    }
    if missing or mismatched or len(installed) != expected["installed_distributions"]:
        raise ValueError("actual installed dependency census differs from the reviewed baseline")
    if len(admitted) != expected["android_admitted_resolved_distributions"]:
        raise ValueError("actual Android-admitted selection differs from the reviewed baseline")
    if result["reusable_wheel_files"] or result["shipped_uv_cache"] or result["shipped_wheelhouse"]:
        raise ValueError("audited cache-absence claim does not match the package")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=Path("audit/compatibility-0.22.2-1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.package, args.resolved, json.loads(args.census.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "package_sha256": result["package_sha256"],
        "installed": len(result["installed_distributions"]),
        "admitted": len(result["admitted_resolved"]),
        "marker_excluded": len(result["excluded_resolved"]),
        "optional_groups": result["optional_group_count"],
        "native_distributions": len(result["native_source_build_distributions"]),
        "missing": result["missing_selected"], "mismatched": result["mismatched_selected"],
        "reusable_wheels": len(result["reusable_wheel_files"]),
    }, indent=2))


if __name__ == "__main__":
    main()
