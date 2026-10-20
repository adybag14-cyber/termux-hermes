#!/usr/bin/env python3
"""Prepare a complete exact-source NeuTTS wheel experiment; no package installation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import time
import tomllib
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_SHA256 = "14acfdf2162c1d70cad30c2f6971655398241ba0014b37928c9059dff49424ac"
SUPPORT_SHA256 = "7e4abf6794f848d399d15a877e9c8a74db1a44ba5e87ceb898d5d4777169f744"


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def support():
    path = SCRIPT_DIR / "prepare_neutts_native_sources.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != SUPPORT_SHA256:
        raise RuntimeError("Reviewed source/wheel verifier changed")
    return module_at("_engine_wheel_source_support", path)


def load_lock():
    helper = support()
    raw = helper.read_regular(SCRIPT_DIR / "neutts_engine_wheel_lock.json", 50000)
    helper.require(helper.digest(raw) == LOCK_SHA256, "Engine-wheel input lock differs")
    lock = json.loads(raw)
    helper.require(lock["schema_version"] == 1, "Unsupported engine-wheel schema")
    for name, pin in lock["helpers"].items():
        data = helper.read_regular(SCRIPT_DIR.parent / name, pin["bytes"])
        helper.require(len(data) == pin["bytes"] and helper.digest(data) == pin["sha256"],
                       "Reviewed shared input differs: " + name)
    native, _ = helper.load_lock(SCRIPT_DIR / "neutts_native_sources_lock.json")
    selected = [p for p in native["additional_python_wheels"]
                if p["name"] in {"scikit-build-core", "packaging", "pathspec"}]
    helper.require(selected == lock["build"]["python_wheels"] and len(selected) == 3,
                   "The passed native three-wheel backend closure changed")
    helper.require(lock["build"]["cflags"] == native["build"]["cflags"]
                   and lock["target"] == native["target"], "The original native target changed")
    return lock, raw


def helpers(lock=None):
    lock = load_lock()[0] if lock is None else lock
    return (
        module_at("_engine_wheel_original_source", SCRIPT_DIR / "prepare_neutts_engine_source.py"),
        module_at("_engine_wheel_espeak_source", SCRIPT_DIR / "prepare_neutts_espeak_source.py"),
        module_at("_engine_wheel_native", SCRIPT_DIR / "compatibility_probe_neutts_native.py"),
        module_at("_engine_wheel_espeak_api", SCRIPT_DIR / "compatibility_probe_neutts_espeak.py"),
        module_at("_engine_wheel_apt", SCRIPT_DIR / "validate_neutts_apt_python.py"),
    )


def requirements_bytes(lock):
    return "".join(f"{p['name']}=={p['version']} --hash=sha256:{p['artifact']['sha256']}\n"
                   for p in lock["build"]["python_wheels"]).encode()


def build_graph(rows, environment):
    try:
        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.utils import canonicalize_name
        from packaging.version import Version
    except ImportError:
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.specifiers import SpecifierSet
        from pip._vendor.packaging.utils import canonicalize_name
        from pip._vendor.packaging.version import Version
    helper = support()
    selected = {p["name"]: p["version"] for p in rows}
    helper.require(len(selected) == len(rows), "Duplicate build distribution")
    edges = []
    for p in rows:
        helper.require(Version(environment["python_full_version"]) in SpecifierSet(p["requires_python"]),
                       "Build wheel excludes the actual interpreter")
        for text in p["declared_requires_dist"]:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            name = canonicalize_name(requirement.name)
            helper.require(not requirement.url and not requirement.extras,
                           "Unresolved URL or extra in the build closure")
            helper.require(name in selected and Version(selected[name]) in requirement.specifier,
                           "Unresolved active build requirement: " + text)
            edges.append({"parent": p["name"], "requirement": text, "name": name,
                          "selected_version": selected[name]})
    return edges


def verify_project(path, lock):
    helper = support()
    raw = helper.read_regular(path, 5000)
    expected = lock["engine_source"]
    helper.require(helper.digest(raw) == expected["unchanged_pyproject_sha256"],
                   "Original NeuTTS pyproject changed")
    project = tomllib.loads(raw.decode("utf-8"))
    helper.require(project["project"] == expected["project"]
                   and project["build-system"] == expected["build_system"]
                   and project["tool"]["scikit-build"]["wheel"]["packages"] == expected["wheel_packages"],
                   "Original NeuTTS metadata or package selection changed")
    return {"pyproject_sha256": helper.digest(raw),
            "requires_python": project["project"]["requires-python"],
            "base_requires_dist": project["project"]["dependencies"],
            "optional_dependencies": project["project"]["optional-dependencies"],
            "engine_install_attempted": False}


def verify_inputs(inputs):
    helper = support()
    lock, raw = load_lock()
    engine, espeak, _, _, _ = helpers(lock)
    helper.require(helper.read_regular(inputs / "engine-wheel-lock.json", len(raw)) == raw,
                   "Prepared engine-wheel lock differs")
    patch = lock["patch"]
    helper.require(helper.digest(helper.read_regular(inputs / "neutts-propagate-espeak-toolchain.patch",
                                                     patch["bytes"])) == patch["sha256"],
                   "Prepared compiler propagation patch differs")
    engine_result = engine.verify_inputs(inputs / "engine-source")
    artifact = lock["engine_source"]["artifact"]
    data = helper.read_regular(inputs / "engine-source" / artifact["filename"], artifact["bytes"])
    helper.require(len(data) == artifact["bytes"] and helper.digest(data) == artifact["sha256"],
                   "Prepared original NeuTTS archive differs")
    espeak_lock, native_lock = espeak.verify_inputs(inputs / "espeak-source")
    rows = json.loads(helper.read_regular(inputs / "wheel-source-manifest.json", 50000))
    source_result = helper.verify_source_tree(inputs / "source", rows,
                                              lock["engine_source"]["wheel_source_manifest"])
    original = json.loads(helper.read_regular(inputs / "engine-source/patched-source-manifest.json", 50000))
    before = {r["path"]: r for r in original}
    helper.require(len(rows) == len(original) == 56 and {r["path"] for r in rows} == set(before),
                   "A complete original source member was omitted")
    changes = {r["path"]: r for r in patch["changes"]}
    for row in rows:
        if row["path"] in changes:
            pin = changes[row["path"]]
            helper.require(before[row["path"]]["sha256"] == pin["before_sha256"]
                           and row["sha256"] == pin["after_sha256"], "Source patch identity differs")
        else:
            helper.require(row == before[row["path"]], "Unrelated original source member changed")
    project = verify_project(inputs / "source/pyproject.toml", lock)
    wheels = helper.core_verifier()
    wheel_paths = {p["artifact"]["filename"] for p in lock["build"]["python_wheels"]}
    wheels.check_file_set(inputs / "wheels", wheel_paths)
    wheel_results = [wheels.verify_wheel(inputs / "wheels" / p["artifact"]["filename"], p)
                     for p in lock["build"]["python_wheels"]]
    helper.require(helper.read_regular(inputs / "requirements.txt", 2000) == requirements_bytes(lock),
                   "Prepared hashed build requirements differ")
    expected_tsv = "".join("\t".join((p["name"], p["version"], p["architecture"], p["sha256"],
                                       str(p["bytes"]), p["filename"])) + "\n"
                           for p in native_lock["build_apt"]["packages"]).encode()
    helper.require(helper.read_regular(inputs / "build-apt-closure.tsv", 20000) == expected_tsv,
                   "Original 44-archive compiler closure changed")
    edges = build_graph(lock["build"]["python_wheels"], lock["build"]["marker_environment"])
    helper.require(len(edges) == lock["build"]["active_python_edge_count"] == 2,
                   "Active native build graph changed")
    return {"schema_version": 1, "status": "verified-exact-inputs", "lock_sha256": LOCK_SHA256,
            "engine_original_preparation": engine_result, "wheel_source": source_result,
            "espeak_source": espeak_lock["patched_manifest"], "project": project,
            "build_wheels": wheel_results, "active_build_edges": edges,
            "compiler_archives": len(native_lock["build_apt"]["packages"]),
            "scope_limits": lock["limits"]}


def copy_exact(source, destination, pin, helper):
    raw = helper.read_regular(source, pin["bytes"])
    helper.require(len(raw) == pin["bytes"] and helper.digest(raw) == pin["sha256"],
                   "Cached artifact identity differs")
    helper.require(not destination.exists() and not destination.is_symlink(), "Fresh artifact path required")
    with destination.open("xb") as stream:
        stream.write(raw)
    copied = helper.read_regular(destination, pin["bytes"])
    helper.require(copied == raw, "Artifact copy did not preserve exact bytes")


def prepare(output, *, engine_archive=None, espeak_archive=None, wheel_cache=None):
    helper = support()
    lock, raw = load_lock()
    engine, espeak, _, _, _ = helpers(lock)
    helper.require(not output.exists() and not output.is_symlink(), "Fresh preparation output required")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".engine-wheel-", dir=output.parent))
    try:
        engine.prepare(staging / "engine-source", engine_archive)
        espeak.prepare(staging / "espeak-source", espeak_archive)
        shutil.copytree(staging / "engine-source/source", staging / "source", symlinks=False)
        original = json.loads((staging / "engine-source/patched-source-manifest.json").read_bytes())
        patch = lock["patch"]
        patch_path = SCRIPT_DIR.parent / patch["path"]
        pin = {"patch": patch, "patched_manifest": lock["engine_source"]["wheel_source_manifest"]}
        rows = helper.apply_loader_patch(staging / "source", original, pin, patch_path,
                                          time.monotonic() + 45)
        (staging / "wheel-source-manifest.json").write_bytes(helper.canonical(rows))
        (staging / "engine-wheel-lock.json").write_bytes(raw)
        (staging / "neutts-propagate-espeak-toolchain.patch").write_bytes(
            helper.read_regular(patch_path, patch["bytes"]))
        (staging / "requirements.txt").write_bytes(requirements_bytes(lock))
        shutil.copyfile(staging / "espeak-source/build-apt-closure.tsv", staging / "build-apt-closure.tsv")
        (staging / "wheels").mkdir()
        wheels = helper.core_verifier()
        opener = urllib.request.build_opener(wheels.NoRedirect())
        deadline = time.monotonic() + 180
        for package in lock["build"]["python_wheels"]:
            artifact = package["artifact"]
            target = staging / "wheels" / artifact["filename"]
            if wheel_cache is not None:
                copy_exact(wheel_cache / artifact["filename"], target, artifact, helper)
            else:
                wheels.download_file(artifact, target, opener, deadline)
            wheels.verify_wheel(target, package)
        report = verify_inputs(staging)
        report.update(preparer_sha256=helper.digest(Path(__file__).read_bytes()),
                      source_patch_sha256=patch["sha256"], build_performed=False)
        (staging / "PREPARED-ENGINE-WHEEL.json").write_bytes(helper.canonical(report))
        helper.publish_modes(staging)
        helper.require(not output.exists() and not output.is_symlink(), "Output appeared during preparation")
        staging.rename(output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engine-archive", type=Path)
    parser.add_argument("--espeak-archive", type=Path)
    parser.add_argument("--wheel-cache", type=Path)
    args = parser.parse_args()
    result = prepare(args.out, engine_archive=args.engine_archive, espeak_archive=args.espeak_archive,
                     wheel_cache=args.wheel_cache)
    print(json.dumps({"status": result["status"], "out": str(args.out),
                      "source_files": result["wheel_source"]["file_count"]}, indent=2))
