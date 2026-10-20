"""Retain the exact failed complete-runtime artifact without altering historical diagnostics."""
import ast,gzip,hashlib,json,pathlib,re,subprocess,sys,zipfile
sys.stdout.reconfigure(encoding="utf-8")
ROOT=pathlib.Path(sys.argv[1]); BASE=pathlib.Path(sys.argv[2])
HEAD="88e2810572a85f1050909ee8373527e983927766"
FROZEN_DIAGNOSTIC_COMMIT="11f7bb6e069e3ee00b5d530997b7d91b690c1781"
RUN=39450032929; JOB=118722085474; ARTIFACT=12278206483
SIZE=416408782; SHA="d39ff082c5ee1de4c0b2c9363e74db976927bff6afe8eee570d4805e44862b9e"
PARENT=ROOT/"audit/neutts-complete-runtime-native-20261020/run-39450032929"
DEST=PARENT/"full-artifact-review"
DEST.mkdir(parents=True,exist_ok=True)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(path.read_bytes())
def encode(value): return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True)+"\n").encode()
def save(name,raw):
 safe=pathlib.PurePosixPath(name)
 assert not safe.is_absolute() and ".." not in safe.parts and safe.as_posix()==name
 path=DEST/safe;path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():assert path.read_bytes()==raw,"Refuse evidence replacement: "+name
 else:path.write_bytes(raw)
 return {"path":name,"bytes":len(raw),"sha256":digest(raw)}
proof=load(BASE/"FULL-DOWNLOAD-VERIFIED.json")
assert proof["head_sha"]==HEAD and proof["run_id"]==RUN and proof["artifact_id"]==ARTIFACT
assert proof["bytes"]==SIZE and proof["sha256"]==SHA
assert proof["whole_archive_verified"] is True and proof["all_members_crc_size_sha256_verified"] is True
archive_path=BASE/"artifact.zip"
assert archive_path.stat().st_size==SIZE
with archive_path.open("rb") as stream:
 assert hashlib.file_digest(stream,"sha256").hexdigest()==SHA
compressed=(BASE/"FULL-MEMBER-INVENTORY.json.gz").read_bytes()
assert len(compressed)==proof["inventory_gzip_bytes"] and digest(compressed)==proof["inventory_gzip_sha256"]
raw=gzip.decompress(compressed)
assert len(raw)==proof["inventory_json_bytes"] and digest(raw)==proof["inventory_json_sha256"]
inventory=json.loads(raw); rows={r["path"]:r for r in inventory}
assert len(rows)==len(inventory)==proof["member_count"]
run=load(BASE/"RUN-TERMINAL.json"); jobs=load(BASE/"JOBS-TERMINAL.json"); artifacts=load(BASE/"ARTIFACTS-TERMINAL.json")
assert run["id"]==RUN and run["head_sha"]==HEAD and run["conclusion"]=="failure" and run["run_attempt"]==1
job=[j for j in jobs["jobs"] if j["id"]==JOB]
assert len(job)==1 and job[0]["head_sha"]==HEAD and job[0]["conclusion"]=="failure"
artifact=[a for a in artifacts["artifacts"] if a["id"]==ARTIFACT]
assert len(artifact)==1 and artifact[0]["size_in_bytes"]==SIZE and artifact[0]["digest"]=="sha256:"+SHA
assert artifact[0]["workflow_run"]["id"]==RUN and artifact[0]["workflow_run"]["head_sha"]==HEAD
historical_names=["COMPLETE-COMPONENT-RESULT.json","COMPLETE-RUNTIME-RESULT.json",
 "complete-public-runtime.stderr.log","complete-public-runtime.stdout.log",
 "PARTIAL-DIAGNOSTIC.json","FAILURE-REVIEW.json",
 "host-ci-88e2810/original-job-log.txt","host-ci-88e2810/original-run-api.json"]
historical=[]
for name in historical_names:
 path=PARENT/pathlib.PurePosixPath(name);raw=path.read_bytes()
 original=subprocess.check_output(["git","-C",str(ROOT),"cat-file","blob",
    FROZEN_DIAGNOSTIC_COMMIT+":"+path.relative_to(ROOT).as_posix()])
 assert raw==original,"Historical diagnosis changed: "+name
 historical.append({"path":name,"bytes":len(raw),"sha256":digest(raw)})
