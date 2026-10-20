#!/usr/bin/env python3
"""Verify the complete original 25-node native Tokenizers subset without engine admission."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX = Path("/data/data/com.termux/files/usr")
SOURCE_PINS = {
    "prepare_neutts_tokenizers_runtime.py": "a8a584da44e789ec7b215551986694182798f895c12e1934ad24c0fed5f7b3f1",
    "compatibility_probe_neutts_nonrust.py": "11d0dc5ed34dd45c855bffbba51c02eecf74ce8c5a5dd38cb1483e57f1d14e4b",
    "compatibility_probe_phonemizer.py": "6387ecead23b7777e879588d7e76bd4c8d462de5574de1d77092053efc596211",
    "validate_neutts_apt_python.py": "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29",
    "neutts_rust_operations.py": "168382b4db418f71879d5d65979a1d9efc59140eac175231c411c312d6e37123",
    "neutts_runtime_elf.py": "73d00842dfe5c6f46712d6171007c3cb2735ca68ba678515c15ace01af500b11",
    "neutts_tokenizers_operations.py": "ba742d7dd5fdc4ceba8c5dc14fb17542b689445aa206f70f8faa79ac0ceeca2b",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "Expected original regular file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, maximum=4_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum,
            "Expected bounded original JSON")
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def module(filename):
    path = SCRIPT_DIR / filename
    require(sha(path) == SOURCE_PINS[filename], "Reviewed support source changed: " + filename)
    spec = importlib.util.spec_from_file_location("_tokenizers_" + path.stem, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def support():
    prep = module("prepare_neutts_tokenizers_runtime.py")
    return (prep, prep.helper(), module("compatibility_probe_neutts_nonrust.py"),
            module("compatibility_probe_phonemizer.py"), module("validate_neutts_apt_python.py"),
            module("neutts_runtime_elf.py"))


def closure(lock):
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name

    actual = default_environment()
    require(all(actual[key] == value for key, value in lock["environment"].items() if key != "extra"),
            "Actual runtime marker environment differs from original Android selection")
    packages = {p["name"]: p for p in lock["packages"]}
    versions = {name: p["version"] for name, p in packages.items()}
    def key(source, requirement):
        parsed = Requirement(requirement)
        require(parsed.url is None, "Unreviewed direct-URL dependency")
        return source, canonicalize_name(parsed.name), str(parsed.specifier), tuple(sorted(parsed.extras)), str(parsed.marker or "")
    expected = {key(edge["from"], edge["requirement"]) for edge in lock["edges"]}
    require(len(expected) == 29, "Original edge inventory is ambiguous")
    observed, rows = set(), []
    for name, package in packages.items():
        require(SpecifierSet(package["requires_python"]).contains(actual["python_full_version"]),
                "Original interpreter bound excludes actual runtime: " + name)
        extras = ["", *package["active_extras"]]
        for value in package["requires_dist"]:
            req = Requirement(value)
            if req.marker and not any(req.marker.evaluate({**actual, "extra": extra}) for extra in extras):
                continue
            target = canonicalize_name(req.name)
            require(req.url is None and target in versions and req.specifier.contains(versions[target]),
                    "Missing or incompatible original runtime requirement: " + name + " -> " + value)
            require(set(req.extras) <= set(packages[target]["active_extras"]),
                    "Required downstream extra is not selected")
            identity = key(name, value)
            require(identity not in observed, "Duplicate active original runtime requirement")
            observed.add(identity)
            rows.append({"from": name, "to": target, "requirement": value})
    require(observed == expected, "Actual active requirements differ from the reviewed 29 edges")
    reached = set(lock["roots"])
    while True:
        expanded = reached | {edge["to"] for edge in rows if edge["from"] in reached}
        if expanded == reached:
            break
        reached = expanded
    require(reached == set(lock["names"]) and len(reached) == 25, "Complete selected runtime is not exactly 25 nodes")
    return {"status": "passed", "node_count": 25, "edge_count": 29,
            "environment": actual, "active_edges": sorted(rows, key=lambda row: (row["from"], row["to"])),
            "original_metadata_modified": False}


def validate_image(path, lock):
    inputs = read_json(path)
    require(inputs["schema_version"] == 1 and inputs["native_image"] == lock["platform_runtime"]["native_image"],
            "Host-selected native image differs")
    require(inputs.get("production_admission_changed") is False and inputs.get("release_output") is False,
            "Source-image preparation boundary differs")
    filenames = set(SOURCE_PINS) | {
        "compatibility_probe_neutts_tokenizers_runtime.py",
        "compatibility_probe_neutts_tokenizers_runtime.sh", "neutts_tokenizers_runtime_lock.json"}
    for filename in filenames:
        name = "scripts/" + filename
        require(inputs["inputs"].get(name) == sha(SCRIPT_DIR / filename), "Executing source differs from host ledger")
    inspected = read_json(path.parent / "TOKENIZERS-SOURCE-IMAGE.json")
    require(len(inspected) == 1, "Ambiguous actual Docker image")
    image = inspected[0]
    require(image["Architecture"] == "arm64" and image["Os"] == "linux"
            and inputs["native_image"] in image["RepoDigests"]
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]), "Actual immutable ARM64 image differs")
    return {"status": "passed", "native_image": inputs["native_image"],
            "docker_image_id": image["Id"], "input_sha256": sha(path)}


def clean_environment(work):
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                "LD_PRELOAD", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    for directory in ("cache", "home", "tmp"):
        (work / directory).mkdir(mode=0o700)
    env.update(PATH=str(PREFIX / "bin") + ":/system/bin:/system/xbin", LD_LIBRARY_PATH=str(PREFIX / "lib"),
               PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_NO_CACHE_DIR="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", HF_HOME=str(work / "home"),
               XDG_CACHE_HOME=str(work / "cache"), TMPDIR=str(work / "tmp"),
               TOKENIZERS_PARALLELISM="true", RAYON_NUM_THREADS="2")
    return env


def install_libyaml(args, lock, common, archive_dir, env):
    expected = next(p for p in lock["apt_archives"] if p["name"] == "libyaml")
    command = [str(PREFIX / "bin/apt-get"), "-o", "Dir::Cache::archives=" + str(archive_dir),
               "-o", "Dpkg::Options::=--force-confnew", "--no-download", "--no-remove",
               "--no-install-recommends", "--reinstall", "install", "libyaml=" + expected["version"]]
    plan = common.bounded_command(command[:1] + ["-s"] + command[1:], args.out, "libyaml-plan", 60, env)
    raw = (args.out / "libyaml-plan.stdout.log").read_text()
    require(not any(line.startswith("Remv ") for line in raw.splitlines()), "APT proposed a removal")
    rows = [line for line in raw.splitlines() if line.startswith("Inst ")]
    require(len(rows) == 1 and rows[0].split()[1].split(":")[0] == "libyaml"
            and re.search(r"\(" + re.escape(expected["version"]) + r"\s", rows[0]),
            "APT proposed an unreviewed package or version")
    installed = common.bounded_command(command[:1] + ["-y"] + command[1:], args.out, "libyaml-install", 90, env)
    wanted = {"libyaml": {"version": expected["version"], "architecture": expected["architecture"], "status": "installed"}}
    require(common.package_snapshot(["libyaml"]) == wanted, "Installed LibYAML identity differs")
    return {"status": "passed", "plan": plan, "install": installed, "installed_packages": wanted,
            "compiler_installed": False}


def mapped_libraries(args, lock, manifest, wheel_prep, native, common, apt, static_elf):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    selected = {}
    for package in manifest["wheels"]:
        for item in package["native_members"]:
            path = site / item["member"]
            selected[path.resolve()] = {"package": package["name"], **item}
    raw = native.read_native_maps()
    rows = native.native_mapping_rows(raw, site, selected,
                                     {Path(p["path"]) for p in lock["platform_runtime"]["files"]})
    save(args.out / "NATIVE-MAPPINGS.json", {"mappings": rows})
    (args.out / "NATIVE-MAPPINGS.raw.txt").write_bytes(raw)
    require(not any(row["classification"].startswith("rejected-") for row in rows),
            "An actual native library is outside the reviewed owners")
    loaded = {Path(row["resolved_path"]) for row in rows if row["classification"] == "source-extension"}
    image_paths = {Path(row["resolved_path"]) for row in rows if row["classification"] == "image-platform"}
    records = []
    for path in sorted(loaded):
        expected = selected[path]
        require(path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"],
                "Actually mapped extension differs from its original wheel")
        details = static_elf.elf(path, dynamic=True)
        if expected["package"] == "hf-xet":
            require("libpython3.so" in details["needed"], "HF ABI3 Python stub linkage is missing")
        records.append({"package": expected["package"], **details})
    require({p["name"] for p in manifest["wheels"] if p["native_members"]}
            <= {row["package"] for row in records}, "A selected native component was not loaded")
    adapter = SimpleNamespace(package_snapshot=common.package_snapshot, elf=static_elf.elf)
    image = native.verify_image_platform_members(image_paths, lock, adapter, apt)
    pins, _ = common.all_apt_pins(lock, wheel_prep.base_helper())
    for p in lock["apt_archives"]:
        require(p["name"] not in pins, "Additional APT pin overwrote an original foundation/compiler pin")
        pins[p["name"]] = p
    paths = {row["resolved_path"] for row in rows if row["classification"] == "apt-library"}
    owners = apt.collect_owners(paths)
    grouped = {}
    for path in paths:
        candidates = owners.get(path, [])
        require(len(candidates) == 1 and candidates[0] in pins, "APT mapping has no single pinned owner")
        grouped.setdefault(candidates[0], set()).add(path)
    state = common.package_snapshot(sorted(grouped))
    apt_rows = []
    for name, wanted in sorted(grouped.items()):
        p = pins[name]
        require(state[name] == {"version": p["version"], "architecture": p["architecture"], "status": "installed"},
                "Actually loaded APT owner version differs")
        members = common.ar_data_members(common.archive_path(args.apt_archives, p), p, wanted)
        require(set(members) == wanted, "Original archive omitted a mapped library")
        for path, original in sorted(members.items()):
            require(Path(path).read_bytes() == original, "Mapped APT bytes differ from the original signed archive")
            apt_rows.append({"package": name, **static_elf.elf(Path(path), dynamic=True)})
    return {"status": "passed", "source_extensions": records, "apt_libraries": apt_rows,
            "image_platform": image, "readelf_or_compiler_used": False,
            "raw_mapping_sha256": sha(args.out / "NATIVE-MAPPINGS.raw.txt")}


def validate_disconnected_container(container, container_id, image_id, hostname):
    require(re.fullmatch(r"[0-9a-f]{64}", container_id) is not None
            and container.get("Id") == container_id and container.get("Image") == image_id
            and container.get("State", {}).get("Running") is True
            and container.get("NetworkSettings", {}).get("Networks") == {}
            and container.get("Config", {}).get("Hostname") == hostname
            and container["Config"].get("User") == "1000:1000",
            "Network evidence is not the actual owned native container")
    host = container["HostConfig"]
    require(host.get("NanoCpus") == 2_000_000_000 and host.get("Memory") == 6_442_450_944
            and host.get("PidsLimit") == 512, "Actual native resource limits differ")
    return container


def offline_network(args, image_id):
    base = args.image_receipt.parent
    signal = base / "TOKENIZERS-NETWORK-OFFLINE.json"
    record = read_json(signal)
    inspection_path = base / "TOKENIZERS-DISCONNECTED-CONTAINER.json"
    inspection = read_json(inspection_path)
    container_id = (base / "TOKENIZERS-CONTAINER-ID.txt").read_text().strip()
    require(record.get("schema_version") == 1 and record.get("status") == "disconnected"
            and record.get("remaining_networks") == {} and record.get("release_output") is False
            and record.get("container_id") == container_id
            and record.get("lock_sha256") == sha(args.inputs / "neutts_tokenizers_runtime_lock.json")
            and record.get("inspect_sha256") == sha(inspection_path)
            and isinstance(inspection, list) and len(inspection) == 1,
            "Owned network receipt or original runtime lock differs")
    validate_disconnected_container(inspection[0], container_id, image_id, socket.gethostname())
    interfaces = socket.if_nameindex()
    require({name for _, name in interfaces} == {"lo"}, "A non-loopback network interface remains")
    routes = Path("/proc/net/route").read_bytes()
    require(len(routes.splitlines()) == 1, "An external runtime network route remains")
    return {"status": "verified-disconnected", "host_receipt_sha256": sha(signal),
            "inspect_sha256": sha(inspection_path), "container_id": container_id,
            "interfaces": interfaces, "route_sha256": hashlib.sha256(routes).hexdigest(),
            "external_network_available": False}


def offline_ready(args, lock, image_id):
    marker = args.image_receipt.parent / "TOKENIZERS-NETWORK-READY.json"
    save(marker, {"schema_version": 1, "status": "ready-for-network-disconnect",
                  "lock_sha256": sha(args.inputs / "neutts_tokenizers_runtime_lock.json")})
    signal = args.image_receipt.parent / "TOKENIZERS-NETWORK-OFFLINE.json"
    deadline = time.monotonic() + 150
    while not signal.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    return offline_network(args, image_id)


def runtime_case(args, lock, prep, wheel_prep, native, common, apt, static_elf):
    report = {"schema_version": 1, "status": "failed", "engine_installed": False,
              "models_downloaded": False, "production_admission_changed": False, "release_output": False}
    try:
        report["runtime"] = native.native_runtime(common)
        require(sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1,
                "Actual child must use isolated imports without bytecode")
        report["source_image"] = validate_image(args.image_receipt, lock)
        report["network"] = offline_network(args, report["source_image"]["docker_image_id"])
        manifest = read_json(args.environment_manifest)
        require(manifest["names"] == lock["names"], "Isolated runtime selection differs")
        report["installed_before"] = native.installed_inventory(manifest, wheel_prep, common)
        report["closure"] = closure(lock)
        operations = module("neutts_tokenizers_operations.py")
        rust_operations = module("neutts_rust_operations.py")
        work = args.out / "operation-data"
        work.mkdir(mode=0o700)
        report["operations"] = {
            "tokenizers": operations.tokenizer_operations(work),
            "dependencies": operations.dependency_operations(work),
            "hf_xet": rust_operations.hash_operation(work),
            "safetensors": rust_operations.safetensors_operation(work)}
        report["native_mappings"] = mapped_libraries(args, lock, manifest, wheel_prep, native, common, apt, static_elf)
        report["installed_after"] = native.installed_inventory(manifest, wheel_prep, common)
        require(report["installed_before"] == report["installed_after"], "Operations changed original installed files")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save(args.out / "TOKENIZERS-RUNTIME-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def run(args, lock, prep, wheel_prep, native, common, apt, static_elf):
    report = {"schema_version": 1, "status": "failed", "engine_installed": False,
              "model_downloaded": False, "production_admission_changed": False, "release_output": False}
    work = None
    try:
        report["runtime"] = native.native_runtime(common)
        require(Path(sys.prefix).resolve() == PREFIX, "Parent must use the pinned global interpreter")
        report["foundation"] = common.validate_foundation(args.foundation_receipt, lock)
        report["source_image"] = validate_image(args.image_receipt, lock)
        work = Path(tempfile.mkdtemp(prefix="tokenizers-runtime-", dir=PREFIX / "tmp"))
        env = clean_environment(work)
        archive_dir = work / "apt-archives"
        archive_dir.mkdir()
        foundation_inputs = args.foundation_receipt.parent / "foundation-apt-inputs/apt-archives"
        for source in [*foundation_inputs.glob("*.deb"), *(args.inputs / "apt-archives").glob("*.deb")]:
            destination = archive_dir / source.name
            require(not destination.exists() and source.is_file() and not source.is_symlink(),
                    "Ambiguous original archive handoff")
            shutil.copyfile(source, destination)
        args.apt_archives = archive_dir
        all_pins, _ = common.all_apt_pins(lock, wheel_prep.base_helper())
        foundation_names = [line.split("\t")[0] for line in
                            (args.foundation_receipt.parent / "foundation-apt-inputs/foundation.tsv").read_text().splitlines()]
        require(len(foundation_names) == 122 and len(set(foundation_names)) == 122, "Foundation package set differs")
        before = common.package_snapshot(foundation_names)
        require(before == {name: {"version": all_pins[name]["version"], "architecture": all_pins[name]["architecture"],
                                  "status": "installed"} for name in foundation_names},
                "Actual foundation package versions differ")
        report["extra_apt"] = install_libyaml(args, lock, common, archive_dir, env)
        require(common.package_snapshot(foundation_names) == before, "LibYAML install changed original foundation packages")
        wheels = [dict(p, wheel_path=str(args.inputs / "wheels" / p["artifact"]["filename"]))
                  for p in lock["packages"]]
        python, manifest_path, _ = native.create_environment(
            args, lock, wheels, set(), work / "runtime", args.out, "tokenizers", wheel_prep, common, env)
        report["raw_pip"] = native.raw_pip_check(python, set(lock["names"]), lock, args.out, common, env)
        report["network"] = offline_ready(args, lock, report["source_image"]["docker_image_id"])
        command = [str(python), "-I", "-B", str(Path(__file__).resolve()), "--phase", "runtime",
                   "--inputs", str(args.inputs), "--out", str(args.out), "--apt-archives", str(archive_dir),
                   "--environment-manifest", str(manifest_path), "--image-receipt", str(args.image_receipt)]
        report["child_command"] = common.bounded_command(command, args.out, "actual-tokenizers-runtime", 240, env)
        result = read_json(args.out / "TOKENIZERS-RUNTIME-RESULT.json")
        require(result["status"] == "passed" and result["closure"]["node_count"] == 25
                and result["closure"]["edge_count"] == 29, "Complete actual runtime gate failed")
        report["runtime_receipt_sha256"] = sha(args.out / "TOKENIZERS-RUNTIME-RESULT.json")
        report["foundation_after"] = common.validate_foundation(args.foundation_receipt, lock)
        require(common.package_snapshot(foundation_names) == before, "Runtime changed original foundation packages")
        report["node_count"], report["edge_count"], report["status"] = 25, 29, "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        save(args.out / "TOKENIZERS-COMPONENT-RESULT.json", report)
        if work is not None:
            shutil.rmtree(work)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("run", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--image-receipt", type=Path, required=True)
    parser.add_argument("--environment-manifest", type=Path)
    parser.add_argument("--apt-archives", type=Path)
    args = parser.parse_args(argv)
    prep, wheel_prep, native, common, apt, static_elf = support()
    lock, _ = prep.verify_inputs(args.inputs)
    if args.phase == "run":
        require(args.foundation_receipt is not None and not args.out.exists(), "Use a fresh component output")
        args.out.mkdir()
        return run(args, lock, prep, wheel_prep, native, common, apt, static_elf)
    require(args.environment_manifest is not None and args.apt_archives is not None,
            "Actual child requires its exact installation and library archives")
    return runtime_case(args, lock, prep, wheel_prep, native, common, apt, static_elf)


if __name__ == "__main__":
    raise SystemExit(main())
