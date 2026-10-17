"""Inspect the canonical Termux bundle and record immutable build provenance.

This checks package contents, not runtime behavior. The native installation and
upgrade gates remain responsible for proving that the inspected artifact runs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tarfile
import tempfile
from typing import BinaryIO

PREFIX = "data/data/com.termux/files/usr"
ROOT = f"{PREFIX}/lib/hermes-agent"
TARGET = "linux-arm64-bionic"
PYTHON = f"tools/python/{PREFIX}/bin/python3.14"
SITE = "venv/lib/python3.14/site-packages"
COMMANDS = ("hermes", "hermes-agent", "hermes-acp")
PROFILE_PACKAGES = ("python-telegram-bot", "mcp", "croniter", "agent-client-protocol")
PROFILE_EXTRAS = ("acp", "cron", "mcp", "telegram", "termux")
METADATA_FILES = (
    "app/.install_method", "app/install-stamp.json", "app/pm/lock.json",
    "manifest.json", "pm-runtime/pm-runtime.json", "native-wheels.json",
    "enabled-features.json",
)
SHA40 = re.compile(r"[0-9a-f]{40}")
STABLE_TAG = re.compile(r"v(0|[1-9]\d{0,2})\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}")


@dataclass
class Archive:
    members: dict[str, tarfile.TarInfo]
    metadata: dict[str, bytes]


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def validate_identity(tag: str, commit: str, version: str, packaging_commit: str,
                      builder_image: str) -> None:
    if not STABLE_TAG.fullmatch(tag):
        raise ValueError("upstream tag must be an exact stable vX.Y.Z release")
    for label, value in (("upstream commit", commit), ("packaging commit", packaging_commit)):
        if not SHA40.fullmatch(value) or value == "0" * 40:
            raise ValueError(f"{label} must be a nonzero full lowercase 40-character SHA")
    if not re.fullmatch(re.escape(tag[1:]) + r"-[1-9]\d*", version):
        raise ValueError("package version must match the upstream release with a Debian revision")
    if not IMAGE.fullmatch(builder_image):
        raise ValueError("builder image must include an immutable sha256 digest")


def validate_control(control: str, expected_version: str) -> dict[str, str]:
    fields = Parser().parsestr(control)
    expected = {"Package": "hermes-agent", "Architecture": "aarch64", "Version": expected_version}
    for key, value in expected.items():
        if fields.get_all(key) != [value]:
            raise ValueError(f"Debian {key} must be exactly {value!r}")
    return expected


def validate_stamp(stamp: object, tag: str, commit: str) -> dict:
    expected = {
        "schemaVersion": 2, "commit": commit, "tag": tag,
        "baseVersion": tag[1:], "displayVersion": tag[1:], "distance": 0,
        "payload": "runtime", "source": "bundle", "distribution": "apt-termux",
        "updateMechanism": "external",
    }
    if not isinstance(stamp, dict):
        raise ValueError("install-stamp.json must contain a JSON object")
    for key, value in expected.items():
        if stamp.get(key) != value or type(stamp.get(key)) is not type(value):
            raise ValueError(f"install stamp {key} must be exactly {value!r}")
    if type(stamp.get("dirty")) is not bool:
        raise ValueError("install stamp must record a boolean dirty source state")
    return stamp


def scan_tar(stream: BinaryIO) -> Archive:
    """Stream the data archive without writing or following any packaged path."""
    members: dict[str, tarfile.TarInfo] = {}
    metadata: dict[str, bytes] = {}
    wanted = {f"{ROOT}/{name}": name for name in METADATA_FILES}
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError(f"unsafe archive path: {member.name!r}")
            if ".git" in path.parts:
                raise ValueError(f"Git metadata must not be shipped: {member.name}")
            name = path.as_posix()
            if name in members:
                raise ValueError(f"duplicate archive path: {name}")
            members[name] = member
            if name in wanted:
                if not member.isfile() or member.size > 16 * 1024 * 1024:
                    raise ValueError(f"metadata must be a bounded regular file: {name}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError(f"cannot read packaged metadata: {name}")
                metadata[wanted[name]] = handle.read()
    return Archive(members, metadata)


def _member(archive: Archive, relative: str, *, executable: bool = False,
            directory: bool = False) -> tarfile.TarInfo:
    """Resolve packaged links inside the bundle, never against the build host."""
    path = f"{ROOT}/{relative}"
    seen: set[str] = set()
    while True:
        if path in seen:
            raise ValueError(f"cyclic packaged link: {relative}")
        seen.add(path)
        if not path.startswith(ROOT + "/"):
            raise ValueError(f"required payload path escapes the bundle: {relative}")
        member = archive.members.get(path)
        if member is None:
            raise ValueError(f"required payload path missing: {relative}")
        if member.issym() or member.islnk():
            target = member.linkname
            if target.startswith("/"):
                path = posixpath.normpath(target.lstrip("/"))
            elif member.islnk():
                path = posixpath.normpath(target)
            else:
                path = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
            continue
        if directory:
            if not member.isdir():
                raise ValueError(f"required payload directory is not a directory: {relative}")
        elif not member.isfile():
            raise ValueError(f"required payload file is not a regular file: {relative}")
        if executable and not member.mode & 0o111:
            raise ValueError(f"required payload executable is not executable: {relative}")
        return member


def _json(archive: Archive, name: str) -> object:
    if name not in archive.metadata:
        raise ValueError(f"required packaged metadata missing: {name}")
    try:
        return json.loads(archive.metadata[name].decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid packaged JSON: {name}") from error


def validate_archive(archive: Archive, tag: str, commit: str) -> dict:
    if archive.metadata.get("app/.install_method", b"").strip() != b"apt":
        raise ValueError("app/.install_method must name apt")
    stamp = validate_stamp(_json(archive, "app/install-stamp.json"), tag, commit)
    manifest = _json(archive, "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")
    for key, value in {"schema": 1, "target": TARGET, "repo": "app",
                       "venv": "venv", "store": "tools"}.items():
        if manifest.get(key) != value:
            raise ValueError(f"bundle manifest {key} must be {value!r}")
    if set(manifest.get("launchers", [])) != set(COMMANDS):
        raise ValueError("bundle must declare the Hermes, agent and ACP launchers")
    runtime = manifest.get("runtime")
    expected_runtime = {
        "repoDir": "app", "toolsDir": "tools", "storePython": PYTHON,
        "sitePackages": SITE, "commands": {name: f"bin/{name}" for name in COMMANDS},
    }
    if not isinstance(runtime, dict) or any(
        runtime.get(key) != value for key, value in expected_runtime.items()
    ):
        raise ValueError("bundle runtime paths do not match the fixed Termux layout")
    for path in ("app/pm", "venv", SITE, "pm-runtime", "tools", "runtime-libs/lib"):
        _member(archive, path, directory=True)
    for path in (
        PYTHON, "venv/bin/python", f"tools/node/{PREFIX}/bin/node",
        f"tools/uv/{PREFIX}/bin/uv", "tools/npm/bin/npm",
        f"tools/ffmpeg/{PREFIX}/bin/ffmpeg", "tools/ripgrep/rg",
        *(f"bin/{name}" for name in COMMANDS),
    ):
        _member(archive, path, executable=True)
    for path in ("app/hermes_cli/tui_dist/entry.js",
                 "app/hermes_cli/tui_dist/package.json", "tools/facts.json"):
        _member(archive, path)
    manager = _json(archive, "pm-runtime/pm-runtime.json")
    if not isinstance(manager, dict):
        raise ValueError("PM runtime marker must contain an object")
    if manager.get("python") != f"../{PYTHON}":
        raise ValueError("PM runtime must use the bundled CPython 3.14 interpreter")
    if manager.get("sitePackages") != "lib/python3.14/site-packages":
        raise ValueError("PM runtime must have an independent Python 3.14 dependency directory")
    _member(archive, f"pm-runtime/{manager['sitePackages']}", directory=True)
    for module in ("packaging", "tomli_w", "truststore", "ruamel/yaml"):
        _member(archive, f"pm-runtime/{manager['sitePackages']}/{module}/__init__.py")
    for package in PROFILE_PACKAGES:
        # Prove the selected optional profiles reached the shipped environment.
        pattern = f"{ROOT}/{SITE}/{package.replace('-', '_')}-"
        if not any(name.startswith(pattern) and name.endswith(".dist-info/METADATA")
                   and entry.isfile() for name, entry in archive.members.items()):
            raise ValueError(f"termux feature dependency missing from package: {package}")
    natives = _json(archive, "native-wheels.json")
    if not isinstance(natives, list) or not all(isinstance(name, str) for name in natives):
        raise ValueError("native-wheels.json must contain a list of distribution names")
    _json(archive, "app/pm/lock.json")
    features = _json(archive, "enabled-features.json")
    if (not isinstance(features, dict) or type(features.get("schema")) is not int
            or features["schema"] != 1 or features.get("extras") != list(PROFILE_EXTRAS)):
        raise ValueError("enabled-features.json must declare the exact sorted Termux extras")
    return {"install_stamp": stamp, "manifest": manifest, "native_distributions": natives,
            "enabled_features": features["extras"]}


def inspect_deb(deb: Path, version: str, tag: str, commit: str) -> tuple[dict, Archive]:
    control = subprocess.run(
        ["dpkg-deb", "--field", str(deb)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout
    validate_control(control, version)
    # stderr goes to a file so neither tar streaming nor an early validation
    # failure can deadlock a child waiting for its stderr pipe to be drained.
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            ["dpkg-deb", "--fsys-tarfile", str(deb)], stdout=subprocess.PIPE, stderr=stderr,
        )
        try:
            assert process.stdout is not None
            with process.stdout:
                archive = scan_tar(process.stdout)
                while process.stdout.read(1024 * 1024):
                    pass  # Drain tar padding before closing the producer's pipe.
            if process.wait() != 0:
                stderr.seek(0)
                raise ValueError("dpkg-deb could not read the data archive: " +
                                 stderr.read().decode("utf-8", errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return validate_archive(archive, tag, commit), archive


def file_record(path: Path, name: str | None = None) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"file": name or path.name, "sha256": digest, "size": path.stat().st_size}


def build_metadata(args: argparse.Namespace) -> dict:
    validate_identity(args.upstream_tag, args.upstream_commit, args.package_version,
                      args.packaging_commit, args.builder_image)
    inspection, archive = inspect_deb(
        args.deb, args.package_version, args.upstream_tag, args.upstream_commit,
    )
    actual_lock = archive.metadata["app/pm/lock.json"]
    if actual_lock != args.pm_lock.read_bytes():
        raise ValueError("packaged PM lock differs from the supplied effective build lock")
    resolved = args.payload / ".work/resolved.txt"
    build_set = args.payload / ".work/build_set.txt"
    rows = [line.split("\t") for line in resolved.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]
    if not rows or any(len(row) != 4 or not row[0] or not row[1] for row in rows):
        raise ValueError("resolved.txt must contain the canonical four-column locked graph")
    names = {canonical_name(row[0]) for row in rows}
    if missing := set(PROFILE_PACKAGES) - names:
        raise ValueError(f"termux profile missing from resolved graph: {sorted(missing)}")
    native_names = [line.strip() for line in
                    build_set.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if inspection["native_distributions"] != native_names:
        raise ValueError("packaged native wheel manifest differs from the build set")
    wheels = sorted((args.payload / "wheelhouse").glob("*.whl"))
    if not wheels:
        raise ValueError("build wheelhouse is empty")
    return {
        "schema_version": 1,
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "package": {"name": "hermes-agent", "version": args.package_version,
                    "architecture": "aarch64", **file_record(args.deb)},
        "upstream": {"repository": "NousResearch/hermes-agent", "tag": args.upstream_tag,
                     "commit": args.upstream_commit,
                     "install_stamp": inspection["install_stamp"]},
        "packaging": {"repository": "adybag14-cyber/termux-hermes",
                      "commit": args.packaging_commit, "builder_image": args.builder_image,
                      "build_patches": [file_record(path) for path in args.build_patch]},
        "runtime": {"target": TARGET, "feature_profile": "termux",
                    "enabled_features": inspection["enabled_features"],
                    "manifest": inspection["manifest"],
                    "pm_lock": file_record(args.pm_lock, "app/pm/lock.json")},
        "wheelhouse": {
            "resolved_graph": file_record(resolved, ".work/resolved.txt"),
            "build_set": file_record(build_set, ".work/build_set.txt"),
            "native_distributions": native_names,
            "wheels": [file_record(path) for path in wheels],
        },
        "inspection": {"package_contract": "passed",
                       "runtime_validation": "reported separately by native installation gates"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("deb", "payload", "pm-lock", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    for option in ("upstream-tag", "upstream-commit", "package-version",
                   "packaging-commit", "builder-image"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--build-patch", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        metadata = build_metadata(args)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(1, f"bundle_metadata: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Inspected {args.deb.name}; wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
