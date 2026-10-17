#!/usr/bin/env python3
"""Build Regex and patched Phonemizer; prove the complete real wrapper subset.

Requires the passed native scientific foundation and separately passed exact
eSpeak C ABI component in the same disposable Termux environment. This runner
does not install APT packages, use models, synthesize speech, or admit production
features. Two fresh venvs keep build tools outside the 23-distribution runtime.
"""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
from email.policy import compat32
import hashlib
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
import traceback
import zipfile

PREFIX = Path("/data/data/com.termux/files/usr")
SCRIPT_DIR = Path(__file__).resolve().parent
PREPARER_SHA256 = "b6a358f87fb675f00a9e125b821d94ae81d9341cb9b4ab9fe2953ea1697318eb"
APT_HELPER_SHA256 = "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29"
FOUNDATION_PINS_SHA256 = "7ad635d7f1ce1157c7f3b3d7808eaf113c8bb77c4e99a8fe30b6b155faf04c5e"
FOUNDATION_CASES = {"python_dependencies", "torch", "torchaudio", "torchcodec",
                    "scipy", "llvmlite", "soxr"}
MAX_LOG_BYTES = 4_000_000


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


def safe_wheel_path(info):
    name = info.filename
    plain = name[:-1] if info.is_dir() else name
    path = PurePosixPath(plain)
    require(info.orig_filename == name and plain and str(path) == plain and not path.is_absolute()
            and "\\" not in name and ":" not in name
            and not any(p in (".", "..") for p in path.parts)
            and all(ord(c) >= 32 for c in name), "Unsafe built-wheel member")
    kind = stat.S_IFMT(info.external_attr >> 16)
    require(kind in ((0, stat.S_IFDIR) if info.is_dir() else (0, stat.S_IFREG)),
            "Built wheel contains a symlink or special member")
    require(not info.flag_bits & 1 and info.compress_type in (0, 8)
            and 0 <= info.file_size <= 200_000_000, "Invalid built-wheel member")
    return path



def module_at(name, path, digest):
    require(sha_file(path) == digest, "Reviewed helper bytes differ: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Cannot load helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    prep = module_at("_phonemizer_preparation", SCRIPT_DIR / "prepare_phonemizer_runtime.py",
                     PREPARER_SHA256)
    apt = module_at("_phonemizer_apt_provenance", SCRIPT_DIR / "validate_neutts_apt_python.py",
                    APT_HELPER_SHA256)
    return prep, apt


def clean_environment(lock):
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                "PHONEMIZER_ESPEAK_LIBRARY", "ESPEAK_DATA_PATH", "LD_PRELOAD",
                "CMAKE_TOOLCHAIN_FILE", "PIP_EXTRA_INDEX_URL", "PIP_INDEX_URL"):
        env.pop(key, None)
    env.update({
        "PATH": str(PREFIX / "bin"), "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "TMPDIR": str(PREFIX / "tmp"),
        "CC": str(PREFIX / "bin/clang"), "CXX": str(PREFIX / "bin/clang++"),
        "CFLAGS": lock["build"]["cflags"], "CXXFLAGS": lock["build"]["cflags"],
        "LDFLAGS": lock["build"]["ldflags"], "MAKEFLAGS": "-j2",
        "SOURCE_DATE_EPOCH": str(lock["build"]["source_date_epoch"]),
    })
    return env


