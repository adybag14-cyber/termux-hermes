from pathlib import Path
import copy,hashlib,importlib.util,io,json,zipfile
base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
repo=base/"termux-hermes-next-stable-20261017"
out=base/"torchao-lazy-sdpa-preparation-20261017"
lock_path=repo/"scripts/neutts_torchao_component_lock.json"
old_raw=lock_path.read_bytes()
assert hashlib.sha256(old_raw).hexdigest()=="8c3303018c326f63540c59855df19d7fc3cef139040c90d64b4e7f4cbc264c22"
old=json.loads(old_raw);lock=copy.deepcopy(old)
lock["schema_version"]=2
lock["upstream_package"]=copy.deepcopy(old["package"])
lock["upstream_source_members"]=copy.deepcopy(old["source_members"])+[{"path":"torchao/prototype/inductor/fx_passes/__init__.py","bytes":211,"sha256":"f9f58d8c905a9de6ebf795a8b3b0c59ae056d12286d59279f908c0ed42456af4"}]
lock["source_members"]=copy.deepcopy(old["source_members"])+[{"path":"torchao/prototype/inductor/fx_passes/__init__.py","bytes":506,"sha256":"e3b00aac6fb639fe732f29468610e60bf85110982959f974d756ca79cd07f0b5"}]
lock["patch"]={"path":"patches/next-stable/torchao-lazy-sdpa.patch","input_filename":"torchao-lazy-sdpa.patch","bytes":697,"sha256":"28e786678ce02f007f77e5cc70a3e48faad1c72eea3dc0ec897c4ee0a89e74cc","member":"torchao/prototype/inductor/fx_passes/__init__.py","before_bytes":211,"before_sha256":"f9f58d8c905a9de6ebf795a8b3b0c59ae056d12286d59279f908c0ed42456af4","after_bytes":506,"after_sha256":"e3b00aac6fb639fe732f29468610e60bf85110982959f974d756ca79cd07f0b5","changed_members":["torchao/prototype/inductor/fx_passes/__init__.py","torchao-0.12.0.dist-info/RECORD"],"container_encoding":"ZIP_STORED, original member order and permissions, fixed 1980-01-01 timestamp, explicit Unix creator"}
lock["purpose"]="Unpublished standalone TorchAO CPU NF4 gate with one lazy optional SDPA import; original version and dependency metadata preserved"
prep_path=repo/"scripts/prepare_neutts_torchao.py"
spec=importlib.util.spec_from_file_location("_torchao_lazy_pin_generation",prep_path)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
upstream=base/"neutts-engine-root-preparation-20261017"/old["package"]["artifact"]["filename"]
raw=mod.patched_wheel_bytes(upstream,lock,repo/lock["patch"]["path"])
with zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(upstream) as original:
 assert len(z.infolist())==422 and z.namelist()==original.namelist()
 changed=[n for n in z.namelist() if z.read(n)!=original.read(n)]
 assert sorted(changed)==sorted(lock["patch"]["changed_members"])
 lock["package"]["artifact"]={"filename":old["package"]["artifact"]["filename"],"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
 lock["package"]["wheel"]["record_sha256"]=hashlib.sha256(z.read(old["package"]["wheel"]["record_member"])).hexdigest()
 lock["package"]["wheel"]["uncompressed_bytes"]=sum(i.file_size for i in z.infolist())
 lock["package"]["wheel"]["max_member_bytes"]=max(i.file_size for i in z.infolist())
 for member in (old["package"]["wheel"]["metadata_member"],old["package"]["wheel"]["wheel_member"]):
  assert z.read(member)==original.read(member)
 assert lock["operation"]==old["operation"] and lock["foundation"]==old["foundation"]
compiled=out/"candidate-wheel-v2"
compiled.mkdir(exist_ok=False)
candidate=compiled/lock["package"]["artifact"]["filename"]
with candidate.open("xb") as f:f.write(raw)
mod.verify_wheel(candidate,lock)
lock_bytes=(json.dumps(lock,sort_keys=True,indent=2)+"\n").encode()
lock_sha=hashlib.sha256(lock_bytes).hexdigest()
prep_text=prep_path.read_text(encoding="utf-8")
old_lock='LOCK_SHA256 = "8c3303018c326f63540c59855df19d7fc3cef139040c90d64b4e7f4cbc264c22"'
assert prep_text.count(old_lock)==1
new_prep=prep_text.replace(old_lock,'LOCK_SHA256 = "'+lock_sha+'"').encode()
prep_sha=hashlib.sha256(new_prep).hexdigest()
probe_path=repo/"scripts/compatibility_probe_neutts_torchao.py"
old_probe=probe_path.read_bytes()
assert hashlib.sha256(old_probe).hexdigest()=="b7a902a67784d211d471dd83ac7f7dc317b936d44b258bfaa13e77950720dd31"
old_prep_sha=b"0ebd003722f80b29b63e143da13c64627deb060b86ab67fdc8ea8d15d1bb5095"
assert old_probe.count(old_prep_sha)==1
new_probe=old_probe.replace(old_prep_sha,prep_sha.encode())
assert new_probe.replace(prep_sha.encode(),old_prep_sha)==old_probe
driver_path=repo/"scripts/compatibility_probe_neutts_torchao.sh"
driver=driver_path.read_bytes()
assert hashlib.sha256(driver).hexdigest()=="b03b20f85092e82b582df6b1108445d05b7f8ab6efed3e9f21ead18abdcaad1f"
new_driver=driver.replace(b'"scripts/prepare_neutts_torchao.py", "scripts/neutts_torchao_component_lock.json",\n',
 b'"scripts/prepare_neutts_torchao.py", "scripts/neutts_torchao_component_lock.json",\n         "patches/next-stable/torchao-lazy-sdpa.patch",\n')
new_driver=new_driver.replace(b'python3 -B "$packaging/scripts/prepare_neutts_torchao.py" --out "$out/torchao-inputs"',
 b'python3 -B "$packaging/scripts/prepare_neutts_torchao.py" \\\n    --patch "$packaging/patches/next-stable/torchao-lazy-sdpa.patch" --out "$out/torchao-inputs"')
assert new_driver!=driver and new_driver.count(b"torchao-lazy-sdpa.patch")==2
workflow_path=repo/".github/workflows/neutts-torchao-component.yml"
workflow=workflow_path.read_bytes()
assert hashlib.sha256(workflow).hexdigest()=="912e1e37d85a402581c9a4940a87fb53abba9ae202110a18a4bdaaf67fdf8858"
needle=b"      - 'scripts/neutts_torchao_component_lock.json'\n"
assert workflow.count(needle)==1
new_workflow=workflow.replace(needle,needle+b"      - 'patches/next-stable/torchao-lazy-sdpa.patch'\n")
for path,data in [(lock_path,lock_bytes),(prep_path,new_prep),(probe_path,new_probe),(driver_path,new_driver),(workflow_path,new_workflow)]:
 path.write_bytes(data)
 assert path.read_bytes()==data
pins=[]
for p in [lock_path,prep_path,probe_path,driver_path,workflow_path,repo/lock["patch"]["path"]]:
 pins.append({"path":p.relative_to(repo).as_posix(),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
receipt={"schema_version":1,"stage":"host-preparation-before-regressions-or-native-retry","wheel":lock["package"]["artifact"],"upstream_wheel":old["package"]["artifact"],"patch":lock["patch"],"changed_members":sorted(changed),"metadata_and_wheel_tag_members_unchanged":True,"five_case_native_gate_body_unchanged":True,"foundation_and_operation_locks_unchanged":True,"files":pins,"native_success_claimed":False,"release_output":False}
with (out/"implementation-v2-identities.json").open("x",encoding="utf-8",newline="\n") as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write("\n")
print(json.dumps(receipt,indent=2))
