#!/usr/bin/env python3
"""Build six independent native dependencies after the unchanged NeuTTS foundation.

Preparation-only: exact source builds, isolated complete runtime subsets, actual
operations and a combined fourteen-distribution gate. No gated weights, NeuTTS
engine install, interpreter-bound change, admission change or release.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
from email.parser import BytesParser
from email.policy import compat32
import gzip
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import traceback
import zipfile

PREFIX = Path("/data/data/com.termux/files/usr")
SCRIPT_DIR = Path(__file__).resolve().parent
PREPARER_SHA256 = "7712d2aec739ae62b226cb0f1b9d868a12fdb046448d4cb1848505b495258fbe"
COMPONENT_HELPER_SHA256 = "6387ecead23b7777e879588d7e76bd4c8d462de5574de1d77092053efc596211"
APT_HELPER_SHA256 = "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29"
OPERATIONS_SHA256 = "ce18cd98cdba38695b26fe36958e7621812a54601522acce1f9734451f55e368"
ORDER = ("audioop-lts", "pyyaml", "pycryptodomex", "sentencepiece", "pandas", "scikit-learn")


class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected a regular non-symlink file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, maximum=8_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum,
            "Missing or oversized JSON evidence")
    return json.loads(path.read_bytes())


def save_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def module_at(name, path, digest):
    require(sha(path) == digest, "Reviewed support module changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def support():
    prep = module_at("_nonrust_preparer", SCRIPT_DIR / "prepare_neutts_nonrust_runtime.py", PREPARER_SHA256)
    common = module_at("_nonrust_native_common", SCRIPT_DIR / "compatibility_probe_phonemizer.py",
                       COMPONENT_HELPER_SHA256)
    apt = module_at("_nonrust_apt_common", SCRIPT_DIR / "validate_neutts_apt_python.py", APT_HELPER_SHA256)
    return prep, common, apt


def closure_names(lock, roots):
    names = set(roots)
    require(names <= set(lock["names"]), "Unreviewed component root")
    while True:
        expanded = names | {edge["to"] for edge in lock["edges"] if edge["from"] in names}
        if expanded == names:
            return names
        names = expanded


def clean_environment(lock, build_python=None):
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                "LD_PRELOAD", "CIBUILDWHEEL", "CMAKE_TOOLCHAIN_FILE", "CMAKE_ARGS",
                "CMAKE_PREFIX_PATH", "MESON_CROSS_FILE", "MESON_ARGS", "PKG_CONFIG_PATH",
                "PIP_EXTRA_INDEX_URL", "PIP_INDEX_URL", "SKLEARN_NO_OPENMP",
                "CPPFLAGS", "LDSHARED", "ARCHFLAGS", "SDKROOT"):
        env.pop(key, None)
    path = str(PREFIX / "bin")
    if build_python is not None:
        path = str(build_python.parent) + os.pathsep + path
    env.update({
        "PATH": path, "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "TMPDIR": str(PREFIX / "tmp"),
        "CC": str(PREFIX / "bin/clang"), "CXX": str(PREFIX / "bin/clang++"),
        "CFLAGS": lock["build"]["cflags"], "CXXFLAGS": lock["build"]["cflags"],
        "LDFLAGS": lock["build"]["ldflags"], "MAKEFLAGS": "-j2",
        "CMAKE_BUILD_PARALLEL_LEVEL": "2", "MAX_JOBS": "2",
        "NINJA": str(PREFIX / "bin/ninja"), "OMP_NUM_THREADS": "2",
        "OMP_DYNAMIC": "FALSE", "OPENBLAS_NUM_THREADS": "2", "LOKY_MAX_CPU_COUNT": "2",
        "SOURCE_DATE_EPOCH": str(lock["build"]["source_date_epoch"]),
        "HF_HUB_OFFLINE": "1",
    })
    return env


def native_runtime(common):
    result = common.native_runtime()
    import sysconfig
    require(not sysconfig.get_config_var("Py_GIL_DISABLED"), "Free-threaded ABI is outside this exact source selection")
    require("_PYTHON_HOST_PLATFORM" not in os.environ, "Native platform tags must not be overridden")
    return result


def snapshot_metadata(snapshot, lock):
    frozen = {p["filename"]: p for p in lock["build_apt"]["snapshot"]}
    for filename, pin in frozen.items():
        path = snapshot / filename
        require(path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"],
                "Frozen signed index bytes differ")
    release = (snapshot / "InRelease").read_text()
    section, rows = False, []
    for line in release.splitlines():
        if line == "SHA256:":
            section = True
            continue
        if section and line and not line[0].isspace():
            section = False
        if section:
            match = re.fullmatch(r"\s+([0-9a-f]{64})\s+([0-9]+)\s+(\S+)", line)
            if match and match[3] == "main/binary-aarch64/Packages.gz":
                rows.append((match[1], int(match[2])))
    require(rows == [(frozen["Packages.gz"]["sha256"], frozen["Packages.gz"]["bytes"])],
            "InRelease does not bind the exact Packages.gz")
    with gzip.GzipFile(fileobj=io.BytesIO((snapshot / "Packages.gz").read_bytes())) as stream:
        packages_raw = stream.read(32_000_001)
    require(len(packages_raw) <= 32_000_000, "Expanded APT index exceeds bound")
    records = {}
    for block in packages_raw.decode().split("\n\n"):
        if not block.strip():
            continue
        fields = BytesParser(policy=compat32).parsebytes(block.encode())
        if fields.get("Architecture") in ("aarch64", "all"):
            key = (fields["Package"], fields["Version"], fields["Architecture"], fields["Filename"])
            require(key not in records, "Duplicate target APT package identity")
            records[key] = fields
    for pin in lock["build_apt"]["packages"]:
        row = records.get((pin["name"], pin["version"], pin["architecture"], pin["filename"]))
        require(row is not None and (row["Version"], row["Architecture"], row["Filename"],
                row["SHA256"], int(row["Size"])) == (pin["version"], pin["architecture"],
                pin["filename"], pin["sha256"], pin["bytes"]), "APT source index pin differs")
    return frozen, packages_raw


def signed_snapshot(args, lock, common, work):
    snapshot = args.inputs / "snapshot"
    frozen, packages_raw = snapshot_metadata(snapshot, lock)
    repo, lists = work / "signed-repository", work / "apt-lists"
    (repo / "dists/stable/main/binary-aarch64").mkdir(parents=True)
    lists.mkdir()
    (lists / "partial").mkdir()
    shutil.copyfile(snapshot / "InRelease", repo / "dists/stable/InRelease")
    shutil.copyfile(snapshot / "Packages.gz", repo / "dists/stable/main/binary-aarch64/Packages.gz")
    sources = work / "frozen.list"
    sources.write_text("deb [arch=aarch64] " + repo.as_uri() + " stable main\n")
    options = [
        "-o", "Dir::Etc::sourcelist=" + str(sources), "-o", "Dir::Etc::sourceparts=-",
        "-o", "Dir::State::lists=" + str(lists), "-o", "Acquire::Languages=none",
        "-o", "Acquire::AllowInsecureRepositories=false",
        "-o", "Acquire::AllowDowngradeToInsecureRepositories=false",
        "-o", "Acquire::AllowWeakRepositories=false", "-o", "APT::Get::AllowUnauthenticated=false",
        "-o", "APT::Update::Error-Mode=any",
    ]
    record = common.bounded_command([str(PREFIX / "bin/apt-get"), *options, "update"],
                                    args.out, "nonrust-frozen-signed-index", 90)
    releases = list(lists.glob("*_InRelease"))
    require(len(releases) == 1 and sha(releases[0]) == frozen["InRelease"]["sha256"],
            "APT did not retain the exact authenticated InRelease")
    indexes = [p for p in lists.iterdir()
               if p.name.endswith(("_Packages", "_Packages.lz4", "_Packages.gz"))]
    require(len(indexes) == 1, "APT did not acquire one exact target package index")
    loaded = subprocess.run([str(PREFIX / "lib/apt/apt-helper"), "cat-file", str(indexes[0])],
                            capture_output=True, timeout=30, check=False)
    require(loaded.returncode == 0 and loaded.stdout == packages_raw and not loaded.stderr,
            "APT-acquired package index differs from the signed bytes")
    return options, {"status": "passed", "authority": "native APT configured trust store",
                     "insecure_repository_exceptions": False, "apt_update": record,
                     "inrelease_sha256": frozen["InRelease"]["sha256"],
                     "packages_gz_sha256": frozen["Packages.gz"]["sha256"],
                     "packages_uncompressed_sha256": hashlib.sha256(packages_raw).hexdigest(),
                     "matched_archives": 51}


def verify_archive_set(args, lock, common):
    packages = lock["build_apt"]["packages"]
    names, rows = set(), []
    for pin in packages:
        path = common.archive_path(args.apt_archives, pin)
        require(path.name == Path(pin["filename"]).name, "APT archive basename differs")
        # This also validates the exact control, even when no payload member is requested.
        common.ar_data_members(path, pin, set())
        names.add(path.name)
        rows.append({"name": pin["name"], "version": pin["version"],
                     "path": str(path), "bytes": pin["bytes"], "sha256": pin["sha256"]})
    require(names == {p.name for p in args.apt_archives.glob("*.deb")} and len(names) == 51,
            "Expected exactly 51 retained APT archives")
    return rows


def install_toolchain(args, lock, common, options):
    pins = lock["build_apt"]["packages"]
    existing = [p for p in pins if not p["additional"]]
    additions = [p for p in pins if p["additional"]]
    require(len(existing) == 30 and len(additions) == 21, "Reviewed compiler addition set differs")
    before = common.package_snapshot([p["name"] for p in existing])
    expected_existing = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                                    "status": "installed"} for p in existing}
    require(before == expected_existing, "Existing foundation/compiler overlap changed")
    command = [
        str(PREFIX / "bin/apt-get"), *options,
        "-o", "Dir::Cache::archives=" + str(args.apt_archives),
        "-o", "Dpkg::Options::=--force-confnew", "--no-download", "--no-remove",
        "--no-install-recommends", "--reinstall", "install",
        *(p["name"] + "=" + p["version"] for p in additions),
    ]
    plan = common.bounded_command(command[:1] + ["-s"] + command[1:],
                                  args.out, "nonrust-apt-plan", 90)
    text = (args.out / "nonrust-apt-plan.stdout.log").read_text()
    require(not any(line.startswith("Remv ") for line in text.splitlines()), "APT proposed a removal")
    proposed = [line.split()[1].split(":", 1)[0] for line in text.splitlines() if line.startswith("Inst ")]
    require(len(proposed) == len(set(proposed)) and set(proposed) == {p["name"] for p in additions},
            "APT proposed an unreviewed addition, upgrade, or omission")
    installed = common.bounded_command(command[:1] + ["-y"] + command[1:],
                                       args.out, "nonrust-apt-install", 300)
    after = common.package_snapshot([p["name"] for p in pins])
    expected = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                           "status": "installed"} for p in pins}
    require(after == expected, "Installed 51-package dependency closure differs")
    return {"status": "passed", "additional_count": 21,
            "new_to_existing_141": ["libyaml", "patchelf"],
            "plan": plan, "install": installed, "installed_packages": after}


def verify_build_files(args, lock, common, apt):
    pins = {p["name"]: p for p in lock["build_apt"]["packages"]}
    expected = lock["build_apt"]["native_build_files"]
    paths = {"/" + row["path"] for row in expected}
    owners = apt.collect_owners(paths)
    grouped = {}
    for row in expected:
        name = "/" + row["path"]
        require(owners.get(name) == [row["package"]], "Build header/library/program ownership differs")
        grouped.setdefault(row["package"], set()).add(name)
    reports = []
    for package, wanted in grouped.items():
        pin = pins[package]
        members = common.ar_data_members(common.archive_path(args.apt_archives, pin), pin, wanted)
        for name, value in members.items():
            row = next(row for row in expected if "/" + row["path"] == name)
            require(len(value) == row["bytes"] and hashlib.sha256(value).hexdigest() == row["sha256"]
                    and Path(name).read_bytes() == value, "Installed build file differs from official archive")
            reports.append({"package": package, "path": name, "bytes": len(value), "sha256": row["sha256"]})
    result = subprocess.run([str(PREFIX / "bin/patchelf"), "--version"],
                            capture_output=True, text=True, timeout=15, check=False)
    require(result.returncode == 0 and result.stdout.strip() == "patchelf 0.19.2",
            "Actual Android patchelf program differs")
    return {"status": "passed", "files": reports, "patchelf_version": result.stdout.strip(),
            "openmp_linkage": "Exact clang-supplied static archive, no invented shared library"}


def copy_apt_python(args, lock, names, site, prep, common):
    reports = []
    for expected in lock["apt_python"]:
        if expected["name"] not in names:
            continue
        pin = expected["archive"]
        path = common.archive_path(args.apt_archives, pin)
        facts, contents = prep.apt_python_payload(path, pin, include_bytes=True)
        require(all(facts[key] == expected[key] for key in facts), "Official APT Python payload manifest differs")
        for row in expected["files"]:
            destination = site.joinpath(*row["path"].split("/"))
            prep.write_new(destination, contents[row["path"]])
            destination.chmod(0o755 if row["mode"] == "100755" else 0o644)
        reports.append({"name": expected["name"], "archive_sha256": pin["sha256"],
                        "file_count": expected["file_count"], "bytes": expected["bytes"],
                        "metadata_sha256": expected["metadata_sha256"],
                        "metadata_changed": False, "record_changed": False,
                        "copy_mode_policy": "preserve executable bit, normalize ordinary copied permissions"})
    return reports


def installed_wheel_bytes(path, package, site, prep):
    prep.verify_wheel(path, package)
    owned, verified, rewrites, external = set(), [], [], []
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            parts = prep.safe_relative(item.filename).split("/")
            target, script = site.joinpath(*parts), False
            if parts[0].endswith(".data"):
                require(len(parts) >= 3, "Malformed wheel data scheme")
                scheme = parts[1]
                if scheme in ("purelib", "platlib"):
                    target = site.joinpath(*parts[2:])
                elif scheme == "scripts":
                    target = site.parents[2] / "bin" / Path(*parts[2:])
                    script = True
                elif scheme == "data":
                    target = site.parents[2].joinpath(*parts[2:])
                else:
                    raise ProbeError("Unreviewed installed wheel data scheme")
            require(target.resolve() == target.absolute() and target.is_file(),
                    "Installed wheel file missing or reached through a symlink")
            if item.filename.endswith(".dist-info/RECORD"):
                require(target.is_relative_to(site), "Installation RECORD escaped site")
                owned.add(target.relative_to(site).as_posix())
                rewrites.append({"path": item.filename, "reason": "pip installation RECORD"})
                continue
            before, after = archive.read(item), target.read_bytes()
            if before != after:
                require(script and before.startswith((b"#!python\n", b"#!pythonw\n"))
                        and after.startswith(b"#!") and before.split(b"\n", 1)[1] == after.split(b"\n", 1)[1],
                        "Installed wheel file bytes changed")
                rewrites.append({"path": item.filename, "reason": "pip script shebang",
                                 "installed_sha256": hashlib.sha256(after).hexdigest()})
            else:
                verified.append(item.filename)
            if target.is_relative_to(site):
                owned.add(target.relative_to(site).as_posix())
            else:
                require(target.is_relative_to(site.parents[2]), "Wheel data escaped isolated prefix")
                external.append({"path": str(target), "sha256": hashlib.sha256(after).hexdigest()})
    return {"owned_paths": owned, "verified_file_count": len(verified),
            "documented_rewrites": rewrites, "verified_external_data": external}


def installed_inventory(manifest, prep, common):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(sys.prefix != sys.base_prefix and Path(sys.base_prefix).resolve() == PREFIX
            and str(PREFIX / "lib/python3.14/site-packages") not in sys.path,
            "Isolated environment exposed global APT site-packages")
    expected = {p["name"]: p for p in manifest["wheels"] + manifest["apt_python"]}
    require(len(expected) == len(manifest["names"]) and set(expected) == set(manifest["names"]),
            "Installation closure is inconsistent")
    distributions = list(importlib.metadata.distributions())
    require(len(distributions) == len(expected), "Missing or extra visible distribution")
    seen, allowed, reports = set(), set(), []
    apt_names = {p["name"] for p in manifest["apt_python"]}
    for dist in distributions:
        name = prep.canonical_name(dist.metadata["Name"])
        require(name in expected and name not in seen, "Unexpected or duplicate distribution")
        seen.add(name)
        package = expected[name]
        metadata_dir = Path(dist._path)
        require(metadata_dir.parent.resolve() == site.resolve() and not metadata_dir.is_symlink(),
                "Metadata selected outside isolated site")
        require(dist.version == package["version"], "Installed distribution version differs")
        if name in apt_names:
            require(metadata_dir / "METADATA" == site / package["metadata_member"],
                    "Copied APT metadata location differs")
            allowed.update(row["path"] for row in package["files"])
            for row in package["files"]:
                path = site / row["path"]
                raw = prep.read_regular(path, row["bytes"])
                require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                        "Copied APT Python file changed")
            reports.append({"name": name, "version": dist.version,
                            "authority": "complete exact APT Python payload copy",
                            "files": package["file_count"], "bytes": package["bytes"],
                            "original_metadata_sha256": package["metadata_sha256"],
                            "original_tags": package["original_apt_ledger"]["wheel"]["tags"],
                            "metadata_modified": False})
        else:
            raw = prep.read_regular(metadata_dir / "METADATA", 2_000_000)
            require(hashlib.sha256(raw).hexdigest() == package["wheel"]["metadata_sha256"],
                    "Installed wheel metadata changed")
            record = installed_wheel_bytes(Path(package["wheel_path"]), package, site, prep)
            allowed.update(record.pop("owned_paths"))
            for filename in ("INSTALLER", "REQUESTED", "direct_url.json"):
                path = metadata_dir / filename
                if not path.exists():
                    continue
                raw = prep.read_regular(path, 200_000)
                if filename == "INSTALLER":
                    require(raw == b"pip\n", "Unexpected installer")
                elif filename == "REQUESTED":
                    require(raw == b"", "Unexpected REQUESTED data")
                else:
                    value = json.loads(raw)
                    require(value.get("archive_info", {}).get("hashes", {}).get("sha256")
                            == package["artifact"]["sha256"], "Installed direct URL hash changed")
                allowed.add(path.relative_to(site).as_posix())
            reports.append({"name": name, "version": dist.version, "authority": "exact verified wheel",
                            "wheel_sha256": package["artifact"]["sha256"],
                            "verified_file_count": record["verified_file_count"],
                            "documented_rewrites": record["documented_rewrites"],
                            "verified_external_data": record["verified_external_data"]})
        require(dist.metadata.get_all("Requires-Dist", []) == package["requires_dist"]
                and dist.metadata.get("Requires-Python", "") == package["requires_python"],
                "Installed dependency/interpreter declarations changed")
    actual = set()
    for path in site.rglob("*"):
        require(not path.is_symlink(), "Unreviewed site symlink")
        if path.is_file():
            actual.add(path.relative_to(site).as_posix())
        else:
            require(path.is_dir(), "Unreviewed site special file")
    require(actual == allowed, "Unowned or missing isolated site files")
    return {"status": "passed", "actual_visible_distribution_count": len(seen),
            "actual_names": sorted(seen), "verified_site_files": len(actual),
            "distributions": sorted(reports, key=lambda r: r["name"]),
            "global_site_visible": False, "declared_metadata_modified": False}


def raw_pip_check(python, names, lock, out, common, env):
    command = common.pip_command(python) + ["check"]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=90, check=False, env=env)
    raw = result.stdout + result.stderr
    require(len(raw) <= 100_000, "Unexpected pip check output size")
    log = out / "RAW-PIP-CHECK.log"
    log.write_bytes(raw)
    apt_rows = [p for p in lock["apt_python"] if p["name"] in names]
    expected = sorted(f"{p['name']} {p['version']} is not supported on this platform" for p in apt_rows)
    if apt_rows:
        require(result.returncode == 1 and sorted(raw.decode().splitlines()) == expected,
                "Raw pip check has an unreviewed failure")
        from pip._vendor.packaging import tags
        supported = set(tags.sys_tags())
        convention = []
        for p in apt_rows:
            original = set().union(*(tags.parse_tag(v) for v in p["original_apt_ledger"]["wheel"]["tags"]))
            require(original and original.isdisjoint(supported), "Recorded APT tag mismatch changed")
            equivalent = []
            for tag in original:
                require(tag.platform == "android_aarch64", "Unreviewed legacy APT platform")
                candidate = tags.Tag(tag.interpreter, tag.abi, "android_24_arm64_v8a")
                require(candidate in supported, "Actual APT interpreter/ABI does not support original convention")
                equivalent.append(str(candidate))
            convention.append({"name": p["name"], "original_tags": sorted(map(str, original)),
                               "native_convention_tags": sorted(equivalent),
                               "metadata_modified": False, "supported_tags_modified": False})
    else:
        require(result.returncode == 0 and raw.decode().strip() == "No broken requirements found.",
                "Isolated source-only runtime pip check failed")
        convention = []
    return {"exit_code": result.returncode, "pip_check_passed": result.returncode == 0,
            "requirements_have_no_missing_or_conflicting_dependencies": True,
            "elapsed_seconds": round(time.monotonic() - started, 3), "log": log.name,
            "sha256": sha(log), "text": raw.decode(), "original_apt_tag_diagnostics": convention,
            "authority": "copied file manifests and exact APT provenance are separate required gates"}


def create_environment(args, lock, wheels, apt_names, destination, out, label, prep, common, env):
    common.bounded_command([str(PREFIX / "bin/python"), "-I", "-B", "-m", "venv",
                            "--without-pip", str(destination)], out, label + "-venv", 60, env)
    require("include-system-site-packages = false" in (destination / "pyvenv.cfg").read_text(),
            "New environment exposed the global site")
    site = destination / "lib/python3.14/site-packages"
    copies = copy_apt_python(args, lock, apt_names, site, prep, common)
    python = destination / "bin/python"
    requirements = out / (label + "-requirements.txt")
    prep.write_new(requirements, prep.base_helper().requirement_text(wheels))
    links = sorted({str(Path(p["wheel_path"]).parent) for p in wheels})
    command = common.pip_command(python) + [
        "install", "--no-index", "--no-deps", "--require-hashes", "--only-binary=:all:",
        "--no-compile", "--no-cache-dir",
    ]
    for link in links:
        command += ["--find-links", link]
    command += ["-r", str(requirements)]
    common.bounded_command(command, out, label + "-wheel-install", 180, env)
    selected_apt = [p for p in lock["apt_python"] if p["name"] in apt_names]
    manifest = {"schema_version": 1, "names": sorted([p["name"] for p in wheels] + list(apt_names)),
                "wheels": wheels, "apt_python": selected_apt, "copied_apt_payloads": copies}
    path = out / (label + "-installed-closure.json")
    save_json(path, manifest)
    return python, path, manifest


def validate_build_requirements(values, versions, marker_environment, extras=("",)):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    rows = []
    for value in values:
        requirement = Requirement(value)
        require(requirement.url is None, "Unreviewed dynamic URL build dependency")
        active = any(not requirement.marker or requirement.marker.evaluate({**marker_environment, "extra": extra})
                     for extra in extras)
        name = canonicalize_name(requirement.name)
        if active:
            require(name in versions and requirement.specifier.contains(versions[name]),
                    "Build requirement is missing or incompatible: " + value)
        rows.append({"requirement": value, "active": active,
                     "selected_version": versions.get(name), "selected_extras": sorted(requirement.extras)})
    return rows


def openmp_probe(args, lock, common, work):
    source = work / "openmp-control.c"
    source.write_text(
        '#include <stdio.h>\n#include <omp.h>\n'
        'int main(void) { int threads = 0; long long total = 0;\n'
        '#pragma omp parallel num_threads(2) reduction(+:total)\n'
        '{\n#pragma omp single\nthreads = omp_get_num_threads();\n'
        '#pragma omp for\nfor (int i=0; i<100; ++i) total += i;\n}\n'
        'printf("{\\"threads\\":%d,\\"sum\\":%lld}\\n", threads, total);\n'
        'return threads == 2 && total == 4950 ? 0 : 1; }\n')
    output = work / "openmp-control"
    compile_result = common.bounded_command([
        str(PREFIX / "bin/clang"), *shlex.split(lock["build"]["cflags"]), "-fopenmp",
        str(source), "-o", str(output), *shlex.split(lock["build"]["ldflags"]),
        "-Wl,-rpath," + str(PREFIX / "lib")], args.out, "openmp-control-build", 60)
    execution = common.bounded_command([str(output)], args.out, "openmp-control-run", 30)
    result = json.loads((args.out / "openmp-control-run.stdout.log").read_text())
    require(result == {"threads": 2, "sum": 4950}, "Actual two-thread OpenMP reduction failed")
    return {"status": "passed", "result": result, "binary": common.elf(output, dynamic=True),
            "compile": compile_result, "execution": execution}


def patchelf_probe(args, lock, common, work):
    import mesonpy._rpath
    require(sys.platform == "android", "RPATH control must exercise the actual Android ELF branch")
    source, library = work / "rpath-control.c", work / "rpath-control.so"
    source.write_text("int component_value(void) { return 42; }\n")
    before = "$ORIGIN/before:" + str(PREFIX / "lib")
    command = [str(PREFIX / "bin/clang"), *shlex.split(lock["build"]["cflags"]),
               "-shared", str(source), "-o", str(library), "-Wl,-rpath," + before]
    report = {"schema_version": 1, "status": "failed", "platform": sys.platform,
              "seed_rpath": before, "source": str(source), "library": str(library)}
    try:
        # Preserve the native driver's actual link command and initial RPATH.
        # This control tests Meson's repair, independently of compiler defaults.
        report["compiler_trace"] = common.bounded_command(
            [*command, "-###"], args.out, "rpath-control-linker-trace", 60)
        report["compile"] = common.bounded_command(
            command, args.out, "rpath-control-build", 60)
        report["compiler_binary"] = common.elf(library, dynamic=True)
        report["compiler_rpath"] = subprocess.check_output(
            [str(PREFIX / "bin/patchelf"), "--print-rpath", str(library)],
            text=True, timeout=15).strip()
        report["seed_process"] = common.bounded_command(
            [str(PREFIX / "bin/patchelf"), "--set-rpath", before, str(library)],
            args.out, "rpath-control-seed", 30)
        initial = subprocess.check_output(
            [str(PREFIX / "bin/patchelf"), "--print-rpath", str(library)],
            text=True, timeout=15).strip()
        report["before"] = initial
        report["before_sha256"] = sha(library)
        require(initial == before, "ELF RPATH control seed differs: " + repr(initial))
        mesonpy._rpath.fix_rpath(library, "after")
        after = subprocess.check_output(
            [str(PREFIX / "bin/patchelf"), "--print-rpath", str(library)],
            text=True, timeout=15).strip()
        report["after"] = after
        require(after == "$ORIGIN/after:" + str(PREFIX / "lib"),
                "Actual Android backend RPATH repair failed: " + repr(after))
        loaded = ctypes.CDLL(str(library))
        loaded.component_value.argtypes = []
        loaded.component_value.restype = ctypes.c_int
        report["native_function_result"] = loaded.component_value()
        require(report["native_function_result"] == 42, "Repaired Android ELF did not execute")
        report["after_binary"] = common.elf(library, dynamic=True)
        report["backend_version"] = importlib.metadata.version("meson-python")
        report["status"] = "passed"
        return report
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        save_json(args.out / "RPATH-CONTROL-RESULT.json", report)


def build_one(args, lock, prep, common):
    native_runtime(common)
    source = next(p for p in lock["sources"] if p["name"] == args.source_name)
    manifest = read_json(args.environment_manifest)
    require(len(manifest["names"]) == 11 and set(manifest["names"])
            == {p["name"] for p in lock["build_packages"]} | {"numpy", "scipy"},
            "Incomplete isolated build environment")
    inventory = installed_inventory(manifest, prep, common)
    versions = {p["name"]: p["version"] for p in manifest["wheels"] + manifest["apt_python"]}
    require(args.source_root.is_dir() and args.wheel_dir.is_dir()
            and not any(args.wheel_dir.iterdir()), "Invalid isolated build paths")
    prep.verify_tree(args.source_root, source["prepared_files"])
    project = tomllib.loads((args.source_root / "pyproject.toml").read_text())["build-system"]
    require(project["requires"] == source["build_requires"]
            and project["build-backend"] == source["build_backend"]
            and project.get("backend-path", []) == source["backend_path"],
            "Source build declarations changed")
    requirements = validate_build_requirements(source["build_requires"], versions, lock["environment"])
    build_graph = []
    for package in lock["build_packages"]:
        build_graph += validate_build_requirements(package["requires_dist"], versions, lock["environment"],
                                                   extras=("toml",) if package["name"] == "versioneer" else ("",))
    controls = {}
    control_work = args.source_root.parent / ("controls-" + source["name"])
    control_work.mkdir()
    if source["name"] in ("pandas", "scikit-learn"):
        controls["android_rpath"] = patchelf_probe(args, lock, common, control_work)
    if source["name"] == "scikit-learn":
        controls["openmp"] = openmp_probe(args, lock, common, control_work)
    if source["name"] == "pyyaml":
        require(os.environ.get("PYYAML_FORCE_LIBYAML") == "1"
                and os.environ.get("PYYAML_FORCE_CYTHON") == "1",
                "PyYAML native/Cython requirements must not fall back silently")
    for relative in reversed(source["backend_path"]):
        prep.safe_relative(relative)
        backend_path = args.source_root / relative
        require(backend_path.is_dir() and backend_path.resolve().is_relative_to(args.source_root.resolve()),
                "Build backend path escaped source")
        sys.path.insert(0, str(backend_path))
    os.chdir(args.source_root)
    backend = importlib.import_module(source["build_backend"])
    settings = {"compile-args": ["-j2", "-v"]} if source["build_backend"] == "mesonpy" else {}
    dynamic = backend.get_requires_for_build_wheel(config_settings=settings)
    require(isinstance(dynamic, list) and all(isinstance(v, str) for v in dynamic),
            "Unreviewed dynamic backend requirement type")
    dynamic_report = validate_build_requirements(dynamic, versions, lock["environment"])
    filename = backend.build_wheel(str(args.wheel_dir), config_settings=settings)
    require(isinstance(filename, str) and filename == Path(filename).name and filename.endswith(".whl")
            and {p.name for p in args.wheel_dir.iterdir()} == {filename},
            "Source backend emitted unreviewed output")
    if source["name"] == "sentencepiece":
        cache = args.source_root / "build/CMakeCache.txt"
        require(cache.is_file(), "Missing actual bundled SentencePiece CMake cache")
        flags = [line for line in cache.read_text().splitlines() if line.startswith("CMAKE_CXX_FLAGS:STRING=")]
        require(len(flags) == 1 and all(flag in shlex.split(flags[0].split("=", 1)[1])
                for flag in ("--target=aarch64-linux-android24", "-march=armv8-a", "-fPIC",
                             "-fvisibility=default", "-ffunction-sections", "-fdata-sections")),
                "Bundled SentencePiece compiler flags were lost")
        controls["sentencepiece_flags"] = {"cache_sha256": sha(cache), "actual_cxx_flags": flags[0],
                                           "CMAKE_BUILD_PARALLEL_LEVEL": os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL")}
    report = {"schema_version": 1, "status": "passed", "component": source["name"],
              "source_archive_sha256": source["artifact"]["sha256"], "wheel": filename,
              "declared_build_requirements": requirements, "build_graph": build_graph,
              "dynamic_build_requirements": dynamic_report, "build_environment": inventory,
              "actual_native_controls": controls, "platform": sys.platform,
              "platform_override_used": False}
    save_json(args.out / "SOURCE-BACKEND-RESULT.json", report)
    return 0


def built_wheel(path, source, prep):
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import parse_tag, sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
    facts = prep.wheel_facts(path)
    name, version, build, tags = parse_wheel_filename(path.name)
    require(name == source["name"] == facts["name"] and str(version) == source["version"] == facts["version"]
            and not build, "Built distribution identity differs")
    require(facts["wheel"]["tags"] == [source["expected_tag"]]
            and tags == parse_tag(source["expected_tag"]) and tags <= set(sys_tags())
            and facts["wheel"]["root_is_purelib"] is False, "Unsupported or altered native wheel tag")
    require(SpecifierSet(facts["requires_python"]) == SpecifierSet(source["requires_python"])
            and SpecifierSet(facts["requires_python"]).contains("3.14.6"),
            "Built interpreter declaration changed")
    def key(value):
        req = Requirement(value)
        require(req.url is None, "Unreviewed runtime URL requirement")
        return canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)), str(req.marker or "")
    require(sorted(map(key, facts["requires_dist"])) == sorted(map(key, source["requires_dist"])),
            "Source wheel changed declared runtime dependencies")
    require(facts["native_members"], "Source silently emitted no native extension")
    if source["name"] == "audioop-lts":
        require([item["member"] for item in facts["native_members"]] == ["audioop/_audioop.abi3.so"],
                "Built audioop extension namespace differs from the exact source")
    prefix = {"audioop-lts": "audioop/_audioop.", "pandas": "pandas/", "pycryptodomex": "Cryptodome/",
              "pyyaml": "yaml/", "scikit-learn": "sklearn/", "sentencepiece": "sentencepiece/"}[source["name"]]
    with zipfile.ZipFile(path) as archive:
        for member in facts["native_members"]:
            raw = archive.read(member["member"])
            require(member["member"].startswith(prefix) and raw[:6] == b"\x7fELF\x02\x01"
                    and len(raw) >= 64 and struct.unpack_from("<H", raw, 18)[0] == 183,
                    "Built native extension has a foreign namespace or ABI")
    return facts


def validate_source_image(args, lock):
    """Bind image-owned members to the host's actual immutable image selection."""
    origin = lock["platform_runtime"]
    inputs = read_json(args.image_receipt, 1_000_000)
    require(inputs.get("schema_version") == 1
            and inputs.get("native_image") == origin["native_image"],
            "Native source-image identity differs")
    expected_inputs = {
        "scripts/compatibility_probe_neutts_nonrust.py": sha(Path(__file__).resolve()),
        "scripts/compatibility_probe_neutts_nonrust.sh": sha(SCRIPT_DIR / "compatibility_probe_neutts_nonrust.sh"),
        "scripts/prepare_neutts_nonrust_runtime.py": PREPARER_SHA256,
        "scripts/neutts_nonrust_runtime_lock.json": sha(args.inputs / "neutts_nonrust_runtime_lock.json"),
    }
    require(all(inputs.get("inputs", {}).get(name) == digest
                for name, digest in expected_inputs.items()),
            "Source-image input ledger differs from the executing preparation")
    inspection_path = args.image_receipt.parent / "NONRUST-SOURCE-IMAGE.json"
    inspected = read_json(inspection_path, 2_000_000)
    require(isinstance(inspected, list) and len(inspected) == 1, "Ambiguous Docker image inspection")
    image = inspected[0]
    require(image.get("Architecture") == "arm64" and image.get("Os") == "linux"
            and origin["native_image"] in image.get("RepoDigests", [])
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("Id", "")),
            "Inspected Docker image differs from the reviewed ARM64 image")
    return {"status": "verified-pinned-image", "native_image": origin["native_image"],
            "docker_image_id": image["Id"], "architecture": image["Architecture"],
            "input_receipt": str(args.image_receipt), "input_receipt_sha256": sha(args.image_receipt),
            "inspection": str(inspection_path), "inspection_sha256": sha(inspection_path)}


