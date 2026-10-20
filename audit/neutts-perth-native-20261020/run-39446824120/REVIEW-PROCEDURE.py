"""Independent bounded review of exact successful public Perth runtime evidence."""
import base64,collections,csv,email.parser,gzip,hashlib,io,json,math,pathlib,re,stat,subprocess,sys,tarfile,zipfile
sys.stdout.reconfigure(encoding="utf-8")
try:
 from packaging.requirements import Requirement
 from packaging.specifiers import SpecifierSet
 from packaging.utils import canonicalize_name
except ImportError:
 from pip._vendor.packaging.requirements import Requirement
 from pip._vendor.packaging.specifiers import SpecifierSet
 from pip._vendor.packaging.utils import canonicalize_name
ROOT=pathlib.Path(sys.argv[1]);BASE=pathlib.Path(sys.argv[2])
DEST=ROOT/"audit/neutts-perth-native-20261020/run-39446824120"
HEAD="73525752755f990926243396f34f5ba8e6148a03"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,value):
 raw=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+"\n").encode()
 path=DEST/name
 if path.exists():assert path.read_bytes()==raw,name
 else:path.write_bytes(raw)
 return {"path":name,"bytes":len(raw),"sha256":sha(raw)}
proof=json.loads((DEST/"FULL-DOWNLOAD-VERIFIED.json").read_bytes())
assert proof["sha256"]=="c9961ed9dfac7177d1aa79e805b38769caf329afbcdd0f9535715fecfa5302dd" and proof["member_count"]==274
rows={r["path"]:r for r in json.loads(gzip.decompress((DEST/"FULL-MEMBER-INVENTORY.json.gz").read_bytes()))}
archive=zipfile.ZipFile(BASE/"artifact.zip")
def member(name,limit=128*1024*1024):
 pin=rows[name];assert pin["bytes"]<=limit
 raw=archive.read(name);assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
 return raw
def obj(name):return json.loads(member(name))
component=obj("PERTH-COMPONENT-RESULT.json");runtime=obj("PERTH-RUNTIME-RESULT.json");setup=obj("PERTH-APT-SETUP.json")
lock=obj("perth-inputs/neutts_perth_runtime_lock.json");manifest=obj("perth-runtime-installed-closure.json")
probe=obj("PERTH-PROBE-INPUTS.json")
assert probe["head_sha"]==HEAD and probe["inputs"]["scripts/neutts_perth_runtime_lock.json"]==sha(member("perth-inputs/neutts_perth_runtime_lock.json"))
flags=("default_speech_model_downloaded","microphone_used","neutts_engine_installed","neutts_python_bound_changed","production_admission_changed","release_output")
for value in (component,runtime,setup):
 assert value["status"]=="passed" and value["stage"]=="complete" and all(value[k] is False for k in flags)
