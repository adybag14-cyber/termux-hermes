"""Interpret the fully verified third complete-runtime failure; no target execution."""
import ast,copy,gzip,hashlib,io,json,math,pathlib,re,subprocess,sys,zipfile
ROOT=pathlib.Path(sys.argv[1]); BASE=pathlib.Path(sys.argv[2])
DEST=ROOT/"audit/neutts-complete-runtime-native-20261020/run-39456043425/full-artifact-review"
ART=DEST/"artifact"
HEAD="3f1f404c72addb91f1d4937342c20e555be58a58"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(name):return (ART/pathlib.PurePosixPath(name)).read_bytes()
def load(name):return json.loads(raw(name))
def jbytes(v):return (json.dumps(v,sort_keys=True,indent=2,ensure_ascii=True)+"\n").encode()
def save(name,data):
 p=DEST/name
 if p.exists():assert p.read_bytes()==data,"Refuse a changed review: "+name
 else:p.write_bytes(data)
 return {"path":name,"bytes":len(data),"sha256":sha(data)}
proof=json.loads((DEST/"FULL-DOWNLOAD-VERIFIED.json").read_bytes())
binding=json.loads((DEST/"EXECUTED-SOURCE-BINDINGS.json").read_bytes())
assert binding["source_count"]==118 and binding["head_sha"]==HEAD
inventory=json.loads(gzip.decompress((DEST/"FULL-MEMBER-INVENTORY.json.gz").read_bytes()))
by_path={r["path"]:r for r in inventory}
lock_bytes=raw("complete-inputs/neutts_complete_runtime_lock.json")
assert sha(lock_bytes)=="0e4818b8da88237f3aacb79d0e0a928605b4851c5a1fb8e4613918142a9c7c19"
assert next(s["sha256"] for s in binding["sources"] if s["path"]=="scripts/neutts_complete_runtime_lock.json")==sha(lock_bytes)
lock=json.loads(lock_bytes);manifest=load("complete-runtime-installed-closure.json")
prepared=load("complete-inputs/COMPLETE-PREPARED-INPUTS.json")
assert lock["node_count"]==len(lock["nodes"])==len(set(lock["names"]))==116
assert lock["edge_count"]==len(lock["edges"])==183
assert lock["wheel_count"]==len(lock["packages"])==105 and len(lock["apt_python"])==11
assert lock["names"]==manifest["names"]
assert {p["name"] for p in manifest["wheels"]}.isdisjoint({p["name"] for p in manifest["apt_python"]})
assert len(manifest["wheels"])+len(manifest["apt_python"])==116
assert len(manifest["copied_apt_payloads"])==11
expected_wheels={p["name"]:p for p in lock["packages"]}
wheels=[]
for p in manifest["wheels"]:
 expected=expected_wheels[p["name"]]
 original={k:v for k,v in p.items() if k!="wheel_path"}
 assert original==expected
 member="complete-inputs/wheels/"+p["artifact"]["filename"]
 assert p["wheel_path"]=="/out/"+member
 actual=by_path[member]
 assert actual["bytes"]==p["artifact"]["bytes"] and actual["sha256"]==p["artifact"]["sha256"]
 wheels.append({"name":p["name"],"version":p["version"],"member":member,
  "bytes":actual["bytes"],"sha256":actual["sha256"]})
assert manifest["apt_python"]==lock["apt_python"]
apt_by_name={p["name"]:p for p in lock["apt_python"]}
for p in manifest["copied_apt_payloads"]:
 expected=apt_by_name[p["name"]]
 assert p["archive_sha256"]==expected["archive"]["sha256"]
 assert p["metadata_sha256"]==expected["metadata_sha256"]
 assert p["bytes"]==expected["bytes"] and p["file_count"]==expected["file_count"]==len(expected["files"])
 assert p["metadata_changed"] is False and p["record_changed"] is False
