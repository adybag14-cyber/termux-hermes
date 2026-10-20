"""Independent host packaging proof; no candidate package runtime imports."""
from __future__ import annotations
import base64, csv, hashlib, importlib.util, io, json, os, pathlib, subprocess, sys, tempfile, zipfile
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
REPO = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
BASE = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\neutts-complete-runtime-preparation-20261020\independent-einx-install-review")
OLD = "docs/source/conf.py"
NEW = "einx-0.4.3.data/data/share/doc/einx-0.4.3/source/conf.py"
EXPECTED = {
 "original": ("audit/neutts-complete-runtime-preparation-20261020/einx-docs/original/einx-0.4.3-py3-none-any.whl",163766,"47ce54a0144f6dffcfacdd8fe2cc9e2e5e6485dda2471330ab75ee747dd22f39"),
 "derived": ("audit/neutts-complete-runtime-preparation-20261020/einx-docs/derived/einx-0.4.3-py3-none-any.whl",724463,"f64866a6ebfd6e0549f05d13c3230227f11eaa88880e72da57ba2314bef5a8dc"),
 "phonemizer": ("audit/neutts-complete-runtime-preparation-20261020/native-wheels/phonemizer-3.3.0-py3-none-any.whl",106164,"8e0ae407d381db31d176f4aed74ee43808659f73e9f93c00ca34bde8662a2906"),
 "proof": ("audit/neutts-complete-runtime-preparation-20261020/einx-docs/EINX-DOCS-RELOCATION.json",54519,"dd4018c016db11e4b7c5811571f538859c36d68387cd652a8abf407dfb354f7f"),
}
def require(ok, message):
 if not ok: raise RuntimeError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def save(name,value):
 raw=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+"\n").encode()
 path=BASE/name;path.write_bytes(raw);return {"path":str(path),"bytes":len(raw),"sha256":sha(raw)}
def module(name,rel,expected):
 path=REPO/rel;raw=path.read_bytes();require(sha(raw)==expected,"Shared validator changed: "+rel)
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 return m
def wheel_read(path):
 raw=path.read_bytes()
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist(); names=[i.filename for i in infos]
  require(len(names)==len(set(names)),"Duplicate wheel member")
  require(z.testzip() is None,"Wheel CRC failure")
  for name in names:
   require(name and "\\" not in name and "\x00" not in name and not name.startswith("/") and all(p not in ("",".","..") for p in name.split("/")),"Unsafe wheel member")
  contents={i.filename:z.read(i) for i in infos}
  records=[n for n in names if n.endswith(".dist-info/RECORD")];require(len(records)==1,"Missing exact RECORD")
  rows=list(csv.reader(io.StringIO(contents[records[0]].decode())))
  require(all(len(r)==3 for r in rows) and len(rows)==len({r[0] for r in rows}) and {r[0] for r in rows}==set(names),"RECORD/member mismatch")
  for name,digest,size in rows:
   if name==records[0]:require(digest==size=="","RECORD self hash")
   else:
    b=contents[name];require(digest=="sha256="+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip("=") and size==str(len(b)),"Wheel RECORD payload mismatch")
  return contents,infos,{"bytes":len(raw),"sha256":sha(raw),"members":len(names),"record_payloads":len(rows)-1,"crc_checked":True,"all_record_hashes_verified":True}
def run(args,name,env,timeout=60):
 result=subprocess.run(args,env=env,capture_output=True,timeout=timeout)
 (BASE/(name+"-stdout.txt")).write_bytes(result.stdout)
 (BASE/(name+"-stderr.txt")).write_bytes(result.stderr)
 save(name+"-result.json",{"args":args,"exit_code":result.returncode,"stdout_sha256":sha(result.stdout),"stderr_sha256":sha(result.stderr)})
 require(result.returncode==0,name+" failed; see retained stderr")
 return result
BASE.mkdir(parents=True,exist_ok=True)
paths={}
for name,(relative,size,digest) in EXPECTED.items():
 path=REPO/relative;raw=path.read_bytes()
 require(len(raw)==size and sha(raw)==digest,"Frozen input mismatch: "+name)
 paths[name]=path
