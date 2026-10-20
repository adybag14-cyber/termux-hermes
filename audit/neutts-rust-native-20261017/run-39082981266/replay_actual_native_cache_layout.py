from __future__ import annotations
import datetime,hashlib,importlib.util,json,pathlib,sys,time
from types import SimpleNamespace
ROOT=pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT=ROOT/"audit/neutts-rust-native-20261017/run-39082981266"
BASE=ROOT.parent/"neutts-rust-native-evidence-20261017/39082981266"
INPUT=BASE/"extracted-termux-neutts-rust-tiktoken-lock/rust-inputs/apt-archives"
WORK=BASE/"native-cache-layout-production-replay-v1"
def sha(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod; spec.loader.exec_module(mod); return mod
native=module("_actual_native_cache_replay",ROOT/"scripts/compatibility_probe_neutts_rust.py")
prep=module("_actual_native_cache_prep",ROOT/"scripts/prepare_neutts_rust_sources.py")
lock,raw=prep.load_lock(ROOT/"scripts"/prep.LOCK_FILENAME)
assert hashlib.sha256(raw).hexdigest()=="de243480c74b12ad81efc2886b8f78a237abb958588c8424f070e5a6be766670"
assert not WORK.exists()
WORK.mkdir()
pins=lock["build_apt"]["packages"]
assert len(pins)==47
started=time.monotonic()
args=SimpleNamespace(apt_archives=INPUT,out=WORK)
output=native.stage_install_archives(args,pins,WORK)
layout=json.loads((WORK/"rust-apt-cache-layout.json").read_bytes())
rows=[]
for pin in pins:
    source=INPUT/prep.apt_archive_filename(pin)
    target=output/native.apt_install_cache_basename(pin)
    assert source.is_file() and target.is_file() and not source.is_symlink() and not target.is_symlink()
    assert source.stat().st_size==target.stat().st_size==pin["bytes"]
    assert sha(source)==sha(target)==pin["sha256"]
    rows.append({"name":pin["name"],"in_foundation":pin["in_foundation"],"signed_filename":pin["filename"],
                 "input_basename":source.name,"apt_cache_basename":target.name,
                 "bytes":pin["bytes"],"sha256":pin["sha256"]})
assert sorted(p.name for p in output.iterdir())==sorted([native.apt_install_cache_basename(p) for p in pins]+["partial"])
try:
    native.stage_install_archives(args,pins,WORK)
except FileExistsError:
    existing_refused=True
else:
    raise AssertionError("Expected refusal of an existing native cache")
assert sha(WORK/"rust-apt-cache-layout.json")==hashlib.sha256(json.dumps(layout,sort_keys=True,indent=2).encode()+b"\n").hexdigest()
for source,target in [(WORK/"rust-apt-cache-layout.json",AUDIT/"actual-host-native-cache-layout.json")]:
    assert not target.exists(); target.write_bytes(source.read_bytes())
receipt={"schema":"actual-native-rust-cache-layout-host-replay/v1",
         "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "elapsed_seconds":round(time.monotonic()-started,3),
         "host_python":sys.version,"host_platform":sys.platform,
         "scope":"Production stage_install_archives and unchanged archive_path/sha_file on all 47 exact downloaded original archives. This is host file staging, not native APT installation or a source build.",
         "status":"passed","archive_count":len(pins),"input_bytes_rechecked_unchanged":True,
         "all_output_bytes_rechecked":True,"existing_output_refused":existing_refused,
         "source_pins_changed":False,"native_install_claimed":False,
         "input_root":str(INPUT),"output_root":str(output),
         "source_lock_sha256":hashlib.sha256(raw).hexdigest(),
         "layout_receipt":{"path":(AUDIT/"actual-host-native-cache-layout.json").relative_to(ROOT).as_posix(),"bytes":(WORK/"rust-apt-cache-layout.json").stat().st_size,"sha256":sha(WORK/"rust-apt-cache-layout.json")},
         "archive_bytes":sum(p["bytes"] for p in pins),"archives":rows}
path=AUDIT/"actual-native-cache-layout-production-replay.json"
assert not path.exists()
path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(json.dumps({k:v for k,v in receipt.items() if k!="archives"}))
print(json.dumps({"receipt":str(path),"bytes":path.stat().st_size,"sha256":sha(path)}))
