#!/usr/bin/env python3
"""Freeze the original 116 NeuTTS dependencies for a single offline native check.

This is a preparation gate. It does not install NeuTTS, alter its Python bound,
download speech models, or change production admission.
"""
from __future__ import annotations

import argparse
import base64
import csv
import functools
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
LOCK_FILENAME = "neutts_complete_runtime_lock.json"
RECEIPT_FILENAME = "COMPLETE-PREPARED-INPUTS.json"
LOCK_SHA256 = "7c05ccac08c2c7875b622ff9b1ef98731a9f72e1f5bf4312f58d63eb25d5eb7e"
PERTH_PREPARER_SHA256 = "7445bf89b0fd26f9f74a7935724e394b24b331409f200ecca9f2904ffacb40db"
NEUCODEC_PREPARER_SHA256 = "ea54baa56bbb9f9a82558233f68c4f2fca02c167e55f785ab3f31cf1cf980d7b"
GRAPH_SHA256 = "d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68"
APT_NAMES = frozenset(("llvmlite", "numpy", "scipy", "soxr", "torch", "torchaudio",
                      "msgpack", "lxml", "pillow", "psutil", "pyarrow"))
FALSE_FLAGS = ("neutts_engine_installed", "default_speech_model_downloaded",
               "production_admission_changed", "release_output")
