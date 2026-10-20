"""Review the exact captured Tiktoken lock and reconstruct its original crate directory source.

This is a host integrity replay, not a native source build or root admission.
"""
from __future__ import annotations
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import tomllib
import zipfile

ROOT = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT = ROOT / "audit/neutts-rust-native-20261017/run-39084939992"
BASE = ROOT.parent / "neutts-rust-native-evidence-20261017/39084939992"
EXTRACTED = BASE / "extracted-termux-neutts-rust-tiktoken-lock"
ARCHIVE = BASE / "artifact-12119853598-assembled.zip"
OUTPUT = BASE / "reviewed-tiktoken-reconstruction-v1"
ARTIFACT_SHA = "7c8fe4aabb20e0dcc6eb4f450c08a4ca087f0db0d734f55ba177d4e6d5a6b9c8"
PARENT_SHA = "de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670"
PREPARER_SHA = "db8ce00daaece15f69b4f7b1de415accd207f13e256b2097d4efcb2d0894c428"
LOCK_SHA = "44c9797be677b8af84478a3d54d09ac34d5a654e4ed8ee3e36a871415bc3dd80"

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def sha_file(path):
    require(path.is_file() and not path.is_symlink(), "Missing or linked expected file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def identity(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha_file(path)}

def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return identity(path)

def relative(path):
    return path.relative_to(ROOT).as_posix()

def main():
    require(not OUTPUT.exists(), "Refuse existing owned reconstruction output")
    require(ARCHIVE.stat().st_size == 270247477 and sha_file(ARCHIVE) == ARTIFACT_SHA,
            "Whole captured artifact identity differs")
    preparer_path = ROOT / "scripts/prepare_neutts_rust_sources.py"
    require(sha_file(preparer_path) == PREPARER_SHA, "Canonical preparer identity differs")
    spec = importlib.util.spec_from_file_location("captured_tiktoken_canonical_preparer", preparer_path)
    prep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prep)
    parent_path = EXTRACTED / "rust-inputs/neutts_rust_sources_lock.json"
    require(sha_file(parent_path) == PARENT_SHA, "Immutable parent input lock differs")
    parent = json.loads(parent_path.read_bytes())
    source = next(s for s in parent["sources"] if s["name"] == "tiktoken")
    require(source["cargo_lock"] is None and source["version"] == "0.14.0"
            and source["file_count"] == 36, "Original unlocked source identity differs")
    report_path = EXTRACTED / "rust-components/TIKTOKEN-LOCK-CAPTURE.json"
    require(sha_file(report_path) == "7ea8bcab4f95479696a54f47cc8400b1755dcf3defa397e0f5d417ec708ed9fa",
            "Native capture receipt differs")
    report = json.loads(report_path.read_bytes())
    require(report["status"] == "captured-requires-review"
            and report["registry_count"] == 27 and report["target_filtered_nodes"] == 25
            and report["online_tls_certificate_verification"] is True
            and not report["tiktoken_source_built"] and not report["tiktoken_wheel_installed"],
            "Native capture boundary differs")
    captured = EXTRACTED / "rust-components/captured-tiktoken-inputs"
    raw_lock = (captured / "sources" / source["archive_root"] / "Cargo.lock").read_bytes()
    require(len(raw_lock) == 6462 and sha(raw_lock) == LOCK_SHA, "New raw Cargo.lock differs")
    parsed = tomllib.loads(raw_lock.decode())
    require(parsed["version"] == 4 and len(parsed["package"]) == 28, "Cargo lock schema/count differs")
    packages = {(p["name"], p["version"]): p for p in parsed["package"]}
    require(len(packages) == 28, "Duplicate Cargo lock package identity")
    local = [p for p in parsed["package"] if "source" not in p]
    require(len(local) == 1 and local[0]["name"] == "tiktoken"
            and local[0]["version"] == "0.14.0", "Unexpected local/Git package")
    registry = {(p["name"], p["version"]): p for p in report["registry"]}
    require(len(registry) == 27 and set(registry) == set(packages) - {("tiktoken", "0.14.0")},
            "Captured registry does not exactly cover the new lock")
    for key, pin in registry.items():
        package = packages[key]
        require(package["source"] == prep.REGISTRY and package["checksum"] == pin["sha256"]
                and re.fullmatch(r"[0-9a-f]{64}", package["checksum"]) is not None,
                "Original registry archive does not match Cargo.lock checksum")
    original_source_archive = EXTRACTED / "rust-inputs/archives" / source["artifact"]["filename"]
    original_raw = prep.verified_bytes(original_source_archive, source["artifact"])
    original_rows = prep.archive_files(original_raw, source["archive_root"])
    require(original_rows == source["files"], "Original sdist bytes/modes differ from the parent pin")
    prep.verify_source(captured / "sources" / source["archive_root"], source, allow_new_lock=True)

    OUTPUT.mkdir(parents=True)
    restored_source = OUTPUT / "sources" / source["archive_root"]
    restored_rows = prep.archive_files(original_raw, source["archive_root"], output=restored_source)
    prep.write_new(restored_source / "Cargo.lock", raw_lock)
    prep.verify_source(restored_source, source, allow_new_lock=True)
    require(restored_rows == original_rows, "Reconstructed original source inventory differs")
    with zipfile.ZipFile(ARCHIVE) as archive:
        archive_names = set(archive.namelist())
        archive_members = {}
        for pin in sorted(registry.values(), key=lambda p: (p["name"], p["version"])):
            crate = captured / "crates" / pin["filename"]
            raw = prep.verified_bytes(crate, pin)
            member_name = "rust-components/captured-tiktoken-inputs/crates/" + pin["filename"]
            require(archive.read(member_name) == raw, "Captured crate copy differs from the CRC-verified ZIP member")
            destination = OUTPUT / "vendor" / (pin["name"] + "-" + pin["version"])
            exported = prep.export_crate(crate, pin, destination)
            count = prep.verify_crate(crate, pin, destination)
            require(count == pin["files"] == len(exported["files"])
                    and exported["checksum_sha256"] == pin["checksum_sha256"],
                    "Canonical reconstruction differs from the native directory-source receipt")
            vendor_prefix = "rust-components/captured-tiktoken-inputs/vendor/" + destination.name + "/"
            absent_original = [r["path"] for r in exported["files"]
                               if vendor_prefix + r["path"] not in archive_names]
            require(all(any(part.startswith(".") for part in PurePosixPath(name).parts)
                        for name in absent_original),
                    "Uploaded vendor lost a nonhidden original member")
            present_original = [r for r in exported["files"]
                                if vendor_prefix + r["path"] in archive_names]
            for row in present_original:
                body = archive.read(vendor_prefix + row["path"])
                require(len(body) == row["bytes"] and sha(body) == row["sha256"],
                        "Uploaded expanded vendor original member differs")
            require(vendor_prefix + ".cargo-checksum.json" not in archive_names,
                    "Observed hidden-file upload boundary changed")
            archive_members[destination.name] = {
                "name": pin["name"], "version": pin["version"], "archive": identity(crate),
                "files": count, "file_inventory": exported["files"],
                "canonical_checksum_sha256": exported["checksum_sha256"],
                "uploaded_expanded_original_files": len(present_original),
                "uploaded_missing_hidden_original_files": absent_original,
                "uploaded_missing_generated_checksum": True,
                "reconstructed_and_independently_reverified": True}

    metadata_path = EXTRACTED / "rust-components/tiktoken-offline-metadata-replay.stdout.log"
    require(sha_file(metadata_path) == report["offline_replay"]["stdout_sha256"]
            == "950fced17a37700a12d7dfea731d48e57eab195d1925538b4bfaeabf732d5a4b",
            "Native offline metadata body differs")
    metadata = json.loads(metadata_path.read_bytes())
    meta_packages = {p["id"]: p for p in metadata["packages"]}
    nodes = metadata["resolve"]["nodes"]
    require(len(meta_packages) == len(metadata["packages"]) == len(nodes) == 25
            and len({n["id"] for n in nodes}) == 25, "Offline target graph identity/count differs")
    native_source_prefix = "/out/rust-components/captured-tiktoken-inputs/sources/" + source["archive_root"]
    native_vendor_prefix = "/out/rust-components/captured-tiktoken-inputs/vendor/"
    selected = []
    for node in nodes:
        package = meta_packages[node["id"]]
        key = (package["name"], package["version"])
        if package["source"] is None:
            require(key == ("tiktoken", "0.14.0")
                    and package["manifest_path"] == native_source_prefix + "/Cargo.toml",
                    "Offline metadata selected an unexpected local source")
            require(node["id"] == metadata["resolve"]["root"], "Offline local root differs")
        else:
            require(key in registry and package["source"] == prep.REGISTRY
                    and package["manifest_path"] == native_vendor_prefix
                       + package["name"] + "-" + package["version"] + "/Cargo.toml",
                    "Offline metadata selected an unpinned source")
        require(all(dep["pkg"] in meta_packages for dep in node["deps"]),
                "Offline dependency edge leaves the resolved package set")
        selected.append({"name": package["name"], "version": package["version"],
                         "source": package["source"], "features": sorted(node["features"]),
                         "dependency_ids": node["deps"]})
    require(metadata["workspace_members"] == [metadata["resolve"]["root"]],
            "Unexpected offline workspace root")
    selected_names = {(p["name"], p["version"]) for p in selected}
    selected_pyo3 = [p for p in selected if p["name"] == "pyo3"]
    selected_root = [p for p in selected if p["name"] == "tiktoken"]
    require(len(selected_pyo3) == 1 and selected_pyo3[0]["version"] == "0.29.3"
            and set(selected_pyo3[0]["features"]) == {"extension-module", "macros", "pyo3-macros"}
            and "python" in selected_root[0]["features"],
            "Resolved Python/PyO3 ABI feature route differs from the original declaration")
    original_manifest = tomllib.loads((restored_source / "Cargo.toml").read_text())
    require(original_manifest["dependencies"]["pyo3"]["version"] == "0.29.2",
            "Original PyO3 semver requirement changed")

    parent_registry = {(p["name"], p["version"]): p for p in parent["registry"]}
    overlaps = sorted(set(registry) & set(parent_registry))
    for key in overlaps:
        require(parent_registry[key]["sha256"] == registry[key]["sha256"],
                "Same name/version conflicts with the unchanged original Cargo union")
    captured_input = {
        "schema": "captured-tiktoken-exact-inputs/v1", "status": "ready-for-root-review",
        "run_id": 39084939992, "head_sha": "fe857011db52cccd3d7bede48523a77481d8fab9",
        "job_id": 117549406160, "job_conclusion": "success",
        "parent_input_lock": {"sha256": PARENT_SHA, "source_record_unchanged": True},
        "original_source": source,
        "captured_cargo_lock": {"path": "Cargo.lock", "bytes": len(raw_lock), "sha256": LOCK_SHA,
                               "raw_audit_path": "raw-termux-neutts-rust-tiktoken-lock/rust-components/captured-tiktoken-inputs/sources/tiktoken-0.14.0/Cargo.lock"},
        "registry": sorted(registry.values(), key=lambda p: (p["name"], p["version"])),
        "registry_count": 27, "registry_archive_bytes": sum(p["bytes"] for p in registry.values()),
        "target_filtered_package_count": 25, "target_filtered_registry_count": 24,
        "target_filtered_packages": selected,
        "target_inactive_frozen_registry": [{"name": k[0], "version": k[1]}
                                            for k in sorted(set(registry) - selected_names)],
        "parent_804_union_overlap": [{"name": k[0], "version": k[1]} for k in overlaps],
        "original_build_backend_and_python_dependencies_preserved": True,
        "existing_project_lock_modified": False, "native_source_build_or_install_performed": False,
        "root_review_and_saved_pin_required_before_build": True}
    input_receipt = save_new(AUDIT / "captured-tiktoken-exact-inputs.json", captured_input)
    reconstruction_receipt = save_new(AUDIT / "tiktoken-canonical-reconstruction.json", {
        "schema": "captured-tiktoken-canonical-reconstruction/v1",
        "canonical_preparer": {"path": "scripts/prepare_neutts_rust_sources.py",
                               "sha256": PREPARER_SHA},
        "owned_fresh_output": str(OUTPUT),
        "original_source_files": original_rows, "new_raw_lock_sha256": LOCK_SHA,
        "reconstructed_source_files": 37, "crate_count": 27,
        "crates": list(archive_members.values()),
        "host": "Windows CPython; no Cargo/build/backend execution",
        "original_mode_bits_verified_from_archives": True,
        "windows_exported_mode_replay": "Canonical helper compares every file body; NT mode semantics are not claimed as POSIX execution permission proof.",
        "uploaded_vendor_is_complete": False,
        "all_missing_hidden_original_files_restored_from_exact_original_crates": True,
        "all_27_generated_checksum_files_reconstructed_and_verified": True,
        "native_offline_replay_preserved": identity(metadata_path),
        "input_catalog": input_receipt})
    review = {
        "schema": "captured-tiktoken-lock-review/v1",
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "host-integrity-review-passed-requires-root-review",
        "run_id": 39084939992, "head_sha": "fe857011db52cccd3d7bede48523a77481d8fab9",
        "job_id": 117549406160, "native_job_conclusion": "success",
        "whole_artifact": identity(ARCHIVE), "whole_artifact_rehashed_in_this_review": True,
        "full_member_capture_receipt": identity(AUDIT / "verified-artifact-12119853598.json"),
        "raw_native_capture": identity(report_path),
        "cargo_lock": {"bytes": len(raw_lock), "sha256": LOCK_SHA, "version": 4, "packages": 28},
        "registry_count": 27, "registry_archive_bytes": sum(p["bytes"] for p in registry.values()),
        "canonical_original_registry_files": sum(p["files"] for p in registry.values()),
        "target_filtered_packages": 25, "target_filtered_registry_packages": 24,
        "target_filtered_dependency_edges": sum(len(p["dependency_ids"]) for p in selected),
        "pyo3_resolution": {"original_requirement": "0.29.2", "captured_version": "0.29.3",
                            "feature_flags": selected_pyo3[0]["features"],
                            "source_requirement_and_abi_features_unchanged": True},
        "preserved_online_and_offline_commands": report["online_commands"] + [report["offline_replay"]],
        "all_original_36_source_files_verified": True,
        "all_27_original_crates_reconstructed_and_verified": True,
        "all_27_raw_archive_hashes_equal_Cargo_lock_checksums": True,
        "all_same_name_version_overlaps_match_original_parent_union": True,
        "uploaded_hidden_vendor_omissions": "Expanded vendor is incomplete because upload-artifact omitted hidden paths; exact original .crate archives are complete and have reconstructed every original file plus canonical .cargo-checksum.json.",
        "captured_input_catalog": input_receipt,
        "canonical_reconstruction_receipt": reconstruction_receipt,
        "native_tiktoken_build": False, "native_tiktoken_install": False,
        "complete_four_component_runtime": False, "project_source_or_lock_changed": False,
        "root_review_and_saved_pin_required_before_build": True}
    receipt = save_new(AUDIT / "TIKTOKEN-LOCK-REVIEW.json", review)
    print(json.dumps({"review": receipt, "input_catalog": input_receipt,
                      "reconstruction": reconstruction_receipt, "registry_count": 27,
                      "registry_archive_bytes": review["registry_archive_bytes"],
                      "registry_source_files": review["canonical_original_registry_files"],
                      "target_filtered_edges": review["target_filtered_dependency_edges"],
                      "parent_union_overlap_count": len(overlaps)}))

if __name__ == "__main__":
    main()