assert component["runtime_receipt_sha256"]==rows["PERTH-RUNTIME-RESULT.json"]["sha256"]
assert component["apt_setup_sha256"]==rows["PERTH-APT-SETUP.json"]["sha256"]
assert component["child"]["exit_code"]==0 and component["actual_runtime_distribution_count"]==43 and component["active_edge_count"]==50
assert component["public_bundled_watermark_checkpoint_executed"] is True
assert runtime["installed_before"]==runtime["installed_after"]
inventory=runtime["installed_before"]
assert inventory["actual_visible_distribution_count"]==43 and inventory["global_site_visible"] is False and inventory["declared_metadata_modified"] is False
assert inventory["verified_site_files"]==19937 and inventory["actual_names"]==sorted(lock["names"])
assert len(inventory["distributions"])==43 and len({x["name"] for x in inventory["distributions"]})==43
assert runtime["record_integrity_before"]==runtime["record_integrity_after"]=={"original_apt_records_modified":False,"record_rows":5456,"status":"passed","wheel_count":36}
assert len(manifest["wheels"])==len(lock["packages"])==36 and manifest["apt_python"]==lock["apt_python"] and len(manifest["apt_python"])==7
assert manifest["names"]==sorted(lock["names"]) and len(lock["nodes"])==43 and len(lock["edges"])==50
assert runtime["closure"]["node_count"]==43 and runtime["closure"]["active_edge_count"]==50
assert runtime["closure"]["metadata_modified"] is False and runtime["closure"]["selected_extras"]==[]
assert runtime["closure"]["foundation_support_outside_graph"]==["pip","torchcodec"]
# Bind the actual disconnected container to its original ID, image and resource contract.
container_id=member("PERTH-CONTAINER-ID.txt").decode().strip()
disconnected=obj("PERTH-DISCONNECTED-CONTAINER.json")
signal=obj("PERTH-NETWORK-DISCONNECTED.json")
assert len(disconnected)==1 and disconnected[0]==signal["container"]
container=disconnected[0]
assert re.fullmatch("[0-9a-f]{64}",container_id) and container["Id"]==container_id
assert container["NetworkSettings"]["Networks"]=={} and container["State"]["Running"] is True
assert container["Image"]==runtime["source_image"]["docker_image_id"] and container["Config"]["User"]=="1000:1000"
assert container["HostConfig"]["Memory"]==6442450944 and container["HostConfig"]["NanoCpus"]==2000000000 and container["HostConfig"]["PidsLimit"]==512
assert runtime["network"]==runtime["network_after"]
assert runtime["network"]["interfaces"]==[[1,"lo"]] and runtime["network"]["network_connections_available"] is False
assert runtime["network"]["host_receipt_sha256"]==rows["PERTH-NETWORK-DISCONNECTED.json"]["sha256"]
# Preserve exact two-package APT setup and the already present GMP provenance.
assert setup["verified_archive_count"]==125 and setup["compiler_installed"] is False
assert setup["only_installed_or_reinstalled"]==["libyaml","python-msgpack"] and setup["plan"]["removals"] is False
assert setup["inherited_gmp"]["installed_or_upgraded"] is False
assert setup["signed_snapshot"]["status"]=="authenticated-original-index"
assert setup["signed_snapshot"]["receipt_sha256"]==rows["perth-signed-snapshot/RESULT.json"]["sha256"]
before=obj("PERTH-APT-BEFORE.json");after=obj("PERTH-APT-AFTER.json");expected=dict(before)
for pin in lock["apt_install"]:expected[pin["name"]]={"version":pin["version"],"architecture":pin["architecture"],"status":"installed"}
assert after==expected
assert component["raw_pip"]["exit_code"]==1 and component["raw_pip"]["pip_check_passed"] is False
assert component["raw_pip"]["requirements_have_no_missing_or_conflicting_dependencies"] is True
assert component["raw_pip"]["sha256"]==rows["RAW-PIP-CHECK.log"]["sha256"]
assert all(x["metadata_modified"] is False and x["supported_tags_modified"] is False for x in component["raw_pip"]["original_apt_tag_diagnostics"])
# Check every selected wheel's actual CRC, RECORD and original metadata identities.
wheel_reviews=[];distributions={};native_pins={};package_by_name={p["name"]:p for p in lock["packages"]}
public_bodies={}
for entry in manifest["wheels"]:
 pin=package_by_name[entry["name"]]
 for key in ("artifact","wheel","requires_dist","requires_python","version","native_members"):assert entry[key]==pin[key]
 path="perth-inputs/wheels/"+pin["artifact"]["filename"];data=member(path)
 assert sha(data)==pin["artifact"]["sha256"] and len(data)==pin["artifact"]["bytes"]
 with zipfile.ZipFile(io.BytesIO(data)) as wh:
  infos=wh.infolist();assert len(infos)==len({x.filename for x in infos}) and len(infos)<=20000
  assert sum(x.file_size for x in infos)<=256*1024*1024
  bodies={}
  for info in infos:
   path_name=pathlib.PurePosixPath(info.filename)
   assert info.orig_filename==info.filename and path_name.as_posix()==info.filename.rstrip("/") and not path_name.is_absolute()
   assert ".." not in path_name.parts and "\\" not in info.filename and ":" not in info.filename
   assert stat.S_IFMT(info.external_attr>>16) in ((0,stat.S_IFDIR) if info.is_dir() else (0,stat.S_IFREG)) and not info.flag_bits&1
   assert info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) and info.file_size<=64*1024*1024
   raw=wh.read(info);assert len(raw)==info.file_size
   if info.is_dir():
    assert raw==b""
    continue
   bodies[info.filename]=raw
  wheel=pin["wheel"];record=wheel["record_member"]
  records=list(csv.reader(io.StringIO(bodies[record].decode())))
  assert all(len(x)==3 for x in records) and len(records)==len({x[0] for x in records})==len(bodies)
  assert {x[0] for x in records}==set(bodies)
  for path_name,digest,size in records:
   if path_name==record:assert digest==size==""
   else:
    raw=bodies[path_name]
    assert digest=="sha256="+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=") and size==str(len(raw))
  for key in ("metadata","record","wheel"):assert sha(bodies[wheel[key+"_member"]])==wheel[key+"_sha256"]
  meta=email.parser.BytesParser().parsebytes(bodies[wheel["metadata_member"]])
  assert canonicalize_name(meta["Name"])==pin["name"] and meta["Version"]==pin["version"]
  assert meta.get("Requires-Python","")==pin["requires_python"] and meta.get_all("Requires-Dist",[])==pin["requires_dist"]
  distributions[pin["name"]]={"version":pin["version"],"requires_python":pin["requires_python"],"requires_dist":pin["requires_dist"]}
  for n in pin["native_members"]:
   raw=bodies[n["member"]];assert sha(raw)==n["sha256"] and len(raw)==n["bytes"]
   native_pins[(pin["name"],n["member"])]=n
  if pin["name"] in ("resemble-perth","soundfile"):public_bodies[pin["name"]]=bodies
  wheel_reviews.append({"name":pin["name"],"version":pin["version"],"artifact":pin["artifact"],"members":len(bodies),
   "all_crc_and_record_hashes_verified":True,"metadata_sha256":wheel["metadata_sha256"],"native_member_count":len(pin["native_members"])})
