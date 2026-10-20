"""Independent retained-byte review of the successful native Tiktoken artifact."""
import base64,csv,email.parser,gzip,hashlib,importlib.util,io,json,pathlib,stat,subprocess,sys,tarfile,tempfile,zipfile
sys.stdout.reconfigure(encoding="utf-8")
ROOT=pathlib.Path(sys.argv[1]);BASE=pathlib.Path(sys.argv[2])
DEST=ROOT/"audit/neutts-tiktoken-native-20261020/run-39446824110"
HEAD="73525752755f990926243396f34f5ba8e6148a03"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,value):
 raw=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+"\n").encode()
 path=DEST/name;path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():assert path.read_bytes()==raw,name
 else:path.write_bytes(raw)
 return {"path":name,"bytes":len(raw),"sha256":sha(raw)}
proof=json.loads((DEST/"FULL-DOWNLOAD-VERIFIED.json").read_bytes())
assert proof["sha256"]=="83b2ae7c5058a7fee3d3637a8f6bef535096512d84abce1de5cb46db79e22ca7"
rows={r["path"]:r for r in json.loads(gzip.decompress((DEST/"FULL-MEMBER-INVENTORY.json.gz").read_bytes()))}
archive=zipfile.ZipFile(BASE/"artifact.zip")
def member(name,limit=128*1024*1024):
 row=rows[name];assert row["bytes"]<=limit
 raw=archive.read(name);assert len(raw)==row["bytes"] and sha(raw)==row["sha256"]
 return raw
def obj(name):return json.loads(member(name))
def git(path):return subprocess.check_output(["git","-C",str(ROOT),"show",HEAD+":"+path])
prefix="tiktoken-component/"
component=obj(prefix+"TIKTOKEN-COMPONENT-RESULT.json")
runtime=obj(prefix+"runtime-operations/TIKTOKEN-RUNTIME-RESULT.json")
lock=obj("tiktoken-inputs/neutts_tiktoken_lock.json")
manifest=obj(prefix+"tiktoken-runtime-installed-closure.json")
assert component["status"]=="passed" and component["stage"]=="complete" and component["original_inputs_unchanged"] is True
assert all(component[k] is False for k in ("engine_installed","model_downloaded","complete_engine_admitted","release_output"))
assert component["runtime_receipt_sha256"]==rows[prefix+"runtime-operations/TIKTOKEN-RUNTIME-RESULT.json"]["sha256"]
assert runtime["status"]=="passed" and runtime["complete_distribution_count"]==7
assert all(runtime[k] is False for k in ("engine_installed","model_downloaded","complete_engine_admitted"))
assert runtime["network_connect_and_dns_forbidden"] is True
assert runtime["before"]==runtime["after"] and runtime["before"]["actual_visible_distribution_count"]==7
assert runtime["before"]["global_site_visible"] is False and runtime["before"]["declared_metadata_modified"] is False
assert manifest["names"]==sorted(lock["runtime_names"])==runtime["before"]["actual_names"]
assert len(manifest["wheels"])==7 and len({p["name"] for p in manifest["wheels"]})==7
assert component["runtime_closure"]["active_edge_count"]==6 and component["runtime_closure"]["distribution_count"]==7
assert component["runtime_closure"]["selected_extras"]==[] and component["runtime_closure"]["original_metadata_modified"] is False
assert component["lock_sha256"]==sha(member("tiktoken-inputs/neutts_tiktoken_lock.json"))
assert component["input_checks"]=={"apt_archives":47,"build_wheels":5,"generated_directory_checksums":27,"original_registry_archives":27,"original_registry_files":1863,"original_source_files":58,"runtime_prebuilt_wheels":5}
operations=runtime["operations"]
expected=[("",[]),("ab ab",[256,32,256]),("cab",[99,256]),("abab",[256,256]),("\u00e9\U0001f642",[195,169,240,159,153,130]),("ab\nab",[256,10,256])]
assert [(x["text"],x["expected_tokens"]) for x in operations["fixed_examples"]]==expected
assert all(x["actual_tokens"]==x["expected_tokens"] for x in operations["fixed_examples"])
assert operations["native_core_type"]=="CoreBPE" and operations["vocabulary_entries"]==258 and operations["batch_threads"]==2
assert operations["network_vocabulary_downloaded"] is False and operations["default_special_token_rejected"] is True
assert all(operations[k]=="passed" for k in ("status","binary_single_token_apis","allowed_special_token","regex_unicode_graphemes","local_dependency_operations"))
assert operations["request_url"]=="https://xn--bcher-kva.example/ab?q=a+b"
# Match all original frozen crate archives, generated checksum bodies and unpacked files.
crate_files=0
for pin in lock["registry"]:
 raw=member("tiktoken-inputs/crates/"+pin["filename"])
 assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
 root="tiktoken-inputs/vendor/"+pin["name"]+"-"+pin["version"]+"/"
 checksum=member(root+".cargo-checksum.json")
 assert sha(checksum)==pin["checksum_sha256"]
 values=json.loads(checksum);assert values["package"]==pin["sha256"] and len(values["files"])==pin["files"]
 actual={name[len(root):] for name in rows if name.startswith(root) and name!=root+".cargo-checksum.json"}
 assert actual==set(values["files"])
 for path,digest in values["files"].items():assert rows[root+path]["sha256"]==digest
 crate_files+=len(actual)
