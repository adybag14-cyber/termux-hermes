"""Freeze the observed APT cache-name failure and the bounded reviewed correction."""
from __future__ import annotations
import datetime,hashlib,json,pathlib,subprocess,xml.etree.ElementTree as ET
ROOT=pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT=ROOT/"audit/neutts-rust-native-20261017/run-39082981266"
HEAD="123e70ee7ec9ff97b2cc82a05c13794d98e3e4b5"
RUN=39082981266
def digest(raw): return hashlib.sha256(raw).hexdigest()
def record(path):
    raw=path.read_bytes()
    return {"path":path.relative_to(ROOT).as_posix(),"bytes":len(raw),"sha256":digest(raw)}
def save(path,value):
    assert not path.exists(), "Preserve existing receipt"
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
def ledger_digest(rows): return digest(json.dumps(rows,sort_keys=True,separators=(",",":")).encode())
lock=json.loads((ROOT/"scripts/neutts_rust_sources_lock.json").read_bytes())
assert digest((ROOT/"scripts/neutts_rust_sources_lock.json").read_bytes())=="de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670"
pins={p["name"]:p for p in lock["build_apt"]["packages"]}
assert len(pins)==47
expected_additions={p["name"] for p in pins.values() if not p["in_foundation"]}
assert len(expected_additions)==20
summary=json.loads((AUDIT/"complete-artifact-capture-summary.json").read_bytes())
assert summary["run_id"]==RUN and summary["head_sha"]==HEAD and summary["artifact_count"]==2
jobs=json.loads((AUDIT/"jobs.json").read_bytes())["jobs"]
assert len(jobs)==2 and all(j["conclusion"]=="failure" for j in jobs)
stages=[]
raw_count=0
for artifact in summary["artifacts"]:
    path=ROOT/artifact["receipt"]["path"]
    assert record(path)==artifact["receipt"]
    capture=json.loads(path.read_bytes())
    assert capture["run_id"]==RUN and capture["head_sha"]==HEAD
    assert capture["artifact_bytes"]==artifact["bytes"] and capture["artifact_sha256"]==artifact["sha256"]
    assert capture["all_member_crc_verified"] and capture["all_member_sha256_recorded"]
    assert len(capture["members"])==artifact["member_count"]
    members={m["name"]:m for m in capture["members"]}
    raw_root=AUDIT/("raw-"+capture["artifact_name"])
    for member in capture["members"]:
        if member["git_audit_raw_copy"]:
            raw=(raw_root/member["name"]).read_bytes()
            assert len(raw)==member["bytes"] and digest(raw)==member["sha256"]
            raw_count+=1
    result_path=raw_root/"rust-components/RUST-COMPONENTS-RESULT.json"
    result=json.loads(result_path.read_bytes())
    assert result["status"]=="failed" and result["stage"]=="native-compiler-install"
    assert result["foundation"]["status"]=="passed" and result["foundation"]["case_count"]==7
    assert result["signed_index"]["status"]=="passed" and result["signed_index"]["matched_archives"]==47
    assert result["signed_index"]["insecure_repository_exceptions"] is False
    assert result["error"]=="rust-apt-install failed; retained exit code 100"
    assert result["engine_installed"] is False and result["model_downloaded"] is False and result["release_output"] is False
    assert {a["name"] for a in result["archives"]}==set(pins)
    for a in result["archives"]:
        assert all(a[k]==pins[a["name"]][k] for k in ("version","bytes","sha256"))
        member="rust-inputs/apt-archives/"+pathlib.PurePosixPath(a["path"]).name
        assert members[member]["bytes"]==a["bytes"] and members[member]["sha256"]==a["sha256"]
    err=raw_root/"rust-components/rust-apt-install.stderr.log"
    expected_error="E: Internal Error, Pathname to install is not absolute 'openssl-tool_1%3a3.6.5_aarch64.deb'\n"
    assert err.read_text(encoding="utf-8")==expected_error
    plan_path=raw_root/"rust-components/rust-apt-plan.stdout.log"
    plan_text=plan_path.read_text()
    proposed=[line.split()[1].split(":",1)[0] for line in plan_text.splitlines() if line.startswith("Inst ")]
    assert len(proposed)==20 and set(proposed)==expected_additions
    assert not any(line.startswith("Remv ") for line in plan_text.splitlines())
    assert "Inst openssl-tool (1:3.6.5 " in plan_text
    assert not any(line.startswith(("Inst openssl ","Inst ca-certificates ")) for line in plan_text.splitlines())
    assert "0 upgraded, 15 newly installed, 5 reinstalled, 0 to remove" in plan_text
    assert not any("captured-tiktoken-inputs/" in name or name.endswith("TIKTOKEN-LOCK-CAPTURE.json")
                   or "tiktoken-generate-lockfile." in name for name in members)
    stage="tiktoken-lock" if "tiktoken-lock" in capture["artifact_name"] else "locked-build"
    stages.append({"stage":stage,"job_id":capture["job_id"],"native_status":"failed",
                   "native_failure_stage":result["stage"],"foundation_cases_passed":7,
                   "native_signed_index":"passed","matched_signed_archive_identities":47,
                   "exact_apt_plan_count":len(proposed),"plan_new_installations":15,
                   "plan_same_version_reinstalls":5,"foundation_epoch_packages_absent_from_install_request":True,
                   "registry_input_checks":result["input_checks"],
                   "result":record(result_path),"apt_install_stderr":record(err),
                   "apt_plan":record(plan_path),"artifact":artifact})
