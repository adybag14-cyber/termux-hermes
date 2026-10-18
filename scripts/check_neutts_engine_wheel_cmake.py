#!/usr/bin/env python3
"""Use real CMake to compare the nested toolchain route; suppress compiler discovery only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(inputs, output):
    scripts = Path(__file__).resolve().parent
    prep = module_at("_engine_wheel_cmake_preparer", scripts / "prepare_neutts_engine_wheel.py")
    lock, _ = prep.load_lock()
    prep.verify_inputs(inputs)
    helper = prep.support()
    cmake, ninja = shutil.which("cmake"), shutil.which("ninja")
    helper.require(cmake is not None and ninja is not None, "Real CMake and Ninja are required")
    helper.require(not output.exists() and not output.is_symlink(), "Fresh configuration evidence directory required")
    output.mkdir(parents=True)
    checks = module_at("_engine_wheel_cmake_checks", scripts / "verify_neutts_engine_wheel.py")
    baseline = (inputs / "engine-source/source/CMakeLists.txt").read_bytes()
    patched = (inputs / "source/CMakeLists.txt").read_bytes()
    change = lock["patch"]["changes"][0]
    helper.require(hashlib.sha256(baseline).hexdigest() == change["before_sha256"]
                   and hashlib.sha256(patched).hexdigest() == change["after_sha256"],
                   "Actual source CMake identities changed")
    cases = []
    with tempfile.TemporaryDirectory(prefix="engine-wheel-cmake-") as temporary:
        work = Path(temporary)
        local = work / "exact-local-route-fixture"
        local.mkdir()
        (local / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.26)\nproject(acquisition_fixture LANGUAGES NONE)\n",
            encoding="utf-8", newline="\n")
        compiler = (work / "not-executed-toolchain" / "clang").as_posix()
        compilerxx = (work / "not-executed-toolchain" / "clang++").as_posix()
        variants = [
            ("baseline-loses-parent-target", baseline, True, lock["build"]["cflags"], lock["build"]["cflags"],
             lock["build"]["ldflags"], "ON"),
            ("patched-portable-target", patched, True, lock["build"]["cflags"], lock["build"]["cflags"],
             lock["build"]["ldflags"], "ON"),
            ("patched-distinct-parent-settings", patched, True, "-O1 -DKEEP_C=1", "-O0 -DKEEP_CXX=2",
             "-Wl,--as-needed", "ON"),
            ("patched-empty-parent-flags", patched, True, "", "", "", "OFF"),
            ("patched-original-git-default", patched, False, lock["build"]["cflags"], lock["build"]["cflags"],
             lock["build"]["ldflags"], "ON"),
        ]
        for label, raw, offline, cflags, cxxflags, linker, export in variants:
            project, build = work / label, work / (label + "-build")
            project.mkdir()
            text = raw.decode("utf-8")
            helper.require(text.count("project(neutts LANGUAGES C CXX)") == 1, "Unexpected actual NeuTTS project declaration")
            text = text.replace("project(neutts LANGUAGES C CXX)", "project(neutts LANGUAGES NONE)", 1)
            text += r'''
get_property(_route_repo TARGET espeak_ng_external PROPERTY _EP_GIT_REPOSITORY)
get_property(_route_tag TARGET espeak_ng_external PROPERTY _EP_GIT_TAG)
get_property(_route_args TARGET espeak_ng_external PROPERTY _EP_CMAKE_ARGS)
file(WRITE "@{CMAKE_BINARY_DIR}/nested-route.txt" "@{_route_repo}\n@{_route_tag}\n@{_route_args}\n")
ExternalProject_Add_StepTargets(espeak_ng_external configure)
'''.replace("@{", chr(36) + "{")
            (project / "CMakeLists.txt").write_text(text, encoding="utf-8", newline="\n")
            command = [cmake, "-S", str(project), "-B", str(build), "-G", "Ninja",
                       "-DCMAKE_MAKE_PROGRAM=" + Path(ninja).as_posix(),
                       "-DCMAKE_C_COMPILER=" + compiler, "-DCMAKE_CXX_COMPILER=" + compilerxx,
                       "-DCMAKE_C_FLAGS=" + cflags, "-DCMAKE_CXX_FLAGS=" + cxxflags,
                       "-DCMAKE_EXE_LINKER_FLAGS=" + linker, "-DCMAKE_SHARED_LINKER_FLAGS=" + linker,
                       "-DCMAKE_MODULE_LINKER_FLAGS=" + linker, "-DCMAKE_EXPORT_COMPILE_COMMANDS=" + export]
            if offline:
                command += ["-DNEUTTS_ESPEAK_SOURCE_DIR=" + local.as_posix()]
            child = subprocess.run(command, capture_output=True, timeout=30, check=False)
            (output / (label + ".stdout.log")).write_bytes(child.stdout)
            (output / (label + ".stderr.log")).write_bytes(child.stderr)
            helper.require(child.returncode == 0, "Real parent CMake configuration failed: " + label)
            route = (build / "nested-route.txt").read_text("utf-8").splitlines()
            helper.require(len(route) == 3, "Unexpected ExternalProject route record")
            (output / (label + ".nested-route.txt")).write_bytes((build / "nested-route.txt").read_bytes())
            repo, revision, args = route
            preserved = [flag for flag in ("-DUSE_LIBSONIC:BOOL=OFF", "-DEXTRA_cmn:BOOL=ON", "-DEXTRA_ru:BOOL=ON")
                         if flag in args]
            helper.require(len(preserved) == 3, "Original feature/language settings changed")
            row = {"case": label, "status": "passed", "source_sha256": hashlib.sha256(raw).hexdigest(),
                   "parent_command": command, "parent_exit_code": child.returncode,
                   "nested_arguments": args, "compiler_discovery_suppressed": True,
                   "compiler_executed": False, "native_abi_claimed": False}
            if offline:
                helper.require(not repo and not revision and not list(build.rglob("*-gitclone.cmake")),
                               "The verified local route still prepared a Git clone")
                nested_command = [cmake, "--build", str(build), "--target", "espeak_ng_external-configure"]
                nested = subprocess.run(nested_command, capture_output=True, timeout=30, check=False)
                (output / (label + ".nested.stdout.log")).write_bytes(nested.stdout)
                (output / (label + ".nested.stderr.log")).write_bytes(nested.stderr)
                helper.require(nested.returncode == 0, "Actual nested fixture CMake failed: " + label)
                cache_path = build / "espeak_ng/src/espeak_ng_external-build/CMakeCache.txt"
                cache_raw = cache_path.read_bytes()
                (output / (label + ".nested-CMakeCache.txt")).write_bytes(cache_raw)
                values = checks.cache_values(cache_raw)
                suffix = "-D_FILE_OFFSET_BITS=64 -I" + (local / "src/ucd-tools/src/include").as_posix()
                if label.startswith("baseline"):
                    helper.require(values.get("CMAKE_C_FLAGS") == suffix
                                   and values.get("CMAKE_CXX_FLAGS") == suffix
                                   and "--target=" not in values["CMAKE_C_FLAGS"],
                                   "The frozen baseline no longer reproduces the lost target")
                    row["baseline_defect_reproduced"] = "Nested C/C++ flags discard all supplied parent flags"
                else:
                    for key, wanted in (("CMAKE_C_COMPILER", compiler), ("CMAKE_CXX_COMPILER", compilerxx),
                                        ("CMAKE_C_FLAGS", cflags + " " + suffix), ("CMAKE_CXX_FLAGS", cxxflags + " " + suffix),
                                        ("CMAKE_EXE_LINKER_FLAGS", linker), ("CMAKE_SHARED_LINKER_FLAGS", linker),
                                        ("CMAKE_MODULE_LINKER_FLAGS", linker), ("CMAKE_EXPORT_COMPILE_COMMANDS", export)):
                        helper.require(values.get(key, "").strip() == wanted.strip(), "Actual nested propagation failed: " + key)
                    row["nested_parent_settings_preserved"] = True
                row.update(nested_command=nested_command, nested_exit_code=nested.returncode,
                           nested_cache_sha256=hashlib.sha256(cache_raw).hexdigest())
            else:
                helper.require(repo == "https://github.com/espeak-ng/espeak-ng.git"
                               and revision == lock["espeak"]["source_commit"]
                               and len(list(build.rglob("*-gitclone.cmake"))) == 1,
                               "The original default source acquisition pin changed")
                row["acquisition_step_executed"] = False
            cases.append(row)
    report = {"schema_version": 1, "status": "passed", "cases": cases,
              "scope": "Real parent and nested CMake configuration; a LANGUAGES NONE acquisition fixture suppresses compiler discovery",
              "source_patch_sha256": lock["patch"]["sha256"],
              "native_compilation_performed": False, "engine_built": False, "python314_admission": False,
              "model_downloaded": False}
    (output / "ENGINE-WHEEL-CMAKE-REGRESSION.json").write_bytes(helper.canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.inputs, args.out)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"])}, indent=2))
