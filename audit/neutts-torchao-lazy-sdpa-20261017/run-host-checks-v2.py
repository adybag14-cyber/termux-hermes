from pathlib import Path
import ast,hashlib,json,os,re,subprocess,sys
from datetime import datetime,timezone
import yaml
base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
repo=base/"termux-hermes-next-stable-20261017"
work=base/"torchao-lazy-sdpa-preparation-20261017"
out=work/"host-checks-v2";out.mkdir(exist_ok=False)
env=dict(os.environ);env["TORCHAO_COMPONENT_INPUTS"]=str(work/"prepared-inputs-v2")
args=[sys.executable,"-X","utf8","-B","-m","unittest","discover","-s","tests","-p","test_neutts_torchao_component.py","-v"]
test=subprocess.run(args,cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
(out/"host-tests.stdout.log").write_bytes(test.stdout);(out/"host-tests.stderr.log").write_bytes(test.stderr)
bash=subprocess.run([r"C:\Program Files\Git\bin\bash.exe","-n",str(repo/"scripts/compatibility_probe_neutts_torchao.sh")],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
(out/"bash-syntax.stdout.log").write_bytes(bash.stdout);(out/"bash-syntax.stderr.log").write_bytes(bash.stderr)
for rel in ["scripts/prepare_neutts_torchao.py","scripts/compatibility_probe_neutts_torchao.py","tests/test_neutts_torchao_component.py"]:
 ast.parse((repo/rel).read_bytes(),filename=rel)
workflow=yaml.safe_load((repo/".github/workflows/neutts-torchao-component.yml").read_bytes())
triggers=workflow.get("on",workflow.get(True))
assert "workflow_dispatch" in triggers and triggers["push"]["branches"]==["prepare/termux-compatibility-next-stable"]
assert len(triggers["push"]["paths"])==6 and "patches/next-stable/torchao-lazy-sdpa.patch" in triggers["push"]["paths"]
assert workflow["permissions"]=={"contents":"read"}
old=(repo/"audit/neutts-torchao-native-20261017/run-39074259828/run-source/scripts/compatibility_probe_neutts_torchao.py").read_bytes()
current=(repo/"scripts/compatibility_probe_neutts_torchao.py").read_bytes()
prep_sha=hashlib.sha256((repo/"scripts/prepare_neutts_torchao.py").read_bytes()).hexdigest()
assert current.replace(prep_sha.encode(),b"0ebd003722f80b29b63e143da13c64627deb060b86ab67fdc8ea8d15d1bb5095")==old
match=re.search(rb"Ran (\d+) tests in ([0-9.]+)s",test.stderr);count=int(match.group(1)) if match else None
passed=test.returncode==0 and count==30 and b"skipped=" not in test.stderr and re.search(rb"\nOK\s*$",test.stderr) is not None
paths=["scripts/prepare_neutts_torchao.py","scripts/compatibility_probe_neutts_torchao.py","scripts/neutts_torchao_component_lock.json","scripts/compatibility_probe_neutts_torchao.sh",".github/workflows/neutts-torchao-component.yml","patches/next-stable/torchao-lazy-sdpa.patch","tests/test_neutts_torchao_component.py"]
record={"schema_version":1,"verified_utc":datetime.now(timezone.utc).isoformat(),"status":"passed" if passed and bash.returncode==0 else "failed","command":args,"environment":{"TORCHAO_COMPONENT_INPUTS":env["TORCHAO_COMPONENT_INPUTS"]},"tests":{"exit_code":test.returncode,"methods_run":count,"skipped":0 if b"skipped=" not in test.stderr else "see raw log","seconds":float(match.group(2)) if match else None},"bash_syntax_exit_code":bash.returncode,"python_ast_parse_passed":True,"scoped_workflow_guard_passed":True,"native_probe_entire_body_unchanged_except_preparer_digest":True,"native_success_claimed":False,"release_output":False,"files":[{"path":rel,"bytes":(repo/rel).stat().st_size,"sha256":hashlib.sha256((repo/rel).read_bytes()).hexdigest()} for rel in paths],"raw_logs":[{"path":p.name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.glob("*.log"))]}
(out/"HOST-VERIFICATION.json").write_text(json.dumps(record,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(record,indent=2))
if not passed:print(test.stderr.decode("utf-8"))
raise SystemExit(0 if record["status"]=="passed" else 1)