MAX_LOCK_BYTES = 12 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@functools.lru_cache(maxsize=1)
def helper():
    path = SCRIPT_DIR / "prepare_neutts_perth_runtime.py"
    require(sha(path.read_bytes()) == PERTH_PREPARER_SHA256, "Reviewed bounded preparer changed")
    spec = importlib.util.spec_from_file_location("_complete_bounded_preparer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def neucodec_helper():
    path = SCRIPT_DIR / "prepare_neucodec_wheel.py"
    require(sha(path.read_bytes()) == NEUCODEC_PREPARER_SHA256, "Reviewed NeuCodec derivative preparer changed")
    spec = importlib.util.spec_from_file_location("_complete_neucodec_preparer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_name(value):
    return helper().canonical_name(value)


def safe_relative(value):
    """Use the reviewed wheel-path validator required by the shared inventory."""
    return helper().safe_relative(value)


def read_regular(path, limit=MAX_LOCK_BYTES):
    return helper().read_regular(path, limit)


def verified_bytes(path, pin):
    return helper().verified_bytes(path, pin)


def write_new(path, raw):
    return helper().write_new(path, raw)


def json_bytes(value):
    return helper().json_bytes(value)


def base_helper():
    return helper().base_helper()


def apt_helper():
    return helper().apt_helper()


def apt_python_payload(path, pin, include_bytes=False):
    return helper().apt_python_payload(path, pin, include_bytes=include_bytes)


def archive_path(directory, pin):
    return helper().archive_path(directory, pin)


def wheel_facts(path, artifact=None):
    return helper().wheel_facts(path, artifact=artifact)


def verify_wheel(path, package):
    return helper().verify_wheel(path, package)


def einx_documentation_bytes(lock):
    """Relocate one original documentation file without changing any runtime payload."""
    rule = lock["einx_documentation_relocation"]
    upstream = rule["upstream_package"]
    path = ROOT / rule["upstream_path"]
    verify_wheel(path, upstream)
    old = "docs/source/conf.py"
    new = "einx-0.4.3.data/data/share/doc/einx-0.4.3/source/conf.py"
    require(rule["relocations"] == {old: new}, "Unreviewed documentation relocation")
    record = upstream["wheel"]["record_member"]
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        before = {item.filename: archive.read(item) for item in infos}
    require(old in before and new not in before and len(infos) == len(before) == 131,
            "Original Einx member set changed")
    content = {new if name == old else name: body for name, body in before.items()}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name, _, _ in csv.reader(io.StringIO(before[record].decode("utf-8"))):
        target = new if name == old else name
        if name == record:
            writer.writerow((target, "", ""))
        else:
            body = content[target]
            writer.writerow((target, "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()).decode().rstrip("="), len(body)))
    content[record] = buffer.getvalue().encode("utf-8")
    require(all(content[new if name == old else name] == body
                for name, body in before.items() if name != record),
            "Documentation relocation changed an original payload")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for original in infos:
            name = new if original.filename == old else original.filename
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.create_version = item.extract_version = 20
            item.external_attr = original.external_attr
            item.internal_attr = 0
            item.compress_type = zipfile.ZIP_STORED
            archive.writestr(item, content[name])
    raw = output.getvalue()
    package = next(p for p in lock["packages"] if p["name"] == "einx")
    require(raw == verified_bytes(ROOT / package["origin"]["retained_path"], package["artifact"]),
            "Documentation derivative is not byte-reproducible")
    return raw


def torchao_compiler_import_bytes(lock):
    """Use the real relocated Torch compiler helpers, preserving every other payload."""
    rule = lock["torchao_compiler_import_compatibility"]
    upstream = rule["upstream_package"]
    path = ROOT / rule["upstream_path"]
    verify_wheel(path, upstream)
    target = "torchao/prototype/inductor/int8_sdpa_lowering.py"
    old = b"from torch._inductor.kernel.flex_attention import construct_strides, maybe_realize\n"
    new = (b"try:\n"
           b"    from torch._inductor.kernel.flex_attention import construct_strides, maybe_realize\n"
           b"except ModuleNotFoundError as error:\n"
           b"    if error.name != \"torch._inductor.kernel.flex_attention\":\n"
           b"        raise\n"
           b"    # Newer Torch keeps these same Inductor helpers in the flex subpackage.\n"
           b"    from torch._inductor.kernel.flex.common import construct_strides, maybe_realize\n")
    require(rule["target_member"] == target and rule["old_import"] == old.decode()
            and rule["new_import"] == new.decode(), "Unreviewed TorchAO import replacement")
    record = upstream["wheel"]["record_member"]
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        before = {item.filename: archive.read(item) for item in infos}
    require(len(infos) == len(before) == 422 and before[target].count(old) == 1,
            "Original TorchAO import or member set changed")
    content = dict(before)
    content[target] = before[target].replace(old, new)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name, _, _ in csv.reader(io.StringIO(before[record].decode("utf-8"))):
        if name == record:
            writer.writerow((name, "", ""))
        else:
            body = content[name]
            writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()).decode().rstrip("="), len(body)))
    content[record] = buffer.getvalue().encode("utf-8")
    require({name for name in before if before[name] != content[name]} == {target, record},
            "TorchAO compatibility derivative changed another original payload")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for original in infos:
            item = zipfile.ZipInfo(original.filename, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.create_version = item.extract_version = 20
            item.external_attr = original.external_attr
            item.internal_attr = 0
            item.compress_type = zipfile.ZIP_STORED
            archive.writestr(item, content[item.filename])
    raw = output.getvalue()
    package = next(p for p in lock["packages"] if p["name"] == "torchao")
    require(raw == verified_bytes(ROOT / package["origin"]["retained_path"], package["artifact"]),
            "TorchAO compatibility derivative is not byte-reproducible")
    return raw


def installed_target(member):
    """Map every wheel scheme into one Android-prefix-relative namespace."""
    parts = safe_relative(member).split("/")
    site = "lib/python3.14/site-packages/"
    if parts[0].endswith(".data"):
        require(len(parts) >= 3, "Malformed wheel data scheme")
        scheme, tail = parts[1], "/".join(parts[2:])
        require(scheme in ("purelib", "platlib", "scripts", "data"), "Unreviewed wheel data scheme")
        return {"purelib": site, "platlib": site, "scripts": "bin/", "data": ""}[scheme] + tail
    return site + "/".join(parts)


def validate_install_targets(directory, packages, apt_python):
    """Reject duplicate installed file owners before invoking the real installer."""
    owners = {}
    def claim(target, owner, member):
        require(target not in owners, "Installed target has multiple file owners: "
                + target + " (" + str(owners.get(target)) + ", " + owner + ":" + member + ")")
        owners[target] = owner + ":" + member
    for package in packages:
        with zipfile.ZipFile(Path(directory) / package["artifact"]["filename"]) as archive:
            for item in archive.infolist():
                if not item.is_dir():
                    claim(installed_target(item.filename), package["name"], item.filename)
    for package in apt_python:
        for item in package["files"]:
            target = "lib/python3.14/site-packages/" + safe_relative(item["path"])
            claim(target, package["name"], item["path"])
    for target in owners:
        parts = target.split("/")
        require(not any("/".join(parts[:i]) in owners for i in range(1, len(parts))),
                "Installed file also owns a parent directory: " + target)
    return {"status": "unique-installed-file-owners", "wheel_count": len(packages),
            "apt_python_payloads": len(apt_python), "target_count": len(owners),
            "target_owners_sha256": sha(json_bytes(owners)), "duplicate_file_owners": 0}


def requirement_key(value):
    try:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
    except ImportError:
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.utils import canonicalize_name
    req = Requirement(value)
    return (canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)),
            str(req.marker or ""), req.url)


