#!/usr/bin/env python3
"""Build pinned eSpeak in an owned directory and test its real C ABI without audio I/O."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX = Path("/data/data/com.termux/files/usr")


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    prep = module_at("_espeak_preparer", SCRIPT_DIR / "prepare_neutts_espeak_source.py")
    lock, _ = prep.load_lock()
    path = SCRIPT_DIR / "compatibility_probe_neutts_native.py"
    prep.support().require(hashlib.sha256(path.read_bytes()).hexdigest() == lock["native_probe_support_sha256"],
                           "Reviewed native compiler/provenance helper changed")
    return prep, module_at("_espeak_native_support", path), lock


def tree_manifest(root, helper):
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        helper.require(stat.S_ISREG(path.lstat().st_mode), "Unexpected link/special data file")
        name = path.relative_to(root).as_posix()
        rows.append(helper.file_row(name, "100755" if path.stat().st_mode & 0o111 else "100644", path.read_bytes()))
    return rows


def api_case(args):
    prep, native, lock = helpers()
    helper = prep.support()
    runtime = native.native_runtime()
    library, data = args.library.resolve(strict=True), args.data.resolve(strict=True)
    lib = ctypes.CDLL(str(library))
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_SetVoiceByName.argtypes, lib.espeak_SetVoiceByName.restype = [ctypes.c_char_p], ctypes.c_int
    lib.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int]
    lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
    lib.espeak_Info.argtypes, lib.espeak_Info.restype = [ctypes.POINTER(ctypes.c_char_p)], ctypes.c_char_p
    lib.espeak_Terminate.argtypes, lib.espeak_Terminate.restype = [], ctypes.c_int
    # Synchronous retrieval initializes no playback backend. No Synth call is made.
    sample_rate = lib.espeak_Initialize(2, 0, os.fsencode(data), 0)
    if args.case == "missing-data":
        raise RuntimeError("Missing language data was unexpectedly accepted")
    helper.require(sample_rate > 0, "eSpeak initialization failed")
    path_data = ctypes.c_char_p()
    version = lib.espeak_Info(ctypes.byref(path_data)).decode("utf-8")
    helper.require(version == "1.52.0.1" and Path(os.fsdecode(path_data.value)).resolve() == data,
                   "Wrong eSpeak version or language-data origin")
    result = {"schema_version": 1, "case": args.case, "status": "passed", "runtime": runtime,
              "version": version, "sample_rate": sample_rate, "data_path": str(data),
              "library": native.elf(library, dynamic=True), "synthesis_called": False}
    try:
        if args.case == "invalid-voice":
            code = lib.espeak_SetVoiceByName(b"hermes-intentionally-unknown-voice")
            helper.require(code == 2, "Unknown voice did not return EE_NOT_FOUND")
            result["voice_error"] = code
        else:
            fixture = lock["fixtures"][args.fixture]
            helper.require(lib.espeak_SetVoiceByName(fixture["language"].encode()) == 0,
                           "Requested voice unavailable")
            encoded = fixture["text"].encode("utf-8")
            buffer = ctypes.create_string_buffer(encoded)
            start, end = ctypes.addressof(buffer), ctypes.addressof(buffer) + len(encoded)
            pointer = ctypes.c_void_p(start)
            clauses = []
            while pointer.value:
                previous = pointer.value
                raw = lib.espeak_TextToPhonemes(ctypes.byref(pointer), 1, 2 if args.case == "ipa" else 0)
                helper.require(raw is not None, "Phonemization returned NULL")
                clauses.append(raw.decode("utf-8", "strict"))
                helper.require(len(clauses) <= 256, "Clause loop did not terminate")
                if pointer.value is not None:
                    helper.require(start <= pointer.value <= end, "C ABI input cursor escaped input")
                    if pointer.value == end:
                        break
                    helper.require(pointer.value > previous, "C ABI input cursor made no progress")
            # Upstream shell tests trim command-substitution newlines; preserve
            # interior phoneme/word spacing and record every raw clause separately.
            actual = "\n".join(c.strip(" \t\r\n") for c in clauses if c.strip(" \t\r\n"))
            helper.require(bool(actual), "Phonemization was empty")
            if args.case == "ascii":
                helper.require(actual == fixture["expected_ascii"], "Frozen upstream phoneme oracle mismatch")
            else:
                helper.require(any(ord(c) > 127 for c in actual), "IPA output contains no IPA code points")
                helper.require("\u02c8" in actual or "\u02cc" in actual, "IPA stress marker absent")
            result.update({"fixture": args.fixture, "language": fixture["language"], "text": fixture["text"],
                           "phonemes": actual, "raw_clauses": clauses, "cursor_completed": True,
                           "upstream_ascii_oracle_checked": args.case == "ascii"})
        mapped = set()
        for line in Path("/proc/self/maps").read_text().splitlines():
            parts = line.split(None, 5)
            if len(parts) == 6 and parts[5].startswith("/") and ".so" in parts[5]:
                helper.require(not parts[5].endswith(" (deleted)"), "Deleted runtime library mapping")
                mapped.add(Path(parts[5]).resolve())
        actual_espeak = {p for p in mapped if p.name.startswith("libespeak-ng.so")}
        helper.require(actual_espeak == {library}, "Unexpected system eSpeak library fallback")
        result["mapped_libraries"] = [native.elf(p) for p in sorted(mapped)]
    finally:
        helper.require(lib.espeak_Terminate() == 0, "eSpeak termination failed")
    args.out.write_bytes(helper.canonical(result))
    return result


def execute_case(args, native, helper, out, label, case, fixture, library, data, expected=0):
    receipt = out / (label + ".json")
    command = [str(PREFIX / "bin/python"), "-I", "-B", str(Path(__file__).resolve()),
               "--case", case, "--fixture", str(fixture), "--library", str(library),
               "--data", str(data), "--out", str(receipt)]
    if expected == 0:
        row = native.bounded_command(command, out, label, 30, env=dict(os.environ))
        child = native.read_json(receipt)
        helper.require(child.get("status") == "passed", "Failed eSpeak C ABI case")
        return {"case": label, "status": "passed", **row, "receipt": receipt.name,
                "receipt_sha256": native.sha_file(receipt)}, child
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    (out / (label + ".stdout.log")).write_bytes(result.stdout)
    (out / (label + ".stderr.log")).write_bytes(result.stderr)
    helper.require(result.returncode == expected and not receipt.exists()
                   and b"phon" in result.stderr.lower(), "Missing data did not fail during initialization")
    return {"case": label, "status": "passed", "command": command, "exit_code": result.returncode,
            "expected_initialization_failure": True, "stdout_sha256": helper.digest(result.stdout),
            "stderr_sha256": helper.digest(result.stderr)}, None


def run(args):
    prep, native, lock = helpers()
    helper = prep.support()
    helper.require(not args.out.exists(), "Fresh native eSpeak evidence directory required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "source_commit": lock["source"]["commit"],
              "lock_sha256": prep.LOCK_SHA256, "patch_sha256": lock["patch"]["sha256"], "cases": [],
              "model_downloaded": False, "synthesis_tested": False, "audio_io_performed": False,
              "real_python_wrapper_proved": False, "release_output": False}
    try:
        report["runtime"] = native.native_runtime()
        with tempfile.TemporaryDirectory(prefix="hermes-espeak-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            source, build, bundle = work / "source", work / "build", args.out / "bundle"
            _, native_lock = prep.verify_inputs(args.inputs, source)
            report["source_manifest"] = lock["patched_manifest"]
            report["foundation"] = native.validate_foundation(args.foundation_receipt, native_lock)
            report["limits"] = native.set_resource_bounds(native_lock)
            report["toolchain"] = native.install_toolchain(native_lock, args.apt_archives, args.out, work)
            flags = native_lock["build"]["cflags"] + " -D_FILE_OFFSET_BITS=64 -I" + str(source / "src/ucd-tools/src/include")
            env = dict(os.environ)
            env.update({"SOURCE_DATE_EPOCH": str(lock["source_date_epoch"]), "CC": str(PREFIX / "bin/clang"),
                        "CXX": str(PREFIX / "bin/clang++"), "CFLAGS": flags, "CXXFLAGS": flags})
            for key in ("ESPEAK_DATA_PATH", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CMAKE_TOOLCHAIN_FILE"):
                env.pop(key, None)
            configure = [str(PREFIX / "bin/cmake"), "-S", str(source), "-B", str(build), "-G", "Ninja",
                         "-DCMAKE_INSTALL_PREFIX=" + str(bundle), "-DCMAKE_C_COMPILER=" + env["CC"],
                         "-DCMAKE_CXX_COMPILER=" + env["CXX"], "-DCMAKE_C_FLAGS=" + flags,
                         "-DCMAKE_CXX_FLAGS=" + flags]
            configure += ["-D" + name + "=" + value for name, value in lock["configure"].items()]
            report["configure"] = native.bounded_command(configure, args.out, "espeak-configure", 180, env)
            systems = list((build / "CMakeFiles").glob("*/CMakeSystem.cmake"))
            helper.require(len(systems) == 1 and 'set(CMAKE_CROSSCOMPILING "FALSE")' in systems[0].read_text(),
                           "eSpeak data generation requires a true native CMake build")
            cache = (build / "CMakeCache.txt").read_text()
            for name, value in lock["configure"].items():
                helper.require(re.search(r"^" + re.escape(name) + r":[^=]+=" + re.escape(value) + r"$", cache, re.M),
                               "CMake option changed: " + name)
            helper.require(not (build / "_deps").exists(), "Unreviewed CMake dependency directory appeared")
            report["build"] = native.bounded_command(
                [str(PREFIX / "bin/cmake"), "--build", str(build), "--target", "espeak-ng-bin", "data", "--parallel", "2"],
                args.out, "espeak-build", 600, env)
            report["install"] = native.bounded_command(
                [str(PREFIX / "bin/cmake"), "--install", str(build)], args.out, "espeak-install", 60, env)
            for name in ("CMakeCache.txt", "compile_commands.json", "install_manifest.txt"):
                shutil.copyfile(build / name, args.out / name)
            shutil.copyfile(systems[0], args.out / "CMakeSystem.cmake")
            shutil.copyfile(source / "COPYING", bundle / "COPYING.espeak-ng")
            library = (bundle / "lib/libespeak-ng.so.1.52.0.1").resolve(strict=True)
            data = (bundle / "share/espeak-ng-data").resolve(strict=True)
            report["library"] = native.elf(library, dynamic=True)
            report["cli"] = native.elf(bundle / "bin/espeak-ng", dynamic=True)
            forbidden = re.compile(r"(sonic|pcaudio|asound|pulse|musl|\.so\.6$|libpthread\.so\.0)")
            helper.require(not any(forbidden.search(name) for name in report["library"]["needed"]),
                           "Unexpected audio or non-Bionic runtime dependency")
            dictionaries = re.search(r"list\(APPEND _dict_compile_list\s+(.*?)\)", (source / "cmake/data.cmake").read_text(), re.S).group(1).split()
            helper.require(len(dictionaries) == len(set(dictionaries)), "Duplicate dictionary source list")
            for name in [*(language + "_dict" for language in dictionaries), "intonations", "phondata", "phonindex", "phontab"]:
                helper.require((data / name).is_file() and (data / name).stat().st_size > 0, "Missing generated language data: " + name)
            for subtree in ("lang", "voices/!v"):
                for path in (source / "espeak-ng-data" / subtree).rglob("*"):
                    if path.is_file():
                        target = data / path.relative_to(source / "espeak-ng-data")
                        helper.require(target.read_bytes() == path.read_bytes(), "Bundled voice/language file changed")
            data_rows = tree_manifest(data, helper)
            manifest = helper.canonical(data_rows)
            (args.out / "ESPEAK-DATA-MANIFEST.json").write_bytes(manifest)
            report["data_tree"] = {"path": str(data), "file_count": len(data_rows),
                                   "bytes": sum(row["size"] for row in data_rows),
                                   "dictionary_count": len(dictionaries), "manifest": "ESPEAK-DATA-MANIFEST.json",
                                   "manifest_sha256": helper.digest(manifest)}
            for index in range(len(lock["fixtures"])):
                row, _ = execute_case(args, native, helper, args.out, "espeak-ascii-" + str(index), "ascii", index, library, data)
                report["cases"].append(row)
            ipa = []
            for index in range(2):
                row, child = execute_case(args, native, helper, args.out, "espeak-ipa-repeat-" + str(index), "ipa", 0, library, data)
                report["cases"].append(row)
                ipa.append(child["phonemes"])
            helper.require(ipa[0] == ipa[1], "IPA changed between fresh processes")
            relocated = work / "relocated"
            shutil.copytree(bundle, relocated, symlinks=True)
            for index in range(len(lock["fixtures"])):
                row, _ = execute_case(args, native, helper, args.out, "espeak-relocated-" + str(index), "ascii", index,
                                      relocated / "lib/libespeak-ng.so.1.52.0.1", relocated / "share/espeak-ng-data")
                report["cases"].append(row)
            row, _ = execute_case(args, native, helper, args.out, "espeak-invalid-voice", "invalid-voice", 0, library, data)
            report["cases"].append(row)
            empty = work / "empty-data"
            empty.mkdir()
            row, _ = execute_case(args, native, helper, args.out, "espeak-missing-data", "missing-data", 0, library, empty, expected=1)
            report["cases"].append(row)
            report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (args.out / "ESPEAK-COMPONENT-RESULT.json").write_bytes(helper.canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--case", choices=("ascii", "ipa", "invalid-voice", "missing-data"))
    parser.add_argument("--fixture", type=int, default=0)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.case:
        if arguments.library is None or arguments.data is None:
            parser.error("C ABI case needs library and data paths")
        result = api_case(arguments)
    else:
        if any(value is None for value in (arguments.inputs, arguments.apt_archives, arguments.foundation_receipt)):
            parser.error("Native build needs source inputs, verified APT archives and foundation receipt")
        result = run(arguments)
    print(json.dumps({"status": result["status"], "receipt": str(arguments.out)}, indent=2))
