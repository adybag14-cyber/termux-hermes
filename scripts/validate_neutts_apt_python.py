"""Validate one frozen Termux APT Python convention without changing the environment.

Exit 0 certifies requirements and APT provenance only. The caller must also require
its independent installed-wheel, ELF, numerical, audio, and codec behavior gates.
This command does not install packages, rewrite WHEEL metadata, alter tags, or
turn the retained nonzero pip check result into a pip success.
"""
from __future__ import annotations

import argparse
import email
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tarfile

PREFIX = Path("/data/data/com.termux/files/usr")
SITE = PREFIX / "lib/python3.14/site-packages"
MANIFEST_SHA256 = "2031c8a6915915ffffb980b268ad5107d42a186682cb2ca7009d803fe2abe200"
APT_NAMES = frozenset(("llvmlite", "numpy", "scipy", "soxr", "torch", "torchaudio", "torchcodec"))
CONTROL_FIELDS = ("Package", "Version", "Architecture", "Depends", "Pre-Depends")


class ValidationError(RuntimeError):
    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details


def require(condition, message, *, details=None):
    if not condition:
        raise ValidationError(message, details=details)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit=1_000_000):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), f"Not a regular, non-symlink file: {path}")
    require(info.st_size <= limit, f"File exceeds the reviewed bound: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == info.st_size, f"File size changed while reading: {path}")
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path):
    raw = read_regular(path, 100_000)
    require(digest(raw) == MANIFEST_SHA256, "Frozen APT metadata ledger differs")
    data = json.loads(raw, object_pairs_hook=unique_object)
    require(data["schema_version"] == 1, "Unexpected metadata ledger schema")
    require({row["name"] for row in data["apt_distributions"]} == APT_NAMES
            and len(data["apt_distributions"]) == len(APT_NAMES),
            "The ledger must describe the exact seven reviewed APT distributions")
    require(data["runtime"]["selected_extras"] == [], "This ledger covers base requirements only")
    return data


def native_runtime(expected):
    """The CLI admits the real interpreter, never a caller-supplied target."""
    require(sys.platform == "android" and os.name == "posix",
            "Requires the actual native Termux Android interpreter")
    require(sys.implementation.name == expected["implementation"]
            and platform.python_version() == expected["python_version"],
            "Requires the exact native CPython 3.14.6 interpreter")
    require(os.uname().machine == expected["machine"], "Requires actual AArch64")
    require(sys.flags.isolated == 1 and sys.dont_write_bytecode,
            "Invoke the validator with -I -B")
    require(os.environ.get("PREFIX") == str(PREFIX), "Unexpected Termux PREFIX")
    require(Path(sys.prefix) == PREFIX and Path(sys.base_prefix) == PREFIX,
            "Requires the APT interpreter, not a venv or Hermes environment")
    require(Path(sys.executable).resolve() == PREFIX / "bin/python3.14",
            "Interpreter executable does not resolve to the pinned APT Python")
    require(platform.system() == expected["system"], "Unexpected native OS identity")
    import sysconfig
    require(sysconfig.get_platform() == expected["sysconfig_platform"],
            "Unexpected Android platform/ABI spelling")
    require(platform.android_ver().api_level == expected["api_level"],
            "Unexpected pinned Termux API level")
    require(sys.implementation.cache_tag == expected["cache_tag"]
            and not getattr(sys, "abiflags", "")
            and not sysconfig.get_config_var("Py_GIL_DISABLED"),
            "Unexpected CPython ABI")
    return {
        "executable": sys.executable, "prefix": sys.prefix,
        "version": platform.python_version(), "sys_platform": sys.platform,
        "system": platform.system(), "machine": os.uname().machine,
        "sysconfig_platform": sysconfig.get_platform(),
        "api_level": platform.android_ver().api_level,
        "cache_tag": sys.implementation.cache_tag,
    }


def archive_members(raw):
    require(raw[:8] == b"!<arch>\n", "Invalid Debian ar archive")
    offset, seen = 8, set()
    while offset < len(raw):
        header = raw[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b"\x60\n", "Invalid ar member header")
        name = header[:16].decode("ascii").strip().removesuffix("/")
        require(name and name not in seen and re.fullmatch(r"[A-Za-z0-9_.+-]+", name),
                "Invalid or duplicate ar member name")
        seen.add(name)
        require(header[48:58].strip().isdigit(), "Invalid ar member length")
        size = int(header[48:58])
        start, end = offset + 60, offset + 60 + size
        require(end <= len(raw), "Truncated ar member")
        yield name, raw[start:end]
        offset = end + size % 2
    require(offset == len(raw), "Invalid ar padding")


