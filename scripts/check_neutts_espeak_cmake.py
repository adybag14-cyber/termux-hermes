#!/usr/bin/env python3
"""Exercise original and guarded eSpeak dependency configuration with downloads disabled."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cmake, ninja = shutil.which("cmake"), shutil.which("ninja")
    if not cmake or not ninja:
        raise SystemExit("CMake and Ninja are required for the real configuration regression")
    path = Path(__file__).with_name("prepare_neutts_espeak_source.py")
    spec = importlib.util.spec_from_file_location("_espeak_preparation", path)
    prep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prep)
    helper = prep.support()
    lock, _ = prep.verify_inputs(args.inputs)
    helper.require(not args.out.exists(), "Fresh configuration evidence directory required")
    args.out.mkdir(parents=True)
    with tarfile.open(args.inputs / lock["source"]["artifact"]["filename"], "r:gz") as archive:
        original = archive.extractfile(lock["source"]["root"] + "/cmake/deps.cmake").read()
    patched = prep.patched_deps(original, lock)
    rows = []
    with tempfile.TemporaryDirectory(prefix="espeak-cmake-guard-") as temporary:
        root = Path(temporary)
        for label, source, option, expected in [
            ("original-explicit-off", original, "OFF", False),
            ("guarded-explicit-off", patched, "OFF", True),
            ("guarded-explicit-on", patched, "ON", False),
            ("guarded-default", patched, None, False),
        ]:
            project, build, empty = root / label, root / (label + "-build"), root / (label + "-empty")
            project.mkdir()
            empty.mkdir()
            (project / "deps.cmake").write_bytes(source)
            cmakelists = "\n".join([
                "cmake_minimum_required(VERSION 3.25)",
                "project(espeak_offline_regression NONE)",
                "set(CMAKE_DISABLE_FIND_PACKAGE_Threads TRUE)",
                "set(CMAKE_FIND_ROOT_PATH " + json.dumps(empty.as_posix()) + ")",
                "set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM ONLY)",
                "set(FETCHCONTENT_FULLY_DISCONNECTED ON)",
                "set(FETCHCONTENT_UPDATES_DISCONNECTED ON)",
                "if(POLICY CMP0170)",
                "  cmake_policy(SET CMP0170 NEW)",
                "endif()",
                "include(" + json.dumps((project / "deps.cmake").as_posix()) + ")",
                "if(TARGET sonic OR HAVE_LIBSONIC)",
                "  message(FATAL_ERROR \"Unexpected Sonic dependency in explicit-OFF regression\")",
                "endif()",
                "message(STATUS \"HERMES_ESPEAK_EXPLICIT_OFF_NO_FETCH\")", "",
            ])
            (project / "CMakeLists.txt").write_text(cmakelists, encoding="utf-8", newline="\n")
            command = [cmake, "-S", str(project), "-B", str(build), "-G", "Ninja",
                       "-DCMAKE_MAKE_PROGRAM=" + Path(ninja).as_posix()]
            if option is not None:
                command += ["-DUSE_LIBSONIC=" + option]
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
            (args.out / (label + ".stdout.log")).write_bytes(result.stdout)
            (args.out / (label + ".stderr.log")).write_bytes(result.stderr)
            text = (result.stdout + result.stderr).decode("utf-8", "replace")
            passed = (result.returncode == 0) == expected
            if expected:
                passed = passed and "HERMES_ESPEAK_EXPLICIT_OFF_NO_FETCH" in text and not (build / "_deps").exists()
            else:
                passed = passed and "sonic" in text.lower()
            rows.append({"case": label, "expected_configure_success": expected,
                         "exit_code": result.returncode, "status": "passed" if passed else "failed",
                         "source_sha256": helper.digest(source),
                         "stdout_sha256": helper.digest(result.stdout), "stderr_sha256": helper.digest(result.stderr),
                         "command": command, "network_fetch_disabled": True})
    receipt = {"schema_version": 1, "status": "passed" if all(r["status"] == "passed" for r in rows) else "failed",
               "source_commit": lock["source"]["commit"], "patch_sha256": lock["patch"]["sha256"],
               "cases": rows, "native_compatibility_claimed": False}
    (args.out / "ESPEAK-CMAKE-REGRESSION.json").write_bytes(helper.canonical(receipt))
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