for pin in manifest["apt_python"]:
 distributions[pin["name"]]={"version":pin["version"],"requires_python":pin["requires_python"],"requires_dist":pin["requires_dist"]}
 for row in pin["files"]:
  if row["path"].endswith(".so") or ".so." in row["path"]:native_pins[(pin["name"],row["path"])]=row
 copied=next(x for x in manifest["copied_apt_payloads"] if x["name"]==pin["name"])
 assert copied["metadata_changed"] is False and copied["record_changed"] is False
 assert copied["archive_sha256"]==pin["archive"]["sha256"] and copied["file_count"]==pin["file_count"] and copied["bytes"]==pin["bytes"]
 # Match the complete original archive bytes via the verified outer ZIP inventory.
 candidates=[r for r in rows.values() if r["sha256"]==pin["archive"]["sha256"] and r["bytes"]==pin["archive"]["bytes"]]
 assert candidates
# Recompute every original declared clause, Python bound and active edge.
def req_key(value):
 req=Requirement(value);return canonicalize_name(req.name),str(req.specifier),tuple(sorted(req.extras)),str(req.marker or ""),req.url
environment=runtime["closure"]["actual_marker_environment"]
assert all(environment[k]==v for k,v in lock["environment"].items())
nodes={p["name"]:p for p in lock["nodes"]};edges=[]
assert set(distributions)==set(nodes)==set(lock["names"])
for name,actual in distributions.items():
 source=nodes[name]
 assert actual["version"]==source["version"] and SpecifierSet(actual["requires_python"])==SpecifierSet(source["requires_python"] or "")
 assert sorted(map(req_key,actual["requires_dist"]))==sorted(map(req_key,source["requires_dist"]))
 assert environment["python_full_version"] in SpecifierSet(actual["requires_python"])
 for declaration in actual["requires_dist"]:
  req=Requirement(declaration)
  if req.marker is not None and not req.marker.evaluate(environment):continue
  target=canonicalize_name(req.name)
  assert req.url is None and not req.extras and target in distributions and distributions[target]["version"] in req.specifier
  edges.append((name,target,req_key(declaration)))