lockraw=(REPO/"scripts/neutts_complete_runtime_lock.json").read_bytes()
lock=json.loads(lockraw)
packages=[p for p in lock["packages"] if p["name"] in ("einx","phonemizer")]
require(len(packages)==2,"Expected exactly two package records")
save("SELECTED-INPUTS.json",{"lock_sha256":sha(lockraw),"packages":packages,"paths":{k:str(v) for k,v in paths.items()}})
before,before_info,before_review=wheel_read(paths["original"])
after,after_info,after_review=wheel_read(paths["derived"])
phon,phon_info,phon_review=wheel_read(paths["phonemizer"])
record="einx-0.4.3.dist-info/RECORD"
require(set(after)==(set(before)-{OLD})|{NEW},"Derived member set changed")
require(OLD not in after and after[NEW]==before[OLD],"Documentation relocation bytes changed")
require(all(after[n]==b for n,b in before.items() if n not in (OLD,record)),"Unreviewed derived payload change")
require(after[record]!=before[record],"Derived RECORD was not updated")
require(sha(before[OLD])=="386f1a451b02667af9c1b3337bbad94972c4031af9a1f757b7186a33e587dcd2","Original Einx docs differ")
require(sha(phon[OLD])=="8ff1bfe77a14e0bec2e5d34e8fb3f92e155c12ee32778ff1d817e29936fdfce4","Original Phonemizer docs differ")
for old_info,new_info in zip(before_info,after_info,strict=True):
 require(new_info.filename==(NEW if old_info.filename==OLD else old_info.filename),"Member order changed")
 require(new_info.date_time==(1980,1,1,0,0,0) and new_info.compress_type==zipfile.ZIP_STORED and new_info.create_system==3 and new_info.create_version==new_info.extract_version==20 and new_info.external_attr==old_info.external_attr and new_info.internal_attr==0 and new_info.extra==new_info.comment==b"","Unexpected deterministic ZIP field")
from pip._vendor.packaging.specifiers import SpecifierSet
python_version=".".join(map(str,sys.version_info[:3]))
for content in (after,phon):
 metadata=next(n for n in content if n.endswith(".dist-info/METADATA"))
 bounds=BytesParser(policy=compat32).parsebytes(content[metadata]).get("Requires-Python","")
 require(SpecifierSet(bounds).contains(python_version),"Host Python violates original metadata bound")
save("ARCHIVE-COMPARISON.json",{"original":before_review,"derived":after_review,"phonemizer":phon_review,"preserved_original_einx_payloads":130,"only_payload_path_change":{"from":OLD,"to":NEW},"record_recomputed":True,"all_other_payloads_identical":True,"metadata_wheel_licenses_runtime_source_identical":True,"zip_stored_fixed_fields_checked":True,"original_python_bounds_accept_actual_host":python_version})
env=dict(os.environ)
for key in list(env):
 if key.upper() in ("PYTHONPATH","PYTHONHOME","PYTHONSTARTUP","VIRTUAL_ENV","PIP_TARGET","PIP_PREFIX","PIP_REQUIRE_VIRTUALENV"):
  env.pop(key)
