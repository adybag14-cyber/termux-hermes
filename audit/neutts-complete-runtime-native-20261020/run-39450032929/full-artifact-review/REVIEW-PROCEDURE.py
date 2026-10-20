"""Interpret the fully verified first complete-runtime failure; no target execution."""
import copy,gzip,hashlib,json,pathlib,re,subprocess,sys
ROOT=pathlib.Path(sys.argv[1]); BASE=pathlib.Path(sys.argv[2])
DEST=ROOT/"audit/neutts-complete-runtime-native-20261020/run-39450032929/full-artifact-review"
ART=DEST/"artifact"
HEAD="88e2810572a85f1050909ee8373527e983927766"
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
assert binding["source_count"]==115 and binding["head_sha"]==HEAD
inventory=json.loads(gzip.decompress((DEST/"FULL-MEMBER-INVENTORY.json.gz").read_bytes()))
by_path={r["path"]:r for r in inventory}
lock_bytes=raw("complete-inputs/neutts_complete_runtime_lock.json")
assert sha(lock_bytes)=="883d0fec890062f93eee763e8c89dfae7deba29970a376c6b951e5fc0b0aa1b5"
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
assert runtime["stage"]=="inputs" and runtime["status"]=="failed"
assert runtime["error"]=={"type":"AttributeError","message":"module '_complete_preparation' has no attribute 'safe_relative'"}
assert "operations" not in runtime and "native_mappings" not in runtime and "closure" not in runtime
assert "COMPLETE-NATIVE-MAPPINGS.json" not in by_path
assert component["foundation"]["case_count"]==7 and component["foundation"]["status"]=="passed"
assert component["foundation"]["sha256"]==sha(raw("NEUTTS-CORE-RESULT.json"))
review={
 "schema":"fully-verified-native-failure-review/v1","status":"verified-failure","run_id":39450032929,"job_id":118722085474,
 "executed_source_commit":HEAD,"artifact":{"id":12278206483,"bytes":proof["bytes"],"sha256":proof["sha256"],
 "whole_archive_verified":True,"member_count":proof["member_count"],"all_member_crc_size_sha256_verified":True,
 "uncompressed_bytes":proof["uncompressed_bytes"],"inventory_gzip_sha256":proof["inventory_gzip_sha256"]},
 "source_binding":{"status":binding["status"],"source_count":binding["source_count"],"source_bytes":binding["source_bytes"],
 "receipt":"EXECUTED-SOURCE-BINDINGS.json","sha256":sha((DEST/"EXECUTED-SOURCE-BINDINGS.json").read_bytes())},
 "failure":{"stage":"inputs","outer_stage":"complete-native-runtime","container_exit_code":1,
 "error":runtime["error"],"native_operation_groups_reached":0,"first_installed_inventory_completed":False,
 "native_runtime_closure_validated":False,"native_mapping_provenance_reached":False,
 "diagnosis":"Exact executed preparation module omitted the safe_relative adapter required by the unchanged shared installed-wheel inventory; failure occurred before operations and runtime closure validation.",
 "source_trace":["compatibility_probe_neutts_complete_runtime.py:542 runtime_case",
 "compatibility_probe_neutts_nonrust.py:458 installed_inventory",
 "compatibility_probe_neutts_nonrust.py:379 installed_wheel_bytes -> prep.safe_relative"],
 "retry_success_claimed":False},
 "completed_setup":{"foundation_cases_passed":binding["foundation_cases_verified"],
 "original_signed_apt_authentication_recorded":True,"apt_archive_count":142,"extra_install_count":19,
 "extra_install_plan_matches_original_pins":True,"before_after_package_inventory_matches_exact_plan":True,
 "compiler_installed":False,"inherited_gmp_verified_without_install":True,
 "input_node_count":116,"input_edge_count":183,"selected_extras":lock["selected_extras"],
 "prepared_wheel_count":105,"copied_apt_python_payload_count":11,
 "installation_manifest_retained":True,
 "input_graph_is_not_a_completed_runtime_closure_proof":True,
 "wheel_artifact_size_sha256_matches_original_lock":wheels,
 "apt_archive_size_sha256_matches_original_pins":archives,
 "copied_apt_payload_manifest_matches_original_lock":True,
 "copy_receipts_preserve_original_metadata_and_record":True,
 "foundation_support_outside_graph":["pip","torchcodec"]},
 "raw_pip":{"exit_code":1,"passed":False,"original_tag_diagnostic_count":11,
 "requirements_missing_or_conflicting":False,"original_metadata_or_supported_tags_modified":False,
 "sha256":pip["sha256"]},
 "offline_boundary":{"exact_container_id_and_inspection_match":True,"remaining_networks":{},
 "native_child_interfaces":[[1,"lo"]],"network_connections_available":False,
 "cpus":2,"memory_bytes":6442450944,"pids":512,"uid":1000,
 "receipt_sha256":sha(raw("COMPLETE-NETWORK-OFFLINE.json"))},
 "historical_partial_evidence":{"commit":binding["historical_diagnostic_commit"],
 "all_eight_original_files_unchanged":True,"four_partial_members_match_whole_archive":True,
 "old_partial_verification_claims_preserved_as_historical":True},
 "excluded_engine":lock["excluded_engine"],
 "new_native_operations_executed_by_this_review":False,"new_tests_executed_by_this_review":False,
 "default_speech_model_downloaded":False,"neutts_engine_installed":False,
 "production_admission_changed":False,"release_output":False,
 "key_original_receipts":[{"path":name,"bytes":len(raw(name)),"sha256":sha(raw(name))} for name in
 ["COMPLETE-COMPONENT-RESULT.json","COMPLETE-RUNTIME-RESULT.json","COMPLETE-APT-SETUP.json",
 "COMPLETE-PROBE-INPUTS.json","COMPLETE-EXIT.json","complete-public-runtime.stderr.log",
 "complete-runtime-installed-closure.json","complete-inputs/COMPLETE-PREPARED-INPUTS.json"]]
}
meta=save("NATIVE-FAILURE-REVIEW.json",jbytes(review))
save("REVIEW-PROCEDURE.py",pathlib.Path(__file__).read_bytes())
print(json.dumps({"status":"verified-failure","review":meta,"sources":len(binding["sources"]),
 "wheel_artifacts":len(wheels),"apt_archives":len(archives),"native_operation_groups_reached":0}))