assert raw_count==90
pre=json.loads((AUDIT/"preliminary-range-proof.json").read_bytes())
assert pre["whole_artifact_verified"] is False
for member in pre["members"]:
    raw=(ROOT/member["path"]).read_bytes()
    canonical=AUDIT/"raw-termux-neutts-rust-tiktoken-lock"/member["member"]
    assert canonical.read_bytes()==raw and digest(raw)==member["sha256"]
prior_path=ROOT/"audit/neutts-rust-native-20261017/run-39079732704/compiler-input-fix-preparation.json"
prior=json.loads(prior_path.read_bytes())
protected=list(prior["protected_files_rechecked"])
protected += [
 {"path":"scripts/prepare_neutts_rust_sources.py","bytes":28083,"sha256":"db8ce00daaece15f69b4f7b1de415accd207f13e256b2097d4efcb2d0894c428"},
 {"path":"scripts/neutts_rust_sources_lock.json","bytes":552620,"sha256":"de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670"},
 {"path":prior_path.relative_to(ROOT).as_posix(),"bytes":46223,"sha256":"e8708e04b79cd02199bd8b34febcf2f0168da0d108779a0914658d40d05b08f7"},
]
for row in protected: assert record(ROOT/row["path"])==row
code_paths=["scripts/compatibility_probe_neutts_rust.py","tests/test_neutts_rust_preparation.py","docs/neutts-rust-preparation.md"]
baseline=subprocess.check_output(["git","show",HEAD+":scripts/compatibility_probe_neutts_rust.py"],cwd=ROOT,timeout=15)
assert digest(baseline)=="cdcff92a28d310536becc9e84e68b4683b45dca2f9230584a748dd72c930276b"
current=(ROOT/code_paths[0]).read_bytes()
assert current[:current.index(b"def apt_install_cache_basename")]==baseline[:baseline.index(b"def stage_install_archives")]
assert current[current.index(b"\ndef install_toolchain"):]==baseline[baseline.index(b"\ndef install_toolchain"):]
boundary={"all_imports_and_preceding_functions_unchanged":True,
          "install_toolchain_and_all_following_functions_unchanged":True,
          "added_function":"apt_install_cache_basename",
          "changed_function":"stage_install_archives",
          "preparer_source_lock_operations_shell_workflow_unchanged":True}
analysis={"schema":"native-rust-apt-cache-failure-analysis/v1","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "run_id":RUN,"head_sha":HEAD,"stages":stages,
          "actual_native_diagnostic":expected_error.rstrip(),
          "diagnosis":"The prior native writable cache copied signed pool basenames containing an epoch colon. APT's native cache lookup expects a lowercase percent-quoted epoch. The sole new epoch addition openssl-tool exercised this cache path; ca-certificates and openssl are prechecked foundation packages and are absent from the unchanged addition request.",
          "evidence_boundary":"The exact native stderr directly reports the expected cache basename; the old staged basename is established from the exact reviewed helper source. The temporary cache directory itself was not uploaded.",
          "upstream_reference":record(AUDIT/"apt-reference-source/reference-source.json"),
          "reference_scope":"Upstream APT3.0.3 at45bebdfb891535d15e66e860aab1ee7c7b2ecaab corroborates naming. It is not asserted to be the container APT version.",
          "complete_capture":{"artifacts":2,"bytes":sum(x["bytes"] for x in summary["artifacts"]),
                              "members":sum(x["member_count"] for x in summary["artifacts"]),
                              "all_whole_sha_verified":True,"all_member_crc_and_sha_verified":True,
                              "raw_audit_copies_rechecked":raw_count,"preliminary_member_bytes_reconciled":len(pre["members"]),
                              "summary":record(AUDIT/"complete-artifact-capture-summary.json")},
          "not_reached":["compiler ABI controls","Cargo lock resolution","Rust source builds","HF TLS behavior"],
          "new_tiktoken_lock_produced":False,"source_or_lock_changed":False,"release_output":False}