assert len(edges)==50 and sorted(edges)==sorted((e["from"],e["to"],req_key(e["requirement"])) for e in lock["edges"])
# Actual native mapping records stay inside the isolated source payload or exact APT/image owner.
maps=obj("PERTH-NATIVE-MAPPINGS.json")
assert maps["raw_sha256"]==sha(member("PERTH-NATIVE-MAPPINGS.raw.txt"))==runtime["native_mappings"]["raw_mapping_sha256"]
assert not any(x["classification"].startswith("rejected-") for x in maps["mappings"])
assert not any(x["resolved_path"].startswith("/data/data/com.termux/files/usr/lib/python3.14/site-packages/") for x in maps["mappings"])
native=runtime["native_mappings"];assert native["status"]=="passed" and len(native["actually_mapped_extensions"])==162
for row in native["actually_mapped_extensions"]:
 path=row["path"].split("/site-packages/",1);assert len(path)==2
 pin=native_pins[(row["package"],path[1])]
 assert row["bytes"]==pin["bytes"] and row["sha256"]==pin["sha256"] and row["class"]==64 and row["machine"]==183
apt=native["apt"]["mapped_apt_libraries"];assert native["apt"]["status"]=="passed" and len(apt)==148
for row in apt:
 candidates=[p for p in rows.values() if p["sha256"]==row["archive_sha256"] and p["path"].endswith(".deb")]
 assert candidates and row["class"]==64 and row["machine"]==183
image=native["image_platform"]
assert image["status"]=="verified-image-members" and len(image["members"])==5
for item in image["members"]:
 pin=next(p for p in lock["platform_runtime"]["files"] if p["path"]==item["path"])
 assert item["sha256"]==pin["sha256"] and item["bytes"]==pin["bytes"] and item["native_image"]==lock["platform_runtime"]["native_image"]
snd=[p for p in apt if p["package"]=="libsndfile"];assert len(snd)==1
snd=snd[0]
assert snd["package_version"]=="1.2.2-3" and snd["archive_sha256"]=="1e1fb77b14ec26f3ff6ded069e9ec816ab7535ae5d074122c6727b0f59d8aff3"
assert snd["sha256"]=="079263392fddcdd975f2d452f6fd654e26f199fda1c85e08d67fedfbb4b55825" and snd["bytes"]==439352 and snd["soname"]==["libsndfile.so"]
# Independently check that the newly discovered library is the exact original DEB member.
original=member(next(p["path"] for p in rows.values() if p["sha256"]==snd["archive_sha256"]))
assert original.startswith(b"!<arch>\n");offset=8;pieces={}
while offset<len(original):
 header=original[offset:offset+60];assert len(header)==60 and header[58:]==b"`\n"
 name=header[:16].decode().strip().rstrip("/");size=int(header[48:58]);offset+=60
 assert name not in pieces and 0<=size<=len(original)-offset
 pieces[name]=original[offset:offset+size];offset+=size+(size%2)
assert offset==len(original)
payload=next(v for k,v in pieces.items() if k.startswith("data.tar."))
with tarfile.open(fileobj=io.BytesIO(payload),mode="r:*") as tf:
 found=[m for m in tf if m.name.lstrip("./")==snd["path"].lstrip("/")]
 assert len(found)==1 and found[0].isfile() and found[0].size==439352
 assert sha(tf.extractfile(found[0]).read())==snd["sha256"]