def all_apt_pins(lock, prep):
    path = SCRIPT_DIR.parent / "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv"
    raw = prep.read_regular(path, 100_000)
    require(sha_bytes(raw) == FOUNDATION_PINS_SHA256, "Foundation archive pins changed")
    pins = {}
    for line in raw.decode().splitlines():
        name, version, arch, digest, size, filename = line.split("\t")
        require(name not in pins, "Duplicate foundation package")
        pins[name] = {"name": name, "version": version, "architecture": arch,
                      "sha256": digest, "bytes": int(size), "filename": filename}
    require(len(pins) == 122, "Incomplete foundation archive identity set")
    native_path = SCRIPT_DIR / "neutts_native_sources_lock.json"
    native_raw = prep.read_regular(native_path, 100_000)
    require(sha_bytes(native_raw) == lock["build"]["native_compiler_lock_sha256"],
            "Existing native compiler lock changed")
    native = json.loads(native_raw)
    for row in native["build_apt"]["packages"]:
        pin = {k: row[k] for k in ("name", "version", "architecture", "sha256", "bytes", "filename")}
        require(pin["name"] not in pins or pins[pin["name"]] == pin, "APT pin disagreement")
        pins[pin["name"]] = pin
    require(len(pins) == 141 and len(native["build_apt"]["packages"]) == 44,
            "Unexpected compiler/foundation package union")
    return pins, native


def archive_path(directory, pin):
    matches = list(directory.glob(pin["name"] + "_*.deb"))
    require(len(matches) == 1, "Missing or ambiguous retained APT archive: " + pin["name"])
    path = matches[0]
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size == pin["bytes"] and sha_file(path) == pin["sha256"],
            "Retained APT archive bytes differ: " + pin["name"])
    return path


def verify_toolchain(archives, native):
    rows = native["build_apt"]["packages"]
    actual = package_snapshot([p["name"] for p in rows])
    expected = {p["name"]: {"version": p["version"], "architecture": p["architecture"], "status": "installed"}
                for p in rows}
    require(actual == expected, "Exact existing compiler package set is not installed")
    records = []
    for pin in rows:
        path = archive_path(archives, pin)
        records.append({k: pin[k] for k in ("name", "version", "architecture", "bytes", "sha256")})
    compiler = PREFIX / "bin/clang"
    require(compiler.resolve().is_file(), "Native compiler is unavailable")
    result = subprocess.run([str(compiler), "--version"], capture_output=True, text=True,
                            timeout=15, check=False)
    require(result.returncode == 0 and "clang version 21.1.8" in result.stdout,
            "Unexpected native compiler identity")
    return {"status": "verified-existing-toolchain", "packages": records,
            "compiler": elf(compiler), "version_output": result.stdout,
            "apt_install_performed": False}


def validate_espeak(receipt_path, library, data, prep):
    receipt = read_json(receipt_path)
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "passed"
            and receipt.get("source_commit") == "69bfd1efde0236654ccc117a28d04aef27673a30"
            and receipt.get("model_downloaded") is False
            and receipt.get("synthesis_tested") is False
            and receipt.get("real_python_wrapper_proved") is False,
            "Separate exact native eSpeak C ABI gate did not pass")
    require(library.is_absolute() and data.is_absolute() and not library.is_symlink()
            and not data.is_symlink(), "Explicit real eSpeak paths are required")
    expected = receipt["library"]
    require(Path(expected["path"]).resolve() == library.resolve()
            and library.stat().st_size == expected["bytes"] and sha_file(library) == expected["sha256"],
            "eSpeak library differs from the passed C ABI artifact")
    fact = elf(library, dynamic=True)
    require(fact["class"] == expected["class"] and fact["machine"] == expected["machine"]
            and fact["needed"] == expected["needed"], "eSpeak ELF identity changed")
    tree = receipt["data_tree"]
    require(Path(tree["path"]).resolve() == data.resolve(), "eSpeak data root differs")
    require(tree["manifest"] == "ESPEAK-DATA-MANIFEST.json", "Unexpected eSpeak data manifest path")
    manifest_path = receipt_path.parent / tree["manifest"]
    raw_manifest = prep.read_regular(manifest_path, 2_000_000)
    require(sha_bytes(raw_manifest) == tree["manifest_sha256"], "eSpeak data manifest changed")
    manifest = json.loads(raw_manifest)
    require(isinstance(manifest, list) and len(manifest) == tree["file_count"],
            "Unexpected eSpeak data manifest shape")
    expected_paths = set()
    total = 0
    for row in manifest:
        relative = prep.safe_relative(row["path"])
        require(relative not in expected_paths and row["mode"] in ("100644", "100755"),
                "Duplicate or unsupported eSpeak data entry")
        expected_paths.add(relative)
        path = data.joinpath(*PurePosixPath(relative).parts)
        raw = prep.read_regular(path, row["size"])
        require(len(raw) == row["size"] and sha_bytes(raw) == row["sha256"],
                "eSpeak data file bytes changed")
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                == row["git_blob_sha1"], "eSpeak data git-blob identity changed")
        require((path.stat().st_mode & 0o111) == (0o111 if row["mode"] == "100755" else 0),
                "eSpeak data executable mode changed")
        total += len(raw)
    actual = set()
    for path in data.rglob("*"):
        require(not path.is_symlink(), "Symlink in eSpeak data")
        if path.is_file():
            actual.add(path.relative_to(data).as_posix())
        else:
            require(path.is_dir(), "Special eSpeak data entry")
    require(actual == expected_paths and total == tree["bytes"], "eSpeak data tree differs")
    return {"status": "verified-separate-c-abi-result", "receipt": str(receipt_path),
            "receipt_sha256": sha_file(receipt_path), "library": fact,
            "data_tree": tree, "data_manifest_sha256": sha_bytes(raw_manifest)}