save(".gitattributes",b"* -text\n")
for source,target in [
 ("RUN-TERMINAL.json","ORIGINAL-GITHUB-RUN.json"),("JOBS-TERMINAL.json","ORIGINAL-GITHUB-JOBS.json"),
 ("ARTIFACTS-TERMINAL.json","ORIGINAL-GITHUB-ARTIFACTS.json"),
 ("JOB-"+str(JOB)+".log","ORIGINAL-GITHUB-JOB.log"),
 ("FULL-DOWNLOAD-VERIFIED.json","FULL-DOWNLOAD-VERIFIED.json"),
 ("FULL-MEMBER-INVENTORY.json.gz","FULL-MEMBER-INVENTORY.json.gz"),
 ("FETCH-RECEIPT.json","ORIGINAL-API-FETCH-RECEIPT.json")]:
 save(target,(BASE/source).read_bytes())
z=zipfile.ZipFile(archive_path)
assert len(z.infolist())==len(inventory)
def member(name,limit=16*1024*1024):
 assert name in rows and rows[name]["bytes"]<=limit,name
 raw=z.read(name)
 assert len(raw)==rows[name]["bytes"] and digest(raw)==rows[name]["sha256"],name
 return raw
for name in historical_names[:4]:assert (PARENT/name).read_bytes()==member(name)
probe=json.loads(member("COMPLETE-PROBE-INPUTS.json"))
assert probe["head_sha"]==HEAD and probe["workflow_ref_commit"]==HEAD and probe["run_id"]==str(RUN)
assert probe["release_output"] is False and probe["production_admission_changed"] is False
bindings=[];source_text={}
process=subprocess.Popen(["git","-C",str(ROOT),"cat-file","--batch"],
 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
 for name,expected in sorted(probe["inputs"].items()):
  path=pathlib.PurePosixPath(name)
  assert path.as_posix()==name and not path.is_absolute() and ".." not in path.parts
  assert not any(c in name for c in "\\\r\n\0") and re.fullmatch("[0-9a-f]{64}",expected)
  process.stdin.write((HEAD+":"+name+"\n").encode());process.stdin.flush()
  header=process.stdout.readline().decode().strip().split()
  assert len(header)==3 and header[1]=="blob",name
  length=int(header[2]);assert 0<=length<=128*1024*1024
  remaining=length;sha=hashlib.sha256();chunks=[]
  capture=name in {"scripts/prepare_neutts_complete_runtime.py",
    "scripts/compatibility_probe_neutts_complete_runtime.py","scripts/compatibility_probe_neutts_nonrust.py"}
  while remaining:
   chunk=process.stdout.read(min(1024*1024,remaining));assert chunk
   remaining-=len(chunk);sha.update(chunk)
   if capture:chunks.append(chunk)
  assert process.stdout.read(1)==b"\n" and sha.hexdigest()==expected,name
  if capture:source_text[name]=b"".join(chunks).decode()
  bindings.append({"path":name,"bytes":length,"sha256":expected,"git_blob":header[0]})
finally:
 process.stdin.close()
 assert process.wait(timeout=10)==0
preparer=source_text["scripts/prepare_neutts_complete_runtime.py"]
module=ast.parse(preparer)
assert not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name=="safe_relative" for n in module.body)
assert "parts = prep.safe_relative(item.filename).split" in source_text["scripts/compatibility_probe_neutts_nonrust.py"]
runtime_source=source_text["scripts/compatibility_probe_neutts_complete_runtime.py"]
assert runtime_source.index('report["installed_before"] = nr.installed_inventory')<runtime_source.index('operations = report["operations"] = {}')
foundation=json.loads(member("NEUTTS-CORE-RESULT.json"))
assert foundation["status"]=="passed" and foundation["uid"]==1000 and foundation["python"]["platform"]=="android"
cases=foundation["cases"]
assert len(cases)==7 and {c["component"] for c in cases}=={"python_dependencies","torch","torchaudio","torchcodec","scipy","llvmlite","soxr"}
for case in cases:
 assert case["status"]=="passed" and case["exit_code"]==0 and case["timed_out"] is False
 assert digest(member(case["receipt"]))==case["receipt_sha256"]
