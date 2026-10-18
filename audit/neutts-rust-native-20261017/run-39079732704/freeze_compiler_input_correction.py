"""Freeze the reviewed Rust compiler input correction and complete failed-run evidence."""
from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT=ROOT/"audit/neutts-rust-native-20261017/run-39079732704"
CODE=[
 "scripts/neutts_rust_sources_lock.json",
 "scripts/prepare_neutts_rust_sources.py",
 "scripts/compatibility_probe_neutts_rust.py",
 "tests/test_neutts_rust_preparation.py",
 "docs/neutts-rust-preparation.md"]
EXPECTED={
 "scripts/neutts_rust_sources_lock.json":"de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670",
 "scripts/prepare_neutts_rust_sources.py":"db8ce00daaece15f69b4f7b1de415accd207f13e256b2097d4efcb2d0894c428",
 "scripts/compatibility_probe_neutts_rust.py":"cdcff92a28d310536becc9e84e68b4683b45dca2f9230584a748dd72c930276b",
 "tests/test_neutts_rust_preparation.py":"82a2c0e881810d7aedaba532407e9704a96a6a3d7952d25a0a4fbc2a92253297"}
PROTECTED={
 "scripts/neutts_rust_operations.py":"a8576c384d3c5aa3854c430df83e6cfb3b1f6a69ba75713079bb6947fee125a7",
 "scripts/compatibility_probe_neutts_rust.sh":"ef8396660721039b0c087b0e69915ba7e537ac723cead9229b3b9cee7dd25428",
 ".github/workflows/neutts-rust-components.yml":"d88f44abc37d4995781833178e677bd0aa4ce428924e835934d2305e1b8118a9",
 "scripts/validate_neutts_apt_python.py":"7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29",
 "audit/neutts-rust-native-20261017/run-39077868589/selected-index-fix-preparation.json":"fc4ff9fce51b54aa6a3cffbb9231fc0a2ae1fe1e732f0918dda960eddfa48ce6",
 "audit/neutts-rust-native-20261017/run-39077868589/complete-failed-run-capture-checkpoint.json":"83bb897eac24b803dc73cc973d8d6446865a03081d276d1220f8d9b918c9f07d"}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def ident(path):
 raw=path.read_bytes()
 return {"path":path.relative_to(ROOT).as_posix(),"bytes":len(raw),"sha256":sha(raw)}