assert crate_files==1863 and len(lock["registry"])==27
cargo=obj(prefix+"TIKTOKEN-CARGO-GRAPH.json")
assert cargo["status"]=="passed" and cargo["target_packages"]==25 and cargo["target_registry_packages"]==24 and cargo["target_edges"]==41
def canonical_graph(values):
 return sorted(({**p,"features":sorted(p["features"]),"dependency_ids":sorted(({**d,"dep_kinds":sorted(d["dep_kinds"],key=lambda k:json.dumps(k,sort_keys=True))} for d in p["dependency_ids"]),key=lambda d:(d["name"],d["pkg"]))} for p in values),key=lambda p:(p["name"],p["version"]))
assert canonical_graph(cargo["packages"])==canonical_graph(lock["target_filtered_packages"])
assert "--locked" in cargo["command"]["command"] and "--offline" in cargo["command"]["command"]
assert cargo["command"]["exit_code"]==0 and cargo["command"]["stdout_sha256"]==rows[prefix+"tiktoken-locked-cargo-metadata.stdout.log"]["sha256"]
cargo_lock=member("tiktoken-inputs/sources/tiktoken-0.14.0/Cargo.lock")
assert len(cargo_lock)==6462 and sha(cargo_lock)==lock["captured_cargo_lock"]["sha256"]==component["approved_cargo_lock_sha256"]
# The static reader itself is hash bound to the same executed Git commit.
elf_raw=git("scripts/neutts_runtime_elf.py")
assert sha(elf_raw)=="73d00842dfe5c6f46712d6171007c3cb2735ca68ba678515c15ace01af500b11"
elf_namespace={"__name__":"_native_audit_elf"};exec(compile(elf_raw,"neutts_runtime_elf.py","exec"),elf_namespace)
elf=elf_namespace["elf"]
wheel_reviews=[];all_native=[]
tmp=BASE/"independent-native-readback";tmp.mkdir(exist_ok=True)
for name,source in (("tiktoken",lock["source"]),("regex",lock["regex_source"])):
 report=obj(prefix+"components/"+name+"/TIKTOKEN-SOURCE-WHEEL-RESULT.json")
 backend=obj(prefix+"components/"+name+"/SOURCE-BACKEND-RESULT.json")
 facts=report["wheel"]
 assert report["status"]=="wheel-built-and-verified" and report["build"]["exit_code"]==0 and backend["status"]=="passed"
 assert all(backend[k] is False for k in ("original_backend_modified","new_cargo_resolution","platform_override_used"))
 assert backend["cargo_offline"] is True and backend["config_settings"]=={}
 assert backend["build_system_declarations"]["original_source_metadata_modified"] is False
 assert backend["source_after"]==report["source_after"]
 assert backend["source_after"]["original_source_code_backend_and_dependency_metadata_unchanged"] is True
 changed=backend["source_after"]["allowed_generated_source_manifests"]
 assert len(changed)==1
 allowed=lock["allowed_generated_source_manifests"][name]
 assert changed[0]["path"]==allowed["path"] and changed[0]["after_sha256"]==allowed["sha256"] and changed[0]["before_sha256"]==allowed["original_sha256"]
 assert backend["original_archive_sha256"]==source["artifact"]["sha256"]
 src=member("tiktoken-inputs/archives/"+source["artifact"]["filename"])
 assert sha(src)==source["artifact"]["sha256"] and len(src)==source["artifact"]["bytes"]
 with tarfile.open(fileobj=io.BytesIO(src),mode="r:*") as tf:
  source_rows={}
  for item in tf:
   if not item.isfile():continue
   assert item.size<8*1024*1024
   raw=tf.extractfile(item).read();assert len(raw)==item.size
   relative=item.name.removeprefix(source["archive_root"]+"/")
   assert relative not in source_rows;source_rows[relative]=raw
 assert backend["source_after"]["original_files_byte_identical"]==len(source_rows)-1
 filename=facts["artifact"]["filename"];wheel_name=prefix+"wheels/"+name+"/"+filename
 data=member(wheel_name,16*1024*1024)
 assert sha(data)==facts["artifact"]["sha256"] and len(data)==facts["artifact"]["bytes"]
 with zipfile.ZipFile(io.BytesIO(data)) as wh:
  infos=wh.infolist();assert len(infos)==len({i.filename for i in infos}) and 1<=len(infos)<=128
  assert sum(i.file_size for i in infos)<=16*1024*1024
  bodies={}
  for item in infos:
   path=pathlib.PurePosixPath(item.filename)
   assert path.as_posix()==item.filename and item.orig_filename==item.filename and not path.is_absolute()
   assert ".." not in path.parts and "\\" not in item.filename and ":" not in item.filename
   assert stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG)
   assert not item.flag_bits&1 and item.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) and item.file_size<=8*1024*1024
   raw=wh.read(item);assert len(raw)==item.file_size
   bodies[item.filename]=raw
  wheel=facts["wheel"];record_name=wheel["record_member"]
  records=list(csv.reader(io.StringIO(bodies[record_name].decode())))
  assert all(len(r)==3 for r in records) and len(records)==len({r[0] for r in records})==len(bodies)
  assert {r[0] for r in records}==set(bodies)
  for path,digest,size in records:
   if path==record_name:assert digest==size==""
   else:
    raw=bodies[path];expected_hash=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    assert digest=="sha256="+expected_hash and size==str(len(raw))
  assert sha(bodies[record_name])==wheel["record_sha256"] and sha(bodies[wheel["metadata_member"]])==wheel["metadata_sha256"]
  assert bodies[wheel["metadata_member"]]==source_rows["PKG-INFO"],"Native wheel changed original PKG-INFO bytes"
  metadata=email.parser.BytesParser().parsebytes(bodies[wheel["metadata_member"]])
  assert metadata["Name"].lower()==name and metadata["Version"]==source["version"] and metadata["Requires-Python"]==source["requires_python"]
  assert metadata.get_all("Requires-Dist",[])==source["requires_dist"]
  wheel_metadata=email.parser.BytesParser().parsebytes(bodies[wheel["wheel_member"]])
  assert wheel_metadata["Root-Is-Purelib"]=="false" and wheel_metadata.get_all("Tag")==["cp314-cp314-android_24_arm64_v8a"]
  python_files=0;licenses=[]
  for path,raw in bodies.items():
   if path.endswith(".py"):
    matches=[v for k,v in source_rows.items() if k==path or k.endswith("/"+path)]
    assert len(matches)==1 and raw==matches[0],path;python_files+=1
   if "/licenses/" in path or pathlib.PurePosixPath(path).name.lower().startswith(("license","copying")):
    matches=[k for k,v in source_rows.items() if v==raw]
    assert matches;licenses.append({"member":path,"bytes":len(raw),"sha256":sha(raw),"original_source_members":matches})
  assert licenses
  native=[]
  for n in facts["native_members"]:
   raw=bodies[n["member"]];assert len(raw)==n["bytes"] and sha(raw)==n["sha256"]
   target=tmp/(name+"-"+pathlib.PurePosixPath(n["member"]).name);target.write_bytes(raw)
   detail=elf(target,dynamic=True);detail["member"]=n["member"];detail.pop("path")
   assert "libpython3.14.so" in detail["needed"]
   native.append(detail);all_native.append(detail)
  assert len(native)==1
  observed=report["native_elf"][0]
  assert all(native[0][k]==observed[k] for k in ("bytes","class","endianness","machine","needed","runpath","sha256"))
  wheel_reviews.append({"name":name,"artifact_member":wheel_name,"artifact":facts["artifact"],"member_count":len(bodies),
   "all_crc_record_hashes_verified":True,"metadata_byte_identical_to_original_pkg_info":True,
   "metadata_sha256":sha(bodies[wheel["metadata_member"]]),"original_python_files_verified":python_files,
   "licenses":licenses,"native_elf":native,"requires_python":source["requires_python"],"requires_dist":source["requires_dist"],
   "allowed_generated_source_manifest":changed[0],"original_files_byte_identical":backend["source_after"]["original_files_byte_identical"]})
