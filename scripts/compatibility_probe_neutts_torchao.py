#!/usr/bin/env python3
"""Actual installed TorchAO 0.12.0 CPU NF4 behavior over the frozen foundation."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import sysconfig
import tempfile
import traceback
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX = Path("/data/data/com.termux/files/usr")
PREPARER_SHA256 = "2053b4b6e457196527e86ee547e9f358bbbfbb78798550fd84bf520bc0f28c55"
CASE_NAMES = ("real_package_import", "nf4_default_quantization",
              "independent_dequantization", "linear_forward", "input_gradient")
CODEBOOK = (-1.0, -0.6962, -0.5251, -0.3949, -0.2844, -0.1848, -0.0911, 0.0,
            0.0796, 0.1609, 0.2461, 0.3379, 0.4407, 0.5626, 0.7230, 1.0)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected regular evidence or package file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preparer():
    path = SCRIPT_DIR / "prepare_neutts_torchao.py"
    require(sha(path) == PREPARER_SHA256, "Reviewed TorchAO preparer changed")
    spec = importlib.util.spec_from_file_location("_torchao_component_preparer", path)
    require(spec is not None and spec.loader is not None, "Cannot load exact input verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def weight_values():
    # Vary every block's scale; a constant absmax would degenerate double quantization.
    return [f32(math.sin(i * 0.173) + (0.5 + (i // 64) / 256.0) * math.cos(i * 0.019))
            for i in range(128 * 128)]


def reference_packed(values):
    """Independent scalar nearest-codebook oracle, without TorchAO or torch."""
    codebook = tuple(map(f32, CODEBOOK))
    codes = []
    for start in range(0, len(values), 64):
        block = values[start:start + 64]
        scale = max(map(abs, block))
        require(scale > 0, "Fixture must contain no zero block")
        for value in block:
            normalized = f32(value / scale)
            distances = [abs(f32(normalized - code)) for code in codebook]
            codes.append(min(range(16), key=distances.__getitem__))
    return [(codes[i] << 4) | codes[i + 1] for i in range(0, len(codes), 2)]


def reference_dequantized(packed, scalers, factors, mean):
    """Decode stored bytes/scalers independently with explicit float32 rounding."""
    require(len(packed) == 8192 and len(scalers) == 256 and len(factors) == 1
            and math.isfinite(factors[0]) and factors[0] > 0,
            "Unexpected default NF4 storage dimensions")
    codebook = tuple(map(f32, CODEBOOK))
    result = []
    for index, pair in enumerate(packed):
        scale = f32(f32(scalers[(index * 2) // 64] / factors[0]) + mean)
        result.extend((f32(codebook[pair >> 4] * scale), f32(codebook[pair & 15] * scale)))
    return result


def verify_installed(wheel, site, lock, prep):
    prep.verify_wheel(wheel, lock)
    require(site.is_dir() and site.resolve() == site.absolute(), "Unexpected venv site directory")
    info = "torchao-0.12.0.dist-info/"
    expected, rows = set(), []
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = item.filename
            target = site.joinpath(*PurePosixPath(name).parts)
            require(target.resolve() == target.absolute() and target.is_file(),
                    "Installed wheel member missing or reached through a symlink: " + name)
            expected.add(name)
            if name == lock["package"]["wheel"]["record_member"]:
                continue
            raw = archive.read(item)
            require(target.read_bytes() == raw, "Installed TorchAO wheel bytes changed: " + name)
            rows.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    generated = {info + name for name in ("INSTALLER", "REQUESTED", "direct_url.json")}
    expected.update(generated)
    require((site / (info + "INSTALLER")).read_bytes() == b"pip\n"
            and (site / (info + "REQUESTED")).read_bytes() == b"", "Unexpected pip installation metadata")
    direct = prep.read_json(site / (info + "direct_url.json"))
    archive_info = direct.get("archive_info", {})
    digest = lock["package"]["artifact"]["sha256"]
    require(set(direct) == {"url", "archive_info"} and direct["url"] == wheel.resolve().as_uri()
            and archive_info.get("hashes") == {"sha256": digest}
            and set(archive_info) <= {"hash", "hashes"}
            and archive_info.get("hash", "sha256=" + digest) == "sha256=" + digest,
            "Pip installation provenance is not the verified wheel")
    actual = set()
    for path in site.rglob("*"):
        require(not path.is_symlink(), "Venv site contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(site).as_posix())
    require(actual == expected, "Venv contains missing or unowned package files")
    record_name = lock["package"]["wheel"]["record_member"]
    record = list(csv.reader(io.StringIO((site / record_name).read_text(encoding="utf-8"))))
    require(all(len(row) == 3 for row in record)
            and len(record) == len(expected)
            and {row[0] for row in record} == expected,
            "Installed RECORD must cover each owned file exactly once")
    for name, digest_text, byte_text in record:
        if name == record_name:
            require(digest_text == byte_text == "", "Unexpected installed RECORD self-hash")
            continue
        raw = (site / name).read_bytes()
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        require(digest_text == "sha256=" + encoded and byte_text == str(len(raw)),
                "Installed RECORD hash differs: " + name)
    distributions = list(importlib.metadata.distributions(path=[str(site)]))
    require(len(distributions) == 1 and distributions[0].metadata["Name"] == "torchao"
            and distributions[0].version == "0.12.0", "Venv must add exactly one distribution")
    return {"name": "torchao", "version": "0.12.0", "wheel_sha256": sha(wheel),
            "original_files_verified": len(rows), "installed_file_count": len(actual),
            "original_files_manifest_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "installer_generated_files": sorted(generated | {record_name}),
            "complete_installed_record_verified": True, "extra_distribution_count": 0}


def recheck_foundation(path, lock, prep, native):
    proof = native.validate_foundation(path, lock)
    result = prep.read_json(path)
    validation = prep.read_json(path.parent / "NEUTTS-APT-PYTHON-VALIDATION.json")
    require(validation["apt_provenance"]["status"] == "passed", "Foundation provenance is incomplete")
    rows = validation["apt_provenance"]["installed_files"]
    require(rows, "Foundation selected file ledger is empty")
    for row in rows:
        file = Path(row["path"])
        require(file.resolve().is_relative_to(PREFIX)
                and file.stat().st_size == row["bytes"] and sha(file) == row["sha256"],
                "APT Python or scientific metadata changed after foundation: " + str(file))
    proof["current_selected_apt_files_rechecked"] = len(rows)
    proof["current_selected_apt_manifest_sha256"] = validation["apt_provenance"]["installed_file_manifest_sha256"]
    return proof, result


def bounded(command, out, name, timeout, env, cwd):
    files = {channel: out / (name + "." + channel + ".log") for channel in ("stdout", "stderr")}
    timed_out = False
    with files["stdout"].open("xb") as stdout, files["stderr"].open("xb") as stderr:
        try:
            code = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=timeout,
                                  env=env, cwd=cwd, check=False).returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
        except OSError as exc:
            stderr.write((type(exc).__name__ + ": " + str(exc) + "\n").encode())
            code = 127
    return {"command": command, "exit_code": code, "timed_out": timed_out,
            "logs": {key: {"path": value.name, "bytes": value.stat().st_size,
                           "sha256": sha(value), "truncated": False} for key, value in files.items()}}


def clean_environment(work):
    env = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                 "LD_PRELOAD", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS",
                 "CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS"):
        env.pop(name, None)
    env.update({"PATH": str(PREFIX / "bin"), "LD_LIBRARY_PATH": str(PREFIX / "lib"),
                "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_NO_CACHE_DIR": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2", "TMPDIR": str(work),
                "TORCHINDUCTOR_CACHE_DIR": str(work / "inductor-cache"),
                "TRITON_CACHE_DIR": str(work / "triton-cache"), "XDG_CACHE_HOME": str(work / "cache")})
    return env


def runtime_case(args, lock, wheel, prep, native, core):
    report = {"schema_version": 1, "status": "failed", "cases": [],
              "model_downloaded": False, "complete_engine_tested": False,
              "cuda_operations_tested": False, "audio_tested": False}
    try:
        report["runtime"] = native.native_runtime()
        require(Path(sys.prefix).resolve() != PREFIX
                and Path(sys.prefix).resolve().is_relative_to(PREFIX / "tmp"),
                "Actual runtime must use a fresh isolated venv")
        report["foundation"], foundation = recheck_foundation(args.foundation_receipt, lock, prep, native)
        site = Path(sysconfig.get_path("purelib"))
        report["installed_wheel"] = verify_installed(wheel, site, lock, prep)
        from pip._vendor.packaging.requirements import Requirement
        distribution = importlib.metadata.distribution("torchao")
        active = [value for value in distribution.requires or []
                  if Requirement(value).marker is None or Requirement(value).marker.evaluate({"extra": ""})]
        require(active == [], "This gate covers the frozen wheel with zero base requirements")

        import torch
        import torchao
        from torchao.dtypes import NF4Tensor, to_nf4
        from torchao.dtypes.nf4tensor import linear_nf4
        require(torch.__version__.split("+", 1)[0] == lock["foundation"]["torch"]
                and torchao.__version__ == "0.12.0", "Actual Torch/TorchAO versions differ")
        require(Path(torchao.__file__).resolve() == site / "torchao/__init__.py",
                "TorchAO import came from outside the verified installed wheel")
        torch_child = prep.read_json(args.foundation_receipt.parent / "neutts-torch.json")
        torch_identity = core.module_identity(torch)
        require(torch_identity in torch_child["behavior"]["modules"],
                "Current Torch Python module differs from the passed foundation")
        report["cases"].append({"case": "real_package_import", "status": "passed",
                                "torch": torch_identity, "torchao_file": torchao.__file__,
                                "torchao_sha256": sha(Path(torchao.__file__)),
                                "active_base_requirements": active})

        torch.set_num_threads(2)
        values = weight_values()
        weight = torch.tensor(values, dtype=torch.float32, device="cpu").reshape(128, 128)
        quantized = to_nf4(weight)
        require(isinstance(quantized, NF4Tensor) and quantized.device.type == "cpu"
                and tuple(quantized.shape) == (128, 128) and quantized.dtype == torch.float32
                and quantized.block_size == 64 and quantized.n_blocks == 256
                and quantized.scaler_block_size == 256, "Actual default NF4 tensor metadata differs")
        for attr in ("quantized_data", "quantized_scalers", "quantization_factor", "scaler_mean", "nf4"):
            require(getattr(quantized, attr).device.type == "cpu", "NF4 stored tensor left the CPU")
        require(quantized.quantized_data.dtype == torch.uint8
                and quantized.quantized_scalers.dtype == torch.int8, "Packed NF4 storage dtype differs")
        packed = quantized.quantized_data.flatten().tolist()
        require(packed == reference_packed(values), "Actual packed NF4 bytes differ from scalar nearest-code oracle")
        report["cases"].append({"case": "nf4_default_quantization", "status": "passed",
                                "shape": [128, 128], "weight_values": len(values), "packed_bytes": len(packed),
                                "packed_sha256": hashlib.sha256(bytes(packed)).hexdigest(),
                                "block_size": 64, "scaler_block_size": 256,
                                "independent_packed_byte_oracle": True})
        independent = reference_dequantized(
            packed, quantized.quantized_scalers.flatten().tolist(),
            quantized.quantization_factor.flatten().tolist(), float(quantized.scaler_mean))
        reference = torch.tensor(independent, dtype=torch.float32, device="cpu").reshape(128, 128)
        actual = quantized.to(torch.float32)
        require(type(actual) is torch.Tensor and tuple(actual.shape) == (128, 128)
                and bool(torch.isfinite(actual).all()), "NF4 dequantization returned invalid ordinary weights")
        dequant_error = float(torch.max(torch.abs(actual - reference)))
        require(dequant_error <= 0.000001, "NF4 dequantization differs from independent stored-byte/scaler oracle")
        relative_error = float(torch.linalg.vector_norm(actual - weight) / torch.linalg.vector_norm(weight))
        require(math.isfinite(relative_error) and 0 < relative_error < lock["operation"]["normalized_l2_error_max"],
                "NF4 reconstruction error exceeds the reviewed synthetic-fixture bound")
        report["cases"].append({"case": "independent_dequantization", "status": "passed",
                                "maximum_absolute_error": dequant_error,
                                "normalized_l2_error_to_original": relative_error,
                                "normalized_l2_error_bound": lock["operation"]["normalized_l2_error_max"]})

        inputs = torch.tensor([[math.sin((row * 128 + col) * 0.071) for col in range(128)]
                               for row in range(3)], dtype=torch.float32, device="cpu", requires_grad=True)
        output = linear_nf4(inputs, quantized)
        expected = torch.nn.functional.linear(inputs.detach(), reference)
        require(tuple(output.shape) == (3, 128) and bool(torch.isfinite(output).all())
                and torch.allclose(output, expected, rtol=lock["operation"]["forward_rtol"],
                                   atol=lock["operation"]["forward_atol"]),
                "Actual NF4 linear forward differs from independently dequantized dense multiplication")
        report["cases"].append({"case": "linear_forward", "status": "passed",
                                "output_shape": list(output.shape),
                                "maximum_absolute_error": float(torch.max(torch.abs(output.detach() - expected))),
                                "public_operation": "torchao.dtypes.nf4tensor.linear_nf4"})
        grad_output = torch.tensor([[math.cos((row * 128 + col) * 0.037) for col in range(128)]
                                    for row in range(3)], dtype=torch.float32, device="cpu")
        output.backward(grad_output)
        expected_gradient = grad_output @ reference
        require(inputs.grad is not None and bool(torch.isfinite(inputs.grad).all())
                and torch.allclose(inputs.grad, expected_gradient, rtol=lock["operation"]["gradient_rtol"],
                                   atol=lock["operation"]["gradient_atol"]),
                "Actual NF4 input gradient differs from dense arithmetic oracle")
        report["cases"].append({"case": "input_gradient", "status": "passed",
                                "maximum_absolute_error": float(torch.max(torch.abs(inputs.grad - expected_gradient))),
                                "weight_training_proved": False})
        require(tuple(row["case"] for row in report["cases"]) == CASE_NAMES,
                "Missing actual TorchAO component case")
        report["mapped_libraries"] = core.libraries()
        current = {row["path"]: row for row in report["mapped_libraries"]}
        critical = [row for row in torch_child["mapped_libraries"] if "/site-packages/torch/" in row["path"]]
        require(critical and all(row["path"] in current
                and current[row["path"]]["sha256"] == row["sha256"] for row in critical),
                "A current Torch native library differs from the actual passed foundation")
        report["foundation_torch_libraries_rechecked"] = len(critical)
        report["library_provenance_scope"] = (
            "All currently mapped ELF identities are recorded. The actual Torch libraries are required "
            "to match the seven-case foundation; additional Python/system libraries are observations.")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
        try:
            report["mapped_libraries"] = core.libraries()
        except Exception as secondary:
            report["library_evidence_error"] = str(secondary)
    prep.save_new(args.out / "TORCHAO-RUNTIME-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def run(args, lock, wheel, prep, native, core):
    require(not args.out.exists() and not args.out.is_symlink(), "Fresh component output is required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "stage": "preflight",
              "scope": "One exact TorchAO wheel, real import and CPU NF4 operations over native APT foundation",
              "lock_sha256": prep.LOCK_SHA256, "commands": [],
              "model_downloaded": False, "complete_engine_tested": False,
              "candidate_modified": False, "production_admission_changed": False, "release_output": False}
    try:
        report["runtime"] = native.native_runtime()
        require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the actual APT base Python")
        report["foundation"], _ = recheck_foundation(args.foundation_receipt, lock, prep, native)
        before = subprocess.check_output([str(PREFIX / "bin/dpkg-query"), "-W",
            "-f", r"${Package}\t${Version}\t${Architecture}\n"], timeout=20)
        with tempfile.TemporaryDirectory(prefix="torchao-component-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            env = clean_environment(work)
            venv = work / "runtime"
            python = venv / "bin/python"
            commands = [
                ("create-venv", [sys.executable, "-I", "-B", "-m", "venv", "--system-site-packages",
                                 "--without-pip", str(venv)], 90),
                ("install-exact-wheel", [sys.executable, "-I", "-B", "-m", "pip", "--python", str(python),
                    "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir",
                    "--only-binary=:all:", "--report", str(args.out / "TORCHAO-PIP-INSTALL.json"), str(wheel)], 120),
                ("actual-native-runtime", [str(python), "-I", "-B", str(Path(__file__).resolve()),
                    "--phase", "runtime", "--inputs", str(args.inputs), "--foundation-receipt",
                    str(args.foundation_receipt), "--out", str(args.out)], 180),
            ]
            for name, command, timeout in commands:
                report["stage"] = name
                row = bounded(command, args.out, name, timeout, env, work)
                report["commands"].append(row)
                require(row["exit_code"] == 0 and not row["timed_out"], "Component command failed: " + name)
            result = prep.read_json(args.out / "TORCHAO-RUNTIME-RESULT.json", 8_000_000)
            require(result.get("status") == "passed" and len(result.get("cases", [])) == len(CASE_NAMES)
                    and tuple(row.get("case") for row in result["cases"]) == CASE_NAMES
                    and all(row.get("status") == "passed" for row in result["cases"]),
                    "Actual complete TorchAO runtime receipt did not pass")
            after = subprocess.check_output([str(PREFIX / "bin/dpkg-query"), "-W",
                "-f", r"${Package}\t${Version}\t${Architecture}\n"], timeout=20)
            require(before == after, "The one-wheel gate changed the installed APT package set")
            report["apt_package_set_unchanged_sha256"] = hashlib.sha256(after).hexdigest()
            report["runtime_receipt"] = {"path": "TORCHAO-RUNTIME-RESULT.json",
                                         "sha256": sha(args.out / "TORCHAO-RUNTIME-RESULT.json")}
            report["status"], report["stage"] = "passed", "complete"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        runtime = args.out / "TORCHAO-RUNTIME-RESULT.json"
        if runtime.is_file():
            report["runtime_receipt"] = {"path": runtime.name, "sha256": sha(runtime)}
        prep.save_new(args.out / "TORCHAO-COMPONENT-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("run", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--foundation-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    prep = preparer()
    lock, wheel, _ = prep.verify_inputs(args.inputs)
    native = prep.helper("compatibility_probe_neutts_native.py", lock)
    core = prep.helper("compatibility_probe_neutts.py", lock)
    return (runtime_case if args.phase == "runtime" else run)(args, lock, wheel, prep, native, core)


if __name__ == "__main__":
    raise SystemExit(main())
