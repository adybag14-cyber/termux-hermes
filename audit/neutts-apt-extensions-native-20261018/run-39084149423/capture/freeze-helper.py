"""Freeze the successful five-extension native gate, preserving original evidence bytes."""
from pathlib import Path, PurePosixPath
import hashlib,json,zipfile
BASE=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
REPO=BASE/"termux-hermes-next-stable-20261017"
SRC=BASE/"apt-extensions-native-evidence-20261018/39084149423"
OUT=REPO/"audit/neutts-apt-extensions-native-20261018/run-39084149423"
HEAD="04fa547db8a7d12f701c7c4cc41a797a36df3f36"
ZIP_SHA="74fbf97e07d4ea91edcdd8f0e95c484ecb88fb31dadac650ee7e401d0a61b754"
LOCK_SHA="52db5e627cf575312d8011b6c000feb0f6075f7266981a1ed5bda68319f42ac3"
IMAGE="termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303"
def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(rel): return json.loads((SRC/"extracted"/rel).read_bytes())
def identity(rel):
    raw=(SRC/"extracted"/rel).read_bytes()
    return {"path":rel,"bytes":len(raw),"sha256":sha(raw)}
def save(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): assert path.read_bytes()==raw,str(path)
    else:
        with path.open("xb") as f: f.write(raw)
    assert path.read_bytes()==raw
pending={}
def retain(rel,raw,source):
    p=PurePosixPath(rel)
    assert not p.is_absolute() and ".." not in p.parts and rel not in pending
    pending[rel]=(raw,source)

vraw=(SRC/"verified-artifact.json").read_bytes();v=json.loads(vraw)
assert (v["run_id"],v["job_id"],v["head_sha"],v["artifact_id"],v["conclusion"])==(39084149423,117547090041,HEAD,12120445637,"success")
zipraw=(SRC/"artifact.zip").read_bytes()
assert len(zipraw)==v["artifact_bytes"]==16304126 and sha(zipraw)==v["artifact_sha256"]==ZIP_SHA
assert len(v["members"])==139 and v["all_member_crc_verified"]
run=json.loads((SRC/"run-api.json").read_bytes())
jobs=json.loads((SRC/"jobs-api.json").read_bytes())["jobs"]
artifacts=json.loads((SRC/"artifacts-api.json").read_bytes())["artifacts"]
assert run["id"]==v["run_id"] and run["head_sha"]==HEAD and run["conclusion"]=="success" and run["status"]=="completed"
assert run["path"]==".github/workflows/neutts-apt-extensions.yml"
assert len(jobs)==1 and jobs[0]["id"]==v["job_id"] and jobs[0]["conclusion"]=="success" and jobs[0]["status"]=="completed"
assert all(s["conclusion"]=="success" for s in jobs[0]["steps"])
assert len(artifacts)==1
artifact=artifacts[0]
assert artifact["id"]==v["artifact_id"] and artifact["digest"]=="sha256:"+ZIP_SHA and artifact["size_in_bytes"]==len(zipraw)
assert artifact["name"]=="termux-neutts-apt-extensions"
with zipfile.ZipFile(SRC/"artifact.zip") as z:
    assert z.testzip() is None
    assert len(z.infolist())==len(v["members"])
    assert {i.filename for i in z.infolist()}=={r["name"] for r in v["members"]}
    for row in v["members"]:
        raw=z.read(row["name"])
        assert len(raw)==row["bytes"] and sha(raw)==row["sha256"] and z.getinfo(row["name"]).CRC==row["crc"]
        if row["extracted"]:
            assert (SRC/"extracted"/row["name"]).read_bytes()==raw
            retain(row["name"],raw,"verified artifact member")
assert sum(r["extracted"] for r in v["members"])==125
assert sum(r["bytes"] for r in v["members"] if r["extracted"])==3091091
for p in sorted(SRC.glob("*-api*.json")):
    retain("capture/"+p.name,p.read_bytes(),"original GitHub API snapshot")
for name in ("verified-artifact.json","native-job.log"):
    retain("capture/"+name,(SRC/name).read_bytes(),"original capture")
retain("capture/capture-helper.py",(BASE/"capture_apt_extensions_run_39080859288.py").read_bytes(),"actual generic capture helper used for this run")
retain("capture/freeze-helper.py",Path(__file__).read_bytes(),"actual success evidence verifier and freezer")
log=(SRC/"native-job.log").read_bytes()
assert {"bytes":len(log),"sha256":sha(log)}==v["native_job_log"]
assert len(log)==194546 and sha(log)=="0d487cd5ffe33cfb8c5ede463cad4a8c4abfd37fcf0825f789e35d49cf7472f6"