def tar_name(name):
    require("\\" not in name and "\0" not in name, "Invalid tar path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe tar member path")
    return "/" + path.as_posix().removeprefix("./").lstrip("/")


def control_record(raw):
    message = email.message_from_bytes(raw)
    result = {}
    for field in CONTROL_FIELDS:
        values = message.get_all(field, [])
        require(len(values) <= 1, f"Duplicate package control field: {field}")
        result[field] = values[0] if values else None
    return result


def inspect_archive(path, pin, wanted, *, include_pip=False):
    """Read verified bytes only; no extraction, dpkg install, or package import."""
    raw = read_regular(path, pin["bytes"])
    require(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"],
            f"APT archive bytes differ: {pin['package']}")
    result, controls, data_archives = {}, [], 0
    for name, compressed in archive_members(raw):
        if not name.startswith(("control.tar", "data.tar")):
            continue
        is_data = name.startswith("data.tar")
        data_archives += int(is_data)
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(compressed), mode="r|*") as archive:
            for member in archive:
                normalized = tar_name(member.name)
                require(normalized not in seen, "Duplicate tar member")
                seen.add(normalized)
                if not is_data and normalized == "/control":
                    require(member.isfile() and member.size <= 100_000, "Invalid package control member")
                    controls.append(control_record(archive.extractfile(member).read()))
                selected = normalized in wanted
                if include_pip and normalized.startswith((SITE / "pip").as_posix() + "/"):
                    selected = member.isfile() and not normalized.endswith((".pyc", ".pyo"))
                if is_data and selected:
                    require(member.isfile(), f"Required archive member is not a regular file: {normalized}")
                    require(member.size <= 20_000_000, "Unexpected selected archive member size")
                    value = archive.extractfile(member).read()
                    require(len(value) == member.size, "Truncated selected archive member")
                    result[normalized] = value
    require(data_archives == 1 and controls == [pin["control"]],
            f"APT archive control identity differs: {pin['package']}")
    require(wanted.issubset(result), f"APT archive omits reviewed members: {pin['package']}")
    return result


def installed_control(pins):
    fields = ("Package", "Version", "Architecture", "db:Status-Status", "Depends", "Pre-Depends")
    format_text = "\t".join(chr(36) + "{" + field + "}" for field in fields) + "\n"
    command = [
        str(PREFIX / "bin/dpkg-query"), "--show", "--showformat=" + format_text,
        *[pin["package"] for pin in pins],
    ]
    child_env = dict(os.environ)
    child_env.pop("LD_LIBRARY_PATH", None)
    child_env.pop("LD_PRELOAD", None)
    completed = subprocess.run(command, check=True, capture_output=True, text=True,
                               timeout=20, env=child_env)
    records = {}
    for line in completed.stdout.splitlines():
        fields = line.split("\t")
        require(len(fields) == 6 and fields[3] == "installed", "APT package is not fully installed")
        name, version, arch, _, depends, pre_depends = fields
        require(name not in records, "Duplicate dpkg package identity")
        records[name] = {
            "Package": name, "Version": version, "Architecture": arch,
            "Depends": depends or None, "Pre-Depends": pre_depends or None,
        }
    require(set(records) == {p["package"] for p in pins}, "dpkg omitted or added a reviewed package")
    for pin in pins:
        require(records[pin["package"]] == pin["control"],
                f"Installed APT package control differs: {pin['package']}")
    return records



def check_apt_dependencies(report):
    """Ask APT to validate its installed graph without downloading or committing."""
    command = [
        str(PREFIX / "bin/apt-get"), "--simulate",
        "-o", "Debug::NoLocking=true",
        "-o", "Dir::Cache::pkgcache=",
        "-o", "Dir::Cache::srcpkgcache=", "check",
    ]
    child_env = dict(os.environ)
    child_env.pop("LD_LIBRARY_PATH", None)
    child_env.pop("LD_PRELOAD", None)
    record = {"status": "failed", "argv": command, "exit_code": None, "timed_out": False}
    stdout, stderr = b"", b""
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, env=child_env)
        stdout, stderr = result.stdout, result.stderr
        record["exit_code"] = result.returncode
        if result.returncode == 0:
            record["status"] = "passed"
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        record["timed_out"] = True
    except OSError as exc:
        record["launch_error"] = {"type": type(exc).__name__, "message": str(exc)}
    record.update({
        "stdout": stdout.decode("utf-8", "backslashreplace"),
        "stderr": stderr.decode("utf-8", "backslashreplace"),
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
    })
    report["apt_dependencies"] = record
    require(record["status"] == "passed", "APT dependency graph validation failed", details=record)
    return record

