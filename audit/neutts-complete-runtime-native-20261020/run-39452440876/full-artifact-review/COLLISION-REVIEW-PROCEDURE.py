"""Bind the independently found input collision to the exact admitted retry artifact."""
import base64,csv,hashlib,io,json,pathlib,stat,sys,zipfile
ROOT=pathlib.Path(sys.argv[1]);BASE=pathlib.Path(sys.argv[2])
DEST=ROOT/"audit/neutts-complete-runtime-native-20261020/run-39452440876/full-artifact-review"
proof_path=ROOT.parent/"neutts-complete-runtime-root-checkpoint-20261020/diagnostic-39452440876/CROSS-WHEEL-COLLISIONS.json"
proof_raw=proof_path.read_bytes()
def sha(raw):return hashlib.sha256(raw).hexdigest()
assert sha(proof_raw)=="674baeaf9ac2d810d8ad592661229c4f08e88ee761d94590c416e898e1e3e5d6"
proof=json.loads(proof_raw)
assert proof["wheel_count"]==105 and proof["shared_targets"]==proof["different_payload_count"]==len(proof["collisions"])==1
collision=proof["collisions"][0]
assert collision["target"]=="/site/docs/source/conf.py" and len(collision["owners"])==2
lock=json.loads((DEST/"artifact/complete-inputs/neutts_complete_runtime_lock.json").read_bytes())
packages={p["artifact"]["filename"]:p for p in lock["packages"]}
expected={
 "einx-0.4.3-py3-none-any.whl":(1635,"386f1a451b02667af9c1b3337bbad94972c4031af9a1f757b7186a33e587dcd2"),
 "phonemizer-3.3.0-py3-none-any.whl":(2051,"8ff1bfe77a14e0bec2e5d34e8fb3f92e155c12ee32778ff1d817e29936fdfce4")}
assert {p["wheel"] for p in collision["owners"]}==set(expected)
rows=[]
with zipfile.ZipFile(BASE/"artifact.zip") as archive:
 for owner in collision["owners"]:
  wheel_name=owner["wheel"];pin=packages[wheel_name]
  parent_member="complete-inputs/wheels/"+wheel_name
  wheel_raw=archive.read(parent_member)
  assert len(wheel_raw)==pin["artifact"]["bytes"] and sha(wheel_raw)==pin["artifact"]["sha256"]
  member=owner["member"]
  assert member=="docs/source/conf.py"
  with zipfile.ZipFile(io.BytesIO(wheel_raw)) as wheel:
   assert wheel.namelist().count(member)==1
   info=wheel.getinfo(member)
   assert info.orig_filename==member and info.file_size<4096 and not info.flag_bits&1
   assert stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG)
   raw=wheel.read(member)
   size,digest=expected[wheel_name]
   assert len(raw)==info.file_size==owner["bytes"]==size and sha(raw)==owner["sha256"]==digest
   record_raw=wheel.read(pin["wheel"]["record_member"])
   assert sha(record_raw)==pin["wheel"]["record_sha256"]
   records=[r for r in csv.reader(io.StringIO(record_raw.decode())) if r[0]==member]
   assert len(records)==1 and records[0][1]=="sha256="+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
   assert int(records[0][2])==size
  rows.append({"name":pin["name"],"version":pin["version"],"wheel_artifact":pin["artifact"],
   "artifact_member":parent_member,"wheel_member":member,"member_bytes":size,"member_sha256":digest,
   "member_crc32":f"{info.CRC:08x}","original_record_row_verified":True})
assert rows[0]["member_sha256"]!=rows[1]["member_sha256"]
result={"schema":"original-wheel-input-collision-review/v1","run_id":39452440876,"job_id":118730511837,
 "head_sha":"11f7bb6e069e3ee00b5d530997b7d91b690c1781","artifact_id":12278513966,
 "whole_artifact_sha256":"0024d291eeb977de65bff4c39712ca6dee4f3ba31b10b4a725378fb89fc423e3",
 "status":"exact-original-input-collision-proved","shared_install_target":"site-packages/docs/source/conf.py",
 "members":rows,"both_original_payloads_can_coexist_at_same_target_unchanged":False,
 "root_full_105_wheel_collision_scan":{"retained_receipt":"ORIGINAL-CROSS-WHEEL-COLLISIONS.json",
 "bytes":len(proof_raw),"sha256":sha(proof_raw),"shared_target_count":1,"different_payload_count":1},
 "this_independent_check_scope":"Exact two wheel/member bytes and their original RECORD rows within the fully verified retry artifact",
 "observed_native_error":{"type":"ProbeError","message":"Installed wheel file bytes changed","stage":"inputs"},
 "original_native_diagnostic_names_specific_rejected_member":False,
 "specific_first_rejected_installed_member_proven":False,
 "native_operation_groups_reached":0,"native_runtime_pass_claimed":False,
 "source_correction_or_retry_outcome_claimed":False,
 "source_modified":False,"release_output":False}
def save(name,raw):
 p=DEST/name
 if p.exists():assert p.read_bytes()==raw
 else:p.write_bytes(raw)
save("ORIGINAL-CROSS-WHEEL-COLLISIONS.json",proof_raw)
body=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode()
save("ORIGINAL-INPUT-COLLISION-REVIEW.json",body)
save("COLLISION-REVIEW-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"path":str(DEST/"ORIGINAL-INPUT-COLLISION-REVIEW.json"),"bytes":len(body),
 "sha256":sha(body),"target":result["shared_install_target"],"members":len(rows),
 "original_native_diagnostic_names_specific_rejected_member":False}))
