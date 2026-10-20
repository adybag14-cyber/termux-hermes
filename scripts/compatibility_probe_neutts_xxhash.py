#!/usr/bin/env python3
"""Actual native Bionic XXHash operations in a fresh, one-wheel venv."""
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
import subprocess
import sys
import sysconfig
import tempfile
import traceback
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX = Path("/data/data/com.termux/files/usr")
PREPARER_SHA256 = "9ec0a426ef3c58ac258fa759ee98c3c349cb721b928c5420bc1544b0df44f1b2"
CASE_NAMES = ("real_package_import", "xxh32_fixed_vectors", "xxh64_fixed_vectors",
              "xxh3_64_fixed_vectors", "xxh3_128_fixed_vectors",
              "streaming_seed_copy_reset", "mapped_native_provenance")
# Original v4.0.1 upstream tests at e2c1bcf1e1d86c4e3d43e4d412dccb521498ea88.
# Each row is (seed bit width, digest byte width, fixed results for b"a" at
# seeds 0, 1 and unsigned maximum). Sources and original BSD license are
# preserved in audit/neutts-xxhash-preparation-20261020/upstream.
FIXED_VECTORS = {
    "xxh32": (32, 4, (1426945110, 4111757423, 3443684653)),
    "xxh64": (64, 8, (15154266338359012955, 16051599287423682246, 6972758980737027682)),
    "xxh3_64": (64, 8, (16629034431890738719, 15201566949650179872, 4875116479388997462)),
    "xxh3_128": (64, 16, (225219434562328483135862406050043285023,
                        337425133163118381928709500770786453280,
                        198297796855923085494266857744987477846)),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected a regular owned file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preparer():
    path = SCRIPT_DIR / "prepare_neutts_xxhash.py"
    require(sha(path) == PREPARER_SHA256, "Reviewed XXHash preparer changed")
    spec = importlib.util.spec_from_file_location("_xxhash_component_preparer", path)
    require(spec is not None and spec.loader is not None, "Cannot load exact input verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_installed(wheel, site, lock, prep):
    prep.verify_wheel(wheel, lock)
    require(site.is_dir() and site.resolve() == site.absolute(), "Unexpected venv site directory")
    info = "xxhash-4.0.1.dist-info/"
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
            require(target.read_bytes() == raw, "Installed XXHash wheel bytes changed: " + name)
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
    require(len(distributions) == 1 and distributions[0].metadata["Name"] == "xxhash"
            and distributions[0].version == "4.0.1", "Venv must add exactly one distribution")
    return {"name": "xxhash", "version": "4.0.1", "wheel_sha256": sha(wheel),
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
                "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(work),
                "XDG_CACHE_HOME": str(work / "cache")})
    return env


def run(args, lock, wheel, prep, native, core):
    require(not args.out.exists() and not args.out.is_symlink(), "Fresh component output is required")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "stage": "preflight",
              "scope": "One exact XXHash wheel, real import and native hash operations over native APT foundation",
              "lock_sha256": prep.LOCK_SHA256, "commands": [],
              "model_downloaded": False, "complete_engine_tested": False,
              "candidate_modified": False, "production_admission_changed": False, "release_output": False}
    try:
        report["runtime"] = native.native_runtime()
        require(Path(sys.prefix).resolve() == PREFIX, "Entry must use the actual APT base Python")
        report["foundation"], _ = recheck_foundation(args.foundation_receipt, lock, prep, native)
        before = subprocess.check_output([str(PREFIX / "bin/dpkg-query"), "-W",
            "-f", r"${Package}\t${Version}\t${Architecture}\n"], timeout=20)
        with tempfile.TemporaryDirectory(prefix="xxhash-component-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            env = clean_environment(work)
            venv = work / "runtime"
            python = venv / "bin/python"
            commands = [
                ("create-venv", [sys.executable, "-I", "-B", "-m", "venv", "--without-pip", str(venv)], 90),
                ("install-exact-wheel", [sys.executable, "-I", "-B", "-m", "pip", "--python", str(python),
                    "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir",
                    "--only-binary=:all:", "--report", str(args.out / "XXHASH-PIP-INSTALL.json"), str(wheel)], 120),
                ("actual-native-runtime", [str(python), "-I", "-B", str(Path(__file__).resolve()),
                    "--phase", "runtime", "--inputs", str(args.inputs), "--foundation-receipt",
                    str(args.foundation_receipt), "--out", str(args.out)], 180),
            ]
            for name, command, timeout in commands:
                report["stage"] = name
                row = bounded(command, args.out, name, timeout, env, work)
                report["commands"].append(row)
                require(row["exit_code"] == 0 and not row["timed_out"], "Component command failed: " + name)
            result = prep.read_json(args.out / "XXHASH-RUNTIME-RESULT.json", 8_000_000)
            require(result.get("status") == "passed" and len(result.get("cases", [])) == len(CASE_NAMES)
                    and tuple(row.get("case") for row in result["cases"]) == CASE_NAMES
                    and all(row.get("status") == "passed" for row in result["cases"]),
                    "Actual complete XXHash runtime receipt did not pass")
            after = subprocess.check_output([str(PREFIX / "bin/dpkg-query"), "-W",
                "-f", r"${Package}\t${Version}\t${Architecture}\n"], timeout=20)
            require(before == after, "The one-wheel gate changed the installed APT package set")
            report["apt_package_set_unchanged_sha256"] = hashlib.sha256(after).hexdigest()
            report["runtime_receipt"] = {"path": "XXHASH-RUNTIME-RESULT.json",
                                         "sha256": sha(args.out / "XXHASH-RUNTIME-RESULT.json")}
            report["foundation_after"], _ = recheck_foundation(args.foundation_receipt, lock, prep, native)
            report["status"], report["stage"] = "passed", "complete"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        runtime = args.out / "XXHASH-RUNTIME-RESULT.json"
        if runtime.is_file():
            report["runtime_receipt"] = {"path": runtime.name, "sha256": sha(runtime)}
        prep.save_new(args.out / "XXHASH-COMPONENT-RESULT.json", report)
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

def check_digests(value, expected, width, context):
    require(value.intdigest() == expected
            and value.digest() == expected.to_bytes(width, "big")
            and value.hexdigest() == format(expected, "0" + str(width * 2) + "x"),
            "Fixed vector or digest representation differs: " + context)


def hash_operations(module):
    cases = []
    for name, (bits, width, expected_values) in FIXED_VECTORS.items():
        constructor = getattr(module, name)
        rows = []
        for seed, expected in zip((0, 1, 2**bits - 1), expected_values):
            label = name + ":" + str(seed)
            value = constructor(b"a", seed=seed)
            require(value.digest_size == width and value.seed == seed,
                    "Digest width or retained seed differs: " + label)
            check_digests(value, expected, width, label)
            for suffix, correct in (("intdigest", expected), ("digest", expected.to_bytes(width, "big")),
                                    ("hexdigest", format(expected, "0" + str(width * 2) + "x"))):
                require(getattr(module, name + "_" + suffix)(b"a", seed=seed) == correct,
                        "One-shot fixed vector differs: " + label + ":" + suffix)
            stream = constructor(seed=seed)
            stream.update(b"")
            stream.update(memoryview(b"a"))
            check_digests(stream, expected, width, label + ":stream")
            copied = stream.copy()
            stream.update(b"changed")
            check_digests(copied, expected, width, label + ":copy-isolation")
            copied.reset()
            copied.update(b"a")
            check_digests(copied, expected, width, label + ":reset-retains-seed")
            wrapped = constructor(b"a", seed=seed + 2**bits)
            check_digests(wrapped, expected, width, label + ":unsigned-seed-wrap")
            rows.append({"data_hex": "61", "seed": seed, "expected_integer": expected,
                         "actual_hex": value.hexdigest(), "digest_bytes": width})
        cases.append({"case": name + "_fixed_vectors", "status": "passed", "vectors": rows,
                      "oracle": "Original upstream test literals, not extension-generated values"})

    # This longer deterministic input exercises block and >64 KiB paths. It is
    # deliberately reported as API consistency, separately from fixed vectors.
    data = bytes(range(256)) * 257 + b"hermes"
    streaming_rows = []
    for name, (bits, width, _) in FIXED_VECTORS.items():
        constructor = getattr(module, name)
        for seed in (0, 1, 2**bits - 1):
            whole = constructor(data, seed=seed)
            stream = constructor(seed=seed)
            position = 0
            for count in (1, 3, 31, 64, 127, 241, 1024, 16384, 32768, len(data)):
                chunk = data[position:position + count]
                stream.update(memoryview(chunk))
                position += len(chunk)
            require(position == len(data) and stream.digest() == whole.digest()
                    and getattr(module, name + "_digest")(data, seed=seed) == whole.digest(),
                    "Long streaming/one-shot consistency failed: " + name)
            prefix = constructor(data[:1025], seed=seed)
            clone = prefix.copy()
            prefix_digest = prefix.digest()
            clone.update(data[1025:])
            require(prefix.digest() == prefix_digest and clone.digest() == whole.digest(),
                    "Long copy state is shared or incomplete: " + name)
            prefix.reset()
            require(prefix.seed == seed, "Reset changed the original seed: " + name)
            prefix.update(data)
            require(prefix.digest() == whole.digest(), "Long reset failed: " + name)
            streaming_rows.append({"algorithm": name, "seed": seed, "actual_hex": whole.hexdigest()})
        try:
            constructor("str must be encoded")
        except TypeError:
            pass
        else:
            raise RuntimeError("XXHash 4.0.1 unexpectedly accepted unencoded str: " + name)
    require(module.xxh128 is module.xxh3_128
            and module.xxh128_digest is module.xxh3_128_digest
            and module.xxh128_hexdigest is module.xxh3_128_hexdigest
            and module.xxh128_intdigest is module.xxh3_128_intdigest,
            "Original XXH128 aliases changed")
    cases.append({"case": "streaming_seed_copy_reset", "status": "passed",
                  "input_bytes": len(data), "input_sha256": hashlib.sha256(data).hexdigest(),
                  "checks": streaming_rows, "oracle": "API consistency; independent fixed vectors are separate",
                  "unencoded_strings_rejected": True, "xxh128_aliases_preserved": True})
    return cases


def library_provenance(libraries, foundation_libraries, extension, lock):
    member = lock["original_package"]["native_elf_members"][0]
    mapped = [row for row in libraries if "/xxhash/" in row["path"]]
    require(len(mapped) == 1 and mapped[0]["path"] == str(extension)
            and mapped[0]["sha256"] == member["sha256"]
            and mapped[0]["bytes"] == member["bytes"],
            "Mapped XXHash extension differs from the original installed ELF")
    baseline = {row["path"]: row for row in foundation_libraries}
    dependencies = []
    for name in member["elf"]["needed"]:
        matches = [row for row in libraries if Path(row["path"]).name == name]
        require(len(matches) == 1, "Missing or ambiguous actual XXHash dependency: " + name)
        row = matches[0]
        previous = baseline.get(row["path"], {})
        require(row["sha256"] == previous.get("sha256")
                and row["bytes"] == previous.get("bytes")
                and bool(row.get("dpkg_owners"))
                and row["dpkg_owners"] == previous.get("dpkg_owners"),
                "Actual XXHash dependency differs from the passed foundation: " + name)
        dependencies.append(row)
    return {"case": "mapped_native_provenance", "status": "passed", "extension": mapped[0],
            "original_dynamic_dependencies": member["elf"]["needed"],
            "dependencies_rechecked_against_passed_foundation": dependencies,
            "other_mapped_libraries": "Recorded observations, not additional dependency admission"}


def runtime_case(args, lock, wheel, prep, native, core):
    report = {"schema_version": 1, "status": "failed", "cases": [],
              "model_downloaded": False, "complete_engine_tested": False,
              "production_admission_changed": False, "release_output": False}
    try:
        report["runtime"] = native.native_runtime()
        require(Path(sys.prefix).resolve() != PREFIX
                and Path(sys.prefix).resolve().is_relative_to(PREFIX / "tmp"),
                "Actual runtime must use a fresh isolated venv")
        require(sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1,
                "Runtime requires isolated imports without bytecode writes")
        report["foundation"], foundation = recheck_foundation(args.foundation_receipt, lock, prep, native)
        site = Path(sysconfig.get_path("purelib"))
        require(site == Path(sys.prefix) / "lib/python3.14/site-packages",
                "Unexpected one-wheel venv import location")
        config = (Path(sys.prefix) / "pyvenv.cfg").read_text()
        require("include-system-site-packages = false" in config,
                "XXHash must not inherit system site-packages")
        report["installed_wheel"] = verify_installed(wheel, site, lock, prep)

        import xxhash
        import xxhash._xxhash as extension_module
        member = lock["original_package"]["native_elf_members"][0]
        extension = site / member["path"]
        require(Path(xxhash.__file__).resolve() == site / "xxhash/__init__.py"
                and Path(extension_module.__file__).resolve() == extension
                and xxhash.VERSION == "4.0.1" and xxhash.XXHASH_VERSION == "0.8.3",
                "Actual package/backend or import origin differs from the unchanged wheel")
        distribution = importlib.metadata.distribution("xxhash")
        require(distribution.version == "4.0.1" and (distribution.requires or []) == [],
                "Original zero-dependency metadata changed")
        report["cases"].append({"case": "real_package_import", "status": "passed",
                                "package_version": xxhash.VERSION, "backend_version": xxhash.XXHASH_VERSION,
                                "initializer": str(Path(xxhash.__file__)),
                                "initializer_sha256": sha(Path(xxhash.__file__)),
                                "extension": core.elf(extension), "declared_requirements": []})
        report["cases"].extend(hash_operations(xxhash))
        # The full child receipt was already digest-checked by validate_foundation.
        previous = prep.read_json(args.foundation_receipt.parent / "neutts-python_dependencies.json")
        maps = Path("/proc/self/maps").read_text()
        require(not any("/xxhash/" in line and " (deleted)" in line for line in maps.splitlines()),
                "Deleted XXHash native mapping")
        report["mapped_libraries"] = core.libraries()
        report["cases"].append(library_provenance(
            report["mapped_libraries"], previous["mapped_libraries"], extension, lock))
        require(tuple(row["case"] for row in report["cases"]) == CASE_NAMES,
                "Missing actual XXHash operation or provenance case")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    prep.save_new(args.out / "XXHASH-RUNTIME-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
