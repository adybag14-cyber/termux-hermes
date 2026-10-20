#!/usr/bin/env python3
"""Independently inspect original Tokenizers native evidence; execute no native payload."""
import ast,base64,collections,csv,gzip,hashlib,importlib.util,io,json,pathlib,re,stat,struct,tarfile,tempfile,urllib.parse,zipfile
from email.parser import BytesParser
from email.policy import compat32
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

BASE=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
OUT=BASE/"review-retained"
HEAD="8995678c0e20c117bbab9830b919e49ba0689a5d"
DIGEST="76ce3046d86b476384f8c87f4d43958a7cead6483f5c1c3e52b2ccc5aa740083"
def need(ok,msg):
 if not ok: raise RuntimeError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,raw):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():need(p.read_bytes()==raw,"Existing retained bytes differ: "+name)
 else:p.write_bytes(raw)
 return {"path":name,"bytes":len(raw),"sha256":sha(raw)}
def save_json(name,value):return save(name,(json.dumps(value,indent=2,sort_keys=True)+"\n").encode())
def safe(name):
 p=pathlib.PurePosixPath(name)
 need(not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name,"Unsafe member")
 return p
def req_key(value):
 r=Requirement(value)
 return (canonicalize_name(r.name),str(r.specifier),tuple(sorted(r.extras)),str(r.marker or ""),r.url)
def reqs(values):return sorted(req_key(x) for x in values)
def ar_data(raw):
 need(raw[:8]==b"!<arch>\n","Bad Debian ar signature")
 off=8;parts={}
 while off<len(raw):
  header=raw[off:off+60];need(len(header)==60 and header[58:]==b"\x60\n","Bad ar header")
  name=header[:16].decode("ascii").strip().rstrip("/");length=int(header[48:58])
  need(name not in parts and length>=0,"Bad ar member")
  parts[name]=raw[off+60:off+60+length];need(len(parts[name])==length,"Short ar member")
  off+=60+length+(length%2)
 need(off==len(raw) and parts.get("debian-binary")==b"2.0\n" and len(parts)==3,"Unexpected Debian members")
 data=[v for k,v in parts.items() if k.startswith("data.tar.")]
 need(len(data)==1,"Ambiguous Debian data")
 return data[0]

