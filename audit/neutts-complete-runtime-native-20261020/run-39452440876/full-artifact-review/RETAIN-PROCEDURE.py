"""Retain the exact failed complete-runtime artifact without altering historical diagnostics."""
import ast,gzip,hashlib,json,pathlib,re,subprocess,sys,zipfile
sys.stdout.reconfigure(encoding="utf-8")
ROOT=pathlib.Path(sys.argv[1]); BASE=pathlib.Path(sys.argv[2])
HEAD="11f7bb6e069e3ee00b5d530997b7d91b690c1781"
FROZEN_DIAGNOSTIC_COMMIT="11f7bb6e069e3ee00b5d530997b7d91b690c1781"
RUN=39452440876; JOB=118730511837; ARTIFACT=12278513966
SIZE=416408851; SHA="0024d291eeb977de65bff4c39712ca6dee4f3ba31b10b4a725378fb89fc423e3"
PARENT=ROOT/"audit/neutts-complete-runtime-native-20261020/run-39452440876"
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
previous_manifest=BASE.parent/"run-39450032929"/"STAGE-MANIFEST.json"
previous_raw=previous_manifest.read_bytes()
assert digest(previous_raw)=="7cae5c9f1b96e6b0099da474135202f3813a51020f62de70bf57ff5936197191"
previous=json.loads(previous_raw)
assert previous["file_count"]==91 and previous["total_bytes"]==10912958
historical=previous["files"]
for row in historical:
 data=(ROOT/pathlib.PurePosixPath(row["path"])).read_bytes()
 assert len(data)==row["bytes"] and digest(data)==row["sha256"],row["path"]
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
assert any(isinstance(n,ast.FunctionDef) and n.name=="safe_relative" for n in module.body)
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
assert runtime["status"]=="failed" and isinstance(runtime["stage"],str)
assert set(runtime["error"])=={"type","message"} and isinstance(runtime["error"]["message"],str)
for report in (component,runtime):
 for key in ("default_speech_model_downloaded","neutts_engine_installed","production_admission_changed","release_output"):
  assert report[key] is False
stderr=member("complete-public-runtime.stderr.log").decode()
assert "Traceback (most recent call last):" in stderr and runtime["error"]["message"] in stderr
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
 "failed_native_stage":runtime["stage"],"completed_operation_groups":list(runtime.get("operations",{})),
 "exact_executed_preparer_has_safe_relative_definition":True,
 "same_recorded_shared_inventory_calls_prep_safe_relative":True,
 "previous_failure_freeze_manifest_sha256":digest(previous_raw),
 "previous_failure_files_unchanged":historical,
 "release_output":False,"complete_engine_admitted":False}))
save("SELECTED-ORIGINAL-MEMBERS.json",encode({"archive_sha256":SHA,"members":selected}))
save("RETAIN-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"complete-artifact-failure-inputs-retained","directory":str(DEST),
 "sources":len(bindings),"source_bytes":sum(p["bytes"] for p in bindings),
 "original_members_retained":len(selected),"selected_bytes":sum(p["bytes"] for p in selected),
 "historical_files_unchanged":len(historical),
 "top_members":[{"path":r["path"],"bytes":r["bytes"]} for r in inventory if "/" not in r["path"]],
 "prepared_json_members":[{"path":r["path"],"bytes":r["bytes"]} for r in inventory if r["path"].startswith("complete-inputs/") and r["path"].count("/")==1 and r["path"].endswith(".json")]},ensure_ascii=True))
