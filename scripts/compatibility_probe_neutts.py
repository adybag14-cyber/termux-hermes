"""Real APT scientific behavior, with one isolated child per ABI boundary."""
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import time
import traceback
import wave
import zipfile

CASES = ("python_dependencies", "torch", "torchaudio", "torchcodec", "scipy", "llvmlite", "soxr")
EXPECTED = {
    "torch": "2.14.1", "torchaudio": "2.11.0", "torchcodec": "0.17.0",
    "scipy": "1.18.1", "llvmlite": "0.49.0", "soxr": "1.1.0", "numpy": "2.5.4",
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def elf(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        header = stream.read(64)
    require(header[:6] == b"\x7fELF\x02\x01", "expected little-endian ELF64")
    machine = struct.unpack_from("<H", header, 18)[0]
    require(machine == 183, "expected actual AArch64 ELF")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path),
            "elf_class": 64, "endianness": "little", "machine": machine}


def libraries():
    prefix = Path(os.environ["PREFIX"])
    owners = {}
    for listing in (prefix / "var/lib/dpkg/info").glob("*.list"):
        for line in listing.read_text(errors="replace").splitlines():
            owners.setdefault(line, []).append(listing.name.removesuffix(".list"))
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/") and ".so" in parts[5]:
            paths.add(parts[5])
    result = []
    for raw in sorted(paths):
        path = Path(raw)
        if path.is_file():
            identity = elf(path)
            identity["mapped_path"] = raw
            identity["dpkg_owners"] = sorted(set(owners.get(raw, []) + owners.get(str(path.resolve()), [])))
            result.append(identity)
    return result


def module_identity(module):
    name = module.__name__.split(".")[0]
    version = importlib.metadata.version(name)
    require(version.split("+", 1)[0] == EXPECTED[name], f"{name} distribution version differs")
    return {"distribution": name, "version": version, "module_file": module.__file__,
            "module_sha256": sha(module.__file__)}