def original_graph():
    path = SCRIPT_DIR / "neutts_runtime_closure_design.json"
    raw = read_regular(path, 1024 * 1024)
    require(sha(raw) == GRAPH_SHA256, "Original 117-node graph changed")
    value = json.loads(raw)
    require(value["node_count"] == 117 and value["edge_count"] == 194,
            "Original graph counts changed")
    nodes = [{k: n[k] for k in ("name", "version", "requires_python", "requires_dist",
                               "active_extras", "metadata_source", "route")}
             for n in value["nodes"] if n["name"] != "neutts"]
    edges = [e for e in value["edges"] if e["from"] != "neutts"]
    engine = next(n for n in value["nodes"] if n["name"] == "neutts")
    require(engine["requires_python"] == "<3.14,>=3.10"
            or engine["requires_python"] == ">=3.10,<3.14",
            "Original engine Python boundary changed")
    require(len(nodes) == 116 and len(edges) == 183
            and all(e["to"] != "neutts" for e in edges),
            "Only the original engine may be outside the dependency environment")
    return nodes, edges, value["environment"], engine


def validate_closure(lock, distributions=None, environment=None):
    """Re-evaluate every original clause, including fsspec[http], on Android."""
    try:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except ImportError:
        from pip._vendor.packaging.markers import default_environment
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.specifiers import SpecifierSet
        from pip._vendor.packaging.version import Version
    import importlib.metadata
    actual = default_environment() if environment is None else dict(environment)
    actual["extra"] = ""
    require(all(actual.get(k) == v for k, v in lock["environment"].items()),
            "Actual marker environment differs from the frozen Android environment")
    if distributions is None:
        rows = list(importlib.metadata.distributions())
        distributions = {canonical_name(d.metadata["Name"]): {
            "version": d.version, "requires_dist": d.metadata.get_all("Requires-Dist", []),
            "requires_python": d.metadata.get("Requires-Python")}
            for d in rows}
        require(len(rows) == len(distributions), "Duplicate visible runtime distribution")
    require(set(distributions) == set(lock["names"]), "Incomplete or extra complete-runtime node")
    nodes = {n["name"]: n for n in lock["nodes"]}
    active = []
    for name, dist in distributions.items():
        original = nodes[name]
        require(dist["version"] == original["version"], "Original dependency version changed: " + name)
        # Empty/absent metadata is normalized for comparison only; no metadata is rewritten.
        require(bool(dist["requires_python"]) == bool(original["requires_python"])
                and SpecifierSet(dist["requires_python"] or "")
                == SpecifierSet(original["requires_python"] or "")
                and sorted(map(requirement_key, dist["requires_dist"]))
                == sorted(map(requirement_key, original["requires_dist"])),
                "Original metadata or Python bound changed: " + name)
        require(Version(actual["python_full_version"]) in SpecifierSet(dist["requires_python"] or ""),
                "Actual Python violates an original bound: " + name)
        for declaration in dist["requires_dist"]:
            req = Requirement(declaration)
            contexts = ["", *original["active_extras"]]
            if req.marker is not None and not any(req.marker.evaluate({**actual, "extra": extra})
                                                  for extra in contexts):
                continue
            target = canonical_name(req.name)
            require(req.url is None and target in distributions,
                    "Active direct URL or missing dependency: " + name)
            require(set(req.extras) <= set(nodes[target]["active_extras"]),
                    "Required dependency extra was omitted: " + name)
            require(Version(distributions[target]["version"]) in req.specifier,
                    "Original dependency version constraint fails: " + name)
            active.append((name, target, requirement_key(declaration)))
    expected = [(e["from"], e["to"], requirement_key(e["requirement"])) for e in lock["edges"]]
    require(len(active) == 183 and sorted(active) == sorted(expected),
            "Original 183 active dependency clauses changed")
    return {"status": "passed", "node_count": 116, "active_edge_count": 183,
            "selected_extras": {"fsspec": ["http"]}, "metadata_modified": False,
            "actual_marker_environment": actual, "global_site_visible": False,
            "neutts_engine_installed": False}