for flag in ("engine_installed","synthesis_tested","model_downloaded","physical_audio_tested","candidate_modified","pm_admission_changed"):
 assert foundation[flag] is False
for field in ("apt_python_validation","apt_python_metadata"):
 assert digest(member(foundation[field]["receipt"]))==foundation[field]["sha256"]
assert digest(member(foundation["pip_check"]["log"]))==foundation["pip_check"]["log_sha256"]
component=json.loads(member("COMPLETE-COMPONENT-RESULT.json"))
runtime=json.loads(member("COMPLETE-RUNTIME-RESULT.json"))
assert component["status"]=="failed" and component["stage"]=="complete-native-runtime"
assert runtime["status"]=="failed" and runtime["stage"]=="inputs"
assert runtime["error"]=={"type":"AttributeError","message":"module '_complete_preparation' has no attribute 'safe_relative'"}
assert not any(key in runtime for key in ("installed_before","record_integrity_before","closure","operations","native_mappings","installed_after"))
for report in (component,runtime):
 for key in ("default_speech_model_downloaded","neutts_engine_installed","production_admission_changed","release_output"):
  assert report[key] is False
stderr=member("complete-public-runtime.stderr.log").decode()
assert 'line 542, in runtime_case' in stderr and 'line 379, in installed_wheel_bytes' in stderr
assert "AttributeError: module '_complete_preparation' has no attribute 'safe_relative'" in stderr
selected=[]
for name,row in rows.items():
 if name.endswith("/"):continue
 top=pathlib.PurePosixPath(name)
 choose="/" not in name and row["bytes"]<=16*1024*1024
 if top.parts[0] in ("NEUTTS-FROZEN-APT","complete-signed-snapshot") and top.name in ("RESULT.json","frozen.conf","sources.list","apt-update.log"):
  choose=True
 if name.count("/")==1 and top.suffix==".json" and top.parts[0] in ("foundation-apt-inputs","python-wheelhouse","complete-inputs","main-candidate-proof"):
  choose=True
 if choose:
  raw=member(name)
  selected.append({"original_member":name,**save("artifact/"+name,raw),"crc32":row["crc32"]})
save("EXECUTED-SOURCE-BINDINGS.json",encode({
 "schema":"native-failure-executed-source-binding/v1","head_sha":HEAD,"run_id":RUN,"job_id":JOB,"artifact_id":ARTIFACT,
 "status":"all-recorded-source-inputs-match","source_count":len(bindings),
 "source_bytes":sum(p["bytes"] for p in bindings),"sources":bindings,
 "source_receipt_member":"COMPLETE-PROBE-INPUTS.json","source_receipt_sha256":rows["COMPLETE-PROBE-INPUTS.json"]["sha256"],
 "foundation_cases_verified":sorted(c["component"] for c in cases),
 "failed_native_stage":"inputs","failed_before_first_operation_group":True,
 "exact_executed_preparer_has_no_safe_relative_definition":True,
 "same_recorded_shared_inventory_calls_prep_safe_relative":True,
 "historical_diagnostic_commit":FROZEN_DIAGNOSTIC_COMMIT,
 "historical_files_unchanged":historical,"partial_original_members_equal_whole_archive":historical_names[:4],
 "release_output":False,"complete_engine_admitted":False}))
save("SELECTED-ORIGINAL-MEMBERS.json",encode({"archive_sha256":SHA,"members":selected}))
save("RETAIN-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"complete-artifact-failure-inputs-retained","directory":str(DEST),
 "sources":len(bindings),"source_bytes":sum(p["bytes"] for p in bindings),
 "original_members_retained":len(selected),"selected_bytes":sum(p["bytes"] for p in selected),
 "historical_files_unchanged":len(historical),
 "top_members":[{"path":r["path"],"bytes":r["bytes"]} for r in inventory if "/" not in r["path"]],
 "prepared_json_members":[{"path":r["path"],"bytes":r["bytes"]} for r in inventory if r["path"].startswith("complete-inputs/") and r["path"].count("/")==1 and r["path"].endswith(".json")]},ensure_ascii=True))