def python_dependencies_case():
    """Verify the installed closed wheel set and require real native MarkupSafe."""
    wheelhouse = Path(os.environ["NEUTTS_PYTHON_WHEELHOUSE"])
    lock_path = wheelhouse / "neutts_core_python_lock.json"
    require(sha(lock_path) == os.environ["NEUTTS_PYTHON_LOCK_SHA256"], "Python closure lock differs")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    require(lock["schema_version"] == 1 and len(lock["packages"]) == 9
            and lock["selected_extras"] == [], "unexpected Python core closure")
    torch_metadata = Path("/") / lock["apt_torch"]["metadata_member"].removeprefix("./")
    require(sha(torch_metadata) == lock["apt_torch"]["metadata_sha256"], "actual APT Torch metadata differs")
    installed = []
    for row in lock["packages"]:
        artifact = row["artifact"]
        wheel_path = wheelhouse / artifact["filename"]
        require(wheel_path.stat().st_size == artifact["bytes"] and sha(wheel_path) == artifact["sha256"],
                "Python wheel archive differs: " + row["name"])
        dist = importlib.metadata.distribution(row["name"])
        require(dist.version == row["version"], "installed Python version differs: " + row["name"])
        verified_files, rewritten = [], []
        with zipfile.ZipFile(wheel_path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                relative = PurePosixPath(item.filename)
                require(not relative.is_absolute() and ".." not in relative.parts,
                        "wheel member escapes its package")
                if item.filename == row["wheel"]["record_member"]:
                    rewritten.append({"member": item.filename, "reason": "installer regenerates RECORD"})
                    continue
                parts = relative.parts
                if parts[0].endswith(".data"):
                    require(len(parts) >= 3, "invalid wheel data path")
                    if parts[1] == "scripts":
                        rewritten.append({"member": item.filename, "reason": "installer rewrites script shebang"})
                        continue
                    require(parts[1] in ("purelib", "platlib"), "unreviewed wheel installation scheme")
                    relative = PurePosixPath(*parts[2:])
                expected = hashlib.sha256(archive.read(item)).hexdigest()
                actual = Path(dist.locate_file(str(relative)))
                require(actual.is_file() and not actual.is_symlink() and sha(actual) == expected,
                        "installed wheel file differs: " + item.filename)
                verified_files.append({"member": item.filename, "installed_file": str(actual), "sha256": expected})
        require(verified_files, "wheel has no verified installed files")
        manifest = json.dumps(verified_files, sort_keys=True, separators=(",", ":")).encode()
        installed.append({"name": row["name"], "version": dist.version,
                          "wheel_sha256": artifact["sha256"], "verified_files": len(verified_files),
                          "installed_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                          "installer_rewrites": rewritten})
    import markupsafe
    from markupsafe import _speedups
    native = next(row for row in lock["packages"] if row["name"] == "markupsafe")["native_members"]
    require(len(native) == 1 and sha(_speedups.__file__) == native[0]["sha256"],
            "native MarkupSafe module differs from the official Android wheel")
    require(markupsafe._escape_inner is _speedups._escape_inner, "MarkupSafe used a Python fallback")
    escaped = str(markupsafe.escape("<Hermes & Termux>"))
    require(escaped == "&lt;Hermes &amp; Termux&gt;", "native MarkupSafe escaping differs")
    return {"lock_sha256": sha(lock_path), "installed_distributions": installed,
            "apt_torch_metadata_sha256": sha(torch_metadata),
            "markupsafe_native_module": elf(_speedups.__file__), "escaped_text": escaped,
            "engine_installed": False, "candidate_modified": False}


def torch_case():
    import torch
    torch.set_num_threads(2)
    x = torch.arange(8, dtype=torch.float32).reshape(1, 1, 8)
    conv = torch.nn.Conv1d(1, 1, 3, bias=False)
    with torch.no_grad():
        conv.weight.copy_(torch.tensor([[[1.0, 2.0, 1.0]]]))
        result = conv(x).flatten().tolist()
    require(result == [4.0, 8.0, 12.0, 16.0, 20.0, 24.0], "Conv1d differs from exact stencil oracle")
    a = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    b = torch.tensor([[2.0, 0.0], [1.0, 2.0]])
    product = (a @ b).tolist()
    require(product == [[4.0, 4.0], [10.0, 8.0]], "tensor multiplication differs")
    return {"modules": [module_identity(torch)], "conv1d": result, "matmul": product, "device": str(x.device)}


def torchaudio_case():
    import torch
    import torchaudio
    torch.set_num_threads(2)
    signal = torch.tensor([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)])
    actual = torchaudio.functional.resample(signal, 24000, 16000)
    require(tuple(actual.shape) == (1600,) and bool(torch.isfinite(actual).all()), "resampled shape or values differ")
    expected = torch.tensor([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(torch.mean(torch.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "resampling differs from independent sinusoid oracle")
    return {"modules": [module_identity(torch), module_identity(torchaudio)],
            "input_rate": 24000, "output_rate": 16000, "output_samples": 1600, "mean_absolute_error": error}


def torchcodec_case(work):
    import torch
    import torchcodec
    from torchcodec.decoders import AudioDecoder
    pcm = [round(10000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(1600)]
    fixture = work / "owned-pcm.wav"
    with wave.open(str(fixture), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(struct.pack("<" + "h" * len(pcm), *pcm))
    decoded = AudioDecoder(str(fixture)).get_all_samples()
    require(decoded.sample_rate == 16000 and tuple(decoded.data.shape) == (1, 1600), "PCM decode shape/rate differs")
    expected = torch.tensor(pcm, dtype=torch.float32).reshape(1, -1) / 32768
    error = float(torch.max(torch.abs(decoded.data - expected)))
    require(bool(torch.isfinite(decoded.data).all()) and error < 0.000002, "decoded PCM differs from source samples")
    return {"modules": [module_identity(torch), module_identity(torchcodec)],
            "fixture_sha256": sha(fixture), "samples": 1600, "sample_rate": 16000, "maximum_absolute_error": error}


def scipy_case():
    import numpy as np
    import scipy
    from scipy import fft, linalg
    solved = linalg.solve(np.array([[3.0, 1.0], [1.0, 2.0]]), np.array([9.0, 8.0]))
    require(bool(np.allclose(solved, [2.0, 3.0], rtol=0, atol=1e-12)), "LAPACK solution differs")
    transformed = fft.fft(np.array([1.0, 2.0, 3.0, 4.0]))
    require(bool(np.allclose(transformed, [10.0, -2+2j, -2.0, -2-2j], rtol=0, atol=1e-12)), "FFT differs")
    return {"modules": [module_identity(np), module_identity(scipy)], "solution": solved.tolist(),
            "fft": [[float(x.real), float(x.imag)] for x in transformed]}


def llvmlite_case():
    import llvmlite
    from llvmlite import binding as llvm
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    triple = llvm.get_default_triple()
    target = llvm.Target.from_default_triple().create_target_machine()
    module = llvm.parse_assembly("""
define double @owned_mul_add(double %a, double %b) {
entry:
  %product = fmul double %a, %b
  %result = fadd double %product, 2.0
  ret double %result
}
""")
    module.triple = triple
    module.verify()
    with llvm.create_mcjit_compiler(module, target) as engine:
        engine.finalize_object()
        address = engine.get_function_address("owned_mul_add")
        require(address != 0, "JIT returned a null function")
        result = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double, ctypes.c_double)(address)(3.0, 7.0)
        require(result == 23.0, "native JIT function differs from independent arithmetic oracle")
    return {"modules": [module_identity(llvmlite)], "llvm_version": list(llvm.llvm_version_info),
            "target_triple": triple, "native_jit_result": result}


def soxr_case():
    import numpy as np
    import soxr
    signal = np.array([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)], dtype=np.float32)
    actual = soxr.resample(signal, 24000, 16000)
    require(actual.shape == (1600,) and bool(np.isfinite(actual).all()), "soxr shape/values differ")
    expected = np.array([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(np.mean(np.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "soxr differs from independent sinusoid oracle")
    return {"modules": [module_identity(np), module_identity(soxr)], "output_samples": 1600,
            "mean_absolute_error": error}


def run_case(name, out):
    receipt = {"schema_version": 1, "component": name, "status": "failed"}
    start = time.monotonic()
    try:
        result = torchcodec_case(Path(__file__).parent) if name == "torchcodec" else globals()[name + "_case"]()
        receipt.update(status="passed", behavior=result)
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        try:
            receipt["mapped_libraries"] = libraries()
        except Exception as exc:
            receipt.update(status="failed", library_evidence_error=str(exc))
        receipt["elapsed_seconds"] = round(time.monotonic() - start, 3)
        (out / f"neutts-{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if receipt["status"] == "passed" else 1


def execute_case(name, out):
    """Retain every child outcome; failed or malformed evidence cannot pass."""
    require(name in CASES, "unknown native component")
    path = out / f"neutts-{name}.json"
    require(not path.exists(), "refusing a stale component receipt: " + path.name)
    timed_out = False
    launch_error = None
    try:
        child = subprocess.run([sys.executable, "-I", "-B", __file__, "--case", name, str(out)],
                               capture_output=True, timeout=90)
        code, stdout, stderr = child.returncode, child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        timed_out = True
    except OSError as exc:
        code, stdout, stderr = 127, b"", str(exc).encode("utf-8")
        launch_error = {"type": type(exc).__name__, "message": str(exc)}
    row = {"component": name, "exit_code": code, "status": "failed", "timed_out": timed_out,
           "receipt": path.name if path.is_file() else None,
           "receipt_sha256": sha(path) if path.is_file() else None}
    for channel, payload in (("stdout", stdout), ("stderr", stderr)):
        saved = payload[-100000:]
        (out / f"neutts-{name}.{channel}.log").write_bytes(saved)
        row[channel + "_bytes"] = len(payload)
        row[channel + "_saved_bytes"] = len(saved)
        row[channel + "_truncated"] = len(saved) != len(payload)
    if code < 0:
        row["termination_signal"] = -code
    if launch_error:
        row["launch_error"] = launch_error
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(result, dict), "component receipt is not an object")
        require(result.get("schema_version") == 1, "component receipt schema differs")
        require(result.get("component") == name, "component receipt identity differs")
        require(result.get("status") in ("passed", "failed"), "component receipt status differs")
        if code == 0 and not timed_out and result["status"] == "passed":
            require(isinstance(result.get("behavior"), dict), "passed receipt has no behavior")
            require(isinstance(result.get("mapped_libraries"), list) and result["mapped_libraries"],
                    "passed receipt has no native library evidence")
            row["status"] = "passed"
        if "error" in result:
            row["error"] = result["error"]
        if "library_evidence_error" in result:
            row["library_evidence_error"] = result["library_evidence_error"]
    except (OSError, ValueError, RuntimeError) as exc:
        row["receipt_error"] = {"type": type(exc).__name__, "message": str(exc)}
    return row


def main(out):
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.getuid() == 1000,
            "native Bionic UID1000 interpreter required")
    require(sys.version_info[:3] == (3, 14, 6), "actual APT Python version differs")
    require(Path(sys.prefix).resolve() == Path(os.environ["PREFIX"]).resolve(), "probe entered a managed environment")
    packages = {}
    for line in (out / "NEUTTS-INSTALLED-PACKAGES.tsv").read_text().splitlines():
        name, version, architecture = line.split("\t")
        packages[name] = {"version": version, "architecture": architecture}
    pins = []
    for line in (out / "NEUTTS-PINNED-APT.tsv").read_text().splitlines():
        name, version, architecture, digest, size, filename = line.split("\t")
        require(packages.get(name) == {"version": version, "architecture": architecture}, "installed APT pin differs: " + name)
        pins.append({"package": name, "version": version, "architecture": architecture,
                     "sha256": digest, "bytes": int(size), "repository_path": filename})
    receipt = {
        "schema_version": 1, "status": "running", "scope": "APT native scientific ABI/behavior with verified Python dependencies",
        "python": {"version": sys.version, "platform": sys.platform, "prefix": sys.prefix,
                   "executable": elf("/proc/self/exe")}, "uid": os.getuid(),
        "apt_archives": pins, "apt_archive_hashes_checked_before_install": True,
        "signed_apt": {p.name: sha(p) for p in (out / "signed-apt").iterdir()},
        "engine_installed": False, "synthesis_tested": False, "model_downloaded": False,
        "physical_audio_tested": False, "candidate_modified": False, "pm_admission_changed": False,
        "cases": [],
    }
    result_path = out / "NEUTTS-CORE-RESULT.json"
    result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name in CASES:
        receipt["cases"].append(execute_case(name, out))
        result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt["status"] = "passed" if all(row["exit_code"] == 0 and row["status"] == "passed" for row in receipt["cases"]) else "failed"
    result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "cases": receipt["cases"]}), flush=True)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    if sys.argv[1] == "--case":
        raise SystemExit(run_case(sys.argv[2], Path(sys.argv[3])))
    raise SystemExit(main(Path(sys.argv[1])))