def verify_image_platform_members(paths, lock, common, apt):
    """Verify exact image-owned AOSP files separately from downloaded APT files."""
    platform = lock["platform_runtime"]
    pins = {Path(pin["path"]): pin for pin in platform["files"]}
    require(len(pins) == 5 and len(pins) == len(platform["files"]),
            "Pinned image platform-member set differs")
    require(set(paths) <= set(pins), "Unreviewed image platform member")
    package = platform["package"]
    expected_owner = package["name"]
    snapshot = common.package_snapshot([expected_owner])
    require(snapshot == {expected_owner: {key: package[key] for key in ("version", "architecture", "status")}},
            "Image platform owner version differs")
    owners = apt.collect_owners({path.as_posix() for path in paths})
    records = []
    for path in sorted(paths):
        pin = pins[path]
        require(path.absolute() == path.resolve() and stat.S_ISREG(path.lstat().st_mode),
                "Image platform member is not an exact regular path: " + str(path))
        require(path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"],
                "Image platform member bytes differ: " + str(path))
        require(owners.get(path.as_posix()) == [expected_owner],
                "Image platform member owner differs: " + str(path))
        details = common.elf(path, dynamic=True)
        require(details["class"] == pin["elf_class"] == 64
                and details["machine"] == pin["machine"] == 183
                and details["endianness"] == pin["endianness"] == "little",
                "Image platform member ABI differs: " + str(path))
        records.append({"package": expected_owner, "package_version": package["version"],
                        "native_image": platform["native_image"], **details})
    return {"status": "verified-image-members", "members": records,
            "source": "Exact files from the pinned image; not represented as retained APT archives."}