def check_declared_requirements(actual, expected):
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
    def key(value):
        req = Requirement(value)
        return canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)), str(req.marker or "")
    require(sorted(map(key, actual)) == sorted(map(key, expected)),
            "Built source changed declared dependencies")


def verify_built_wheel(path, source, prep):
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import parse_tag, sys_tags
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    name, version, build, filename_tags = parse_wheel_filename(path.name)
    require(name == source["name"] and str(version) == source["version"] and not build,
            "Built wheel identity differs")
    require(filename_tags == parse_tag(source["expected_tag"]) and filename_tags <= set(sys_tags()),
            "Built wheel does not directly carry its supported original Android/pure tag")
    require(0 < path.stat().st_size <= 16_000_000, "Unexpected built wheel size")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [row.filename for row in entries]
        require(len(names) == len(set(names)) and len(entries) < 1000
                and sum(i.file_size for i in entries) <= 32_000_000, "Invalid built inventory")
        for row in entries:
            prep.safe_member(row)
        metas = [n for n in names if re.fullmatch(r"[^/]+\.dist-info/METADATA", n)]
        require(len(metas) == 1, "Ambiguous built metadata")
        mn = metas[0]
        prefix = mn.rsplit("/", 1)[0]
        wn, rn = prefix + "/WHEEL", prefix + "/RECORD"
        raw_meta = archive.read(mn)
        metadata = BytesParser(policy=compat32).parsebytes(raw_meta)
        require(canonicalize_name(prep.one_header(metadata, "Name")) == name
                and prep.one_header(metadata, "Version") == str(version), "Built metadata identity differs")
        requires_python = prep.one_header(metadata, "Requires-Python", optional=True)
        require(SpecifierSet(requires_python) == SpecifierSet(source["requires_python"])
                and SpecifierSet(requires_python).contains("3.14.6"), "Built interpreter bound changed")
        declared = metadata.get_all("Requires-Dist", [])
        check_declared_requirements(declared, source["requires_dist"])
        wheel = BytesParser(policy=compat32).parsebytes(archive.read(wn))
        pure = source["name"] == "phonemizer"
        require(wheel.get_all("Tag", []) == [source["expected_tag"]]
                and prep.one_header(wheel, "Root-Is-Purelib") == str(pure).lower(),
                "Built WHEEL metadata differs")
        native = []
        hashes = {}
        for row in entries:
            if row.is_dir():
                continue
            raw = archive.read(row)
            hashes[row.filename] = sha_bytes(raw)
            if row.filename.endswith((".so", ".pyd", ".dll", ".dylib")) or ".so." in row.filename:
                require(raw[:6] == b"\x7fELF\x02\x01" and len(raw) >= 64
                        and struct.unpack_from("<H", raw, 18)[0] == 183, "Foreign native build member")
                native.append({"member": row.filename, "bytes": len(raw), "sha256": sha_bytes(raw)})
        if pure:
            require(not native and hashes.get(source["patch"]["production_path"])
                    == source["patch"]["after_sha256"], "Phonemizer patch missing from actual wheel")
        else:
            require(len(native) == 1 and native[0]["member"].startswith("regex/_regex."),
                    "Regex native extension missing or unexpected")
        package = {
            "name": name, "version": str(version), "requires_python": requires_python,
            "requires_dist": declared, "base_requires_dist": [r for r in declared if ";" not in r],
            "artifact": {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path)},
            "wheel": {
                "tags": [source["expected_tag"]], "root_is_purelib": pure,
                "metadata_member": mn, "metadata_sha256": sha_bytes(raw_meta),
                "wheel_member": wn, "wheel_sha256": sha_bytes(archive.read(wn)),
                "record_member": rn, "record_sha256": sha_bytes(archive.read(rn)),
                "entry_count": len(entries), "file_count": len(hashes),
                "uncompressed_bytes": sum(i.file_size for i in entries),
                "max_member_bytes": max(i.file_size for i in entries),
                "members_sha256": prep.lines_sha256(sorted(names)),
                "declared_requires_dist_count": len(declared),
                "declared_requires_dist_sha256": prep.lines_sha256(declared),
            },
            "native_members": native,
        }
    prep.verify_wheel(path, package)
    return package