a=load("apt-extension-components/APT-EXTENSIONS-RESULT.json")
core=load("NEUTTS-CORE-RESULT.json")
assert core["status"]=="passed" and len(core["cases"])==7
assert {c["component"] for c in core["cases"]}=={"python_dependencies","torch","torchaudio","torchcodec","scipy","llvmlite","soxr"}
for c in core["cases"]:
    assert c["status"]=="passed" and c["exit_code"]==0 and not c["timed_out"]
    assert c["receipt_sha256"]==identity(c["receipt"])["sha256"]
assert a["status"]=="passed" and len(a["cases"])==5
assert a["foundation"]["status"]=="passed" and a["foundation"]["case_count"]==7
assert a["foundation"]["sha256"]==identity("NEUTTS-CORE-RESULT.json")["sha256"]
assert a["foundation"]["apt_validation_sha256"]==identity("NEUTTS-APT-PYTHON-VALIDATION.json")["sha256"]
assert a["archives"]["status"]=="passed" and a["archives"]["archives"]==84 and a["archives"]["bytes"]==126542852
assert a["archives"]["receipt_sha256"]==identity("apt-extension-components/VERIFIED-APT-ARCHIVES.json")["sha256"]
assert a["installation"]["status"]=="passed" and a["installation"]["selected_count"]==18
assert a["installation"]["selected_archive_bytes"]==14043104
assert len(a["installation"]["new_packages"])==15 and len(a["installation"]["reinstalled_exact_packages"])==3
for key in ("removed_packages","unreviewed_upgrades","other_state_changes"): assert a["installation"][key]==[]
assert a["signed_index"]["status"]=="passed" and not a["signed_index"]["insecure_exceptions"]
assert a["signed_index"]["matched_foundation_packages"]==122 and a["signed_index"]["matched_provenance_archives"]==84
assert a["requirements"]["status"]=="requirements-and-provenance-passed"
assert a["requirements"]["apt_distributions"]==12 and a["requirements"]["raw_pip_exit_code"]==1 and not a["requirements"]["raw_pip_passed"]
assert a["requirements"]["sha256"]==identity("apt-extension-components/APT-EXTENSIONS-REQUIREMENTS.json")["sha256"]
assert a["original_files_before"]==a["original_files_after"]
assert a["original_files_after"]["status"]=="passed" and a["original_files_after"]["regular_files"]==893 and a["original_files_after"]["symlinks"]==1 and a["original_files_after"]["aarch64_elf_files"]==34
assert a["original_files_after"]["original_metadata_and_tags_preserved"]
for key in ("compiler_requested","engine_installed","metadata_modified","model_downloaded","production_admission_changed","published","speech_synthesis_tested","supported_tags_modified"): assert a[key] is False
assert (a["runtime"]["version"],a["runtime"]["system"],a["runtime"]["machine"],a["runtime"]["api_level"])==("3.14.6","Android","aarch64",24)
for rel in ("APT-EXTENSIONS-EXIT.json","NEUTTS-EXIT.json"):
    ex=load(rel);assert ex["stage"]=="complete" and ex["exit_code"]==0