def native_mapping_rows(raw, site, native, platform):
    """Classify every mapped .so path and retain rejection details before gating."""
    require(len(raw) <= 4 * 1024 * 1024, "Native memory-map evidence exceeds its bound")
    rows = []
    for number, line in enumerate(raw.decode("utf-8", "surrogateescape").splitlines(), 1):
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("/") or ".so" not in parts[5]:
            continue
        original = parts[5]
        deleted = original.endswith(" (deleted)")
        path = Path(original.removesuffix(" (deleted)")).resolve()
        if deleted:
            classification = "rejected-deleted"
        elif path.is_relative_to(site):
            classification = "source-extension" if path in native else "rejected-isolated-site"
        elif path in platform:
            classification = ("image-platform" if Path(original).absolute() == path
                              else "rejected-image-alias")
        elif (path.is_relative_to(PREFIX / "lib")
              and Path(original).absolute().is_relative_to(PREFIX / "lib")):
            classification = "apt-library"
        elif str(path).startswith(("/apex/", "/system/")):
            classification = "android-system"
        else:
            classification = "rejected-foreign"
        rows.append({"line": number, "mapped_path": original, "resolved_path": str(path),
                     "classification": classification, "deleted": deleted})
    return rows


def read_native_maps():
    with Path("/proc/self/maps").open("rb") as stream:
        return stream.read(4 * 1024 * 1024 + 1)