# Bind all four actually mapped extensions to the full original seven-wheel install manifest.
mapped=runtime["mapped_extensions"];assert len(mapped)==4 and len({r["path"] for r in mapped})==4
selected={n["sha256"]:(p["name"],n) for p in manifest["wheels"] for n in p["native_members"]}
assert len(selected)==4 and {r["sha256"] for r in mapped}==set(selected)
for row in mapped:
 name,pin=selected[row["sha256"]]
 assert row["path"].endswith("/site-packages/"+pin["member"]) and row["bytes"]==pin["bytes"]
 assert row["machine"]==183 and row["class"]==64 and "libpython3.14.so" in row["needed"]
# Every archive and snapshot still equals the frozen source lock.
rust_raw=git(lock["references"]["rust_lock"]["path"]);assert sha(rust_raw)==lock["references"]["rust_lock"]["sha256"]
rust=json.loads(rust_raw);apt={p["name"]:p for p in rust["build_apt"]["packages"]}
assert len(apt)==47 and len(component["archives"])==47
for pin in component["archives"]:
 expected=apt[pin["name"]];path=pin["path"].removeprefix("/out/")
 assert pin["sha256"]==expected["sha256"]==rows[path]["sha256"] and pin["bytes"]==expected["bytes"]==rows[path]["bytes"]
 assert pin["version"]==expected["version"]