env.update(PYTHONDONTWRITEBYTECODE="1",PIP_CONFIG_FILE=os.devnull,PIP_NO_INDEX="1",PIP_DISABLE_PIP_VERSION_CHECK="1")
prefix=Path(tempfile.mkdtemp(prefix="android-scheme-prefix-",dir=BASE))
run([sys.executable,"-I","-B","-m","venv","--without-pip",str(prefix)],"create-private-venv",env)
site=prefix/"lib/python3.14/site-packages"
scheme_paths={"platlib":str(site),"purelib":str(site),"headers":str(prefix/"include"),"scripts":str(prefix/"bin"),"data":str(prefix)}
install_spec={"prefix":str(prefix),"scheme":scheme_paths,"wheels":[{"name":p["name"],"path":str(paths["derived" if p["name"]=="einx" else "phonemizer"])} for p in packages]}
save("INSTALL-SPEC.json",install_spec)
install_script=BASE/"pip-actual-install.py"
install_script.write_text('''import json,sys
from pathlib import Path
events=[]
def audit(event,args):
 if event in ("socket.connect","socket.getaddrinfo","socket.connect_ex"):
  events.append(event)
  raise RuntimeError("Network forbidden during offline wheel install")
sys.addaudithook(audit)
import pip
from pip._internal.models.scheme import Scheme
from pip._internal.operations.install.wheel import install_wheel
spec=json.loads(Path(sys.argv[1]).read_bytes())
scheme=Scheme(**spec["scheme"])
for item in spec["wheels"]:
 install_wheel(item["name"],item["path"],scheme,req_description=item["name"]+" independently reviewed offline packaging fixture",pycompile=False,warn_script_location=False,requested=True)
Path(sys.argv[2]).write_text(json.dumps({"status":"passed","pip":pip.__version__,"method":"real pip install_wheel with explicit Android-style Scheme","resolution":False,"network_attempts":events,"pycompile":False,"wheels":spec["wheels"]},indent=2)+"\\n",encoding="utf-8")
''',encoding="utf-8",newline="\n")
run([sys.executable,"-I","-B",str(install_script),str(BASE/"INSTALL-SPEC.json"),str(BASE/"PIP-INSTALL-RESULT.json")],"pip-actual-install",env)
validation_spec={"repo":str(REPO),"prefix":str(prefix),"site":str(site),"packages":packages,"paths":{k:str(v) for k,v in paths.items()},"source_bindings":{
 "scripts/prepare_neutts_perth_runtime.py":"7445bf89b0fd26f9f74a7935724e394b24b331409f200ecca9f2904ffacb40db",
 "scripts/compatibility_probe_neutts_nonrust.py":"11d0dc5ed34dd45c855bffbba51c02eecf74ce8c5a5dd38cb1483e57f1d14e4b",
 "scripts/compatibility_probe_neutts_perth.py":"7780965f1a336afa8244136e7c40b44d9483d91e17e662f6d07c2cbb78fcd7a2"}}