assert prepared["status"]=="verified-complete-dependency-inputs" and prepared["lock_sha256"]==sha(lock_bytes)
assert prepared["node_count"]==116 and prepared["active_edge_count"]==183 and prepared["wheel_count"]==105
assert prepared["native_runtime_tested"] is False and prepared["installed"] is False
assert prepared["foundation_support_outside_graph"]==lock["foundation_support_outside_graph"]==["pip","torchcodec"]
assert lock["excluded_engine"]=={"installed":False,"name":"neutts","requires_python":"<3.14,>=3.10","version":"1.4.1"}
apt_pins=[]
for line in raw("NEUTTS-PINNED-APT.tsv").decode().splitlines():
 name,version,arch,digest,size,filename=line.split("\t")
 apt_pins.append({"name":name,"version":version,"architecture":arch,"sha256":digest,"bytes":int(size),"filename":filename})
assert len(apt_pins)==len({p["name"] for p in apt_pins})==122
apt_pins += lock["apt_install"]+lock["apt_provenance_only"]
assert len(apt_pins)==len({p["name"] for p in apt_pins})==142
extra={p["name"] for p in lock["apt_install"]+lock["apt_provenance_only"]}
archives=[]
for p in apt_pins:
 basename=pathlib.PurePosixPath(p["filename"]).name.replace(":","%3A")
 member=("complete-inputs/apt-extra-archives/" if p["name"] in extra else "foundation-apt-inputs/apt-archives/")+basename
 actual=by_path[member]
 assert actual["bytes"]==p["bytes"] and actual["sha256"]==p["sha256"]
 archives.append({"name":p["name"],"version":p["version"],"architecture":p["architecture"],"member":member,
  "bytes":actual["bytes"],"sha256":actual["sha256"]})
setup=load("COMPLETE-APT-SETUP.json");component=load("COMPLETE-COMPONENT-RESULT.json")
runtime=load("COMPLETE-RUNTIME-RESULT.json");exit_result=load("COMPLETE-EXIT.json")
assert component["apt_setup_sha256"]==sha(raw("COMPLETE-APT-SETUP.json"))
assert setup["status"]=="passed" and setup["stage"]=="complete"
assert setup["verified_archive_count"]==142 and setup["compiler_installed"] is False
requests={p["name"]:p["version"] for p in lock["apt_install"]}
assert len(requests)==19 and setup["plan"]["packages"]==requests and setup["plan"]["removals"] is False
assert set(setup["only_installed_or_reinstalled"])==set(requests)
parsed={}
for line in raw("complete-extra-apt-plan.stdout.log").decode().splitlines():
 assert not line.startswith("Remv ")
 if line.startswith("Inst "):
  match=re.match(r"^Inst ([a-z0-9+.-]+)(?::[a-z0-9-]+)? (?:\[[^\]]+\] )?\((\S+)",line)
  assert match
  name,version=match.groups()
  assert name not in parsed
  parsed[name]=version
assert parsed==requests
for label,process in (("complete-extra-apt-plan",setup["plan"]["process"]),("complete-extra-apt-install",setup["install"])):
 assert process["exit_code"]==0
 for stream in ("stdout","stderr"):assert sha(raw(label+"."+stream+".log"))==process[stream+"_sha256"]
assert "--no-download" in setup["install"]["command"] and "APT::Get::AllowUnauthenticated=false" in setup["install"]["command"]
before=load("COMPLETE-APT-BEFORE.json");after=load("COMPLETE-APT-AFTER.json");expected=copy.deepcopy(before)
for p in lock["apt_install"]:expected[p["name"]]={"version":p["version"],"architecture":p["architecture"],"status":"installed"}
assert after==expected
assert setup["inherited_gmp"]["status"]=="verified-already-installed" and setup["inherited_gmp"]["installed_or_upgraded"] is False
signed=load("complete-signed-snapshot/RESULT.json")
assert signed["status"]=="passed" and signed["authority"]=="native APT configured trust store"
assert signed["archive_count"]==122 and signed["insecure_repository_exceptions"] is False and signed["acquired_index_bytes_equal"] is True
assert setup["signed_snapshot"]["receipt_sha256"]==sha(raw("complete-signed-snapshot/RESULT.json"))
assert setup["signed_snapshot"]["active_config_sha256"]==sha(raw("complete-signed-snapshot/frozen.conf"))
for name,key in (("InRelease","inrelease_sha256"),("Packages.gz","packages_gz_sha256")):
 assert by_path["complete-signed-snapshot/"+name]["sha256"]==signed[key]
 assert by_path["NEUTTS-FROZEN-APT/"+name]["sha256"]==signed[key]