# Public checkpoint and SoundFile derivative identity, then measured real API output.
operation=runtime["perth"]
assert operation["status"]=="passed" and operation["public_class"]=="perth.PerthImplicitWatermarker"
assert operation["injected_original_model"] is True and operation["weights_only"] is True and operation["map_location"]=="cpu" and operation["strict_state_dict"] is True
assert operation["checkpoint_step"]==250000 and operation["actual_state_tensor_count"]==59
assert operation["checkpoint_sha256"]==lock["operation"]["checkpoint"]["sha256"]=="a15bce457ebc53ce5e6c9c3f11df78cf7ee2bf9cdab0a798902135b4c4027670"
for key in ("checkpoint","hparams"):
 pin=lock["operation"][key];raw=public_bodies["resemble-perth"][pin["member"]]
 assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
assert package_by_name["soundfile"]["artifact"]["sha256"]=="ad4f764ecc142ab5a9e05a0d61fda83ddf190fb7d59ca3c0da094be6229ee992"
assert package_by_name["resemble-perth"]["artifact"]["sha256"]=="b38db439e790d1bd0fd78eca9ce1c0ab9660ff4c6c0106abd0414b0816e2ce81"
assert operation["soundfile_ctypes_lookup"] is None and operation["soundfile_library"]=="libsndfile.so" and operation["libsndfile_version"]=="1.2.2"
assert [x["sample_rate"] for x in operation["operations"]]==[24000,32000]
for measured in operation["operations"]:
 rate=measured["sample_rate"];assert measured["samples"]==rate and measured["dtype"]=="float32" and measured["wav_bytes"]==4*rate+80
 assert measured["input_unchanged"] is True and measured["output_changed"] is True and measured["quality_threshold_asserted"] is False
 assert measured["watermarked_sha256"]!=measured["waveform_sha256"] and math.isfinite(measured["max_absolute_delta"]) and measured["max_absolute_delta"]>0
 for label in ("clean","watermarked"):
  confidence=measured["confidence"][label]
  assert math.isfinite(confidence["confidence"]) and 0<=confidence["confidence"]<=1 and confidence["rounded"]==float(round(confidence["confidence"]))
assert runtime["auxiliary"]["status"]=="passed" and runtime["auxiliary"]["jit_disabled"] is False and runtime["auxiliary"]["numba_nopython_result"]==14.0
review={"schema":"perth-native-independent-review/v1","status":"passed","head_sha":HEAD,"run_id":39446824120,
 "job_id":118710822208,"artifact_id":12275718653,"whole_artifact_sha256":proof["sha256"],"whole_artifact_bytes":proof["bytes"],
 "all_zip_members_verified":274,"recorded_source_inputs_verified":52,"complete_runtime_distributions":43,"active_dependency_edges":50,
 "runtime_wheels":36,"original_apt_python_payloads":7,"verified_native_installed_site_files":19937,"verified_native_installed_wheel_record_rows":5456,
 "installed_before_after_identical":True,"all_selected_wheels_independently_crc_record_metadata_verified":wheel_reviews,
 "actual_mapped_extensions":162,"actual_mapped_extension_distribution_count":len({r["package"] for r in native["actually_mapped_extensions"]}),
 "native_verified_apt_library_mappings":148,"apt_library_owner_count":len({r["package"] for r in apt}),"pinned_image_members":5,
 "all_mapping_identities_bound_to_original_manifests":True,"independently_rehashed_original_libsndfile":snd,
 "network_before_after":runtime["network"],"compiler_installed":False,"only_additional_apt_installs":["libyaml","python-msgpack"],
 "foundation_support_outside_graph":["pip","torchcodec"],"foundation_cases":7,
 "public_operations":operation,"auxiliary_operations":runtime["auxiliary"],
 "raw_pip_check_exit_code_preserved":1,"original_apt_tags_or_metadata_changed":False,
 "watermark_detection_quality_certified":False,"scope":"Public bundled checkpoint and deterministic one-second synthetic waveforms; real API compatibility operations",
 **{flag:False for flag in flags}}
result=save("NATIVE-REVIEW.json",review);save("REVIEW-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"passed","review":result,"runtime_distributions":43,"dependency_edges":50,"wheel_record_reviews":36,"native_mappings":162,"apt_mappings":148,"state_tensors":59},ensure_ascii=True))
