#!/usr/bin/env python3
"""Readiness probe for a freshly prepared full Hermes audio environment.

Loads NumPy/cffi/PortAudio and reads device metadata if initialization succeeds.
Never opens, starts, records, plays, or uploads an audio stream.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def preparer():
    name = "_audio_preparation_contract"
    path = Path(__file__).with_name("prepare_audio_hermes_environment.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def classify_initialization(*, error, framework_present, input_devices):
    """Preparation and Android audio capability are separate outcomes."""
    if error is not None:
        return {
            "status": "unavailable", "initialization_error": error,
            "container_framework_absent": not framework_present,
            "physical_vad": "not-tested", "microphone_accessed": False,
        }
    return {
        "status": "initialized", "initialization_error": None,
        "container_framework_absent": not framework_present, "input_device_count": input_devices,
        "capture_readiness": "inventory-only" if input_devices else "no-input-device",
        "physical_vad": "not-tested", "microphone_accessed": False,
    }


def mapped_files():
    result = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith("/") and not fields[5].endswith(" (deleted)"):
            path = Path(fields[5])
            if path.is_file():
                result.add(path.resolve())
    return sorted(result)


def runtime_worker(request):
    prep = preparer()
    payload, output = Path(request["payload"]), Path(request["out"])
    prep.native_identity(payload)
    require = prep.require
    require(Path(sys.prefix).resolve() == payload / "venv", "probe did not enter the fresh application environment")
    sys.path.insert(0, str(payload / "app"))
    from pm.paths import repo_root
    import pm
    require(repo_root().resolve() == payload / "app", "runtime imported a different PM")
    from tools import voice_mode
    from tools import voice_mode_capture
    require(Path(voice_mode.__file__).resolve() == payload / "app/tools/voice_mode.py"
            and Path(voice_mode_capture.__file__).resolve() == payload / "app/tools/voice_mode_capture.py",
            "runtime imported another voice implementation")
    for name, (size, digest) in prep.SOURCE_FILES.items():
        prep.pinned(payload / "app" / name, size, digest)
    require(pm.available("audio-io"), "fresh full runtime does not expose audio-io anchors")
    import cffi
    import _cffi_backend
    import numpy as np
    for module in (cffi, _cffi_backend, np):
        require(Path(module.__file__).resolve().is_relative_to(payload / "venv/lib/python3.14/site-packages"),
                "native module came from another environment")
    require(cffi.__version__ == "2.1.1" and np.__version__ == "2.4.3", "native audio dependency versions differ")
    ffi = cffi.FFI()
    native_array = ffi.new("int[]", [7, 11, 23])
    require([native_array[i] for i in range(3)] == [7, 11, 23], "cffi native allocation failed")
    raw = ffi.buffer(native_array)
    require(len(raw) == 3 * ffi.sizeof("int"), "cffi native buffer size differs")
    x = np.arange(8, dtype=np.float64)
    require(np.array_equal(x * 3 + 1, np.array([1., 4., 7., 10., 13., 16., 19., 22.])),
            "NumPy native arithmetic failed")
    require(np.allclose(np.fft.ifft(np.fft.fft(x)).real, x, atol=1e-12), "NumPy FFT roundtrip failed")
    matrix = np.array([[3., 1.], [1., 2.]])
    rhs = np.array([9., 8.])
    require(np.allclose(np.linalg.solve(matrix, rhs), [2., 3.]), "NumPy internal LAPACK solve failed")
    require(np.allclose(matrix @ np.array([[1., 2.], [3., 4.]]), [[6., 10.], [7., 10.]]),
            "NumPy matrix multiplication failed")
    wrapper = payload / "runtime-libs/lib/libOpenSLES.so"
    portaudio = payload / "runtime-libs/lib/libportaudio.so.2"
    prep.pinned(wrapper, prep.OPENSLES_BYTES, prep.OPENSLES_SHA)
    prep.pinned(portaudio, 61976, prep.PORTAUDIO_SHA)
    # Explicit owned objects bind the SONAME before sounddevice's library discovery.
    ctypes.CDLL(str(wrapper))
    ctypes.CDLL(str(portaudio))
    paths = {p: Path(p).exists() for p in (
        "/dev/binder", "/dev/vndbinder", "/dev/hwbinder", "/dev/binderfs/binder",
        "/system/bin/audioserver", "/system/bin/servicemanager",
        "/system/lib64/libOpenSLES.so", "/system/lib/libOpenSLES.so",
    )}
    error, devices, device_error = None, [], None
    try:
        import sounddevice as sd
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "args": repr(exc.args)}
        require(type(exc).__name__ == "PortAudioError", "audio import failed for a reason other than PortAudio initialization")
        require(voice_mode._audio_available() is False, "native initialization error was not reported as unavailable")
        reason = voice_mode._audio_unavailable_reason()
        require(isinstance(reason, str) and str(exc) in reason, "readiness diagnostic lost the real initialization error")
        try:
            voice_mode_capture.import_audio_modules()
        except voice_mode_capture.AudioInitializationError as wrapped:
            require(wrapped.__cause__ is not None and str(exc) in str(wrapped),
                    "audio initialization wrapper lost its original cause")
        else:
            raise AssertionError("initialization failure did not raise the reviewed diagnostic")
    else:
        require(Path(sd.__file__).resolve().is_relative_to(payload / "venv/lib/python3.14/site-packages"),
                "sounddevice came from another environment")
        require(voice_mode._audio_available() is True, "initialized audio was reported unavailable")
        try:
            devices = [dict(device) for device in sd.query_devices()]
        except Exception as exc:
            device_error = {"type": type(exc).__name__, "message": str(exc)}
    mapped = mapped_files()
    audio_mappings = []
    for path in mapped:
        if path.name.startswith(("libportaudio.so", "libOpenSLES.so")):
            expected = prep.PORTAUDIO_SHA if path.name.startswith("libportaudio") else prep.OPENSLES_SHA
            # Android's genuine framework object is measured separately, never equated with the wrapper.
            if str(path).startswith("/system/"):
                audio_mappings.append({"path": str(path), "sha256": prep.sha256(path), "kind": "Android framework"})
            else:
                require(path.is_relative_to(payload) and prep.sha256(path) == expected,
                        "audio resolved an unreviewed runtime library")
                audio_mappings.append({"path": str(path), "sha256": prep.sha256(path), "kind": "owned pinned library"})
    require(any(p["sha256"] == prep.PORTAUDIO_SHA for p in audio_mappings)
            and any(p["sha256"] == prep.OPENSLES_SHA for p in audio_mappings), "owned audio mappings are incomplete")
    originals = request["original_files"]
    borrowed = []
    for path in mapped:
        if path.is_relative_to(payload):
            relative = path.relative_to(payload).as_posix()
            if relative.startswith(("tools/", "runtime-libs/")) and relative in originals:
                row = originals[relative]
                if row["kind"] == "symlink":
                    # The canonical inventory's resolved target carries the file hash.
                    row = originals.get((payload / relative).resolve().relative_to(payload).as_posix())
                require(row and row["kind"] == "file" and prep.sha256(path) == row["sha256"],
                        "mapped original runtime bytes differ")
                borrowed.append({"path": relative, "sha256": row["sha256"]})
        elif path.is_relative_to(prep.PREFIX) and ".so" in path.name:
            require(path.name in {"libc.so", "libdl.so", "libm.so", "liblog.so", "libandroid.so", "libz.so"},
                    "native import borrowed an undeclared prefix library: " + str(path))
    input_count = sum(int(device.get("max_input_channels", 0)) > 0 for device in devices)
    result = {
        "schema_version": 1, "dependency_readiness": "passed", "native_numerics": "passed",
        "numpy_checks": ["arithmetic", "FFT roundtrip", "internal LAPACK solve", "matrix multiplication"],
        "cffi_checks": ["native allocation", "native buffer", "owned extension import"],
        "audio_io_anchors": True, "voice_module": str(voice_mode.__file__),
        "initialization": classify_initialization(error=error,
                        framework_present=paths["/system/lib64/libOpenSLES.so"], input_devices=input_count),
        "device_inventory": devices, "device_inventory_error": device_error,
        "android_framework_paths": paths, "mapped_audio_libraries": audio_mappings,
        "mapped_original_payload_libraries": borrowed, "physical_vad": "not-tested",
        "microphone_accessed": False, "audio_stream_opened": False,
        "interpretation": "A complete dependency environment can be prepared while PortAudio initialization is unavailable. Android framework presence and real capture/VAD require separate device validation.",
    }
    prep.write_json(output, result)


def run(options):
    prep = preparer()
    out = options.environment.resolve()
    receipt_path = out / "audio-environment-receipt.json"
    receipt = prep.json_object(receipt_path.read_bytes())
    prep.require(receipt.get("status") == "prepared-environment" and receipt.get("preparation_integrity") == "passed",
                 "environment has no successful preparation receipt")
    prep.require(receipt["final_path"] == str(out), "environment moved after preparation; rebuild it at its final path")
    prep.require(receipt["preparer_sha256"] == prep.sha256(Path(prep.__file__))
                 and receipt["probe_sha256"] == prep.sha256(Path(__file__)),
                 "preparation/probe code differs from the prepared receipt")
    payload = out / "payload"
    prep.require(prep.inventory_sha(prep.inventory(payload)) == receipt["prepared_inventory_sha256"],
                 "prepared payload differs from its receipt")
    evidence = out / "evidence"
    prep.require(not (evidence / "audio-readiness-probe.json").exists(), "probe receipt already exists")
    before = prep.inventory(payload)
    source = prep.json_object((evidence / "original-payload-inventory.json").read_bytes())["files"]
    request = evidence / "audio-readiness-request.json"
    prep.write_json(request, {"payload": str(payload), "out": str(evidence / "audio-readiness-probe.json"),
                              "original_files": source})
    environment = prep.native_environment(payload, out / "state")
    prep.run_logged([str(payload / "venv/bin/python"), "-I", "-B", str(Path(__file__).resolve()),
                     "--runtime-worker", str(request)], evidence, "audio-readiness",
                    env=environment, timeout=180)
    prep.run_logged([str(out / "run-hermes"), "--version"], evidence, "hermes-version",
                    env=environment, timeout=120)
    prep.require(before == prep.inventory(payload), "readiness/version probes modified the prepared payload")
    result = prep.json_object((evidence / "audio-readiness-probe.json").read_bytes())
    prep.write_json(evidence / "audio-readiness-summary.json", {
        "schema_version": 1, "preparation_integrity": "passed", "complete_hermes_runtime": "passed",
        "native_dependencies": result["native_numerics"], "portaudio_initialization": result["initialization"],
        "device_inventory_error": result["device_inventory_error"], "payload_preserved": True,
        "physical_vad": "not-tested", "microphone_accessed": False, "published": False,
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--runtime-worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.runtime_worker:
            runtime_worker(json.loads(args.runtime_worker.read_text()))
        else:
            if args.environment is None:
                parser.error("--environment is required")
            run(args)
    except Exception as exc:
        print("Audio readiness probe failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