config=raw("complete-signed-snapshot/frozen.conf").decode()
for line in ('Acquire::AllowInsecureRepositories "false";','Acquire::AllowDowngradeToInsecureRepositories "false";',
 'Acquire::AllowWeakRepositories "false";','APT::Get::AllowUnauthenticated "false";'):
 assert config.splitlines().count(line)==1
pip=component["raw_pip"]
assert pip["exit_code"]==1 and pip["pip_check_passed"] is False and pip["requirements_have_no_missing_or_conflicting_dependencies"] is True
assert pip["sha256"]==sha(raw("RAW-PIP-CHECK.log")) and pip["text"]==raw("RAW-PIP-CHECK.log").decode()
assert {p["name"] for p in pip["original_apt_tag_diagnostics"]}==set(apt_by_name)
for p in pip["original_apt_tag_diagnostics"]:
 assert p["metadata_modified"] is False and p["supported_tags_modified"] is False
assert len(pip["text"].splitlines())==11
offline=load("COMPLETE-NETWORK-OFFLINE.json");inspection=load("COMPLETE-DISCONNECTED-CONTAINER.json")
image=load("COMPLETE-SOURCE-IMAGE.json");cid=raw("COMPLETE-CONTAINER-ID.txt").decode().strip()
assert len(inspection)==len(image)==1 and re.fullmatch("[0-9a-f]{64}",cid)
assert inspection[0]["Id"]==offline["container_id"]==cid and offline["container"]==inspection[0]
assert offline["inspect_sha256"]==sha(raw("COMPLETE-DISCONNECTED-CONTAINER.json"))
assert offline["remaining_networks"]==inspection[0]["NetworkSettings"]["Networks"]=={}
assert inspection[0]["State"]["Running"] is True and inspection[0]["Image"]==image[0]["Id"]
assert offline["lock_sha256"]==sha(lock_bytes)
assert inspection[0]["HostConfig"]["NanoCpus"]==2000000000
assert inspection[0]["HostConfig"]["Memory"]==6442450944 and inspection[0]["HostConfig"]["PidsLimit"]==512
assert inspection[0]["Config"]["User"]=="1000:1000"
for report in (component,runtime):
 assert report["network"]["host_receipt_sha256"]==sha(raw("COMPLETE-NETWORK-OFFLINE.json"))
 assert report["network"]["status"]=="verified-disconnected" and report["network"]["interfaces"]==[[1,"lo"]]
 assert report["network"]["network_connections_available"] is False
 assert report["source_image"]["input_receipt_sha256"]==sha(raw("COMPLETE-PROBE-INPUTS.json"))
 assert report["source_image"]["inspection_sha256"]==sha(raw("COMPLETE-SOURCE-IMAGE.json"))
 assert report["source_image"]["docker_image_id"]==image[0]["Id"]
 for flag in lock["boundaries"]:assert report[flag] is False
assert exit_result["exit_code"]==1 and exit_result["stage"]=="isolated-public-complete-runtime"