for pin in rust["build_apt"]["snapshot"]:
 raw=member("tiktoken-inputs/snapshot/"+pin["filename"])
 assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
assert component["signed_index"]["status"]=="passed" and component["signed_index"]["insecure_repository_exceptions"] is False
assert component["signed_index"]["matched_archives"]==47 and component["compiler_install"]["status"]=="passed"
for kind in ("plan","install"):
 command=component["compiler_install"][kind]["command"]
 assert "--no-download" in command and "--no-remove" in command and "APT::Get::AllowUnauthenticated=false" in command
provenance=runtime["apt_provenance"]
assert provenance["status"]=="passed" and len(provenance["mapped_apt_libraries"])==39
assert any(r["package"]=="python" and pathlib.PurePosixPath(r["path"]).name=="libpython3.14.so" for r in provenance["mapped_apt_libraries"])
# Review the actual original DEB data members for all mapped APT owners.
def ar_members(raw):
 assert raw.startswith(b"!<arch>\n") and len(raw)<=128*1024*1024
 offset=8;result={}
 while offset<len(raw):
  header=raw[offset:offset+60];assert len(header)==60 and header[58:]==b"`\n"
  name=header[:16].decode("ascii").strip().rstrip("/");length=int(header[48:58])
  offset+=60;assert 0<=length<=len(raw)-offset and name not in result
  result[name]=raw[offset:offset+length];offset+=length+(length%2)
 assert offset==len(raw)
 return result