archive=BASE/"artifact-verified.zip"
with archive.open("rb") as f:actual_archive_sha=hashlib.file_digest(f,"sha256").hexdigest()
need(archive.stat().st_size==197910138 and actual_archive_sha==DIGEST,"Whole artifact identity")
download=json.loads((BASE/"DOWNLOAD-VERIFIED.json").read_bytes())
inventory_raw=gzip.decompress((BASE/"FULL-MEMBER-INVENTORY.json.gz").read_bytes())
inventory=json.loads(inventory_raw)
need(sha(inventory_raw)==download["inventory_sha256"],"Full member inventory identity")
run=json.loads((BASE/"original-run-api.json").read_bytes())
need(run["id"]==39447721557 and run["head_sha"]==HEAD and run["status"]=="completed" and run["conclusion"]=="success","Original successful run identity")
tree=json.loads((BASE/"original-source-tree-api.json").read_bytes())
need(tree["sha"]==HEAD and tree["truncated"] is False,"Complete exact-commit tree")
tree_files={x["path"]:x for x in tree["tree"] if x["type"]=="blob"}
retained=[]
with zipfile.ZipFile(archive) as z:
 entries=z.infolist();need(len(entries)==247 and len({i.filename for i in entries})==247,"Archive member count/duplicates")
 observed=[]
 for i in entries:
  safe(i.filename);need(not stat.S_ISLNK(i.external_attr>>16) and not i.flag_bits&1 and i.file_size<256_000_000,"Unsafe archive member")
  raw=z.read(i)
  observed.append({"path":i.filename,"bytes":len(raw),"sha256":sha(raw),"crc32":i.CRC})
 need(observed==inventory and sum(x["bytes"] for x in observed)==199382279,"Every original outer member CRC/size/SHA")
 def raw(name):return z.read(name)
 def j(name):return json.loads(raw(name))
 inputs=j("TOKENIZERS-PROBE-INPUTS.json");lock=j("tokenizers-inputs/neutts_tokenizers_runtime_lock.json")
 need(inputs["head_sha"]==inputs["workflow_ref_commit"]==HEAD and inputs["run_id"]=="39447721557","Source head/run receipt")
 need(sha(raw("tokenizers-inputs/neutts_tokenizers_runtime_lock.json"))==inputs["inputs"]["scripts/neutts_tokenizers_runtime_lock.json"],"Actual prepared lock")
 bindings=[]
 for name,expected in inputs["inputs"].items():
  safe(name);p=REPO/name;need(p.is_file() and not p.is_symlink(),"Missing original source input: "+name)
  b=p.read_bytes();entry=tree_files[name]
  git_hash=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
  need(sha(b)==expected and git_hash==entry["sha"] and len(b)==entry["size"],"Exact 899 source tree/ledger mismatch: "+name)
  bindings.append({"path":name,"bytes":len(b),"sha256":sha(b),"git_blob_sha1":git_hash})
 save_json("SOURCE-BINDINGS.json",{"head_sha":HEAD,"status":"passed","input_count":len(bindings),"bindings":bindings})
 graph=json.loads((REPO/lock["frozen_graph"]["path"]).read_bytes())
 handoff=json.loads((REPO/lock["handoff"]["path"]).read_bytes())
 need(graph["node_count"]==117 and graph["edge_count"]==194,"Original complete design graph")
 need(handoff["node_count"]==25 and handoff["edge_count"]==29,"Original subset handoff")
 graph_nodes={p["name"]:p for p in graph["nodes"]};handoff_nodes={p["name"]:p for p in handoff["nodes"]}
 packages={p["name"]:p for p in lock["packages"]}
 need(len(packages)==25 and sorted(packages)==lock["names"] and "neutts" not in packages,"Original selected nodes")
 need(lock["roots"]==["fsspec","safetensors","tokenizers"] and {n:p["active_extras"] for n,p in packages.items() if p["active_extras"]}=={"fsspec":["http"]},"Original roots and extra")
 manifest=j("tokenizers-component/tokenizers-installed-closure.json")
 need(manifest["names"]==lock["names"] and manifest["apt_python"]==[] and manifest["copied_apt_payloads"]==[],"Pure exact wheel installation inventory")
 runtime=j("tokenizers-component/TOKENIZERS-RUNTIME-RESULT.json")
 component=j("tokenizers-component/TOKENIZERS-COMPONENT-RESULT.json")
 need(runtime["status"]==component["status"]=="passed" and component["node_count"]==25 and component["edge_count"]==29,"Native completion")
 need(component["runtime_receipt_sha256"]==sha(raw("tokenizers-component/TOKENIZERS-RUNTIME-RESULT.json")),"Parent/child receipt binding")
 need(component["foundation"]==component["foundation_after"],"Original foundation validation changed")
 before=runtime["installed_before"]
 need(before==runtime["installed_after"] and before["status"]=="passed" and before["global_site_visible"] is False and before["declared_metadata_modified"] is False,"Before/after original installed inventory")
 need(before["actual_names"]==lock["names"] and before["actual_visible_distribution_count"]==25 and before["verified_site_files"]==825,"Actual isolated installed file inventory")
 installed={p["name"]:p for p in before["distributions"]}
 env=runtime["closure"]["environment"];active=[]
 wheelfacts=[];memberfacts={};all_wheel_members=0;all_record_hashes=0
 for name,p in sorted(packages.items()):
  original=graph_nodes[name];hand=handoff_nodes[name]
  need(p["version"]==original["version"]==hand["version"],"Original selected version: "+name)
  need(reqs(p["graph_requires_dist"])==reqs(original["requires_dist"])==reqs(hand["requires_dist"]),"Original full requirements: "+name)
  need(str(SpecifierSet(p["requires_python"]))==str(SpecifierSet(original["requires_python"]))==str(SpecifierSet(hand["requires_python"])),"Original Python bound: "+name)
  need(SpecifierSet(p["requires_python"]).contains(env["python_full_version"]),"Actual interpreter outside requirement: "+name)
  b=raw("tokenizers-inputs/wheels/"+p["artifact"]["filename"])
  need(len(b)==p["artifact"]["bytes"] and sha(b)==p["artifact"]["sha256"],"Actual wheel archive: "+name)
  with zipfile.ZipFile(io.BytesIO(b)) as w:
   infos=w.infolist();need(len(infos)==len({x.filename for x in infos})==p["wheel"]["entry_count"],"Wheel member inventory: "+name)
   bodies={}
   for item in infos:
    safe(item.filename);need(not stat.S_ISLNK(item.external_attr>>16) and not item.flag_bits&1,"Unsafe wheel member")
    if not item.is_dir():bodies[item.filename]=w.read(item)
   need(len(bodies)==p["wheel"]["file_count"],"Wheel regular member count")
   all_wheel_members+=len(bodies)
   for label in ("metadata","wheel","record"):
    member=p["wheel"][label+"_member"];body=bodies[member]
    need(sha(body)==p["wheel"][label+"_sha256"],"Exact original "+label+": "+name)
    retained.append(save("wheel-metadata/"+name+"/"+pathlib.PurePosixPath(member).name,body))
   meta=BytesParser(policy=compat32).parsebytes(bodies[p["wheel"]["metadata_member"]])
   need(canonicalize_name(meta["Name"])==name and meta["Version"]==p["version"],"Actual metadata identity")
   declared=meta.get_all("Requires-Dist",[])
   need(reqs(declared)==reqs(p["requires_dist"])==reqs(p["graph_requires_dist"]),"Original declared requirement semantics")
   need(str(SpecifierSet(meta.get("Requires-Python","")))==str(SpecifierSet(p["requires_python"])),"Original declared Python semantics")
   rows=list(csv.reader(io.StringIO(bodies[p["wheel"]["record_member"]].decode())))
   need(len(rows)==len(bodies) and len({r[0] for r in rows})==len(rows) and {r[0] for r in rows}==set(bodies),"Complete original RECORD")
   for member,encoded,size in rows:
    if member==p["wheel"]["record_member"]:need(encoded==size=="","Original RECORD self-row")
    else:
     algorithm,value=encoded.split("=",1);need(algorithm=="sha256","Original RECORD algorithm")
     need(base64.urlsafe_b64encode(hashlib.sha256(bodies[member]).digest()).rstrip(b"=").decode()==value and int(size)==len(bodies[member]),"Original RECORD digest/size")
     all_record_hashes+=1
   memberfacts[name]={member:{"bytes":len(body),"sha256":sha(body)} for member,body in bodies.items()}
   for m in p["native_members"]:
    need(memberfacts[name][m["member"]]=={"bytes":m["bytes"],"sha256":m["sha256"]},"Original native wheel member")
   need(installed[name]["wheel_sha256"]==sha(b) and installed[name]["version"]==p["version"] and installed[name]["verified_file_count"]==len(bodies)-1,"Native installed original wheel receipt")
   need(installed[name]["documented_rewrites"]==[{"path":p["wheel"]["record_member"],"reason":"pip installation RECORD"}],"Unreviewed installed member rewrite")
   wheelfacts.append({"name":name,"version":p["version"],"artifact":p["artifact"],"metadata_sha256":p["wheel"]["metadata_sha256"],"record_sha256":p["wheel"]["record_sha256"],"file_count":len(bodies),"native_member_count":len(p["native_members"]),"requires_python":p["requires_python"],"active_extras":p["active_extras"]})
   for value in declared:
    req=Requirement(value)
    if req.marker and not any(req.marker.evaluate({**env,"extra":extra}) for extra in ["",*p["active_extras"]]):continue
    target=canonicalize_name(req.name)
    need(req.url is None and target in packages and req.specifier.contains(packages[target]["version"]) and set(req.extras)<=set(packages[target]["active_extras"]),"Unclosed original active requirement")
    active.append({"from":name,"to":target,"requirement":value})
 expected={(e["from"],req_key(e["requirement"])) for e in lock["edges"]}
 need(len(active)==29 and {(e["from"],req_key(e["requirement"])) for e in active}==expected=={(e["from"],req_key(e["requirement"])) for e in runtime["closure"]["active_edges"]},"Actual original 29-edge closure")
 reached=set(lock["roots"])
 while True:
  more=reached|{e["to"] for e in active if e["from"] in reached}
  if more==reached:break
  reached=more
 need(reached==set(packages),"All selected nodes reachable from original roots")
 native=runtime["native_mappings"];maps=j("tokenizers-component/NATIVE-MAPPINGS.json")["mappings"]
 need(native["status"]=="passed" and native["raw_mapping_sha256"]==sha(raw("tokenizers-component/NATIVE-MAPPINGS.raw.txt")),"Actual mapping receipt/raw binding")
 need(all(not x["deleted"] and x["classification"] in ("source-extension","apt-library","image-platform") for x in maps),"Deleted/foreign native mapping")
 site=runtime["runtime"]["prefix"]+"/lib/python3.14/site-packages/"
 for row in native["source_extensions"]:
  need(row["path"].startswith(site) and row["class"]==64 and row["machine"]==183,"Native extension platform/path")
  member=row["path"][len(site):]
  need(memberfacts[row["package"]][member]=={"bytes":row["bytes"],"sha256":row["sha256"]},"Actually mapped original extension bytes")
  need(any(m["resolved_path"]==row["path"] and m["classification"]=="source-extension" for m in maps),"Native extension not actually mapped")
 need(len(native["source_extensions"])==8 and {x["package"] for x in native["source_extensions"]}=={"aiohttp","hf-xet","safetensors","tokenizers","pyyaml"},"All selected native wheel owners")
 hf=next(x for x in native["source_extensions"] if x["package"]=="hf-xet")
 need("libpython3.so" in hf["needed"],"HF scoped ABI3 stub link missing")
 for row in native["image_platform"]["members"]:
  original=next(x for x in lock["platform_runtime"]["files"] if x["path"]==row["path"])
  need(row["bytes"]==original["bytes"] and row["sha256"]==original["sha256"],"Pinned image library identity")
 pinned={}
 for line in raw("foundation-apt-inputs/foundation.tsv").decode().splitlines():
  name,version,architecture,digest,size,filename=line.split("\t")
  pinned[name]={"name":name,"version":version,"architecture":architecture,"sha256":digest,"bytes":int(size),"filename":filename}
 need(len(pinned)==122,"Original foundation archive set")
 for p in lock["apt_archives"]:need(p["name"] not in pinned,"Additional pin overwrites foundation");pinned[p["name"]]=p
 index={}
 for block in gzip.decompress(raw("TOKENIZERS-FROZEN-APT/Packages.gz")).split(b"\n\n"):
  if not block.strip():continue
  m=BytesParser(policy=compat32).parsebytes(block);key=(m["Package"],m["Version"],m["Architecture"])
  if key in {(p["name"],p["version"],p["architecture"]) for p in pinned.values()}:need(key not in index,"Duplicate original index");index[key]=m
 archive_members={urllib.parse.unquote(pathlib.PurePosixPath(n).name):n for n in z.namelist() if n.endswith(".deb")}
 need(len(archive_members)==124,"Ambiguous encoded APT archive names")
 apt_bodies={}
 for name,p in pinned.items():
  basename=pathlib.PurePosixPath(p["filename"]).name
  member=archive_members[basename];b=raw(member);record=index[(name,p["version"],p["architecture"])]
  need(len(b)==p["bytes"]==int(record["Size"]) and sha(b)==p["sha256"]==record["SHA256"] and record["Filename"]==p["filename"],"Original signed index/archive bytes: "+name)
  if name in {x["package"] for x in native["apt_libraries"]}:apt_bodies[name]=(member,b)
 apt_rows=[]
 for name,(archive_member,b) in sorted(apt_bodies.items()):
  wanted={x["path"]:x for x in native["apt_libraries"] if x["package"]==name}
  found=set()
  with tarfile.open(fileobj=io.BytesIO(ar_data(b)),mode="r:*") as t:
   for member in t:
    path="/"+member.name.removeprefix("./").lstrip("/")
    if path not in wanted:continue
    need(member.isfile() and path not in found,"Mapped library absent/ambiguous in original archive")
    body=t.extractfile(member).read();p=wanted[path]
    need(len(body)==p["bytes"] and sha(body)==p["sha256"],"Actual mapped library differs from original APT bytes")
    need(body[:6]==b"\x7fELF\x02\x01" and struct.unpack_from("<H",body,18)[0]==183,"Mapped APT library platform")
    need(any(m["resolved_path"]==path and m["classification"]=="apt-library" for m in maps),"APT library not actually mapped")
    found.add(path);apt_rows.append({"package":name,"path":path,"archive_member":archive_member,"bytes":len(body),"sha256":sha(body),"original_archive_sha256":pinned[name]["sha256"]})
  need(found==set(wanted),"Original APT archive omitted actual mapped bytes")
 need(len(apt_rows)==44,"All actual APT library records")
 py_stub=next(x for x in native["apt_libraries"] if x["path"].endswith("/libpython3.so"))
 py_real=next(x for x in native["apt_libraries"] if x["path"].endswith("/libpython3.14.so"))
 need(py_stub["bytes"]==4160 and "libpython3.14.so" in py_stub["needed"] and py_real["package"]=="python","Actual pinned stub/runtime chain")
 image=j("TOKENIZERS-SOURCE-IMAGE.json")[0]
 disconnected=j("TOKENIZERS-DISCONNECTED-CONTAINER.json")[0];completed=j("TOKENIZERS-COMPLETED-CONTAINER.json")[0]
 cid=raw("TOKENIZERS-CONTAINER-ID.txt").decode().strip();offline=j("TOKENIZERS-NETWORK-OFFLINE.json")
 need(len(cid)==64 and disconnected["Id"]==completed["Id"]==cid==offline["container_id"]==runtime["network"]["container_id"],"Actual owned container identity")
 need(image["Architecture"]=="arm64" and image["Os"]=="linux" and inputs["native_image"] in image["RepoDigests"],"Immutable ARM64 image")
 need(disconnected["Image"]==completed["Image"]==image["Id"]==runtime["source_image"]["docker_image_id"],"Actual source image binding")
 need(disconnected["State"]["Running"] is True and completed["State"]["Running"] is False and completed["State"]["ExitCode"]==0,"Actual container completion")
 need(disconnected["NetworkSettings"]["Networks"]==completed["NetworkSettings"]["Networks"]=={},"Actual offline container")
 for inspection in (disconnected,completed):
  need(inspection["Config"]["User"]=="1000:1000" and inspection["HostConfig"]["NanoCpus"]==2000000000 and inspection["HostConfig"]["Memory"]==6442450944 and inspection["HostConfig"]["PidsLimit"]==512,"Finite resource/user contract")
 need(offline["inspect_sha256"]==sha(raw("TOKENIZERS-DISCONNECTED-CONTAINER.json")) and offline["lock_sha256"]==sha(raw("tokenizers-inputs/neutts_tokenizers_runtime_lock.json")),"Offline host evidence binding")
 need(runtime["network"]==component["network"] and runtime["network"]["interfaces"]==[[1,"lo"]] and runtime["network"]["external_network_available"] is False,"Actual loopback-only runtime")
 need(component["raw_pip"]["exit_code"]==0 and raw("tokenizers-component/RAW-PIP-CHECK.log")==b"No broken requirements found.\n","Actual raw pip check")
 need(runtime["runtime"]["sys_platform"]=="android" and runtime["runtime"]["machine"]=="aarch64" and runtime["runtime"]["api_level"]==24 and runtime["runtime"]["uid"]==1000 and env["python_full_version"]=="3.14.6","Actual native target")
 operations=runtime["operations"]
 need(set(operations)=={"tokenizers","dependencies","hf_xet","safetensors"} and all(v["status"]=="passed" for v in operations.values()),"All actual operation groups")
 word=operations["tokenizers"]["wordpiece"]
 need(word["actual_ids"]==word["expected_ids"]==[1,3,5,6,7,8,9,2] and word["pair_ids"]==[1,3,2,4,2] and word["pair_type_ids"]==[0,0,0,1,1] and word["batch_count"]==64,"Literal WordPiece/native batch")
 need(word["actual_offsets"]==[[0,0],[0,5],[6,8],[8,11],[11,15],[16,20],[20,21],[0,0]],"Literal Unicode/source offsets")
 need(word["serialized_sha256"]==sha(raw("tokenizers-component/operation-data/wordpiece.json")),"Actual serialization fixture")
 need(operations["tokenizers"]["byte_bpe"]=={"training_rows":20,"vocab_size":280,"batch_count":80,"unicode_round_trips":6},"Actual byte BPE/Unicode/batch")
 dep=operations["dependencies"]
 need(dep["http"]["loopback_only"] is True and dep["http"]["body_sha256"]==sha(b'{"fixture":"termux-tokenizers","values":[1,2,3]}\n') and dep["http"]["requests"]==[{"method":"GET","path":"/fixture.json"},{"method":"HEAD","path":"/fixture.json"},{"method":"GET","path":"/fixture.json"}],"Actual local HTTP dependency fixture")
 need(dep["pyyaml"]["actual_c_api"] is True and dep["hub"]["local_only_cache_miss"]=="LocalEntryNotFoundError","Actual LibYAML and local-only Hub")
 need(operations["hf_xet"]["original_hash"]!=operations["hf_xet"]["changed_hash"] and operations["hf_xet"]["bytes"]==3298,"Actual HF file sensitivity")
 s=operations["safetensors"];body=raw("tokenizers-component/operation-data/fixture.safetensors")
 need(sha(body)==s["serialized_sha256"]==s["file_sha256"] and s["serialization_api"]=="TensorSpec" and s["backing_buffer_retained"] is True,"Actual Safetensors serialization")
 hlen=struct.unpack_from("<Q",body)[0];header=json.loads(body[8:8+hlen]);values=struct.unpack("<4f",body[8+hlen:])
 need(list(values)==s["values"]==[0.25,-1.5,3.0,42.0] and s["shape"]==[2,2] and s["dtype"]=="F32" and {x["case"] for x in s["corrupt_inputs_rejected"]}=={"truncated-header","truncated-payload","invalid-header"},"Literal Safetensors bytes and corrupt-input rejection")
 core=j("NEUTTS-CORE-RESULT.json")
 need(core["status"]=="passed" and len(core["cases"])==7 and all(x["status"]=="passed" and x["exit_code"]==0 and not x["timed_out"] and x["receipt_sha256"]==sha(raw(x["receipt"])) for x in core["cases"]),"Original seven foundation cases")
 frozen=j("TOKENIZERS-FROZEN-APT/RESULT.json")
 need(frozen["status"]=="passed" and frozen["insecure_repository_exceptions"] is False and frozen["acquired_index_bytes_equal"] is True,"Native signed APT authentication")
 need(j("TOKENIZERS-EXIT.json")=={"schema_version":1,"stage":"complete","exit_code":0,"release_output":False},"Original exit receipt")
 need(b"NEUTTS_TOKENIZERS_RUNTIME_PASSED" in raw("tokenizers-native-probe.log") and b"NEUTTS_TOKENIZERS_RUNTIME_PASSED" in (BASE/"original-job-log.txt").read_bytes(),"Actual native and original job log marker")
 need(all(runtime.get(k) is False for k in ("engine_installed","models_downloaded","production_admission_changed","release_output")),"Engine/model/release boundary")
 # Retain every non-archive member, excluding repeated byte-identical package index snapshots.
 selected=[i.filename for i in entries if not i.is_dir() and not i.filename.endswith((".deb",".whl")) and i.filename not in {"NEUTTS-FROZEN-APT/Packages.gz","foundation-apt-inputs/snapshot/Packages.gz"}]
 for name in selected:retained.append(save("raw/"+name,raw(name)))
 save_json("WHEEL-AND-METADATA-REVIEW.json",{"status":"passed","wheel_count":25,"original_wheel_member_count":all_wheel_members,"original_record_payload_hashes_verified":all_record_hashes,"original_metadata_and_record_hashes_match":True,"original_graph_node_count":117,"original_graph_edge_count":194,"runtime_node_count":25,"runtime_edge_count":29,"active_edges":active,"wheels":wheelfacts,"native_installed_before_equals_after":True,"native_verified_site_files":825,"installed_files_reexamined_on_host":False,"installed_record_scope":"Original wheel RECORDs independently verified here; native source verifies pip's installation RECORD and owned files before and after."})
 save_json("MAPPED-LIBRARY-REVIEW.json",{"status":"passed","actual_source_extensions":native["source_extensions"],"original_apt_member_comparisons":apt_rows,"image_platform":native["image_platform"],"mapping_classification_counts":dict(collections.Counter(x["classification"] for x in maps)),"hf_abi3_python_stub":py_stub,"actual_python_runtime":py_real,"image_scope":"Five actual image platform identities match the immutable image lock and native receipt; this host review does not independently extract the OCI image."})
 summary={"schema_version":1,"status":"passed","head_sha":HEAD,"run_id":39447721557,"job_id":118713971420,
 "artifact":{"id":12277372818,"bytes":197910138,"sha256":DIGEST,"whole_archive_verified":True,"member_count":247,"all_member_crc_size_sha256_verified":True,"uncompressed_bytes":199382279,"full_inventory_sha256":sha(inventory_raw)},
 "source":{"exact_commit_tree_verified":True,"input_count":len(bindings),"lock_sha256":sha(raw("tokenizers-inputs/neutts_tokenizers_runtime_lock.json"))},
 "runtime":{"python":"3.14.6","sys_platform":"android","machine":"aarch64","api_level":24,"uid":1000,"node_count":25,"edge_count":29,"raw_pip_exit_code":0,"native_verified_site_files":825,"before_after_equal":True,"global_site_visible":False},
 "original_inputs":{"wheel_count":25,"wheel_members":all_wheel_members,"record_payload_hashes":all_record_hashes,"foundation_apt_archives":122,"extra_apt_archives":2,"all_124_archive_hashes_match_original_signed_index":True},
 "network":{"container_id":cid,"image":inputs["native_image"],"docker_image_id":image["Id"],"actual_inspection_before_and_after_disconnected":True,"actual_child_interfaces":[[1,"lo"]],"external_network_available":False,"cpus":2,"memory_bytes":6442450944,"pids":512,"host_timeout_minutes":35,"child_timeout_seconds":240,"workflow_timeout_minutes":45},
 "operations":operations,"native_mappings":{"source_extensions":8,"apt_libraries":44,"image_platform_files":5,"rejected_mappings":0},"foundation":{"cases":7,"status":"passed","raw_pip_exit_code":component["foundation"]["raw_pip_exit_code"],"note":"The original foundation's raw pip exit 1 and reviewed APT tag diagnostics remain preserved separately from the isolated Tokenizers raw pip exit 0."},
 "limits":{"engine_admitted":False,"engine_python_bound_modified":False,"model_downloaded":False,"gated_weights_requested":False,"synthesis_tested":False,"physical_audio_tested":False,"release_output":False,"combined_116_runtime_claimed":False,"host_native_execution_performed":False},
 "retention":{"full_artifact_outside_repository":True,"all_outer_members_in_inventory":True,"all_non_archive_members_retained_except_identical_index_copies":True,"omitted_duplicate_indices":["NEUTTS-FROZEN-APT/Packages.gz","foundation-apt-inputs/snapshot/Packages.gz"]}}
 for name in summary["retention"]["omitted_duplicate_indices"]:need(raw(name)==raw("TOKENIZERS-FROZEN-APT/Packages.gz"),"Index omission is not byte-identical")