assert runtime["stage"]=="complete_dependency_integration" and runtime["status"]=="failed"
assert runtime["error"]["type"]=="ImportError" and "torchao not installed." in runtime["error"]["message"]
stderr=raw("complete-public-runtime.stderr.log").decode()
assert "ModuleNotFoundError: No module named 'torch._inductor.kernel.flex_attention'" in stderr
assert "from torch._inductor.kernel.flex_attention import construct_strides, maybe_realize" in stderr
assert runtime["error"]["message"] in stderr
assert by_path["COMPLETE-RUNTIME-RESULT.json"]["sha256"]=="0ac652f13cbc2bee7d92321d7399c3433d775133dda824e91e77304a61ac7d53"
assert by_path["complete-public-runtime.stderr.log"]["sha256"]=="0dec614b186dc830e67dfdd11efce8a91d073e203d2e5fcc2fdaa960cdfa1f69"
missing_final=["native_mappings","installed_after","record_integrity_after","network_after"]
assert all(k not in runtime for k in missing_final)
assert "COMPLETE-NATIVE-MAPPINGS.json" not in by_path
assert component["foundation"]["case_count"]==7 and component["foundation"]["status"]=="passed"
assert component["foundation"]["sha256"]==sha(raw("NEUTTS-CORE-RESULT.json"))
installed=runtime["installed_before"]
assert installed["status"]=="passed" and installed["actual_visible_distribution_count"]==116
assert installed["actual_names"]==lock["names"] and installed["verified_site_files"]==29140
assert installed["declared_metadata_modified"] is False and installed["global_site_visible"] is False
distributions=installed["distributions"]
assert len(distributions)==len({p["name"] for p in distributions})==116
assert sorted(p["name"] for p in distributions)==lock["names"]
for p in distributions:
 if p["name"] in expected_wheels:
  q=expected_wheels[p["name"]]
  assert p["authority"]=="exact verified wheel" and p["wheel_sha256"]==q["artifact"]["sha256"]
  assert p["version"]==q["version"] and p["verified_file_count"]>0
 else:
  q=apt_by_name[p["name"]]
  assert p["authority"]=="complete exact APT Python payload copy" and p["version"]==q["version"]
  assert p["files"]==q["file_count"] and p["bytes"]==q["bytes"]
  assert p["original_metadata_sha256"]==q["metadata_sha256"]
  assert p["metadata_modified"] is False and p["original_tags"]==q["distribution"]["wheel_tags"]
records=runtime["record_integrity_before"]
assert records=={"status":"passed","record_rows":13818,"wheel_count":105,"original_apt_records_modified":False}
closure=runtime["closure"]
assert closure["status"]=="passed" and closure["node_count"]==116 and closure["active_edge_count"]==183
assert closure["selected_extras"]==lock["selected_extras"]=={"fsspec":["http"]}
for k in ("metadata_modified","global_site_visible","neutts_engine_installed"):assert closure[k] is False
env=closure["actual_marker_environment"]
assert env["sys_platform"]=="android" and env["platform_machine"]=="aarch64" and env["python_full_version"]=="3.14.6"

# The exact executed source establishes order and that the final checks follow all operations.
probe_name="scripts/compatibility_probe_neutts_complete_runtime.py"
probe_source=subprocess.check_output(["git","-C",str(ROOT),"show",HEAD+":"+probe_name])
assert sha(probe_source)==next(p["sha256"] for p in binding["sources"] if p["path"]==probe_name)
tree=ast.parse(probe_source)
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="runtime_case")
case_assignment=next(n for n in ast.walk(function) if isinstance(n,ast.Assign)
 and any(isinstance(t,ast.Name) and t.id=="cases" for t in n.targets))
operation_order=[ast.literal_eval(e.elts[0]) for e in case_assignment.value.elts]
expected_order=["foundation_and_audio","nonrust","hf_xet","safetensors","tokenizers","hub_http_yaml","tiktoken","phonemizer","llama_cpu","perth_public_watermark","complete_dependency_integration"]
assert operation_order==expected_order
ops=runtime["operations"]
assert set(ops)==set(expected_order[:-1]) and len(ops)==10
for name,result in ops.items():
 if name=="nonrust":
  assert len(result)==3 and all(p["status"]=="passed" for p in result)
 else:assert result["status"]=="passed"
text=probe_source.decode()
assert text.index('report["installed_before"] = nr.installed_inventory')<text.index('operations = report["operations"] = {}')
assert text.index('operations[name] = operation()')<text.index('report["native_mappings"] = native_mappings')
assert text.index('report["native_mappings"] = native_mappings')<text.index('report["installed_after"] = nr.installed_inventory')

