import datetime,hashlib,json,os,pathlib,subprocess,sys,xml.etree.ElementTree as ET
root=pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
audit=root/"audit/neutts-rust-native-20261017/run-39082981266"
log=audit/"rust-host-tests-native-cache-fix.log"
xml=audit/"rust-host-tests-native-cache-fix.xml"
assert not log.exists() and not xml.exists()
env=os.environ.copy()
selected={"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","HERMES_RUST_TLS_OPENSSL":r"C:\Strawberry\c\bin\openssl.EXE"}
env.update(selected)
argv=[sys.executable,"-I","-B","-m","pytest","-q","tests/test_neutts_rust_preparation.py","--junitxml="+xml.relative_to(root).as_posix()]
result=subprocess.run(argv,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
log.write_bytes(result.stdout)
def record(path):
    raw=path.read_bytes()
    return {"path":path.relative_to(root).as_posix(),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
suites=[x.attrib for x in ET.parse(xml).getroot().iter("testsuite")]
receipt={"schema":"native-rust-cache-filename-host-gate/v1","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"command":argv,"environment":selected,"exit_code":result.returncode,"python":sys.version,"openssl":subprocess.check_output([selected["HERMES_RUST_TLS_OPENSSL"],"version"],text=True,timeout=10).strip(),"log":record(log),"xml":record(xml),"suites":suites}
(audit/"native-cache-host-test-environment.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(result.stdout.decode("utf-8","replace"))
print(json.dumps(receipt))
raise SystemExit(result.returncode)
