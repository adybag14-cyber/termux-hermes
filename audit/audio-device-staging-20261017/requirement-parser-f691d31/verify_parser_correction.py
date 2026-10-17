from pathlib import Path
import copy, hashlib, json, subprocess, sys
out=Path(sys.argv[1])
repo=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-resume-20261017")
def pin(path):
 raw=path.read_bytes()
 return {"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
names=["scripts/prepare_audio_device_environment.py","tests/test_audio_device_staging.py",
       "scripts/prepare_audio_device_bundle.py","scripts/audio_device_bundle_lock.json"]
before={name:pin(repo/name) for name in names}
parser=out/"packaging-26.0-py3-none-any.whl"
code="import sys;sys.path.insert(0,"+repr(str(parser))+");import packaging;assert packaging.__version__=='26.0';import pytest;raise SystemExit(pytest.main(['-q','tests/test_audio_device_staging.py']))"
result=subprocess.run([sys.executable,"-c",code],cwd=repo,capture_output=True,timeout=60)
(out/"pytest.stdout").write_bytes(result.stdout)
(out/"pytest.stderr").write_bytes(result.stderr)
print(result.stdout.decode("utf-8",errors="replace"))
print(result.stderr.decode("utf-8",errors="replace"),file=sys.stderr)
assert result.returncode==0,"focused tests failed; original output retained"
sys.path[:0]=[str(parser),str(repo)]
from scripts import prepare_audio_device_environment as native
subset=out/"original-input-subset"
manifest=json.loads((out/"checkpoint-manifest.json").read_text())
binding=native.frozen_psutil_binding(subset,manifest)
actual_adaptations=[]
parent=native.metadata.PathDistribution(subset/"app/hermes_agent-0.0.0.dist-info")
for raw in parent.requires:
 parsed,proof=native.parse_frozen_requirement("hermes-agent",raw,"0.0.0",direct_url_binding=binding)
 if proof is not None:actual_adaptations.append(proof)
assert len(actual_adaptations)==2
tamper=[]
for name in ["app/hermes_agent-0.0.0.dist-info/METADATA","app/pyproject.toml"]:
 path=subset/name
 original=path.read_bytes()
 try:
  path.write_bytes(original[:-1]+bytes([original[-1]^1]))
  try:
   native.frozen_psutil_binding(subset,manifest)
  except native.StagingError as exc:
   tamper.append({"path":name,"rejected":True,"error":{"type":type(exc).__name__,"message":str(exc)}})
  else:
   raise AssertionError("modified source was accepted: "+name)
 finally:
  path.write_bytes(original)
 assert pin(path)==binding["source_inputs"][name]
after={name:pin(repo/name) for name in names}
assert before==after
report={"schema_version":1,"status":"passed","scope":"Focused host regression and original-input parser binding; no native runtime proof",
 "observed_failure":{"run_id":39070524219,"head_sha":"0111f4dbd08e609e0e66811360875ee267b83d34",
                    "error_excerpt":pin(out/"observed-native-error-excerpt.log")},
 "source_before":before,"source_after":after,"source_unchanged_during_tests":True,
 "parser_wheel":pin(parser),"pytest":{"argv":[sys.executable,"-c",code],"exit_code":result.returncode,
                                      "stdout":pin(out/"pytest.stdout"),"stderr":pin(out/"pytest.stderr")},
 "original_scan":pin(out/"original-parser-scan.json"),"allowed_binding":binding,
 "actual_original_adaptations":actual_adaptations,"actual_source_tamper_guards":tamper,
 "original_inputs_restored_and_unchanged":True,"metadata_rewritten":False,"install_policy_changed":False,
 "network_accessed":False,"source_build_executed":False}
(out/"focused-correction-receipt.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(json.dumps({"status":report["status"],"sources":after,"receipt":pin(out/"focused-correction-receipt.json")},indent=2))