def json_bytes(value): return (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()
def verify_rows(rows):
 for row in rows:
  assert ident(ROOT/row["path"])==row, ("Frozen file changed",row["path"])
def main():
 out=AUDIT/"compiler-input-fix-preparation.json";assert not out.exists()
 for name,digest in {**EXPECTED,**PROTECTED}.items():
  assert ident(ROOT/name)["sha256"]==digest, name
 protected=[ident(ROOT/name) for name in sorted(PROTECTED)]
 failure=json.loads((AUDIT/"compiler-input-failure-analysis.json").read_bytes())
 assert failure["run_id"]==39079732704 and len(failure["stages"])==2
 review=json.loads((AUDIT/"compiler-input-archive-review-attempt3.json").read_bytes())
 replay_path=AUDIT/"compiler-input-corrected-archive-replay.json"
 replay=json.loads(replay_path.read_bytes())
 assert replay["status"]=="passed-host-archive-replay" and replay["archive_count"]==47
 assert replay["requested_path_count"]==89 and replay["unique_original_regular_file_count"]==88
 assert replay["actual_ar_data_members_executed"] and replay["actual_verify_archive_set_executed"]
 assert replay["parser_functions_or_limits_mocked"] is False
 assert ident(replay_path)["sha256"]=="ab635efa36dcb37e2891dbe813781817ad6c674ebb7e0fdda3f86a4b203eade8"
 assert ident(AUDIT/"rust-host-tests-compiler-input-fix-attempt2.log")["sha256"]=="46c7c6df2e51ec4b81fcf411ca4636eaaecc23e31e48681065609074106b51c9"
 xml=AUDIT/"rust-host-tests-compiler-input-fix-attempt2.xml"
 assert ident(xml)["sha256"]=="38aa851d746146c0cbded3d8177e558507895d9a707bcb435a5654bc62bf9b1a"
 suites=[e.attrib for e in ET.parse(xml).getroot().findall("testsuite")]
 assert len(suites)==1 and suites[0]["tests"]=="110"
 assert all(suites[0][k]=="0" for k in ("errors","failures","skipped"))
 host=json.loads((AUDIT/"host-test-environment.json").read_bytes())
 assert host["exit_code"]==0 and host["suites"]==suites
 capture=json.loads((AUDIT/"complete-artifact-capture-summary.json").read_bytes())
 assert capture["run_id"]==39079732704 and capture["head_sha"]=="3109530049338f8a4fe063d5ad08bbae57f7e95f"
 assert len(capture["artifacts"])==2
 copied=0; members=0; total_archive_bytes=0
 artifacts=[]
 for entry in capture["artifacts"]:
  receipt=ROOT/entry["receipt"]["path"]
  assert ident(receipt)==entry["receipt"]
  value=json.loads(receipt.read_bytes())
  assert value["all_member_crc_verified"] and value["all_member_sha256_recorded"]
  assert value["artifact_sha256"]==entry["sha256"] and value["artifact_bytes"]==entry["bytes"]
  assert value["native_success_claimed"] is False
  raw_root=AUDIT/("raw-"+value["artifact_name"])
  for member in value["members"]:
   if not member["git_audit_raw_copy"]: continue
   p=raw_root/member["name"]; raw=p.read_bytes()
   assert len(raw)==member["bytes"] and sha(raw)==member["sha256"]
   copied+=1
  members+=len(value["members"]);total_archive_bytes+=value["artifact_bytes"]
  artifacts.append({k:value[k] for k in ("artifact_id","artifact_name","artifact_bytes","artifact_sha256",
                   "artifact_path","job_id","job_conclusion")})
 assert copied==110 and members==47544 and total_archive_bytes==817178891
 diff=subprocess.run(["git","-c","core.quotePath=false","diff","--no-ext-diff","--no-textconv","--no-color","--binary","--",*CODE],
                     cwd=ROOT,capture_output=True,check=True,timeout=25)
 assert diff.stdout and not diff.stderr and diff.stdout.count(b"diff --git ")==5
 diff_path=AUDIT/"compiler-input-fix.diff";assert not diff_path.exists();diff_path.write_bytes(diff.stdout)
 code_pins=[ident(ROOT/name) for name in CODE]
 paths=[ROOT/name for name in CODE]
 paths += [p for p in AUDIT.rglob("*") if p.is_file() and "__pycache__" not in p.parts
           and not p.name.startswith("ROOT-") and p!=out]
 assert not any(p.is_symlink() for p in paths)
 assert len(paths)==len(set(paths))
 files=sorted((ident(p) for p in paths),key=lambda p:p["path"])
 digest=sha(json.dumps(files,sort_keys=True,separators=(",",":")).encode())
 record={
  "schema":"native-rust-compiler-input-fix-preparation/v1",
  "observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "scope":"Preparation-only correction of observed missing compiler input and exact original Rust member bounds.",
  "failed_run_id":39079732704,"failed_head_sha":"3109530049338f8a4fe063d5ad08bbae57f7e95f",
  "code_files":code_pins,"source_diff":ident(diff_path),
  "observed_native_result":{"both_stages":"failed at native-compiler-abi after native signed-index and compiler installation passed",
     "original_error":"Compiler/runtime path escaped prefix","original_error_recorded_offending_path":False,
     "rust_version":"1.99.1","cargo_version":"1.99.1","clang_version":"21.1.8","native_api_control_stdout":"24\n",
     "cargo_resolution_or_source_build_started":False},
  "original_failure_receipt":ident(AUDIT/"compiler-input-failure-analysis.json"),
  "corrections":{
   "sole_new_apt_input":review["supplemental_archive"],
   "build_apt_count_before":46,"build_apt_count_after":47,"foundation_overlap_count_unchanged":27,
   "compiler_addition_count_before":19,"compiler_addition_count_after":20,
   "all_original_lock_bytes_reconstructed_after_removing_only_new_input":True,
   "ordinary_apt_member_bound_bytes":64000000,"exact_larger_member_pins":review["original_native_parser_large_member_rejections"],
   "original_and_resolved_paths_recorded_before_admission":True,
   "missing_escaped_nonregular_and_resolution_errors_distinct":True,
   "whole_archive_control_owner_installed_byte_guards_retained":True,
   "tls_certificate_chain_and_hostname_controls_unchanged":True},
  "host_gate":{"status":"passed","tests":110,"failures":0,"errors":0,"skipped":0,
     "record":ident(AUDIT/"host-test-environment.json"),"log":ident(AUDIT/"rust-host-tests-compiler-input-fix-attempt2.log"),
     "xml":ident(xml),"prior_105_check_log_is_intermediate":True},
  "actual_original_archive_gate":{"status":"passed","archives":47,"requested_paths":89,"original_regular_files":88,
     "actual_production_readers_executed":True,"reader_or_limit_mocks":False,
     "record":ident(replay_path),"stdout":ident(AUDIT/"compiler-input-corrected-archive-replay-attempt1.stdout.log"),
     "stderr":ident(AUDIT/"compiler-input-corrected-archive-replay-attempt1.stderr.log"),
     "native_install_or_execution_claimed":False},
  "failed_run_capture":{"whole_artifacts":artifacts,"whole_archive_total_bytes":total_archive_bytes,
     "all_zip_member_crc_and_sha_verified_count":members,"all_saved_raw_native_members_rechecked":copied,
     "native_run_claimed_successful":False,
     "uploaded_hidden_unpacked_source_entries_remain_missing":True,
     "complete_original_download_archives_require_canonical_reconstruction":True},
  "boundaries":{"source_archives_cargo_locks_python_build_wheels_runtime_graph_unchanged":True,
     "native_operations_shell_workflow_unchanged":True,"historical_receipts_unchanged":True,
     "native_retry_for_this_correction_executed":False,"four_component_runtime_admitted":False,
     "tokenizers_full_runtime_still_requires_passed_pyyaml_output":True,"tiktoken_lock_capture_pending":True,
     "source_build_or_model_download_executed_by_this_host_gate":False,
     "commit_push_dispatch_release_actions_executed_by_this_agent":False},
  "protected_files_rechecked":protected,
  "owned_files_excluding_this_receipt":files,"owned_file_count_excluding_this_receipt":len(files),
  "owned_bytes_excluding_this_receipt":sum(row["bytes"] for row in files),
  "owned_ledger_sha256":digest}
 verify_rows(files);verify_rows(protected)
 raw=json_bytes(record);out.write_bytes(raw);assert out.read_bytes()==raw
 receipt=ident(out)
 all_files=sorted([*files,receipt],key=lambda p:p["path"])
 print(json.dumps({"receipt":receipt,"source_diff":ident(diff_path),"code_files":code_pins,
     "total_files_including_receipt":len(all_files),"total_bytes_including_receipt":sum(p["bytes"] for p in all_files),
     "complete_ledger_sha256":sha(json.dumps(all_files,sort_keys=True,separators=(",",":")).encode()),
     "owned_ledger_sha256":digest,"tests":110,"test_skips":0,
     "whole_artifact_bytes":total_archive_bytes,"all_crc_sha_members":members,"raw_copies_rechecked":copied},sort_keys=True))
if __name__=="__main__":
 main()