owner_reviews=[]
for owner in sorted({r["package"] for r in provenance["mapped_apt_libraries"]}):
 pin=apt[owner];record=next(p for p in component["archives"] if p["name"]==owner)
 raw=member(record["path"].removeprefix("/out/"))
 pieces=ar_members(raw);assert pieces["debian-binary"]==b"2.0\n"
 controls=[v for k,v in pieces.items() if k.startswith("control.tar.")]
 datasets=[v for k,v in pieces.items() if k.startswith("data.tar.")]
 assert len(controls)==len(datasets)==1
 with tarfile.open(fileobj=io.BytesIO(controls[0]),mode="r:*") as tf:
  control=[m for m in tf if m.name.lstrip("./")=="control"];assert len(control)==1 and control[0].isfile()
  fields=email.parser.BytesParser().parsebytes(tf.extractfile(control[0]).read())
  assert fields["Package"]==owner and fields["Version"]==pin["version"] and fields["Architecture"]==pin["architecture"]
 needed={r["path"].lstrip("/"):r for r in provenance["mapped_apt_libraries"] if r["package"]==owner};verified=[]
 with tarfile.open(fileobj=io.BytesIO(datasets[0]),mode="r:*") as tf:
  seen=set();total=0
  for item in tf:
   total+=item.size;assert total<=512*1024*1024
   name=item.name[2:] if item.name.startswith("./") else item.name
   assert name not in seen;seen.add(name)
   if name not in needed:continue
   assert item.isfile() and item.size==needed[name]["bytes"]<=16*1024*1024
   raw=tf.extractfile(item).read();assert sha(raw)==needed[name]["sha256"]
   verified.append(name)
 assert set(verified)==set(needed)
 owner_reviews.append({"package":owner,"version":pin["version"],"architecture":pin["architecture"],
  "archive_sha256":pin["sha256"],"mapped_original_files_verified":len(verified)})
review={"schema":"tiktoken-native-independent-review/v1","status":"passed","head_sha":HEAD,
 "run_id":39446824110,"job_id":118710822103,"artifact_id":12276642938,
 "whole_artifact_sha256":proof["sha256"],"whole_artifact_bytes":proof["bytes"],"all_zip_members_verified":proof["member_count"],
 "recorded_source_bindings":"EXECUTED-SOURCE-BINDINGS.json","source_input_count":80,
 "native_runtime":component["native_runtime"],"foundation_cases":7,
 "complete_runtime_distributions":7,"active_dependency_edges":6,"selected_extras":[],
 "original_runtime_metadata_modified":False,"runtime_inventory_before_after_identical":True,
 "original_registry_archives":27,"original_registry_files":crate_files,"target_cargo_packages":25,"target_cargo_edges":41,
 "approved_cargo_lock_sha256":sha(cargo_lock),"native_wheels":wheel_reviews,"operations":operations,
 "actually_mapped_native_extensions":4,"mapped_apt_libraries":39,"mapped_original_apt_owners":owner_reviews,
 "original_metadata_byte_identity":True,"only_measured_source_manifest_regeneration_allowed":True,
 "network_vocabulary_downloaded":False,"speech_model_downloaded":False,"engine_installed":False,
 "complete_engine_admitted":False,"production_admission_changed":False,"release_output":False}
saved=save("NATIVE-REVIEW.json",review)
save("REVIEW-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"passed","review":saved,"wheels":[w["artifact"] for w in wheel_reviews],
 "apt_owner_count":len(owner_reviews),"mapped_apt_files_verified":sum(p["mapped_original_files_verified"] for p in owner_reviews)},ensure_ascii=True))