aux=ops["foundation_and_audio"]
assert aux["numba_nopython_result"]==14 and aux["jit_disabled"] is False
assert aux["torchaudio_resample_shape"]==[1,32] and aux["scikit_learn_prediction"]==[0,2]
assert aux["audioop_max"]==400 and aux["cffi_sum"]==10 and aux["msgpack_roundtrip"] is True
assert aux["libyaml_parser"] is True and aux["markup_escape"] is True and aux["charset_mess_ratio"]==0
nr={p["component"]:p["checks"] for p in ops["nonrust"]}
assert set(nr)=={"pycryptodomex","pandas","sentencepiece"}
assert nr["pycryptodomex"]["invalid_tag_rejected"] is True and nr["pycryptodomex"]["raw_loader_backend"]=="cffi"
for k in ("aes128_standard_vector","aes_gcm_roundtrip","modular_inverse","sha256_standard_vector"):assert nr["pycryptodomex"][k]=="passed"
for k in ("group_reduction","join","leap_day_datetime","numpy_interchange","unicode_strings"):assert nr["pandas"][k]=="passed"
assert nr["pandas"]["pandas_version"]=="3.0.6" and nr["pandas"]["numpy_version"]=="2.5.4"
sp=nr["sentencepiece"]
assert sp["model_downloaded"] is False and sp["synthetic_tokenizer_created"] is True and sp["piece_count"]==64
for k in ("serialized_model","standard_unicode_normalization","tokenizer_roundtrip","trainer"):assert sp[k]=="passed"
assert sp["synthetic_model_bytes"]==241019 and sp["synthetic_model_sha256"]=="e24084db010cad2ac043420e166cb47b47a5c0129fcff0fc80bd0a3c0f2afe72"
hf=ops["hf_xet"]
assert hf["version"]=="1.6.0" and hf["bytes"]==3298 and hf["model_downloaded"] is False
assert hf["original_hash"]=="1b4e70abede390e386c1a7d117049d06daa16bead4dbacf12039c53b77be7b64"
assert hf["changed_hash"]=="fa4185c0998c83ae69142251a3a876a7d025a66f42547ed2daa620a7d948e760"
st=ops["safetensors"]
assert st["version"]=="0.8.0" and st["serialization_api"]=="TensorSpec" and st["backing_buffer_retained"] is True
assert st["dtype"]=="F32" and st["shape"]==[2,2] and st["values"]==[0.25,-1.5,3,42]
assert st["file_sha256"]==st["serialized_sha256"]=="9705c6922502b9d4c5a78d3e270a1ddb3b556e73ec7b6dc5fef7711c6ff12629"
assert {p["case"] for p in st["corrupt_inputs_rejected"]}=={"truncated-header","truncated-payload","invalid-header"}
assert st["numpy_or_torch_dependency_not_requested"] is True
tok=ops["tokenizers"];wp=tok["wordpiece"]
assert tok["version"]=="0.22.2" and tok["model_downloaded"] is False
assert wp["actual_ids"]==wp["expected_ids"]==[1,3,5,6,7,8,9,2] and wp["batch_count"]==64
assert wp["pair_ids"]==[1,3,2,4,2] and wp["pair_type_ids"]==[0,0,0,1,1]
assert tok["byte_bpe"]=={"batch_count":80,"training_rows":20,"unicode_round_trips":6,"vocab_size":280}
deps=ops["hub_http_yaml"]
assert deps["model_downloaded"] is False and deps["gated_weights_requested"] is False
assert deps["hub"]["version"]=="1.31.0" and deps["hub"]["local_only_cache_miss"]=="LocalEntryNotFoundError"
assert deps["http"]["loopback_only"] is True
assert deps["http"]["requests"]==[{"method":"GET","path":"/fixture.json"},{"method":"HEAD","path":"/fixture.json"},{"method":"GET","path":"/fixture.json"}]
assert deps["http"]["body_sha256"]=="1160559c6dd4e46e608fb7a427a349401332bc2766641c01f9ad1a16cc9673f0"
assert deps["pyyaml"]["actual_c_api"] is True and deps["pyyaml"]["version"]=="6.0.3"
tik=ops["tiktoken"]
assert tik["native_core_type"]=="CoreBPE" and tik["vocabulary_entries"]==258 and tik["batch_threads"]==2
assert tik["network_vocabulary_downloaded"] is False and tik["default_special_token_rejected"] is True
assert len(tik["fixed_examples"])==6 and all(p["actual_tokens"]==p["expected_tokens"] for p in tik["fixed_examples"])
for k in ("allowed_special_token","binary_single_token_apis","local_dependency_operations","regex_unicode_graphemes"):assert tik[k]=="passed"
assert tik["request_url"]=="https://xn--bcher-kva.example/ab?q=a+b"
ph=ops["phonemizer"];life=ph["gate_only_lifetime_instrumentation"]
assert ph["public_output"]=="h\u0259l\u02c8o\u028a" and ph["without_stress"]=="h\u0259lo\u028a"
assert ph["data_files"]==371 and ph["model_downloaded"] is False and ph["engine_installed"] is False
assert ph["rpds"]==ph["xxhash"]=="passed"
assert life["kind"]=="bounded-original-constructor-profile-return-retention"
assert life["constructor_calls"]==life["retained_instances"]==len(ph["library_copies"])==9
assert life["maximum_instances"]==32 and life["package_source_changed"] is False and life["public_api_replaced"] is False
assert life["prior_profile_restored"] is True
assert life["retained_until"]=="complete-native-mapping-verification"
for p in ph["library_copies"]:
 assert p["bytes"]==1245128 and p["sha256"]=="21f4f416325fb3a9d6de07553cb9b9ea53973e9e2d9d008d02e34614732c2a55"