lockraw=(REPO/"scripts/neutts_apt_extensions_lock.json").read_bytes()
assert sha(lockraw)==a["lock_sha256"]==LOCK_SHA
assert lockraw==(SRC/"extracted/apt-extension-inputs/neutts_apt_extensions_lock.json").read_bytes()
lock=json.loads(lockraw)
source=load("APT-EXTENSIONS-PROBE-INPUTS.json")
assert source["head_sha"]==source["workflow_ref_commit"]==HEAD and source["run_id"]=="39084149423" and source["native_image"]==IMAGE
assert len(source["inputs"])==16
for rel,digest in source["inputs"].items(): assert sha((REPO/rel).read_bytes())==digest,rel
image_pins={r["path"]:r for r in lock["image_runtime"]["files"]}
extension_pins={r["path"]:r for r in lock["extension_image_runtime"]["files"]}
assert len(image_pins)==5 and len(extension_pins)==1
assert a["image_runtime"]["status"]=="passed" and a["image_runtime"]["image"]==IMAGE
assert a["image_runtime"]["files"]==lock["image_runtime"]["files"]
assert a["image_runtime"]["snapshot_archive_claim"] is False
ext=a["extension_image_runtime"]
assert ext["status"]=="passed" and ext["image"]==IMAGE and ext["original_foundation_file_count"]==5 and not ext["snapshot_archive_claim"]
assert ext["source_evidence"]==lock["extension_image_runtime"]["source_evidence"]
prior=(REPO/ext["source_evidence"]["path"]).read_bytes()
assert len(prior)==ext["source_evidence"]["bytes"] and sha(prior)==ext["source_evidence"]["sha256"]
pins={r["package"]:r for r in lock["apt"]["provenance_packages"]}
assert len(pins)==84
for name,pin in pins.items(): assert a["installed_apt_controls"][name]==pin["control"]
expected={"pyarrow":(108,5,1,114),"lxml":(35,5,0,40),"msgpack":(30,5,0,35),"pillow":(39,5,0,44),"psutil":(31,5,0,36)}
parents={c["component"]:c for c in a["cases"]}
assert set(parents)==set(expected)
cases=[]
for name,counts in expected.items():
    rel="apt-extension-components/"+name
    c=load(rel+"/CASE-RESULT.json");o=load(rel+"/MAPPED-LIBRARY-OBSERVATIONS.json");m=c["mappings"];parent=parents[name]
    assert parent["status"]==parent["child_status"]=="passed" and parent["command"]["status"]=="passed" and parent["command"]["exit_code"]==0 and not parent["command"]["timed_out"]
    assert parent["sha256"]==identity(rel+"/CASE-RESULT.json")["sha256"]
    for stream in ("stdout","stderr"):
        r=parent["command"][stream];ident=identity("apt-extension-components/"+r["file"])
        assert r["bytes"]==ident["bytes"] and r["sha256"]==ident["sha256"]
    assert c["component"]==name and c["status"]=="passed" and c["behavior"]["operations"] and "error" not in c
    assert o["image"]==IMAGE and o["complete"] and not o["admitted"] and o["collection_errors"]==[] and o["resolution_errors"]==[] and len(o["files"])==counts[3]
    assert c["mapping_observations"]["sha256"]==identity(rel+"/MAPPED-LIBRARY-OBSERVATIONS.json")["sha256"]
    observations={r["resolved_path"]:r for r in o["files"]}
    assert len(observations)==len(o["files"])
    assert m["status"]=="passed" and (m["apt_count"],m["image_count"],m["extension_image_count"])==counts[:3]
    assert {r["path"] for r in m["mapped_files"]}==set(observations) and len(m["mapped_files"])==counts[3]
    authorities={"exact APT archive":0,"pinned-image-aosp":0,"pinned-image-aosp-extension":0}
    for row in m["mapped_files"]:
        obs=observations[row["path"]]
        assert row["bytes"]==obs["bytes"] and row["sha256"]==obs["sha256"]
        assert obs["owners"]==[row["owner"]] and obs["elf"]=={"class":64,"endianness":"little","machine":183}
        assert row["mapped_paths"]==obs["mapped_paths"]
        authorities[row["authority"]]+=1
        if row["authority"]=="exact APT archive":
            pin=pins[row["owner"]]
            assert row["version"]==pin["version"]==obs["owner_states"][row["owner"]]["version"]
            assert obs["owner_states"][row["owner"]]["architecture"]==pin["architecture"]
        elif row["authority"]=="pinned-image-aosp":
            pin=image_pins[row["path"]]
            assert row["bytes"]==pin["bytes"] and row["sha256"]==pin["sha256"] and obs["owners"]==pin["dpkg_owners"]
        else:
            pin=extension_pins[row["path"]]
            assert row["bytes"]==pin["bytes"] and row["sha256"]==pin["sha256"] and obs["owners"]==pin["owners"]
            assert obs["owner_states"][row["owner"]]==pin["owner_state"]
            for key in ("mode","uid","gid"): assert row[key]==obs[key]==pin[key]
            assert row["version"]==pin["owner_state"]["version"] and obs["elf"]==pin["elf"]
        assert obs["owner_states"][row["owner"]]["status"]=="installed"
    assert tuple(authorities.values())==counts[:3]
    cases.append({"component":name,"status":"passed","behavior":c["behavior"],"mapping_status":"passed","mapping_counts":{"apt":counts[0],"original_image":counts[1],"extension_image":counts[2]},"observed_libraries":counts[3],"diagnostics_complete":True,"unknown_paths":[],"case_receipt":identity(rel+"/CASE-RESULT.json"),"observation_receipt":identity(rel+"/MAPPED-LIBRARY-OBSERVATIONS.json")})
