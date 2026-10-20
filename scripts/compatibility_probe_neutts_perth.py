#!/usr/bin/env python3
"""Run the complete isolated public Perth watermark API on native Termux.

The caller supplies the passed unchanged scientific foundation, authenticated
frozen APT context, original wheel inputs and a disconnected Docker container.
This does not install NeuTTS, use gated weights, or change production admission.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
import types

PREFIX = Path("/data/data/com.termux/files/usr")
SCRIPT_DIR = Path(__file__).resolve().parent
PREPARER_SHA256 = "2dbe52e9142b5093523144c6a445698076a0c6ba72be60ee0101e3c58813d28c"
ELF_SHA256 = "73d00842dfe5c6f46712d6171007c3cb2735ca68ba678515c15ace01af500b11"
NONRUST_SHA256 = "11d0dc5ed34dd45c855bffbba51c02eecf74ce8c5a5dd38cb1483e57f1d14e4b"
FALSE_FLAGS = ("neutts_engine_installed", "neutts_python_bound_changed",
               "default_speech_model_downloaded", "microphone_used",
               "production_admission_changed", "release_output")


class ProbeError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ProbeError(message)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def read_json(path, limit=8 * 1024 * 1024):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "Unsafe JSON input")
    raw = path.read_bytes()
    require(len(raw) == info.st_size, "JSON input changed")
    return json.loads(raw)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)


def module_at(name, path, digest):
    require(sha_file(path) == digest, "Reviewed runtime support changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Cannot load reviewed runtime support")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def support():
    prep = module_at("_perth_runtime_preparation", SCRIPT_DIR / "prepare_neutts_perth_runtime.py",
                     PREPARER_SHA256)
    nr = module_at("_perth_isolated_helpers", SCRIPT_DIR / "compatibility_probe_neutts_nonrust.py",
                   NONRUST_SHA256)
    _, common, apt = nr.support()
    return prep, nr, common, apt


def native_elf(path, dynamic=False):
    """Read the real original ELF bytes without adding a compiler package."""
    helper = module_at("_perth_static_elf", SCRIPT_DIR / "neutts_runtime_elf.py", ELF_SHA256)
    return helper.elf(path, dynamic=dynamic)


def all_apt_pins(lock, prep):
    foundation, _, compiler = prep.apt_helper().load_pins(prep.ROOT, False)
    require(compiler is None and len(foundation) == 122, "Original foundation scope changed")
    pins = {p["name"]: p for p in foundation}
    for p in prep.extra_apt_pins(lock):
        require(p["name"] not in pins, "Extra APT package overwrote an original foundation pin")
        pins[p["name"]] = p
    require(len(pins) == 125, "Unexpected complete retained APT set")
    return pins


def source_image(args, lock):
    inputs = read_json(args.image_receipt, 1000000)
    require(inputs.get("schema_version") == 1
            and inputs.get("native_image") == lock["platform_runtime"]["native_image"]
            and inputs.get("production_admission_changed") is False
            and inputs.get("release_output") is False, "Source-image boundary differs")
    for name in ("compatibility_probe_neutts_perth.py", "compatibility_probe_neutts_perth.sh",
                 "prepare_neutts_perth_runtime.py", "neutts_perth_runtime_lock.json"):
        require(inputs.get("inputs", {}).get("scripts/" + name) == sha_file(SCRIPT_DIR / name),
                "Executing Perth source differs from host input receipt")
    for pin in lock["source_files"]:
        require(inputs.get("inputs", {}).get(pin["path"]) == pin["sha256"],
                "Reviewed supporting source is missing from host receipt")
    path = args.image_receipt.parent / "PERTH-SOURCE-IMAGE.json"
    image = read_json(path, 2000000)
    require(isinstance(image, list) and len(image) == 1, "Ambiguous source-image inspection")
    image = image[0]
    require(image.get("Architecture") == "arm64" and image.get("Os") == "linux"
            and inputs["native_image"] in image.get("RepoDigests", [])
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("Id", "")), "Wrong immutable ARM64 image")
    return {"status": "verified-pinned-image", "native_image": inputs["native_image"],
            "docker_image_id": image["Id"], "input_receipt_sha256": sha_file(args.image_receipt),
            "inspection_sha256": sha_file(path)}


def installed_packages():
    result = subprocess.run([str(PREFIX / "bin/dpkg-query"), "-W",
                             "-f", r"${Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n"],
                            capture_output=True, text=True, timeout=30, check=True)
    require(not result.stderr and len(result.stdout) < 2000000, "Invalid installed APT inventory")
    rows = {}
    for line in result.stdout.splitlines():
        values = line.split("\t")
        require(len(values) == 4 and values[0] not in rows, "Duplicate/malformed installed APT row")
        if values[3] == "installed":
            rows[values[0]] = {"version": values[1], "architecture": values[2], "status": values[3]}
    return rows


def validate_install_plan(text, pins):
    expected = {p["name"]: p["version"] for p in pins}
    require(len(expected) == len(pins) == 2, "Unexpected Perth APT install request")
    seen = {}
    for line in text.splitlines():
        require(not line.startswith("Remv "), "APT proposed a removal")
        if line.startswith("Inst "):
            match = re.match(r"^Inst ([a-z0-9+.-]+)(?::[a-z0-9-]+)? (?:\[[^\]]+\] )?\((\S+)", line)
            require(match is not None, "Unparseable APT install proposal")
            name, version = match.groups()
            require(name in expected and name not in seen and expected[name] == version,
                    "APT proposed an extra, duplicate or different package")
            seen[name] = version
    require(seen == expected, "APT omitted or added an original required package")
    return {"status": "exact-two-package-plan", "packages": seen, "removals": False}


def runtime_environment(work):
    env = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "_PYTHON_HOST_PLATFORM",
                 "LD_PRELOAD", "CMAKE_TOOLCHAIN_FILE", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL",
                 "NUMBA_DISABLE_JIT", "NUMBA_DISABLE_CUDA", "PYTORCH_JIT"):
        env.pop(name, None)
    env.update({"PATH": str(PREFIX / "bin") + ":/system/bin:/system/xbin",
                "LD_LIBRARY_PATH": str(PREFIX / "lib"), "PIP_CONFIG_FILE": os.devnull,
                "PIP_NO_INDEX": "1", "PIP_NO_CACHE_DIR": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
                "NUMBA_NUM_THREADS": "2", "NUMBA_CACHE_DIR": str(work / "numba-cache"),
                "LIBROSA_CACHE_DIR": str(work / "librosa-cache"), "LIBROSA_DATA_DIR": str(work / "librosa-data"),
                "XDG_CACHE_HOME": str(work / "xdg-cache"), "TMPDIR": str(work / "tmp")})
    for name in ("numba-cache", "librosa-cache", "librosa-data", "xdg-cache", "tmp"):
        (work / name).mkdir(exist_ok=True)
    return env


def verify_signed_context(args):
    evidence = args.out / "perth-signed-snapshot"
    result = read_json(evidence / "RESULT.json")
    require(result.get("status") == "passed" and result.get("authority") == "native APT configured trust store"
            and result.get("insecure_repository_exceptions") is False
            and result.get("acquired_index_bytes_equal") is True and result.get("archive_count") == 122
            and result.get("inrelease_sha256") == "249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901"
            and result.get("packages_gz_sha256") == "dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6",
            "Native signed snapshot did not pass unchanged")
    config = Path(os.environ.get("APT_CONFIG", ""))
    require(config.is_file() and not config.is_symlink()
            and config.read_bytes() == (evidence / "frozen.conf").read_bytes(),
            "Active native APT configuration differs from the authenticated snapshot")
    text = config.read_text()
    for line in ('Acquire::AllowInsecureRepositories "false";',
                 'Acquire::AllowDowngradeToInsecureRepositories "false";',
                 'Acquire::AllowWeakRepositories "false";',
                 'APT::Get::AllowUnauthenticated "false";',
                 'Dir::Etc::sourceparts "-";'):
        require(text.splitlines().count(line) == 1, "Native APT authentication was relaxed")
    return {"status": "authenticated-original-index", "receipt_sha256": sha_file(evidence / "RESULT.json"),
            "active_config_sha256": sha_file(config)}


def verify_gmp(args, lock, common, apt):
    origin = lock["runtime_apt_provenance"]
    pin = lock["apt_provenance_only"][0]
    require(common.package_snapshot(["libgmp"]) == {"libgmp": {
        "version": pin["version"], "architecture": pin["architecture"], "status": "installed"}},
        "Inherited GMP version differs")
    base = next(p for p in origin["provenance"]["package_inventories"]
                if p["path"] == "NEUTTS-BASE-PACKAGES.tsv")
    path = args.out / base["path"]
    require(path.stat().st_size == base["bytes"] and sha_file(path) == base["sha256"]
            and path.read_text().splitlines().count(base["matching_row"]) == 1,
            "Inherited GMP is absent from the pinned image baseline")
    row, = origin["files"]
    target = Path(row["path"])
    require(target.absolute() == target.resolve() and stat.S_ISREG(target.lstat().st_mode),
            "Inherited GMP is not an exact regular path")
    members = common.ar_data_members(common.archive_path(args.apt_archives, pin), pin, {row["path"]})
    raw = members[row["path"]]
    require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
            and target.read_bytes() == raw, "Inherited GMP differs from its signed original archive")
    require(apt.collect_owners({row["path"]}) == {row["path"]: ["libgmp"]}, "Inherited GMP owner differs")
    return {"status": "verified-already-installed", "installed_or_upgraded": False,
            "package": pin["name"], "version": pin["version"], "archive_sha256": pin["sha256"],
            "member": native_elf(target, dynamic=True), "base_inventory_sha256": sha_file(path)}


def setup(args, lock, prep, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "inputs",
              **{flag: False for flag in FALSE_FLAGS}}
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["foundation"] = common.validate_foundation(args.out / "NEUTTS-CORE-RESULT.json", lock)
        prep.verify_inputs(args.inputs, args.foundation_inputs)
        report["signed_snapshot"] = verify_signed_context(args)
        pins = all_apt_pins(lock, prep)
        require(not args.apt_archives.exists(), "Use a new exact native APT cache")
        (args.apt_archives / "partial").mkdir(parents=True)
        for pin in pins.values():
            root = args.inputs / "apt-extra-archives" if pin["name"] in {
                p["name"] for p in prep.extra_apt_pins(lock)} else args.foundation_inputs / "apt-archives"
            source = prep.archive_path(root, pin)
            target = args.apt_archives / prep.apt_helper().archive_name(pin, native=True)
            prep.verified_bytes(source, pin)
            shutil.copyfile(source, target)
            prep.verified_bytes(target, pin)
            for field, key in (("Package", "name"), ("Version", "version"), ("Architecture", "architecture")):
                actual = subprocess.check_output([str(PREFIX / "bin/dpkg-deb"), "-f", str(target), field],
                                                 text=True, timeout=15).strip()
                require(actual == pin[key], "Staged APT control differs")
        report["inherited_gmp"] = verify_gmp(args, lock, common, apt)
        report["stage"] = "two-original-extra-packages"
        before = installed_packages()
        save_json(args.out / "PERTH-APT-BEFORE.json", before)
        requests = [p["name"] + "=" + p["version"] for p in lock["apt_install"]]
        options = ["-o", "Dir::Cache::archives=" + str(args.apt_archives),
                   "-o", "APT::Get::AllowUnauthenticated=false"]
        env = runtime_environment(args.work)
        simulation = common.bounded_command([str(PREFIX / "bin/apt-get"), *options, "--simulate",
            "--reinstall", "--no-install-recommends", "install", *requests],
            args.out, "perth-extra-apt-plan", 90, env)
        raw = (args.out / "perth-extra-apt-plan.stdout.log").read_text()
        report["plan"] = {**validate_install_plan(raw, lock["apt_install"]), "process": simulation}
        report["install"] = common.bounded_command([str(PREFIX / "bin/apt-get"), *options,
            "--yes", "--no-download", "--reinstall", "--no-install-recommends", "install", *requests],
            args.out, "perth-extra-apt-install", 180, env)
        after = installed_packages()
        save_json(args.out / "PERTH-APT-AFTER.json", after)
        expected_after = dict(before)
        for pin in lock["apt_install"]:
            expected_after[pin["name"]] = {"version": pin["version"], "architecture": pin["architecture"],
                                           "status": "installed"}
        require(after == expected_after, "Extra APT install removed or changed an unreviewed package")
        base_distributions = sorted([{"name": prep.canonical_name(d.metadata["Name"]), "version": d.version}
                                     for d in importlib.metadata.distributions()], key=lambda row: row["name"])
        original_base = set(lock["names"]) - {p["name"] for p in lock["packages"]
                         if p["origin"]["kind"] != "foundation-core-wheel"}
        expected_base = original_base | {"pip", "torchcodec"}
        require(len(base_distributions) == len(expected_base)
                and {p["name"] for p in base_distributions} == expected_base,
                "Base Python support inventory contains an unreviewed distribution")
        report["base_python_distributions"] = base_distributions
        report["foundation_support_outside_graph"] = [p for p in base_distributions
                                                     if p["name"] in {"pip", "torchcodec"}]
        report["verified_archive_count"] = 125
        report["only_installed_or_reinstalled"] = ["libyaml", "python-msgpack"]
        report["compiler_installed"] = False
        report["stage"] = "complete"
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "PERTH-APT-SETUP.json", report)
    return 0 if report["status"] == "passed" else 1


def validate_network_inspection(value, image_id, hostname):
    require(value.get("schema_version") == 1 and value.get("status") == "disconnected"
            and value.get("release_output") is False, "Missing host network-disconnect receipt")
    inspection = value["container"]
    require(inspection.get("Image") == image_id and inspection.get("State", {}).get("Running") is True
            and inspection.get("NetworkSettings", {}).get("Networks") == {}
            and inspection.get("Config", {}).get("User") == "1000:1000"
            and inspection["Config"].get("Hostname") == hostname,
            "Actual container is not the reviewed disconnected native runtime")
    host = inspection["HostConfig"]
    require(host.get("NanoCpus") == 2000000000 and host.get("Memory") == 6442450944
            and host.get("PidsLimit") == 512, "Actual container resource limits changed")
    return inspection


def validate_network(args, image_id):
    path = args.out / "PERTH-NETWORK-DISCONNECTED.json"
    value = read_json(path, 3000000)
    require(value.get("schema_version") == 1 and value.get("status") == "disconnected"
            and value.get("release_output") is False, "Missing host network-disconnect receipt")
    validate_network_inspection(value, image_id, socket.gethostname())
    interfaces = socket.if_nameindex()
    require({name for _, name in interfaces} == {"lo"}, "A non-loopback runtime network interface remains")
    route = Path("/proc/net/route").read_bytes()
    require(len(route.splitlines()) == 1, "A runtime network route remains")
    return {"status": "verified-disconnected", "host_receipt_sha256": sha_file(path),
            "interfaces": interfaces, "route_sha256": hashlib.sha256(route).hexdigest(),
            "network_connections_available": False}


def requirement_key(value):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    req = Requirement(value)
    return (canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)),
            str(req.marker or ""), req.url)


def validate_closure(lock, distributions=None, environment=None):
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import Version
    actual_environment = default_environment() if environment is None else dict(environment)
    actual_environment["extra"] = ""
    require(all(actual_environment.get(k) == v for k, v in lock["environment"].items()),
            "Actual marker environment differs from the original closure")
    if distributions is None:
        distributions = {canonicalize_name(d.metadata["Name"]): {
            "version": d.version, "requires_dist": d.metadata.get_all("Requires-Dist", []),
            "requires_python": d.metadata.get("Requires-Python", "")}
            for d in importlib.metadata.distributions()}
    require(set(distributions) == set(lock["names"]), "Incomplete or extra runtime distribution closure")
    nodes = {p["name"]: p for p in lock["nodes"]}
    active = []
    for name, distribution in distributions.items():
        original = nodes[name]
        require(distribution["version"] == original["version"]
                and SpecifierSet(distribution["requires_python"]) == SpecifierSet(original["requires_python"] or "")
                and sorted(map(requirement_key, distribution["requires_dist"]))
                == sorted(map(requirement_key, original["requires_dist"])),
                "Original full dependency clauses or Python bounds changed")
        require(Version(actual_environment["python_full_version"]) in SpecifierSet(distribution["requires_python"]),
                "Actual Python violates an original runtime bound")
        for declaration in distribution["requires_dist"]:
            req = Requirement(declaration)
            if req.marker is not None and not req.marker.evaluate(actual_environment):
                continue
            target = canonicalize_name(req.name)
            require(req.url is None and not req.extras and target in distributions,
                    "Active requirement has an extra, URL or missing dependency")
            require(Version(distributions[target]["version"]) in req.specifier,
                    "An original active dependency version constraint fails")
            active.append((name, target, requirement_key(declaration)))
    expected = [(edge["from"], edge["to"], requirement_key(edge["requirement"])) for edge in lock["edges"]]
    require(len(active) == 50 and sorted(active) == sorted(expected), "Original 50 active dependency links changed")
    reached = set(lock["manual_import_roots"])
    while True:
        expanded = reached | {target for source, target, _ in active if source in reached}
        if expanded == reached:
            break
        reached = expanded
    require(reached == set(lock["names"]), "Manual import roots do not reach the complete original closure")
    return {"status": "passed", "node_count": 43, "active_edge_count": 50,
            "selected_extras": [], "metadata_modified": False, "actual_marker_environment": actual_environment,
            "manual_import_roots": lock["manual_import_roots"],
            "foundation_support_outside_graph": ["pip", "torchcodec"], "global_site_visible": False}


def validate_manifest(manifest, args, lock):
    expected_wheels = [{**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])}
                       for p in lock["packages"]]
    require(manifest.get("schema_version") == 1 and manifest.get("names") == lock["names"]
            and manifest.get("wheels") == expected_wheels and manifest.get("apt_python") == lock["apt_python"],
            "Runtime manifest differs from all 43 frozen original distributions")
    expected_copies = [{
        "name": p["name"], "archive_sha256": p["archive"]["sha256"],
        "file_count": p["file_count"], "bytes": p["bytes"], "metadata_sha256": p["metadata_sha256"],
        "metadata_changed": False, "record_changed": False,
        "copy_mode_policy": "preserve executable bit, normalize ordinary copied permissions"}
        for p in lock["apt_python"]]
    require(manifest.get("copied_apt_payloads") == expected_copies, "Copied original APT receipt changed")


def installed_records(manifest, prep):
    """Validate pip's rewritten RECORD against actual installed files, including scripts."""
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    prefix = Path(sys.prefix).resolve()
    count = 0
    for package in manifest["wheels"]:
        record = site / package["wheel"]["record_member"]
        rows = list(csv.reader(io.StringIO(prep.read_regular(record, 2000000).decode("utf-8"))))
        require(rows and all(len(row) == 3 for row in rows)
                and len({row[0] for row in rows}) == len(rows), "Invalid installed wheel RECORD")
        for member, digest, size in rows:
            require(member and "\\" not in member and not member.startswith("/") and "\x00" not in member,
                    "Unsafe installed RECORD path")
            target = site.joinpath(*member.split("/"))
            resolved = target.resolve()
            require(resolved.is_relative_to(prefix) and stat.S_ISREG(target.lstat().st_mode),
                    "Installed RECORD escaped the isolated environment")
            if resolved == record.resolve():
                require(digest == size == "", "Installed RECORD self-entry changed")
            else:
                raw = prep.read_regular(target, 128 * 1024 * 1024)
                expected = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
                require(digest == "sha256=" + expected and size == str(len(raw)),
                        "Installed RECORD byte/hash mismatch")
            count += 1
    return {"status": "passed", "wheel_count": 36, "record_rows": count,
            "original_apt_records_modified": False}


