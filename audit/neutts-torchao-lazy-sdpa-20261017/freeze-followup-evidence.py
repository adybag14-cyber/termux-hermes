from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,io,json,zipfile
base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
repo=base/"termux-hermes-next-stable-20261017"
work=base/"torchao-lazy-sdpa-preparation-20261017"
raw=repo/"audit/neutts-torchao-lazy-sdpa-20261017"
summary=raw.with_suffix(".json")
assert not raw.exists() and not summary.exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(o):return (json.dumps(o,sort_keys=True,indent=2)+"\n").encode()
def save(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b)
 assert p.read_bytes()==b
host=json.loads((work/"host-checks-v2/HOST-VERIFICATION.json").read_bytes())
assert host["status"]=="passed" and host["tests"]["methods_run"]==30 and host["tests"]["skipped"]==0
assert host["native_probe_entire_body_unchanged_except_preparer_digest"] is True
for row in host["files"]:
 p=repo/row["path"]
 assert p.stat().st_size==row["bytes"] and sha(p.read_bytes())==row["sha256"]
 save(raw/"reviewed-source"/row["path"],p.read_bytes())
for p in (work/"host-checks-v2").iterdir():
 assert p.is_file() and not p.is_symlink()
 save(raw/"host-checks-v2"/p.name,p.read_bytes())
for row in host["raw_logs"]:
 p=raw/"host-checks-v2"/row["path"]
 assert p.stat().st_size==row["bytes"] and sha(p.read_bytes())==row["sha256"]
for p in (work/"source-review").iterdir():
 assert p.is_file() and not p.is_symlink()
 save(raw/"source-review"/p.name,p.read_bytes())
for name in ("freeze-input-lock-v2.py","run-host-checks-v2.py","implementation-v2-identities.json"):
 save(raw/name,(work/name).read_bytes())
inputs=work/"prepared-inputs-v2"
lock=json.loads((inputs/"neutts_torchao_component_lock.json").read_bytes())
receipt=json.loads((inputs/"TORCHAO-PREPARED-INPUTS.json").read_bytes())
assert receipt["lock_sha256"]==sha((inputs/"neutts_torchao_component_lock.json").read_bytes())=="10017cbb4992011143a6928b1beb09a647d6c14c9ec479d0c89e9a6f35d40de4"
assert receipt["installed"] is False and receipt["production_admission_changed"] is False
for n in ("TORCHAO-PREPARED-INPUTS.json","neutts_torchao_component_lock.json","torchao-lazy-sdpa.patch"):
 save(raw/"prepared-inputs"/n,(inputs/n).read_bytes())
original=inputs/"upstream"/lock["upstream_package"]["artifact"]["filename"]
patched=inputs/lock["package"]["artifact"]["filename"]
for p,pin in [(original,lock["upstream_package"]["artifact"]),(patched,lock["package"]["artifact"])]:
 assert p.stat().st_size==pin["bytes"] and sha(p.read_bytes())==pin["sha256"]
member_rows=[];changed=[];regular=0;unchanged=0
with zipfile.ZipFile(original) as before,zipfile.ZipFile(patched) as after:
 assert before.namelist()==after.namelist() and len(before.infolist())==len(after.infolist())==422
 assert before.testzip() is None and after.testzip() is None
 for old,new in zip(before.infolist(),after.infolist()):
  a,b=before.read(old),after.read(new)
  assert old.filename==new.filename and old.is_dir()==new.is_dir()
  if not old.is_dir():
   regular+=1
   if a==b:unchanged+=1
  if a!=b:changed.append(old.filename)
  member_rows.append({"path":old.filename,"directory":old.is_dir(),"before_bytes":len(a),"before_sha256":sha(a),"after_bytes":len(b),"after_sha256":sha(b),"unchanged_member_bytes":a==b})
 assert sorted(changed)==sorted(lock["patch"]["changed_members"]) and len(changed)==2
 assert regular==348 and unchanged==346
 for field in ("metadata","wheel","record"):
  n=lock["package"]["wheel"][field+"_member"]
  save(raw/"wheel-metadata"/("original-"+field),before.read(n))
  save(raw/"wheel-metadata"/("patched-"+field),after.read(n))
 assert before.read(lock["package"]["wheel"]["metadata_member"])==after.read(lock["package"]["wheel"]["metadata_member"])
 assert before.read(lock["package"]["wheel"]["wheel_member"])==after.read(lock["package"]["wheel"]["wheel_member"])
 assert before.read("torchao/dtypes/nf4tensor.py")==after.read("torchao/dtypes/nf4tensor.py")