def verify_native_mappings(manifest, prep, common, apt, args, lock):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    native = {}
    for package in manifest["wheels"]:
        for item in package["native_members"]:
            native[(site / item["member"]).resolve()] = {"package": package["name"],
                                                        "sha256": item["sha256"], "bytes": item["bytes"]}
    for package in manifest["apt_python"]:
        for item in package["files"]:
            if item["path"].endswith(".so") or ".so." in item["path"]:
                native[(site / item["path"]).resolve()] = {"package": package["name"],
                                                         "sha256": item["sha256"], "bytes": item["bytes"]}
    platform = {Path(pin["path"]) for pin in lock["platform_runtime"]["files"]}
    raw = read_native_maps()
    raw_path = args.out / "NATIVE-MAPPINGS.raw.txt"
    with raw_path.open("xb") as stream:
        stream.write(raw)
    rows = native_mapping_rows(raw, site, native, platform)
    diagnostic = {"schema_version": 1, "raw": raw_path.name, "raw_bytes": len(raw),
                  "raw_sha256": hashlib.sha256(raw).hexdigest(), "mappings": rows,
                  "source_image": lock["platform_runtime"]["native_image"]}
    save_json(args.out / "NATIVE-MAPPINGS.json", diagnostic)
    rejected = [row for row in rows if row["classification"].startswith("rejected-")]
    require(not rejected, "Unverified native mapping: " + json.dumps(rejected, ensure_ascii=True))
    loaded = {Path(row["resolved_path"]) for row in rows if row["classification"] == "source-extension"}
    image_loaded = {Path(row["resolved_path"]) for row in rows if row["classification"] == "image-platform"}
    image_mappings = verify_image_platform_members(image_loaded, lock, common, apt)
    records = []
    for path in sorted(loaded):
        pin = native[path]
        require(path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"],
                "Mapped native extension differs from source wheel/APT payload: " + str(path))
        details = common.elf(path, dynamic=True)
        require(not any(name in {"libc.so.6", "libstdc++.so.6", "libpython3.14.so.1.0"}
                        for name in details.get("needed", [])), "Foreign GNU/Linux ABI dependency")
        records.append({"package": pin["package"], **details})
    required = {p["name"] for p in manifest["wheels"] if p["native_members"]}
    require(required <= {r["package"] for r in records}, "An installed source extension was not actually loaded")
    all_pins, _ = common.all_apt_pins(lock, prep.base_helper())
    for pin in lock["build_apt"]["additional_to_141"]:
        all_pins[pin["name"]] = pin
    apt_mappings = common.verify_mapped_apt_libraries(args.apt_archives, all_pins, apt)
    return {"status": "passed", "actually_mapped_extensions": records, "apt": apt_mappings,
            "image_platform": image_mappings, "diagnostic": "NATIVE-MAPPINGS.json",
            "diagnostic_sha256": sha(args.out / "NATIVE-MAPPINGS.json"),
            "raw_sha256": diagnostic["raw_sha256"]}