def validate_lock(lock):
    nodes, edges, environment, engine = original_graph()
    require(lock.get("schema_version") == 1 and lock.get("node_count") == 116
            and lock.get("edge_count") == 183 and lock.get("wheel_count") == 105,
            "Complete dependency counts changed")
    require(lock.get("nodes") == nodes and lock.get("edges") == edges
            and lock.get("names") == sorted(n["name"] for n in nodes)
            and lock.get("environment") == {**environment, "extra": ""}
            and lock.get("selected_extras") == {"fsspec": ["http"]},
            "Original dependency graph or selected extras changed")
    require(lock.get("excluded_engine") == {
        "name": "neutts", "version": engine["version"],
        "requires_python": engine["requires_python"], "installed": False},
        "Original engine boundary was changed")
    packages = lock["packages"]
    apt_python = lock["apt_python"]
    require(len(packages) == 105 and len(apt_python) == 11
            and {p["name"] for p in apt_python} == APT_NAMES
            and len({p["name"] for p in packages + apt_python}) == 116
            and {p["name"] for p in packages} == set(lock["names"]) - APT_NAMES,
            "Complete 105-wheel/11-APT inventory changed")
    for package in packages + apt_python:
        node = next(n for n in nodes if n["name"] == package["name"])
        require(package["version"] == node["version"]
                and package["frozen_graph_requires_dist"] == node["requires_dist"],
                "An original full dependency declaration was dropped")
    codec = next(p for p in packages if p["name"] == "neucodec")
    require(codec["origin"]["kind"] == "neucodec-hub1-derivative"
            and codec["artifact"] == neucodec_helper().load_lock()["derived_artifact"],
            "Reviewed NeuCodec Hub compatibility derivative changed")
    docs = lock["einx_documentation_relocation"]
    einx = next(p for p in packages if p["name"] == "einx")
    original = docs["upstream_package"]
    require(original["artifact"]["sha256"]
            == "47ce54a0144f6dffcfacdd8fe2cc9e2e5e6485dda2471330ab75ee747dd22f39"
            and docs["relocations"] == {"docs/source/conf.py":
                "einx-0.4.3.data/data/share/doc/einx-0.4.3/source/conf.py"}
            and einx["origin"]["kind"] == "einx-documentation-derivative"
            and all(einx[k] == original[k] for k in ("name", "version", "requires_python", "requires_dist",
                    "base_requires_dist", "frozen_graph_requires_dist", "native_members"))
            and all(einx["wheel"][k] == original["wheel"][k]
                    for k in ("metadata_sha256", "wheel_sha256", "file_count")),
            "Original Einx metadata, runtime boundary or reviewed docs relocation changed")
    compiler = lock["torchao_compiler_import_compatibility"]
    ao = next(p for p in packages if p["name"] == "torchao")
    original_ao = compiler["upstream_package"]
    provider = compiler["torch_provider"]
    torch = next(p for p in apt_python if p["name"] == "torch")
    require(original_ao["artifact"]["sha256"]
            == "103f2a9164d2e4f705332af1aafbb8473eadd14d9164e45857ca187cde1f13d2"
            and ao["origin"]["kind"] == "torchao-compiler-import-derivative"
            and all(ao[k] == original_ao[k] for k in ("name", "version", "requires_python", "requires_dist",
                    "base_requires_dist", "frozen_graph_requires_dist", "native_members"))
            and all(ao["wheel"][k] == original_ao["wheel"][k]
                    for k in ("metadata_sha256", "wheel_sha256", "file_count", "entry_count"))
            and provider["archive"] == torch["archive"]
            and provider["member"] == "torch/_inductor/kernel/flex/common.py"
            and provider["sha256"] == "d20df6180978954f79a576f20b32a021558318f0c53d2c7c3bb8164edfa1918d"
            and any(f["path"] == provider["member"] and f["sha256"] == provider["sha256"]
                    and f["bytes"] == provider["bytes"] for f in torch["files"]),
            "Original TorchAO metadata or real Torch compiler provider changed")
    metadata = {p["name"]: {k: p[k] for k in ("version", "requires_dist", "requires_python")}
                for p in packages + apt_python}
    validate_closure(lock, metadata, lock["environment"])
    require(len(lock["apt_install"]) == 19
            and len({p["name"] for p in lock["apt_install"]}) == 19
            and [p["name"] for p in lock["apt_provenance_only"]] == ["libgmp"]
            and lock["foundation"]["archive_count"] == 122,
            "Original native APT scope changed")
    require(all(lock["boundaries"].get(flag) is False for flag in FALSE_FLAGS)
            and lock["foundation_support_outside_graph"] == ["pip", "torchcodec"],
            "Complete dependency admission boundary changed")
    require(lock["assets"]["engine_installed"] is False
            and lock["assets"]["distribution_metadata_extracted"] is False
            and lock["assets"]["library"]["sha256"]
            == "21f4f416325fb3a9d6de07553cb9b9ea53973e9e2d9d008d02e34614732c2a55"
            and len(lock["assets"]["data"]) == 371,
            "Reviewed eSpeak asset-only handoff changed")
    return lock