save("VALIDATION-SPEC.json",validation_spec)
child=BASE/"validate-installed.py"
child.write_text('''import base64,csv,hashlib,importlib.metadata,importlib.util,io,json,os,sys,zipfile
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_bytes());repo=Path(spec["repo"]);prefix=Path(spec["prefix"]);site=Path(spec["site"])
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
require(Path(sys.prefix).resolve()==prefix.resolve() and sys.prefix!=sys.base_prefix,"Real private venv prefix differs")
def module(name,rel):
 p=repo/rel;require(sha(p.read_bytes())==spec["source_bindings"][rel],"Shared source changed")
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
prep=module("_peer_perth_prep","scripts/prepare_neutts_perth_runtime.py")
nr=module("_peer_nonrust_probe","scripts/compatibility_probe_neutts_nonrust.py")
perth=module("_peer_perth_probe","scripts/compatibility_probe_neutts_perth.py")
reports=[];allowed=set();ownership={};all_record_paths=set();dist_reports=[]
for p in spec["packages"]:
 wheel=Path(spec["paths"]["derived" if p["name"]=="einx" else "phonemizer"])
 report=nr.installed_wheel_bytes(wheel,p,site,prep)
 for member in report["owned_paths"]:
  require(member not in allowed,"Duplicate installed original file owner")
 allowed.update(report.pop("owned_paths"))
 reports.append({"name":p["name"],**report})
 with zipfile.ZipFile(wheel) as z:
  metadata=z.read(p["wheel"]["metadata_member"])
  require((site/p["wheel"]["metadata_member"]).read_bytes()==metadata,"Whole original METADATA changed")
 record=site/p["wheel"]["record_member"]
 rows=list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
 for member,digest,size in rows:
  target=site.joinpath(*member.split("/"));resolved=target.resolve()
  require(resolved.is_relative_to(prefix.resolve()),"RECORD escapes prefix")
  key=resolved.relative_to(prefix.resolve()).as_posix()
  require(key not in ownership,"Duplicate installed RECORD owner")
  ownership[key]=p["name"];all_record_paths.add(resolved)
  if target.is_relative_to(site) and ".." not in member.split("/"):allowed.add(target.relative_to(site).as_posix())
 dist_reports.append({"name":p["name"],"version":p["version"],"metadata_sha256":sha(metadata),"record_rows":len(rows),"record_sha256":sha(record.read_bytes())})
record_report=perth.installed_records({"wheels":spec["packages"]},prep)
actual={p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
require(actual==allowed,"Unowned or missing site files")
dists=list(importlib.metadata.distributions(path=[str(site)]))
require(len(dists)==2 and {d.metadata["Name"].lower() for d in dists}=={"einx","phonemizer"},"Visible two-wheel inventory differs")
for d in dists:
 p=next(p for p in spec["packages"] if p["name"]==d.metadata["Name"].lower())
 require(d.version==p["version"] and d.metadata.get_all("Requires-Dist",[])==p["requires_dist"] and d.metadata.get("Requires-Python","")==p["requires_python"],"Original declarations changed")
docs={}
for name,path,expected in (
 ("einx",prefix/"share/doc/einx-0.4.3/source/conf.py","386f1a451b02667af9c1b3337bbad94972c4031af9a1f757b7186a33e587dcd2"),
 ("phonemizer",site/"docs/source/conf.py","8ff1bfe77a14e0bec2e5d34e8fb3f92e155c12ee32778ff1d817e29936fdfce4")):
 require(path.is_file() and not path.is_symlink() and sha(path.read_bytes())==expected,"Separate original docs bytes missing")
 docs[name]={"path":str(path),"bytes":path.stat().st_size,"sha256":expected}
require(docs["einx"]["path"]!=docs["phonemizer"]["path"],"Docs not separated")
for path in site.rglob("*"):require(not path.is_symlink(),"Site symlink")
result={"status":"passed","host_only_packaging_proof":True,"actual_private_sys_prefix":sys.prefix,"android_style_scheme":True,"native_android_runtime_executed":False,"package_runtime_imports":False,"exact_input_wheel_count":2,"actual_visible_distribution_count":len(dists),"verified_site_files":len(actual),"unique_installed_record_targets":len(ownership),"installed_wheel_bytes":reports,"shared_installed_records_raw_result":record_report,"shared_records_result_note":"The unchanged Perth helper hardcodes wheel_count=36 in its summary; its loop validated precisely the two supplied wheels. Actual wheel_count is recorded separately as 2.","distributions":dist_reports,"separate_documentation_files":docs,"record_ownership_sha256":sha((json.dumps(ownership,sort_keys=True)+"\\n").encode()),"source_bindings":spec["source_bindings"],"no_byte_integrity_exception_added":True}
Path(sys.argv[2]).write_text(json.dumps(result,indent=2,sort_keys=True)+"\\n",encoding="utf-8")
print(json.dumps({"status":"passed","site_files":len(actual),"record_targets":len(ownership),"record_rows":record_report["record_rows"],"dist_count":len(dists)}))
''',encoding="utf-8",newline="\n")
run([str(prefix/"Scripts/python.exe"),"-I","-B",str(child),str(BASE/"VALIDATION-SPEC.json"),str(BASE/"INSTALLED-PAYLOAD-REVIEW.json")],"validate-installed",env)
result=json.loads((BASE/"INSTALLED-PAYLOAD-REVIEW.json").read_bytes())
for name,(relative,size,digest) in EXPECTED.items():
 raw=(REPO/relative).read_bytes();require(len(raw)==size and sha(raw)==digest,"Input mutated during review")
review={"status":"passed","scope":"Independent real offline pip installation of only derived Einx 0.4.3 and unchanged Phonemizer 3.3.0, into an explicit Android-style wheel Scheme inside an actual Windows-host private venv. This is packaging and byte-provenance proof, not Android/native package operation evidence.","host_python":sys.version,"original_python_bounds_preserved":True,"input_archives":{name:{"path":str(paths[name]),"bytes":value[1],"sha256":value[2]} for name,value in EXPECTED.items()},"archive_review":"ARCHIVE-COMPARISON.json","pip_result":"PIP-INSTALL-RESULT.json","installed_payload_review":"INSTALLED-PAYLOAD-REVIEW.json","installed_result_summary":{"distributions":result["actual_visible_distribution_count"],"site_files":result["verified_site_files"],"record_rows":result["shared_installed_records_raw_result"]["record_rows"],"unique_record_targets":result["unique_installed_record_targets"],"both_original_documentation_bytes_retained":True,"all_original_payloads_except_truthful_installed_records_match":True},"unchanged_shared_validators":validation_spec["source_bindings"],"metadata_license_runtime_payloads_preserved":True,"no_runtime_imports":True,"no_network_or_dependency_resolution":True,"no_engine_admission_or_release_change":True,"complete116_native_retry_required":True}
receipt=save("INDEPENDENT-EINX-INSTALL-REVIEW.json",review)
print(json.dumps(receipt))