def isolated_native_library_path(prefix):
    # Original Torch APT RUNPATH and PREFIX/lib links select the global payload
    # unless its verified isolated library directory precedes PREFIX/lib.
    return str(Path(prefix) / "lib/python3.14/site-packages/torch/lib") + os.pathsep + str(PREFIX / "lib")


def validate_mapping_classes(rows):
    require(not any(row["classification"].startswith("rejected-") for row in rows),
            "Foreign or unowned native runtime mapping")
    global_site = (PREFIX / "lib/python3.14/site-packages").resolve()
    require(not any(Path(row["resolved_path"]).is_relative_to(global_site) for row in rows),
            "A global Python package library entered the isolated runtime")


def mapped_apt_libraries(rows, archives, pins, common, apt):
    """Bind every classified global APT mapping to its exact signed archive."""
    paths = {row["resolved_path"] for row in rows if row["classification"] == "apt-library"}
    for name in paths:
        path = Path(name)
        require(path.is_relative_to(PREFIX / "lib") and path.absolute() == path.resolve()
                and stat.S_ISREG(path.lstat().st_mode), "Mapped APT path escaped its regular prefix")
    owners = apt.collect_owners(paths)
    grouped = {}
    for name in sorted(paths):
        candidates = owners.get(name, [])
        require(len(candidates) == 1 and candidates[0] in pins, "Unowned or unpinned APT native library")
        grouped.setdefault(candidates[0], set()).add(name)
    snapshot = common.package_snapshot(sorted(grouped))
    verified = []
    for package, wanted in sorted(grouped.items()):
        pin = pins[package]
        require(snapshot.get(package) == {"version": pin["version"], "architecture": pin["architecture"],
                                          "status": "installed"}, "Mapped APT owner version differs")
        archive = common.archive_path(archives, pin)
        members = common.ar_data_members(archive, pin, wanted)
        require(set(members) == wanted, "A mapped APT member is absent from its original archive")
        for name, raw in sorted(members.items()):
            path = Path(name)
            require(path.stat().st_size == len(raw) and path.read_bytes() == raw,
                    "Mapped APT library differs from its signed original archive")
            verified.append({"package": package, "package_version": pin["version"],
                             "archive_sha256": pin["sha256"], **native_elf(path, dynamic=True)})
    return {"status": "passed", "mapped_apt_libraries": verified,
            "android_system_mappings": sorted({row["resolved_path"] for row in rows
                                                if row["classification"] == "android-system"}),
            "system_scope": "Android platform libraries recorded separately; not represented as APT-owned files."}


