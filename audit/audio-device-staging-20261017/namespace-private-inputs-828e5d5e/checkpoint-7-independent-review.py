from pathlib import Path
import copy,hashlib,json,sys
from datetime import datetime,timezone
WS=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace");REPO=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\termux-hermes-resume-20261017");OUT=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\audio-staging-input-audit-20261017\\platform-namespace-routing-20261017")
def identity(path):
 raw=path.read_bytes();return {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def read(path):
 return json.loads(path.read_bytes())
proof_path=WS/"audio-device-bundle-resume-20261017/checkpoint-7-proof.json"
assert identity(proof_path)=={"bytes":3419,"sha256":"5600ff5e538b88e269fda284ef44bc14c2f0b6601716f63af1c8ad11fe278dae"}
proof=read(proof_path)
newdir=Path(proof["checkpoint"]);olddir=Path(proof["previous_checkpoint"])
oldproof_path=WS/"audio-device-bundle-resume-20261017/checkpoint-6-proof.json"
assert identity(oldproof_path)=={"bytes":3561,"sha256":"13d617b3ff4f32d4981d35602276845c4d605ad82cf2514ecca316c484944f1e"}
oldproof=read(oldproof_path)
checked={}
for dirname,claim in ((olddir,oldproof),(newdir,proof)):
 checked[dirname.name]={}
 for name in ("manifest.json","prepare.sh","BUNDLE-RECEIPT.json"):
  actual=identity(dirname/name)
  assert actual==claim["files"][name],(dirname,name)
  checked[dirname.name][name]=actual
old=read(olddir/"manifest.json");new=read(newdir/"manifest.json")
oldrows={r["path"]:r for r in old["entries"]};newrows={r["path"]:r for r in new["entries"]}
assert len(oldrows)==len(old["entries"])==25274
assert len(newrows)==len(new["entries"])==25275
added=sorted(newrows.keys()-oldrows.keys());removed=sorted(oldrows.keys()-newrows.keys())
changed=sorted(n for n in oldrows.keys()&newrows.keys() if oldrows[n]!=newrows[n])
assert added==["runtime-libs/lib/libtermux-platform-ns.so"] and not removed
assert changed==["staging/audio_device_bundle_lock.json","staging/prepare_audio_device_bundle.py"]
assert added==proof["added_entries"] and changed==proof["changed_prior_entries"]
for obj in (old,new):
 assert not any(r["path"].split("/")[0] in ("venv","pm-runtime","bin","state") for r in obj["entries"])
headers=lambda m:{k:v for k,v in m.items() if k not in ("archive","entries","lock")}
assert headers(old)==headers(new),"an unrelated manifest header changed"
stripped=copy.deepcopy(new["lock"]);ns=stripped["opensles"].pop("platform_namespace")
assert stripped==old["lock"]
newrow=newrows[ns["file"]]
assert newrow["kind"]=="file"
assert (newrow["size"],newrow["sha256"])==(ns["size"],ns["sha256"])==(6552,"6c39c6a3318accd5e34f4f2c9e5c9e14eed113fb3a92e8c0be86006dc9256e34")
assert len(new["wheels"])==102 and new["wheels"]==old["wheels"]
current={}
for name,pin in proof["source_inputs"].items():
 actual=identity(REPO/name);assert actual==pin,(name,actual,pin);current[name]=actual
for relative in ("scripts/prepare_audio_device_bundle.py","scripts/prepare_audio_device_environment.py","scripts/audio_device_bundle_lock.json"):
 row=newrows["staging/"+Path(relative).name]
 assert row["kind"]=="file"
 assert (row["size"],row["sha256"])==(current[relative]["bytes"],current[relative]["sha256"])
assert newrows["staging/prepare_audio_device_environment.py"]==oldrows["staging/prepare_audio_device_environment.py"]
receipts={}
for dirname,manifest,claim in ((olddir,old,oldproof),(newdir,new,proof)):
 receipt=read(dirname/"BUNDLE-RECEIPT.json")
 for name in ("manifest.json","prepare.sh","payload.tar.gz"):
  expected=claim["files"][name]
  assert receipt["files"][name]=={"size":expected["bytes"],"sha256":expected["sha256"]}
 assert manifest["archive"]=={"file":"payload.tar.gz","size":claim["files"]["payload.tar.gz"]["bytes"],"sha256":claim["files"]["payload.tar.gz"]["sha256"]}
 assert receipt["environment_included"] is False and receipt["environment_recreated_at_destination"] is True
 assert receipt["assembly_validated_natively"] is False and receipt["audio_readiness"] is False
 assert (dirname/"payload.tar.gz").stat().st_size==manifest["archive"]["size"]
 receipts[dirname.name]={"unchanged_claims":{k:v for k,v in receipt.items() if k!="files"}}
assert receipts[olddir.name]["unchanged_claims"]==receipts[newdir.name]["unchanged_claims"]
def normalized_bootstrap(directory,claim):
 raw=(directory/"prepare.sh").read_bytes()
 for name,token in (("manifest.json",b"MANIFEST_DIGEST"),("payload.tar.gz",b"ARCHIVE_DIGEST")):
  digest=claim["files"][name]["sha256"].encode()
  assert raw.count(digest)==1
  raw=raw.replace(digest,token)
 return raw
assert normalized_bootstrap(olddir,oldproof)==normalized_bootstrap(newdir,proof)
report={"schema_version":1,"status":"passed","scope":"Independent full manifest and source-entry comparison; exact small output hashes; no bundle rebuild or repeat hash of the already bound 315 MB payload",
"root_proof":{"path":str(proof_path),**identity(proof_path)},"previous_proof":{"path":str(oldproof_path),**identity(oldproof_path)},
"checked_outputs":checked,"added_entries":[newrow],"removed_entries":removed,"changed_prior_entries":changed,
"unchanged_prior_entry_count":len(oldrows)-len(changed),"entry_count":len(newrows),"wheel_count":len(new["wheels"]),
"all_other_headers_and_prior_lock_fields_unchanged":True,"all_wheel_rows_unchanged":True,
"source_inputs":current,"embedded_source_entries_match_current_files":True,"native_helper_unchanged":True,
"bootstrap_only_changes_embedded_manifest_and_archive_digests":True,"prepared_claims_unchanged":True,
"payload_validation":{"source":"root's previously completed build/hash receipt","full_hash_repeated":False,"size_rechecked":True,"claims_cross_bound_in_manifest_and_bundle_receipt":True},
"native_execution_performed":False,"audio_readiness":False,"created_utc":datetime.now(timezone.utc).isoformat(),"driver":identity(Path(__file__))}
path=OUT/"checkpoint-7-independent-review.json";assert not path.exists();path.write_bytes((json.dumps(report,indent=2,sort_keys=True)+"\n").encode())
print(json.dumps({"status":"passed","receipt":str(path),**identity(path),"added":added,"changed":changed,"unchanged_prior_entries":report["unchanged_prior_entry_count"]}))
