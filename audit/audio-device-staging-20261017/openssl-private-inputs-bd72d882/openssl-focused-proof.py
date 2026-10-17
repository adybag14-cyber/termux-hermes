from pathlib import Path
import hashlib, importlib.util, io, json, os, re, subprocess, sys, tarfile, traceback
from datetime import datetime, timezone

REPO = Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\termux-hermes-resume-20261017")
OUT = Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\audio-staging-input-audit-20261017\\openssl-provider-routing-20261017")
WORKSPACE = Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace")
EXPECTED = {
"scripts/prepare_audio_device_environment.py": (63097, "bd72d882ae712f84b636e6266f60a0037055dfb3ad656ed80ca7d1cb80255197"),
"tests/test_audio_device_staging.py": (68033, "8d835c3d3c110c904e3fe6debac5f2ffc8c05fdf8a21342a2dda9dce1cd8e5b4"),
"scripts/prepare_audio_device_bundle.py": (37568, "456d3d32a393c1dbddda08d99036c3b3e60f3339172bb5dd42f064faa0f8f8b3"),
"scripts/audio_device_bundle_lock.json": (21537, "664efe4fc15300a4cb33da28aab1352da0255d530a8427ace17298d09f5f14d6"),
}
def info(path):
    raw=Path(path).read_bytes()
    return {"size":len(raw), "sha256":hashlib.sha256(raw).hexdigest()}
def save_json(name, data):
    path=OUT/name
    assert not path.exists(), str(path)
    path.write_bytes((json.dumps(data, indent=2, sort_keys=True)+"\n").encode())
    return {"path":str(path), **info(path)}
def sources():
    rows={name:info(REPO/name) for name in EXPECTED}
    assert all((rows[n]["size"], rows[n]["sha256"]) == value for n,value in EXPECTED.items()), rows
    return rows

OUT.mkdir(parents=True,exist_ok=True)
before=sources()
proof={"schema_version":1,"scope":"Focused host staging regressions and original frozen OpenSSL input binding; not native runtime or hardware proof",
       "started_utc":datetime.now(timezone.utc).isoformat(),"source_before":before,
       "host":{"python":sys.version,"platform":sys.platform,"executable":sys.executable},
       "driver":info(Path(__file__)), "native_validation_passed":False, "device_readiness":False,
       "source_or_runtime_payload_mutated":False,"network_or_install_operations":False}
