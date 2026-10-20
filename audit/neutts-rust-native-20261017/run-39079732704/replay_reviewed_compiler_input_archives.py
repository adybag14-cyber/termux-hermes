"""Replay all exact APT controls and requested compiler members with the corrected reader."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT=ROOT/"audit/neutts-rust-native-20261017/run-39079732704"
BASE=ROOT.parent/"neutts-rust-native-evidence-20261017/39079732704"
CACHE=ROOT.parent/"neutts-rust-native-evidence-20261017/39077868589/extracted-termux-neutts-rust-locked-build/rust-inputs/apt-archives"
UNION=BASE/"reviewed-47-apt-union"
EXPECTED={
"scripts/neutts_rust_sources_lock.json":"de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670",
"scripts/prepare_neutts_rust_sources.py":"db8ce00daaece15f69b4f7b1de415accd207f13e256b2097d4efcb2d0894c428",
"scripts/compatibility_probe_neutts_rust.py":"cdcff92a28d310536becc9e84e68b4683b45dca2f9230584a748dd72c930276b",
"tests/test_neutts_rust_preparation.py":"82a2c0e881810d7aedaba532407e9704a96a6a3d7952d25a0a4fbc2a92253297"}
sys.dont_write_bytecode=True
def sha(raw): return hashlib.sha256(raw).hexdigest()
def ident(path):
    raw=path.read_bytes()
    return {"path":path.relative_to(ROOT).as_posix(),"bytes":len(raw),"sha256":sha(raw)}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value
def main():
    source_pins=[]
    for name,digest in EXPECTED.items():
        p=ROOT/name; row=ident(p);assert row["sha256"]==digest;source_pins.append(row)
    review_path=AUDIT/"compiler-input-archive-review-attempt3.json"
    raw=review_path.read_bytes();assert len(raw)==43003 and sha(raw)=="31c433d124add5a5bfe9693a77fedfd06b5005b7a5b5445cb7b93ffe0aa78343"
    review=json.loads(raw)
    prep=load("_compiler_replay_preparer",ROOT/"scripts/prepare_neutts_rust_sources.py")
    native=load("_compiler_replay_native",ROOT/"scripts/compatibility_probe_neutts_rust.py")
    inspector=load("_compiler_original_ast_inspector",AUDIT/"inspect_compiler_input_archives_v3.py")
    lock,lock_raw=prep.load_lock(ROOT/"scripts/neutts_rust_sources_lock.json")
    pins=lock["build_apt"]["packages"];assert len(pins)==47
    original=deepcopy(lock)
    tool=next(p for p in original["build_apt"]["packages"] if p["name"]=="openssl-tool")
    original["build_apt"]["packages"].remove(tool)
    original["build_apt"]["additional_to_foundation"].remove("openssl-tool")
    original["build_apt"]["roots"].pop("openssl-tool")
    assert sha((json.dumps(original,sort_keys=True,indent=2)+"\n").encode())==review["baseline_lock_sha256"]
    static=inspector.static_native_paths((ROOT/"scripts/compatibility_probe_neutts_rust.py").read_bytes())
    assert static==[x["requested_path"] for x in review["requested_paths"][:14]]
    exact={(p["archive_sha256"],p["path"]):{"bytes":p["bytes"],"sha256":p["sha256"]}
           for p in review["original_native_parser_large_member_rejections"]}
    assert native.APT_MEMBER_MAX_BYTES==64000000 and native.APT_EXACT_LARGE_MEMBERS==exact
    assert not UNION.exists();UNION.mkdir()
    for pin in pins:
        basename=prep.apt_archive_filename(pin)
        source=(BASE/"supplemental-apt-inputs" if pin["name"]=="openssl-tool" else CACHE)/basename
        assert source.is_file() and not source.is_symlink()
        raw=source.read_bytes();assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
        shutil.copyfile(source,UNION/basename)
    args=SimpleNamespace(apt_archives=UNION)
    archive_rows=native.verify_archive_set(args,lock,prep)
    assert len(archive_rows)==47
    print(json.dumps({"stage":"all-original-archive-controls","verified_archives":47}),flush=True)
    grouped=defaultdict(set)
    expected={}
    for row in review["requested_paths"]:
        path=row["resolved_archive_path"]
        value={"bytes":row["bytes"],"sha256":row["sha256"],"package":row["package"]}
        assert path not in expected or expected[path]==value
        expected[path]=value;grouped[row["package"]].add(path)
    matched=[]
    for pin in pins:
        if pin["name"] not in grouped: continue
        wanted=grouped[pin["name"]]
        contents=native.ar_data_members(UNION/prep.apt_archive_filename(pin),pin,wanted)
        for path,raw in sorted(contents.items()):
            row=expected[path]
            assert len(raw)==row["bytes"] and sha(raw)==row["sha256"] and pin["name"]==row["package"]
            matched.append({"path":path,**row})
        print(json.dumps({"stage":"actual-corrected-member-reader","package":pin["name"],"selected_files":len(contents)}),flush=True)
    assert len(matched)==88 and len(review["requested_paths"])==89
    for row in source_pins:
        assert ident(ROOT/row["path"])==row
    report={"schema":"native-rust-compiler-input-corrected-archive-replay/v1",
        "observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"status":"passed-host-archive-replay",
        "source_pins":source_pins,"original_path_review":ident(review_path),
        "original_46_archive_and_all_source_lock_bytes_reconstructed_exactly":True,
        "sole_addition":tool,"archive_count":47,"all_archive_controls_verified":True,
        "actual_verify_archive_set_executed":True,"actual_ar_data_members_executed":True,
        "parser_functions_or_limits_mocked":False,"generic_member_bound_bytes":native.APT_MEMBER_MAX_BYTES,
        "exact_large_members":review["original_native_parser_large_member_rejections"],
        "requested_path_count":89,"fixed_requested_path_count":14,"rust_library_requested_path_count":75,
        "unique_original_regular_file_count":88,"verified_original_members":matched,
        "original_alias_count":sum(bool(r["symlink_chain"]) for r in review["requested_paths"]),
        "original_aliases_preserved_by_exact_archive_sha":True,"fresh_owned_archive_directory":str(UNION),
        "archive_rows":archive_rows,
        "native_dpkg_owner_query_executed":False,"native_install_or_execution_claimed":False,
        "cargo_or_source_build_executed":False,"tls_verification_controls_changed":False,"release_output":False}
    out=AUDIT/"compiler-input-corrected-archive-replay.json";assert not out.exists()
    raw=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode();out.write_bytes(raw);assert out.read_bytes()==raw
    print(json.dumps({"status":report["status"],"receipt":ident(out),"archive_count":47,"requested_paths":89,"regular_files":88}),flush=True)
if __name__=="__main__":
    main()
