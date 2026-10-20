#!/usr/bin/env python3
"""Prepare the complete frozen public Perth runtime without installing it.

This gate preserves the original 43-node/50-edge metadata closure. Four native
wheels are retained original build outputs; one separately reviewed Perth wheel
changes resource lookup only. APT payloads keep their original files and tags.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
from functools import lru_cache
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
LOCK_FILENAME = "neutts_perth_runtime_lock.json"
LOCK_SHA256 = "2396b2ff626aff9e422a3857e0cc1af2b6932ae9f13064ccbcdfd6a84a331fc6"
RECEIPT_FILENAME = "PERTH-PREPARED-INPUTS.json"
PREPARER_SHA256 = "6540cae859c390bdceed18aac315bf27559425262935d3e015ac99393bddc047"
APT_HELPER_SHA256 = "d7aacac1084448d544f4b78891acb72556a2a039ec5c4fd026ac1979b027d179"
SOUNDFILE_HELPER_SHA256 = "974eac261ad97b268c0f03f8abfe52c1b644635886b5a203729482c869c6de00"
RESOURCE_HELPER_SHA256 = "9fde6476fa3f5d793899943052e3b4f6ac4b1df991664e14d1bb846ef77eb752"
EXTRACT_HELPER_SHA256 = "96cae525e9c421f2e5fa820c386cfa18a52f3eca271f7e5be83754d0181c44a5"
SITE_PREFIX = "data/data/com.termux/files/usr/lib/python3.14/site-packages/"
MAX_APT_MEMBER_BYTES = 128 * 1024 * 1024
MAX_APT_PAYLOAD_BYTES = 256 * 1024 * 1024
MAX_APT_MEMBERS = 25000
MAX_LOCK_BYTES = 8 * 1024 * 1024
EXPECTED_NAMES = frozenset((
    "audioop-lts audioread certifi cffi charset-normalizer cloudpickle decorator "
    "filelock fsspec idna jinja2 joblib lazy-loader librosa llvmlite markupsafe "
    "mpmath msgpack narwhals networkx numba numpy packaging platformdirs pooch "
    "pycparser pyyaml requests resemble-perth scikit-learn scipy setuptools "
    "soundfile soxr standard-aifc standard-chunk standard-sunau sympy "
    "threadpoolctl torch torchaudio typing-extensions urllib3"
).split())
APT_NAMES = frozenset(("torch", "torchaudio", "numpy", "scipy", "llvmlite", "soxr", "msgpack"))
NATIVE_NAMES = frozenset(("audioop-lts", "pyyaml", "scikit-learn", "numba"))
MAIN_NAMES = frozenset(("certifi", "cffi", "charset-normalizer", "idna",
                        "packaging", "pycparser", "requests", "urllib3"))
FALSE_FLAGS = ("installed", "native_runtime_tested", "default_speech_model_downloaded",
               "production_admission_changed", "release_output")


class PrepareError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def read_regular(path, limit):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
            "Missing, linked, special or oversized input: " + str(path))
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    require(len(value) == info.st_size, "Input changed while being read")
    return value


def verified_bytes(path, pin):
    raw = read_regular(path, pin["bytes"])
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"],
            "Exact input identity differs: " + str(path))
    return raw


def safe_relative(value):
    return wheel_helper().safe_relative(value)


def write_new(path, raw):
    wheel_helper().write_new(Path(path), raw)


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def load_module(name, path, digest):
    raw = read_regular(path, MAX_LOCK_BYTES)
    require(sha(raw) == digest, "Reviewed support source changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Cannot load reviewed support")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def wheel_helper():
    return load_module("_perth_wheel_facts", SCRIPT_DIR / "prepare_neutts_nonrust_runtime.py",
                       PREPARER_SHA256)


def base_helper():
    return wheel_helper().base_helper()


@lru_cache(maxsize=1)
def apt_helper():
    return load_module("_perth_signed_apt", SCRIPT_DIR / "prepare_neutts_apt_snapshot.py",
                       APT_HELPER_SHA256)


@lru_cache(maxsize=1)
def soundfile_helper():
    return load_module("_perth_soundfile_derivative", SCRIPT_DIR / "prepare_neutts_soundfile.py",
                       SOUNDFILE_HELPER_SHA256)


@lru_cache(maxsize=1)
def resource_helper():
    return load_module("_perth_resource_derivative", SCRIPT_DIR / "prepare_neutts_perth_resource.py",
                       RESOURCE_HELPER_SHA256)


def wheel_facts(path, *, artifact=None):
    return wheel_helper().wheel_facts(path, artifact=artifact)


def verify_wheel(path, package):
    facts = wheel_facts(path, artifact=package["artifact"])
    require(all(facts[key] == package[key] for key in facts), "Reviewed wheel facts differ")
    return facts


def apt_python_payload(path, pin, *, include_bytes=False):
    """Read one exact original .deb using finite bounds for Torch/LLVM payloads.

    The 128 MiB member limit is local to this reader. The unchanged shared wheel
    and APT readers retain their smaller limits. Complete header and file
    manifests, including original metadata/RECORD, bind every copied byte.
    """
    raw = verified_bytes(path, pin)
    parts = dict(wheel_helper().ar_parts(raw))
    require(set(parts) in ({"debian-binary", "control.tar.xz", "data.tar.xz"},
                           {"debian-binary", "control.tar.gz", "data.tar.xz"},
                           {"debian-binary", "control.tar.gz", "data.tar.gz"})
            and parts["debian-binary"] == b"2.0\n", "Unreviewed Debian archive structure")
    control_data = next(v for k, v in parts.items() if k.startswith("control.tar."))
    payload = next(v for k, v in parts.items() if k.startswith("data.tar."))
    control_raw, controls, control_total = None, [], 0
    with tarfile.open(fileobj=io.BytesIO(control_data), mode="r|*") as archive:
        seen = set()
        for item in archive:
            name = item.name.removeprefix("./").rstrip("/")
            if name in ("", "."):
                require(item.isdir() and "." not in seen, "Invalid Debian control root")
                seen.add(".")
                continue
            safe_relative(name)
            require(name not in seen and len(seen) < 128 and item.isfile()
                    and 0 <= item.size <= 1024 * 1024, "Unsafe Debian control member")
            seen.add(name)
            control_total += item.size
            require(control_total <= 2 * 1024 * 1024, "Oversized Debian control inventory")
            value = archive.extractfile(item).read()
            require(len(value) == item.size, "Truncated Debian control member")
            controls.append({"path": name, "bytes": len(value), "sha256": sha(value),
                             "mode": format(item.mode, "04o")})
            if name == "control":
                require(control_raw is None, "Duplicate Debian control")
                control_raw = value
    require(control_raw is not None, "Missing Debian control")
    control = BytesParser(policy=compat32).parsebytes(control_raw)
    for field, key in (("Package", "name"), ("Version", "version"), ("Architecture", "architecture")):
        require(control.get_all(field, []) == [pin[key]], "APT control identity changed: " + field)
    for field, key in (("Depends", "depends"), ("Pre-Depends", "pre_depends")):
        values = control.get_all(field, [])
        require(len(values) <= 1, "Duplicate APT dependency field")
        if key in pin:
            require((values[0] if values else "") == pin[key], "Original APT dependencies changed")
    rows, contents, headers, seen, special = [], {}, [], set(), []
    total, data_bytes = 0, 0
    metadata_raw = wheel_raw = None
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r|*") as archive:
        for item in archive:
            name = item.name.removeprefix("./").rstrip("/")
            if name in ("", "."):
                require(item.isdir() and "." not in seen, "Invalid or duplicate APT root")
                seen.add(".")
                continue
            safe_relative(name)
            require(name not in seen and len(seen) < MAX_APT_MEMBERS, "Duplicate or excessive APT inventory")
            seen.add(name)
            require(item.isfile() or item.isdir() or item.issym() or item.islnk(),
                    "Unreviewed APT special member")
            require(0 <= item.size <= MAX_APT_MEMBER_BYTES, "APT member exceeds local finite bound")
            data_bytes += item.size
            require(data_bytes <= MAX_APT_PAYLOAD_BYTES, "APT expanded data exceeds local finite bound")
            headers.append({"path": name, "type": item.type.decode("ascii"), "bytes": item.size,
                            "mode": format(item.mode, "04o"), "link": item.linkname})
            if not name.startswith(SITE_PREFIX) or item.isdir():
                continue
            relative = safe_relative(name[len(SITE_PREFIX):])
            require(item.isfile(), "Unreviewed APT Python symlink or special member")
            total += item.size
            require(total <= MAX_APT_PAYLOAD_BYTES, "APT Python payload exceeds local finite bound")
            value = archive.extractfile(item).read()
            require(len(value) == item.size, "Truncated APT Python member")
            rows.append({"path": relative, "bytes": len(value), "sha256": sha(value),
                         "mode": "100755" if item.mode & 0o111 else "100644",
                         "archive_mode": format(item.mode, "04o")})
            if re.fullmatch(r"[^/]+\.dist-info/METADATA", relative):
                require(metadata_raw is None, "Multiple APT distributions")
                metadata_raw = value
            if re.fullmatch(r"[^/]+\.dist-info/WHEEL", relative):
                require(wheel_raw is None, "Multiple APT WHEEL declarations")
                wheel_raw = value
            if include_bytes:
                contents[relative] = value
    rows.sort(key=lambda row: row["path"])
    require(rows and len({r["path"].casefold() for r in rows}) == len(rows),
            "Empty or aliased APT Python payload")
    metadata = [r for r in rows if re.fullmatch(r"[^/]+\.dist-info/METADATA", r["path"])]
    require(len(metadata) == 1 and metadata_raw is not None and wheel_raw is not None,
            "APT Python archive lacks exactly one distribution")
    message = BytesParser(policy=compat32).parsebytes(metadata_raw)
    wheel = BytesParser(policy=compat32).parsebytes(wheel_raw)
    for field in ("Name", "Version"):
        require(len(message.get_all(field, [])) == 1, "Duplicate/missing APT metadata identity")
    require(len(message.get_all("Requires-Python", [])) <= 1, "Ambiguous APT Python bound")
    return {
        "archive": dict(pin), "control_sha256": sha(control_raw),
        "control_members_sha256": sha(json_bytes(sorted(controls, key=lambda row: row["path"]))),
        "data_headers_sha256": sha(json_bytes(headers)),
        "data_member_count": len(headers), "data_bytes": data_bytes,
        "files": rows, "file_count": len(rows), "bytes": total,
        "metadata_member": metadata[0]["path"], "metadata_sha256": metadata[0]["sha256"],
        "distribution": {"name": canonical_name(message["Name"]), "version": message["Version"],
                         "requires_dist": message.get_all("Requires-Dist", []),
                         "requires_python": message.get("Requires-Python", ""),
                         "wheel_sha256": sha(wheel_raw), "wheel_tags": wheel.get_all("Tag", [])},
    }, contents


def validate_lock(lock):
    require(lock.get("schema_version") == 1 and lock.get("node_count") == 43
            and lock.get("edge_count") == 50 and lock.get("selected_extras") == [],
            "Original Perth closure counts or extras changed")
    require(set(lock.get("names", [])) == EXPECTED_NAMES and len(lock["names"]) == 43,
            "Original Perth node set changed")
    require(len(lock["nodes"]) == 43 and {p["name"] for p in lock["nodes"]} == EXPECTED_NAMES
            and len(lock["edges"]) == 50, "Incomplete original dependency graph")
    require(len(lock["packages"]) == 36 and {p["name"] for p in lock["packages"]} == EXPECTED_NAMES - APT_NAMES
            and len(lock["apt_python"]) == 7 and {p["name"] for p in lock["apt_python"]} == APT_NAMES,
            "Complete 36-wheel/7-APT selection changed")
    nodes = {p["name"]: p for p in lock["nodes"]}
    for package in lock["packages"] + lock["apt_python"]:
        node = nodes[package["name"]]
        require(package["version"] == node["version"]
                and package["frozen_graph_requires_dist"] == node["requires_dist"]
                and package["requires_python"] == (node["requires_python"] or ""),
                "Original full dependency metadata or Python bounds changed")
    for kind, expected in (("main-catalog", MAIN_NAMES), ("native-handoff", NATIVE_NAMES)):
        require({p["name"] for p in lock["packages"] if p["origin"]["kind"] == kind} == expected,
                "Original wheel origin selection changed")
    soundfile = next(p for p in lock["packages"] if p["name"] == "soundfile")
    require(soundfile["origin"]["kind"] == "soundfile-android-derivative"
            and soundfile["artifact"] == soundfile_helper().load_lock()["derived_artifact"],
            "Reviewed SoundFile Android derivative changed")
    require([p["name"] for p in lock["apt_install"]] == ["libyaml", "python-msgpack"]
            and [p["name"] for p in lock["apt_provenance_only"]] == ["libgmp"],
            "Extra APT install/provenance boundary changed")
    require(lock["foundation_support_outside_graph"] == ["pip", "torchcodec"]
            and all(lock["boundaries"].get(name) is False for name in FALSE_FLAGS),
            "Preparation/admission boundary changed")
    require(lock["limits"] == {"apt_member_bytes": MAX_APT_MEMBER_BYTES,
                              "apt_payload_bytes": MAX_APT_PAYLOAD_BYTES,
                              "apt_members": MAX_APT_MEMBERS},
            "Reviewed local APT limits changed")
    return lock


def load_lock(path=None):
    path = Path(path) if path is not None else SCRIPT_DIR / LOCK_FILENAME
    raw = read_regular(path, MAX_LOCK_BYTES)
    require(sha(raw) == LOCK_SHA256, "Reviewed Perth runtime lock changed")
    lock = validate_lock(json.loads(raw))
    for pin in lock["source_files"]:
        safe_relative(pin["path"])
        verified_bytes(ROOT / pin["path"], pin)
    return lock, raw


def extra_apt_pins(lock):
    return lock["apt_install"] + lock["apt_provenance_only"]


def archive_path(directory, pin):
    return Path(directory) / apt_helper().archive_name(pin)


def extract_main(deb, lock, destination):
    """Select eight unchanged catalog members from the proven unpublished candidate."""
    tool = load_module("_perth_main_stream", SCRIPT_DIR / "extract_phonemizer_catalog.py",
                       EXTRACT_HELPER_SHA256)
    require(stat.S_ISREG(deb.lstat().st_mode) and deb.stat().st_size == lock["main_deb"]["bytes"]
            and tool.sha_file(deb) == lock["main_deb"]["sha256"], "Original main .deb identity differs")
    packages = [p for p in lock["packages"] if p["origin"]["kind"] == "main-catalog"]
    prefix = tool.PAYLOAD
    catalog_name = prefix + "bundled-wheels.json"
    wanted = {prefix + p["origin"]["catalog_record"]["file"]: p for p in packages}
    selected, data_count, names = {}, 0, set()
    with deb.open("rb") as stream:
        require(stream.read(8) == b"!<arch>\n", "Invalid main .deb header")
        while stream.tell() < lock["main_deb"]["bytes"]:
            header = stream.read(60)
            require(len(header) == 60 and header[58:] == b"\x60\n", "Invalid main ar header")
            size = int(header[48:58])
            name = header[:16].decode("ascii").strip().rstrip("/")
            require(name not in names and 0 <= size <= lock["main_deb"]["bytes"] - stream.tell(),
                    "Duplicate or oversized main ar member")
            names.add(name)
            end = stream.tell() + size + size % 2
            if name.startswith("data.tar."):
                data_count += 1
                seen = set()
                with tarfile.open(fileobj=tool.MemberStream(stream, size), mode="r|*") as archive:
                    for item in archive:
                        relative = item.name.removeprefix("./").rstrip("/")
                        if relative in ("", "."):
                            require(item.isdir(), "Invalid main tar root")
                            continue
                        safe_relative(relative)
                        require(relative not in seen and len(seen) < 100000,
                                "Duplicate or excessive main tar inventory")
                        seen.add(relative)
                        if relative != catalog_name and relative not in wanted:
                            continue
                        pin = lock["main_catalog"] if relative == catalog_name else wanted[relative]["artifact"]
                        require(item.isfile() and relative not in selected and item.size == pin["bytes"],
                                "Main selected member changed")
                        raw = archive.extractfile(item).read()
                        require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"],
                                "Main selected member bytes differ")
                        selected[relative] = raw
            stream.seek(end)
        require(stream.tell() == lock["main_deb"]["bytes"] and data_count == 1,
                "Unreviewed main .deb structure")
    require(set(selected) == set(wanted) | {catalog_name}, "Missing original main wheels/catalog")
    write_new(destination / "main-bundled-wheels.json", selected[catalog_name])
    for name, package in wanted.items():
        write_new(destination / "wheels" / package["artifact"]["filename"], selected[name])


def verified_catalog(path, lock):
    raw = verified_bytes(path, lock["main_catalog"])
    catalog = json.loads(raw)
    require(catalog.get("schema_version") == 1 and len(catalog["wheels"]) == 100,
            "Original complete main catalog changed")
    for package in lock["packages"]:
        if package["origin"]["kind"] == "main-catalog":
            expected = package["origin"]["catalog_record"]
            require([p for p in catalog["wheels"] if p["name"] == package["name"]] == [expected],
                    "Selected original catalog record changed")
    return raw


def receipt_for(lock, raw_lock, wheels, downloads):
    return {"schema_version": 1, "status": "verified-original-runtime-inputs",
            "scope": "Complete public Perth implicit API closure; no engine admission",
            "lock_sha256": sha(raw_lock), "node_count": 43, "active_edge_count": 50,
            "wheel_count": 36, "apt_python_payloads": 7, "wheels": wheels,
            "apt_downloads": downloads,
            "extra_apt_installs": ["libyaml", "python-msgpack"],
            "inherited_apt_verification_only": ["libgmp"],
            "foundation_support_outside_graph": ["pip", "torchcodec"],
            "embedded_public_watermark_checkpoint_present": True,
            **{name: False for name in FALSE_FLAGS}}


def verify_prepared_receipt(receipt, lock, raw_lock, wheels):
    extras = extra_apt_pins(lock)
    downloads = receipt.get("apt_downloads", [])
    require(len(downloads) == len(extras)
            and len({row.get("filename") for row in downloads}) == len(extras),
            "Duplicate/missing extra APT acquisition receipt")
    by_name = {apt_helper().archive_name(p): p for p in extras}
    for row in downloads:
        pin = by_name.get(row.get("filename"))
        require(pin is not None and row.get("bytes") == pin["bytes"]
                and row.get("sha256") == pin["sha256"]
                and row.get("origin_url") == apt_helper().ORIGIN + pin["filename"]
                and row.get("method") in ("verified-retained-cache", "original-https-archive"),
                "Extra APT acquisition provenance changed")
        if row["method"] == "original-https-archive":
            require(urllib.parse.urlsplit(row.get("effective_url", "")).scheme == "https",
                    "Insecure APT acquisition receipt")
        else:
            require(isinstance(row.get("cache_path"), str) and row["cache_path"],
                    "Missing retained APT descriptive path")
    require(receipt == receipt_for(lock, raw_lock, wheels, downloads), "Prepared receipt facts or boundaries changed")
    return receipt


def verify_inputs(directory, foundation_inputs=None):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Missing or linked prepared Perth inputs")
    lock, raw_lock = load_lock(directory / LOCK_FILENAME)
    expected = {LOCK_FILENAME, RECEIPT_FILENAME, "wheels", "apt-extra-archives",
                "main-bundled-wheels.json", "runtime-requirements.txt", "extra-install.tsv",
                "perth-resource-inputs", "soundfile-inputs"}
    require({p.name for p in directory.iterdir()} == expected, "Prepared Perth inventory changed")
    for name in ("wheels", "apt-extra-archives", "perth-resource-inputs", "soundfile-inputs"):
        require((directory / name).is_dir() and not (directory / name).is_symlink(),
                "Linked prepared Perth subdirectory")
    verified_catalog(directory / "main-bundled-wheels.json", lock)
    resource = resource_helper().verify_inputs(directory / "perth-resource-inputs")
    require(resource.get("installed") is False, "Perth resource receipt scope changed")
    soundfile = soundfile_helper().verify_inputs(directory / "soundfile-inputs")
    require(soundfile.get("installed") is False, "SoundFile derivative receipt scope changed")
    require({p.name for p in (directory / "wheels").iterdir()}
            == {p["artifact"]["filename"] for p in lock["packages"]}, "Prepared wheel inventory changed")
    wheels = [verify_wheel(directory / "wheels" / p["artifact"]["filename"], p) for p in lock["packages"]]
    derived = next(p for p in lock["packages"] if p["name"] == "resemble-perth")
    require(verified_bytes(directory / "wheels" / derived["artifact"]["filename"], derived["artifact"])
            == verified_bytes(directory / "perth-resource-inputs" / derived["artifact"]["filename"],
                              derived["artifact"]), "Perth runtime/resource derivative differs")
    soundfile_package = next(p for p in lock["packages"] if p["name"] == "soundfile")
    require(verified_bytes(directory / "wheels" / soundfile_package["artifact"]["filename"], soundfile_package["artifact"])
            == verified_bytes(directory / "soundfile-inputs" / soundfile_package["artifact"]["filename"],
                              soundfile_package["artifact"]), "SoundFile runtime/source derivative differs")
    extras = extra_apt_pins(lock)
    require({p.name for p in (directory / "apt-extra-archives").iterdir()}
            == {apt_helper().archive_name(p) for p in extras}, "Extra APT inventory changed")
    for pin in extras:
        verified_bytes(archive_path(directory / "apt-extra-archives", pin), pin)
    require(read_regular(directory / "runtime-requirements.txt", 100000)
            == base_helper().requirement_text(lock["packages"]), "Wheel install requirements changed")
    require(read_regular(directory / "extra-install.tsv", 10000)
            == apt_helper().pins_tsv(lock["apt_install"]), "Extra APT install set changed")
    receipt = json.loads(read_regular(directory / RECEIPT_FILENAME, 1000000))
    verify_prepared_receipt(receipt, lock, raw_lock, wheels)
    if foundation_inputs is not None:
        foundation_inputs = Path(foundation_inputs)
        original = apt_helper().verify_inputs(foundation_inputs)
        require(original["compiler_packages"] == 0, "Perth runtime does not require the compiler closure")
        apt_helper().verify_snapshot(foundation_inputs / "snapshot", extras)
        for package in lock["apt_python"]:
            pin = package["archive"]
            root = directory / "apt-extra-archives" if pin["name"] == "python-msgpack" else foundation_inputs / "apt-archives"
            facts, _ = apt_python_payload(archive_path(root, pin), pin)
            require(all(facts[k] == package[k] for k in facts), "Original full APT Python payload changed")
    return lock, receipt


def prepare(out, *, foundation_inputs, main_deb=None, main_wheelhouse=None, main_catalog=None,
            resource_inputs=None, caches=()):
    lock, raw_lock = load_lock()
    out = Path(os.path.abspath(out))
    require(not os.path.lexists(out) and out.parent.is_dir(), "Use a fresh output under an existing parent")
    require(not any(p.is_symlink() for p in (out.parent, *out.parent.parents)), "Linked output parent")
    original = apt_helper().verify_inputs(Path(foundation_inputs))
    require(original["compiler_packages"] == 0, "Unexpected compiler installation inputs")
    apt_helper().verify_snapshot(Path(foundation_inputs) / "snapshot", extra_apt_pins(lock))
    staging = Path(tempfile.mkdtemp(prefix="." + out.name + ".staging-", dir=out.parent))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), base_helper().NoRedirect())
    deadline = time.monotonic() + 900
    try:
        (staging / "wheels").mkdir()
        (staging / "apt-extra-archives").mkdir()
        if main_deb is not None:
            require(main_wheelhouse is None and main_catalog is None, "Ambiguous original main input")
            extract_main(Path(main_deb), lock, staging)
        else:
            require(main_wheelhouse is not None and main_catalog is not None, "Exact main .deb or catalog/wheels required")
            write_new(staging / "main-bundled-wheels.json", verified_catalog(Path(main_catalog), lock))
            for p in lock["packages"]:
                if p["origin"]["kind"] == "main-catalog":
                    write_new(staging / "wheels" / p["artifact"]["filename"],
                              verified_bytes(Path(main_wheelhouse) / p["artifact"]["filename"], p["artifact"]))
        if resource_inputs is not None:
            resource_helper().verify_inputs(Path(resource_inputs))
            shutil.copytree(resource_inputs, staging / "perth-resource-inputs")
        else:
            resource_helper().prepare(staging / "perth-resource-inputs")
        sf = soundfile_helper()
        sf_pin = sf.load_lock()["upstream_package"]["artifact"]
        sf.prepare(staging / "soundfile-inputs",
                   ROOT / "audit/neutts-soundfile-discovery-fix-20261020/original" / sf_pin["filename"])
        for package in lock["packages"]:
            if package["origin"]["kind"] == "main-catalog":
                continue
            artifact = package["artifact"]
            target = staging / "wheels" / artifact["filename"]
            kind = package["origin"]["kind"]
            if kind == "perth-resource-derivative":
                source = staging / "perth-resource-inputs" / artifact["filename"]
            elif kind == "soundfile-android-derivative":
                source = staging / "soundfile-inputs" / artifact["filename"]
            elif kind == "native-handoff":
                source = ROOT / package["origin"]["retained_path"]
            else:
                candidates = [Path(root) / artifact["filename"] for root in caches]
                source = next((p for p in candidates if os.path.lexists(p)), None)
            if source is not None:
                write_new(target, verified_bytes(source, artifact))
            else:
                base_helper().download_file(artifact, target, opener, deadline)
        downloads = []
        for pin in extra_apt_pins(lock):
            target = archive_path(staging / "apt-extra-archives", pin)
            downloads.append(apt_helper().acquire_archive(pin, target, [Path(p) for p in caches]))
        write_new(staging / LOCK_FILENAME, raw_lock)
        write_new(staging / "runtime-requirements.txt", base_helper().requirement_text(lock["packages"]))
        write_new(staging / "extra-install.tsv", apt_helper().pins_tsv(lock["apt_install"]))
        wheels = [verify_wheel(staging / "wheels" / p["artifact"]["filename"], p) for p in lock["packages"]]
        receipt = receipt_for(lock, raw_lock, wheels, downloads)
        write_new(staging / RECEIPT_FILENAME, json_bytes(receipt))
        verify_inputs(staging, Path(foundation_inputs))
        for path in (staging, *staging.rglob("*")):
            if path.is_dir():
                path.chmod(0o755)
        require(not os.path.lexists(out), "Output appeared during preparation")
        staging.rename(out)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--foundation-inputs", type=Path, required=True)
    parser.add_argument("--main-deb", type=Path)
    parser.add_argument("--main-wheelhouse", type=Path)
    parser.add_argument("--main-catalog", type=Path)
    parser.add_argument("--resource-inputs", type=Path)
    parser.add_argument("--cache", action="append", type=Path, default=[])
    args = parser.parse_args(argv)
    try:
        result = prepare(args.out, foundation_inputs=args.foundation_inputs, main_deb=args.main_deb,
                         main_wheelhouse=args.main_wheelhouse, main_catalog=args.main_catalog,
                         resource_inputs=args.resource_inputs, caches=args.cache)
    except (PrepareError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, type(exc).__name__ + ": " + str(exc) + "\n")
    print(json.dumps({"status": result["status"], "node_count": 43, "active_edge_count": 50,
                      "out": str(args.out)}))


if __name__ == "__main__":
    main()