def load_lock(path=None):
    raw = read_regular(Path(path) if path else SCRIPT_DIR / LOCK_FILENAME)
    require(isinstance(LOCK_SHA256, str) and len(LOCK_SHA256) == 64
            and sha(raw) == LOCK_SHA256, "Complete runtime lock is not finalized or changed")
    lock = validate_lock(json.loads(raw))
    for pin in lock["source_files"]:
        helper().safe_relative(pin["path"])
        verified_bytes(ROOT / pin["path"], pin)
    return lock, raw


def extra_apt_pins(lock):
    return lock["apt_install"] + lock["apt_provenance_only"]


def asset_rows(lock):
    assets = lock["assets"]
    return [assets["library"], *assets["data"], *assets["licenses"]]


def prepare_assets(destination, lock):
    assets = lock["assets"]
    archive = ROOT / assets["source_wheel"]["path"]
    verified_bytes(archive, assets["source_wheel"])
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, "Source eSpeak asset wheel CRC failed")
        for row in asset_rows(lock):
            helper().safe_relative(row["path"])
            require(not row["path"].endswith(".py") and ".dist-info/" not in row["path"],
                    "Asset-only handoff attempted to copy engine code or metadata")
            if "source_path" in row:
                helper().safe_relative(row["source_path"])
                raw = verified_bytes(ROOT / row["source_path"], row)
            else:
                helper().safe_relative(row["member"])
                raw = z.read(row["member"])
            require(len(raw) == row["bytes"] and sha(raw) == row["sha256"],
                    "Original eSpeak asset changed")
            write_new(destination / row["path"], raw)