def build_one(args, lock, prep):
    native_runtime()
    require(Path(sys.prefix).resolve() != PREFIX, "Build requires a separate virtual environment")
    source = next(row for row in lock["sources"] if row["name"] == args.source_name)
    require(args.source_root.is_dir() and args.wheel_dir.is_dir(), "Missing isolated build paths")
    require(not any(args.wheel_dir.iterdir()), "Build wheel output must be empty")
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    inventory = {prep.canonical_name(d.metadata["Name"]): d.version
                 for d in importlib.metadata.distributions()}
    require(inventory == {p["name"]: p["version"] for p in lock["build_packages"]},
            "Build environment contains unreviewed distributions")
    for package in lock["build_packages"]:
        verify_installed_wheel(args.inputs / "wheels" / package["artifact"]["filename"],
                               package, site, prep)
    import packaging
    import setuptools
    from setuptools import build_meta
    require(setuptools.__version__ == "83.0.0" and packaging.__version__ == "26.0",
            "Unexpected build backend version")
    os.chdir(args.source_root)
    additional = build_meta.get_requires_for_build_wheel({})
    require(additional == lock["build"]["expected_dynamic_build_requirements"],
            "Build backend requested unreviewed dynamic requirements: " + repr(additional))
    filename = build_meta.build_wheel(str(args.wheel_dir), config_settings={})
    require(isinstance(filename, str) and Path(filename).name == filename
            and filename.endswith(".whl"), "Build backend returned an unsafe wheel path")
    require({p.name for p in args.wheel_dir.iterdir()} == {filename},
            "Build backend emitted unreviewed artifacts")
    print(json.dumps({"source": source["name"], "wheel": filename,
                      "dynamic_build_requirements": additional, "native_python": sys.version}))
    return 0


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


