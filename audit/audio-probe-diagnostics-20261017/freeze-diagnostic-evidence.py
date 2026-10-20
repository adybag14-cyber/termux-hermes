"""Save the bounded audio-probe diagnostic change and exact host verification."""
from pathlib import Path
import ast,difflib,hashlib,json
BASE=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
REPO=BASE/"termux-hermes-next-stable-20261017"
ORIGINAL=REPO/"audit/audio-hermes-native-20261017/run-39075197287/run-source"
HOST=BASE/"audio-probe-diagnostics-20261017/host-checks-v1"
OUT=REPO/"audit/audio-probe-diagnostics-20261017"
SUMMARY=OUT.with_suffix(".json")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def row(raw):return {"bytes":len(raw),"sha256":sha(raw)}
def encoded(obj):return (json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()
saved={}
def put(name,raw):
    target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb")as stream:stream.write(raw)
    assert target.read_bytes()==raw;saved[name]=row(raw)
def main():
    assert not OUT.exists()and not SUMMARY.exists()
    report=json.loads((HOST/"HOST-VERIFICATION.json").read_bytes())
    assert report["exit_code"]==0 and report["test_cases"]==125 and report["failed"]==report["skipped"]==0
    diff=[]
    for name,pin in {
        "scripts/compatibility_probe_audio_hermes.py":"a38c4ba7c119650c7fcd2e81a286a6b9878bc9cd5906db9059682d700b1e3253",
        "tests/test_audio_hermes_preparation.py":"a3e8c53acd093f2f82bab1d3a9f6229e81c63533850d4155e5ceac8bb3d72549",
    }.items():
        before=(ORIGINAL/name).read_bytes();after=(REPO/name).read_bytes()
        assert sha(after)==pin and row(after)==report["source_files"][name]
        ast.parse(after)
        put("before/"+name,before);put("after/"+name,after)
        diff.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),fromfile="a/"+name,tofile="b/"+name))
    put("audio-probe-failure-diagnostics.patch","".join(diff).encode())
    helper="scripts/prepare_audio_hermes_environment.py"
    assert sha((REPO/helper).read_bytes())=="9c0186ac96cb897fee764a51995b0834586b7c953439092e6b184097753dad88"
    for path in sorted(HOST.iterdir()):
        assert path.is_file()
        if path.name in report["raw"]: assert row(path.read_bytes())==report["raw"][path.name]
        put("host-checks/"+path.name,path.read_bytes())
    put("freeze-diagnostic-evidence.py",Path(__file__).read_bytes())
    design="""# Audio runtime failure diagnostics

Native run 39075197287 at 09dda7a9e7e55977e846742064cd7b4fa32978bc completed its first fresh preparation and failed inside the subsequent readiness worker. The exact original run, 81-member proof ZIP and full text receipts are preserved in the adjacent native-run audit. Its child stderr contains only the generic failure of the strict sounddevice exception-type predicate; the original exception details were not retained by that version.

This change preserves that failure and adds evidence for the next native run. Main now records the error's type/message, exception-chain type/module/message/args, and formatted original traceback in audio-readiness-failure.json. It also emits the full traceback to retained stderr. If receipt writing fails, the original traceback and nonzero exit still survive.

Every existing function except main remains byte-identical, including the whole runtime worker, full preparation/probe verification, numerics, explicit pinned audio libraries, exact PortAudioError predicate, runtime mappings, payload preservation, launcher-version check, and native success receipts. The preparation helper is unchanged. The original 118 test bytes remain intact, with seven new parameterized host regression cases appended.

The new tests exercise actual Python exception chaining, CLI nonzero behavior, durable diagnostics, suppressed/explicit causes, and a real filesystem write failure. They do not simulate or certify Android, sounddevice imports, a native dependency pass, audio initialization, capture, or VAD.

The import's underlying cause is still unknown. Exact upstream sounddevice source performs library discovery before PortAudio initialization, but that source observation is not a diagnosis. No generic failure is reclassified as an expected missing-framework condition. A root-reviewed native retry must expose the actual exception before further compatibility changes.
"""
    put("DESIGN.md",design.encode())
    put("SAVED-FILES.json",encoded({"schema_version":1,"files":dict(saved),"files_in_ledger":len(saved),"bytes_in_ledger":sum(x["bytes"]for x in saved.values())}))
    summary={
        "schema_version":1,"status":"host-verified-native-diagnostic-pending",
        "observed_run":39075197287,"observed_head":"09dda7a9e7e55977e846742064cd7b4fa32978bc",
        "original_failure_audit":{"path":"audit/audio-hermes-native-20261017/run-39075197287.json","sha256":"11a10d1ff94c9ff94ace49cca3241abf2c1f7fca7f4ea15cb4925eee01a194d6"},
        "change":"Durable original exception-chain and traceback diagnostics; all success predicates preserved.",
        "changed_files":{n:report["source_files"][n]for n in ["scripts/compatibility_probe_audio_hermes.py","tests/test_audio_hermes_preparation.py"]},
        "unchanged_preparer":report["source_files"][helper],
        "all_existing_functions_except_main_byte_identical":True,
        "original_test_bytes_preserved":True,"host_tests":{"passed":125,"failed":0,"skipped":0,"original_cases":118,"new_cases":7},
        "native_retry":"pending root review and push","actual_sounddevice_import_error":"not retained by original run; remains unknown",
        "preparation_in_original_native_run":"passed","runtime_readiness_in_original_native_run":"failed",
        "physical_vad":"not-tested","microphone_accessed":False,"audio_stream_opened":False,"published":False,
        "raw_files":len(saved),"raw_bytes":sum(x["bytes"]for x in saved.values()),"saved_files_ledger":saved["SAVED-FILES.json"]}
    with SUMMARY.open("xb")as stream:stream.write(encoded(summary))
    for name,pin in saved.items(): assert row((OUT/name).read_bytes())==pin
    print(json.dumps({"summary_path":str(SUMMARY),"summary":row(SUMMARY.read_bytes()),"raw_files":len(saved),"raw_bytes":sum(x["bytes"]for x in saved.values()),"total_files":len(saved)+1,"total_bytes":sum(x["bytes"]for x in saved.values())+SUMMARY.stat().st_size,"source_files":summary["changed_files"]},indent=2))
if __name__=="__main__":main()