def native_mappings(args, lock, manifest, prep, nr, common, apt):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    native = {}
    for package in manifest["wheels"]:
        for row in package["native_members"]:
            native[(site / row["member"]).resolve()] = {"package": package["name"],
                                                        "bytes": row["bytes"], "sha256": row["sha256"]}
    for package in manifest["apt_python"]:
        for row in package["files"]:
            if row["path"].endswith(".so") or ".so." in row["path"]:
                native[(site / row["path"]).resolve()] = {"package": package["name"],
                                                         "bytes": row["bytes"], "sha256": row["sha256"]}
    platform = {Path(row["path"]) for row in lock["platform_runtime"]["files"]}
    raw = nr.read_native_maps()
    (args.out / "PERTH-NATIVE-MAPPINGS.raw.txt").write_bytes(raw)
    rows = nr.native_mapping_rows(raw, site, native, platform)
    save_json(args.out / "PERTH-NATIVE-MAPPINGS.json", {"schema_version": 1, "mappings": rows,
              "raw_sha256": hashlib.sha256(raw).hexdigest()})
    validate_mapping_classes(rows)
    loaded = {Path(row["resolved_path"]) for row in rows if row["classification"] == "source-extension"}
    image_loaded = {Path(row["resolved_path"]) for row in rows if row["classification"] == "image-platform"}
    records = []
    for path in sorted(loaded):
        pin = native[path]
        require(path.stat().st_size == pin["bytes"] and sha_file(path) == pin["sha256"],
                "Mapped extension differs from its original wheel/APT payload")
        details = native_elf(path, dynamic=True)
        require(details["class"] == 64 and details["machine"] == 183 and details["endianness"] == "little"
                and not any(v in {"libc.so.6", "libstdc++.so.6", "libpython3.14.so.1.0"}
                            for v in details.get("needed", [])), "Foreign native ABI")
        records.append({"package": pin["package"], **details})
    required = {p["name"] for p in manifest["wheels"] if p["native_members"]} | prep.APT_NAMES
    require(required <= {p["package"] for p in records}, "A required native runtime component was not loaded")
    apt_mappings = mapped_apt_libraries(rows, args.apt_archives, all_apt_pins(lock, prep), common, apt)
    require(any(p["package"] == "libsndfile" for p in apt_mappings["mapped_apt_libraries"]),
            "Soundfile did not actually map the original APT libsndfile")
    return {"status": "passed", "actually_mapped_extensions": records,
            "apt": apt_mappings,
            "image_platform": nr.verify_image_platform_members(image_loaded, lock,
                types.SimpleNamespace(package_snapshot=common.package_snapshot, elf=native_elf), apt),
            "raw_mapping_sha256": hashlib.sha256(raw).hexdigest()}


