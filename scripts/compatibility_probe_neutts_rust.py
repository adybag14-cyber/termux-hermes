#!/usr/bin/env python3
"""Prepare native Rust wheels with real CPython/Bionic ABI and strict inputs.

This owns fresh build environments and temporary source copies only. Four original
Cargo locks remain fixed; Tiktoken's separate native lock-capture mode never builds
or installs it. Complete engine and Tokenizers runtime admission are later gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import traceback
from types import SimpleNamespace
import zipfile

PREFIX = Path("/data/data/com.termux/files/usr")
SCRIPT_DIR = Path(__file__).resolve().parent
PREPARER_SHA256 = "2635c33048122dc0ade3f3afef3e179d45770c846f794551611be645fe491fe0"
OPERATIONS_SHA256 = "a8576c384d3c5aa3854c430df83e6cfb3b1f6a69ba75713079bb6947fee125a7"
APT_HELPER_SHA256 = "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29"
FOUNDATION_PINS_SHA256 = "7ad635d7f1ce1157c7f3b3d7808eaf113c8bb77c4e99a8fe30b6b155faf04c5e"
FOUNDATION_CASES = {"python_dependencies", "torch", "torchaudio", "torchcodec",
                    "scipy", "llvmlite", "soxr"}

class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)

def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()

def sha_file(path):
    require(stat.S_ISREG(path.stat().st_mode), "Expected regular file")
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def read_json(path, limit=2_000_000):
    require(stat.S_ISREG(path.lstat().st_mode), "Invalid JSON file")
    require(path.stat().st_size <= limit, "Oversized JSON input")
    return json.loads(path.read_bytes())

def save_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")

def native_runtime():
    require(sys.platform == "android" and os.uname().machine == "aarch64"
            and os.getuid() == 1000 and sys.version_info[:3] == (3, 14, 6),
            "Real native Bionic aarch64 Python3.14.6 UID1000 is required")
    require(Path(sys.base_prefix).resolve() == PREFIX
            and Path("/proc/self/exe").resolve() == (PREFIX / "bin/python3.14").resolve(),
            "Unexpected base Python origin")
    require(sys.getandroidapilevel() >= 24, "Android API24 or newer is required")
    return {"sys_platform": sys.platform, "machine": os.uname().machine,
            "uid": os.getuid(), "python": sys.version, "api_level": sys.getandroidapilevel(),
            "prefix": sys.prefix, "base_prefix": sys.base_prefix,
            "executable": elf(Path("/proc/self/exe"))}

def elf(path, dynamic=False):
    path = path.resolve()
    with path.open("rb") as stream:
        header = stream.read(64)
    require(header[:4] == b"\x7fELF" and header[4:6] == b"\x02\x01"
            and struct.unpack_from("<H", header, 18)[0] == 183,
            "Expected little-endian AArch64 ELF: " + str(path))
    row = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha_file(path),
           "class": 64, "machine": 183, "endianness": "little"}
    if dynamic:
        result = subprocess.run([str(PREFIX / "bin/llvm-readelf"), "--dynamic", str(path)],
                                capture_output=True, timeout=15, check=False)
        require(result.returncode == 0, "ELF dynamic-table inspection failed")
        text = result.stdout.decode("utf-8", "strict")
        row["needed"] = re.findall(r"\(NEEDED\).*Shared library: \[([^]]+)\]", text)
        row["runpath"] = re.findall(r"\((?:RUNPATH|RPATH)\).*\[([^]]+)\]", text)
        require(not any(name in ("libc.so.6", "libm.so.6", "libpthread.so.0")
                        or "musl" in name for name in row["needed"]),
                "Non-Bionic dynamic dependency in native result")
    return row

def validate_foundation(path, lock):
    result = read_json(path)
    require(result.get("schema_version") == 1 and result.get("status") == "passed"
            and result.get("uid") == 1000 and result.get("python", {}).get("platform") == "android"
            and result.get("python", {}).get("prefix") == str(PREFIX),
            "Full native foundation did not pass")
    require(result.get("apt_archive_hashes_checked_before_install") is True
            and result.get("engine_installed") is False and result.get("model_downloaded") is False
            and result.get("pm_admission_changed") is False, "Unexpected foundation scope")
    validation = result.get("apt_python_validation", {})
    require(validation.get("status") == "requirements-and-provenance-passed"
            and validation.get("exit_code") == 0
            and validation.get("metadata_ledger_sha256")
            == lock["foundation"]["apt_metadata_ledger_sha256"],
            "Foundation requirements/provenance gate did not pass")
    require(validation.get("receipt") == "NEUTTS-APT-PYTHON-VALIDATION.json",
            "Unexpected foundation provenance receipt")
    provenance_path = path.parent / validation["receipt"]
    require(sha_file(provenance_path) == validation.get("sha256"),
            "Foundation provenance receipt digest mismatch")
    rows = result.get("cases", [])
    require(len(rows) == 7 and {r.get("component") for r in rows} == FOUNDATION_CASES,
            "Foundation is missing an actual native case")
    for row in rows:
        require(row.get("status") == "passed" and row.get("exit_code") == 0
                and row.get("timed_out") is False, "Failed foundation child")
        name = "neutts-" + row["component"] + ".json"
        require(row.get("receipt") == name, "Unexpected foundation child path")
        child_path = path.parent / name
        require(sha_file(child_path) == row.get("receipt_sha256"),
                "Foundation child digest mismatch")
        child = read_json(child_path)
        require(child.get("component") == row["component"] and child.get("status") == "passed",
                "Foundation child identity mismatch")
    require(result["python"]["executable"]["sha256"] == sha_file(Path("/proc/self/exe").resolve()),
            "Actual base Python changed since the foundation gate")
    return {"path": str(path), "sha256": sha_file(path), "status": "passed",
            "case_count": 7, "apt_validation_sha256": validation["sha256"],
            "raw_pip_exit_code": result["pip_check"]["exit_code"]}

def bounded_command(command, out, label, timeout, env=None, cwd=None):
    stdout_path, stderr_path = out / (label + ".stdout.log"), out / (label + ".stderr.log")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=cwd, env=env,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Stop the compiler/CMake descendants as well as their pip parent.
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            code = 124
    require(code == 0, label + " failed; retained exit code " + str(code))
    return {"command": command, "exit_code": code,
            "stdout_sha256": sha_file(stdout_path), "stderr_sha256": sha_file(stderr_path)}

def package_snapshot(names):
    fmt = "\t".join(chr(36) + "{" + field + "}" for field in
                    ("Package", "Version", "Architecture", "db:Status-Status")) + "\n"
    result = subprocess.run(
        [str(PREFIX / "bin/dpkg-query"), "-W", "-f=" + fmt, *names],
        capture_output=True, timeout=30, check=False,
    )
    require(result.returncode == 0, "Required installed APT package is absent")
    rows = {}
    for line in result.stdout.decode().splitlines():
        fields = line.split("\t")
        require(len(fields) == 4 and fields[0] not in rows, "Malformed installed APT inventory")
        rows[fields[0]] = {"version": fields[1], "architecture": fields[2], "status": fields[3]}
    return rows

def archive_path(directory, pin):
    matches = list(directory.glob(pin["name"] + "_*.deb"))
    require(len(matches) == 1, "Missing or ambiguous retained APT archive: " + pin["name"])
    path = matches[0]
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size == pin["bytes"] and sha_file(path) == pin["sha256"],
            "Retained APT archive bytes differ: " + pin["name"])
    return path

def ar_data_members(path, pin, wanted):
    raw = path.read_bytes()
    require(len(raw) == pin["bytes"] and sha_bytes(raw) == pin["sha256"], "APT archive changed during read")
    require(raw[:8] == b"!<arch>\n", "Invalid APT ar archive")
    offset, data_count, control_count, result = 8, 0, 0, {}
    while offset < len(raw):
        header = raw[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b"\x60\n", "Invalid ar member")
        size = int(header[48:58])
        require(0 <= size <= len(raw) - offset - 60, "Invalid ar member size")
        name = header[:16].decode("ascii").strip().rstrip("/")
        payload = raw[offset + 60:offset + 60 + size]
        require(len(payload) == size, "Truncated ar member")
        offset += 60 + size + size % 2
        if name.startswith("data.tar."):
            data_count += 1
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r|*") as archive:
                seen = set()
                for item in archive:
                    member = "/" + item.name.removeprefix("./").lstrip("/")
                    require(member not in seen, "Duplicate APT tar member")
                    seen.add(member)
                    if member not in wanted:
                        continue
                    require(item.isfile() and item.size <= 64_000_000, "Invalid selected APT native member")
                    value = archive.extractfile(item).read()
                    require(len(value) == item.size, "Truncated APT native member")
                    result[member] = value
        elif name.startswith("control.tar."):
            control_count += 1
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r|*") as archive:
                controls = []
                for item in archive:
                    if item.name.removeprefix("./") == "control":
                        require(item.isfile() and item.size < 100_000, "Invalid APT control")
                        controls.append(BytesParser(policy=compat32).parsebytes(archive.extractfile(item).read()))
                require(len(controls) == 1, "Missing/duplicate APT control")
                control = controls[0]
                require(control["Package"] == pin["name"] and control["Version"] == pin["version"]
                        and control["Architecture"] == pin["architecture"], "APT control identity differs")
    require(offset == len(raw) and data_count == control_count == 1 and set(result) == wanted,
            "Incomplete APT member inventory")
    return result

def verify_installed_wheel(path, package, site, prep):
    prep.verify_wheel(path, package)
    verified, rewrites, owned = [], [], set()
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            prep.safe_member(item)
            parts = PurePosixPath(item.filename).parts
            target = site.joinpath(*parts)
            script = False
            if parts[0].endswith(".data"):
                require(len(parts) >= 3, "Malformed wheel data scheme")
                if parts[1] in ("purelib", "platlib"):
                    target = site.joinpath(*parts[2:])
                elif parts[1] == "scripts":
                    target = site.parents[2] / "bin" / Path(*parts[2:])
                    script = True
                else:
                    raise ProbeError("Unreviewed installed wheel data scheme")
            if item.filename.endswith(".dist-info/RECORD"):
                require(target.is_file() and not target.is_symlink(), "Missing rewritten installation RECORD")
                owned.add(target.relative_to(site).as_posix())
                rewrites.append({"path": item.filename, "reason": "pip installation RECORD"})
                continue
            require(target.resolve() == target.absolute() and target.is_file(),
                    "Installed wheel file missing or reached through a symlink")
            before, after = archive.read(item), target.read_bytes()
            if before != after:
                require(script and before.startswith((b"#!python\n", b"#!pythonw\n"))
                        and after.startswith(b"#!") and before.split(b"\n", 1)[1] == after.split(b"\n", 1)[1],
                        "Installed wheel file changed")
                rewrites.append({"path": item.filename, "reason": "pip script shebang",
                                 "installed_sha256": sha_bytes(after)})
            else:
                verified.append({"path": item.filename, "sha256": sha_bytes(after)})
            if target.is_relative_to(site):
                owned.add(target.relative_to(site).as_posix())
    return {"name": package["name"], "wheel_sha256": package["artifact"]["sha256"],
            "verified_file_count": len(verified), "files": verified,
            "documented_rewrites": rewrites, "owned_paths": sorted(owned)}

def verify_mapped_apt_libraries(archives, pins, apt):
    paths = set()
    external = []
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith("/") or ".so" not in fields[5]:
            continue
        value = fields[5]
        if value.startswith(str(PREFIX) + "/lib/"):
            require(not value.endswith(" (deleted)"), "Deleted APT native mapping")
            path = Path(value).resolve()
            require(path.is_relative_to(PREFIX / "lib"), "APT library escaped its prefix")
            paths.add(path.as_posix())
        elif value.startswith(("/apex/", "/system/")):
            external.append(value)
    owners = apt.collect_owners(paths)
    grouped = {}
    for path in paths:
        candidates = owners.get(path, [])
        require(len(candidates) == 1 and candidates[0] in pins, "Unowned or unpinned APT native library")
        grouped.setdefault(candidates[0], set()).add(path)
    snapshot = package_snapshot(sorted(grouped))
    verified = []
    for package, wanted in sorted(grouped.items()):
        pin = pins[package]
        require(snapshot[package] == {"version": pin["version"], "architecture": pin["architecture"], "status": "installed"},
                "Mapped APT owner version differs")
        archive = archive_path(archives, pin)
        members = ar_data_members(archive, pin, wanted)
        for name, raw in sorted(members.items()):
            path = Path(name)
            require(path.read_bytes() == raw, "Mapped APT library differs from pinned archive")
            verified.append({"package": package, **elf(path, dynamic=True)})
    return {"status": "passed", "mapped_apt_libraries": verified,
            "android_system_mappings": sorted(set(external)),
            "system_scope": "Android platform libraries recorded separately; not represented as APT-owned files."}

def pip_command(python):
    return [str(PREFIX / "bin/python"), "-I", "-B", "-m", "pip", "--python", str(python)]

# The bounded process, APT member, and installed-wheel checks above are copied
# from the reviewed common implementation at SHA256
# b27b83ed722b893adf96740aeb862d3dbd0e51a12eeaf20bede85b36bc84df95.
# Keeping this narrow copy avoids binding independent in-flight Phonemizer work.


def module_at(name, path, digest):
    require(sha_file(path) == digest, "Reviewed helper changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def helpers():
    prep = module_at("_rust_source_preparer", SCRIPT_DIR / "prepare_neutts_rust_sources.py", PREPARER_SHA256)
    apt = module_at("_rust_apt_provenance", SCRIPT_DIR / "validate_neutts_apt_python.py", APT_HELPER_SHA256)
    return prep, apt


def clean_environment(lock, work, python=None, *, online_lock_capture=False):
    # An allowlist avoids ambient Cargo, TLS, PyO3, platform, or Python overrides.
    env = {key: os.environ[key] for key in ("HOME", "TMPDIR", "LANG", "LC_ALL") if key in os.environ}
    path = ([str(Path(python).parent)] if python else []) + [str(PREFIX / "bin"), "/system/bin", "/system/xbin"]
    env.update({
        "PREFIX": str(PREFIX), "PATH": ":".join(path), "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "TMPDIR": str(work / "tmp"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PIP_CONFIG_FILE": "/dev/null", "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CARGO_HOME": str(work / "cargo-home"), "CARGO_TARGET_DIR": str(work / "target"),
        "CARGO_BUILD_JOBS": "2", "CMAKE_BUILD_PARALLEL_LEVEL": "2", "MAKEFLAGS": "-j2",
        "CARGO_BUILD_TARGET": "aarch64-linux-android",
        "CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER": str(PREFIX / "bin/clang"),
        "RUSTC": str(PREFIX / "bin/rustc"), "CARGO": str(PREFIX / "bin/cargo"),
        "CC": str(PREFIX / "bin/clang"), "CXX": str(PREFIX / "bin/clang++"),
        "AR": str(PREFIX / "bin/llvm-ar"), "CFLAGS": lock["build"]["cflags"],
        "CXXFLAGS": lock["build"]["cflags"], "LDFLAGS": lock["build"]["ldflags"],
        "RUSTFLAGS": lock["build"]["rustflags"],
        "PKG_CONFIG": str(PREFIX / "bin/pkg-config"),
        "PKG_CONFIG_LIBDIR": str(PREFIX / "lib/pkgconfig"),
        "OPENSSL_DIR": str(PREFIX), "OPENSSL_INCLUDE_DIR": str(PREFIX / "include"),
        "OPENSSL_LIB_DIR": str(PREFIX / "lib"), "OPENSSL_STATIC": "0", "OPENSSL_NO_VENDOR": "1",
        "MATURIN_NO_INSTALL_RUST": "1", "SOURCE_DATE_EPOCH": str(lock["build"]["source_date_epoch"]),
        "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false",
    })
    if not online_lock_capture:
        env["CARGO_NET_OFFLINE"] = "true"
    if python:
        env["PYO3_PYTHON"] = str(python)
    return env


def cargo_source_config(home, vendor):
    require(not home.exists(), "Use a fresh Cargo home")
    home.mkdir()
    require(vendor.is_dir() and not vendor.is_symlink(), "Invalid verified registry source")
    raw = ('[source.crates-io]\nreplace-with = "reviewed-directory"\n'
           '[source.reviewed-directory]\ndirectory = ' + json.dumps(str(vendor.resolve())) + '\n').encode()
    with (home / "config.toml").open("xb") as stream:
        stream.write(raw)
    return {"path": str(home / "config.toml"), "sha256": sha_bytes(raw),
            "source_replacement": "independently SHA-verified original registry archives"}


def signed_snapshot(args, lock, work):
    snapshot = args.inputs / "snapshot"
    frozen = {p["filename"]: p for p in lock["build_apt"]["snapshot"]}
    for filename, pin in frozen.items():
        path = snapshot / filename
        require(path.stat().st_size == pin["bytes"] and sha_file(path) == pin["sha256"],
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
            require(fields["Package"] not in records, "Duplicate target APT package")
            records[fields["Package"]] = fields
    for pin in lock["build_apt"]["packages"]:
        row = records.get(pin["name"])
        require(row is not None and (row["Version"], row["Architecture"], row["Filename"],
                row["SHA256"], int(row["Size"])) == (pin["version"], pin["architecture"],
                pin["filename"], pin["sha256"], pin["bytes"]), "APT source index pin differs")
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
    record = bounded_command([str(PREFIX / "bin/apt-get"), *options, "update"],
                                    args.out, "rust-frozen-signed-index", 90)
    releases = list(lists.glob("*_InRelease"))
    require(len(releases) == 1 and sha_file(releases[0]) == frozen["InRelease"]["sha256"],
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
                     "matched_archives": len(lock["build_apt"]["packages"])}

def verify_archive_set(args, lock):
    pins = lock["build_apt"]["packages"]
    rows = []
    for pin in pins:
        path = archive_path(args.apt_archives, pin)
        require(path.name == Path(pin["filename"]).name, "APT archive basename differs")
        ar_data_members(path, pin, set())
        rows.append({"name": pin["name"], "version": pin["version"],
                     "bytes": pin["bytes"], "sha256": pin["sha256"], "path": str(path)})
    require(len(rows) == 46 and {Path(r["path"]).name for r in rows}
            == {p.name for p in args.apt_archives.iterdir()}, "Incomplete/extra compiler archives")
    return rows


def install_toolchain(args, lock, options, work):
    pins = lock["build_apt"]["packages"]
    existing = [p for p in pins if p["in_foundation"]]
    additions = [p for p in pins if not p["in_foundation"]]
    require(len(existing) == 27 and len(additions) == 19, "Reviewed APT addition set differs")
    expected_existing = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                                    "status": "installed"} for p in existing}
    require(package_snapshot(list(expected_existing)) == expected_existing, "Foundation APT overlap differs")
    # APT may lock/rename cache entries. Its cache is owned and writable; the source
    # archives stay independently verified and read-only in the inputs mount.
    archives = work / "install-archives"
    archives.mkdir()
    (archives / "partial").mkdir()
    for p in pins:
        source = archive_path(args.apt_archives, p)
        shutil.copyfile(source, archives / source.name)
        require(sha_file(archives / source.name) == p["sha256"], "APT cache copy changed")
    command = [str(PREFIX / "bin/apt-get"), *options,
               "-o", "Dir::Cache::archives=" + str(archives),
               "-o", "Dpkg::Options::=--force-confnew", "--no-download", "--no-remove",
               "--no-install-recommends", "--reinstall", "install",
               *(p["name"] + "=" + p["version"] for p in additions)]
    plan = bounded_command(command[:1] + ["-s"] + command[1:], args.out, "rust-apt-plan", 90)
    text = (args.out / "rust-apt-plan.stdout.log").read_text()
    require(not any(line.startswith("Remv ") for line in text.splitlines()), "APT proposed a removal")
    proposed = [line.split()[1].split(":", 1)[0] for line in text.splitlines() if line.startswith("Inst ")]
    require(len(proposed) == len(set(proposed)) and set(proposed) == {p["name"] for p in additions},
            "APT proposed an unreviewed addition, upgrade, or omission")
    installed = bounded_command(command[:1] + ["-y"] + command[1:], args.out, "rust-apt-install", 300)
    expected = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                           "status": "installed"} for p in pins}
    require(package_snapshot(list(expected)) == expected, "Installed compiler closure differs")
    return {"status": "passed", "additional_count": len(additions),
            "plan": plan, "install": installed, "installed_packages": expected}


def verify_apt_files(paths, archives, pins, apt):
    paths = {Path(p).resolve().as_posix() for p in paths}
    owners = apt.collect_owners(paths)
    grouped, records = {}, []
    for path in paths:
        require(Path(path).is_relative_to(PREFIX) and Path(path).is_file(), "Compiler/runtime path escaped prefix")
        candidates = owners.get(path, [])
        require(len(candidates) == 1 and candidates[0] in pins, "Unowned/unpinned compiler or TLS input")
        grouped.setdefault(candidates[0], set()).add(path)
    for name, wanted in sorted(grouped.items()):
        p = pins[name]
        contents = ar_data_members(archive_path(archives, p), p, wanted)
        for path, raw in sorted(contents.items()):
            require(Path(path).read_bytes() == raw, "Installed compiler/TLS input differs from its archive")
            records.append({"path": path, "package": name, "bytes": len(raw), "sha256": sha_bytes(raw)})
    return records


def native_controls(args, lock, work, env, apt):
    pins = {p["name"]: p for p in lock["build_apt"]["packages"]}
    results = {}
    for program, argv, expected in (
        ("rustc", ["--version", "--verbose"], "rustc 1.99.1"),
        ("cargo", ["--version", "--verbose"], "cargo 1.99.1"),
        ("clang", ["--version"], "clang version 21.1.8"),
    ):
        record = bounded_command([str(PREFIX / "bin" / program), *argv], args.out, "rust-" + program, 30, env)
        text = (args.out / ("rust-" + program + ".stdout.log")).read_text()
        require(expected in text, "Actual compiler version differs: " + program)
        if program == "rustc":
            require("host: aarch64-linux-android" in text, "Rust host is not native Android AArch64")
        results[program] = {**record, "output": text}
    source = work / "native-api.c"
    source.write_text('#include <stdio.h>\n#include <android/api-level.h>\n'
                      'int main(void) { printf("%d\\n", __ANDROID_API__); return 0; }\n')
    binary = work / "native-api"
    results["compile_api24"] = bounded_command(
        [str(PREFIX / "bin/clang"), "--target=aarch64-linux-android24", "-march=armv8-a",
         str(source), "-o", str(binary)], args.out, "rust-api-compile", 60, env)
    results["execute_api24"] = bounded_command([str(binary)], args.out, "rust-api-execute", 20, env)
    require((args.out / "rust-api-execute.stdout.log").read_text() == "24\n", "Real compiler API level differs")
    results["api24_elf"] = elf(binary, dynamic=True)
    # The explicit level is based on the actual native compiler execution above.
    env["ANDROID_API_LEVEL"] = "24"
    paths = [PREFIX / "bin" / n for n in ("rustc", "cargo", "clang", "clang++", "llvm-ar", "cmake", "pkg-config", "openssl")]
    paths += [PREFIX / "lib" / n for n in ("libpython3.so", "libpython3.14.so", "libssl.so", "libcrypto.so")]
    paths += [PREFIX / "include/openssl/opensslv.h", PREFIX / "etc/tls/cert.pem"]
    std = PREFIX / "lib/rustlib/aarch64-linux-android/lib"
    require(std.is_dir(), "Pinned native Rust standard library is absent")
    paths += [p for p in std.iterdir() if p.is_file() and not p.is_symlink()]
    results["original_apt_bytes"] = verify_apt_files(paths, args.apt_archives, pins, apt)
    results["abi3_link_stub"] = elf(PREFIX / "lib/libpython3.so", dynamic=True)
    require("libpython3.14.so" in results["abi3_link_stub"]["needed"], "Real abi3 stub does not link the exact interpreter")
    return results


def source_originals_unchanged(root, source, prep):
    original = {row["path"]: row for row in source["files"]}
    rows = prep.tree_files(root)
    selected = [row for row in rows if row["path"] in original]
    prep.same_files(selected, source["files"])
    return {"original_files_unchanged": len(selected),
            "derived_files": [row for row in rows if row["path"] not in original]}


def capture_cargo_metadata(source, root, lock, args, env):
    features = list(source["maturin_config"].get("features", [])) + source["extra_cargo_features"]
    options = ["--no-default-features"] if source["name"] == "maturin" else []
    if features:
        options += ["--features", ",".join(features)]
    command = [str(PREFIX / "bin/cargo"), "metadata", "--format-version", "1", "--locked", "--offline",
               "--filter-platform", "aarch64-linux-android", "--manifest-path",
               str(root / source["cargo_manifest"]["path"]), *options]
    record = bounded_command(command, args.out, "cargo-metadata-" + source["name"], 120, env, root)
    raw_path = args.out / ("cargo-metadata-" + source["name"] + ".stdout.log")
    value = read_json(raw_path, 24_000_000)
    registry = {(p["name"], p["version"]): p for p in lock["registry"]}
    packages, local = {}, []
    for package in value["packages"]:
        require(package["id"] not in packages, "Duplicate resolved Cargo package")
        packages[package["id"]] = package
        if package["source"] is None:
            manifest = Path(package["manifest_path"])
            require(manifest.is_file() and manifest.resolve().is_relative_to(root.resolve()),
                    "Cargo resolved a local path outside the original source")
            local.append(package["id"])
        else:
            require(package["source"] == "registry+https://github.com/rust-lang/crates.io-index"
                    and (package["name"], package["version"]) in registry,
                    "Cargo metadata selected an unpinned Git/registry/version")
            pin = registry[(package["name"], package["version"])]
            manifest = Path(package["manifest_path"])
            require(manifest.parent.resolve() == (args.inputs / "vendor" /
                    (pin["name"] + "-" + pin["version"])).resolve(),
                    "Cargo metadata did not use the exact verified directory source")
    nodes = value["resolve"]["nodes"]
    require(len({n["id"] for n in nodes}) == len(nodes)
            and all(n["id"] in packages for n in nodes), "Invalid target-filtered Cargo graph")
    selected = [{"name": packages[n["id"]]["name"], "version": packages[n["id"]]["version"],
                 "source": packages[n["id"]]["source"], "features": sorted(n["features"]),
                 "deps": n["deps"]} for n in nodes]
    if source["name"] == "hf-xet":
        hf = [n for n in selected if n["name"] == "hf-xet" or n["name"] == "hf_xet"]
        reqwest = [n for n in selected if n["name"] == "reqwest"]
        require(len(hf) == 1 and "native-tls" in hf[0]["features"], "HF native TLS feature did not resolve")
        require(len(reqwest) == 1 and "native-tls" in reqwest[0]["features"]
                and "http3" not in reqwest[0]["features"], "Real reqwest feature graph differs from reviewed TLS route")
        require(any(n["name"] == "openssl-sys" for n in selected), "Native OpenSSL edge is missing")
    report = {"schema_version": 1, "status": "passed", "component": source["name"],
              "command": record, "original_cargo_lock_sha256": source["cargo_lock"]["sha256"],
              "full_embedded_union_count": 804, "target_filtered_resolved_node_count": len(nodes),
              "graph_scope": "Cargo metadata target-filtered resolve graph; includes active development/build edges, not only linked final ELF crates.",
              "local_original_workspace_packages": local, "selected_packages": selected}
    save_json(args.out / ("CARGO-GRAPH-" + source["name"] + ".json"), report)
    return {"path": str(args.out / ("CARGO-GRAPH-" + source["name"] + ".json")),
            "sha256": sha_file(args.out / ("CARGO-GRAPH-" + source["name"] + ".json")),
            "resolved_nodes": len(nodes)}


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

def installed_inventory(manifest, prep):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(sys.prefix != sys.base_prefix and Path(sys.base_prefix).resolve() == PREFIX
            and str(PREFIX / "lib/python3.14/site-packages") not in sys.path,
            "Isolated environment exposed global APT site-packages")
    expected = {p["name"]: p for p in manifest["wheels"]}
    require(len(expected) == len(manifest["names"]) and set(expected) == set(manifest["names"]),
            "Installation closure is inconsistent")
    distributions = list(importlib.metadata.distributions())
    require(len(distributions) == len(expected), "Missing or extra visible distribution")
    seen, allowed, reports = set(), set(), []
    adapter = SimpleNamespace(verify_wheel=prep.verify_wheel,
                              safe_member=lambda item: prep.safe_relative(item.filename.rstrip("/")))
    for dist in distributions:
        name = prep.canonical_name(dist.metadata["Name"])
        require(name in expected and name not in seen, "Unexpected or duplicate distribution")
        seen.add(name)
        package = expected[name]
        metadata_dir = Path(dist._path)
        require(metadata_dir.parent.resolve() == site.resolve() and not metadata_dir.is_symlink(),
                "Metadata selected outside isolated site")
        require(dist.version == package["version"], "Installed distribution version differs")
        raw = prep.read_regular(metadata_dir / "METADATA", 2_000_000)
        require(hashlib.sha256(raw).hexdigest() == package["wheel"]["metadata_sha256"],
                "Installed wheel metadata changed")
        record = verify_installed_wheel(Path(package["wheel_path"]), package, site, adapter)
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
                        "documented_rewrites": record["documented_rewrites"]})
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



def environment_manifest(wheels, path):
    value = {"schema_version": 1, "names": sorted(p["name"] for p in wheels), "wheels": wheels}
    require(len(value["names"]) == len(set(value["names"])), "Duplicate installed distribution selection")
    save_json(path, value)
    return value


def create_environment(wheels, destination, out, label, prep, env):
    require(not destination.exists(), "Use a fresh isolated Python environment")
    bounded_command([str(PREFIX / "bin/python"), "-I", "-B", "-m", "venv", "--without-pip",
                     str(destination)], out, label + "-venv", 60, env)
    require("include-system-site-packages = false" in (destination / "pyvenv.cfg").read_text(),
            "New environment exposed the global site")
    python = destination / "bin/python"
    requirements = out / (label + "-requirements.txt")
    prep.write_new(requirements, prep.requirement_text(wheels))
    command = pip_command(python) + ["install", "--no-index", "--no-deps", "--require-hashes",
               "--only-binary=:all:", "--no-compile", "--no-cache-dir"]
    for link in sorted({str(Path(p["wheel_path"]).parent) for p in wheels}):
        command += ["--find-links", link]
    bounded_command([*command, "-r", str(requirements)], out, label + "-install", 180, env)
    manifest_path = out / (label + "-installed-closure.json")
    environment_manifest(wheels, manifest_path)
    return python, manifest_path


def run_inventory(python, manifest, out, label, env):
    result = bounded_command(
        [str(python), "-I", "-B", str(Path(__file__).resolve()), "--mode", "inventory",
         "--environment-manifest", str(manifest), "--out", str(out / (label + "-inventory.json"))],
        out, label + "-inventory", 90, env)
    receipt = read_json(out / (label + "-inventory.json"), 8_000_000)
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.utils import canonicalize_name
    markers = default_environment()
    require(receipt["marker_environment"] == markers, "Child native environment markers differ")
    manifest_data = read_json(manifest, 8_000_000)
    versions = {p["name"]: p["version"] for p in manifest_data["wheels"]}
    graph = []
    for package in manifest_data["wheels"]:
        require(SpecifierSet(package["requires_python"]).contains("3.14.6"),
                "Installed package rejects actual native Python")
        for value in package["requires_dist"]:
            req = Requirement(value)
            require(req.url is None, "Unreviewed runtime URL")
            active = not req.marker or req.marker.evaluate({**markers, "extra": ""})
            name = canonicalize_name(req.name)
            if active:
                require(name in versions and req.specifier.contains(versions[name]),
                        "Installed runtime closure has an unsatisfied requirement: " + value)
            graph.append({"requirement": value, "active": active, "selected_version": versions.get(name)})
    result["receipt_sha256"] = sha_file(out / (label + "-inventory.json"))
    result["requirements"] = graph
    return result


def inventory_case(args, prep):
    native_runtime()
    manifest = read_json(args.environment_manifest, 8_000_000)
    result = installed_inventory(manifest, prep)
    import platform
    result["marker_environment"] = {
        "implementation_name": sys.implementation.name,
        "implementation_version": platform.python_version(),
        "os_name": os.name, "platform_machine": platform.machine(),
        "platform_python_implementation": platform.python_implementation(),
        "platform_release": platform.release(), "platform_system": platform.system(),
        "platform_version": platform.version(), "python_full_version": platform.python_version(),
        "python_version": ".".join(platform.python_version_tuple()[:2]), "sys_platform": sys.platform,
    }
    save_json(args.out, result)


def build_one(args, lock, prep):
    native_runtime()
    source = next(p for p in lock["sources"] if p["name"] == args.source_name)
    require(source["name"] in prep.LOCKED_NAMES, "Unreviewed Tiktoken lock cannot be built")
    manifest = read_json(args.environment_manifest, 8_000_000)
    expected = {p["name"] for p in lock["python_build_packages"]}
    if source["name"] != "maturin":
        expected.add("maturin")
    require(set(manifest["names"]) == expected, "Build backend is not the complete isolated selected closure")
    inventory = installed_inventory(manifest, prep)
    from packaging.markers import default_environment
    versions = {p["name"]: p["version"] for p in manifest["wheels"]}
    markers = default_environment()
    require(not any(args.wheel_dir.iterdir()), "Backend wheel output must be fresh")
    prep.verify_source(args.source_root, source)
    project = tomllib.loads((args.source_root / "pyproject.toml").read_text())
    build = project["build-system"]
    require(build["requires"] == source["build_requires"] and build["build-backend"] == source["build_backend"]
            and build.get("backend-path", []) == source["backend_path"], "Source backend declarations changed")
    requirements = validate_build_requirements(source["build_requires"], versions, markers)
    for package in manifest["wheels"]:
        validate_build_requirements(package["requires_dist"], versions, markers)
    for relative in reversed(source["backend_path"]):
        prep.safe_relative(relative)
        path = args.source_root / relative
        require(path.is_dir() and path.resolve().is_relative_to(args.source_root.resolve()),
                "Backend path escaped original source")
        sys.path.insert(0, str(path))
    os.chdir(args.source_root)
    backend = importlib.import_module(source["build_backend"])
    backend_path = Path(backend.__file__).resolve()
    expected_root = args.source_root.resolve() if source["backend_path"] else Path(sys.prefix).resolve()
    require(backend_path.is_relative_to(expected_root), "PEP517 backend origin differs")
    settings = {}
    if source["name"] != "maturin":
        value = "--locked --offline"
        if source["name"] == "hf-xet":
            value += " --features native-tls"
        settings["maturin.build-args"] = value
    else:
        require(os.environ.get("MATURIN_NO_INSTALL_RUST") == "1"
                and "MATURIN_SETUP_ARGS" not in os.environ, "Original Maturin bootstrap controls changed")
    require(os.environ.get("CARGO_NET_OFFLINE") == "true"
            and os.environ.get("PYO3_PYTHON") == sys.executable
            and os.environ.get("ANDROID_API_LEVEL") == "24", "Native backend controls differ")
    dynamic = backend.get_requires_for_build_wheel(config_settings=settings)
    require(isinstance(dynamic, list) and all(isinstance(v, str) for v in dynamic),
            "Backend returned invalid dynamic requirements")
    dynamic_report = validate_build_requirements(dynamic, versions, markers)
    filename = backend.build_wheel(str(args.wheel_dir), config_settings=settings)
    require(isinstance(filename, str) and filename == Path(filename).name and filename.endswith(".whl")
            and {p.name for p in args.wheel_dir.iterdir()} == {filename}, "Backend emitted unreviewed outputs")
    unchanged = source_originals_unchanged(args.source_root, source, prep)
    require(sha_file(args.source_root / source["cargo_lock"]["path"]) == source["cargo_lock"]["sha256"],
            "Original Cargo lock changed during native build")
    save_json(args.out / "SOURCE-BACKEND-RESULT.json", {
        "schema_version": 1, "status": "passed", "component": source["name"],
        "archive_sha256": source["artifact"]["sha256"], "cargo_lock_sha256": source["cargo_lock"]["sha256"],
        "backend_path": str(backend_path), "backend_sha256": sha_file(backend_path),
        "declared_build_requirements": requirements, "dynamic_build_requirements": dynamic_report,
        "build_environment": inventory, "config_settings": settings, "source_after": unchanged,
        "wheel": filename, "sys_platform": sys.platform, "platform_override_used": False})


def built_wheel(path, source, prep):
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import parse_tag, sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename, canonicalize_name
    from pip._vendor.packaging.requirements import Requirement
    facts = prep.wheel_facts(path)
    name, version, build, tags = parse_wheel_filename(path.name)
    require(name == source["name"] == facts["name"] and str(version) == source["version"] == facts["version"]
            and not build, "Built distribution identity differs")
    require(facts["wheel"]["tags"] == [source["expected_tag"]] and tags == parse_tag(source["expected_tag"])
            and tags <= set(sys_tags()) and facts["wheel"]["root_is_purelib"] is False,
            "Built wheel changed the real native platform/ABI")
    require(SpecifierSet(facts["requires_python"]) == SpecifierSet(source["requires_python"])
            and SpecifierSet(facts["requires_python"]).contains("3.14.6"), "Original Python version declaration changed")
    def key(value):
        req = Requirement(value)
        require(req.url is None, "Unreviewed URL requirement")
        return canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)), str(req.marker or "")
    require(sorted(map(key, facts["requires_dist"])) == sorted(map(key, source.get(
        "expected_bootstrap_requires_dist", source["requires_dist"]))), "Original runtime dependency declarations changed")
    with zipfile.ZipFile(path) as archive:
        native = facts["native_members"]
        if source["name"] == "maturin":
            member = source["native_extension_prefix"]
            require(member in archive.namelist() and not native, "Unexpected Maturin binary wheel layout")
            native = [{"member": member, "bytes": len(archive.read(member)),
                       "sha256": sha_bytes(archive.read(member))}]
        require(native, "Native source silently emitted no native binary")
        for item in native:
            raw = archive.read(item["member"])
            require(item["member"].startswith(source["native_extension_prefix"]) and len(raw) >= 64
                    and raw[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", raw, 18)[0] == 183,
                    "Built wheel contains a foreign ABI or namespace")
    return {**facts, "built_native_binary_members": native, "wheel_path": str(path)}


def inspect_wheel_elf(path, facts, out, prep):
    directory = out / "native-elf"
    directory.mkdir()
    rows = []
    with zipfile.ZipFile(path) as archive:
        for index, member in enumerate(facts["built_native_binary_members"]):
            target = directory / (str(index) + "-" + Path(member["member"]).name)
            prep.write_new(target, archive.read(member["member"]), 0o755)
            rows.append({"wheel_member": member["member"], **elf(target, dynamic=True)})
    return rows


def with_python(env, python):
    value = dict(env)
    value["PATH"] = str(python.parent) + ":" + str(PREFIX / "bin") + ":/system/bin:/system/xbin"
    value["PYO3_PYTHON"] = str(python)
    return value


def runtime_case(args, lock, prep, apt):
    native_runtime()
    manifest = read_json(args.environment_manifest, 8_000_000)
    require(set(manifest["names"]) == {"hf-xet", "safetensors"},
            "Independent complete base runtime must contain exactly HF Xet and Safetensors")
    before = installed_inventory(manifest, prep)
    ops = module_at("_rust_native_operations", SCRIPT_DIR / "neutts_rust_operations.py", OPERATIONS_SHA256)
    def run(command, label, timeout, env=None):
        return bounded_command(command, args.out, label, timeout, env or dict(os.environ))
    operations = ops.operations(args.work / "operations", args.out / "operations", dict(os.environ), run)
    pins = {p["name"]: p for p in lock["build_apt"]["packages"]}
    apt_mappings = verify_mapped_apt_libraries(args.apt_archives, pins, apt)
    selected_native = {}
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    for package in manifest["wheels"]:
        for member in package["native_members"]:
            path = site / member["member"]
            selected_native[path.resolve().as_posix()] = member
    mapped = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith(str(site)) or ".so" not in fields[5]:
            continue
        path = fields[5]
        require(path in selected_native and sha_file(Path(path)) == selected_native[path]["sha256"],
                "Unowned or changed native Python extension mapping")
        mapped.add(path)
    require(mapped == set(selected_native), "A built native extension was not actually loaded")
    after = installed_inventory(manifest, prep)
    require(before == after, "Runtime operations changed the exact installed files")
    save_json(args.out / "RUST-BASE-RUNTIME-RESULT.json", {
        "schema_version": 1, "status": "passed", "complete_distribution_count": 2,
        "scope": "HF Xet and Safetensors complete base dependencies only; their optional framework extras are separate.",
        "before": before, "operations": operations, "after": after, "mapped_extensions": sorted(mapped),
        "apt_provenance": apt_mappings, "tokenizers_full_runtime_admitted": False,
        "tiktoken_built": False, "engine_installed": False, "model_downloaded": False})


def tiktoken_capture(args, lock, prep, work, env):
    source = next(p for p in lock["sources"] if p["name"] == "tiktoken")
    require(source["cargo_lock"] is None and "CARGO_NET_OFFLINE" not in env,
            "Tiktoken capture must be the explicitly online, previously missing-lock stage")
    root = work / source["archive_root"]
    shutil.copytree(args.inputs / "sources" / source["archive_root"], root)
    prep.verify_source(root, source)
    env = {**env, "CARGO_HTTP_SSL_VERIFY": "true", "CARGO_HTTP_CAINFO": str(PREFIX / "etc/tls/cert.pem")}
    generated = bounded_command(
        [str(PREFIX / "bin/cargo"), "generate-lockfile", "--manifest-path", str(root / "Cargo.toml"), "--verbose"],
        args.out, "tiktoken-generate-lockfile", 600, env, root)
    prep.verify_source(root, source, allow_new_lock=True)
    lock_raw = prep.read_regular(root / "Cargo.lock", 8_000_000)
    value = tomllib.loads(lock_raw.decode())
    rows, identities = [], set()
    for item in value["package"]:
        identity = item["name"], item["version"]
        require(identity not in identities, "Generated lock has an ambiguous package identity")
        identities.add(identity)
        if "source" not in item:
            require(identity == ("tiktoken", source["version"]), "Generated lock added a local path package")
            continue
        require(item["source"] == prep.REGISTRY and re.fullmatch(r"[0-9a-f]{64}", item["checksum"]),
                "Tiktoken resolved an unreviewed Git/registry source")
        rows.append({"name": item["name"], "version": item["version"], "source": item["source"],
                     "sha256": item["checksum"], "filename": item["name"] + "-" + item["version"] + ".crate",
                     "url": "https://static.crates.io/crates/" + item["name"] + "/" + item["name"] + "-" + item["version"] + ".crate"})
    require(0 < len(rows) <= 500, "Generated Tiktoken registry closure exceeds the explicit review bound")
    fetched = bounded_command(
        [str(PREFIX / "bin/cargo"), "fetch", "--manifest-path", str(root / "Cargo.toml"), "--locked", "--verbose"],
        args.out, "tiktoken-fetch-locked", 900, env, root)
    require((root / "Cargo.lock").read_bytes() == lock_raw, "Cargo fetch changed the just-captured lock")
    prep.verify_source(root, source, allow_new_lock=True)
    captured = args.out / "captured-tiktoken-inputs"
    captured.mkdir()
    for directory in ("crates", "vendor", "sources"):
        (captured / directory).mkdir()
    shutil.copytree(root, captured / "sources" / source["archive_root"])
    source_root = captured / "sources" / source["archive_root"]
    prep.verify_source(source_root, source, allow_new_lock=True)
    require((source_root / "Cargo.lock").read_bytes() == lock_raw, "Captured source copy changed Cargo.lock")
    registry = []
    for pin in sorted(rows, key=lambda p: (p["name"], p["version"])):
        matches = list((work / "cargo-home/registry/cache").glob("*/" + pin["filename"]))
        require(len(matches) == 1, "Native Cargo did not cache exactly one locked registry archive")
        raw = prep.verified_bytes(matches[0], pin)
        pin = {**pin, "bytes": len(raw)}
        target = captured / "crates" / pin["filename"]
        prep.write_new(target, raw)
        record = prep.export_crate(target, pin, captured / "vendor" / (pin["name"] + "-" + pin["version"]))
        prep.verify_crate(target, pin, captured / "vendor" / (pin["name"] + "-" + pin["version"]))
        registry.append({**pin, "files": len(record["files"]), "checksum_sha256": record["checksum_sha256"]})
    offline_home = work / "tiktoken-offline-cargo-home"
    source_config = cargo_source_config(offline_home, captured / "vendor")
    offline_env = {**env, "CARGO_HOME": str(offline_home), "CARGO_NET_OFFLINE": "true"}
    offline = bounded_command(
        [str(PREFIX / "bin/cargo"), "metadata", "--manifest-path", str(source_root / "Cargo.toml"),
         "--format-version", "1", "--locked", "--offline", "--filter-platform", "aarch64-linux-android",
         "--features", "python"],
        args.out, "tiktoken-offline-metadata-replay", 120, offline_env, source_root)
    metadata = read_json(args.out / "tiktoken-offline-metadata-replay.stdout.log", 16_000_000)
    registry_ids = {(p["name"], p["version"]) for p in registry}
    for package in metadata["packages"]:
        if package["source"] is not None:
            require(package["source"] == prep.REGISTRY and (package["name"], package["version"]) in registry_ids,
                    "Offline replay selected outside the captured registry lock")
            require(Path(package["manifest_path"]).resolve().is_relative_to((captured / "vendor").resolve()),
                    "Offline replay ignored independently verified directory sources")
    prep.verify_source(source_root, source, allow_new_lock=True)
    require((source_root / "Cargo.lock").read_bytes() == lock_raw, "Offline replay changed captured Cargo.lock")
    report = {"schema_version": 1, "status": "captured-requires-review",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "original_source": source["artifact"],
              "original_source_files_unchanged": source["file_count"],
              "cargo_lock": {"path": str(source_root / "Cargo.lock"), "bytes": len(lock_raw),
                             "sha256": sha_bytes(lock_raw)},
              "online_commands": [generated, fetched], "online_tls_certificate_verification": True,
              "registry_count": len(registry), "registry": registry, "offline_replay": offline,
              "directory_source": source_config, "target_filtered_nodes": len(metadata["resolve"]["nodes"]),
              "gate": "Root must review and save this new exact Cargo.lock and registry closure before any Tiktoken build.",
              "tiktoken_source_built": False, "tiktoken_wheel_installed": False,
              "complete_four_component_runtime": False, "model_downloaded": False, "release_output": False}
    save_json(args.out / "TIKTOKEN-LOCK-CAPTURE.json", report)
    return report


def run(args, lock, prep, apt):
    require(not args.out.exists() and args.out.is_absolute(), "Use a fresh absolute native evidence path")
    args.out.mkdir(parents=True)
    result = {"schema_version": 1, "status": "started", "stage": "input-verification",
              "scope": "unpublished exact Rust component preparation", "engine_installed": False,
              "model_downloaded": False, "release_output": False, "complete_four_component_runtime": False}
    try:
        result["runtime"] = native_runtime()
        result["foundation"] = validate_foundation(args.foundation_receipt, lock)
        _, receipt, checks = prep.verify_inputs(args.inputs)
        require(receipt["stage"] == args.stage, "Native stage differs from verified inputs")
        result["input_checks"] = checks
        result["lock_sha256"] = prep.LOCK_SHA256
        result["input_receipt_sha256"] = sha_file(args.inputs / "RUST-PREPARED-INPUTS.json")
        result["archives"] = verify_archive_set(args, lock)
        with tempfile.TemporaryDirectory(prefix="neutts-rust-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            (work / "tmp").mkdir()
            (work / "sources").mkdir()
            online = args.stage == "tiktoken-lock"
            env = clean_environment(lock, work, online_lock_capture=online)
            env.update(HF_HOME=str(work / "hf-home"), HF_XET_CACHE=str(work / "hf-xet-cache"),
                       XDG_CACHE_HOME=str(work / "xdg-cache"))
            if online:
                (work / "cargo-home").mkdir()
            else:
                result["cargo_directory_source"] = cargo_source_config(work / "cargo-home", args.inputs / "vendor")
            result["stage"] = "native-signed-index"
            options, result["signed_index"] = signed_snapshot(args, lock, work)
            result["stage"] = "native-compiler-install"
            result["compiler_install"] = install_toolchain(args, lock, options, work)
            result["stage"] = "native-compiler-abi"
            result["compiler_controls"] = native_controls(args, lock, work, env, apt)
            if online:
                result["stage"] = "tiktoken-native-lock-capture"
                capture = tiktoken_capture(args, lock, prep, work, env)
                result["tiktoken_capture"] = {"status": capture["status"],
                                             "sha256": sha_file(args.out / "TIKTOKEN-LOCK-CAPTURE.json"),
                                             "cargo_lock": capture["cargo_lock"], "registry_count": capture["registry_count"]}
                result["status"] = "lock-captured-requires-review"
            else:
                result["stage"] = "isolated-python-backend"
                wheels = [{**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])}
                          for p in lock["python_build_packages"]]
                build_python, build_manifest = create_environment(
                    wheels, work / "build-venv", args.out, "rust-build-tools", prep, env)
                build_env = with_python(env, build_python)
                result["initial_build_environment"] = run_inventory(
                    build_python, build_manifest, args.out, "rust-build-tools", build_env)
                built, reports = {}, []
                (args.out / "wheels").mkdir()
                (args.out / "components").mkdir()
                for name in prep.LOCKED_NAMES:
                    source = next(p for p in lock["sources"] if p["name"] == name)
                    result["stage"] = "source-" + name
                    root = work / "sources" / source["archive_root"]
                    shutil.copytree(args.inputs / "sources" / source["archive_root"], root)
                    prep.verify_source(root, source)
                    graph = capture_cargo_metadata(source, root, lock, args, build_env)
                    wheel_dir = args.out / "wheels" / name
                    wheel_dir.mkdir()
                    component_out = args.out / "components" / name
                    component_out.mkdir()
                    command = [str(build_python), "-I", "-B", str(Path(__file__).resolve()),
                               "--mode", "build", "--source-name", name, "--source-root", str(root),
                               "--wheel-dir", str(wheel_dir), "--environment-manifest", str(build_manifest),
                               "--inputs", str(args.inputs), "--out", str(component_out)]
                    timeout = {"maturin": 1800, "hf-xet": 2400, "safetensors": 1200, "tokenizers": 1800}[name]
                    build_record = bounded_command(command, component_out, "native-build-" + name,
                                                   timeout, build_env, root)
                    outputs = list(wheel_dir.iterdir())
                    require(len(outputs) == 1 and outputs[0].suffix == ".whl", "Native backend emitted wrong outputs")
                    facts = built_wheel(outputs[0], source, prep)
                    built[name] = facts
                    report = {"name": name, "status": "wheel-built-and-verified", "cargo_graph": graph,
                              "build": build_record, "wheel": facts,
                              "native_elf": inspect_wheel_elf(outputs[0], facts, component_out, prep),
                              "source_after": source_originals_unchanged(root, source, prep)}
                    save_json(component_out / "RUST-WHEEL-RESULT.json", report)
                    reports.append({"name": name, "wheel": facts["artifact"],
                                    "receipt_sha256": sha_file(component_out / "RUST-WHEEL-RESULT.json")})
                    # Preserve a successful component checkpoint even if a later component fails.
                    save_json(args.out / "RUST-COMPONENT-CHECKPOINT.json", {"schema_version": 1, "completed": reports})
                    if name == "maturin":
                        requirements = args.out / "maturin-backend-requirements.txt"
                        prep.write_new(requirements, prep.requirement_text([facts]))
                        bounded_command(pip_command(build_python) + [
                            "install", "--no-index", "--no-deps", "--require-hashes", "--no-compile",
                            "--no-cache-dir", "--only-binary=:all:", "--find-links", str(wheel_dir),
                            "-r", str(requirements)], args.out, "maturin-backend-install", 90, build_env)
                        wheels.append(facts)
                        build_manifest = args.out / "rust-full-backend-installed-closure.json"
                        environment_manifest(wheels, build_manifest)
                        result["full_maturin_backend_environment"] = run_inventory(
                            build_python, build_manifest, args.out, "rust-full-backend", build_env)
                        cli = build_python.parent / "maturin"
                        result["built_maturin_cli"] = elf(cli, dynamic=True)
                        result["built_maturin_version"] = bounded_command(
                            [str(cli), "--version"], args.out, "built-maturin-version", 30, build_env)
                        require((args.out / "built-maturin-version.stdout.log").read_text().strip()
                                == "maturin 1.15.0", "The actual full PEP517 CLI version differs")
                result["built_wheels"] = reports
                result["stage"] = "complete-hf-safetensors-base-runtime"
                runtime_python, runtime_manifest = create_environment(
                    [built["hf-xet"], built["safetensors"]], work / "base-runtime", args.out,
                    "rust-base-runtime", prep, env)
                runtime_env = with_python(env, runtime_python)
                result["base_runtime_inventory"] = run_inventory(
                    runtime_python, runtime_manifest, args.out, "rust-base-runtime", runtime_env)
                runtime_out = args.out / "base-runtime-operations"
                runtime_out.mkdir()
                result["base_runtime_command"] = bounded_command(
                    [str(runtime_python), "-I", "-B", str(Path(__file__).resolve()), "--mode", "runtime",
                     "--environment-manifest", str(runtime_manifest), "--inputs", str(args.inputs),
                     "--apt-archives", str(args.apt_archives), "--work", str(work), "--out", str(runtime_out)],
                    args.out, "rust-base-runtime-operations", 300, runtime_env)
                result["base_runtime_receipt_sha256"] = sha_file(runtime_out / "RUST-BASE-RUNTIME-RESULT.json")
                result["tokenizers_runtime"] = {"status": "requires-external-native-pyyaml-and-full-subset",
                                               **lock["complete_runtime_handoff"]}
                result["status"] = "locked-wheels-and-two-base-runtimes-passed"
            result["stage"] = "final-original-input-verification"
            prep.verify_inputs(args.inputs)
            expected = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                                   "status": "installed"} for p in lock["build_apt"]["packages"]}
            require(package_snapshot(list(expected)) == expected, "Native compiler/runtime package selection changed")
            result["original_inputs_unchanged"] = True
            result["stage"] = "complete"
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        traceback.print_exc()
        return 1
    finally:
        save_json(args.out / "RUST-COMPONENTS-RESULT.json", result)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("run", "build", "inventory", "runtime"), default="run")
    parser.add_argument("--stage", choices=("locked-build", "tiktoken-lock"), default="locked-build")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--environment-manifest", type=Path)
    parser.add_argument("--source-name")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    prep, apt = helpers()
    if args.mode == "inventory":
        require(args.environment_manifest is not None, "Inventory needs the exact environment manifest")
        inventory_case(args, prep)
        return 0
    require(args.inputs is not None, "Native stage needs exact prepared inputs")
    lock, _ = prep.load_lock(args.inputs / prep.LOCK_FILENAME)
    if args.mode == "build":
        build_one(args, lock, prep)
        return 0
    if args.mode == "runtime":
        runtime_case(args, lock, prep, apt)
        return 0
    require(args.foundation_receipt is not None, "Native preparation needs the full passed foundation")
    if args.apt_archives is None:
        args.apt_archives = args.inputs / "apt-archives"
    return run(args, lock, prep, apt)


if __name__ == "__main__":
    raise SystemExit(main())