def collect_owners(wanted):
    owners = {path: [] for path in wanted}
    directory = PREFIX / "var/lib/dpkg/info"
    for listing in directory.glob("*.list"):
        package = listing.name.removesuffix(".list")
        require(not listing.is_symlink(), "Symlinked dpkg ownership list")
        for line in listing.read_text(encoding="utf-8").splitlines():
            if line in owners and package not in owners[line]:
                owners[line].append(package)
    return owners


def verify_installed_files(expected, owners, *, root=Path("/")):
    results = []
    for path, row in sorted(expected.items()):
        actual = Path(root) / path.lstrip("/")
        require(actual.resolve() == actual.absolute(), f"Symlink in installed provenance path: {path}")
        raw = read_regular(actual, max(row["bytes"], 1))
        require(len(raw) == row["bytes"] and digest(raw) == row["sha256"],
                f"Installed APT file bytes differ: {path}")
        require(owners.get(path) == [row["package"]], f"APT ownership differs or is ambiguous: {path}")
        results.append({"path": path, **row})
    return results


def apt_provenance(manifest, archives):
    rows = manifest["apt_distributions"]
    pins = manifest["runtime"]["archives"] + [row["apt"] for row in rows]
    installed = installed_control(pins)
    expected, archive_receipts = {}, []
    for pin in pins:
        package = pin["package"]
        wanted = {
            f["path"] for f in manifest["runtime"]["files"] if f["package"] == package
        }
        for row in rows:
            if row["apt"]["package"] == package:
                wanted.update((row["metadata"]["path"], row["wheel"]["path"]))
        matches = sorted(Path(archives).glob(package + "_*.deb"))
        require(len(matches) == 1, f"Missing or ambiguous exact archive: {package}")
        members = inspect_archive(matches[0], pin, wanted, include_pip=package == "python-pip")
        for path, raw in members.items():
            require(path not in expected, "Two APT archives claim the same selected file")
            expected[path] = {"bytes": len(raw), "sha256": digest(raw), "package": package}
        archive_receipts.append({
            "package": package, "version": pin["version"], "architecture": pin["architecture"],
            "archive": str(matches[0]), "bytes": pin["bytes"], "sha256": pin["sha256"],
            "control": installed[package], "verified_selected_files": len(members),
        })
    frozen_files = manifest["runtime"]["files"] + [
        member for row in rows for member in (row["metadata"], row["wheel"])
    ]
    for row in frozen_files:
        actual = expected.get(row["path"])
        require(actual is not None and actual["sha256"] == row["sha256"]
                and ("bytes" not in row or actual["bytes"] == row["bytes"]),
                f"Archive member differs from frozen ledger: {row['path']}")
    verified = verify_installed_files(expected, collect_owners(expected))
    return {
        "status": "passed", "archives": archive_receipts,
        "installed_files": verified,
        "installed_file_manifest_sha256": digest(
            json.dumps(verified, sort_keys=True, separators=(",", ":")).encode()
        ),
    }