def auxiliary_operations():
    import array
    import audioop
    import cffi
    import charset_normalizer.md
    import markupsafe
    import msgpack
    import numba
    import numpy as np
    import torchaudio
    import torch
    import yaml
    from sklearn.neighbors import KNeighborsRegressor
    require(audioop.max(array.array("h", [-400, 0, 300]).tobytes(), 2) == 400, "Actual audioop failed")
    ffi = cffi.FFI()
    require(sum(ffi.new("int[3]", [2, 3, 5])) == 10, "Actual CFFI operation failed")
    require(str(markupsafe.escape("<perth>")) == "&lt;perth&gt;", "Actual MarkupSafe operation failed")
    ratio = float(charset_normalizer.md.mess_ratio("Perth public audio test. " * 8))
    require(0.0 <= ratio <= 1.0, "Actual Charset Normalizer operation failed")
    value = {"rates": [24000, 32000], "gate": True}
    require(msgpack.unpackb(msgpack.packb(value, use_bin_type=True), raw=False) == value,
            "Actual original MsgPack operation failed")
    require(yaml.__with_libyaml__ is True and yaml.load("rates: [24000, 32000]\ngate: true\n",
                                                      Loader=yaml.CSafeLoader) == value,
            "Actual original libyaml parser failed")
    model = KNeighborsRegressor(n_neighbors=1).fit(np.array([[0.0], [2.0]]), np.array([0.0, 2.0]))
    require(np.array_equal(model.predict(np.array([[0.0], [2.0]])), np.array([0.0, 2.0])),
            "Actual scikit-learn nearest-neighbor operation failed")
    @numba.njit(cache=False)
    def sum_squares(values):
        total = 0.0
        for value in values:
            total += value * value
        return total
    result = float(sum_squares(np.arange(4, dtype=np.float64)))
    require(result == 14.0 and bool(sum_squares.nopython_signatures), "Actual Numba/LLVM JIT failed")
    signal = torch.arange(64, dtype=torch.float32).reshape(1, 64) / 128
    resampled = torchaudio.functional.resample(signal, 32000, 16000)
    require(tuple(resampled.shape) == (1, 32) and bool(torch.isfinite(resampled).all()),
            "Actual Torchaudio resampling failed")
    return {"status": "passed", "audioop_max": 400, "cffi_sum": 10, "msgpack_roundtrip": True,
            "libyaml_parser": True, "markup_escape": True, "charset_mess_ratio": ratio,
            "scikit_learn_prediction": [0.0, 2.0], "numba_nopython_result": result,
            "torchaudio_resample_shape": [1, 32], "jit_disabled": False}


