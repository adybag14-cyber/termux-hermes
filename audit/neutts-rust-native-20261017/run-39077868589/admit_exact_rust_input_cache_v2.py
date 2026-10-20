"""Admit only original pinned download inputs from the two fully verified failed Rust artifacts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import sys
import zipfile

ROOT = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT = ROOT / "audit/neutts-rust-native-20261017/run-39077868589"
BASE = ROOT.parent / "neutts-rust-native-evidence-20261017/39077868589"
EXPECTED = {
    12117447366: ("tiktoken-lock", 257669587, "23ecb572f5e2e0f3f26ac791216dd26c29a2f281a616fc58712637f417949ff5"),
    12117907464: ("locked-build", 559495835, "57364a78bab0509d076616819cf815fcb629bb4a09925753da10b41c8bed5a45"),
}

EXPECTED_MISSING_SOURCE_PATHS = {
    "tiktoken": [],
    "maturin": [".codespellrc", ".config/nextest.toml", ".gitattributes", ".gitignore",
                ".pre-commit-config.yaml", "src/templates/.gitignore.j2"],
    "hf-xet": ["hf_xet/.gitignore"],
    "safetensors": ["bindings/python/.gitignore"],
    "tokenizers": ["bindings/python/.cargo/config.toml", "bindings/python/.gitignore"],
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def record(path):
    raw = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)}

def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, path.name
    else:
        path.write_bytes(raw)

def main():
    source = ROOT / "scripts/prepare_neutts_rust_sources.py"
    assert sha(source.read_bytes()) == "0f5db491b6a2d2cbe13e908fe24613b62f9db38ac2f0d33968328c499038a9a1"
    spec = importlib.util.spec_from_file_location("_rust_run2_cache_admission", source)
    prep = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = prep
    spec.loader.exec_module(prep)
    lock, lock_raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    source_by_file = {s["artifact"]["filename"]: s for s in lock["sources"]}
    crate_by_file = {p["filename"]: p for p in lock["registry"]}
    wheel_by_file = {p["artifact"]["filename"]: p for p in lock["python_build_packages"]}
    apt_by_file = {prep.apt_archive_filename(p): p for p in lock["build_apt"]["packages"]}
    snapshot_by_file = {p["filename"]: p for p in lock["build_apt"]["snapshot"]}
    apt_by_name = {p["name"]: p for p in lock["build_apt"]["packages"]}
    unique, archives, source_count, source_files = {}, [], 0, 0
    all_raw_proofs = []
    source_upload_records, uploaded_source_count = [], 0
    for identity, (stage, size, digest) in EXPECTED.items():
        receipt_path = AUDIT / f"verified-artifact-{identity}.json"
        proof = json.loads(receipt_path.read_bytes())
        assert proof["artifact_id"] == identity and proof["artifact_bytes"] == size and proof["artifact_sha256"] == digest
        assert proof["run_id"] == 39077868589 and proof["head_sha"] == "dcd4224112bef3c504c0198ab1251cc4c6b6544f"
        assert proof["all_member_crc_verified"] is True and proof["all_member_sha256_recorded"] is True
        expected_name = "termux-neutts-rust-" + stage
        external = BASE / ("extracted-" + expected_name)
        assert Path(proof["external_extracted_root"]) == external
        members = {r["name"]: r for r in proof["members"]}
        stage_rows = []
        for member, row in members.items():
            if not member.startswith("rust-inputs/"):
                continue
            relative = member.removeprefix("rust-inputs/")
            if relative == prep.LOCK_FILENAME:
                kind, filename = "source-lock", relative
            else:
                parts = relative.split("/")
                if len(parts) != 2 or parts[0] not in ("archives", "crates", "wheels", "apt-archives", "snapshot"):
                    continue
                kind, filename = parts
            assert row["external_copy"] is True
            path = external / member
            raw = path.read_bytes()
            actual = sha(raw)
            assert len(raw) == row["bytes"] and actual == row["sha256"], member
            if kind == "source-lock":
                assert raw == lock_raw
                selected_identity = prep.LOCK_FILENAME
            else:
                if kind == "archives":
                    source_pin = source_by_file[filename]
                    pin = source_pin["artifact"]
                    selected_identity = source_pin["name"]
                    parsed = prep.archive_files(raw, source_pin["archive_root"])
                    prep.same_files(parsed, source_pin["files"])
                    source_count += 1
                    source_files += len(parsed)
                    uploaded_prefix = "rust-inputs/sources/" + source_pin["archive_root"] + "/"
                    uploaded = {n.removeprefix(uploaded_prefix): r for n, r in members.items()
                                if n.startswith(uploaded_prefix)}
                    expected_paths = {p["path"] for p in source_pin["files"]}
                    missing = sorted(expected_paths - set(uploaded))
                    assert not set(uploaded) - expected_paths
                    assert missing == sorted(EXPECTED_MISSING_SOURCE_PATHS[source_pin["name"]])
                    for source_row in source_pin["files"]:
                        if source_row["path"] in uploaded:
                            actual_row = uploaded[source_row["path"]]
                            assert actual_row["bytes"] == source_row["bytes"] and actual_row["sha256"] == source_row["sha256"]
                    uploaded_source_count += len(uploaded)
                    source_upload_records.append({"source": source_pin["name"],
                        "original_archive_files": len(source_pin["files"]), "uploaded_files": len(uploaded),
                        "omitted_uploaded_source_paths": missing,
                        "complete_original_archive_preserved": True})
                elif kind == "crates":
                    pin = crate_by_file[filename]
                    selected_identity = pin["name"] + "==" + pin["version"]
                elif kind == "wheels":
                    wheel_pin = wheel_by_file[filename]
                    pin = wheel_pin["artifact"]
                    selected_identity = wheel_pin["name"] + "==" + wheel_pin["version"]
                    prep.verify_wheel(path, wheel_pin)
                elif kind == "apt-archives":
                    pin = apt_by_file[filename]
                    selected_identity = pin["name"] + "==" + pin["version"]
                else:
                    pin = snapshot_by_file[filename]
                    selected_identity = filename
                assert actual == pin["sha256"] and (pin.get("bytes") is None or len(raw) == pin["bytes"]), member
            admitted = {"kind": kind, "identity": selected_identity, "relative_path": relative,
                        "bytes": len(raw), "sha256": actual}
            key = (kind, selected_identity)
            if key in unique:
                assert unique[key] == admitted
            else:
                unique[key] = admitted
            stage_rows.append(admitted)
        expected_sources = {s["name"] for s in lock["sources"]
                            if (s["name"] == "tiktoken") == (stage == "tiktoken-lock")}
        assert {r["identity"] for r in stage_rows if r["kind"] == "archives"} == expected_sources
        assert sum(r["kind"] == "crates" for r in stage_rows) == (804 if stage == "locked-build" else 0)
        assert sum(r["kind"] == "wheels" for r in stage_rows) == (5 if stage == "locked-build" else 0)
        assert sum(r["kind"] == "apt-archives" for r in stage_rows) == 46
        prep.snapshot_binding(external / "rust-inputs/snapshot", lock["build_apt"]["snapshot"])
        raw_root = AUDIT / ("raw-" + expected_name)
        native_path = raw_root / "rust-components/RUST-COMPONENTS-RESULT.json"
        core_path = raw_root / "NEUTTS-CORE-RESULT.json"
        native, core = json.loads(native_path.read_bytes()), json.loads(core_path.read_bytes())
        assert native["status"] == "failed" and native["stage"] == "native-signed-index"
        assert native["error"] == "Duplicate target APT package"
        assert native["lock_sha256"] == prep.LOCK_SHA256
        assert native["foundation"]["sha256"] == sha(core_path.read_bytes())
        assert core["status"] == "passed" and len(core["cases"]) == 7
        assert native["foundation"]["case_count"] == 7 and native["foundation"]["status"] == "passed"
        assert core["apt_python_validation"]["status"] == "requirements-and-provenance-passed"
        assert core["apt_python_validation"]["exit_code"] == 0
        assert core["pip_check"]["exit_code"] == native["foundation"]["raw_pip_exit_code"] == 1
        for metadata in (core["apt_python_validation"], core["apt_python_metadata"]):
            assert sha((raw_root / metadata["receipt"]).read_bytes()) == metadata["sha256"]
        assert sha((raw_root / core["pip_check"]["log"]).read_bytes()) == core["pip_check"]["log_sha256"]
        case_records = []
        for case in core["cases"]:
            path = raw_root / case["receipt"]
            assert case["status"] == "passed" and case["exit_code"] == 0 and not case["timed_out"]
            assert sha(path.read_bytes()) == case["receipt_sha256"]
            case_records.append({"component": case["component"], "receipt": record(path)})
        assert len(native["archives"]) == 46 and len({r["name"] for r in native["archives"]}) == 46
        for row in native["archives"]:
            pin = apt_by_name[row["name"]]
            assert (row["version"], row["bytes"], row["sha256"]) == (pin["version"], pin["bytes"], pin["sha256"])
        original_zip = BASE / f"artifact-{identity}-assembled.zip"
        assert original_zip.stat().st_size == size
        with zipfile.ZipFile(original_zip) as archive:
            prepared_raw = archive.read("rust-inputs/RUST-PREPARED-INPUTS.json")
        prepared_row = members["rust-inputs/RUST-PREPARED-INPUTS.json"]
        assert len(prepared_raw) == prepared_row["bytes"] and sha(prepared_raw) == prepared_row["sha256"]
        assert sha(prepared_raw) == native["input_receipt_sha256"]
        prepared_path = raw_root / "rust-inputs/RUST-PREPARED-INPUTS.json"
        save(prepared_path, prepared_raw)
        prepared = json.loads(prepared_raw)
        assert prepared["status"] == "verified-inputs" and prepared["stage"] == stage
        assert prepared["lock_sha256"] == prep.LOCK_SHA256
        assert prepared["apt_owned_cache_filenames"] == prep.apt_archive_names(lock["build_apt"]["packages"])
        assert not prepared["cargo_executed"] and not prepared["source_backend_executed"] and not prepared["tiktoken_lock_resolved"]
        assert prepared["registry_archives"] == native["input_checks"]["registry_archives"]
        assert prepared["registry_source_files"] == native["input_checks"]["registry_source_files"]
        for member, row in members.items():
            if row["git_audit_raw_copy"]:
                path = raw_root / member
                raw = path.read_bytes()
                assert len(raw) == row["bytes"] and sha(raw) == row["sha256"], member
                all_raw_proofs.append(record(path))
        all_raw_proofs.append(record(prepared_path))
        archives.append({
            "artifact_id": identity, "stage": stage, "artifact_bytes": size, "artifact_sha256": digest,
            "member_count": len(members), "verified_artifact_receipt": record(receipt_path),
            "cache_root": str(external / "rust-inputs"), "admitted_input_count": len(stage_rows),
            "counts": {kind: sum(r["kind"] == kind for r in stage_rows) for kind in sorted({r["kind"] for r in stage_rows})},
            "original_prepared_input_receipt": record(prepared_path),
            "original_preparer_and_native_registry_check": native["input_checks"],
            "native_result": record(native_path),
            "native_status": native["status"], "native_failure_stage": native["stage"], "native_error": native["error"],
            "native_runtime": native["runtime"], "native_apt_archive_records": len(native["archives"]),
            "foundation": {"core_receipt": record(core_path), "cases_passed": 7,
                           "case_receipts": case_records, "strict_apt_python_validation": core["apt_python_validation"],
                           "raw_pip_check_exit_code_preserved": core["pip_check"]["exit_code"],
                           "earlier_foundation_recorded_signed_apt": core["signed_apt"],
                           "later_rust_signed_snapshot_authentication_reached": False},
        })
    rows = sorted(unique.values(), key=lambda r: (r["kind"], r["identity"]))
    counts = {kind: sum(r["kind"] == kind for r in rows) for kind in sorted({r["kind"] for r in rows})}
    assert counts == {"apt-archives": 46, "archives": 5, "crates": 804, "snapshot": 2, "source-lock": 1, "wheels": 5}
    assert source_count == 5 and source_files == 744 and len(rows) == 863
    assert uploaded_source_count == 734
    action_source = AUDIT / "upload-artifact-action-at-pinned-commit.yml"
    assert sha(action_source.read_bytes()) == "c5979822866a72362e609844b6ebe77d4b7e759af68cc1c2c425dcf51481fab4"
    workflow_raw = (ROOT / ".github/workflows/neutts-rust-components.yml").read_bytes()
    assert sha(workflow_raw) == "d88f44abc37d4995781833178e677bd0aa4ce428924e835934d2305e1b8118a9"
    assert b"include-hidden-files:" not in workflow_raw
    receipt = {
        "schema": "exact-rust-original-download-input-cache-admission/v1",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "all-original-download-inputs-captured-and-verified-native-stages-failed",
        "run_id": 39077868589, "head_sha": "dcd4224112bef3c504c0198ab1251cc4c6b6544f",
        "source_lock": {"path": "scripts/" + prep.LOCK_FILENAME, "bytes": len(lock_raw), "sha256": prep.LOCK_SHA256},
        "preparer": record(source), "artifacts": archives,
        "unique_admitted_counts": counts, "unique_admitted_input_count": len(rows),
        "unique_admitted_files": rows,
        "unique_catalog_sha256": sha(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()),
        "all_download_inputs_rechecked_against_actual_extracted_bytes_and_original_lock": True,
        "all_five_build_wheels_crc_record_metadata_verified": True,
        "original_source_archives_reparsed_against_full_inventory": {"archives": source_count, "files": source_files},
        "uploaded_source_files_hash_and_size_match_original_inventory": uploaded_source_count,
        "uploaded_source_tree_complete": False,
        "source_trees_must_be_reconstructed_with_canonical_preparer": True,
        "uploaded_source_coverage": source_upload_records,
        "upload_policy": {
            "action_commit": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "original_action_definition": record(action_source),
            "include_hidden_files_default": False,
            "workflow_omits_include_hidden_files_input": True,
            "ten_omitted_dot_path_files_exist_in_complete_original_archives": True,
            "direct_unpacked_artifact_copy_is_not_admitted_as_complete_preparation": True},
        "initial_admission_assumption_failure": {
            "script": record(AUDIT / "admit_exact_rust_input_cache.py"),
            "stderr": record(AUDIT / "input-cache-admission-attempt1.stderr.log"),
            "failed_assumption": "Uploaded unpacked source copies preserve every original archive path.",
            "correction_scope": "Record the exact 10 omitted dot paths and complete original source archives separately; do not claim a complete uploaded source tree.",
            "native_result_changed": False},
        "uploaded_source_modes_independently_checked": False,
        "reusable_download_cache_subdirectories": ["archives", "crates", "wheels", "apt-archives"],
        "complete_download_cache_for_both_existing_stages": True,
        "offline_preparation_reexecuted_from_captured_cache": False,
        "remaining_apt_downloads": [],
        "raw_native_proof_files": all_raw_proofs,
        "raw_native_proof_file_count": len(all_raw_proofs),
        "original_cargo_union_is_target_active_graph": False,
        "target_active_cargo_graph_resolved": False, "tiktoken_cargo_lock_captured": False,
        "cargo_or_source_backend_executed": False, "native_rust_wheels_built": False,
        "complete_rust_runtime_admitted": False, "model_downloaded": False, "release_output": False,
        "historical_failure_and_fix_receipts_modified": False,
        "capture_job": {"id": "job-1792279384645-edc1deea-c00", "status": "succeeded",
                        "completed_at_utc": "2026-10-17T23:31:30.370Z"},
    }
    output = AUDIT / "captured-original-input-cache-admission.json"
    assert not output.exists()
    output.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"receipt": record(output), "counts": counts, "source_files": source_files, "uploaded_source_files": uploaded_source_count,
                      "all_verified_zip_members": sum(a["member_count"] for a in archives),
                      "raw_native_proofs": len(all_raw_proofs), "registry_checks": [
                          {"stage": a["stage"], **a["original_preparer_and_native_registry_check"]} for a in archives],
                      "catalog_sha256": receipt["unique_catalog_sha256"]}, ensure_ascii=True))

if __name__ == "__main__":
    main()
