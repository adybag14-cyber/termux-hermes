#!/usr/bin/env python3
"""Native build-only NeuTTS wheel and wheel-bundled eSpeak proof; no engine admission."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import traceback
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX = Path("/data/data/com.termux/files/usr")


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    prep = module_at("_engine_wheel_preparation", SCRIPT_DIR / "prepare_neutts_engine_wheel.py")
    lock, _ = prep.load_lock()
    checks = module_at("_engine_wheel_checks", SCRIPT_DIR / "verify_neutts_engine_wheel.py")
    engine, espeak_source, native, espeak_api, apt = prep.helpers(lock)
    return prep, lock, checks, engine, espeak_source, native, espeak_api, apt


def save(path, value):
    path.write_bytes((json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def clean_environment(lock):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("SKBUILD_", "CMAKE_")) or key in {
            "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM", "LD_PRELOAD",
            "ESPEAK_DATA_PATH", "CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
        }:
            env.pop(key, None)
    env.update({
        "CC": str(PREFIX / "bin/clang"), "CXX": str(PREFIX / "bin/clang++"),
        "CFLAGS": lock["build"]["cflags"], "CXXFLAGS": lock["build"]["cflags"],
        "LDFLAGS": lock["build"]["ldflags"], "CMAKE_BUILD_PARALLEL_LEVEL": "2",
        "CMAKE_GENERATOR": "Ninja", "MAKEFLAGS": "-j2",
        "SOURCE_DATE_EPOCH": str(lock["engine_source"]["source_date_epoch"]),
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def pip_command(python):
    return [str(PREFIX / "bin/python"), "-I", "-B", "-m", "pip", "--python", str(python)]


def source_identity(path, lock, checks):
    checks.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 100000,
                   "Missing, nonregular or oversized source receipt")
    raw = path.read_bytes()
    receipt = json.loads(raw)
    image_path = path.parent / "NATIVE-IMAGE-IDENTITY.json"
    checks.require(image_path.is_file() and not image_path.is_symlink()
                   and image_path.stat().st_size <= 10000,
                   "Missing, nonregular or oversized actual image receipt")
    image_raw = image_path.read_bytes()
    image = json.loads(image_raw)
    checks.require(set(image) == {"Id", "RepoDigests", "Architecture", "Os"}
                   and image["Architecture"] == "arm64" and image["Os"] == "linux"
                   and re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"] or "")
                   and isinstance(image["RepoDigests"], list)
                   and lock["native_image"] in image["RepoDigests"],
                   "The pulled image architecture, OS or immutable digest differs")
    required = {
        "scripts/compatibility_probe_neutts_engine_wheel.py",
        "scripts/compatibility_probe_neutts_engine_wheel.sh",
        "scripts/prepare_neutts_engine_wheel.py", "scripts/neutts_engine_wheel_lock.json",
        "scripts/verify_neutts_engine_wheel.py", "scripts/check_neutts_engine_wheel_cmake.py",
        "patches/next-stable/neutts-propagate-espeak-toolchain.patch",
        ".github/workflows/neutts-engine-wheel.yml",
    } | set(lock["helpers"])
    checks.require(receipt.get("schema_version") == 1 and receipt.get("native_image") == lock["native_image"]
                   and re.fullmatch(r"[0-9a-f]{40}", receipt.get("head_sha", "")),
                   "The native image/source receipt differs")
    hashes = receipt.get("inputs", {})
    checks.require(required <= set(hashes), "Native source receipt omitted a required gate/helper")
    for name, expected in hashes.items():
        relative = PurePosixPath(name)
        checks.require(relative.as_posix() == name and not relative.is_absolute()
                       and ".." not in relative.parts and "\\" not in name,
                       "Unsafe source ledger member")
        target = SCRIPT_DIR.parent.joinpath(*relative.parts)
        checks.require(target.is_file() and not target.is_symlink() and file_sha(target) == expected,
                       "Executed gate source differs from host source ledger: " + name)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "head_sha": receipt["head_sha"], "native_image": receipt["native_image"],
            "run_id": receipt.get("run_id"), "verified_source_files": len(hashes),
            "actual_image_receipt": {"path": str(image_path),
                                     "sha256": hashlib.sha256(image_raw).hexdigest(),
                                     "identity": image}}


def runtime_provenance(apt, lock, compiler_archives, pip_archive, work, checks):
    manifest = apt.load_manifest(SCRIPT_DIR / "neutts_apt_python_metadata.json")
    runtime = apt.native_runtime(manifest["runtime"])
    pin = next(p for p in manifest["runtime"]["archives"] if p["package"] == "python-pip")
    checks.require(pip_archive.is_file() and not pip_archive.is_symlink()
                   and pip_archive.stat().st_size == pin["bytes"] and file_sha(pip_archive) == pin["sha256"],
                   "Exact already-installed pip provenance archive differs")
    directory = work / "python-provenance-archives"
    directory.mkdir()
    for package in manifest["runtime"]["archives"]:
        if package["package"] == "python-pip":
            origin = pip_archive
        else:
            found = list(compiler_archives.glob(package["package"] + "_*.deb"))
            checks.require(len(found) == 1, "Missing or ambiguous exact APT Python archive")
            origin = found[0]
        target = directory / package["filename"]
        shutil.copyfile(origin, target)
        checks.require(file_sha(target) == package["sha256"] and target.stat().st_size == package["bytes"],
                       "Retained runtime archive copy changed")
    # This is an explicit two-archive interpreter/pip scope. The unchanged
    # seven-case foundation and 44-archive compiler gate remain separate.
    selected = {"runtime": manifest["runtime"], "apt_distributions": []}
    result = apt.apt_provenance(selected, directory)
    result.update(scope="Exact APT Python and all pip Python source; no scientific-distribution admission here",
                  native_runtime=runtime, full_foundation_unchanged=True,
                  compiler_archives_verified_separately=44, archive_count=2,
                  additional_archive_download_only=True, pip_reinstalled=False)
    return result


def build_settings(lock, espeak_source, build_dir):
    flags = lock["build"]["cflags"]
    linker = lock["build"]["ldflags"]
    return {
        "build-dir": str(build_dir), "build.tool-args": ["-j2"],
        "cmake.build-type": lock["build"]["parent_cmake_build_type"],
        "cmake.define.NEUTTS_ESPEAK_SOURCE_DIR": str(espeak_source),
        "cmake.define.CMAKE_C_COMPILER": str(PREFIX / "bin/clang"),
        "cmake.define.CMAKE_CXX_COMPILER": str(PREFIX / "bin/clang++"),
        "cmake.define.CMAKE_MAKE_PROGRAM": str(PREFIX / "bin/ninja"),
        "cmake.define.CMAKE_C_FLAGS": flags, "cmake.define.CMAKE_CXX_FLAGS": flags,
        "cmake.define.CMAKE_EXE_LINKER_FLAGS": linker,
        "cmake.define.CMAKE_SHARED_LINKER_FLAGS": linker,
        "cmake.define.CMAKE_MODULE_LINKER_FLAGS": linker,
        "cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
    }


def installed_build_inventory(inputs, venv, prep, lock, checks):
    from packaging.markers import default_environment
    from packaging.utils import canonicalize_name

    venv = venv.resolve()
    checks.require(Path(sys.prefix).resolve() == venv and Path(sys.base_prefix).resolve() == PREFIX
                   and venv != PREFIX, "Expected the separate three-distribution build venv")
    site = venv / "lib/python3.14/site-packages"
    distributions = list(importlib.metadata.distributions())
    expected = {p["name"]: p["version"] for p in lock["build"]["python_wheels"]}
    actual = {}
    for distribution in distributions:
        name = canonicalize_name(distribution.metadata["Name"])
        checks.require(name not in actual and name in expected
                       and distribution.version == expected[name]
                       and Path(distribution.locate_file("")).resolve() == site,
                       "Unexpected distribution or APT site visibility in the build venv")
        actual[name] = distribution.version
    checks.require(actual == expected and len(distributions) == 3,
                   "The actual visible build environment is not exactly three distributions")
    rows, allowed_site_files = [], set()
    declared = []
    for package in lock["build"]["python_wheels"]:
        distribution = importlib.metadata.distribution(package["name"])
        checks.require((distribution.requires or []) == package["declared_requires_dist"],
                       "Installed backend dependency metadata differs")
        wheel = inputs / "wheels" / package["artifact"]["filename"]
        prep.support().core_verifier().verify_wheel(wheel, package)
        checked = []
        with zipfile.ZipFile(wheel) as archive:
            original_names = []
            for item in archive.infolist():
                if item.is_dir():
                    continue
                prep.support().core_verifier().safe_member(item)
                checks.require(".data/" not in item.filename, "Unexpected build-wheel installation scheme")
                original_names.append(item.filename)
                target = site.joinpath(*PurePosixPath(item.filename).parts)
                allowed_site_files.add(item.filename)
                checks.require(target.is_file() and not target.is_symlink(), "Missing installed backend source member")
                if item.filename == package["wheel"]["record_member"]:
                    continue
                raw = target.read_bytes()
                checks.require(raw == archive.read(item), "Installed backend source or metadata bytes changed")
                checked.append({"path": item.filename, "bytes": len(raw), "sha256": checks.digest(raw)})
        info = package["wheel"]["record_member"].rsplit("/", 1)[0]
        for suffix, raw in (("INSTALLER", b"pip\n"), ("REQUESTED", b"")):
            name = info + "/" + suffix
            target = site / name
            checks.require(target.is_file() and not target.is_symlink() and target.read_bytes() == raw,
                           "Unexpected pip installation metadata")
            allowed_site_files.add(name)
        record = site / package["wheel"]["record_member"]
        records = list(csv.reader(io.StringIO(record.read_text("utf-8"))))
        checks.require(all(len(r) == 3 for r in records)
                       and len({r[0] for r in records}) == len(records), "Invalid installed build RECORD")
        observed = []
        for name, encoded, size in records:
            relative = PurePosixPath(name)
            checks.require(name == relative.as_posix() and not relative.is_absolute() and "\\" not in name,
                           "Invalid installed build RECORD path")
            target = site.joinpath(*relative.parts).resolve(strict=True)
            checks.require(target.is_relative_to(venv) and target.is_file()
                           and not target.is_symlink(), "Installed build RECORD escapes its venv")
            raw = target.read_bytes()
            if name == package["wheel"]["record_member"]:
                checks.require(encoded == size == "", "Unexpected installed RECORD self-entry")
            else:
                checks.require(encoded == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
                               and size == str(len(raw)), "Installed build RECORD hash differs")
            observed.append({"path": name, "bytes": len(raw), "sha256": checks.digest(raw)})
        checks.require(set(original_names) <= {r[0] for r in records}, "Installed RECORD omits original wheel members")
        rows.append({"name": package["name"], "version": package["version"],
                     "wheel_sha256": package["artifact"]["sha256"], "original_byte_identical_members": checked,
                     "documented_rewrite": "pip rewrites only the original RECORD; generated installer metadata and entry points are recorded",
                     "installed_record_sha256": file_sha(record), "installed_record_members": observed})
        declared.append({**package, "declared_requires_dist": distribution.requires or []})
    found = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file() or p.is_symlink()}
    checks.require(found == allowed_site_files, "Unexpected source/cache file in the isolated backend site")
    environment = default_environment()
    environment["extra"] = ""
    checks.require(environment["sys_platform"] == "android"
                   and environment["python_full_version"] == "3.14.6",
                   "Actual backend marker environment differs")
    edges = prep.build_graph(declared, environment)
    checks.require(len(edges) == 2, "Actual complete build graph changed")
    return {"status": "passed", "visible_distribution_count": 3, "visible_distributions": actual,
            "original_wheel_members": rows, "active_edges": edges, "marker_environment": environment,
            "system_site_packages_visible": False, "engine_installed": False}


def backend_build(args):
    prep, lock, checks, _, _, native, _, _ = helpers()
    report = {"schema_version": 1, "status": "failed", "engine_installed": False,
              "engine_imported": False, "python314_admission": False, "model_downloaded": False}
    try:
        report["runtime"] = native.native_runtime()
        checks.require(args.source.resolve() != (args.inputs / "source").resolve(),
                       "Build needs its own source copy")
        report["project"] = prep.verify_project(args.source / "pyproject.toml", lock)
        report["before"] = installed_build_inventory(args.inputs, args.venv, prep, lock, checks)
        settings = build_settings(lock, args.espeak_source, args.build_dir)
        report["settings"] = settings
        save(args.out / "BACKEND-BUILD-STATE.json", report)
        os.chdir(args.source)
        from scikit_build_core import __version__ as backend_version
        from scikit_build_core import build as backend
        checks.require(backend_version == "1.1.1", "Unreviewed backend version")
        site = args.venv / "lib/python3.14/site-packages"
        checks.require(Path(backend.__file__).resolve().is_relative_to(site.resolve()),
                       "The backend resolved outside its verified venv")
        additional = backend.get_requires_for_build_wheel(settings)
        report["dynamic_build_requires"] = additional
        checks.require(additional == lock["build"]["expected_dynamic_build_requires"],
                       "Backend requested an unprepared additional build dependency")
        wheel_dir = args.out / "wheels"
        wheel_dir.mkdir()
        filename = backend.build_wheel(str(wheel_dir), settings)
        checks.require(PurePosixPath(filename).name == filename and filename.endswith(".whl")
                       and {p.name for p in wheel_dir.iterdir()} == {filename},
                       "Backend emitted an unexpected output")
        report["wheel"] = {"filename": filename, "bytes": (wheel_dir / filename).stat().st_size,
                           "sha256": file_sha(wheel_dir / filename)}
        report["after"] = installed_build_inventory(args.inputs, args.venv, prep, lock, checks)
        checks.require(report["before"] == report["after"], "Backend mutated its installed build environment")
        report["status"] = "passed-build-only"
    except (Exception, SystemExit) as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        traceback.print_exc()
    finally:
        save(args.out / "BACKEND-BUILD-STATE.json", report)
    return 0 if report["status"] == "passed-build-only" else 1


def capture_cmake(build, out):
    """Keep raw first-failure diagnostics as well as successful configuration evidence."""
    if not build.exists():
        return {"files": [], "build_directory_created": False}
    target = out / "cmake-evidence"
    target.mkdir(exist_ok=True)
    rows = []
    selected = []
    for root in (build, build / "espeak_ng/src/espeak_ng_external-build"):
        for name in ("CMakeCache.txt", "compile_commands.json", "build.ninja", "install_manifest.txt"):
            if (root / name).is_file():
                selected.append(root / name)
        selected.extend((root / "CMakeFiles").glob("*/CMakeSystem.cmake"))
        selected.extend((root / "CMakeFiles").glob("*/CMakeCCompiler.cmake"))
        selected.extend((root / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    selected.extend((build / "espeak_ng").rglob("*-cfgcmd.txt"))
    for path in sorted(set(selected)):
        name = path.relative_to(build)
        raw = path.read_bytes()
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        rows.append({"path": name.as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    result = {"files": rows, "build_directory_created": True}
    save(out / "RAW-CMAKE-CAPTURE.json", result)
    return result


def wheel_cabi(args, lock, checks, native, espeak, helper, wheel_result, work):
    out = args.out / "wheel-espeak-cases"
    out.mkdir()
    package = args.out / "inspected-wheel/neutts"
    library = package / "libespeak-ng.so.1.52.0.1"
    data = package / "espeak-ng-data"
    expected = wheel_result["native_members"]["neutts/libespeak-ng.so.1.52.0.1"]
    cases, ipa = [], []
    def run(label, case, fixture, lib=library, tree=data, expected_exit=0):
        row, child = espeak.execute_case(args, native, helper, out, label, case, fixture, lib, tree, expected_exit)
        if child is not None:
            checks.require(child["library"]["sha256"] == expected["sha256"]
                           and child["library"]["bytes"] == expected["bytes"],
                           "The C ABI process did not load the exact wheel library bytes")
            row.update(wheel_library_sha256=expected["sha256"], wheel_sha256=wheel_result["sha256"])
        cases.append(row)
        return child
    for index in range(lock["espeak"]["fixture_count"]):
        run("wheel-ascii-" + str(index), "ascii", index)
    for index in range(2):
        child = run("wheel-ipa-" + str(index), "ipa", 0)
        ipa.append(child["phonemes"])
    checks.require(ipa[0] == ipa[1], "Wheel-bundled IPA changed between fresh processes")
    relocated = work / "relocated-wheel-neutts"
    shutil.copytree(package, relocated)
    for index in range(lock["espeak"]["fixture_count"]):
        run("wheel-relocated-" + str(index), "ascii", index,
            relocated / library.name, relocated / "espeak-ng-data")
    run("wheel-invalid-voice", "invalid-voice", 0)
    empty = work / "empty-espeak-data"
    empty.mkdir()
    run("wheel-missing-data", "missing-data", 0, library, empty, 1)
    result = {"status": "passed", "wheel_sha256": wheel_result["sha256"], "cases": cases,
              "library": native.elf(library, dynamic=True), "data_directory": str(data),
              "real_python_wrapper_proved": False, "engine_imported": False,
              "audio_synthesis_called": False, "model_inference_called": False}
    forbidden = re.compile(r"(sonic|pcaudio|asound|pulse|musl|\.so\.6$|libpthread\.so\.0)")
    checks.require(not any(forbidden.search(n) for n in result["library"]["needed"]),
                   "Wheel library gained an unreviewed audio or non-Bionic dependency")
    save(args.out / "WHEEL-ESPEAK-CABI-RESULT.json", result)
    return result


def run(args):
    prep, lock, checks, _, espeak_source, native, espeak, apt = helpers()
    checks.require(not args.out.exists() and not args.out.is_symlink(), "Fresh native wheel evidence directory required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "stage": "preflight",
              "scope": "Native exact-source NeuTTS wheel build plus wheel-bundled eSpeak C ABI/data only",
              "engine_source_commit": lock["engine_source"]["commit"], "source_lock_sha256": prep.LOCK_SHA256,
              "scope_limits": lock["limits"], "engine_installed": False, "engine_imported": False,
              "model_downloaded": False, "python314_admission": False, "release_output": False}
    work = None
    try:
        report["runtime"] = native.native_runtime()
        checks.require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the exact APT base Python")
        report["source_identity"] = source_identity(args.source_receipt, lock, checks)
        report["inputs"] = prep.verify_inputs(args.inputs)
        helper = prep.support()
        _, native_lock = espeak_source.verify_inputs(args.inputs / "espeak-source")
        report["foundation"] = native.validate_foundation(args.foundation_receipt, native_lock)
        report["resource_bounds"] = native.set_resource_bounds({"build": lock["build"]})
        work = Path(tempfile.mkdtemp(prefix="neutts-engine-wheel-", dir=PREFIX / "tmp"))
        source, build, espeak_tree = work / "source", work / "cmake-build", work / "espeak-source"
        report["stage"] = "compiler-provenance"
        report["compiler"] = native.install_toolchain(native_lock, args.apt_archives, args.out, work)
        report["python_pip_provenance"] = runtime_provenance(apt, lock, args.apt_archives,
                                                           args.pip_archive, work, checks)
        apt.check_apt_dependencies(report)
        report["stage"] = "isolated-build-environment"
        shutil.copytree(args.inputs / "source", source)
        source_rows = json.loads((args.inputs / "wheel-source-manifest.json").read_bytes())
        helper.verify_source_tree(source, source_rows, lock["engine_source"]["wheel_source_manifest"])
        espeak_source.verify_inputs(args.inputs / "espeak-source", espeak_tree)
        env = clean_environment(lock)
        venv = work / "venv"
        python = venv / "bin/python"
        report["create_venv"] = native.bounded_command(
            [str(PREFIX / "bin/python"), "-I", "-B", "-m", "venv", "--without-pip", str(venv)],
            args.out, "engine-create-build-venv", 60, env)
        report["install_backend"] = native.bounded_command(
            pip_command(python) + ["install", "--no-index", "--no-deps", "--only-binary=:all:",
                                   "--require-hashes", "--no-compile", "--find-links",
                                   str(args.inputs / "wheels"), "-r", str(args.inputs / "requirements.txt")],
            args.out, "engine-install-build-wheels", 90, env)
        report["stage"] = "native-backend-build"
        report["build_command"] = native.bounded_command(
            [str(python), "-I", "-B", str(Path(__file__).resolve()), "--backend",
             "--inputs", str(args.inputs), "--out", str(args.out), "--venv", str(venv),
             "--source", str(source), "--espeak-source", str(espeak_tree), "--build-dir", str(build)],
            args.out, "engine-native-wheel-build", lock["build"]["build_timeout_seconds"], env)
        backend = json.loads((args.out / "BACKEND-BUILD-STATE.json").read_bytes())
        checks.require(backend.get("status") == "passed-build-only", "Native backend did not finish")
        report["backend_state_sha256"] = file_sha(args.out / "BACKEND-BUILD-STATE.json")
        report["isolated_build_inventory"] = backend["after"]
        report["pip_check"] = native.bounded_command(
            pip_command(python) + ["check"], args.out, "engine-build-venv-pip-check", 30, env)
        report["stage"] = "actual-nested-toolchain"
        report["raw_cmake"] = capture_cmake(build, args.out)
        nested = build / "espeak_ng/src/espeak_ng_external-build"
        parent_system = list((build / "CMakeFiles").glob("*/CMakeSystem.cmake"))
        nested_system = list((nested / "CMakeFiles").glob("*/CMakeSystem.cmake"))
        checks.require(len(parent_system) == len(nested_system) == 1,
                       "Missing or ambiguous actual CMake system records")
        report["nested_toolchain"] = checks.verify_cmake(
            (build / "CMakeCache.txt").read_bytes(), (nested / "CMakeCache.txt").read_bytes(),
            parent_system[0].read_bytes(), nested_system[0].read_bytes(),
            json.loads((nested / "compile_commands.json").read_bytes()), lock, source, espeak_tree, nested)
        checks.require(not list(build.rglob("*-gitclone.cmake"))
                       and not list(build.rglob("_deps")), "Unreviewed source/dependency acquisition route appeared")
        report["all_original_source_files"] = checks.verify_original_source_files(source, source_rows)
        espeak_rows = json.loads((args.inputs / "espeak-source/patched-source-manifest.json").read_bytes())
        report["all_original_espeak_files"] = checks.verify_original_source_files(espeak_tree, espeak_rows)
        install = build / "espeak_ng-install"
        report["stage"] = "wheel-content-and-data"
        data_manifest = checks.verify_data_tree(install / "share/espeak-ng-data", espeak_tree)
        save(args.out / "WHEEL-ESPEAK-DATA-MANIFEST.json", data_manifest)
        from pip._vendor.packaging.tags import sys_tags
        built_path = args.out / "wheels" / backend["wheel"]["filename"]
        report["wheel"] = checks.verify_built_wheel(
            built_path, lock, source, install, data_manifest, helper.core_verifier().safe_member,
            {str(t) for t in sys_tags()}, args.out / "inspected-wheel")
        checks.require(report["wheel"]["sha256"] == backend["wheel"]["sha256"],
                       "Wheel output changed after the backend result")
        report["stage"] = "wheel-bundled-c-abi"
        report["cabi"] = wheel_cabi(args, lock, checks, native, espeak, helper, report["wheel"], work)
        report["status"], report["stage"] = "passed-build-and-bundled-cabi-only", "complete"
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        traceback.print_exc()
    finally:
        if work is not None:
            try:
                report["raw_cmake"] = capture_cmake(work / "cmake-build", args.out)
            except Exception as error:
                report["diagnostic_capture_error"] = str(error)
            shutil.rmtree(work)
        save(args.out / "NEUTTS-ENGINE-WHEEL-RESULT.json", report)
        prep.support().publish_modes(args.out)
    print(json.dumps({"status": report["status"], "stage": report["stage"],
                      "engine_installed": False, "python314_admission": False}))
    return 0 if report["status"] == "passed-build-and-bundled-cabi-only" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--pip-archive", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--backend", action="store_true")
    parser.add_argument("--venv", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--espeak-source", type=Path)
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    if args.backend:
        if any(value is None for value in (args.venv, args.source, args.espeak_source, args.build_dir)):
            parser.error("Backend mode requires the exact isolated venv and owned source/build directories")
        raise SystemExit(backend_build(args))
    if any(value is None for value in (args.apt_archives, args.pip_archive, args.foundation_receipt, args.source_receipt)):
        parser.error("Native mode requires exact retained archives, foundation and source/image receipts")
    raise SystemExit(run(args))