def installed_runtime(args, lock, built, prep):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(Path(sys.prefix).resolve() != PREFIX and sys.prefix != sys.base_prefix
            and str(PREFIX / "lib/python3.14/site-packages") not in sys.path,
            "Runtime must exclude global APT site-packages")
    expected = {p["name"]: p for p in lock["packages"] + built}
    require(set(expected) == set(lock["names"]) and len(expected) == 23, "Runtime wheel closure incomplete")
    inventory = list(importlib.metadata.distributions())
    require(len(inventory) == 23, "Runtime has missing or extra distributions")
    actual = {}
    allowed = set()
    records = []
    for dist in inventory:
        name = prep.canonical_name(dist.metadata["Name"])
        require(name in expected and name not in actual, "Unexpected/duplicate installed distribution")
        package = expected[name]
        metadata_dir = Path(dist._path)
        require(metadata_dir.parent.resolve() == site.resolve() and metadata_dir.name.endswith(".dist-info")
                and not metadata_dir.is_symlink(), "Distribution selected outside runtime site")
        raw = prep.read_regular(metadata_dir / "METADATA", 2_000_000)
        require(dist.version == package["version"]
                and sha_bytes(raw) == package["wheel"]["metadata_sha256"],
                "Installed distribution metadata changed")
        require(dist.metadata.get_all("Requires-Dist", []) == package["requires_dist"]
                and dist.metadata.get("Requires-Python", "") == package["requires_python"],
                "Installed declarations changed")
        base = args.out / "wheels" if name in ("phonemizer", "regex") else args.inputs / "wheels"
        row = verify_installed_wheel(base / package["artifact"]["filename"], package, site, prep)
        allowed.update(row.pop("owned_paths"))
        for filename in ("INSTALLER", "REQUESTED", "direct_url.json"):
            path = metadata_dir / filename
            if not path.exists():
                continue
            require(path.is_file() and not path.is_symlink(), "Invalid pip installation metadata")
            if filename == "INSTALLER":
                require(path.read_bytes() == b"pip\n", "Unexpected installer metadata")
            elif filename == "REQUESTED":
                require(path.read_bytes() == b"", "Unexpected REQUESTED content")
            else:
                value = json.loads(path.read_bytes())
                require(value.get("archive_info", {}).get("hashes", {}).get("sha256")
                        == package["artifact"]["sha256"], "pip direct-URL wheel hash differs")
            allowed.add(path.relative_to(site).as_posix())
        actual[name] = {"version": dist.version, "metadata_path": str(metadata_dir / "METADATA"),
                        "metadata_sha256": sha_bytes(raw),
                        "requires_dist": package["requires_dist"], "requires_python": package["requires_python"]}
        records.append(row)
    found = set()
    for path in site.rglob("*"):
        require(not path.is_symlink(), "Unexpected symlink in runtime site")
        if path.is_file():
            found.add(path.relative_to(site).as_posix())
        else:
            require(path.is_dir(), "Unexpected special file in runtime site")
    require(found == allowed, "Unreviewed installed files outside verified wheel members")
    return {"status": "passed", "distribution_count": 23, "active_edge_count": 26,
            "distributions": actual, "installed_wheels": sorted(records, key=lambda p: p["name"]),
            "graph_edges": lock["edges"], "build_distributions_visible": False}


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


