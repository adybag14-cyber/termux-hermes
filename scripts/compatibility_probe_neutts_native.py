#!/usr/bin/env python3
"""Bounded native Numba/llama CPU build and behavior gate, without models.

Run only after the separate seven-case APT scientific foundation has passed.
Compiler archives, source bytes, backend wheels and build settings are frozen;
the published Hermes package and its managed PM graph are not involved.
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
import tempfile
import traceback
import zipfile

PREFIX = Path("/data/data/com.termux/files/usr")
SCRIPT_DIR = Path(__file__).resolve().parent
FOUNDATION_CASES = {"python_dependencies", "torch", "torchaudio", "torchcodec",
                    "scipy", "llvmlite", "soxr"}
CASES = ("installed_inputs", "numba", "llama")
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


def support():
    path = SCRIPT_DIR / "prepare_neutts_native_sources.py"
    spec = importlib.util.spec_from_file_location("_neutts_native_preparation", path)
    require(spec is not None and spec.loader is not None, "Cannot load input verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def mapped_libraries():
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("/"):
            continue
        path = parts[5]
        if ".so" in path and any(term in path for term in
                                 ("/numba/", "/llvmlite/", "/numpy/", "/llama_cpp/")):
            require(not path.endswith(" (deleted)"), "Deleted native mapping")
            paths.add(Path(path).resolve())
    return [elf(path, dynamic=True) for path in sorted(paths)]


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


def expected_requirements(lock):
    return "".join(f"{p['name']}=={p['version']} --hash=sha256:{p['artifact']['sha256']}\n"
                   for p in lock["additional_python_wheels"]).encode()


def expected_tsv(packages):
    return "".join("\t".join((p["name"], p["version"], p["architecture"], p["sha256"],
                              str(p["bytes"]), p["filename"])) + "\n" for p in packages).encode()


def validate_inputs(inputs, verifier):
    lock, raw = verifier.load_lock(inputs / "neutts-native-sources-lock.json")
    receipt = read_json(inputs / "PREPARED-NATIVE-SOURCES.json")
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "verified"
            and receipt.get("lock_sha256") == verifier.LOCK_SHA256
            and receipt.get("wheel_verifier_sha256") == verifier.CORE_VERIFIER_SHA256,
            "Unverified prepared source inputs")
    require(receipt.get("models_fetched") is False
            and receipt.get("build_or_install_performed") is False,
            "Unexpected prepared input scope")
    wheels = verifier.core_verifier()
    wheel_rows = []
    expected_names = {p["artifact"]["filename"] for p in lock["additional_python_wheels"]}
    require({p.name for p in (inputs / "wheels").iterdir()} == expected_names,
            "Extra or missing build/runtime wheel")
    for package in lock["additional_python_wheels"]:
        wheel_rows.append(wheels.verify_wheel(inputs / "wheels" / package["artifact"]["filename"],
                                              package))
    require(verifier.read_regular(inputs / "requirements.txt", 10_000) == expected_requirements(lock),
            "Additional hashed requirements changed")
    for name, packages in (
        ("build-apt-closure.tsv", lock["build_apt"]["packages"]),
        ("build-apt-additional.tsv", [p for p in lock["build_apt"]["packages"] if p["additional"]]),
    ):
        require(verifier.read_regular(inputs / name, 100_000) == expected_tsv(packages),
                "Build APT TSV differs from frozen lock")
    source_checks = {}
    pin = lock["sources"]["numba"]
    rows = read_json(inputs / "source-manifests/numba.json")
    source_checks["numba"] = verifier.verify_source_tree(inputs / "sources" / pin["root"],
                                                          rows, pin["manifest"])
    wrapper = lock["sources"]["llama-cpp-python"]
    vendor = wrapper["submodules"]["vendor/llama.cpp"]
    wrapper_rows = read_json(inputs / "source-manifests/llama-cpp-python.json")
    vendor_rows = read_json(inputs / "source-manifests/llama.cpp.json")
    verifier.check_manifest(wrapper_rows, wrapper["patched_manifest"])
    verifier.check_manifest(vendor_rows, vendor["manifest"])
    combined = wrapper_rows + [{**row, "path": "vendor/llama.cpp/" + row["path"]}
                               for row in vendor_rows]
    root = inputs / "sources/llama-cpp-python"
    require(verifier.tree_files(root) == {r["path"] for r in combined},
            "Missing or extra wrapper/vendor source")
    for row in combined:
        raw = verifier.read_regular(root.joinpath(*verifier.safe_path(row["path"]).parts), row["size"])
        require(verifier.file_row(row["path"], row["mode"], raw) == row,
                "Prepared wrapper/vendor source bytes changed")
    for row in vendor["omitted_model_fixtures"]:
        require(not (root / "vendor/llama.cpp" / row["path"]).exists(),
                "Omitted model fixture was supplied")
    source_checks["llama-cpp-python"] = wrapper["patched_manifest"]
    source_checks["llama.cpp"] = vendor["manifest"]
    return lock, {"lock_sha256": verifier.LOCK_SHA256,
                  "prepared_receipt_sha256": sha_file(inputs / "PREPARED-NATIVE-SOURCES.json"),
                  "sources": source_checks, "wheels": wheel_rows}


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


def validate_apt_archives(archives, lock):
    rows = []
    for package in lock["build_apt"]["packages"]:
        matches = list(archives.glob(package["name"] + "_*.deb"))
        require(len(matches) == 1, "Missing or duplicate exact APT build archive: " + package["name"])
        path = matches[0]
        require(stat.S_ISREG(path.lstat().st_mode) and path.stat().st_size == package["bytes"]
                and sha_file(path) == package["sha256"], "APT build archive bytes differ")
        result = subprocess.run(
            [str(PREFIX / "bin/dpkg-deb"), "-f", str(path), "Package", "Version", "Architecture"],
            capture_output=True, timeout=20, check=False,
        )
        fields = dict(line.split(": ", 1) for line in result.stdout.decode().splitlines()
                      if ": " in line)
        require(result.returncode == 0 and fields == {
            "Package": package["name"], "Version": package["version"],
            "Architecture": package["architecture"]}, "APT archive control identity differs")
        rows.append({**package, "path": str(path)})
    return rows


def validate_apt_plan(text, additional):
    require(not any(line.startswith("Remv ") for line in text.splitlines()),
            "APT proposed a removal")
    names = [line.split()[1].split(":", 1)[0] for line in text.splitlines()
             if line.startswith("Inst ")]
    require(len(names) == len(set(names)) and set(names) == set(additional),
            "APT proposed an unreviewed addition, upgrade or omission")


def install_toolchain(lock, archives, out, work):
    verified = validate_apt_archives(archives, lock)
    existing = [p for p in verified if not p["additional"]]
    before = package_snapshot([p["name"] for p in existing])
    for p in existing:
        require(before[p["name"]] == {"version": p["version"], "architecture": p["architecture"],
                                      "status": "installed"}, "APT foundation/build overlap changed")
    additions = [p for p in verified if p["additional"]]
    require(len(additions) == 19 and len(verified) == 44, "Unexpected compiler closure")
    cache = work / "apt-archives"
    (cache / "partial").mkdir(parents=True)
    for p in additions:
        shutil.copyfile(p["path"], cache / Path(p["path"]).name)
    specs = [p["name"] + "=" + p["version"] for p in additions]
    command = [str(PREFIX / "bin/apt-get"), "-o", "Dir::Cache::archives=" + str(cache),
               "-o", "Dpkg::Options::=--force-confnew", "--no-download", "--no-remove",
               "--no-install-recommends", "--reinstall", "install", *specs]
    bounded_command(command[:1] + ["-s"] + command[1:], out, "native-apt-plan", 60)
    validate_apt_plan((out / "native-apt-plan.stdout.log").read_text(), [p["name"] for p in additions])
    installed = bounded_command(command[:1] + ["-y"] + command[1:],
                                out, "native-apt-install", 300)
    after = package_snapshot([p["name"] for p in verified])
    for p in verified:
        require(after[p["name"]] == {"version": p["version"], "architecture": p["architecture"],
                                     "status": "installed"}, "Installed compiler closure differs")
    report = {"status": "passed", "mode": "19 additions from verified retained no-download archives",
              "verified_archive_count": 44, "additional_count": 19, "archives": verified,
              "installed_packages": after, "apt": installed}
    save_json(out / "NEUTTS-NATIVE-BUILD-APT.json", report)
    return report


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


def verify_built_wheel(path, package, lock):
    from pip._vendor.packaging.tags import parse_tag, sys_tags
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    from pip._vendor.packaging.requirements import Requirement

    identity, version, _, filename_tags = parse_wheel_filename(path.name)
    require(identity == package and str(version) == lock["sources"][package]["version"],
            "Built wheel identity differs")
    platform_tag = lock["target"]["wheel_platform"]
    expected_tag = ("cp314-cp314-" if package == "numba" else "py3-none-") + platform_tag
    require(filename_tags == parse_tag(expected_tag) and filename_tags <= set(sys_tags()),
            "Built wheel must directly carry a supported modern Android tag")
    require(path.stat().st_size < 300_000_000, "Oversized built wheel")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        require(len(names) == len(set(names)) and sum(i.file_size for i in entries) < 600_000_000,
                "Duplicate or oversized built-wheel inventory")
        for item in entries:
            safe_wheel_path(item)
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "Ambiguous built distribution")
        mn = metadata_names[0]
        prefix = mn.rsplit("/", 1)[0]
        metadata = BytesParser(policy=compat32).parsebytes(archive.read(mn))
        require(canonicalize_name(metadata["Name"]) == package
                and metadata["Version"] == str(version), "Built metadata identity differs")
        declared = [Requirement(v) for v in metadata.get_all("Requires-Dist", [])
                    if ";" not in v]
        expected = [Requirement(v) for v in lock["sources"][package]["runtime_requires_dist"]]
        require(sorted(map(str, declared)) == sorted(map(str, expected)),
                "Built package changed base dependency requirements")
        wheel = BytesParser(policy=compat32).parsebytes(archive.read(prefix + "/WHEEL"))
        require(wheel.get_all("Tag") == [expected_tag] and wheel["Root-Is-Purelib"] == "false",
                "Built WHEEL metadata does not match native artifact")
        hashes, sizes, native = {}, {}, {}
        for item in entries:
            if item.is_dir():
                continue
            raw = archive.read(item)
            hashes[item.filename], sizes[item.filename] = sha_bytes(raw), len(raw)
            if item.filename.endswith(".so") or ".so." in item.filename:
                require(raw[:6] == b"\x7fELF\x02\x01" and len(raw) >= 64
                        and struct.unpack_from("<H", raw, 18)[0] == 183,
                        "Built wheel contains a foreign native library")
                native[item.filename] = {"sha256": sha_bytes(raw), "bytes": len(raw)}
        rn = prefix + "/RECORD"
        records = list(csv.reader(io.StringIO(archive.read(rn).decode())))
        require(all(len(r) == 3 for r in records) and len(records) == len(hashes)
                and {r[0] for r in records} == set(hashes), "Built RECORD inventory differs")
        for name, encoded, size in records:
            if name == rn:
                require(encoded == size == "", "Invalid RECORD self-entry")
            else:
                require(encoded == "sha256=" + base64.urlsafe_b64encode(
                    bytes.fromhex(hashes[name])).decode().rstrip("=")
                    and size == str(sizes[name]), "Built RECORD hash differs")
        require(native, "Built native package has no native members")
        if package == "numba":
            require(any("/workqueue." in n for n in native)
                    and not any("/tbbpool." in n or "/omppool." in n for n in native),
                    "Numba is not the requested workqueue-only build")
        else:
            for basename in ("libllama.so", "libggml.so", "libggml-base.so", "libggml-cpu.so", "libmtmd.so"):
                require(any(PurePosixPath(n).name == basename for n in native),
                        "Missing matching vendored library: " + basename)
            loader = "llama_cpp/_ctypes_extensions.py"
            expected_loader = next(r["after_sha256"] for r in
                                   lock["sources"][package]["patch"]["changes"] if r["path"] == loader)
            require(hashes[loader] == expected_loader, "Android loader patch is absent")
    return {"name": package, "version": str(version), "filename": path.name,
            "bytes": path.stat().st_size, "sha256": sha_file(path), "tag": expected_tag,
            "metadata_sha256": hashes[mn], "native_members": native, "member_sha256": hashes}


def build_packages(lock, inputs, out, work):
    venv = work / "venv"
    base_python = str(PREFIX / "bin/python")
    bounded_command([base_python, "-I", "-B", "-m", "venv", "--system-site-packages",
                     "--without-pip", str(venv)], out, "native-create-venv", 60)
    python = str(venv / "bin/python")
    env = dict(os.environ)
    # These are native builds. CPython expects an OS/machine cross-build pair,
    # whereas scikit-build-core treats that override as a finished platform tag.
    # Let both backends derive the API24 Android tag from the exact interpreter.
    env.pop("_PYTHON_HOST_PLATFORM", None)
    env.update({"PIP_NO_INDEX": "1", "PIP_CONFIG_FILE": os.devnull,
                "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_CACHE_DIR": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    bounded_command([python, "-I", "-B", "-m", "pip", "install", "--no-index", "--no-deps",
                     "--only-binary=:all:", "--require-hashes", "--force-reinstall", "--no-compile",
                     "--find-links", str(inputs / "wheels"), "-r", str(inputs / "requirements.txt")],
                    out, "native-build-python-inputs", 90, env=env)
    env.update(lock["build"]["numba_environment"])
    env.update({
        "CC": str(PREFIX / "bin/clang"), "CXX": str(PREFIX / "bin/clang++"),
        "CFLAGS": lock["build"]["cflags"], "CXXFLAGS": lock["build"]["cflags"],
        "LDFLAGS": "--target=aarch64-linux-android24",
        "CMAKE_BUILD_PARALLEL_LEVEL": "2", "MAKEFLAGS": "-j2",
        "CMAKE_GENERATOR": "Ninja", "SOURCE_DATE_EPOCH": str(lock["build"]["source_date_epoch"]),
        "CMAKE_ARGS": " ".join("-D" + k + "=" + v for k, v in lock["build"]["llama_cmake"].items()),
        "SKBUILD_BUILD_DIR": str(work / "llama-cmake"), "SKBUILD_CMAKE_BUILD_TYPE": "Release",
    })
    source_root = work / "sources"
    shutil.copytree(inputs / "sources", source_root)
    (out / "wheels").mkdir()
    builds = []
    for package, directory, seconds in (("numba", lock["sources"]["numba"]["root"], 900),
                                         ("llama-cpp-python", "llama-cpp-python", 1200)):
        stage = out / ("wheel-" + package)
        stage.mkdir()
        command = [python, "-I", "-B", "-m", "pip", "wheel", "--no-index", "--no-deps",
                   "--no-build-isolation", "--no-cache-dir", "--no-clean",
                   "--wheel-dir", str(stage), str(source_root / directory)]
        build = bounded_command(command, out, "native-build-" + package, seconds, env=env)
        wheels = list(stage.iterdir())
        require(len(wheels) == 1 and wheels[0].suffix == ".whl", "Build emitted an unexpected artifact")
        facts = verify_built_wheel(wheels[0], package, lock)
        target = out / "wheels" / wheels[0].name
        wheels[0].rename(target)
        stage.rmdir()
        builds.append({**facts, "build": build})
    cache = work / "llama-cmake/CMakeCache.txt"
    require(cache.is_file(), "Missing actual llama CMake configuration")
    text = cache.read_text()
    for key, value in lock["build"]["llama_cmake"].items():
        if key.startswith("CMAKE_") or key.startswith("FETCHCONTENT_"):
            continue
        require(re.search(r"^" + re.escape(key) + r":[^=]+=" + re.escape(value) + r"$",
                          text, re.MULTILINE), "CMake did not retain the frozen option: " + key)
    shutil.copyfile(cache, out / "llama-CMakeCache.txt")
    compile_commands = work / "llama-cmake/compile_commands.json"
    require(compile_commands.is_file(), "Missing actual compiler-command receipt")
    commands = read_json(compile_commands, 10_000_000)
    serialized = json.dumps(commands)
    require("-march=native" not in serialized and "-mcpu=native" not in serialized
            and "-fopenmp" not in serialized and "--target=aarch64-linux-android24" in serialized,
            "Compiler flags departed from the portable Android CPU build")
    shutil.copyfile(compile_commands, out / "llama-compile_commands.json")
    requirements = "".join(f"{p['name']}=={p['version']} --hash=sha256:{p['sha256']}\n"
                           for p in builds)
    (out / "built-requirements.txt").write_text(requirements)
    bounded_command([python, "-I", "-B", "-m", "pip", "install", "--no-index", "--no-deps",
                     "--require-hashes", "--only-binary=:all:", "--no-compile",
                     "--find-links", str(out / "wheels"), "-r", str(out / "built-requirements.txt")],
                    out, "native-install-built-wheels", 90, env=env)
    save_json(out / "NEUTTS-NATIVE-BUILT-WHEELS.json", {"schema_version": 1, "wheels": builds})
    # Keep runtime cases free of cross-build platform overrides as well.
    env.pop("_PYTHON_HOST_PLATFORM", None)
    return venv, builds, env


def installed_wheel(path, expected_name, venv):
    site = venv / "lib/python3.14/site-packages"
    checked, rewritten = [], []
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            safe_wheel_path(item)
            parts = PurePosixPath(item.filename).parts
            if item.filename.endswith(".dist-info/RECORD"):
                rewritten.append({"path": item.filename, "reason": "pip rewrites installation RECORD"})
                continue
            script = False
            if parts[0].endswith(".data"):
                require(len(parts) >= 3, "Malformed wheel data path")
                if parts[1] in ("purelib", "platlib"):
                    target = site.joinpath(*parts[2:])
                elif parts[1] == "scripts":
                    target = venv.joinpath("bin", *parts[2:])
                    script = True
                else:
                    raise ProbeError("Unexpected wheel installation scheme")
            else:
                target = site.joinpath(*parts)
            require(target.is_file() and not target.is_symlink(), "Missing installed wheel member")
            before, after = archive.read(item), target.read_bytes()
            if before != after:
                require(script and before.startswith((b"#!python\n", b"#!pythonw\n"))
                        and after.startswith(b"#!") and before.split(b"\n", 1)[1] == after.split(b"\n", 1)[1],
                        "Installed wheel member changed beyond the permitted script shebang")
                rewritten.append({"path": item.filename, "reason": "pip rewrites script interpreter",
                                  "installed_sha256": sha_bytes(after)})
            else:
                checked.append({"path": item.filename, "sha256": sha_bytes(after)})
    selected = importlib.metadata.distribution(expected_name)
    require(Path(selected.locate_file("")).resolve() == site.resolve(),
            "Distribution resolved outside the isolated native venv")
    return {"name": expected_name, "wheel_sha256": sha_file(path),
            "installed_byte_identical_count": len(checked), "members": checked,
            "documented_rewrites": rewritten}


def installed_inputs_case(lock, inputs, out):
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
    from pip._vendor.packaging.version import Version

    venv = Path(sys.prefix)
    require(venv != PREFIX and Path(sys.base_prefix).resolve() == PREFIX,
            "Expected isolated system-site-packages native venv")
    built = read_json(out / "NEUTTS-NATIVE-BUILT-WHEELS.json")["wheels"]
    identities = [installed_wheel(inputs / "wheels" / p["artifact"]["filename"], p["name"], venv)
                  for p in lock["additional_python_wheels"]]
    identities.extend(installed_wheel(out / "wheels" / p["filename"], p["name"], venv) for p in built)
    expected = dict(lock["foundation"]["python_distributions"])
    expected.update({p["name"]: p["version"] for p in lock["additional_python_wheels"]})
    expected.update({p["name"]: p["version"] for p in built})
    environment = default_environment()
    environment["extra"] = ""
    graph = []
    for name, version in sorted(expected.items()):
        distribution = importlib.metadata.distribution(name)
        require(distribution.version == version, "Selected Python dependency version changed: " + name)
        for text in distribution.requires or []:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            dependency = canonicalize_name(requirement.name)
            require(dependency in expected, "Unfrozen active base dependency: " + dependency)
            require(Version(expected[dependency]) in requirement.specifier,
                    "Native base dependency version conflict")
            graph.append({"parent": name, "requirement": text, "selected": expected[dependency]})
    import setuptools
    import wheel
    require(wheel.__version__ == "0.46.3"
            and Path(wheel.__file__).resolve().is_relative_to(
                Path(setuptools.__file__).resolve().parent / "_vendor"),
            "Numba wheel backend must be the already frozen setuptools-vendored wheel")
    return {"installed_wheels": identities, "active_base_dependencies": graph,
            "setuptools_vendored_wheel": {"version": wheel.__version__, "path": wheel.__file__},
            "physical_audio_tested": False}


def numba_case():
    import llvmlite
    import llvmlite.binding as llvm
    import numpy as np
    import numba
    from numba import float64, guvectorize, njit

    require(numba.__version__ == "0.67.0" and llvmlite.__version__ == "0.49.0"
            and np.__version__ == "2.5.4", "Native JIT versions differ")

    @njit(cache=False)
    def weighted_sum(values):
        result = 0.0
        for index in range(len(values)):
            result += (index + 1) * values[index]
        return result

    values = np.linspace(-2.0, 2.0, 17)
    expected = sum((i + 1) * float(value) for i, value in enumerate(values))
    actual = weighted_sum(values)
    require(abs(actual - expected) < 1e-12 and len(weighted_sum.nopython_signatures) == 1,
            "Numba CPU nopython JIT oracle failed")
    assembly = weighted_sum.inspect_asm(weighted_sum.signatures[0])
    require(isinstance(assembly, str) and len(assembly) > 100, "No actual generated JIT assembly")

    @guvectorize([(float64[:], float64[:])], "(n)->(n)", target="parallel", nopython=True)
    def affine(source, destination):
        for index in range(source.shape[0]):
            destination[index] = 2.0 * source[index] + 1.0

    matrix = np.arange(24, dtype=np.float64).reshape(4, 6) / 8.0
    result = affine(matrix)
    require(np.array_equal(result, matrix * 2.0 + 1.0), "Parallel guvectorize numerical oracle failed")
    require(numba.threading_layer() == "workqueue" and numba.get_num_threads() == 2,
            "Parallel execution did not use the exact two-thread workqueue path")
    require(Path(numba.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
            "Numba import escaped its newly built isolated venv")
    return {"jit_actual": actual, "jit_expected": expected,
            "nopython_signature_count": len(weighted_sum.nopython_signatures),
            "generated_assembly_sha256": sha_bytes(assembly.encode()),
            "guvectorize_shape": list(result.shape), "guvectorize_exact": True,
            "threading_layer": numba.threading_layer(), "threads": numba.get_num_threads(),
            "llvm_version": list(llvm.llvm_version_info), "llvm_default_triple": llvm.get_default_triple()}


def llama_case():
    import llama_cpp
    from llama_cpp import llama_cpp as api

    require(llama_cpp.__version__ == "0.3.36", "Built llama Python version differs")
    require(Path(llama_cpp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
            "llama import escaped its newly built venv")
    library = Path(api._lib._name).resolve()
    library_root = Path(llama_cpp.__file__).resolve().parent / "lib"
    require(library.is_relative_to(library_root), "An arbitrary system libllama was loaded")
    api.llama_backend_init()
    try:
        text = api.llama_print_system_info().decode("utf-8")
        model = api.llama_model_default_params()
        context = api.llama_context_default_params()
        require(text and "CPU" in text, "No real CPU backend system information")
        require(context.n_ctx > 0 and context.n_batch > 0 and context.n_threads > 0,
                "Invalid real default context parameters")
        require(api.llama_supports_gpu_offload() is False and api.llama_supports_rpc() is False,
                "Unexpected accelerator or remote backend in portable CPU result")
        result = {
            "backend_initialized": True, "system_info": text,
            "default_context": {"n_ctx": context.n_ctx, "n_batch": context.n_batch,
                                "n_threads": context.n_threads},
            "default_model_use_mmap": bool(model.use_mmap),
            "supports_mmap": api.llama_supports_mmap(), "supports_mlock": api.llama_supports_mlock(),
            "supports_gpu_offload": False, "supports_rpc": False,
            "library": elf(library, dynamic=True), "model_loaded": False, "inference_tested": False,
        }
    finally:
        api.llama_backend_free()
    result["backend_freed"] = True
    for row in mapped_libraries():
        if any(name in Path(row["path"]).name for name in ("libllama", "libggml", "libmtmd")):
            require(Path(row["path"]).is_relative_to(library_root),
                    "Mixed arbitrary system llama/ggml library")
    return result


def run_case(name, lock, inputs, out):
    result = {"schema_version": 1, "component": name, "status": "failed",
              "model_downloaded": False, "inference_tested": False}
    try:
        result["runtime"] = native_runtime()
        if name == "installed_inputs":
            result["behavior"] = installed_inputs_case(lock, inputs, out)
        elif name == "numba":
            result["behavior"] = numba_case()
        elif name == "llama":
            result["behavior"] = llama_case()
        else:
            raise ProbeError("Unknown native case")
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        try:
            result["mapped_libraries"] = mapped_libraries()
        except Exception as exc:
            result["status"] = "failed"
            result["library_evidence_error"] = {"type": type(exc).__name__, "message": str(exc)}
        save_json(out / ("native-" + name + ".json"), result)
    return 0 if result["status"] == "passed" else 1


def execute_case(name, python, lock, inputs, out, env):
    path = out / ("native-" + name + ".json")
    require(not path.exists(), "Refusing stale native child evidence")
    command = [str(python), "-I", "-B", str(Path(__file__).resolve()),
               "--case", name, "--inputs", str(inputs), "--out", str(out)]
    try:
        child = subprocess.run(command, capture_output=True, timeout=180, env=env, check=False)
        code, stdout, stderr, timed_out = child.returncode, child.stdout, child.stderr, False
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr, timed_out = 124, exc.stdout or b"", exc.stderr or b"", True
    row = {"component": name, "status": "failed", "exit_code": code, "timed_out": timed_out}
    for channel, payload in (("stdout", stdout), ("stderr", stderr)):
        saved = payload[-MAX_LOG_BYTES:]
        log = out / ("native-" + name + "." + channel + ".log")
        log.write_bytes(saved)
        row[channel] = {"bytes": len(payload), "saved_bytes": len(saved), "sha256": sha_bytes(saved)}
    if code < 0:
        row["termination_signal"] = -code
    if path.is_file():
        row["receipt_sha256"] = sha_file(path)
        result = read_json(path)
        if result.get("component") == name and result.get("schema_version") == 1 \
                and result.get("status") == "passed" and code == 0 and not timed_out \
                and isinstance(result.get("behavior"), dict):
            if name == "installed_inputs" or result.get("mapped_libraries"):
                row["status"] = "passed"
        if "error" in result:
            row["error"] = result["error"]
    return row


def set_resource_bounds(lock):
    import resource

    limit = lock["build"]["address_space_limit_bytes"]
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    effective = min(limit, hard) if hard != resource.RLIM_INFINITY else limit
    resource.setrlimit(resource.RLIMIT_AS, (effective, effective))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    affinity = sorted(os.sched_getaffinity(0))
    require(affinity, "No available CPU")
    os.sched_setaffinity(0, set(affinity[:2]))
    return {"address_space_bytes": effective, "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "compiler_jobs": 2, "jit_threads": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args(argv)
    verifier = support()
    if args.case:
        lock, _ = verifier.load_lock(args.inputs / "neutts-native-sources-lock.json")
        return run_case(args.case, lock, args.inputs, args.out)
    require(args.apt_archives is not None and args.foundation_receipt is not None,
            "The exact retained archives and full native foundation receipt are required")
    require(not args.out.is_symlink()
            and (not args.out.exists() or not any(args.out.iterdir())), "Output must be fresh")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1, "status": "failed", "stage": "preflight",
        "scope": "Numba workqueue CPU JIT and matching vendored llama CPU library initialization",
        "models_downloaded": False, "synthesis_tested": False, "engine_installed": False,
        "pm_admission_changed": False, "published_candidate_modified": False, "cases": [],
        "workflow": {k: os.environ.get(k) for k in
                     ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA")},
    }
    try:
        report["runtime"] = native_runtime()
        require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the exact APT base Python")
        lock, report["prepared_inputs"] = validate_inputs(args.inputs, verifier)
        report["foundation"] = validate_foundation(args.foundation_receipt, lock)
        report["resource_bounds"] = set_resource_bounds(lock)
        work = Path(tempfile.mkdtemp(prefix="neutts-native-build-", dir=os.environ["TMPDIR"]))
        report["stage"] = "compiler-install"
        save_json(args.out / "NEUTTS-NATIVE-COMPONENTS.json", report)
        report["build_apt"] = install_toolchain(lock, args.apt_archives, args.out, work)
        report["stage"] = "native-build"
        save_json(args.out / "NEUTTS-NATIVE-COMPONENTS.json", report)
        venv, built, env = build_packages(lock, args.inputs, args.out, work)
        report["built_wheels"] = [{k: p[k] for k in ("name", "version", "filename", "bytes", "sha256", "tag")}
                                  for p in built]
        report["stage"] = "native-behavior"
        for name in CASES:
            report["cases"].append(execute_case(name, venv / "bin/python", lock, args.inputs, args.out, env))
            save_json(args.out / "NEUTTS-NATIVE-COMPONENTS.json", report)
        require(all(row["status"] == "passed" for row in report["cases"]),
                "A native source/component case failed")
        report["stage"], report["status"] = "complete", "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        save_json(args.out / "NEUTTS-NATIVE-COMPONENTS.json", report)
        verifier.publish_modes(args.out)
    print(json.dumps({"status": report["status"], "stage": report["stage"], "cases": report["cases"]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