def verify_assets(directory, lock):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Missing or linked eSpeak assets")
    actual = []
    for p in directory.rglob("*"):
        require(not p.is_symlink(), "Linked eSpeak asset")
        if p.is_file():
            actual.append(p.relative_to(directory).as_posix())
        else:
            require(p.is_dir(), "Special eSpeak asset")
    rows = asset_rows(lock)
    require(sorted(actual) == sorted(r["path"] for r in rows), "eSpeak asset inventory changed")
    for row in rows:
        verified_bytes(directory / row["path"], row)
    return {"status": "passed", "data_files": 371, "library_sha256": lock["assets"]["library"]["sha256"],
            "licenses": len(lock["assets"]["licenses"]), "engine_installed": False,
            "distribution_metadata_extracted": False}


def receipt_for(lock, raw, wheels, downloads, targets):
    return {"schema_version": 1, "status": "verified-complete-dependency-inputs",
            "lock_sha256": sha(raw), "node_count": 116, "active_edge_count": 183,
            "wheel_count": 105, "apt_python_payloads": 11, "wheels": wheels,
            "installed_target_ownership": targets,
            "apt_downloads": downloads, "extra_apt_installs": [p["name"] for p in lock["apt_install"]],
            "inherited_apt_verification_only": ["libgmp"],
            "foundation_support_outside_graph": ["pip", "torchcodec"],
            "installed": False, "native_runtime_tested": False,
            **{flag: False for flag in FALSE_FLAGS}}