def runtime_case(args, lock, prep, common, apt):
    report = {"schema_version": 1, "status": "failed", "model_downloaded": False,
              "speech_synthesis_tested": False, "production_admission_changed": False}
    try:
        report["native_runtime"] = native_runtime(common)
        report["source_image"] = validate_source_image(args, lock)
        manifest = read_json(args.environment_manifest)
        roots = list(ORDER) if args.source_name == "combined" else [args.source_name]
        expected = closure_names(lock, roots)
        require(set(manifest["names"]) == expected, "Runtime does not contain its complete declared subset")
        report["installed"] = installed_inventory(manifest, prep, common)
        operations = module_at("_nonrust_real_operations", SCRIPT_DIR / "neutts_nonrust_operations.py",
                               OPERATIONS_SHA256)
        report["operations"] = operations.run_operations(roots, args.out / "operation-data")
        report["native_mappings"] = verify_native_mappings(manifest, prep, common, apt, args, lock)
        report["active_edges"] = [e for e in lock["edges"] if e["from"] in expected]
        report["active_edge_count"] = len(report["active_edges"])
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "RUNTIME-OPERATIONS-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def runtime_gate(args, lock, roots, built, runtime_directory, out, prep, common, env):
    expected = closure_names(lock, roots)
    wheels = [dict(p, wheel_path=str(args.inputs / "wheels" / p["artifact"]["filename"]))
              for p in lock["packages"] if p["name"] in expected]
    wheels += [p for p in built if p["name"] in expected]
    apt_names = expected & {"numpy", "scipy"}
    require({p["name"] for p in wheels} | apt_names == expected, "Native wheel closure is incomplete")
    python, manifest_path, manifest = create_environment(
        args, lock, wheels, apt_names, runtime_directory, out, "runtime", prep, common, env)
    pip_record = raw_pip_check(python, expected, lock, out, common, env)
    name = "combined" if len(roots) == 6 else roots[0]
    command = [str(python), "-I", "-B", str(Path(__file__).resolve()),
               "--phase", "runtime", "--inputs", str(args.inputs), "--out", str(out),
               "--apt-archives", str(args.apt_archives), "--source-name", name,
               "--environment-manifest", str(manifest_path),
               "--image-receipt", str(args.image_receipt)]
    process = common.bounded_command(command, out, "runtime-operations", 300, env)
    receipt = out / "RUNTIME-OPERATIONS-RESULT.json"
    report = read_json(receipt)
    require(report.get("status") == "passed"
            and report["installed"]["actual_visible_distribution_count"] == len(expected),
            "Actual native runtime gate failed")
    return {"status": "passed", "actual_runtime_distribution_count": len(expected),
            "active_edge_count": len([e for e in lock["edges"] if e["from"] in expected]),
            "raw_pip": pip_record, "process": process,
            "receipt": receipt.name, "receipt_sha256": sha(receipt),
            "copied_apt_payloads": manifest["copied_apt_payloads"]}