def perth_operations(args, lock, prep):
    import numpy as np
    import soundfile as sf
    import torch
    import yaml
    import perth
    from perth.perth_net import PREPACKAGED_MODELS_DIR
    from perth.perth_net.perth_net_implicit.config import PerthConfig
    from perth.perth_net.perth_net_implicit.model.perth_net import PerthNet
    from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(perth.PerthImplicitWatermarker is PerthImplicitWatermarker
            and perth.PerthImplicitWatermarker is not None,
            "The real public implicit watermarker was not exposed")
    require(Path(inspect.getfile(PerthImplicitWatermarker)).resolve()
            == (site / "perth/perth_net/perth_net_implicit/perth_watermarker.py").resolve(),
            "The public watermarker did not come from the original verified source")
    require(importlib.metadata.version("resemble-perth") == "1.0.1" and perth.__version__ == "1.0.0",
            "Original Perth distribution/module version discrepancy was altered")
    require(Path(PREPACKAGED_MODELS_DIR).resolve()
            == (site / "perth/perth_net/pretrained").resolve(), "Derived resource lookup selected a foreign directory")
    operation = lock["operation"]
    checkpoint = site / operation["checkpoint"]["member"]
    hparams = site / operation["hparams"]["member"]
    prep.verified_bytes(checkpoint, operation["checkpoint"])
    hparams_raw = prep.verified_bytes(hparams, operation["hparams"])
    parsed = yaml.safe_load(hparams_raw)
    require(isinstance(parsed, dict), "Original public model configuration is not a mapping")
    hp = PerthConfig(**parsed)
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    model = PerthNet(hp).to("cpu").eval()
    checkpoint_value = torch.load(checkpoint, weights_only=True, map_location="cpu")
    require(isinstance(checkpoint_value, dict) and set(checkpoint_value) == {"model", "step"}
            and checkpoint_value["step"] == operation["checkpoint_saved_step"]
            and isinstance(checkpoint_value["model"], dict), "Unexpected original checkpoint schema")
    state = checkpoint_value["model"]
    require(state and all(isinstance(v, torch.Tensor) and v.device.type == "cpu"
                          and bool(torch.isfinite(v).all()) for v in state.values()),
            "Checkpoint did not safely produce finite CPU tensors")
    loaded = model.load_state_dict(state, strict=True)
    require(not loaded.missing_keys and not loaded.unexpected_keys
            and all(value.device.type == "cpu" for value in model.state_dict().values()),
            "Original checkpoint does not strictly fit the original model")
    watermarker = perth.PerthImplicitWatermarker(run_name=None, perth_net=model, device="cpu")
    records = []
    with torch.inference_mode():
        for rate in operation["sample_rates"]:
            time_axis = np.arange(rate, dtype=np.float64) / rate
            signal = (0.12 * np.sin(2 * np.pi * 220 * time_axis)
                      + 0.04 * np.sin(2 * np.pi * 659 * time_axis)).astype(np.float32)
            original = signal.tobytes()
            buffer = io.BytesIO()
            sf.write(buffer, signal, rate, format="WAV", subtype="FLOAT")
            wav = buffer.getvalue()
            buffer.seek(0)
            roundtrip, actual_rate = sf.read(buffer, dtype="float32", always_2d=False)
            require(actual_rate == rate and roundtrip.shape == signal.shape
                    and roundtrip.dtype == signal.dtype and roundtrip.tobytes() == original,
                    "Original libsndfile in-memory float WAV roundtrip failed")
            watermarked = watermarker.apply_watermark(signal, rate)
            require(isinstance(watermarked, np.ndarray) and watermarked.shape == signal.shape
                    and watermarked.dtype == np.float32 and np.isfinite(watermarked).all()
                    and not np.array_equal(watermarked, signal) and signal.tobytes() == original,
                    "Real public watermark application failed or modified its input")
            confidences = {}
            for label, samples in (("clean", signal), ("watermarked", watermarked)):
                confidence = watermarker.get_watermark(samples, rate, round=False)
                rounded = watermarker.get_watermark(samples, rate, round=True)
                require(isinstance(confidence, np.ndarray) and confidence.shape == ()
                        and confidence.dtype == np.float32 and np.isfinite(confidence).all()
                        and 0 <= float(confidence) <= 1
                        and isinstance(rounded, np.ndarray) and rounded.shape == ()
                        and float(rounded) in (0.0, 1.0)
                        and float(rounded) == float(np.round(confidence)), "Real public watermark decoder failed")
                confidences[label] = {"confidence": float(confidence), "rounded": float(rounded)}
            require(signal.tobytes() == original, "A public decoder modified its original signal")
            records.append({"sample_rate": rate, "samples": rate, "dtype": str(watermarked.dtype),
                "wav_bytes": len(wav), "wav_sha256": hashlib.sha256(wav).hexdigest(),
                "waveform_sha256": hashlib.sha256(original).hexdigest(),
                "watermarked_sha256": hashlib.sha256(watermarked.tobytes()).hexdigest(),
                "input_unchanged": True, "output_changed": True,
                "max_absolute_delta": float(np.max(np.abs(watermarked - signal))),
                "confidence": confidences, "quality_threshold_asserted": False})
    return {"status": "passed", "public_class": "perth.PerthImplicitWatermarker",
            "injected_original_model": True, "checkpoint_sha256": operation["checkpoint"]["sha256"],
            "checkpoint_step": checkpoint_value["step"], "actual_state_tensor_count": len(state),
            "weights_only": True, "map_location": "cpu", "strict_state_dict": True,
            "soundfile_library": sf._libname, "libsndfile_version": sf.__libsndfile_version__,
            "operations": records, "default_speech_model_downloaded": False,
            "public_bundled_watermark_checkpoint_executed": True}


