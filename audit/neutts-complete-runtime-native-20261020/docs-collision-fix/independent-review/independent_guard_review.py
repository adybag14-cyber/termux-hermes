import hashlib,importlib.util,json,pathlib,sys,unittest,io
from pathlib import Path
repo=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017");base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\neutts-complete-runtime-preparation-20261020\independent-einx-install-review")
pins={
 "scripts/prepare_neutts_complete_runtime.py":("f12add142a48890c8933dc609d86f3e08105925cb0575bc07fee73d3eb9c4bc2",30800),
 "scripts/neutts_complete_runtime_lock.json":("0e4818b8da88237f3aacb79d0e0a928605b4851c5a1fb8e4613918142a9c7c19",4749683),
 "scripts/compatibility_probe_neutts_complete_runtime.py":("427190f97f384c744f1c4b6d7637d159e87c6f4ccaf32870d9a104946b8d4756",38591),
 "tests/test_neutts_complete_runtime.py":("e3d99f1acbe91f6e06b456b31abe1c66f326b226e4f49f99877164547bde6dcf",23186)}
def check():
 for p,(h,n) in pins.items():
  raw=(repo/p).read_bytes()
  assert len(raw)==n and hashlib.sha256(raw).hexdigest()==h,(p,"changed")
check()
spec=importlib.util.spec_from_file_location("_independent_complete_prep",repo/"scripts/prepare_neutts_complete_runtime.py")
prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
lock,raw=prep.load_lock()
assert hashlib.sha256(prep.einx_documentation_bytes(lock)).hexdigest()=="f64866a6ebfd6e0549f05d13c3230227f11eaa88880e72da57ba2314bef5a8dc"
prepared=repo.parent/"neutts-complete-runtime-preparation-20261020/prepared-inputs-v2"
targets=prep.validate_install_targets(prepared/"wheels",lock["packages"],lock["apt_python"])
assert targets["target_count"]==28936 and targets["duplicate_file_owners"]==0
assert targets["target_owners_sha256"]=="4747d5ed3ba3b909873cfa9b434f428611c465685746b689059fea4977988aa9"
class CountResult(unittest.TextTestResult):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.subtest_count=0
 def addSubTest(self,test,subtest,outcome):
  self.subtest_count+=1;super().addSubTest(test,subtest,outcome)
suite=unittest.defaultTestLoader.discover(str(repo/"tests"),pattern="test_neutts_complete_runtime.py")
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=CountResult).run(suite)
(base/"FROZEN-GUARD-TESTS.txt").write_text(stream.getvalue(),encoding="utf-8",newline="\n")
check()
receipt={"status":"passed" if result.wasSuccessful() else "failed","tests":result.testsRun,"subtests":result.subtest_count,"failures":len(result.failures),"errors":len(result.errors),"skips":len(result.skipped),"source_pins":{p:{"sha256":h,"bytes":n} for p,(h,n) in pins.items()},"full_original_graph_validation":"prep.load_lock validated original 116 distributions / 183 active edges without version or requirement changes","derivative_reconstruction_sha256":"f64866a6ebfd6e0549f05d13c3230227f11eaa88880e72da57ba2314bef5a8dc","all_actual_wheel_apt_installed_targets":targets,"source_review":{"single_einx_documentation_move_only":True,"metadata_version_runtime_and_license_payloads_preserved":True,"unified_prefix_relative_wheel_and_apt_namespace":True,"rejects_identical_or_differing_duplicate_owners":True,"rejects_file_directory_aliases":True,"derivative_verified_in_prepare_and_verify_inputs":True,"preflight_record_bound_into_prepared_receipt":True,"runtime_probe_only_changes_preparer_hash":True,"shared_runtime_byte_verifiers_unchanged":True},"limits":"Host packaging and exact source/input review; complete116 native retry remains required."}
raw=(json.dumps(receipt,indent=2,sort_keys=True)+"\n").encode();path=base/"INDEPENDENT-FROZEN-GUARD-REVIEW.json";path.write_bytes(raw)
print(json.dumps({"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"tests":result.testsRun,"subtests":result.subtest_count,"success":result.wasSuccessful()}))
if not result.wasSuccessful():print(stream.getvalue());sys.exit(1)