def run(args, lock, prep, common, apt):
    import resource
    require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the actual APT base Python")
    require(not args.out.exists() and not args.out.is_symlink(), "A fresh component output is required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "stage": "preflight",
              "scope": "Six independent native Python dependencies and their complete combined runtime subset",
              "lock_sha256": prep.LOCK_SHA256, "model_downloaded": False,
              "neutts_engine_installed": False, "speech_synthesis_tested": False,
              "neutts_python_bound_changed": False, "production_admission_changed": False,
              "release_output": False,
              "components": [{"component": name, "status": "not-run"} for name in ORDER]}
    try:
        report["runtime"] = native_runtime(common)
        report["source_image"] = validate_source_image(args, lock)
        report["foundation"] = common.validate_foundation(
            args.foundation_receipt, {"foundation": {"apt_metadata_ledger_sha256": lock["apt_metadata_ledger"]["sha256"]}})
        metadata = apt.load_manifest(SCRIPT_DIR / "neutts_apt_python_metadata.json")
        report["apt_runtime_provenance"] = apt.apt_provenance(
            {"runtime": metadata["runtime"], "apt_distributions": []}, args.apt_archives)
        report["archives"] = verify_archive_set(args, lock, common)
        limit = lock["build"]["memory_limit_bytes"]
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        require(hard in (-1, resource.RLIM_INFINITY) or hard >= limit, "Existing address-space hard limit is too small")
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        report["resource_limits"] = {"max_build_jobs": 2, "address_space_bytes": limit,
                                     "container_contract": "two CPUs, six GiB memory, 512 processes"}
        env = clean_environment(lock)
        with tempfile.TemporaryDirectory(prefix="nonrust-native-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            options, report["signed_snapshot"] = signed_snapshot(args, lock, common, work)
            report["toolchain_install"] = install_toolchain(args, lock, common, options)
            report["native_build_files"] = verify_build_files(args, lock, common, apt)
            _, original_native = common.all_apt_pins(lock, prep.base_helper())
            report["original_compiler_identity"] = common.verify_toolchain(args.apt_archives, original_native)
            build_wheels = [dict(p, wheel_path=str(args.inputs / "wheels" / p["artifact"]["filename"]))
                            for p in lock["build_packages"]]
            build_out = args.out / "build-environment"
            build_out.mkdir()
            build_python, manifest_path, manifest = create_environment(
                args, lock, build_wheels, {"numpy", "scipy"}, work / "build-venv",
                build_out, "build", prep, common, env)
            report["build_raw_pip"] = raw_pip_check(build_python, manifest["names"], lock, build_out, common, env)
            build_env = clean_environment(lock, build_python)
            report["stage"] = "independent-components"
            built = []
            for index, name in enumerate(ORDER):
                source = next(p for p in lock["sources"] if p["name"] == name)
                out = args.out / name
                out.mkdir()
                component = {"schema_version": 1, "component": name, "status": "failed", "stage": "source-build",
                             "source_archive_sha256": source["artifact"]["sha256"], "release_output": False,
                             "model_downloaded": False, "production_admission_changed": False}
                save_json(out / "COMPONENT-RESULT.json", component)
                try:
                    source_root = work / source["archive_root"]
                    shutil.copytree(args.inputs / "sources" / source["archive_root"], source_root)
                    wheel_dir = out / "wheels"
                    wheel_dir.mkdir()
                    source_env = dict(build_env)
                    if name == "pyyaml":
                        source_env.update(PYYAML_FORCE_LIBYAML="1", PYYAML_FORCE_CYTHON="1")
                    command = [str(build_python), "-I", "-B", str(Path(__file__).resolve()),
                               "--phase", "build", "--inputs", str(args.inputs), "--out", str(out),
                               "--source-name", name, "--source-root", str(source_root),
                               "--wheel-dir", str(wheel_dir), "--environment-manifest", str(manifest_path)]
                    component["build_process"] = common.bounded_command(
                        command, out, "native-source-build", source["build_timeout_seconds"], source_env)
                    found = list(wheel_dir.iterdir())
                    require(len(found) == 1 and found[0].suffix == ".whl", "Unexpected source build output")
                    package = built_wheel(found[0], source, prep)
                    package["wheel_path"] = str(found[0])
                    component["wheel"] = package
                    component["backend_receipt_sha256"] = sha(out / "SOURCE-BACKEND-RESULT.json")
                    log = (out / "native-source-build.stdout.log").read_text()
                    log += (out / "native-source-build.stderr.log").read_text()
                    require("--target=aarch64-linux-android24" in log and "-march=native" not in log,
                            "Build did not record the portable native compiler target")
                    component["stage"] = "runtime"
                    component["runtime"] = runtime_gate(
                        args, lock, [name], [package], work / ("runtime-" + name), out, prep, common, env)
                    component["status"], component["stage"] = "passed", "complete"
                    built.append(package)
                except Exception as exc:
                    component["error"] = {"type": type(exc).__name__, "message": str(exc)}
                    traceback.print_exc()
                finally:
                    save_json(out / "COMPONENT-RESULT.json", component)
                    report["components"][index] = {"component": name, "status": component["status"],
                                                   "stage": component["stage"],
                                                   "receipt": name + "/COMPONENT-RESULT.json",
                                                   "receipt_sha256": sha(out / "COMPONENT-RESULT.json")}
                    save_json(args.out / "NONRUST-COMPONENTS-RESULT.json", report)
            if len(built) == 6:
                report["stage"] = "combined-runtime"
                out = args.out / "combined"
                out.mkdir()
                report["combined"] = runtime_gate(
                    args, lock, list(ORDER), built, work / "runtime-combined", out, prep, common, env)
                require(report["combined"]["actual_runtime_distribution_count"] == 14
                        and report["combined"]["active_edge_count"] == 10, "Combined runtime scope differs")
                report["status"], report["stage"] = "passed", "complete"
            else:
                report["combined"] = {"status": "not-run", "reason": "Requires all six independent native gates to pass"}
                report["stage"] = "independent-component-failures"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        save_json(args.out / "NONRUST-COMPONENTS-RESULT.json", report)
        for path in args.out.rglob("*"):
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() else 0o644)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("run", "build", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--image-receipt", type=Path)
    parser.add_argument("--source-name", choices=(*ORDER, "combined"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--environment-manifest", type=Path)
    args = parser.parse_args(argv)
    prep, common, apt = support()
    lock, _ = prep.verify_inputs(args.inputs)
    if args.phase == "build":
        require(args.source_name in ORDER and args.source_root is not None
                and args.wheel_dir is not None and args.environment_manifest is not None,
                "Build phase needs explicit isolated source/environment paths")
        return build_one(args, lock, prep, common)
    require(args.apt_archives is not None and args.image_receipt is not None,
            "Native runtime requires retained exact APT archives and host image evidence")
    if args.phase == "runtime":
        require(args.source_name is not None and args.environment_manifest is not None,
                "Runtime phase needs an explicit complete environment manifest")
        return runtime_case(args, lock, prep, common, apt)
    require(args.foundation_receipt is not None, "The unchanged full foundation receipt is required")
    return run(args, lock, prep, common, apt)


if __name__ == "__main__":
    raise SystemExit(main())