icu=next(iter(extension_pins.values()))
assert len(ext["files"])==1
for key in ("path","bytes","sha256","mode","uid","gid"): assert ext["files"][0][key]==icu[key]
assert ext["files"][0]["owner"]=="aosp-libs" and ext["files"][0]["version"]==icu["owner_state"]["version"]
before=load("apt-extension-components/dpkg-before.json");after=load("apt-extension-components/dpkg-after.json")
assert before["aosp-libs"]==after["aosp-libs"]==icu["owner_state"]
assert "aosp-libs" not in a["installation"]["selected_versions"]
assert ("Digest: "+IMAGE.split("@",1)[1]).encode() in log
raw_files=[{"path":rel,"bytes":len(raw),"sha256":sha(raw),"source":origin} for rel,(raw,origin) in sorted(pending.items())]
summary={
 "schema_version":1,"recorded_date_utc":"2026-10-18",
 "status":"passed native five-component operations and provenance gates after the unchanged seven-case scientific foundation",
 "run":{"id":39084149423,"job_id":117547090041,"head_sha":HEAD,"url":run["html_url"],"conclusion":"success","workflow":run["path"]},
 "artifact":{"id":v["artifact_id"],"bytes":len(zipraw),"sha256":ZIP_SHA,"members":139,"every_zip_crc_and_member_sha256_verified":True,"retained_members":125,"retained_member_bytes":3091091,"large_binary_members_omitted_from_git":True},
 "source_inputs":source,
 "foundation":a["foundation"],"foundation_cases":core["cases"],"archives":a["archives"],
 "installation":{"status":a["installation"]["status"],"selected_count":18,"selected_archive_bytes":a["installation"]["selected_archive_bytes"],"selected_versions":a["installation"]["selected_versions"],"new_packages":a["installation"]["new_packages"],"reinstalled_exact_packages":a["installation"]["reinstalled_exact_packages"],"removed_packages":[],"unreviewed_upgrades":[],"other_state_changes":[]},
 "signed_index":{k:a["signed_index"][k] for k in ("status","authority","insecure_exceptions","matched_foundation_packages","matched_provenance_archives","snapshot","uncompressed")},
 "original_files_before":a["original_files_before"],"original_files_after":a["original_files_after"],
 "requirements":a["requirements"],"runtime":a["runtime"],"cases":cases,
 "original_image_runtime":a["image_runtime"],"extension_image_runtime":ext,
 "image_binding":{"image":IMAGE,"docker_pull_digest_verified_in_raw_job_log":True,"owner_state_before":before["aosp-libs"],"owner_state_after":after["aosp-libs"],"owner_package_selected_for_install":False,"authority":"Exact original five-file foundation plus the single previously observed and reviewed ICU member in the same immutable image. ICU is not attributed to a snapshot APT archive."},
 "limitations":["This validates five isolated APT component operation groups and complete observed mapping provenance in the recorded native Android container. It does not validate a combined full NeuTTS engine.","No metadata or wheel tags changed. Raw pip still exited 1 for the 12 original legacy-tag distributions; the separate requirement/provenance result passed.","No compiler was requested. No speech model download, speech synthesis, device, microphone, training, release or production admission is claimed.","Both earlier failed native runs remain unchanged; the success does not retroactively change their outcomes."],
 "raw_file_count":len(raw_files),"raw_bytes":sum(x["bytes"] for x in raw_files),"raw_files":raw_files
}
summaryraw=(json.dumps(summary,indent=2,sort_keys=True)+"\n").encode()
for rel,(raw,_) in pending.items(): save(OUT/rel,raw)
save(OUT.with_suffix(".json"),summaryraw)
actual={p.relative_to(OUT).as_posix():p.read_bytes() for p in OUT.rglob("*") if p.is_file()}
assert set(actual)==set(pending)
for row in raw_files: assert len(actual[row["path"]])==row["bytes"] and sha(actual[row["path"]])==row["sha256"]
print(json.dumps({"audit":str(OUT.with_suffix(".json")),"bytes":len(summaryraw),"sha256":sha(summaryraw),"raw_file_count":len(raw_files),"raw_bytes":sum(x["bytes"] for x in raw_files),"total_files":len(raw_files)+1,"total_bytes":sum(x["bytes"] for x in raw_files)+len(summaryraw),"cases":{c["component"]:c["status"] for c in cases},"all_copied_bytes_reverified":True},indent=2))
