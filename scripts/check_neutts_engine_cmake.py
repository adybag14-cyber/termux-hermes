#!/usr/bin/env python3
"""Test the NeuTTS ExternalProject source route with real CMake, without compiling."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def check(inputs, output):
    path = Path(__file__).with_name("prepare_neutts_engine_source.py")
    spec = importlib.util.spec_from_file_location("_neutts_engine_source", path)
    prep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prep)
    helper = prep.support()
    lock, _ = prep.load_lock()
    prep.verify_inputs(inputs)
    cmake, ninja = shutil.which("cmake"), shutil.which("ninja")
    helper.require(cmake is not None and ninja is not None, "CMake and Ninja are required")
    helper.require(not output.exists() and not output.is_symlink(), "Fresh CMake evidence directory required")
    output.mkdir(parents=True)
    artifact = lock["source"]["artifact"]
    archive_path = inputs / artifact["filename"]
    archive_raw = helper.read_regular(archive_path, artifact["bytes"])
    helper.require(len(archive_raw) == artifact["bytes"] and helper.digest(archive_raw) == artifact["sha256"],
                   "Original source archive differs")
    with tarfile.open(archive_path, "r:gz") as archive:
        original = archive.extractfile(lock["source"]["root"] + "/CMakeLists.txt").read()
    patched = (inputs / "source" / "CMakeLists.txt").read_bytes()
    helper.require(helper.digest(original) == lock["patch"]["before_sha256"] and
                   helper.digest(patched) == lock["patch"]["after_sha256"], "CMake source identities differ")
    cases = []
    with tempfile.TemporaryDirectory(prefix="neutts-cmake-source-") as temporary:
        root = Path(temporary)
        local = root / "local-source"
        local.mkdir()
        # Only ExternalProject acquisition steps run. This is a source-directory
        # fixture, not a replacement native eSpeak build.
        (local / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.26)\nproject(route_fixture NONE)\n",
                                           encoding="utf-8", newline="\n")
        variants = [
            ("original-default", original, None, True),
            ("patched-default", patched, None, True),
            ("patched-offline", patched, local.as_posix(), True),
            ("patched-missing-source", patched, (root / "absent").as_posix(), False),
            ("patched-relative-source", patched, "relative-source", False),
        ]
        for label, raw, source_option, success in variants:
            project, build = root / label, root / (label + "-build")
            project.mkdir()
            text = raw.decode("utf-8")
            helper.require(text.count("project(neutts LANGUAGES C CXX)") == 1, "Unexpected upstream project declaration")
            # Suppress only compiler discovery for this configuration-only test.
            # Exact ExternalProject and install declarations remain evaluated.
            text = text.replace("project(neutts LANGUAGES C CXX)", "project(neutts LANGUAGES NONE)", 1)
            text += r'''
ExternalProject_Get_Property(espeak_ng_external SOURCE_DIR)
get_property(_route_repo TARGET espeak_ng_external PROPERTY _EP_GIT_REPOSITORY)
get_property(_route_tag TARGET espeak_ng_external PROPERTY _EP_GIT_TAG)
get_property(_route_args TARGET espeak_ng_external PROPERTY _EP_CMAKE_ARGS)
file(WRITE "${CMAKE_BINARY_DIR}/source-route.txt" "${SOURCE_DIR}\n${_route_repo}\n${_route_tag}\n${_route_args}\n")
ExternalProject_Add_StepTargets(espeak_ng_external download update)
'''
            (project / "CMakeLists.txt").write_text(text, encoding="utf-8", newline="\n")
            command = [cmake, "-S", str(project), "-B", str(build), "-G", "Ninja",
                       "-DCMAKE_MAKE_PROGRAM=" + Path(ninja).as_posix()]
            if source_option is not None:
                command += ["-DNEUTTS_ESPEAK_SOURCE_DIR=" + source_option]
            p = subprocess.run(command, capture_output=True, timeout=30, check=False)
            (output / (label + ".stdout.log")).write_bytes(p.stdout)
            (output / (label + ".stderr.log")).write_bytes(p.stderr)
            passed = (p.returncode == 0) == success
            detail = {}
            if success and p.returncode == 0:
                route = (build / "source-route.txt").read_text("utf-8").splitlines()
                source_dir, repository, revision, cmake_args = route
                (output / (label + ".source-route.txt")).write_bytes((build / "source-route.txt").read_bytes())
                helper.require("-DUSE_LIBSONIC:BOOL=OFF" in cmake_args and
                               "-DEXTRA_cmn:BOOL=ON" in cmake_args and
                               "-DEXTRA_ru:BOOL=ON" in cmake_args, "Original synthesis/language flags changed")
                include = source_dir + "/src/ucd-tools/src/include"
                helper.require(cmake_args.count("-I" + include) == 2, "Nested C/C++ include directory is wrong")
                scripts = list(build.rglob("*-gitclone.cmake"))
                detail = {"source_directory": source_dir, "repository": repository, "revision": revision,
                          "git_clone_scripts": len(scripts), "nested_cmake_args": cmake_args}
                if label == "patched-offline":
                    passed = passed and source_dir == local.as_posix() and not repository and not revision and not scripts
                    command2 = [cmake, "--build", str(build), "--target",
                                "espeak_ng_external-download", "espeak_ng_external-update"]
                    p2 = subprocess.run(command2, capture_output=True, timeout=30, check=False)
                    (output / (label + ".acquisition.stdout.log")).write_bytes(p2.stdout)
                    (output / (label + ".acquisition.stderr.log")).write_bytes(p2.stderr)
                    passed = passed and p2.returncode == 0
                    detail.update(acquisition_exit_code=p2.returncode, native_compilation_performed=False)
                else:
                    passed = passed and repository == "https://github.com/espeak-ng/espeak-ng.git"
                    passed = passed and revision == lock["espeak_source_lock"]["commit"] and len(scripts) == 1
            elif not success:
                passed = passed and b"NEUTTS_ESPEAK_SOURCE_DIR must be an existing absolute source directory" in p.stderr
            cases.append({"case": label, "status": "passed" if passed else "failed",
                          "expected_configure_success": success, "exit_code": p.returncode,
                          "source_sha256": hashlib.sha256(raw).hexdigest(), "command": command, **detail})
    receipt = {"schema_version": 1, "status": "passed" if all(c["status"] == "passed" for c in cases) else "failed",
               "cases": cases, "source_commit": lock["source"]["commit"],
               "patch_sha256": lock["patch"]["sha256"],
               "scope": "Real CMake ExternalProject acquisition/configuration regression with compiler discovery suppressed",
               "native_compilation_performed": False, "native_engine_compatibility_claimed": False,
               "model_downloaded": False}
    (output / "NEUTTS-CMAKE-SOURCE-REGRESSION.json").write_bytes(helper.canonical(receipt))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.inputs, args.out)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