def read_metadata_inventory(distributions, site, requirements, specifiers, versions, utils, marker_environment):
    inventory = {}
    for dist in distributions:
        metadata_dir = Path(dist._path)
        require(metadata_dir.is_dir() and not metadata_dir.is_symlink()
                and metadata_dir.name.endswith(".dist-info")
                and metadata_dir.parent.resolve() == Path(site).resolve(),
                "Distribution metadata is outside the single APT site-packages directory")
        raw = read_regular(metadata_dir / "METADATA")
        message = email.message_from_bytes(raw)
        for field in ("Name", "Version"):
            require(len(message.get_all(field, [])) == 1, f"Missing or duplicate metadata {field}")
        name = utils.canonicalize_name(message["Name"], validate=True)
        require(name not in inventory, f"Duplicate distribution metadata: {name}")
        version = versions.Version(message["Version"])
        declared_python = message.get_all("Requires-Python", [])
        require(len(declared_python) <= 1, f"Duplicate Requires-Python: {name}")
        if declared_python:
            require(specifiers.SpecifierSet(declared_python[0]).contains(
                marker_environment["python_full_version"], prereleases=True
            ), f"Requires-Python is incompatible: {name}")
        active = []
        for text in message.get_all("Requires-Dist", []):
            req = requirements.Requirement(text)
            if req.marker is None or req.marker.evaluate({**marker_environment, "extra": ""}):
                require(not req.extras and req.url is None,
                        f"Unreviewed extra or direct-URL dependency outside base-only scope: {name}: {req}")
                active.append(str(req))
        inventory[name] = {
            "name": str(message["Name"]), "version": str(version),
            "metadata_path": str(metadata_dir / "METADATA"), "metadata_sha256": digest(raw),
            "requires_python": declared_python, "active_requires_dist": active,
        }
    require(inventory, "Empty installed Python distribution inventory")
    return inventory


def check_dependency_graph(operations, inventory):
    package_set, parsing_problems = operations.create_package_set_from_installed()
    missing, conflicting = operations.check_package_set(package_set)
    details = {
        "parsing_problems": parsing_problems,
        "missing": {str(k): [str(v) for v in values] for k, values in missing.items()},
        "conflicting": {str(k): [str(v) for v in values] for k, values in conflicting.items()},
        "packages": {str(k): str(v.version) for k, v in package_set.items()},
        "ignore_callback_used": False,
    }
    require(parsing_problems is False and not missing and not conflicting,
            "Installed Python requirements are inconsistent or unreadable", details=details)
    require(set(package_set) == set(inventory), "pip and direct metadata inventories disagree")
    for name, row in inventory.items():
        require(str(package_set[name].version) == row["version"],
                f"pip selected different distribution metadata: {name}")
        require(sorted(map(str, package_set[name].dependencies)) == sorted(row["active_requires_dist"]),
                f"pip selected different requirement metadata: {name}")
    return {"status": "passed", **details}


def check_tag_convention(unsupported, supported, manifest, tags, inventory):
    expected = {row["name"]: row for row in manifest["apt_distributions"]}
    admitted, seen = [], set()
    for dist in unsupported:
        name = dist.canonical_name
        require(name in expected and name not in seen,
                f"Unknown or duplicate unsupported distribution: {name}")
        seen.add(name)
        row = expected[name]
        require(str(dist.version) == row["version"]
                and Path(dist.info_location) / "METADATA" == Path(row["metadata"]["path"])
                and inventory[name]["metadata_path"] == row["metadata"]["path"],
                f"Unsupported distribution identity differs: {name}")
        actual_text = dist.read_text("WHEEL")
        actual_tags = email.message_from_string(actual_text).get_all("Tag", [])
        require(actual_tags == row["wheel"]["tags"], f"Unsupported WHEEL tags changed: {name}")
        original = set().union(*(tags.parse_tag(value) for value in actual_tags))
        require(original and original.isdisjoint(supported),
                f"Legacy tag no longer has the recorded mismatch: {name}")
        equivalent = set()
        for tag in original:
            require(tag.platform == manifest["tag_convention"]["original_platform"],
                    f"Unreviewed unsupported platform tag: {name}")
            candidate = tags.Tag(tag.interpreter, tag.abi, manifest["tag_convention"]["native_platform"])
            require(candidate in supported,
                    f"The real native interpreter/ABI does not support the recorded convention: {name}")
            equivalent.add(candidate)
        admitted.append({
            "distribution": name, "version": row["version"],
            "original_tags": sorted(map(str, original)),
            "native_convention_tags": sorted(map(str, equivalent)),
            "authority": "exact APT archive/control/installed-byte ownership",
            "metadata_modified": False, "supported_tags_modified": False,
        })
    require(seen == set(expected), "Unsupported set differs from the exact seven-package convention")
    return {"status": "recorded-apt-convention", "distributions": sorted(admitted, key=lambda x: x["distribution"])}