def runtime_case(args, lock, prep, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "complete-inputs",
              **{flag: False for flag in FALSE_FLAGS}}
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["network"] = validate_network(args, report["source_image"]["docker_image_id"])
        require(all(os.environ.get(name) and Path(os.environ[name]).is_relative_to(args.work)
                    for name in ("NUMBA_CACHE_DIR", "LIBROSA_CACHE_DIR", "LIBROSA_DATA_DIR",
                                 "XDG_CACHE_HOME", "TMPDIR"))
                and os.environ.get("NUMBA_DISABLE_JIT") in (None, "", "0"),
                "Runtime caches or JIT behavior differ")
        require(os.environ.get("LD_LIBRARY_PATH") == isolated_native_library_path(sys.prefix),
                "Native library lookup does not prefer the exact isolated Torch payload")
        report["native_library_path"] = os.environ["LD_LIBRARY_PATH"]
        manifest = read_json(args.environment_manifest)
        validate_manifest(manifest, args, lock)
        report["installed_before"] = nr.installed_inventory(manifest, prep, common)
        report["record_integrity_before"] = installed_records(manifest, prep)
        report["closure"] = validate_closure(lock)
        report["stage"] = "actual-native-dependency-operations"
        import torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(2)
        report["auxiliary"] = auxiliary_operations()
        report["stage"] = "public-checkpoint-and-watermark-operations"
        report["perth"] = perth_operations(args, lock, prep)
        report["stage"] = "actual-native-provenance"
        report["native_mappings"] = native_mappings(args, lock, manifest, prep, nr, common, apt)
        report["installed_after"] = nr.installed_inventory(manifest, prep, common)
        report["record_integrity_after"] = installed_records(manifest, prep)
        require(report["installed_after"] == report["installed_before"]
                and report["record_integrity_after"] == report["record_integrity_before"],
                "Native operations changed the exact isolated runtime")
        report["network_after"] = validate_network(args, report["source_image"]["docker_image_id"])
        report["stage"] = "complete"
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "PERTH-RUNTIME-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def run(args, lock, prep, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "setup",
              **{flag: False for flag in FALSE_FLAGS}}
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["foundation"] = common.validate_foundation(args.out / "NEUTTS-CORE-RESULT.json", lock)
        setup_receipt = read_json(args.out / "PERTH-APT-SETUP.json")
        require(setup_receipt.get("status") == "passed" and setup_receipt.get("stage") == "complete"
                and setup_receipt.get("verified_archive_count") == 125
                and setup_receipt.get("only_installed_or_reinstalled") == ["libyaml", "python-msgpack"]
                and setup_receipt.get("compiler_installed") is False,
                "Exact two-package APT setup did not pass")
        report["apt_setup_sha256"] = sha_file(args.out / "PERTH-APT-SETUP.json")
        report["network"] = validate_network(args, report["source_image"]["docker_image_id"])
        prep.verify_inputs(args.inputs)
        for pin in all_apt_pins(lock, prep).values():
            common.archive_path(args.apt_archives, pin)
        env = runtime_environment(args.work)
        wheels = [{**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])}
                  for p in lock["packages"]]
        destination = args.work / "perth-runtime"
        report["stage"] = "complete-isolated-install"
        python, manifest_path, manifest = nr.create_environment(args, lock, wheels, prep.APT_NAMES,
            destination, args.out, "perth-runtime", prep, common, env)
        validate_manifest(manifest, args, lock)
        report["raw_pip"] = nr.raw_pip_check(python, set(lock["names"]), lock, args.out, common, env)
        report["stage"] = "public-native-runtime"
        command = [str(python), "-I", "-B", str(Path(__file__).resolve()), "--phase", "runtime",
                   "--inputs", str(args.inputs), "--foundation-inputs", str(args.foundation_inputs),
                   "--out", str(args.out), "--work", str(args.work),
                   "--apt-archives", str(args.apt_archives), "--image-receipt", str(args.image_receipt),
                   "--environment-manifest", str(manifest_path)]
        child_env = dict(env)
        child_env["LD_LIBRARY_PATH"] = isolated_native_library_path(destination)
        report["child"] = common.bounded_command(command, args.out, "perth-public-runtime", 900, child_env)
        child_path = args.out / "PERTH-RUNTIME-RESULT.json"
        child = read_json(child_path)
        require(child.get("status") == "passed" and child.get("stage") == "complete"
                and child.get("closure", {}).get("node_count") == 43
                and child.get("closure", {}).get("active_edge_count") == 50
                and len(child.get("perth", {}).get("operations", [])) == 2
                and child.get("native_mappings", {}).get("status") == "passed"
                and all(child.get(flag) is False for flag in FALSE_FLAGS),
                "Actual public Perth child did not pass the complete gate")
        report["runtime_receipt"] = child_path.name
        report["runtime_receipt_sha256"] = sha_file(child_path)
        report["actual_runtime_distribution_count"] = 43
        report["active_edge_count"] = 50
        report["foundation_support_outside_graph"] = ["pip", "torchcodec"]
        report["public_bundled_watermark_checkpoint_executed"] = True
        report["stage"] = "complete"
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "PERTH-COMPONENT-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("setup", "run", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--foundation-inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path, required=True)
    parser.add_argument("--image-receipt", type=Path, required=True)
    parser.add_argument("--environment-manifest", type=Path)
    args = parser.parse_args(argv)
    prep, nr, common, apt = support()
    lock, _ = prep.load_lock(args.inputs / prep.LOCK_FILENAME)
    require(args.out.is_dir() and args.work.is_dir(), "Existing owned work/evidence directories required")
    if args.phase == "runtime":
        require(args.environment_manifest is not None, "Missing isolated environment manifest")
        return runtime_case(args, lock, prep, nr, common, apt)
    if args.phase == "setup":
        return setup(args, lock, prep, nr, common, apt)
    return run(args, lock, prep, nr, common, apt)


if __name__ == "__main__":
    raise SystemExit(main())