llama=ops["llama_cpu"]
assert llama["inference_tested"] is False and llama["model_loaded"] is False
assert llama["default_context"]=={"n_batch":2048,"n_ctx":512,"n_threads":4}
perth=ops["perth_public_watermark"]
assert perth["checkpoint_sha256"]=="a15bce457ebc53ce5e6c9c3f11df78cf7ee2bf9cdab0a798902135b4c4027670"
assert perth["actual_state_tensor_count"]==59 and perth["checkpoint_step"]==250000
for k in ("injected_original_model","public_bundled_watermark_checkpoint_executed","strict_state_dict","weights_only"):assert perth[k] is True
assert perth["map_location"]=="cpu" and perth["default_speech_model_downloaded"] is False
assert perth["public_class"]=="perth.PerthImplicitWatermarker"
assert perth["soundfile_ctypes_lookup"] is None and perth["soundfile_library"]=="libsndfile.so" and perth["libsndfile_version"]=="1.2.2"
assert [p["sample_rate"] for p in perth["operations"]]==[24000,32000]
for p in perth["operations"]:
 assert p["samples"]==p["sample_rate"] and p["dtype"]=="float32"
 assert p["input_unchanged"] is True and p["output_changed"] is True and p["quality_threshold_asserted"] is False
 assert math.isfinite(p["max_absolute_delta"]) and p["max_absolute_delta"]>0
 assert p["waveform_sha256"]!=p["watermarked_sha256"]
 for result in p["confidence"].values():
  assert math.isfinite(result["confidence"]) and 0<=result["confidence"]<=1 and result["rounded"]==0

# Independently bind selected reported native origins and the failed source imports to actual verified wheels.
archive=zipfile.ZipFile(BASE/"artifact.zip")
wheel_cache={}
def wheel_member(package,name):
 p=expected_wheels[package];archive_name="complete-inputs/wheels/"+p["artifact"]["filename"]
 if package not in wheel_cache:
  data=archive.read(archive_name)
  assert len(data)==p["artifact"]["bytes"] and sha(data)==p["artifact"]["sha256"]
  wheel_cache[package]=zipfile.ZipFile(io.BytesIO(data))
 z=wheel_cache[package];assert z.namelist().count(name)==1
 info=z.getinfo(name);assert not info.is_dir() and info.file_size<=16*1024*1024
 data=z.read(name);assert len(data)==info.file_size
 return data
origins=[]
for package,record in [
 ("hf-xet",hf["origin"]),("safetensors",st["origin"]),("tokenizers",tok["native_origin"]),
 ("tokenizers",tok["python_origin"]),("pyyaml",deps["pyyaml"]["native_origin"]),
 ("huggingface-hub",deps["hub"]["origin"]),("httpx",deps["http"]["httpx_origin"]),
 ("aiohttp",deps["http"]["aiohttp_origin"]),("fsspec",deps["http"]["fsspec_origin"])]:
 parts=record["path"].split("/site-packages/")
 assert len(parts)==2
 member=parts[1];data=wheel_member(package,member)
 assert len(data)==record["bytes"] and sha(data)==record["sha256"]
 origins.append({"package":package,"wheel_sha256":expected_wheels[package]["artifact"]["sha256"],
 "member":member,"bytes":len(data),"sha256":sha(data)})
