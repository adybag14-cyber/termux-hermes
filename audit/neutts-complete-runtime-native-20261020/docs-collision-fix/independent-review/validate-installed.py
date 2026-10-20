import base64,csv,hashlib,importlib.metadata,importlib.util,io,json,os,sys,zipfile
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
result={"status":"passed","host_only_packaging_proof":True,"actual_private_sys_prefix":sys.prefix,"android_style_scheme":True,"native_android_runtime_executed":False,"package_runtime_imports":False,"exact_input_wheel_count":2,"actual_visible_distribution_count":len(dists),"verified_site_files":len(actual),"unique_installed_record_targets":len(ownership),"installed_wheel_bytes":reports,"shared_installed_records_raw_result":record_report,"shared_records_result_note":"The unchanged Perth helper hardcodes wheel_count=36 in its summary; its loop validated precisely the two supplied wheels. Actual wheel_count is recorded separately as 2.","distributions":dist_reports,"separate_documentation_files":docs,"record_ownership_sha256":sha((json.dumps(ownership,sort_keys=True)+"\n").encode()),"source_bindings":spec["source_bindings"],"no_byte_integrity_exception_added":True}
Path(sys.argv[2]).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps({"status":"passed","site_files":len(actual),"record_targets":len(ownership),"record_rows":record_report["record_rows"],"dist_count":len(dists)}))