def native_operations(args, lock, prep):
    require("dlinfo" not in sys.modules, "dlinfo was imported before the explicit-library probe")
    import regex
    import regex._regex
    import rpds
    import rpds.rpds
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    built = read_json(args.out / "PHONEMIZER-BUILT-WHEELS.json")["packages"]
    native_expected = {p["name"]: p for p in lock["packages"] + built}
    for name, module in (("regex", regex._regex), ("rpds-py", rpds.rpds)):
        members = native_expected[name]["native_members"]
        require(len(members) == 1, "Unexpected native extension inventory")
        row = members[0]
        path = Path(module.__file__)
        require(path.resolve() == (site / row["member"]).resolve()
                and path.stat().st_size == row["bytes"] and sha_file(path) == row["sha256"],
                "Actual imported native module differs from its verified runtime wheel")
    graphemes = regex.findall(r"\X", "a\u0301🇦🇷👩‍💻")
    require(graphemes == ["a\u0301", "🇦🇷", "👩‍💻"], "Native Regex grapheme operation failed")
    require(regex.findall(r"(?V1)\p{Letter}+", "café123") == ["café"],
            "Native Regex Unicode property operation failed")
    fuzzy = regex.fullmatch(r"(?:colour){e<=1}", "color")
    require(fuzzy is not None and sum(fuzzy.fuzzy_counts) == 1, "Native Regex fuzzy operation failed")
    original = rpds.HashTrieMap({"first": 1})
    updated = original.insert("second", 2)
    require(dict(original) == {"first": 1} and dict(updated) == {"first": 1, "second": 2},
            "Native RPDS persistent-map operation failed")
    from phonemizer import phonemize
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    from phonemizer.backend.espeak import api
    require(sha_file(Path(api.__file__)) == lock["sources"][0]["patch"]["after_sha256"],
            "Real imported Phonemizer API lacks the reviewed patch")
    os.environ["ESPEAK_DATA_PATH"] = str(args.espeak_data)
    EspeakWrapper.set_library(str(args.espeak_library))
    wrapper = EspeakWrapper()
    require(wrapper.library_path.resolve() == args.espeak_library.resolve()
            and wrapper.data_path.resolve() == args.espeak_data.resolve(),
            "Real wrapper selected a different eSpeak library or data tree")
    # Exact 3.3.0 API copies each library before initialization; keep this real
    # wrapper alive while checking the loaded copy, without replacing any API.
    copied = Path(wrapper._espeak._library._name)
    require(copied.is_file() and not copied.is_symlink()
            and sha_file(copied) == sha_file(args.espeak_library),
            "Actual per-wrapper native library copy differs")
    wrapper.set_voice("en-us")
    raw_phonemes = wrapper.text_to_phonemes("hello")
    expected = raw_phonemes.replace("_", "").strip()
    result = phonemize("hello", language="en-us", backend="espeak", strip=True,
                       preserve_punctuation=True, with_stress=True, njobs=1)
    require(result == expected and result != "hello" and "ˈ" in result,
            "Public phonemize did not match the actual native wrapper result")
    no_stress = phonemize("hello", language="en-us", backend="espeak", strip=True,
                          with_stress=False, njobs=1)
    require(no_stress == result.replace("ˈ", "").replace("ˌ", ""),
            "Public phonemize stress option did not propagate")
    texts = ["Hello, world!", "A simple test."]
    batch = phonemize(texts, language="en-us", backend="espeak", strip=True,
                      preserve_punctuation=True, with_stress=True, njobs=1)
    repeated = phonemize(texts, language="en-us", backend="espeak", strip=True,
                         preserve_punctuation=True, with_stress=True, njobs=1)
    require(isinstance(batch, list) and len(batch) == 2 and batch == repeated
            and batch[0].endswith("!") and "," in batch[0] and batch[1].endswith(".")
            and batch != texts, "Public batch phonemization or punctuation failed")
    require("dlinfo" not in sys.modules, "Explicit-path public wrapper imported dlinfo")
    return {
        "status": "passed",
        "regex": {"graphemes": graphemes, "fuzzy_counts": list(fuzzy.fuzzy_counts),
                  "native_module": elf(Path(regex._regex.__file__), dynamic=True)},
        "rpds": {"original": dict(original), "updated": dict(updated),
                 "native_module": elf(Path(rpds.rpds.__file__), dynamic=True)},
        "phonemizer": {"api_path": api.__file__, "api_sha256": sha_file(Path(api.__file__)),
                       "library": elf(args.espeak_library, dynamic=True),
                       "actual_wrapper_copy": elf(copied, dynamic=True),
                       "data_path": str(wrapper.data_path), "version": list(wrapper.version),
                       "raw_wrapper_phonemes": raw_phonemes, "public_output": result,
                       "without_stress": no_stress, "batch_output": batch,
                       "dlinfo_imported": False, "public_api": "phonemizer.phonemize",
                       "njobs": 1, "real_wrapper_proved": True},
        "model_downloaded": False, "speech_synthesis_tested": False,
    }


def runtime_case(args, lock, prep, apt):
    report = {"schema_version": 1, "status": "failed", "model_downloaded": False,
              "synthesis_tested": False, "production_admission_changed": False}
    try:
        report["runtime"] = native_runtime()
        pins, _ = all_apt_pins(lock, prep)
        report["espeak_input"] = validate_espeak(args.espeak_receipt, args.espeak_library, args.espeak_data, prep)
        built = read_json(args.out / "PHONEMIZER-BUILT-WHEELS.json")["packages"]
        report["installed"] = installed_runtime(args, lock, built, prep)
        report["operations"] = native_operations(args, lock, prep)
        report["mapped_apt_libraries"] = verify_mapped_apt_libraries(args.apt_archives, pins, apt)
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "PHONEMIZER-RUNTIME-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def pip_command(python):
    return [str(PREFIX / "bin/python"), "-I", "-B", "-m", "pip", "--python", str(python)]


