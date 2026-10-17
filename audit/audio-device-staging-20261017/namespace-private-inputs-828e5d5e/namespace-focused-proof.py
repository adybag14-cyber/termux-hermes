from pathlib import Path
import copy,hashlib,importlib.util,json,re,subprocess,sys,traceback
from datetime import datetime,timezone
REPO=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\termux-hermes-resume-20261017")
OUT=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\audio-staging-input-audit-20261017\\platform-namespace-routing-20261017")
WS=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace")
EXPECTED={
"scripts/prepare_audio_device_environment.py":(63097,"bd72d882ae712f84b636e6266f60a0037055dfb3ad656ed80ca7d1cb80255197"),
"tests/test_audio_device_staging.py":(72797,"7c36a03efecdae97e42c620522e048ae0fa1143cda3aeb19d51b1ad572a01701"),
"scripts/prepare_audio_device_bundle.py":(38774,"828e5d5e78ac9dd1bebe8b7eb446add51cfc1f2112a9c7fead8cee794494629c"),
"scripts/audio_device_bundle_lock.json":(21815,"d2ef118edb68335f49f43db563ab966b08dcfd217fabe44980956bd4eb9162a9")}
def info(p):
 b=Path(p).read_bytes();return {"size":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def sources():
 rows={n:info(REPO/n) for n in EXPECTED}
 assert all((rows[n]["size"],rows[n]["sha256"])==v for n,v in EXPECTED.items()),rows
 return rows
def save(name,value):
 p=OUT/name;assert not p.exists(),str(p)
 p.write_bytes((json.dumps(value,indent=2,sort_keys=True)+"\n").encode())
 return {"path":str(p),**info(p)}
before=sources()
proof={"schema_version":1,"scope":"Focused host namespace-input regressions and exact original input verification",
"source_before":before,"driver":info(Path(__file__)),"host":{"python":sys.version,"platform":sys.platform},
"native_execution_performed":False,"device_readiness":False,"network_or_install_operations":False,
"started_utc":datetime.now(timezone.utc).isoformat()}
exit_code=1
try:
 wheel=WS/"audio-staging-input-audit-20261017/requirement-parser-adaptation-20261017/packaging-26.0-py3-none-any.whl"
 assert info(wheel)=={"size":74366,"sha256":"b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529"}
 child="import sys;sys.path.insert(0,"+repr(str(wheel))+");import packaging;assert packaging.__version__=='26.0';import pytest;raise SystemExit(pytest.main(['-q','tests/test_audio_device_staging.py']))"
 command=[sys.executable,"-c",child]
 result=subprocess.run(command,cwd=REPO,capture_output=True,timeout=75)
 for name,data in (("focused-namespace-1.stdout",result.stdout),("focused-namespace-1.stderr",result.stderr)):
  p=OUT/name;assert not p.exists();p.write_bytes(data)
 stdout=result.stdout.decode("utf-8",errors="replace")
 counts=re.findall(r"(?<![\w-])(\d+) passed",stdout)
 proof["focused_regressions"]={"command":command,"working_directory":str(REPO),"exit_code":result.returncode,
 "packaging":{"version":"26.0",**info(wheel)},"passed":int(counts[-1]) if counts else None,
 "stdout":info(OUT/"focused-namespace-1.stdout"),"stderr":info(OUT/"focused-namespace-1.stderr")}
 print(stdout)
 if result.stderr:print(result.stderr.decode("utf-8",errors="replace"),file=sys.stderr)
 assert result.returncode==0,"focused namespace regression failed"
 lock=json.loads((REPO/"scripts/audio_device_bundle_lock.json").read_bytes())
 oldpath=WS/"audio-device-bundle-resume-20261017/checkpoint-6/manifest.json"
 assert info(oldpath)=={"size":5643205,"sha256":"cec6b5b01c391b087e61201b6a31a77322d03094d16267169198cf4d3cdca627"}
 old=json.loads(oldpath.read_bytes())
 stripped=copy.deepcopy(lock)
 ns=stripped["opensles"].pop("platform_namespace")
 assert stripped==old["lock"],"an unrelated frozen lock field changed"
 oldrows={row["path"]:row for row in old["entries"]}
 assert ns["file"] not in oldrows
 assert (oldrows[lock["opensles"]["file"]]["size"],oldrows[lock["opensles"]["file"]]["sha256"])==(lock["opensles"]["size"],lock["opensles"]["sha256"])
 archive=WS/"audio-staging-input-audit-20261017/libandroid-stub_30-2_aarch64.deb"
 spec=importlib.util.spec_from_file_location("namespace_original_packer",REPO/"scripts/prepare_audio_device_bundle.py")
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 additions=module.verified_opensles_additions(archive,lock["opensles"])
 selected=[lock["opensles"],ns]
 assert set(additions)=={r["file"] for r in selected}
 actual={}
 for row in selected:
  data=additions[row["file"]]
  identity={"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
  assert identity=={k:row[k] for k in ("size","sha256")}
  actual[row["file"]]={"member":row["member"],**identity}
 elfpath=OUT/"frozen-stub-elf-trace.json"
 assert info(elfpath)["sha256"]=="85bcf38a1e6aca3edaef0e854cba36612f10c435866c6c8dea468ee94a762e80"
 elf=json.loads(elfpath.read_bytes())
 opensles=elf["members"][lock["opensles"]["member"]]
 namespace=elf["members"][ns["member"]]
 assert any(d=={"tag":"NEEDED","value":"libtermux-platform-ns.so"} for d in opensles["elf"]["dynamic"])
 assert {r["value"] for r in namespace["elf"]["dynamic"] if r["tag"]=="NEEDED"}=={"libc.so","libdl.so"}
 assert {k:namespace[k] for k in ("size","sha256")}=={k:ns[k] for k in ("size","sha256")}
 binding={"schema_version":1,"source":before,"archive":{"path":str(archive),**info(archive)},
 "selected_original_members":actual,"previous_manifest":{"path":str(oldpath),**info(oldpath)},
 "all_prior_lock_fields_unchanged":True,"prior_opensles_wrapper_preserved":True,"namespace_previously_absent":True,
 "elf_trace":{"path":str(elfpath),**info(elfpath)},"namespace_dynamic_dependencies":["libc.so","libdl.so"],
 "namespace_requested_by_bare_dt_needed":True,"new_archive_required":False,
 "runtime_helper_changed":False,"mapped_library_guard_changed":False,
 "native_routing_verified_by_this_host_check":False}
 proof["original_input_binding"]=save("original-namespace-input-binding.json",binding)
 rawlog=WS/"audio-native-verification-resume-20261017/run-39074656769-raw/job.log"
 raw=rawlog.read_bytes()
 diagnostic_lines=[line for line in raw.splitlines(keepends=True) if b'"expected_portaudio_failure": true' in line and b'libtermux-platform-ns.so' in line]
 assert len(diagnostic_lines)==1
 diagnostic=json.loads(diagnostic_lines[0][diagnostic_lines[0].index(b"{"):])
 assert diagnostic["protocol_valid"] is False and diagnostic["expected_portaudio_failure"] is True
 assert diagnostic["error"]["message"].endswith("/data/data/com.termux/files/usr/lib/libtermux-platform-ns.so")
 p=OUT/"observed-native-diagnostic.log";assert not p.exists();p.write_bytes(diagnostic_lines[0])
 proof["observed_native_failure"]={"run_id":39074656769,"raw_job":{"path":str(rawlog),**info(rawlog)},
 "raw_diagnostic_line":{"path":str(p),**info(p)},"diagnostic":diagnostic}
 proof["passed"]=True
 exit_code=0
except BaseException as exc:
 proof["passed"]=False;proof["error"]={"type":type(exc).__name__,"message":str(exc)}
 tb=traceback.format_exc().encode();(OUT/"focused-namespace-1.exception").write_bytes(tb)
 print(tb.decode(),file=sys.stderr)
finally:
 proof["source_after"]=sources()
 assert proof["source_after"]==before
 proof["completed_utc"]=datetime.now(timezone.utc).isoformat()
 receipt=save("focused-namespace-1.json",proof)
 print(json.dumps({"exit_code":exit_code,"receipt":receipt,"passed_count":proof.get("focused_regressions",{}).get("passed"),"source_unchanged":True}))
raise SystemExit(exit_code)