def verify_inputs(directory, foundation_inputs=None):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Missing or linked complete inputs")
    lock, raw = load_lock(directory / LOCK_FILENAME)
    expected = {LOCK_FILENAME, RECEIPT_FILENAME, "wheels", "apt-extra-archives",
                "main-bundled-wheels.json", "runtime-requirements.txt", "extra-install.tsv",
                "perth-resource-inputs", "soundfile-inputs", "neucodec-inputs", "espeak-assets"}
    require({p.name for p in directory.iterdir()} == expected, "Complete input inventory changed")
    for name in ("wheels", "apt-extra-archives", "perth-resource-inputs", "soundfile-inputs", "neucodec-inputs", "espeak-assets"):
        require((directory / name).is_dir() and not (directory / name).is_symlink(),
                "Linked prepared input directory")
    helper().verified_catalog(directory / "main-bundled-wheels.json", lock)
    helper().resource_helper().verify_inputs(directory / "perth-resource-inputs")
    helper().soundfile_helper().verify_inputs(directory / "soundfile-inputs")
    neucodec_helper().verify_inputs(directory / "neucodec-inputs")
    verify_assets(directory / "espeak-assets", lock)
    require({p.name for p in (directory / "wheels").iterdir()}
            == {p["artifact"]["filename"] for p in lock["packages"]}, "Complete wheel set changed")
    wheels = [verify_wheel(directory / "wheels" / p["artifact"]["filename"], p) for p in lock["packages"]]
    einx = next(p for p in lock["packages"] if p["name"] == "einx")
    require(read_regular(directory / "wheels" / einx["artifact"]["filename"], 2 * 1024 * 1024)
            == einx_documentation_bytes(lock), "Prepared Einx documentation derivative changed")
    ao = next(p for p in lock["packages"] if p["name"] == "torchao")
    require(read_regular(directory / "wheels" / ao["artifact"]["filename"], 8 * 1024 * 1024)
            == torchao_compiler_import_bytes(lock), "Prepared TorchAO compiler derivative changed")
    targets = validate_install_targets(directory / "wheels", lock["packages"], lock["apt_python"])
    for name, subdir in (("resemble-perth", "perth-resource-inputs"), ("soundfile", "soundfile-inputs"),
                         ("neucodec", "neucodec-inputs")):
        p = next(p for p in lock["packages"] if p["name"] == name)
        require(verified_bytes(directory / "wheels" / p["artifact"]["filename"], p["artifact"])
                == verified_bytes(directory / subdir / p["artifact"]["filename"], p["artifact"]),
                "Derived runtime wheel differs from its original deterministic preparation")
    extras = extra_apt_pins(lock)
    require({p.name for p in (directory / "apt-extra-archives").iterdir()}
            == {apt_helper().archive_name(p) for p in extras}, "Extra APT input set changed")
    for pin in extras:
        verified_bytes(archive_path(directory / "apt-extra-archives", pin), pin)
    require(read_regular(directory / "runtime-requirements.txt", 100000)
            == base_helper().requirement_text(lock["packages"])
            and read_regular(directory / "extra-install.tsv", 20000)
            == apt_helper().pins_tsv(lock["apt_install"]), "Exact offline install request changed")
    receipt = json.loads(read_regular(directory / RECEIPT_FILENAME, 4000000))
    downloads = receipt.get("apt_downloads", [])
    require(len(downloads) == len(extras) and len({p.get("filename") for p in downloads}) == len(extras),
            "Duplicate or incomplete APT acquisition receipt")
    pins = {apt_helper().archive_name(p): p for p in extras}
    for row in downloads:
        pin = pins.get(row.get("filename"))
        require(pin is not None and row.get("bytes") == pin["bytes"] and row.get("sha256") == pin["sha256"]
                and row.get("origin_url") == apt_helper().ORIGIN + pin["filename"]
                and row.get("method") in ("verified-retained-cache", "original-https-archive"),
                "Original APT acquisition provenance changed")
    require(receipt == receipt_for(lock, raw, wheels, downloads, targets), "Prepared input receipt changed")
    if foundation_inputs is not None:
        foundation_inputs = Path(foundation_inputs)
        foundation = apt_helper().verify_inputs(foundation_inputs)
        require(foundation["compiler_packages"] == 0, "Compiler closure is outside this runtime")
        apt_helper().verify_snapshot(foundation_inputs / "snapshot", extras)
        extra_names = {p["name"] for p in extras}
        for p in lock["apt_python"]:
            pin = p["archive"]
            root = directory / "apt-extra-archives" if pin["name"] in extra_names else foundation_inputs / "apt-archives"
            facts, _ = apt_python_payload(archive_path(root, pin), pin)
            require(all(facts[k] == p[k] for k in facts), "Original APT Python payload changed")
    return lock, receipt


