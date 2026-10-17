from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
repo,previous,out,proof,candidate,audio,opensles,openssl=map(Path,sys.argv[1:9])
expected=json.loads(sys.argv[9])
def record(path):
 with path.open("rb") as stream:d=hashlib.file_digest(stream,"sha256").hexdigest()
 return {"bytes":path.stat().st_size,"sha256":d}
before={name:record(repo/name) for name in expected}
assert before==expected
assert not out.exists() and not proof.exists()
result=subprocess.run([sys.executable,"-B",str(repo/"scripts/prepare_audio_device_bundle.py"),"build",
 "--candidate-archive",str(candidate),"--audio-archive",str(audio),"--opensles-deb",str(opensles),
 "--openssl-deb",str(openssl),"--out",str(out)],cwd=repo,capture_output=True,check=False)
proof.with_suffix(".stdout").write_bytes(result.stdout)
proof.with_suffix(".stderr").write_bytes(result.stderr)
assert result.returncode==0, result.stderr.decode("utf-8",errors="replace")[-2000:]
after={name:record(repo/name) for name in expected}
assert before==after
manifest=json.loads((out/"manifest.json").read_bytes())
prior=json.loads((previous/"manifest.json").read_bytes())
receipt=json.loads((out/"BUNDLE-RECEIPT.json").read_bytes())
entries={e["path"]:e for e in manifest["entries"]};old={e["path"]:e for e in prior["entries"]}
source_names={"staging/prepare_audio_device_bundle.py":"scripts/prepare_audio_device_bundle.py",
 "staging/prepare_audio_device_environment.py":"scripts/prepare_audio_device_environment.py",
 "staging/audio_device_bundle_lock.json":"scripts/audio_device_bundle_lock.json"}
for embedded,source in source_names.items():
 e=entries[embedded];v=before[source]
 assert e["size"]==v["bytes"] and e["sha256"]==v["sha256"]
assert old.keys()<=entries.keys()
changed=sorted(k for k in old if old[k]!=entries[k])
assert set(changed)=={"staging/prepare_audio_device_bundle.py","staging/audio_device_bundle_lock.json"},changed
added=sorted(entries.keys()-old.keys())
assert added==["runtime-libs/lib/libtermux-platform-ns.so"],added
assert manifest["wheels"]==prior["wheels"] and len(manifest["wheels"])==102
assert manifest["candidate"]==prior["candidate"] and manifest["source_changes"]==prior["source_changes"]
lock=manifest["lock"]
assert lock==json.loads((repo/"scripts/audio_device_bundle_lock.json").read_bytes())
pin=lock["opensles"]["platform_namespace"];entry=entries[pin["file"]]
assert entry["size"]==pin["size"] and entry["sha256"]==pin["sha256"]
import copy
prior_lock=copy.deepcopy(lock)
prior_lock["opensles"].pop("platform_namespace")
assert prior_lock==prior["lock"]
assert lock["openssl"]==prior["lock"]["openssl"]
files={name:record(out/name) for name in ("payload.tar.gz","manifest.json","prepare.sh","BUNDLE-RECEIPT.json")}
for name,value in receipt["files"].items():
 assert files[name]=={"bytes":value["size"],"sha256":value["sha256"]}
assert receipt["status"]=="prepared-input-bundle"
for key in ("assembly_validated_natively","audio_readiness","microphone_accessed","recording_tested"):
 assert receipt[key] is False
subprocess.run([r"C:\Program Files\Git\bin\bash.exe","-n",str(out/"prepare.sh").replace("\\","/")],cwd=repo,check=True)
output={"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),
 "purpose":"Frozen source and prepared transfer proof after retaining the original namespace helper from the same OpenSL ES archive",
 "source_inputs":before,"all_source_bytes_unchanged_during_build":True,"embedded_source_inputs_match":True,
 "previous_checkpoint":str(previous),"checkpoint":str(out),"files":files,"entry_count":len(entries),
 "wheel_count":len(manifest["wheels"]),"changed_prior_entries":changed,"added_entries":added,
 "all_other_prior_entries_identical":True,"wheel_manifest_unchanged":True,"candidate_identity_unchanged":True,
 "audio_source_patch_outputs_unchanged":True,"bootstrap_shell_syntax_passed":True,
 "native_execution_performed":False,"audio_readiness":False,"microphone_accessed":False,"recording_tested":False,
 "original_build_stdout":record(proof.with_suffix(".stdout")),"original_build_stderr":record(proof.with_suffix(".stderr"))}
proof.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(json.dumps({"status":"prepared-and-verified","proof":record(proof),"proof_path":str(proof),
 "files":files,"entry_count":len(entries),"changed_prior_entries":changed,"added_entries":added,"native_execution_performed":False},indent=2))
