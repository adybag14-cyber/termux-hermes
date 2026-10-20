"""Freeze the exact failed audio run before a diagnostic-only repair."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, sys, zipfile

BASE=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
REPO=BASE/"termux-hermes-next-stable-20261017"
RUN=39075197287
HEAD="09dda7a9e7e55977e846742064cd7b4fa32978bc"
EVIDENCE=BASE/"audio-hermes-native-evidence-20261017"/str(RUN)
OUT=REPO/"audit/audio-hermes-native-20261017"/f"run-{RUN}"
SUMMARY=OUT.with_suffix(".json")
def sha(raw): return hashlib.sha256(raw).hexdigest()
def identity(raw): return {"bytes":len(raw),"sha256":sha(raw)}
def encoded(value): return (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()
def put(relative, raw):
    target=OUT/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as stream: stream.write(raw)
    assert target.read_bytes()==raw
    return identity(raw)

def main():
    assert not OUT.exists() and not SUMMARY.exists()
    verified=json.loads((EVIDENCE/"verified-artifact.json").read_bytes())
    assert verified["run_id"]==RUN and verified["head_sha"]==HEAD and verified["job_id"]==117520804086
    archive=(EVIDENCE/"artifact.zip").read_bytes()
    assert identity(archive)=={"bytes":33928175,"sha256":"f5690d4a97d1b1e15e941a5ec73ad493fb01f107f25e8de074c89eba1a0b5c51"}
    prepared=EVIDENCE/"extracted/prepared"
    receipt=json.loads((prepared/"audio-environment-receipt.json").read_bytes())
    assert receipt["status"]=="prepared-environment" and receipt["preparation_integrity"]=="passed"
    assert receipt["preparer_sha256"]=="9c0186ac96cb897fee764a51995b0834586b7c953439092e6b184097753dad88"
    assert receipt["probe_sha256"]=="487b35edf7f65c0c1482095486a12d021473e73fceac11038e3769d490a8c85b"
    assert receipt["native_audio_initialization"]=="not-probed"
    assert receipt["physical_vad"]=="not-tested" and not receipt["microphone_accessed"] and not receipt["published"]
    child=(prepared/"evidence/audio-readiness.stderr.log").read_bytes()
    assert child==b"Audio readiness probe failed: audio import failed for a reason other than PortAudio initialization\n"
    assert (prepared/"evidence/audio-readiness.stdout.log").read_bytes()==b""
    originals=json.loads((prepared/"evidence/original-payload-inventory.json").read_bytes())["files"]
    final=json.loads((prepared/"evidence/prepared-payload-inventory.json").read_bytes())["files"]
    source_names=[
        "scripts/prepare_audio_hermes_environment.py",
        "scripts/compatibility_probe_audio_hermes.py",
        "scripts/run_audio_hermes_preparation.sh",
        "tests/test_audio_hermes_preparation.py",
        ".github/workflows/audio-hermes-preparation.yml",
        "patches/next-stable/audio-readiness.patch",
        "patches/next-stable/audio-pm-marker-bytecode.patch",
    ]
    sources={}
    for name in source_names:
        raw=subprocess.check_output(["git","show",HEAD+":"+name],cwd=REPO,timeout=15)
        if name.startswith("scripts/") or name.startswith("tests/"):
            assert (REPO/name).read_bytes()==raw
        sources[name]=raw
    assert sha(sources[source_names[0]])==receipt["preparer_sha256"]
    assert sha(sources[source_names[1]])==receipt["probe_sha256"]
    spec=importlib.util.spec_from_file_location("_audio_failed_inventory_recheck",REPO/source_names[0])
    prep=importlib.util.module_from_spec(spec); sys.modules[spec.name]=prep; spec.loader.exec_module(prep)
    assert prep.inventory_sha(originals)==receipt["original_inventory_sha256"]
    assert prep.inventory_sha(final)==receipt["prepared_inventory_sha256"]
    assert prep.allowed_changes(originals,final)==receipt["payload_changes"]
    assert (prepared/"evidence/post-build-payload-inventory.json").read_bytes()==(prepared/"evidence/prepared-payload-inventory.json").read_bytes()
    gate=receipt["canonical_build"]
    assert gate["status"]=="passed" and gate["manager_built_fresh"] and gate["application_built_fresh"]
    assert gate["manager"]["distribution_count"]==4 and gate["manager"]["wheel_owned_files_checked"]==75
    assert gate["application"]["distribution_count"]==101 and gate["application"]["wheel_owned_files_checked"]==6906
    assert gate["catalog_union"]=={"additional_rows":2,"original_rows":100,"original_rows_preserved":True,"total_rows":102}
    normal=receipt["generated_tool_bytecode"]
    assert normal["removed_files"]==50 and normal["removed_directories"]==6
    assert normal["exact_original_python_inventory_restored"] and normal["source_files_changed"]==normal["baseline_entries_removed"]==0
    links=receipt["baseline_missing_documentation_links"]
    assert len(links)==1 and len(receipt["contained_links"])==76
    rows=verified["members"]; assert len(rows)==81
    members=[]; saved={}
    with zipfile.ZipFile(EVIDENCE/"artifact.zip") as z:
        assert z.testzip() is None and len(z.infolist())==len(rows)
        assert {x.filename for x in z.infolist()}=={x["name"]for x in rows}
        for row in rows:
            info=z.getinfo(row["name"]); raw=z.read(info)
            assert identity(raw)=={"bytes":row["bytes"],"sha256":row["sha256"]} and info.CRC==row["crc"]
            assert (EVIDENCE/"extracted"/row["name"]).read_bytes()==raw
            retain=not row["name"].endswith(".pyc")
            if retain: saved["native-artifact/"+row["name"]]=put("native-artifact/"+row["name"],raw)
            members.append({**row,"saved_in_git_audit":retain,
                "retention":"exact raw evidence" if retain else "generated bytecode: exact bytes retained outside Git; full digest and CRC in ledger"})
    assert sum(m["saved_in_git_audit"]for m in members)==31
    for name in ["run-api.json","jobs-api.json","artifacts-api.json","native-job.log","verified-artifact.json"]:
        saved[name]=put(name,(EVIDENCE/name).read_bytes())
    for path in sorted((EVIDENCE/"root-capture-v1").iterdir()):
        assert path.is_file()
        name="initial-root-capture/"+path.name
        saved[name]=put(name,path.read_bytes())
    for name,raw in sources.items(): saved["run-source/"+name]=put("run-source/"+name,raw)
    helper=BASE/"capture_audio_environment_run_39075197287.py"
    saved[helper.name]=put(helper.name,helper.read_bytes())
    saved["freeze-run-evidence.py"]=put("freeze-run-evidence.py",Path(__file__).read_bytes())
    saved["ARTIFACT-MEMBERS.json"]=put("ARTIFACT-MEMBERS.json",encoded({"members":members,"artifact":identity(archive),"all_crc_verified":True}))
    check={
        "schema_version":1,"run_id":RUN,"status":"evidence-verified",
        "artifact":identity(archive),"zip_members_rehashed_and_crc_checked":81,
        "raw_retained_member_copies_rechecked":81,
        "original_inventory_entries":len(originals),"prepared_inventory_entries":len(final),
        "recorded_payload_changes":len(receipt["payload_changes"]),
        "full_original_to_prepared_policy_replayed":True,
        "post_build_and_prepared_inventory_bytes_identical":True,
        "source_files":{n:identity(v)for n,v in sources.items()},
        "limits":[
            "Host verification replays saved inventories and hashes; it does not re-execute native code or re-read the removed container filesystem.",
            "Original sounddevice exception type/message/traceback were suppressed by this run's probe and cannot be recovered from the artifact.",
            "No full dependency-readiness completion, native PortAudio classification, launcher version check, second reconstruction, device capture or VAD success is claimed."
        ]}
    saved["INDEPENDENT-RECHECK.json"]=put("INDEPENDENT-RECHECK.json",encoded(check))
    saved["SAVED-FILES.json"]=put("SAVED-FILES.json",encoded({"schema_version":1,"files":saved,"files_in_ledger":len(saved),"bytes_in_ledger":sum(x["bytes"]for x in saved.values())}))
    summary={
        "schema_version":1,"run_id":RUN,"head_sha":HEAD,"job_id":117520804086,
        "url":f"https://github.com/adybag14-cyber/termux-hermes/actions/runs/{RUN}",
        "conclusion":"failure","artifact_id":12115794152,"artifact":identity(archive),
        "all_zip_member_crc_and_sha256_verified":81,"text_artifact_members_saved":31,
        "generated_bytecode_members_preserved_outside_git":50,
        "preparation":{
            "status":"passed","manager_distributions":4,"manager_wheel_owned_files_checked":75,
            "application_distributions":101,"application_wheel_owned_files_checked":6906,
            "catalog_original":100,"catalog_added":2,"catalog_total":102,
            "manager_and_application_built_fresh":True,
            "generated_cache_files_normalized":50,"generated_cache_directories_removed":6,
            "full_payload_policy_passed":True,"contained_working_links":76,
            "unchanged_baseline_missing_documentation_link_reported":1,
            "source_and_installed_inputs_preserved_by_native_preparer":True},
        "runtime_probe":{
            "status":"failed","recorded_child_stderr":child.decode().rstrip("\n"),
            "sounddevice_exception_type":"not-retained","sounddevice_exception_message":"not-retained",
            "sounddevice_exception_traceback":"not-retained",
            "source_control_flow_reached":[
                "fresh owned runtime and voice source checks","audio-io anchors",
                "cffi allocation/buffer","NumPy arithmetic/FFT/LAPACK/matrix multiplication",
                "explicit pinned OpenSL ES and PortAudio CDLL loads","sounddevice import"],
            "control_flow_interpretation":"The reviewed probe reaches this exact error only after prior assertions return; the dedicated runtime success receipt was never written.",
            "full_native_dependency_readiness":"not-completed","portaudio_initialization":"not-classified",
            "launcher_version":"not-reached","second_fresh_reconstruction":"not-reached"},
        "original_failed_evidence_unchanged":True,
        "physical_vad":"not-tested","microphone_accessed":False,"audio_stream_opened":False,"published":False,
        "raw_files":len(saved),"raw_bytes":sum(x["bytes"]for x in saved.values()),
        "saved_files_ledger":saved["SAVED-FILES.json"],"independent_recheck":saved["INDEPENDENT-RECHECK.json"],
        "reconstruction_artifact":{
            "id":12117100393,"bytes":233699949,
            "sha256":"225942c10769b9af18656c36111c0dfe46a10d70d6210b9247ee44f6b9da6d16",
            "status":"GitHub metadata and job-log digest retained; not downloaded by this capture"}}
    with SUMMARY.open("xb")as stream: stream.write(encoded(summary))
    for n,row in saved.items(): assert identity((OUT/n).read_bytes())==row
    print(json.dumps({"summary_path":str(SUMMARY),"summary":identity(SUMMARY.read_bytes()),"raw_files":len(saved),"raw_bytes":sum(x["bytes"]for x in saved.values()),"total_files":len(saved)+1,"total_bytes":sum(x["bytes"]for x in saved.values())+SUMMARY.stat().st_size},indent=2))
if __name__=="__main__": main()