actual_ph=wheel_member("phonemizer","phonemizer/backend/espeak/api.py")
assert len(actual_ph)==life["original_source"]["bytes"] and sha(actual_ph)==life["original_source"]["sha256"]
assert life["original_source"]["wheel_sha256"]==expected_wheels["phonemizer"]["artifact"]["sha256"]
einx=next(p for p in distributions if p["name"]=="einx")
assert einx["wheel_sha256"]=="f64866a6ebfd6e0549f05d13c3230227f11eaa88880e72da57ba2314bef5a8dc"
assert len(einx["verified_external_data"])==1
external=einx["verified_external_data"][0]
assert external["path"].endswith("/share/doc/einx-0.4.3/source/conf.py")
assert external["sha256"]=="386f1a451b02667af9c1b3337bbad94972c4031af9a1f757b7186a33e587dcd2"
imports=[]
for package,name in [
 ("torchao","torchao/prototype/inductor/int8_sdpa_lowering.py"),("torchtune","torchtune/__init__.py")]:
 data=wheel_member(package,name)
 if package=="torchao":assert b"from torch._inductor.kernel.flex_attention import construct_strides, maybe_realize" in data
 else:assert b"import torchao" in data and b"torchao not installed." in data
 folder=DEST/"failure-import"/package;folder.mkdir(parents=True,exist_ok=True)
 path=folder/pathlib.PurePosixPath(name).name
 if path.exists():assert path.read_bytes()==data
 else:path.write_bytes(data)
 imports.append({"package":package,"version":expected_wheels[package]["version"],"member":name,
 "wheel_sha256":expected_wheels[package]["artifact"]["sha256"],"bytes":len(data),"sha256":sha(data),
 "retained_path":path.relative_to(DEST).as_posix()})
save("FAILED-IMPORT-SOURCE-BINDINGS.json",jbytes({"source_commit":HEAD,"run_id":39456043425,
 "original_import_members":imports,"no_source_imported_or_executed_by_review":True}))

