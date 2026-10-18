from pathlib import Path
import json,hashlib,zipfile,subprocess,sys,os,time
base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
repo=base/"termux-hermes-next-stable-20261017"
fix=base/"neutts-nonrust-failure-review-20261017/39081270494-fix-v1"
cap=base/"neutts-nonrust-failure-review-20261017/39081270494-v1"
lock=json.loads((repo/"scripts/neutts_nonrust_runtime_lock.json").read_bytes())
pins={p["name"]:p for p in lock["build_packages"]}
meson=fix/"meson-1.12.1-py3-none-any.whl"
assert hashlib.sha256(meson.read_bytes()).hexdigest()==pins["meson"]["artifact"]["sha256"]
cython=fix/pins["cython"]["artifact"]["filename"]
with zipfile.ZipFile(cap/"termux-neutts-nonrust-components.zip") as z:
 raw=z.read("nonrust-inputs/wheels/"+cython.name)
 assert hashlib.sha256(raw).hexdigest()==pins["cython"]["artifact"]["sha256"]
 assert not cython.exists() or cython.read_bytes()==raw
 if not cython.exists(): cython.write_bytes(raw)
 init=z.read("nonrust-inputs/sources/scikit_learn-1.9.1/sklearn/__init__.py")
out=fix/"meson-prepared-source-controls-v1";out.mkdir(exist_ok=False)
launcher="import sys;sys.path.insert(0,"+repr(str(fix/"meson-source"))+");from mesonbuild.mesonmain import main;sys.exit(main())"
env=dict(os.environ);env["PYTHONPATH"]=str(cython);env["PYTHONDONTWRITEBYTECODE"]="1"
results=[]
for label,invalid in (("selected-python",False),("source path with spaces",False),("missing-selected-python",True)):
 d=out/label;source=d/"source";build=d/"build";(source/"sklearn/_build_utils").mkdir(parents=True)
 (source/"sklearn/__init__.py").write_bytes(init)
 for name in ("version.py","tempita.py"):
  raw=(cap/"source-diagnosis-v1/sklearn/_build_utils"/name).read_bytes()
  (source/"sklearn/_build_utils"/name).write_bytes(raw)
 prepared=(fix/"prepared-inputs-v1/sources/scikit_learn-1.9.1/meson.build").read_bytes()
 source_pin=next(s for s in lock["sources"] if s["name"]=="scikit-learn")
 assert hashlib.sha256(prepared).hexdigest()==source_pin["patch"]["files"][0]["after_sha256"]
 lines=prepared.decode().splitlines()
 version_line=next(line.strip().rstrip(",") for line in lines if line.strip().startswith("version:"))
 py_line=next(line for line in lines if line.startswith("py ="))
 tempita_line=next(line for line in lines if line.startswith("tempita ="))
 meson_text="project('selected-python-control',\n "+version_line+")\n"+py_line+"\n"+tempita_line+"\n"+"""run_command(py, 'record-interpreter.py', check: true)
custom_target('known', input: 'known.pyx.tp', output: 'known.pyx',
 command: [tempita, '@INPUT@', '-o', '@OUTDIR@'], build_by_default: true)
"""
 (source/"meson.build").write_text(meson_text,encoding="utf-8",newline="\n")
 (source/"known.pyx.tp").write_text("# templated value {{ 6 * 7 }}\n",encoding="utf-8",newline="\n")
 (source/"record-interpreter.py").write_text("import sys,json,Cython;from pathlib import Path;Path("+repr(str(d/"actual-python.json"))+").write_text(json.dumps({'executable':sys.executable,'cython_version':Cython.__version__,'cython_source':Cython.__file__}))",encoding="utf-8")
 native=d/"native.ini";python=str(d/"missing-python.exe") if invalid else sys.executable
 native.write_text("[binaries]\npython = '"+Path(python).as_posix()+"'\n",encoding="utf-8",newline="\n")
 cmd=[sys.executable,"-B","-c",launcher,"setup",str(build),str(source),"--native-file",str(native)]
 t=time.monotonic();r=subprocess.run(cmd,env=env,capture_output=True,timeout=40)
 (d/"setup.stdout.log").write_bytes(r.stdout);(d/"setup.stderr.log").write_bytes(r.stderr)
 row={"case":label,"setup_command":cmd,"setup_exit_code":r.returncode,"setup_stdout_sha256":hashlib.sha256(r.stdout).hexdigest(),"setup_stderr_sha256":hashlib.sha256(r.stderr).hexdigest(),"elapsed_seconds":round(time.monotonic()-t,3)}
 print("SETUP",label,r.returncode,r.stdout.decode(errors="replace")[-1800:],r.stderr.decode(errors="replace")[-1000:],flush=True)
 if invalid:
  assert r.returncode!=0 and not (d/"actual-python.json").exists()
  row["expected_missing_selected_interpreter_rejected"]=True
 else:
  assert r.returncode==0
  actual=json.loads((d/"actual-python.json").read_bytes())
  assert Path(actual["executable"]).resolve()==Path(sys.executable).resolve() and actual["cython_version"]=="3.2.5"
  assert str(cython) in actual["cython_source"]
  assert "Project version: 1.9.1" in r.stdout.decode()
  cmd=[sys.executable,"-B","-c",launcher,"compile","-C",str(build),"-v"]
  c=subprocess.run(cmd,env=env,capture_output=True,timeout=40)
  (d/"compile.stdout.log").write_bytes(c.stdout);(d/"compile.stderr.log").write_bytes(c.stderr)
  print("COMPILE",label,c.returncode,c.stdout.decode(errors="replace")[-1800:],c.stderr.decode(errors="replace")[-1000:],flush=True)
  assert c.returncode==0 and (build/"known.pyx").read_text(encoding="utf-8")=="# templated value 42\n"
  row.update(actual_interpreter=actual,compile_command=cmd,compile_exit_code=c.returncode,output_sha256=hashlib.sha256((build/"known.pyx").read_bytes()).hexdigest())
 results.append(row)
value={"schema_version":1,"status":"passed","scope":"actual Meson/Python/Tempita host command semantics only; no target compiler, native ABI or sklearn package build","meson_wheel_sha256":pins["meson"]["artifact"]["sha256"],"cython_wheel_sha256":pins["cython"]["artifact"]["sha256"],"cases":results}
(out/"RESULT.json").write_text(json.dumps(value,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="\n")
print("PASSED",len(results))
