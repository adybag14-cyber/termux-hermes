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
import re
import stat
import subprocess
import sys
import traceback


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


# Exact platform objects from the immutable Termux container image. These are
# not application dependencies and are never copied into the device payload.
IMAGE_PLATFORM_FILES = {
    "libc++.so": (926896, "3b3a556e1a175baa03cd5e82a4a9189182ad1b1824319f15c681a13fdfdc42f0"),
    "libc.so": (1126832, "f9eacc7c6402ae1cca97e6e080340e12203bcd43cb44b054522239a7eed64fc4"),
    "libdl.so": (67504, "cfee715580eac1a5cf3a7713ceebd61e83544a2889bd4799be7c23272356815b"),
    "liblog.so": (136800, "af8872cb6e476b8d66bbf6d84eb6fb12e3312ea79a5c947a63a8428256b45a81"),
    "libm.so": (265480, "d99e586652e539e4840c4466d6a8d8a7fe169b662a48935000226eb7f1c41f9b"),
}


def image_shared_objects(mapped, prefix):
    """Select image .so mappings without treating the linker as a dependency."""
    return {path for path in mapped
            if path.is_relative_to(prefix / "opt/aosp") and ".so" in path.name}


def verify_image_platform_members(paths, inspection_path, evidence, prep):
    """Admit only measured image files with exact bytes, ABI and ownership."""
    require = prep.require
    if not paths:
        return {"status": "not-used", "members": [],
                "interpretation": "No container image platform library was mapped."}
    platform_root = prep.PREFIX / "opt/aosp/lib64"
    pins = {platform_root / name: pin for name, pin in IMAGE_PLATFORM_FILES.items()}
    require(set(paths) <= set(pins), "unreviewed container image platform member")
    require(inspection_path is not None,
            "container image platform members require the Docker image inspection")
    inspection_path = Path(inspection_path)
    require(inspection_path.is_file() and not inspection_path.is_symlink()
            and inspection_path.stat().st_size <= 2_000_000, "invalid Docker image inspection")
    raw = inspection_path.read_bytes()
    images = json.loads(raw)
    require(isinstance(images, list) and len(images) == 1 and isinstance(images[0], dict),
            "ambiguous Docker image inspection")
    image = images[0]
    require(image.get("Architecture") == "arm64" and image.get("Os") == "linux"
            and prep.IMAGE in image.get("RepoDigests", [])
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("Id", "")) is not None,
            "Docker image differs from the reviewed ARM64 image")
    # Keep the unmodified host Docker observation with each independent probe.
    with (evidence / "audio-source-image.json").open("xb") as stream:
        stream.write(raw)
    query = str(prep.PREFIX / "bin/dpkg-query")
    snapshot = prep.run_logged([
        query, "-W", "-f=${Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n",
        "aosp-libs",
    ], evidence, "audio-image-owner", timeout=20).stdout
    require(snapshot == b"aosp-libs\t9.0.0-r76-4\taarch64\tinstalled\n",
            "container image platform owner version differs")
    originals = sorted(set(paths))
    owner_raw = prep.run_logged(
        [query, "-S", *(str(path) for path in originals)],
        evidence, "audio-image-path-owners", timeout=20).stdout
    owners = {}
    for line in owner_raw.decode("utf-8").splitlines():
        owner, separator, name = line.rpartition(": ")
        require(separator and owner == "aosp-libs" and name not in owners,
                "container image platform owner differs or is ambiguous")
        owners[name] = owner
    require(set(owners) == {str(path) for path in originals},
            "container image platform ownership is incomplete")
    members = []
    for path in originals:
        require(path.absolute() == path.resolve() and stat.S_ISREG(path.lstat().st_mode),
                "container image platform member is not an exact regular path")
        prep.pinned(path, *pins[path])
        with path.open("rb") as stream:
            header = stream.read(64)
        require(len(header) == 64 and header[:6] == b"\x7fELF\x02\x01"
                and int.from_bytes(header[18:20], "little") == 183,
                "container image platform member ABI differs")
        members.append({"path": str(path), "bytes": pins[path][0], "sha256": pins[path][1],
                        "elf_class": 64, "endianness": "little", "machine": 183,
                        "package": owners[str(path)], "version": "9.0.0-r76-4",
                        "architecture": "aarch64"})
    return {"status": "verified-image-members", "native_image": prep.IMAGE,
            "docker_image_id": image["Id"], "inspection_sha256": hashlib.sha256(raw).hexdigest(),
            "members": members,
            "interpretation": "Exact immutable-image platform files; no AOSP directory or device-library allowance."}


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
    namespace = payload / "runtime-libs/lib" / prep.PLATFORM_NAMESPACE_FILE
    prep.pinned(namespace, prep.PLATFORM_NAMESPACE_BYTES, prep.PLATFORM_NAMESPACE_SHA)
    prep.pinned(wrapper, prep.OPENSLES_BYTES, prep.OPENSLES_SHA)
    prep.pinned(portaudio, 61976, prep.PORTAUDIO_SHA)
    # Explicit owned objects bind the SONAME before sounddevice's library discovery.
    ctypes.CDLL(str(namespace))
    ctypes.CDLL(str(wrapper))
    ctypes.CDLL(str(portaudio))
    paths = {p: Path(p).exists() for p in (
        "/dev/binder", "/dev/vndbinder", "/dev/hwbinder", "/dev/binderfs/binder",
        "/system/bin/audioserver", "/system/bin/servicemanager",
        "/system/lib64/libOpenSLES.so", "/system/lib/libOpenSLES.so",
    )}
    sounddevice_source = payload / "venv/lib/python3.14/site-packages/sounddevice.py"
    prep.pinned(sounddevice_source, *prep.SOUNDDEVICE_SOURCE_AFTER)
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
    # Retain observations before a later provenance check can fail. This is
    # diagnostic evidence, never a dependency-readiness or capture success.
    prep.write_json(output.with_name("audio-runtime-observations.json"), {
        "schema_version": 1, "status": "observed-before-provenance-validation",
        "initialization_error": error, "device_inventory": devices,
        "device_inventory_error": device_error, "android_framework_paths": paths,
        "mapped_shared_objects": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": prep.sha256(path)}
            for path in mapped if ".so" in path.name
        ],
        "physical_vad": "not-tested", "microphone_accessed": False,
        "audio_stream_opened": False, "published": False,
    })
    audio_mappings = []
    for path in mapped:
        if (path.name.startswith(("libportaudio.so", "libOpenSLES.so"))
                or path.name == prep.PLATFORM_NAMESPACE_FILE):
            expected = (prep.PLATFORM_NAMESPACE_SHA if path.name == prep.PLATFORM_NAMESPACE_FILE
                        else prep.PORTAUDIO_SHA if path.name.startswith("libportaudio")
                        else prep.OPENSLES_SHA)
            # Android's genuine framework object is measured separately, never equated with the wrapper.
            if str(path).startswith("/system/"):
                audio_mappings.append({"path": str(path), "sha256": prep.sha256(path), "kind": "Android framework"})
            else:
                require(path.is_relative_to(payload) and prep.sha256(path) == expected,
                        "audio resolved an unreviewed runtime library")
                audio_mappings.append({"path": str(path), "sha256": prep.sha256(path), "kind": "owned pinned library"})
    require(any(p["sha256"] == prep.PORTAUDIO_SHA for p in audio_mappings)
            and any(p["sha256"] == prep.OPENSLES_SHA for p in audio_mappings)
            and any(p["sha256"] == prep.PLATFORM_NAMESPACE_SHA for p in audio_mappings),
            "owned audio mappings are incomplete")
    image_paths = image_shared_objects(mapped, prep.PREFIX)
    image_platform = verify_image_platform_members(
        image_paths, request.get("image_inspection"), output.parent, prep)
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
        elif path in image_paths:
            # The separate exact file/hash/ELF/owner/image checks above passed.
            continue
        elif path.is_relative_to(prep.PREFIX) and ".so" in path.name:
            require(path.name in {"libc.so", "libdl.so", "libm.so", "liblog.so", "libandroid.so", "libz.so"},
                    "native import borrowed an undeclared prefix library: " + str(path))
    input_count = sum(int(device.get("max_input_channels", 0)) > 0 for device in devices)
    result = {
        "schema_version": 1, "dependency_readiness": "passed", "native_numerics": "passed",
        "sounddevice_android_discovery": {
            "source_sha256": prep.SOUNDDEVICE_SOURCE_AFTER[1],
            "derived_wheel_sha256": prep.SOUNDDEVICE_WHEEL_AFTER[1],
            "native_initialization_errors_preserved": True,
        },
        "numpy_checks": ["arithmetic", "FFT roundtrip", "internal LAPACK solve", "matrix multiplication"],
        "cffi_checks": ["native allocation", "native buffer", "owned extension import"],
        "audio_io_anchors": True, "voice_module": str(voice_mode.__file__),
        "initialization": classify_initialization(error=error,
                        framework_present=paths["/system/lib64/libOpenSLES.so"], input_devices=input_count),
        "device_inventory": devices, "device_inventory_error": device_error,
        "android_framework_paths": paths, "mapped_audio_libraries": audio_mappings,
        "image_platform_validation": image_platform,
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
                              "original_files": source,
                              "image_inspection": (str(options.image_inspection.resolve())
                                                   if options.image_inspection is not None else None)})
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



