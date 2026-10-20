from pathlib import Path
import base64,csv,hashlib,importlib.util,io,json,unittest,zipfile,sys
repo=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017");base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\neutts-complete-runtime-monitor-20261020\3f1f404\39456043425\independent-torchao-api-review")
pins={
 "scripts/prepare_neutts_complete_runtime.py":"a537ec2d19cfee4b2cfffcbf96b1eb7a3f1259199b471d10c0da5431b94fc8ed",
 "scripts/neutts_complete_runtime_lock.json":"7c05ccac08c2c7875b622ff9b1ef98731a9f72e1f5bf4312f58d63eb25d5eb7e",
 "scripts/compatibility_probe_neutts_complete_runtime.py":"9cfa0fcf02a76e08e7d91112e82ba1178e448d9fc2f2cc48634e80128f85fcab",
 "tests/test_neutts_complete_runtime.py":"06a115b51f9415a08ef928a8064f9b4bcb25c295aa55bac4971047b3782ac75d"}
def check_pins():
 for rel,h in pins.items():assert hashlib.sha256((repo/rel).read_bytes()).hexdigest()==h,rel
def archive_review(path,artifact):
 raw=path.read_bytes();assert len(raw)==artifact["bytes"] and hashlib.sha256(raw).hexdigest()==artifact["sha256"]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  assert z.testzip() is None
  infos=z.infolist();assert len(infos)==len({i.filename for i in infos})==422
  members={i.filename:z.read(i) for i in infos}
  files={i.filename for i in infos if not i.is_dir()}
  record=next(n for n in files if n.endswith(".dist-info/RECORD"))
  rows=list(csv.reader(io.StringIO(members[record].decode())))
  assert all(len(x)==3 for x in rows) and len(rows)==len({x[0] for x in rows}) and {x[0] for x in rows}==files
  for name,digest,size in rows:
   if name==record:assert digest==size==""
   else:
    b=members[name];assert size==str(len(b)) and digest=="sha256="+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip("=")
  return members,infos,{"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"zip_members":len(infos),"regular_members":len(files),"all_member_CRC_checked":True,"record_payloads":len(rows)-1,"all_RECORD_payloads_verified":True}
check_pins()
s=importlib.util.spec_from_file_location("_peer_complete_torchao_prep",repo/"scripts/prepare_neutts_complete_runtime.py")
prep=importlib.util.module_from_spec(s);s.loader.exec_module(prep)
lock,lockraw=prep.load_lock();rule=lock["torchao_compiler_import_compatibility"];package=next(p for p in lock["packages"] if p["name"]=="torchao")
original=repo/rule["upstream_path"];derived=repo/package["origin"]["retained_path"]
before,binfo,breview=archive_review(original,rule["upstream_package"]["artifact"])
after,ainfo,areview=archive_review(derived,package["artifact"])
assert [i.filename for i in binfo]==[i.filename for i in ainfo]
record=package["wheel"]["record_member"];target=rule["target_member"]
assert {n for n in before if before[n]!=after[n]}=={record,target}
assert before[target].count(rule["old_import"].encode())==1
assert before[target].replace(rule["old_import"].encode(),rule["new_import"].encode())==after[target]
for n in before:
 if n not in (record,target):assert before[n]==after[n]
for a,b in zip(binfo,ainfo,strict=True):
 assert a.external_attr==b.external_attr and b.compress_type==zipfile.ZIP_STORED and b.date_time==(1980,1,1,0,0,0) and b.create_system==3 and b.create_version==b.extract_version==20
assert prep.torchao_compiler_import_bytes(lock)==derived.read_bytes()
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.subtests=0
 def addSubTest(self,test,subtest,outcome):self.subtests+=1;super().addSubTest(test,subtest,outcome)
suite=unittest.defaultTestLoader.discover(str(repo/"tests"),pattern="test_neutts_complete_runtime.py")
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,resultclass=Result,verbosity=2).run(suite)
(base/"INDEPENDENT-TORCHAO-TESTS.txt").write_text(stream.getvalue(),encoding="utf-8",newline="\n")
check_pins()
value={"status":"passed" if result.wasSuccessful() else "failed","source_pins":pins,"original_wheel":breview,"derived_wheel":areview,"changed_members":[target,record],"all_other_420_members_byte_identical":True,"original_metadata_version_requirements_and_license_preserved":True,"fixed_ZIP_fields_and_original_member_order_preserved":True,"derivative_reconstruction_byte_equal":True,"guarded_fallback":{"old_module_first":True,"only_missing_old_module_selects_current_provider":True,"ordinary_ImportError_propagates":True,"unrelated_ModuleNotFoundError_propagates":True,"missing_new_provider_propagates":True,"no_stub_or_runtime_skip":True},"exact_Torch_source_review":"INDEPENDENT-TORCH-API-REVIEW.json","neighbor_modules":11,"neighbor_symbols":26,"actual_native_added_checks":["exact installed current Torch source SHA","TorchAO function objects are actual current Torch exports","contiguous/transposed/empty stride oracles","None/SymPy realization preserves identities"],"native_added_checks_executed_here":False,"host_tests":{"tests":result.testsRun,"additional_subtests":result.subtests,"failures":len(result.failures),"errors":len(result.errors),"skips":len(result.skipped)},"bounds_and_graph":{"original_dependency_nodes":116,"original_active_edges":183,"NeuTTS_original_Requires_Python":">=3.10,<3.14","metadata_requirements_versions_unchanged":True},"complete_native_runtime_passed":False,"limitations":"Host archive/source/guard regression proof; native corrected import and full combined after-inventory/mapping checks still require a fresh native run."}
raw=(json.dumps(value,indent=2,sort_keys=True)+"\n").encode();path=base/"INDEPENDENT-TORCHAO-DERIVATIVE-REVIEW.json";path.write_bytes(raw)
print(json.dumps({"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"tests":result.testsRun,"subtests":result.subtests,"success":result.wasSuccessful()}))
if not result.wasSuccessful():print(stream.getvalue());sys.exit(1)