def build_runtime(args, lock, prep, env, work):
    base = str(PREFIX / "bin/python")
    build_venv, runtime_venv = work / "build-venv", work / "runtime-venv"
    for name, path in (("build", build_venv), ("runtime", runtime_venv)):
        bounded_command([base, "-I", "-B", "-m", "venv", "--without-pip", str(path)],
                        args.out, "phonemizer-create-" + name, 60, env)
        require("include-system-site-packages = false" in (path / "pyvenv.cfg").read_text(),
                "Virtual environment exposed the global site")
    build_python = build_venv / "bin/python"
    runtime_python = runtime_venv / "bin/python"
    install_options = ["install", "--no-index", "--no-deps", "--require-hashes",
                       "--only-binary=:all:", "--no-compile", "--no-cache-dir",
                       "--find-links", str(args.inputs / "wheels")]
    bounded_command(pip_command(build_python) + install_options
                    + ["-r", str(args.inputs / "build-requirements.txt")],
                    args.out, "phonemizer-install-build-inputs", 90, env)
    source_root = work / "sources"
    shutil.copytree(args.inputs / "sources", source_root)
    (args.out / "wheels").mkdir()
    built, build_records = [], []
    for source in lock["sources"]:
        wheel_dir = work / ("wheel-" + source["name"])
        wheel_dir.mkdir()
        command = [str(build_python), "-I", "-B", str(Path(__file__).resolve()),
                   "--phase", "build", "--inputs", str(args.inputs), "--out", str(args.out),
                   "--source-name", source["name"], "--source-root", str(source_root / source["archive_root"]),
                   "--wheel-dir", str(wheel_dir)]
        record = bounded_command(command, args.out, "phonemizer-build-" + source["name"],
                                 lock["build"]["maximum_build_seconds"], env)
        found = list(wheel_dir.iterdir())
        require(len(found) == 1 and found[0].suffix == ".whl", "Source build output differs")
        package = verify_built_wheel(found[0], source, prep)
        if source["name"] == "regex":
            log = (args.out / ("phonemizer-build-" + source["name"] + ".stdout.log")).read_text()
            log += (args.out / ("phonemizer-build-" + source["name"] + ".stderr.log")).read_text()
            require("--target=aarch64-linux-android24" in log and "-march=native" not in log,
                    "Regex build did not record portable native compiler flags")
        found[0].rename(args.out / "wheels" / found[0].name)
        built.append(package)
        build_records.append({"name": source["name"], "result": record})
    save_json(args.out / "PHONEMIZER-BUILT-WHEELS.json",
              {"schema_version": 1, "packages": built, "source_builds": build_records})
    complete = sorted(lock["packages"] + built, key=lambda p: p["name"])
    require([p["name"] for p in complete] == lock["names"], "Runtime install closure differs")
    prep.write_new(args.out / "runtime-requirements.txt", prep.requirement_text(complete))
    bounded_command(pip_command(runtime_python) + install_options
                    + ["--find-links", str(args.out / "wheels"), "-r", str(args.out / "runtime-requirements.txt")],
                    args.out, "phonemizer-install-runtime", 120, env)
    pip_record = bounded_command(pip_command(runtime_python) + ["check"],
                                 args.out, "phonemizer-pip-check", 60, env)
    return runtime_python, built, build_records, pip_record