analysis_path=AUDIT/"native-cache-failure-analysis.json"
save(analysis_path,analysis)
diff=subprocess.check_output(["git","diff","--no-ext-diff","--no-color","--",*code_paths],cwd=ROOT,timeout=15)
diff_path=AUDIT/"native-cache-fix.diff"
assert not diff_path.exists(); diff_path.write_bytes(diff)
test=json.loads((AUDIT/"native-cache-host-test-environment.json").read_bytes())
assert test["exit_code"]==0
assert all(x["tests"]=="126" and x["errors"]=="0" and x["failures"]=="0" and x["skipped"]=="0" for x in test["suites"])
assert record(ROOT/test["log"]["path"])==test["log"] and record(ROOT/test["xml"]["path"])==test["xml"]
replay_path=AUDIT/"actual-native-cache-layout-production-replay.json"
replay=json.loads(replay_path.read_bytes())
assert replay["status"]=="passed" and replay["archive_count"]==47 and replay["archive_bytes"]==246673988
assert replay["input_bytes_rechecked_unchanged"] and replay["all_output_bytes_rechecked"] and replay["existing_output_refused"]
owned_paths=sorted([p for p in AUDIT.rglob("*") if p.is_file()]+[ROOT/p for p in code_paths],
                   key=lambda p:p.relative_to(ROOT).as_posix())
assert len(owned_paths)==len(set(owned_paths))
assert not any("__pycache__" in p.parts for p in owned_paths)
owned=[record(p) for p in owned_paths]
receipt={"schema":"native-rust-apt-cache-fix-preparation/v1","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "failed_run_id":RUN,"failed_head_sha":HEAD,
         "scope":"Preparation-only native writable APT cache basename correction; no source or lock selection changes.",
         "correction":"Use APT's lowercase percent-quoted epoch in verified native cache copies; retain the original signed pool basename, portable input name, version, bytes and hash.",
         "source_change_boundary":boundary,"source_diff":record(diff_path),
         "failure_analysis":record(analysis_path),"complete_failed_run_capture":record(AUDIT/"complete-artifact-capture-summary.json"),
         "host_gate":test,"production_staging_replay":record(replay_path),
         "native_retry_status":"not run for this correction; pending parent source review/save/dispatch",
         "code_files":[record(ROOT/p) for p in code_paths],
         "protected_files_rechecked":sorted(protected,key=lambda r:r["path"]),
         "boundaries":{"main_unchanged_by_this_work":True,"release_or_version_change":False,"source_resolution_changed":False,
                       "native_build_gates_changed":False,"foundation_reinstall_workaround":False,
                       "tls_verification_disabled":False,"new_tiktoken_lock_or_later_build":False},
         "owned_files_excluding_this_receipt":owned,
         "owned_file_count_excluding_this_receipt":len(owned),
         "owned_bytes_excluding_this_receipt":sum(r["bytes"] for r in owned),
         "owned_ledger_sha256":ledger_digest(owned)}
receipt_path=AUDIT/"native-cache-fix-preparation.json"
save(receipt_path,receipt)
complete=sorted(owned+[record(receipt_path)],key=lambda r:r["path"])
print(json.dumps({"receipt":record(receipt_path),"complete_owned_files":len(complete),
                  "complete_owned_bytes":sum(r["bytes"] for r in complete),
                  "complete_owned_ledger_sha256":ledger_digest(complete),"code_files":receipt["code_files"],
                  "source_diff":record(diff_path),"failure_analysis":record(analysis_path),
                  "protected_count":len(protected),"complete_artifact_bytes":analysis["complete_capture"]["bytes"],
                  "complete_artifact_members":analysis["complete_capture"]["members"],
                  "host_tests":126,"host_skips":0,"production_staging_archives":47},indent=2))