def prepare(out, *, foundation_inputs, main_deb=None, main_wheelhouse=None, main_catalog=None, caches=()):
    lock, raw = load_lock()
    out = Path(os.path.abspath(out))
    require(not os.path.lexists(out) and out.parent.is_dir(), "Use a fresh output under an existing parent")
    require(not any(p.is_symlink() for p in (out.parent, *out.parent.parents)), "Linked output parent")
    foundation = apt_helper().verify_inputs(Path(foundation_inputs))
    require(foundation["compiler_packages"] == 0, "Compiler closure is outside this runtime")
    apt_helper().verify_snapshot(Path(foundation_inputs) / "snapshot", extra_apt_pins(lock))
    staging = Path(tempfile.mkdtemp(prefix="." + out.name + ".staging-", dir=out.parent))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), base_helper().NoRedirect())
    deadline = time.monotonic() + 1800
    try:
        (staging / "wheels").mkdir()
        (staging / "apt-extra-archives").mkdir()
        if main_deb is not None:
            require(main_wheelhouse is None and main_catalog is None, "Ambiguous original main input")
            helper().extract_main(Path(main_deb), lock, staging)
        else:
            require(main_wheelhouse is not None and main_catalog is not None, "Original main inputs required")
            write_new(staging / "main-bundled-wheels.json", helper().verified_catalog(Path(main_catalog), lock))
            for p in lock["packages"]:
                if p["origin"]["kind"] == "main-catalog":
                    write_new(staging / "wheels" / p["artifact"]["filename"],
                              verified_bytes(Path(main_wheelhouse) / p["artifact"]["filename"], p["artifact"]))
        helper().resource_helper().prepare(staging / "perth-resource-inputs")
        sf = helper().soundfile_helper()
        sf_pin = sf.load_lock()["upstream_package"]["artifact"]
        sf.prepare(staging / "soundfile-inputs",
                   ROOT / "audit/neutts-soundfile-discovery-fix-20261020/original" / sf_pin["filename"])
        neucodec_helper().prepare(staging / "neucodec-inputs")
        prepare_assets(staging / "espeak-assets", lock)
        for p in lock["packages"]:
            kind, artifact = p["origin"]["kind"], p["artifact"]
            if kind == "main-catalog":
                continue
            if kind == "torchao-compiler-import-derivative":
                write_new(staging / "wheels" / artifact["filename"], torchao_compiler_import_bytes(lock))
                continue
            if kind == "einx-documentation-derivative":
                write_new(staging / "wheels" / artifact["filename"], einx_documentation_bytes(lock))
                continue
            derivatives = {"perth-resource-derivative": "perth-resource-inputs",
                           "soundfile-android-derivative": "soundfile-inputs",
                           "neucodec-hub1-derivative": "neucodec-inputs"}
            if kind in derivatives:
                source = staging / derivatives[kind] / artifact["filename"]
            elif kind == "native-handoff":
                source = ROOT / p["origin"]["retained_path"]
            else:
                source = next((Path(c) / artifact["filename"] for c in caches
                               if os.path.lexists(Path(c) / artifact["filename"])), None)
            target = staging / "wheels" / artifact["filename"]
            if source is not None:
                write_new(target, verified_bytes(source, artifact))
            else:
                base_helper().download_file(artifact, target, opener, deadline)
        downloads = [apt_helper().acquire_archive(pin, archive_path(staging / "apt-extra-archives", pin),
                                                  [Path(p) for p in caches])
                     for pin in extra_apt_pins(lock)]
        write_new(staging / LOCK_FILENAME, raw)
        write_new(staging / "runtime-requirements.txt", base_helper().requirement_text(lock["packages"]))
        write_new(staging / "extra-install.tsv", apt_helper().pins_tsv(lock["apt_install"]))
        wheels = [verify_wheel(staging / "wheels" / p["artifact"]["filename"], p) for p in lock["packages"]]
        targets = validate_install_targets(staging / "wheels", lock["packages"], lock["apt_python"])
        receipt = receipt_for(lock, raw, wheels, downloads, targets)
        write_new(staging / RECEIPT_FILENAME, json_bytes(receipt))
        verify_inputs(staging, foundation_inputs)
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
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--foundation-inputs", type=Path, required=True)
    parser.add_argument("--main-deb", type=Path)
    parser.add_argument("--main-wheelhouse", type=Path)
    parser.add_argument("--main-catalog", type=Path)
    parser.add_argument("--cache", action="append", default=[], type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        _, result = verify_inputs(args.verify, args.foundation_inputs)
    else:
        require(args.out is not None, "An owned new output is required")
        result = prepare(args.out, foundation_inputs=args.foundation_inputs, main_deb=args.main_deb,
                         main_wheelhouse=args.main_wheelhouse, main_catalog=args.main_catalog, caches=args.cache)
    print(json.dumps({"status": result["status"], "node_count": 116, "active_edge_count": 183,
                      **{flag: False for flag in FALSE_FLAGS}}, sort_keys=True))


if __name__ == "__main__":
    main()