save(raw/"WHEEL-MEMBER-COMPARISON.json",enc({"schema_version":1,"entry_count":422,"regular_file_count":348,"unchanged_regular_files":346,"changed_members":sorted(changed),"all_member_crcs_recomputed":True,"members":member_rows}))
old=json.loads((repo/"audit/neutts-torchao-native-20261017/run-39074259828/run-source/scripts/neutts_torchao_component_lock.json").read_bytes())
assert lock["foundation"]==old["foundation"] and lock["operation"]==old["operation"]
before_probe=(repo/"audit/neutts-torchao-native-20261017/run-39074259828/run-source/scripts/compatibility_probe_neutts_torchao.py").read_bytes()
after_probe=(repo/"scripts/compatibility_probe_neutts_torchao.py").read_bytes()
prep_sha=sha((repo/"scripts/prepare_neutts_torchao.py").read_bytes())
assert after_probe.replace(prep_sha.encode(),b"0ebd003722f80b29b63e143da13c64627deb060b86ab67fdc8ea8d15d1bb5095")==before_probe
cases=None
for node in ast.parse(after_probe).body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="CASE_NAMES" for t in node.targets):cases=ast.literal_eval(node.value)
assert cases==("real_package_import","nf4_default_quantization","independent_dequantization","linear_forward","input_gradient")
design={"schema_version":1,"reviewed_utc":datetime.now(timezone.utc).isoformat(),
"observed_native_failure":{"run_id":39074259828,"head_sha":"1fc3dde05aca3786d28d656ced9a807e872bff4f","audit":"audit/neutts-torchao-native-20261017/run-39074259828.json","error":"ModuleNotFoundError: No module named 'torch._inductor.kernel.flex_attention'","stage":"Eager optional SDPA compiler import before any CPU NF4 case"},
"change":{"member":lock["patch"]["member"],"patch":lock["patch"],"behavior":"Package-level __getattr__ defers only _int8_sdpa_init. An explicit request imports, caches and returns the original callable, retaining identity and lru_cache attributes. Unsupported or broken optional imports retain their actual exceptions.","da8w4_import_and_registration":"unchanged","other_regular_member_bytes_preserved":346,"metadata_version_tags_and_dependency_declarations":"byte-identical","distributed_operator_registration":"unchanged","nf4_implementation":"byte-identical"},
"preparation":{"source":lock["upstream_package"]["artifact"],"local_patched_artifact":lock["package"]["artifact"],"original_and_patched_full_zip_crc_record_verified":True,"deterministic_container":"ZIP_STORED with explicit Unix creator, original order/permissions and 1980-01-01 timestamp; avoids compressor and host timestamp drift.","native_input_replay":"Requires retained original wheel, exact patch, patched wheel, lock and receipt; rebuilds and compares exact output bytes before installation.","public_download_url_for_patched_bytes":None},
"host_checks":{"test_methods":30,"skipped":0,"original_tests":20,"new_artifact_boundary_tests":4,"new_lazy_import_semantics_tests":6,"source_fixture_scope":"The import-semantics tests load the actual patched initializer in a unique non-Torch temporary package with controlled peer modules. They prove deferral, original callable/cache identity, unchanged exports/da8w4 behavior, and propagation of missing and other errors. They do not substitute modules into or claim the native TorchAO gate.","native_gate_body":"entire original file unchanged except the required preparer SHA-256","cases":list(cases),"python_ast_bash_syntax_and_scoped_workflow_guards":"passed"},
"next_gate":"Root review, then the same actual installed native package import and five CPU NF4 checks.",
"full_engine_proved":False,"native_fix_proved":False,"model_downloaded":False,"audio_io_tested":False,"production_admission_changed":False,"release_output":False}
save(raw/"DESIGN.json",enc(design))
save(raw/"freeze-followup-evidence.py",Path(__file__).read_bytes())
save(raw/".gitattributes",b"* -text\n")
rows=[{"path":p.relative_to(raw).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())} for p in sorted(raw.rglob("*")) if p.is_file()]
save(raw/"SAVED-FILES.json",enc({"schema_version":1,"scope":"All raw files except this ledger","file_count":len(rows),"total_bytes":sum(r["bytes"] for r in rows),"files":rows}))
for r in rows:
 p=raw/r["path"];assert p.stat().st_size==r["bytes"] and sha(p.read_bytes())==r["sha256"]
all_raw=[p for p in raw.rglob("*") if p.is_file()]
record={"schema_version":1,"captured_utc":design["reviewed_utc"],"status":"host-verified-scoped-fix-native-retry-pending","observed_failure":design["observed_native_failure"],"patch":lock["patch"],"original_wheel":lock["upstream_package"]["artifact"],"patched_wheel":lock["package"]["artifact"],"preserved":{"metadata_version_tags_dependency_declarations":True,"other_regular_wheel_members":346,"nf4_source":True,"five_native_case_bodies":True,"foundation_and_operation_locks":True,"full_engine_graph_not_changed":True},"host_tests":{"methods_passed":30,"skipped":0,"seconds":host["tests"]["seconds"],"actual_fixture":str(inputs),"stderr_sha256":sha((raw/"host-checks-v2/host-tests.stderr.log").read_bytes())},"implementation":host["files"],"raw_evidence":{"directory":raw.relative_to(repo).as_posix(),"file_count":len(all_raw),"total_bytes":sum(p.stat().st_size for p in all_raw),"saved_files_sha256":sha((raw/"SAVED-FILES.json").read_bytes()),"all_copied_bytes_verified":True},"previous_preparation_and_failure_unchanged":["audit/neutts-torchao-preparation-20261017.json","audit/neutts-torchao-native-20261017/run-39074259828.json"],"not_claimed":["Successful native TorchAO import or NF4 operation","Complete NeuTTS or Torchtune","Model inference or audio I/O","Physical device behavior","Release readiness"],"production_admission_changed":False,"release_output":False}
save(summary,enc(record))
print(json.dumps({"summary":str(summary),"summary_bytes":summary.stat().st_size,"summary_sha256":sha(summary.read_bytes()),"raw_file_count":len(all_raw),"raw_bytes":sum(p.stat().st_size for p in all_raw),"saved_files_sha256":record["raw_evidence"]["saved_files_sha256"],"total_file_count":len(all_raw)+1,"total_bytes":sum(p.stat().st_size for p in all_raw)+summary.stat().st_size},indent=2))