review={
 "schema":"fully-verified-native-failure-review/v1","status":"verified-failure","run_id":39456043425,"job_id":118743063748,
 "executed_source_commit":HEAD,"artifact":{"id":12280522718,"bytes":proof["bytes"],"sha256":proof["sha256"],
 "whole_archive_verified":True,"member_count":proof["member_count"],"all_member_crc_size_sha256_verified":True,
 "uncompressed_bytes":proof["uncompressed_bytes"],"inventory_gzip_sha256":proof["inventory_gzip_sha256"]},
 "source_binding":{"status":binding["status"],"source_count":binding["source_count"],"source_bytes":binding["source_bytes"],
 "receipt":"EXECUTED-SOURCE-BINDINGS.json","sha256":sha((DEST/"EXECUTED-SOURCE-BINDINGS.json").read_bytes())},
 "failure":{"stage":"complete_dependency_integration","outer_stage":"complete-native-runtime","container_exit_code":1,
 "reported_error":runtime["error"],
 "underlying_error":{"type":"ModuleNotFoundError","message":"No module named 'torch._inductor.kernel.flex_attention'"},
 "diagnosis":"The installed Torchtune initializer imports the installed TorchAO. TorchAO's prototype Inductor lowering imports a missing pinned-Torch module; Torchtune wraps that ModuleNotFoundError as 'torchao not installed'. Exact installed inventory proves TorchAO is present. This does not establish the success of any subsequent import repair.",
 "native_operation_groups_completed":10,"native_operation_groups_total":11,
 "source_operation_order":operation_order,"completed_in_source_order":operation_order[:-1],
 "complete_integration_result_recorded":False,
 "first_installed_inventory_completed":True,"first_record_integrity_completed":True,"native_declared_closure_validated":True,
 "native_mapping_provenance_reached":False,"after_inventory_reached":False,"after_record_integrity_reached":False,
 "final_network_recheck_reached":False,"missing_final_receipts":missing_final,
 "trace_source_members":imports,"retry_success_claimed":False},
 "completed_setup":{"foundation_cases_passed":binding["foundation_cases_verified"],
 "original_signed_apt_authentication_recorded":True,"apt_archive_count":142,"extra_install_count":19,
 "extra_install_plan_matches_original_pins":True,"before_after_package_inventory_matches_exact_plan":True,
 "compiler_installed":False,"inherited_gmp_verified_without_install":True,
 "input_node_count":116,"input_edge_count":183,"selected_extras":lock["selected_extras"],
 "prepared_wheel_count":105,"copied_apt_python_payload_count":11,
 "installation_manifest_retained":True,
 "wheel_artifact_size_sha256_matches_executed_lock":wheels,
 "apt_archive_size_sha256_matches_original_pins":archives,
 "copied_apt_payload_manifest_matches_original_lock":True,
 "copy_receipts_preserve_original_metadata_and_record":True,
 "foundation_support_outside_graph":["pip","torchcodec"]},
 "native_before_checks":{"visible_distributions":116,"verified_site_files":29140,"record_rows":13818,"wheel_records":105,
 "declared_closure":closure,"declared_metadata_modified":False,"original_apt_records_modified":False,
 "global_site_visible":False,"all_reported_distribution_hashes_or_copy_manifests_match":True,
 "einx_external_documentation_receipt":einx,
 "these_pre_operation_receipts_do_not_replace_final_after_checks":True},
 "completed_operations":ops,
 "reported_operation_origins_independently_matched_to_exact_wheel_members":origins,
 "scope_limits":{"complete_dependency_gate_passed":False,
 "ten_operation_results_do_not_establish_final_mapping_or_after_integrity":True,
 "llama_model_loaded":False,"llama_inference_tested":False,
 "perth_inputs":"deterministic one-second float32 mono synthetic audio at 24000 and 32000 Hz",
 "perth_model":"original public bundled watermark checkpoint; safe CPU weights-only strict state load",
 "perth_quality_threshold_asserted":False,"perth_rounded_confidences_all_zero":True,
 "speech_model_synthesis_tested":False,"physical_device_or_audio_certified":False,
 "phonemizer_retention_target_recorded_but_final_mapping_step_not_reached":True},
 "raw_pip":{"exit_code":1,"passed":False,"original_tag_diagnostic_count":11,
 "requirements_missing_or_conflicting":False,"original_metadata_or_supported_tags_modified":False,"sha256":pip["sha256"]},
 "offline_boundary":{"exact_container_id_and_inspection_match":True,"remaining_networks":{},
 "native_child_interfaces":[[1,"lo"]],"network_connections_available":False,
 "cpus":2,"memory_bytes":6442450944,"pids":512,"uid":1000,
 "loopback_fixture_http_used":True,"final_network_recheck_reached":False,
 "receipt_sha256":sha(raw("COMPLETE-NETWORK-OFFLINE.json"))},
 "previous_failure_evidence":{"freezes":binding["previous_failure_freezes"],
 "all_185_frozen_files_unchanged":True,"separate_failure_audits_preserved":True},
 "excluded_engine":lock["excluded_engine"],
 "new_native_operations_executed_by_this_review":False,"new_tests_executed_by_this_review":False,
 "default_speech_model_downloaded":False,"neutts_engine_installed":False,
 "production_admission_changed":False,"release_output":False,
 "key_original_receipts":[{"path":name,"bytes":len(raw(name)),"sha256":sha(raw(name))} for name in
 ["COMPLETE-COMPONENT-RESULT.json","COMPLETE-RUNTIME-RESULT.json","COMPLETE-APT-SETUP.json",
 "COMPLETE-PROBE-INPUTS.json","COMPLETE-EXIT.json","complete-public-runtime.stderr.log",
 "complete-runtime-installed-closure.json","complete-inputs/COMPLETE-PREPARED-INPUTS.json"]]
}
assert len(binding["previous_failure_files_unchanged"])==185
assert binding["exact_executed_preparer_has_safe_relative_definition"] is True
meta=save("NATIVE-FAILURE-REVIEW.json",jbytes(review))
save("REVIEW-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"verified-failure","review":meta,"sources":len(binding["sources"]),
 "wheel_artifacts":len(wheels),"apt_archives":len(archives),"native_operation_groups_completed":10,
 "final_native_provenance_reached":False}))
