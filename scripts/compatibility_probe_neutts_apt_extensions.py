#!/usr/bin/env python3
"""Actual five-APT-extension operations after the unchanged seven-case foundation.

This gate preserves the twelve original APT WHEEL tags and the nonzero raw pip
result. It does not install a NeuTTS engine, models, build tools or a new release.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import traceback

SCRIPT_DIR = Path(__file__).resolve().parent
PREFIX_TEXT = "/data/data/com.termux/files/usr"
PREFIX = Path(PREFIX_TEXT)
SITE = PREFIX / "lib/python3.14/site-packages"
PREPARER_SHA256 = "0d954a2b4f9e68d8bb80ecea132b97e6e05a23f41835a2189ccf53884d811c3a"
COMMON_SHA256 = "862efa59b3c967fd360e1d9ce86d4ebadc5bbf9a4b0a3023f2990a66da130c74"
CASES = ("pyarrow", "lxml", "msgpack", "pillow", "psutil")
RESULT = "APT-EXTENSIONS-RESULT.json"


class ProbeError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ProbeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def save(path, value):
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


def module_at(name, path, expected):
    require(path.is_file() and not path.is_symlink() and sha(path) == expected,
            "Reviewed helper source differs: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def support():
    prep = module_at("_apt_extension_preparer", SCRIPT_DIR / "prepare_neutts_apt_extensions.py",
                     PREPARER_SHA256)
    common = module_at("_apt_extension_foundation", SCRIPT_DIR / "compatibility_probe_neutts_native.py",
                       COMMON_SHA256)
    return prep, common, prep.apt_helper()


def clean_command_environment():
    env = dict(os.environ)
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(name, None)
    env.update(LC_ALL="C", LANG="C")
    return env


def command(argv, out, label, timeout, expected=0, env=None, check=True):
    stdout, stderr = out / (label + ".stdout.log"), out / (label + ".stderr.log")
    record = {"argv": list(map(str, argv)), "exit_code": None, "timed_out": False}
    try:
        with stdout.open("xb") as a, stderr.open("xb") as b:
            process = subprocess.Popen(argv, stdout=a, stderr=b, env=env,
                                       start_new_session=os.name == "posix")
            try:
                record["exit_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait(timeout=10)
                record["exit_code"] = process.returncode
    except Exception as exc:
        record["launch_error"] = {"type": type(exc).__name__, "message": str(exc),
                                  "traceback": traceback.format_exc()}
    for name, path in (("stdout", stdout), ("stderr", stderr)):
        if path.exists():
            record[name] = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}
    record["status"] = ("passed" if record["exit_code"] == expected and not record["timed_out"]
                        and "launch_error" not in record else "failed")
    save(out / (label + ".command.json"), record)
    if check:
        require(record["status"] == "passed",
                label + " failed: exit=" + str(record["exit_code"]) + "; logs retained under " + str(out))
    return record


def parse_package_snapshot(text):
    rows = {}
    for line in text.splitlines():
        fields = line.split("\t")
        require(len(fields) == 4 and fields[0] not in rows, "Malformed or duplicate dpkg state")
        name, version, architecture, status = fields
        rows[name] = {"version": version, "architecture": architecture, "status": status}
    require(rows, "Empty dpkg state")
    return rows


def package_snapshot(out, label):
    fields = ("Package", "Version", "Architecture", "db:Status-Status")
    fmt = "\t".join(chr(36) + "{" + field + "}" for field in fields) + "\n"
    record = command([str(PREFIX / "bin/dpkg-query"), "--show", "--showformat=" + fmt],
                     out, label, 30, env=clean_command_environment())
    rows = parse_package_snapshot((out / record["stdout"]["file"]).read_text())
    save(out / (label + ".json"), rows)
    return rows


def installed_identity(pin):
    return {"version": pin["version"], "architecture": pin["architecture"], "status": "installed"}


def validate_before(before, lock):
    for pin in lock["foundation"]["packages"]:
        require(before.get(pin["package"]) == installed_identity(pin),
                "Original foundation package changed: " + pin["package"])
    additions = [p for p in lock["apt"]["provenance_packages"]
                 if p["package"] in lock["apt"]["additional_names"]]
    for pin in additions:
        require(pin["package"] not in before or before[pin["package"]] == installed_identity(pin),
                "Unreviewed pre-existing version/status of addition: " + pin["package"])
    return additions


def validate_plan(text, additions):
    wanted = {p["package"]: p for p in additions}
    found = {}
    for line in text.splitlines():
        require(not line.startswith(("Remv ", "Purg ")), "APT proposed removal/purge: " + line)
        if not line.startswith("Inst "):
            continue
        match = re.match(r"Inst (\S+)(?: \[([^\]]+)\])? \((\S+)(?:\s|\))", line)
        require(match is not None, "Unreadable APT plan line: " + line)
        name = match[1].split(":", 1)[0]
        require(name in wanted and name not in found, "APT proposed extra/duplicate package: " + name)
        require(match[3] == wanted[name]["version"], "APT proposed unreviewed version: " + line)
        if match[2] is not None:
            require(match[2] == wanted[name]["version"], "APT proposed an upgrade/downgrade: " + line)
        found[name] = match[3]
    require(set(found) == set(wanted), "APT proposed an omission or unreviewed selection")
    return found


def validate_after(before, after, additions):
    expected = dict(before)
    for pin in additions:
        expected[pin["package"]] = installed_identity(pin)
    require(after == expected, "DPKG state changed outside the eighteen exact selected packages")
    return {"new_packages": sorted(set(after) - set(before)),
            "reinstalled_exact_packages": sorted(p["package"] for p in additions if p["package"] in before),
            "unreviewed_upgrades": [], "removed_packages": [], "other_state_changes": []}


def signed_snapshot(args, lock, prep, work):
    expanded = prep.snapshot_metadata(args.inputs / "snapshot", lock)
    repo, lists = work / "signed-repository", work / "apt-lists"
    (repo / "dists/stable/main/binary-aarch64").mkdir(parents=True)
    (lists / "partial").mkdir(parents=True)
    shutil.copyfile(args.inputs / "snapshot/InRelease", repo / "dists/stable/InRelease")
    shutil.copyfile(args.inputs / "snapshot/Packages.gz",
                    repo / "dists/stable/main/binary-aarch64/Packages.gz")
    sources = work / "frozen.list"
    sources.write_text("deb [arch=aarch64] " + repo.as_uri() + " stable main\n")
    options = [
        "-o", "Dir::Etc::sourcelist=" + str(sources), "-o", "Dir::Etc::sourceparts=-",
        "-o", "Dir::State::lists=" + str(lists), "-o", "Acquire::Languages=none",
        "-o", "Acquire::AllowInsecureRepositories=false",
        "-o", "Acquire::AllowDowngradeToInsecureRepositories=false",
        "-o", "Acquire::AllowWeakRepositories=false", "-o", "APT::Get::AllowUnauthenticated=false",
        "-o", "APT::Update::Error-Mode=any",
    ]
    record = command([str(PREFIX / "bin/apt-get"), *options, "update"], args.out,
                     "authenticated-frozen-index", 90, env=clean_command_environment())
    frozen = lock["repository"]["snapshot"]
    releases = list(lists.glob("*_InRelease"))
    require(len(releases) == 1 and sha(releases[0]) == frozen["InRelease"]["sha256"],
            "APT did not authenticate and retain the exact InRelease")
    indexes = [p for p in lists.iterdir() if p.name.endswith(("_Packages", "_Packages.lz4", "_Packages.gz"))]
    require(len(indexes) == 1, "APT did not acquire one exact target index")
    loaded = subprocess.run([str(PREFIX / "lib/apt/apt-helper"), "cat-file", str(indexes[0])],
                            capture_output=True, timeout=30, env=clean_command_environment())
    require(loaded.returncode == 0 and loaded.stdout == expanded and not loaded.stderr,
            "APT-acquired package index differs from the exact signed bytes")
    return options, {"status": "passed", "authority": "native APT configured Termux trust store",
                     "insecure_exceptions": False, "update": record, "snapshot": frozen,
                     "uncompressed": lock["repository"]["packages_uncompressed"],
                     "matched_provenance_archives": 84, "matched_foundation_packages": 122}


def verify_archives(args, lock, prep):
    pins = lock["apt"]["provenance_packages"]
    children = list(args.apt_archives.iterdir())
    require({p.name for p in children if p.is_file()} == {p["filename"] for p in pins}
            and all(p.is_file() or p.name == "partial" and p.is_dir() for p in children)
            and all(not p.is_symlink() for p in children), "Exact archive directory differs")
    partial = args.apt_archives / "partial"
    require(not partial.exists() or not any(partial.iterdir()), "Unexpected partial APT archive")
    results = []
    for pin in pins:
        checked = prep.inspect_deb(args.apt_archives / pin["filename"], pin, wanted=set())
        results.append({"package": pin["package"], "version": pin["version"], "architecture": pin["architecture"],
                        "file": pin["filename"], "bytes": pin["bytes"], "sha256": pin["sha256"],
                        "control": checked["control"]})
    save(args.out / "VERIFIED-APT-ARCHIVES.json", {"status": "passed", "archives": results})
    return {"status": "passed", "archives": 84, "bytes": sum(p["bytes"] for p in pins),
            "receipt_sha256": sha(args.out / "VERIFIED-APT-ARCHIVES.json")}


def install_additions(args, lock, options):
    before = package_snapshot(args.out, "dpkg-before")
    additions = validate_before(before, lock)
    argv = [str(PREFIX / "bin/apt-get"), *options,
            "-o", "Dir::Cache::archives=" + str(args.apt_archives),
            "-o", "Dpkg::Options::=--force-confnew", "--no-download", "--no-remove",
            "--no-install-recommends", "--reinstall", "install",
            *(p["package"] + "=" + p["version"] for p in additions)]
    planned = command(argv[:1] + ["--simulate"] + argv[1:], args.out, "apt-plan", 90,
                      env=clean_command_environment())
    selection = validate_plan((args.out / "apt-plan.stdout.log").read_text(), additions)
    installed = command(argv[:1] + ["--yes"] + argv[1:], args.out, "apt-install", 300,
                        env=clean_command_environment())
    after = package_snapshot(args.out, "dpkg-after")
    changes = validate_after(before, after, additions)
    return {"status": "passed", "selected_count": 18, "selected_versions": selection,
            "selected_archive_bytes": 14_043_104, "compiler_requested": False,
            "plan": planned, "install": installed, **changes}


def verify_root_files(lock, apt, prep):
    rows = [row for package in lock["original_root_files"].values() for row in package]
    owners = apt.collect_owners(row["path"] for row in rows)
    expected = {row["path"]: row for row in rows if row["kind"] == "file"}
    verified = apt.verify_installed_files(expected, owners)
    for row in rows:
        path = Path(row["path"])
        if row["kind"] == "symlink":
            require(path.is_symlink() and os.readlink(path) == row["target"]
                    and owners.get(row["path"]) == [row["package"]], "Original package symlink differs: " + str(path))
        require(stat.S_IMODE(path.lstat().st_mode) == row["mode"],
                "Original package mode differs: " + str(path))
    for package, frozen in lock["original_root_files"].items():
        listing = PREFIX / "var/lib/dpkg/info" / (package + ".list")
        require(listing.is_file() and not listing.is_symlink(), "Missing original dpkg file list")
        listed = set(listing.read_text().splitlines())
        actual_files = {name for name in listed if Path(name).is_symlink() or Path(name).is_file()}
        require(actual_files == {row["path"] for row in frozen},
                "Installed package file inventory differs: " + package)
    for package in lock["root_native_files"].values():
        for row in package:
            value = prep.read_regular(Path(row["path"]), row["bytes"])
            require(len(value) == row["bytes"] and prep.sha(value) == row["sha256"],
                    "Original native file differs: " + row["path"])
            prep.elf_identity(value)
    return {"status": "passed", "regular_files": len(verified), "symlinks": 1, "aarch64_elf_files": 34,
            "installed_manifest_sha256": hashlib.sha256(json_bytes(rows)).hexdigest(),
            "original_metadata_and_tags_preserved": True}


def validate_image_foundation(lock, foundation, common, apt):
    expected = {row["path"]: row for row in lock["image_runtime"]["files"]}
    root = json.loads(foundation.read_bytes())
    recorded = {}
    for child in root["cases"]:
        receipt = foundation.parent / child["receipt"]
        require(sha(receipt) == child["receipt_sha256"], "Foundation child changed")
        for row in json.loads(receipt.read_bytes()).get("mapped_libraries", []):
            if row.get("path") in expected:
                require(row == expected[row["path"]], "Pinned-image library differs from its original evidence")
                recorded[row["path"]] = row
    require(set(recorded) == set(expected), "Foundation omitted a pinned-image AOSP library")
    owners = apt.collect_owners(expected)
    for name, row in expected.items():
        path = Path(name)
        require(path.resolve() == path and path.is_file() and path.stat().st_size == row["bytes"]
                and sha(path) == row["sha256"] and owners.get(name) == ["aosp-libs"],
                "Pinned-image AOSP file or ownership changed: " + name)
        details = common.elf(path)
        require(details["machine"] == 183, "Pinned-image library is not AArch64")
    return {"status": "passed", "image": lock["image_runtime"]["image"], "files": list(expected.values()),
            "authority": lock["image_runtime"]["authority"], "snapshot_archive_claim": False}


def verify_extension_image_file(row, owners, owner_state, prep):
    path = Path(row["path"])
    require(path.resolve(strict=True) == path and path.is_file(),
            "Extension image member is not a canonical regular file: " + str(path))
    raw = prep.read_regular(path, row["bytes"])
    require(len(raw) == row["bytes"] and prep.sha(raw) == row["sha256"],
            "Extension image member bytes differ: " + str(path))
    require(owners == row["owners"] and owner_state == row["owner_state"],
            "Extension image member ownership/state differs: " + str(path))
    info = path.stat()
    require((stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) ==
            (row["mode"], row["uid"], row["gid"]),
            "Extension image member mode/UID/GID differs: " + str(path))
    details = prep.elf_identity(raw)
    require(details == row["elf"], "Extension image member ELF differs: " + str(path))
    return {"path": row["path"], "bytes": len(raw), "sha256": prep.sha(raw), **details,
            "owner": owners[0], "version": owner_state["version"],
            "mode": row["mode"], "uid": row["uid"], "gid": row["gid"],
            "authority": "pinned-image-aosp-extension"}


def validate_extension_image(args, lock, apt, prep):
    extension = lock["extension_image_runtime"]
    owners = apt.collect_owners([row["path"] for row in extension["files"]])
    states = package_snapshot(args.out, "extension-image-owner-state")
    files = [verify_extension_image_file(row, owners.get(row["path"], []),
                                        states.get(row["owners"][0]), prep)
             for row in extension["files"]]
    return {"status": "passed", "image": extension["image"], "files": files,
            "authority": extension["authority"], "source_evidence": extension["source_evidence"],
            "original_foundation_file_count": 5, "snapshot_archive_claim": False}


def classify_mapping(path, lock):
    path = PurePosixPath(path)
    require(path.is_absolute() and ".." not in path.parts, "Non-canonical native mapping: " + str(path))
    image = {row["path"] for row in lock["image_runtime"]["files"]}
    if str(path) in image:
        return "pinned-image-aosp"
    if str(path) in {row["path"] for row in lock["extension_image_runtime"]["files"]}:
        return "pinned-image-aosp-extension"
    if path.is_relative_to(PurePosixPath(PREFIX_TEXT + "/lib")):
        return "apt"
    raise ProbeError("Unreviewed native mapping outside exact APT/image paths: " + str(path))


def mapping_observations(args, lock, apt, prep, paths, aliases, resolution_errors):
    """Preserve actual bytes/ownership before applying the unchanged admission policy."""
    observations = {"schema_version": 1, "status": "observations-only", "admitted": False,
                    "image": lock["image_runtime"]["image"], "files": [],
                    "resolution_errors": resolution_errors, "collection_errors": []}
    owners, states = {}, {}
    try:
        owners = apt.collect_owners(paths)
    except Exception as exc:
        observations["collection_errors"].append({"stage": "ownership", "type": type(exc).__name__,
                                                   "message": str(exc), "traceback": traceback.format_exc()})
    try:
        states = package_snapshot(args.out, "mapped-owner-state")
    except Exception as exc:
        observations["collection_errors"].append({"stage": "installed-owner-state", "type": type(exc).__name__,
                                                   "message": str(exc), "traceback": traceback.format_exc()})
    for name in sorted(paths):
        row = {"resolved_path": name, "mapped_paths": sorted(aliases[name]),
               "owners": sorted(owners.get(name, [])),
               "owner_states": {owner: states.get(owner) for owner in sorted(owners.get(name, []))},
               "admitted": False}
        try:
            raw = prep.read_regular(name, lock["limits"]["max_expanded_member_bytes"])
            info = Path(name).stat()
            row.update(bytes=len(raw), sha256=prep.sha(raw), mode=stat.S_IMODE(info.st_mode),
                       uid=info.st_uid, gid=info.st_gid)
            row["elf"] = prep.elf_identity(raw)
        except Exception as exc:
            row["observation_error"] = {"type": type(exc).__name__, "message": str(exc),
                                        "traceback": traceback.format_exc()}
        observations["files"].append(row)
    observations["complete"] = (not resolution_errors and not observations["collection_errors"]
                                and bool(paths)
                                and all("observation_error" not in row for row in observations["files"]))
    save(args.out / "MAPPED-LIBRARY-OBSERVATIONS.json", observations)
    return owners, observations


def verify_mappings(args, lock, apt, prep):
    raw = Path("/proc/self/maps").read_bytes()
    with (args.out / "proc-self-maps.txt").open("xb") as stream:
        stream.write(raw)
    paths, aliases, resolution_errors = set(), {}, []
    for line in raw.decode().splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("/") or ".so" not in parts[5]:
            continue
        try:
            require(not parts[5].endswith(" (deleted)"), "Deleted native mapping: " + parts[5])
            path = Path(parts[5]).resolve(strict=True)
            paths.add(path.as_posix())
            aliases.setdefault(path.as_posix(), set()).add(parts[5])
        except Exception as exc:
            resolution_errors.append({"mapped_path": parts[5], "type": type(exc).__name__,
                                      "message": str(exc), "traceback": traceback.format_exc()})
    owners, observations = mapping_observations(args, lock, apt, prep, paths, aliases, resolution_errors)
    require(observations["complete"], "Native mapping observation incomplete; exact diagnostics retained")
    pins = {p["package"]: p for p in lock["apt"]["provenance_packages"]}
    image = {row["path"]: row for row in lock["image_runtime"]["files"]}
    extension_image = {row["path"]: row for row in lock["extension_image_runtime"]["files"]}
    observed = {row["resolved_path"]: row for row in observations["files"]}
    apt_groups, records = {}, []
    for name in sorted(paths):
        kind = classify_mapping(name, lock)
        if kind == "pinned-image-aosp":
            row = image[name]
            require(owners.get(name) == ["aosp-libs"] and sha(name) == row["sha256"]
                    and Path(name).stat().st_size == row["bytes"], "Mapped image library differs: " + name)
            prep.elf_identity(prep.read_regular(name, row["bytes"]))
            records.append({"path": name, "mapped_paths": sorted(aliases[name]), "authority": kind,
                            "bytes": row["bytes"], "sha256": row["sha256"], "owner": "aosp-libs"})
        elif kind == "pinned-image-aosp-extension":
            row = extension_image[name]
            details = verify_extension_image_file(row, owners.get(name, []),
                                                   observed[name]["owner_states"].get(row["owners"][0]), prep)
            records.append({**details, "mapped_paths": sorted(aliases[name])})
        else:
            own = owners.get(name, [])
            require(len(own) == 1 and own[0] in pins,
                    "Mapped APT library has unreviewed/ambiguous ownership: " + name + " owners=" + repr(own))
            apt_groups.setdefault(own[0], set()).add(name)
    for package, wanted in sorted(apt_groups.items()):
        pin = pins[package]
        members = prep.inspect_deb(args.apt_archives / pin["filename"], pin, wanted=wanted)["selected"]
        for name, original in sorted(members.items()):
            actual = prep.read_regular(name, len(original))
            require(actual == original, "Mapped APT library differs from frozen archive: " + name)
            identity = prep.elf_identity(actual)
            records.append({"path": name, "mapped_paths": sorted(aliases[name]), "authority": "exact APT archive",
                            "owner": package, "version": pin["version"], "bytes": len(actual),
                            "sha256": prep.sha(actual), **identity})
    return {"status": "passed", "proc_maps_sha256": sha(args.out / "proc-self-maps.txt"),
            "mapped_files": sorted(records, key=lambda row: row["path"]),
            "apt_count": sum(row["authority"] == "exact APT archive" for row in records),
            "image_count": sum(row["authority"] == "pinned-image-aosp" for row in records),
            "extension_image_count": sum(row["authority"] == "pinned-image-aosp-extension" for row in records)}


def module_identity(module, distribution, lock):
    path = Path(module.__file__).resolve()
    frozen = {row["path"]: row for rows in lock["original_root_files"].values() for row in rows
              if row["kind"] == "file"}
    row = frozen.get(path.as_posix())
    require(row is not None and path.is_relative_to(SITE) and path.stat().st_size == row["bytes"]
            and sha(path) == row["sha256"], "Module origin is not an original installed file: " + str(path))
    require(importlib.metadata.version(distribution) ==
            next(r["version"] for r in lock["metadata"]["apt_distributions"] if r["name"] == distribution),
            "Actual distribution version differs: " + distribution)
    return {"module": module.__name__, "distribution": distribution, "path": str(path),
            "bytes": row["bytes"], "sha256": row["sha256"], "apt_package": row["package"]}


def pyarrow_case(args, lock):
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.lib as native
    require(np.__version__ == "2.5.4", "Original foundation NumPy changed")
    array = np.arange(6, dtype=np.int64)
    column = pa.array(array, from_pandas=False)
    require(column.buffers()[1].address == array.ctypes.data and
            np.array_equal(column.to_numpy(zero_copy_only=True), array), "NumPy zero-copy roundtrip differs")
    table = pa.table({"id": column, "text": ["zero", "one", "two", "cafe", "four", "five"]})
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    payload = sink.getvalue()
    require(pa.ipc.open_stream(payload).read_all().equals(table), "Arrow IPC stream roundtrip differs")
    file = args.out / "tiny-arrow-ipc.arrow"
    with pa.OSFile(str(file), "wb") as stream:
        with pa.ipc.new_file(stream, table.schema) as writer:
            writer.write_table(table)
    with pa.memory_map(str(file), "r") as source:
        require(pa.ipc.open_file(source).read_all().equals(table), "Arrow file/memory-map roundtrip differs")
    selected = pc.filter(column, pc.greater_equal(column, 3))
    require(selected.to_pylist() == [3, 4, 5] and pc.sum(selected).as_py() == 12,
            "Arrow compute filter/sum differs")
    require(pc.utf8_upper(pa.array(["caf\u00e9"])).to_pylist() == ["CAF\u00c9"],
            "Arrow Unicode compute differs")
    projected = ds.dataset(table).to_table(filter=ds.field("id") >= 3, columns=["id"])
    require(projected.column("id").to_pylist() == [3, 4, 5], "Arrow dataset projection/filter differs")
    return {"operations": ["NumPy zero-copy", "IPC stream", "IPC file/memory-map", "compute", "dataset filter/projection"],
            "rows": 6, "filtered_ids": [3, 4, 5], "sum": 12, "ipc_stream_bytes": payload.size,
            "modules": [module_identity(pa, "pyarrow", lock), module_identity(native, "pyarrow", lock)]}


def lxml_case(args, lock):
    from lxml import etree
    source = b'<root><item id="a">ONE</item><item id="b">TWO</item></root>'
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    document = etree.fromstring(source, parser)
    require(document.xpath("count(/root/item)") == 2.0 and document.xpath("/root/item/@id") == ["a", "b"],
            "Native XML/XPath result differs")
    style = etree.XML(b'<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
                      b'<xsl:output method="text"/><xsl:template match="/">'
                      b'<xsl:value-of select="/root/item[1]"/>|<xsl:value-of select="/root/item[2]"/>'
                      b'</xsl:template></xsl:stylesheet>')
    transform = etree.XSLT(style, access_control=etree.XSLTAccessControl.DENY_ALL)
    require(str(transform(document)) == "ONE|TWO", "Native XSLT result differs")
    return {"operations": ["XML parse", "XPath", "XSLT"], "xpath_count": 2, "xslt": "ONE|TWO",
            "modules": [module_identity(etree, "lxml", lock)]}


def msgpack_case(args, lock):
    import msgpack
    from msgpack import _cmsgpack
    require(msgpack.Packer.__module__ == "msgpack._cmsgpack" and
            msgpack.Unpacker.__module__ == "msgpack._cmsgpack", "Pure fallback replaced native Msgpack")
    value = {"n": 42, "text": "h\u00e9", "data": b"\x00\xff"}
    wire = msgpack.packb(value, use_bin_type=True)
    require(wire.hex() == "83a16e2aa474657874a368c3a9a464617461c40200ff", "Msgpack independent wire oracle differs")
    require(msgpack.unpackb(wire, raw=False) == value, "Native Msgpack roundtrip differs")
    expected = [value, [1, True, None, b"\x01"], {"last": -7}]
    stream = b"".join(msgpack.packb(v, use_bin_type=True) for v in expected)
    unpacker, actual = msgpack.Unpacker(raw=False), []
    for byte in stream:
        unpacker.feed(bytes((byte,)))
        actual.extend(unpacker)
    require(actual == expected, "Native Msgpack incremental stream differs")
    return {"operations": ["independent wire encoding", "roundtrip", "bytewise stream"], "frames": 3,
            "wire_hex": wire.hex(), "modules": [module_identity(_cmsgpack, "msgpack", lock)]}


def pillow_case(args, lock):
    from PIL import Image, _imaging
    require(Image.core is _imaging, "Pillow native core differs")
    pixels = bytes(range(24))
    source = Image.frombytes("RGBA", (3, 2), pixels)
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    payload = buffer.getvalue()
    require(payload.startswith(b"\x89PNG\r\n\x1a\n"), "Pillow did not emit PNG")
    with Image.open(io.BytesIO(payload)) as decoded:
        decoded.load()
        require(decoded.mode == "RGBA" and decoded.size == (3, 2) and decoded.tobytes() == pixels,
                "Pillow native PNG roundtrip differs")
        resized = decoded.resize((6, 4), Image.Resampling.NEAREST)
        expected = b"".join(pixels[((y // 2) * 3 + (x // 2)) * 4:((y // 2) * 3 + (x // 2)) * 4 + 4]
                            for y in range(4) for x in range(6))
        require(resized.tobytes() == expected, "Pillow independent nearest-resize oracle differs")
    return {"operations": ["native PNG encode/decode", "nearest resize"], "size": [3, 2],
            "resized": [6, 4], "png_bytes": len(payload),
            "modules": [module_identity(_imaging, "pillow", lock)]}


def psutil_case(args, lock):
    import psutil
    from psutil import _psutil_linux
    process = psutil.Process(os.getpid())
    proc = Path("/proc/self/stat").read_text()
    comm = proc.split("(", 1)[1].rsplit(")", 1)[0]
    require(process.pid == os.getpid() and process.ppid() == os.getppid()
            and process.uids().real == os.getuid(), "Own-process psutil identity differs")
    require(Path(process.exe()).resolve() == Path("/proc/self/exe").resolve()
            and process.name() == comm and process.is_running(), "Own /proc executable/name differs")
    memory, times = process.memory_info(), process.cpu_times()
    require(memory.rss > 0 and memory.rss % os.sysconf("SC_PAGE_SIZE") == 0
            and process.num_threads() >= 1 and times.user >= 0 and times.system >= 0,
            "Own-process native psutil measurements are invalid")
    return {"operations": ["own PID/PPID/UID", "own /proc executable/name", "RSS", "threads", "CPU time"],
            "pid": process.pid, "uid": os.getuid(), "rss": memory.rss, "name": comm,
            "modules": [module_identity(_psutil_linux, "psutil", lock)]}


def case_run(args, lock, prep, common, apt):
    require(args.case in CASES and os.getuid() == 1000, "Actual UID1000 native case required")
    apt.native_runtime(lock["metadata"]["runtime"])
    common.validate_foundation(args.foundation_receipt, lock)
    record = {"schema_version": 1, "component": args.case, "status": "failed",
              "model_downloaded": False, "engine_installed": False}
    try:
        record["behavior"] = globals()[args.case + "_case"](args, lock)
    except Exception as exc:
        record["error"] = {"stage": "behavior", "type": type(exc).__name__,
                           "message": str(exc), "traceback": traceback.format_exc()}
        traceback.print_exc()
    try:
        record["mappings"] = verify_mappings(args, lock, apt, prep)
    except Exception as exc:
        error = {"stage": "native-mapping-provenance", "type": type(exc).__name__,
                 "message": str(exc), "traceback": traceback.format_exc()}
        record["mapping_error"] = error
        record.setdefault("error", error)
        traceback.print_exc()
    observation_path = args.out / "MAPPED-LIBRARY-OBSERVATIONS.json"
    if observation_path.exists():
        record["mapping_observations"] = {"file": observation_path.name, "sha256": sha(observation_path),
                                          "admitted": False}
    if "error" not in record and "behavior" in record and record.get("mappings", {}).get("status") == "passed":
        record["status"] = "passed"
    save(args.out / "CASE-RESULT.json", record)
    require(record["status"] == "passed", "Actual native case failed: " + args.case)
    return record


def run_cases(args, lock, report):
    """Attempt all five independent cases; each command and receipt must still pass."""
    report["cases"] = []
    for name in CASES:
        target = args.out / name
        argv = [str(PREFIX / "bin/python"), "-I", "-B", str(Path(__file__).resolve()),
                "--inputs", str(args.inputs), "--apt-archives", str(args.apt_archives),
                "--foundation-receipt", str(args.foundation_receipt), "--out", str(target), "--case", name]
        child = command(argv, args.out, "case-" + name, lock["limits"]["native_case_seconds"], check=False)
        record = {"component": name, "status": "failed", "command": child}
        path = target / "CASE-RESULT.json"
        try:
            raw = path.read_bytes()
            record.update(receipt=name + "/CASE-RESULT.json", sha256=hashlib.sha256(raw).hexdigest())
            result = json.loads(raw)
            require(result.get("component") == name and result.get("status") in ("passed", "failed"),
                    "Native child receipt differs: " + name)
            record["child_status"] = result["status"]
            if result.get("error") is not None:
                record["child_error"] = result["error"]
            if child["status"] == "passed" and result["status"] == "passed":
                record["status"] = "passed"
        except Exception as exc:
            record["receipt_error"] = {"type": type(exc).__name__, "message": str(exc),
                                       "traceback": traceback.format_exc()}
        report["cases"].append(record)
    failed = [row["component"] for row in report["cases"] if row["status"] != "passed"]
    require(not failed, "Native APT extension cases failed: " + ", ".join(failed))


def run(args, lock, prep, common, apt, report):
    report["runtime"] = apt.native_runtime(lock["metadata"]["runtime"])
    require(os.getuid() == 1000 and os.environ.get("LD_PRELOAD") is None,
            "Actual unprivileged native runtime required")
    report["foundation"] = common.validate_foundation(args.foundation_receipt, lock)
    report["prepared_inputs"] = prep.verify_inputs(args.inputs)[1]
    report["archives"] = verify_archives(args, lock, prep)
    with tempfile.TemporaryDirectory(prefix="neutts-apt-extensions-", dir=PREFIX / "tmp") as temporary:
        work = Path(temporary)
        options, report["signed_index"] = signed_snapshot(args, lock, prep, work)
        report["installation"] = install_additions(args, lock, options)
    report["installed_apt_controls"] = apt.installed_control(lock["apt"]["provenance_packages"])
    report["original_files_before"] = verify_root_files(lock, apt, prep)
    report["image_runtime"] = validate_image_foundation(lock, args.foundation_receipt, common, apt)
    report["extension_image_runtime"] = validate_extension_image(args, lock, apt, prep)
    pip = command([str(PREFIX / "bin/python"), "-I", "-B", "-m", "pip", "check"],
                  args.out, "raw-pip-check", 60, expected=1)
    raw_log = args.out / "raw-pip-check.txt"
    with raw_log.open("xb") as stream:
        stream.write((args.out / pip["stdout"]["file"]).read_bytes())
        stream.write((args.out / pip["stderr"]["file"]).read_bytes())
    validation = {"schema_version": 1, "status": "failed", "exact_apt_distributions": 12,
                  "metadata_modified": False, "supported_tags_modified": False}
    try:
        apt.validate(lock["metadata"], args.apt_archives, raw_log, 1, validation)
    finally:
        save(args.out / "APT-EXTENSIONS-REQUIREMENTS.json", validation)
    report["requirements"] = {"status": validation["status"], "sha256": sha(args.out / "APT-EXTENSIONS-REQUIREMENTS.json"),
                              "apt_distributions": 12, "raw_pip_exit_code": 1, "raw_pip_passed": False}
    try:
        run_cases(args, lock, report)
    finally:
        report["original_files_after"] = verify_root_files(lock, apt, prep)
        require(report["original_files_before"] == report["original_files_after"],
                "Operation changed original APT files or metadata")
    report["status"] = "passed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path, required=True)
    parser.add_argument("--foundation-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args(argv)
    require(not args.out.exists() and not args.out.is_symlink() and args.out.absolute() == args.out.resolve(),
            "Use a fresh evidence directory without symlink ancestors")
    args.out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "failed", "scope": "Five APT extension prerequisites only",
              "model_downloaded": False, "engine_installed": False, "compiler_requested": False,
              "production_admission_changed": False, "metadata_modified": False,
              "supported_tags_modified": False, "speech_synthesis_tested": False, "published": False}
    try:
        prep, common, apt = support()
        lock, _ = prep.load_lock(args.inputs / prep.LOCK_FILENAME)
        report["lock_sha256"] = prep.LOCK_SHA256
        if args.case:
            case_run(args, lock, prep, common, apt)
        else:
            run(args, lock, prep, common, apt, report)
        if not args.case:
            save(args.out / RESULT, report)
        print(json.dumps({"status": "passed", "component": args.case or "five-APT-extensions", "out": str(args.out)}))
        return 0
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        if getattr(exc, "details", None) is not None:
            report["error"]["details"] = exc.details
        save(args.out / (RESULT if not args.case else "CASE-FAILURE.json"), report)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