def raw_pip_record(path, exit_code, manifest):
    raw = read_regular(path, 100_000)
    text = raw.decode("utf-8")
    expected = sorted(f"{row['name']} {row['version']} is not supported on this platform"
                      for row in manifest["apt_distributions"])
    require(exit_code == 1 and sorted(text.splitlines()) == expected,
            "Raw pip check differs from the exact retained platform failure")
    return {"exit_code": exit_code, "passed": False, "log_path": str(path),
            "bytes": len(raw), "sha256": digest(raw), "text": text}


def validate(manifest, archives, raw_log, raw_exit, report):
    report["runtime"] = native_runtime(manifest["runtime"])
    raw_bytes = read_regular(raw_log, 100_000)
    report["raw_pip_check"] = {
        "exit_code": raw_exit, "passed": raw_exit == 0, "log_path": str(raw_log),
        "bytes": len(raw_bytes), "sha256": digest(raw_bytes), "text": raw_bytes.decode("utf-8"),
    }
    report["apt_provenance"] = apt_provenance(manifest, archives)
    check_apt_dependencies(report)
    # The complete shipped pip source tree has been bound to the verified APT
    # archive before using its private, version-pinned dependency/check APIs.
    import pip
    from pip._internal.metadata import get_default_environment
    from pip._internal.operations import check as operations
    from pip._internal.utils.compatibility_tags import get_supported
    from pip._vendor import packaging
    from pip._vendor.packaging import markers, requirements, specifiers, tags, utils, version
    require(pip.__version__ == manifest["runtime"]["pip_version"]
            and packaging.__version__ == manifest["runtime"]["packaging_version"],
            "Unexpected pip or vendored packaging version")
    require(Path(pip.__file__).resolve() == SITE / "pip/__init__.py",
            "Unexpected pip import origin")
    environment = markers.default_environment()
    report["marker_environment"] = environment
    inventory = read_metadata_inventory(
        importlib.metadata.distributions(), SITE, requirements, specifiers, version, utils, environment
    )
    for row in manifest["apt_distributions"]:
        found = inventory.get(row["name"])
        require(found is not None and found["version"] == row["version"]
                and found["metadata_sha256"] == row["metadata"]["sha256"]
                and found["metadata_path"] == row["metadata"]["path"],
                f"Actual APT distribution selection differs: {row['name']}")
    report["installed_distributions"] = inventory
    report["requirements"] = check_dependency_graph(operations, inventory)
    supported = get_supported()
    sys_tags = list(tags.sys_tags())
    require(set(supported) == set(sys_tags), "pip and packaging supported-tag sets disagree")
    report["supported_tags"] = {
        "get_supported": list(map(str, supported)), "sys_tags": list(map(str, sys_tags)),
    }
    unsupported = list(operations.check_unsupported(
        get_default_environment().iter_installed_distributions(), supported
    ))
    report["apt_tag_convention"] = check_tag_convention(
        unsupported, set(supported), manifest, tags, inventory
    )
    report["raw_pip_check"] = raw_pip_record(raw_log, raw_exit, manifest)
    report["status"] = "requirements-and-provenance-passed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, default=Path(__file__).with_name("neutts_apt_python_metadata.json"))
    parser.add_argument("--pip-check-log", type=Path, required=True)
    parser.add_argument("--pip-check-exit-code", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {
        "schema_version": 1, "status": "failed",
        "overall_compatibility_passed": False,
        "native_behavior": {
            "status": "required-pending",
            "required_by_collector": [
                "installed Python-wheel file identities", "native ELF and loaded-library ownership",
                "Torch numerical/Conv1d", "Torchaudio resampling", "Torchcodec WAV decoding",
                "SciPy numerical/FFT", "llvmlite native JIT", "soxr resampling",
            ],
        },
        "engine_synthesis_tested": False, "pm_admission_changed": False,
        "metadata_modified": False, "supported_tags_modified": False,
        "metadata_ledger": {"path": str(args.metadata), "sha256": MANIFEST_SHA256},
        "raw_pip_check_input": {"path": str(args.pip_check_log), "exit_code": args.pip_check_exit_code},
    }
    code = 1
    try:
        require(not args.out.exists(), "Refusing to overwrite a stale validation receipt")
        manifest = load_manifest(args.metadata)
        validate(manifest, args.archives, args.pip_check_log, args.pip_check_exit_code, report)
        code = 0
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, ValidationError) and exc.details is not None:
            report["error"]["details"] = exc.details
    try:
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as exc:
        print(f"Could not write validation receipt: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "receipt": str(args.out),
                      "overall_compatibility_passed": False}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