def run(args, lock, prep, apt):
    import resource
    require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the real APT base Python")
    require(not args.out.exists() and not args.out.is_symlink(), "Fresh component output is required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "stage": "preflight",
              "scope": "Complete 23-distribution Phonemizer subset and actual public eSpeak wrapper",
              "model_downloaded": False, "synthesis_tested": False,
              "production_admission_changed": False, "release_output": False,
              "lock_sha256": prep.LOCK_SHA256}
    try:
        report["runtime"] = native_runtime()
        pins, native = all_apt_pins(lock, prep)
        report["foundation"] = validate_foundation(
            args.foundation_receipt, {"foundation": {"apt_metadata_ledger_sha256": lock["apt_metadata_ledger"]["sha256"]}})
        metadata = apt.load_manifest(SCRIPT_DIR / "neutts_apt_python_metadata.json")
        # This projection verifies the two APT runtime archives and full shipped
        # pip source; the unchanged separate foundation receipt covers its seven
        # scientific components. No shortened scientific receipt is fabricated.
        report["apt_runtime_provenance"] = apt.apt_provenance(
            {"runtime": metadata["runtime"], "apt_distributions": []}, args.apt_archives)
        report["toolchain"] = verify_toolchain(args.apt_archives, native)
        report["espeak_input"] = validate_espeak(args.espeak_receipt, args.espeak_library, args.espeak_data, prep)
        env = clean_environment(lock)
        require(resource.getrlimit(resource.RLIMIT_AS)[0] in (-1, resource.RLIM_INFINITY)
                or resource.getrlimit(resource.RLIMIT_AS)[0] >= 2_000_000_000,
                "Existing memory limit is too small for native source preparation")
        with tempfile.TemporaryDirectory(prefix="phonemizer-native-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            report["stage"] = "native-build"
            save_json(args.out / "PHONEMIZER-COMPONENT-RESULT.json", report)
            python, built, builds, pip_record = build_runtime(args, lock, prep, env, work)
            report["built_wheels"] = [{k: p[k] for k in ("name", "version", "artifact", "native_members")} for p in built]
            report["source_builds"] = builds
            report["raw_pip_check"] = pip_record
            report["stage"] = "real-runtime"
            command = [str(python), "-I", "-B", str(Path(__file__).resolve()),
                       "--phase", "runtime", "--inputs", str(args.inputs), "--out", str(args.out),
                       "--apt-archives", str(args.apt_archives),
                       "--espeak-receipt", str(args.espeak_receipt),
                       "--espeak-library", str(args.espeak_library), "--espeak-data", str(args.espeak_data)]
            report["runtime_process"] = bounded_command(command, args.out, "phonemizer-runtime", 180, env)
            result = read_json(args.out / "PHONEMIZER-RUNTIME-RESULT.json", 8_000_000)
            require(result.get("status") == "passed", "Complete native runtime gate did not pass")
            report["runtime_receipt"] = {"path": "PHONEMIZER-RUNTIME-RESULT.json",
                                         "sha256": sha_file(args.out / "PHONEMIZER-RUNTIME-RESULT.json")}
            report["status"], report["stage"] = "passed", "complete"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        save_json(args.out / "PHONEMIZER-COMPONENT-RESULT.json", report)
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
    parser.add_argument("--espeak-receipt", type=Path)
    parser.add_argument("--espeak-library", type=Path)
    parser.add_argument("--espeak-data", type=Path)
    parser.add_argument("--source-name", choices=("phonemizer", "regex"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    args = parser.parse_args(argv)
    prep, apt = helpers()
    lock, _ = prep.verify_inputs(args.inputs)
    if args.phase == "build":
        require(args.source_name is not None and args.source_root is not None and args.wheel_dir is not None,
                "Build phase requires explicit source and wheel paths")
        return build_one(args, lock, prep)
    require(all(value is not None for value in
                (args.apt_archives, args.espeak_receipt, args.espeak_library, args.espeak_data)),
            "Native phase requires retained archives and separate eSpeak artifacts")
    if args.phase == "runtime":
        return runtime_case(args, lock, prep, apt)
    require(args.foundation_receipt is not None, "Full passed foundation receipt is required")
    return run(args, lock, prep, apt)


if __name__ == "__main__":
    raise SystemExit(main())
