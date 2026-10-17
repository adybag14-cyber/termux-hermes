"""Freeze the first TorchAO native failure without changing existing audits or code."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
import base64, csv, hashlib, io, json, stat, zipfile, zlib

BASE = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
REPO = BASE / "termux-hermes-next-stable-20261017"
EVIDENCE = BASE / "torchao-termux-native-evidence-20261017/39074259828"
RAW = REPO / "audit/neutts-torchao-native-20261017/run-39074259828"
SUMMARY = RAW.with_suffix(".json")
HEAD = "1fc3dde05aca3786d28d656ced9a807e872bff4f"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_json(path):
    return json.loads(path.read_bytes())

def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()

def save_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw

def check(raw, record):
    assert len(raw) == record["bytes"] and sha(raw) == record["sha256"]

def main():
    assert not RAW.exists() and not SUMMARY.exists()
    ledger = read_json(EVIDENCE / "verified-artifact.json")
    assert ledger["run_id"] == 39074259828 and ledger["head_sha"] == HEAD
    assert ledger["job_id"] == 117518048072 and ledger["conclusion"] == "failure"
    assert ledger["artifact_id"] == 12116536631 and ledger["artifact_bytes"] == 11201574
    assert ledger["artifact_sha256"] == "cb37a410088ad778ad36b1ba3befac78f94263c4ee3ebaef17dc44f89bd5ec90"
    archive_path = EVIDENCE / "artifact.zip"
    assert archive_path.stat().st_size == ledger["artifact_bytes"] and sha(archive_path.read_bytes()) == ledger["artifact_sha256"]
    rows = {r["name"]: r for r in ledger["members"]}
    assert len(rows) == len(ledger["members"]) == 61
    retained = {name: row for name, row in rows.items() if row["extracted"]}
    assert len(retained) == 51
    extracted = EVIDENCE / "extracted"
    assert {p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file()} == set(retained)
    for name, row in retained.items():
        path = extracted / name
        assert path.is_file() and not path.is_symlink()
        check(path.read_bytes(), row)
    log = (EVIDENCE / "native-job.log").read_bytes()
    assert len(log) == 189485 and sha(log) == "846c3a184900efbf44a53b6e07a5bccf533da548d9326f0bb95a3699cdc65e02"
    inputs = read_json(extracted / "TORCHAO-PROBE-INPUTS.json")
    assert inputs["head_sha"] == inputs["workflow_ref_commit"] == HEAD and inputs["run_id"] == "39074259828"
    assert len(inputs["inputs"]) == 12
    sources = {}
    for name, pin in inputs["inputs"].items():
        assert not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
        raw = (REPO / name).read_bytes()
        assert sha(raw) == pin, name
        sources[name] = raw
    core = read_json(extracted / "NEUTTS-CORE-RESULT.json")
    assert core["status"] == "passed" and len(core["cases"]) == 7
    for row in core["cases"]:
        assert row["status"] == "passed" and row["exit_code"] == 0 and row["timed_out"] is False
        assert sha((extracted / row["receipt"]).read_bytes()) == row["receipt_sha256"]
        child = read_json(extracted / row["receipt"])
        assert child["status"] == "passed" and child["component"] == row["component"]
    validation = core["apt_python_validation"]
    assert validation["status"] == "requirements-and-provenance-passed" and validation["exit_code"] == 0
    assert sha((extracted / validation["receipt"]).read_bytes()) == validation["sha256"]
    assert core["pip_check"]["exit_code"] == 1
    assert sha((extracted / core["pip_check"]["log"]).read_bytes()) == core["pip_check"]["log_sha256"]
    component = extracted / "torchao-component"
    report = read_json(component / "TORCHAO-COMPONENT-RESULT.json")
    runtime = read_json(component / "TORCHAO-RUNTIME-RESULT.json")
    assert report["status"] == "failed" and report["stage"] == "actual-native-runtime"
    assert sha((component / report["runtime_receipt"]["path"]).read_bytes()) == report["runtime_receipt"]["sha256"]
    assert runtime["status"] == "failed" and runtime["cases"] == []
    assert runtime["error"] == {"type": "ModuleNotFoundError", "message": "No module named 'torch._inductor.kernel.flex_attention'"}
    assert [r["exit_code"] for r in report["commands"]] == [0, 0, 1]
    for command in report["commands"]:
        assert command["timed_out"] is False
        for channel in ("stdout", "stderr"):
            detail = command["logs"][channel]
            assert detail["truncated"] is False
            check((component / detail["path"]).read_bytes(), detail)
    stderr = (component / "actual-native-runtime.stderr.log").read_bytes()
    assert len(stderr) == 2806 and sha(stderr) == "25223b5e9d091ade7babdad7c881d53480d31b3af82f98d9f230e0d51bc60c3f"
    for frame in (b"import torchao", b"fx_passes/__init__.py", b"int8_sdpa_fusion.py",
                  b"int8_sdpa_lowering.py", b"No module named 'torch._inductor.kernel.flex_attention'"):
        assert frame in stderr
    assert (component / "actual-native-runtime.stdout.log").read_bytes() == b""
    for receipt in (report, runtime):
        assert receipt["foundation"]["sha256"] == sha((extracted / "NEUTTS-CORE-RESULT.json").read_bytes())
        assert receipt["foundation"]["apt_validation_sha256"] == validation["sha256"]
        assert receipt["foundation"]["case_count"] == 7 and receipt["foundation"]["current_selected_apt_files_rechecked"] == 474
        assert receipt["foundation"]["raw_pip_exit_code"] == 1
        assert receipt["complete_engine_tested"] is False and receipt["model_downloaded"] is False
    installed = runtime["installed_wheel"]
    assert installed["name"] == "torchao" and installed["version"] == "0.12.0"
    assert installed["original_files_verified"] == 347 and installed["installed_file_count"] == 351
    assert installed["complete_installed_record_verified"] is True and installed["extra_distribution_count"] == 0
    assert installed["wheel_sha256"] == "103f2a9164d2e4f705332af1aafbb8473eadd14d9164e45857ca187cde1f13d2"
    lock = read_json(extracted / "torchao-inputs/neutts_torchao_component_lock.json")
    assert sha((extracted / "torchao-inputs/neutts_torchao_component_lock.json").read_bytes()) == report["lock_sha256"] == "8c3303018c326f63540c59855df19d7fc3cef139040c90d64b4e7f4cbc264c22"
    source_review = {}
    wheels = []
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == set(rows) and len(archive.infolist()) == 61
        for info in archive.infolist():
            raw = archive.read(info)
            check(raw, rows[info.filename])
            assert info.CRC == rows[info.filename]["crc"] == zlib.crc32(raw) & 0xffffffff
            if info.filename.endswith(".whl"):
                with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
                    assert wheel.testzip() is None
                    regular = {i.filename: wheel.read(i) for i in wheel.infolist() if not i.is_dir()}
                    assert len({i.filename for i in wheel.infolist()}) == len(wheel.infolist())
                    records = [n for n in regular if n.endswith(".dist-info/RECORD") and n.count("/") == 1]
                    assert len(records) == 1
                    record_name = records[0]
                    records = list(csv.reader(io.StringIO(regular[record_name].decode())))
                    assert all(len(row) == 3 for row in records)
                    assert len(records) == len(regular) and {r[0] for r in records} == set(regular)
                    for name, digest, size in records:
                        if name == record_name:
                            assert digest == size == ""
                        else:
                            assert size == str(len(regular[name]))
                            assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(regular[name]).digest()).decode().rstrip("=")
                    wheels.append({"path": info.filename, "bytes": len(raw), "sha256": sha(raw),
                                   "regular_files": len(regular), "all_inner_crc_record_verified": True})
                    if info.filename.endswith(lock["package"]["artifact"]["filename"]):
                        check(raw, lock["package"]["artifact"])
                        assert len(regular) == 348 and len(wheel.infolist()) == 422
                        for kind in ("metadata", "wheel", "record"):
                            pin = lock["package"]["wheel"]
                            assert sha(regular[pin[kind + "_member"]]) == pin[kind + "_sha256"]
                        assert not any(b.startswith(b"\x7fELF") for b in regular.values())
                        for row in lock["source_members"]:
                            check(regular[row["path"]], row)
                            source_review[row["path"]] = regular[row["path"]]
                        for name in ("torchao/prototype/inductor/fx_passes/__init__.py",
                                     "torchao/prototype/inductor/fx_passes/int8_sdpa_fusion.py",
                                     "torchao/prototype/inductor/int8_sdpa_lowering.py",
                                     "torchao/dtypes/uintx/dyn_int8_act_int4_wei_cpu_layout.py"):
                            source_review[name] = regular[name]
                        assert b"from .int8_sdpa_fusion import _int8_sdpa_init" in source_review["torchao/prototype/inductor/fx_passes/__init__.py"]
                        assert b"from torch._inductor.kernel.flex_attention import construct_strides, maybe_realize" in source_review["torchao/prototype/inductor/int8_sdpa_lowering.py"]
        assert archive.testzip() is None
    assert len(wheels) == 10
    recheck = {
        "schema_version": 1, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "whole_artifact_and_all_61_member_sha256_crc_recomputed": True,
        "all_51_retained_files_match_member_ledger": True, "exact_run_input_files_saved": 12,
        "foundation_cases_passed": 7, "foundation_child_receipt_hashes_verified": True,
        "foundation_raw_pip_check_exit_code": 1, "foundation_separate_requirements_and_provenance_passed": True,
        "fresh_venv_creation_and_exact_wheel_install_passed": True,
        "runtime_reported_original_wheel_files_verified": 347, "runtime_reported_installed_files_verified": 351,
        "runtime_reported_regenerated_installed_record_verified": True,
        "runtime_reported_current_foundation_apt_files_verified": 474,
        "all_10_original_wheels_inner_crc_record_recomputed": wheels,
        "torchao_real_import_passed": False, "nf4_operation_cases_reached": 0,
        "actual_native_child_exit_code": 1, "actual_native_child_timed_out": False,
        "all_child_command_stdout_stderr_preserved_and_hash_verified": True,
        "native_error": runtime["error"],
        "source_grounded_import_path": ["torchao", "torchao.quantization", "torchao.dtypes",
            "torchao.dtypes.uintx.dyn_int8_act_int4_wei_cpu_layout",
            "torchao.prototype.inductor.fx_passes", "torchao.prototype.inductor.fx_passes.int8_sdpa_fusion",
            "torchao.prototype.inductor.int8_sdpa_lowering", "torch._inductor.kernel.flex_attention"],
        "boundary": "Missing optional compiler module is imported eagerly before any of the five actual CPU NF4 gates. Native installation verification is a recorded prior gate, not a successful TorchAO import.",
        "proposed_followup": "Review lazy loading of the optional compiler pass at its requested-operation boundary, preserving ordinary compiler behavior and all real CPU gates.",
        "host_recheck_scope": "Receipt and artifact/source verification; no second Android execution and no source-only import substituted for the failed real package import.",
        "complete_engine_tested": False, "model_downloaded": False, "audio_tested": False,
        "production_admission_changed": False, "release_output": False}
    for name in retained:
        save_new(RAW / name, (extracted / name).read_bytes())
    for path in EVIDENCE.iterdir():
        if path.is_file() and (path.name.endswith("-api.json") or "-api-" in path.name or path.name in ("native-job.log", "verified-artifact.json")):
            raw = path.read_bytes()
            assert b"&sig=" not in raw and b"?sv=" not in raw
            save_new(RAW / path.name, raw)
    for name, raw in sources.items():
        save_new(RAW / "run-source" / name, raw)
    for name, raw in source_review.items():
        save_new(RAW / "original-wheel-source" / name, raw)
    save_new(RAW / "capture_torchao_component_run_20261017.py", (BASE / "capture_torchao_component_run_20261017.py").read_bytes())
    save_new(RAW / "freeze-run-evidence.py", Path(__file__).read_bytes())
    save_new(RAW / ".gitattributes", b"* -text\n")
    save_new(RAW / "VERIFIED-RESULT-RECHECK.json", encoded(recheck))
    saved = [{"path": p.relative_to(RAW).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
             for p in sorted(RAW.rglob("*")) if p.is_file()]
    save_new(RAW / "SAVED-FILES.json", encoded({"schema_version": 1, "scope": "All raw files except this ledger",
        "files": saved, "file_count": len(saved), "total_bytes": sum(r["bytes"] for r in saved)}))
    for row in saved:
        check((RAW / row["path"]).read_bytes(), row)
    all_raw = [p for p in RAW.rglob("*") if p.is_file()]
    summary = {
        "schema_version": 1, "captured_utc": recheck["checked_utc"],
        "repository": "adybag14-cyber/termux-hermes", "run_id": 39074259828,
        "url": "https://github.com/adybag14-cyber/termux-hermes/actions/runs/39074259828",
        "head_sha": HEAD, "job_id": 117518048072, "workflow_conclusion": "failure",
        "failure": {"stage": "Real installed TorchAO package import, before CPU NF4 checks",
                    "error": runtime["error"], "child_exit_code": 1, "child_timed_out": False,
                    "source_grounded_import_path": recheck["source_grounded_import_path"],
                    "proposed_followup": recheck["proposed_followup"]},
        "proved": {"scientific_foundation_cases": 7, "exact_original_torchao_wheel": lock["package"]["artifact"],
                   "fresh_venv_and_one_wheel_install": True, "original_files_verified_in_native_runtime": 347,
                   "installed_files_verified_in_native_runtime": 351, "installed_record_verified_in_native_runtime": True,
                   "current_foundation_files_rechecked_in_native_runtime": 474},
        "not_proved": ["TorchAO real package import", "Five CPU NF4 operations", "Complete NeuTTS or Torchtune",
                       "Model inference", "Audio I/O", "Physical device behavior", "Release readiness"],
        "foundation_raw_pip_check_exit_code": 1, "foundation_separate_requirements_and_provenance_gate": "passed",
        "artifact": {"id": ledger["artifact_id"], "bytes": ledger["artifact_bytes"], "sha256": ledger["artifact_sha256"],
                     "zip_members": 61, "retained_members": 51, "all_member_crc_sha256_verified": True,
                     "full_zip_saved_outside_git": str(archive_path),
                     "full_member_ledger_sha256": sha((RAW / "verified-artifact.json").read_bytes())},
        "native_job_log": ledger["native_job_log"],
        "native_child_stderr": {"bytes": 2806, "sha256": sha(stderr)},
        "raw_evidence": {"directory": RAW.relative_to(REPO).as_posix(), "file_count": len(all_raw),
                         "total_bytes": sum(p.stat().st_size for p in all_raw),
                         "saved_files_sha256": sha((RAW / "SAVED-FILES.json").read_bytes()),
                         "result_recheck_sha256": sha((RAW / "VERIFIED-RESULT-RECHECK.json").read_bytes()),
                         "preserved_exact_bytes": True, "binary_wheels_excluded_from_git": True},
        "existing_preparation_evidence_unchanged": "audit/neutts-torchao-preparation-20261017.json",
        "production_admission_changed": False, "release_output": False}
    save_new(SUMMARY, encoded(summary))
    print(json.dumps({"summary": str(SUMMARY), "summary_bytes": SUMMARY.stat().st_size,
        "summary_sha256": sha(SUMMARY.read_bytes()), "raw_file_count": len(all_raw),
        "raw_bytes": sum(p.stat().st_size for p in all_raw), "saved_files_sha256": summary["raw_evidence"]["saved_files_sha256"],
        "total_file_count": len(all_raw) + 1, "total_bytes": sum(p.stat().st_size for p in all_raw) + SUMMARY.stat().st_size}, indent=2))

if __name__ == "__main__":
    main()
