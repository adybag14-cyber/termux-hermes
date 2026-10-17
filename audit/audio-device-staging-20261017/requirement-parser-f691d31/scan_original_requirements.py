from pathlib import Path
import hashlib, importlib.metadata as metadata, io, json, re, sys, tarfile, tomllib, zipfile
out = Path(sys.argv[1])
checkpoint = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\audio-device-bundle-resume-20261017\checkpoint-4")
repo = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-resume-20261017")
def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw = path.read_bytes()
    return {"size":len(raw), "sha256":sha(raw)}
def write_json(name,value): (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
manifest_raw = (checkpoint/"manifest.json").read_bytes()
manifest = json.loads(manifest_raw)
(out/"checkpoint-manifest.json").write_bytes(manifest_raw)
(out/"checkpoint-bundle-receipt.json").write_bytes((checkpoint/"BUNDLE-RECEIPT.json").read_bytes())
entries = {row["path"]:row for row in manifest["entries"]}
wheels = {row["file"]:row for row in manifest["wheels"]}
assert len(wheels) == 102
source_names = {"app/hermes_agent-0.0.0.dist-info/METADATA","app/pyproject.toml","app/uv.lock","bundled-wheels.json","app/pm/lock.json"}
stdlib = "tools/python/data/data/com.termux/files/usr/lib/python3.14/platform.py"
todo = set(wheels) | source_names | {stdlib}
all_rows = []
subset = out/"original-input-subset"
with tarfile.open(checkpoint/"payload.tar.gz","r|gz") as archive:
    for member in archive:
        if member.name not in todo: continue
        assert member.isfile()
        data = archive.extractfile(member).read()
        declared = entries[member.name]
        assert len(data) == declared["size"] and sha(data) == declared["sha256"],member.name
        if member.name in source_names or member.name == stdlib or member.name.startswith("wheelhouse/psutil-"):
            dest = subset/member.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
        if member.name in wheels:
            row=wheels[member.name]
            assert len(data)==row["size"] and sha(data)==row["sha256"]
            with zipfile.ZipFile(io.BytesIO(data)) as wheel:
                names=[name for name in wheel.namelist() if name.count("/")==1 and name.endswith(".dist-info/METADATA")]
                assert len(names)==1,member.name
                raw=wheel.read(names[0])
            destination=out/"metadata"/row["name"]/names[0]
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(raw)
            dist=metadata.PathDistribution(destination.parent)
            assert re.sub(r"[-_.]+","-",dist.metadata["Name"]).lower()==row["name"]
            assert dist.version==row["version"]
            all_rows.append({"parent":row["name"],"version":row["version"],"metadata_path":destination.relative_to(out).as_posix(),
                             "metadata":pin(destination),"source":"wheel","wheel":row})
            if row["name"]=="packaging":
                parser_path=out/Path(row["file"]).name
                parser_path.write_bytes(data)
        todo.remove(member.name)
        if not todo:break
assert not todo, sorted(todo)
hermes = subset/"app/hermes_agent-0.0.0.dist-info/METADATA"
all_rows.append({"parent":"hermes-agent","version":"0.0.0","metadata_path":hermes.relative_to(out).as_posix(),
                 "metadata":pin(hermes),"source":"source-layout"})
assert not any(name=="packaging" or name.startswith("packaging.") for name in sys.modules)
sys.path.insert(0,str(parser_path))
import packaging
from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet
assert packaging.__version__=="26.0"
assert str(parser_path) in packaging.__file__
results=[]
failures=[]
variables=set()
def mark_variables(node):
    if isinstance(node,list):
        for child in node:mark_variables(child)
    elif isinstance(node,tuple):
        for obj in node:
            if type(obj).__name__=="Variable":variables.add(obj.value)
for row in sorted(all_rows,key=lambda item:item["parent"]):
    dist=metadata.PathDistribution((out/row["metadata_path"]).parent)
    requirements=[]
    for raw in dist.requires or []:
        result={"raw":raw,"status":"parsed"}
        try:
            parsed=Requirement(raw)
            result.update(name=parsed.name,url=parsed.url,extras=sorted(parsed.extras),
                          marker=str(parsed.marker) if parsed.marker is not None else None,
                          specifier=str(parsed.specifier))
            if parsed.marker is not None:mark_variables(parsed.marker._markers)
        except InvalidRequirement as exc:
            result.update(status="invalid",error=str(exc))
            failures.append({"parent":row["parent"],"version":row["version"],"metadata":row["metadata"],**result})
        requirements.append(result)
    constraint=dist.metadata.get("Requires-Python")
    if constraint:SpecifierSet(constraint)
    results.append({**row,"requires_python":constraint,"requirements":requirements})
project=tomllib.loads((subset/"app/pyproject.toml").read_text())
report={"schema_version":1,"purpose":"Original frozen requirement parser audit on host; no native runtime proof",
        "checkpoint_manifest":pin(checkpoint/"manifest.json"),"checkpoint_receipt":pin(checkpoint/"BUNDLE-RECEIPT.json"),
        "parser":{"version":packaging.__version__,"module":packaging.__file__,"wheel":pin(parser_path)},
        "host":{"python":sys.version,"sys_platform":sys.platform},
        "wheel_metadata_count":102,"source_metadata_count":1,"metadata_count":len(results),
        "requires_dist_count":sum(len(row["requirements"]) for row in results),
        "failure_count":len(failures),"failures":failures,"marker_variables":sorted(variables),
        "source_optional_kittentts":project["project"]["optional-dependencies"]["kittentts"],
        "distributions":results,"original_inputs":{name:pin(subset/name) for name in sorted(source_names)},
        "source_before":{name:pin(repo/name) for name in ["scripts/prepare_audio_device_environment.py","tests/test_audio_device_staging.py","scripts/prepare_audio_device_bundle.py","scripts/audio_device_bundle_lock.json"]},
        "original_metadata_rewritten":False,"wheels_installed":False,"network_accessed":False}
write_json("original-parser-scan.json",report)
log=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\audio-native-verification-resume-20261017\run-39070524219-raw\job.log")
rawlog=log.read_bytes()
(out/"observed-native-error-tail.log").write_bytes(b"\n".join(rawlog.split(b"\n")[-100:]))
print(json.dumps({key:report[key] for key in ["parser","wheel_metadata_count","source_metadata_count","requires_dist_count","failure_count","failures","marker_variables","source_optional_kittentts"]},indent=2))
print("receipt_sha256="+sha((out/"original-parser-scan.json").read_bytes()))