ci_base=BASE.parent.parent/"neutts-readable-inputs-checkpoint-20261020/native-monitor"
for name in ("ci-push-original-api.json","ci-pr-original-api.json","ci-push-original-job-log.txt"):
 b=(ci_base/name).read_bytes();save("ci/"+name,b)
 if name.endswith(".json"):
  c=json.loads(b);need(c["head_sha"]==HEAD and c["status"]=="completed" and c["conclusion"]=="success","Exact 899 CI success")
 else:need(b"1241 passed, 84 skipped, 577 subtests passed in 28.34s" in b,"Actual 899 CI totals")
summary["ci"]={"head_sha":HEAD,"push_run":39447721333,"push_job":118713969680,"pr_run":39447740828,"passed":1241,"skipped":84,"subtests_passed":577,"seconds":28.34,"linux_full_preparation_umask_0077_regression":"Included in the exact source-bound focused test file and full successful Linux suite; no separate per-test log is claimed."}
for name in ("DOWNLOAD-VERIFIED.json","FULL-MEMBER-INVENTORY.json.gz","original-artifacts-wrapper.json","original-jobs-wrapper.json","original-run-api.json","original-job-log.txt"):
 save(name,(BASE/name).read_bytes())
save("original-source-tree-api.json.gz",gzip.compress((BASE/"original-source-tree-api.json").read_bytes(),mtime=0))
summary["source"]["original_tree_json_sha256"]=sha((BASE/"original-source-tree-api.json").read_bytes())
summary["review_script_sha256"]=sha(pathlib.Path(__file__).read_bytes())
save("verify_evidence.py",pathlib.Path(__file__).read_bytes())
save_json("REVIEW.json",summary)
print(json.dumps({"status":"passed","review":str(OUT/"REVIEW.json"),"review_bytes":(OUT/"REVIEW.json").stat().st_size,"review_sha256":sha((OUT/"REVIEW.json").read_bytes()),"source_inputs":len(bindings),"wheels":25,"wheel_members":all_wheel_members,"record_hashes":all_record_hashes,"apt_library_comparisons":len(apt_rows),"retained_artifact_members":len(selected),"retained_wheel_metadata_members":75}))