exit_code=1
try:
    packaging_wheel=WORKSPACE/"audio-staging-input-audit-20261017/requirement-parser-adaptation-20261017/packaging-26.0-py3-none-any.whl"
    packaging_identity=info(packaging_wheel)
    assert packaging_identity == {"size":74366,"sha256":"b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529"}
    child="import sys;sys.path.insert(0,"+repr(str(packaging_wheel))+");import packaging;assert packaging.__version__=='26.0';import pytest;raise SystemExit(pytest.main(['-q','tests/test_audio_device_staging.py']))"
    command=[sys.executable,"-c",child]
    result=subprocess.run(command,cwd=REPO,capture_output=True,timeout=75)
    for name,data in (("focused-openssl-1.stdout",result.stdout),("focused-openssl-1.stderr",result.stderr)):
        p=OUT/name
        assert not p.exists(), str(p)
        p.write_bytes(data)
    output=result.stdout.decode("utf-8",errors="replace")
    counts=re.findall(r"(?<![\w-])(\d+) passed",output)
    proof["focused_regressions"]={"command":command,"working_directory":str(REPO),"exit_code":result.returncode,
        "packaging":{"version":"26.0","wheel":str(packaging_wheel),**packaging_identity},
        "passed":int(counts[-1]) if counts else None,
        "stdout":info(OUT/"focused-openssl-1.stdout"),"stderr":info(OUT/"focused-openssl-1.stderr")}
    print(output)
    if result.stderr:
        print(result.stderr.decode("utf-8",errors="replace"),file=sys.stderr)
    assert result.returncode==0, "focused staging regressions failed"

    lock=json.loads((REPO/"scripts/audio_device_bundle_lock.json").read_bytes())
    manifest_path=WORKSPACE/"audio-device-bundle-resume-20261017/checkpoint-5/manifest.json"
    original_manifest_identity=info(manifest_path)
    assert original_manifest_identity["sha256"]=="dab3c2888f0b56f432cacc1b18cd387c1dc4dfdf249ffbe7e3c4c891a2aaebdf"
    old=json.loads(manifest_path.read_bytes())
    assert {k:v for k,v in lock.items() if k!="openssl"}==old["lock"], "existing frozen lock fields changed"
    rows={r["path"]:r for r in old["entries"]}
    pin=lock["openssl"]
    original_libraries={}
    for name,row in pin["libraries"].items():
        for file in (row["file"], row["file"].removesuffix(".3")):
            frozen=rows[file]
            assert frozen["kind"]=="file"
            assert (frozen["size"],frozen["sha256"]) == (row["size"],row["sha256"])
            original_libraries[file]={"kind":frozen["kind"],"size":frozen["size"],"sha256":frozen["sha256"]}
    for key in ("provider","config"):
        assert pin[key]["file"] not in rows, "claimed missing input already present"

    archive=WORKSPACE/"audio-staging-input-audit-20261017/openssl_1-3.6.5_aarch64.deb"
    spec=importlib.util.spec_from_file_location("openssl_focused_packer",REPO/"scripts/prepare_audio_device_bundle.py")
    packer=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packer)
    verified=packer.verified_openssl_additions(archive,pin)
    assert set(verified)=={pin["provider"]["file"],pin["config"]["file"]}
    returned={}
    for name,data in verified.items():
        row={"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        expected=pin["provider"] if name==pin["provider"]["file"] else pin["config"]
        assert row=={k:expected[k] for k in ("size","sha256")}
        returned[name]=row
    actual_members={}
    wanted={r["member"]:r for r in [pin["provider"],pin["config"],*pin["libraries"].values()]}
    with tarfile.open(fileobj=io.BytesIO(packer.deb_data(archive)),mode="r:*") as tf:
        for member in tf:
            if member.name not in wanted:
                continue
            assert member.isfile()
            raw=tf.extractfile(member).read()
            row={"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
            assert row == {k:wanted[member.name][k] for k in ("size","sha256")}
            assert member.name not in actual_members
            actual_members[member.name]=row
    assert set(actual_members)==set(wanted)
    binding={"schema_version":1,"scope":"Original package verification and unchanged candidate-library byte binding on the host",
      "archive":{"path":str(archive),**info(archive)},"locked_openssl":pin,
      "members":actual_members,"returned_additions":returned,
      "previous_manifest":{"path":str(manifest_path),**original_manifest_identity},
      "original_candidate_library_aliases":original_libraries,
      "prior_provider_and_config_absent":True,"all_other_lock_fields_unchanged":True,
      "verification_api":"prepare_audio_device_bundle.verified_openssl_additions","source":before,
      "host_only":True,"native_or_device_readiness":False}
    assert binding["archive"]["sha256"]==pin["archive"]["sha256"]
    assert binding["archive"]["size"]==pin["archive"]["size"]
    proof["original_input_binding"]=save_json("original-openssl-input-binding.json",binding)
    proof["source_trace"]={"path":str(OUT/"source-trace.json"),**info(OUT/"source-trace.json")}
    proof["passed"]=True
    exit_code=0
except BaseException as exc:
    proof["passed"]=False
    proof["error"]={"type":type(exc).__name__,"message":str(exc)}
    tb=traceback.format_exc().encode()
    (OUT/"focused-openssl-1.exception").write_bytes(tb)
    print(tb.decode(),file=sys.stderr)
finally:
    proof["source_after"]=sources()
    assert proof["source_after"]==before
    proof["completed_utc"]=datetime.now(timezone.utc).isoformat()
    receipt=save_json("focused-openssl-1.json",proof)
    print(json.dumps({"exit_code":exit_code,"receipt":receipt,"passed_count":proof.get("focused_regressions",{}).get("passed"),"source_unchanged":True}))
raise SystemExit(exit_code)