def exception_details(exc):
    """Retain the original exception chain; never turn an error into readiness."""
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append({
            "type": type(current).__name__, "module": type(current).__module__,
            "message": str(current), "args": repr(current.args),
        })
        current = (current.__cause__ if current.__cause__ is not None
                   else None if current.__suppress_context__ else current.__context__)
    return {
        "type": type(exc).__name__, "message": str(exc), "chain": chain,
        "traceback": "".join(traceback.format_exception(exc)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--image-inspection", type=Path,
                        help="Host Docker image inspection for the container-only platform file gate")
    parser.add_argument("--runtime-worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    request = None
    try:
        if args.runtime_worker:
            request = json.loads(args.runtime_worker.read_text())
            runtime_worker(request)
        else:
            if args.environment is None:
                parser.error("--environment is required")
            run(args)
    except Exception as exc:
        details = exception_details(exc)
        if args.runtime_worker and isinstance(request, dict) and isinstance(request.get("out"), str):
            try:
                preparer().write_json(Path(request["out"]).with_name("audio-readiness-failure.json"), {
                    "schema_version": 1, "status": "failed", "stage": "runtime-worker",
                    "error": details, "dependency_readiness": "not-completed",
                    "physical_vad": "not-tested", "microphone_accessed": False,
                    "audio_stream_opened": False, "published": False,
                })
            except Exception as receipt_error:
                print("Could not retain audio failure receipt: " + str(receipt_error), file=sys.stderr)
        print("Audio readiness probe failed: " + str(exc), file=sys.stderr)
        print(details["traceback"], file=sys.stderr, end="")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
