#!/usr/bin/env python3
"""Prepare the unchanged frozen XXHash 4.0.1 Android wheel; no installation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time
import urllib.request
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_RELATIVE = "audit/neutts-xxhash-preparation-20261020"
AUDIT_DIR = SCRIPT_DIR.parent / AUDIT_RELATIVE
FIXTURES_SHA256 = "84d56689161666a091f101152c8e533a719f37aa9fb30dab590ade4565e7e7d9"
LOCK_NAME = "neutts_public_wheels_lock.json"
LOCK_SHA256 = "a9e8e228dc9157f3b9613e970f7de97fc0656e0124ef5684da4ef4c185286e3b"
WITNESS_NAME = "neutts_runtime_closure_design.json"
WITNESS_SHA256 = "d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68"
RECEIPT_NAME = "XXHASH-PREPARED-INPUTS.json"
FOUNDATION = {
    "apt_metadata_ledger_sha256": "2031c8a6915915ffffb980b268ad5107d42a186682cb2ca7009d803fe2abe200",
    "helpers": {
        "compatibility_probe_neutts.py": "170d2381b6c73863b18727ccda5c03718871df416a73e8e796bf2443c3d9bcbd",
        "compatibility_probe_neutts_native.py": "862efa59b3c967fd360e1d9ce86d4ebadc5bbf9a4b0a3023f2990a66da130c74",
        "prepare_neutts_core_python.py": "b78a252eb1c3d1872b64f7ffe5e16bf16c161057b6579732a7af966317e0b19e",
    },
    "image": "termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303",
    "python": "3.14.6",
}


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected a regular owned file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, limit=1_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            "Missing, nonregular or oversized JSON input")
    return json.loads(path.read_bytes())


def save_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def load_lock():
    require(sha(SCRIPT_DIR / LOCK_NAME) == LOCK_SHA256, "Original public wheel lock changed")
    require(sha(SCRIPT_DIR / WITNESS_NAME) == WITNESS_SHA256, "Original closure witness changed")
    require(sha(AUDIT_DIR / "FIXTURES.json") == FIXTURES_SHA256, "Primary fixture manifest changed")
    fixtures = read_json(AUDIT_DIR / "FIXTURES.json")
    for row in fixtures["source_files"]:
        path = AUDIT_DIR / row["path"]
        require(path.stat().st_size == row["bytes"] and sha(path) == row["sha256"],
                "Primary fixed-vector source changed: " + row["path"])
    rows = [p for p in read_json(SCRIPT_DIR / LOCK_NAME)["packages"] if p["name"] == "xxhash"]
    require(len(rows) == 1 and rows[0] == fixtures["original_wheel"],
            "XXHash differs from the original frozen distribution")
    original = rows[0]
    require(original["version"] == "4.0.1" and original["requires_dist"] == []
            and len(original["native_elf_members"]) == 1, "Unexpected XXHash package scope")
    package = {key: copy.deepcopy(original[key]) for key in
               ("name", "version", "requires_python", "artifact", "wheel")}
    # The original public witness hashes newline-joined names without a final
    # newline; the unchanged core verifier includes one. Verify both encodings.
    package["wheel"]["members_sha256"] = "7163e586642b22c206cfb56e180ae1e17bd41a4d14b143b5afcd0d743138ef30"
    package["base_requires_dist"] = []
    package["native_members"] = [
        {"member": row["path"], "bytes": row["bytes"], "sha256": row["sha256"]}
        for row in original["native_elf_members"]
    ]
    return {"foundation": copy.deepcopy(FOUNDATION), "package": package,
            "original_package": original, "primary_sources": fixtures["source_files"],
            "upstream_commit": fixtures["upstream_commit"]}


def helper(name, lock):
    path = SCRIPT_DIR / name
    require(sha(path) == lock["foundation"]["helpers"][name],
            "Reviewed foundation helper changed: " + name)
    spec = importlib.util.spec_from_file_location("_xxhash_" + path.stem, path)
    require(spec is not None and spec.loader is not None, "Cannot load reviewed helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_wheel(path, lock):
    proof = helper("prepare_neutts_core_python.py", lock).verify_wheel(path, lock["package"])
    native = lock["original_package"]["native_elf_members"][0]
    with zipfile.ZipFile(path) as archive:
        original_names = "\n".join(sorted(archive.namelist())).encode()
        require(hashlib.sha256(original_names).hexdigest()
                == lock["original_package"]["wheel"]["members_sha256"],
                "Original public member inventory differs")
        for entry in archive.infolist():
            if not entry.is_dir():
                require(".data/" not in entry.filename
                        and not entry.filename.endswith((".pth", ".pyc")),
                        "Unexpected install scheme or executable import hook")
                if archive.read(entry).startswith(b"\x7fELF"):
                    require(entry.filename == native["path"], "Unowned ELF member")
        raw = archive.read(native["path"])
        require(raw[:6] == b"\x7fELF\x02\x01"
                and struct.unpack_from("<HH", raw, 16) == (3, 183),
                "Original extension must be a little-endian AArch64 shared ELF")
    proof["original_wheel_metadata"] = lock["original_package"]["wheel"]
    proof["member_name_digest_adapter"] = "Original no-final-newline and core final-newline encodings both verified"
    proof["original_elf_provenance"] = native
    proof["elf_dynamic_provenance"] = (
        "Frozen original witness; the complete unchanged ELF is SHA-256 verified")
    return proof


def input_receipt(lock, proof):
    return {
        "schema_version": 1, "status": "verified-inputs",
        "public_wheel_lock_sha256": LOCK_SHA256, "closure_witness_sha256": WITNESS_SHA256,
        "primary_fixture_manifest_sha256": FIXTURES_SHA256,
        "upstream_commit": lock["upstream_commit"], "primary_sources": lock["primary_sources"],
        "wheel": proof, "original_archive_and_metadata_unchanged": True,
        "installed": False, "native_operations_proved": False, "model_downloaded": False,
        "production_admission_changed": False, "release_output": False,
    }


def verify_inputs(inputs):
    lock = load_lock()
    require(inputs.is_dir() and inputs.resolve() == inputs.absolute(),
            "Expected an owned prepared input directory")
    wheel = inputs / lock["package"]["artifact"]["filename"]
    expected = {wheel.name, RECEIPT_NAME}
    paths = list(inputs.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in paths)
            and {p.name for p in paths} == expected,
            "Prepared directory must contain exactly the original wheel and receipt")
    proof = verify_wheel(wheel, lock)
    require(read_json(inputs / RECEIPT_NAME) == input_receipt(lock, proof),
            "Prepared input receipt differs from the verified original wheel")
    return lock, wheel, proof


def prepare(out, wheel=None):
    lock = load_lock()
    require(not out.exists() and not out.is_symlink(), "Use a new input directory")
    if wheel is not None:
        verify_wheel(wheel, lock)
    out.mkdir(parents=True)
    destination = out / lock["package"]["artifact"]["filename"]
    if wheel is None:
        core = helper("prepare_neutts_core_python.py", lock)
        core.download_file(lock["package"]["artifact"], destination,
                           urllib.request.build_opener(core.NoRedirect()), time.monotonic() + 120)
    else:
        with destination.open("xb") as stream:
            stream.write(wheel.read_bytes())
    proof = verify_wheel(destination, lock)
    receipt = input_receipt(lock, proof)
    save_new(out / RECEIPT_NAME, receipt)
    verify_inputs(out)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, help="Optional exact original Android wheel")
    args = parser.parse_args(argv)
    receipt = prepare(args.out, args.wheel)
    print(json.dumps({"status": receipt["status"], "wheel_sha256": receipt["wheel"]["artifact"]["sha256"],
                      "native_operations_proved": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
