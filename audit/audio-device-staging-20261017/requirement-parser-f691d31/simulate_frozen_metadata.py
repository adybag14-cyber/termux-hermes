from pathlib import Path
import copy, hashlib, importlib.metadata as metadata, json, sys, tomllib, traceback
from unittest.mock import patch
out=Path(sys.argv[1])
repo=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-resume-20261017")
def pin(path):
 raw=path.read_bytes()
 return {"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
scan=json.loads((out/"original-parser-scan.json").read_text())
manifest=json.loads((out/"checkpoint-manifest.json").read_text())
parser=out/"packaging-26.0-py3-none-any.whl"
assert pin(parser)==scan["parser"]["wheel"]
sys.path[:0]=[str(parser),str(repo)]
import packaging
assert packaging.__version__=="26.0" and str(parser) in packaging.__file__
import packaging.markers
from scripts import prepare_audio_device_environment as native
subset=out/"original-input-subset"
inputs={name:pin(subset/name) for name in scan["original_inputs"]}
source_before=pin(repo/"scripts/prepare_audio_device_environment.py")
binding=native.frozen_psutil_binding(subset,manifest)
all_distributions={}
total=0
adapted=[]
for row in scan["distributions"]:
 path=out/row["metadata_path"]
 assert pin(path)==row["metadata"]
 dist=metadata.PathDistribution(path.parent)
 assert native.normalized_name(dist.metadata["Name"])==row["parent"] and dist.version==row["version"]
 all_distributions[row["parent"]]=dist
 for raw in dist.requires or []:
  requirement,proof=native.parse_frozen_requirement(row["parent"],raw,row["version"],direct_url_binding=binding)
  if proof is not None:adapted.append(proof)
  total+=1
assert total==710 and len(adapted)==2
project=tomllib.loads((subset/"app/pyproject.toml").read_text())["project"]
for proof in adapted:
 assert project["optional-dependencies"]["kittentts"].count(proof["project_requirement"])==1
 assert proof["parsed_requirement"]==proof["raw_requirement"].replace("; "," ; ",1)
expected=native.expected_versions(manifest["lock"])
selected={name:dist for name,dist in all_distributions.items() if name!="setuptools"}
assert len(selected)==102 and {name:dist.version for name,dist in selected.items()}==expected
environment={
 "implementation_name":"cpython","implementation_version":"3.14.6","os_name":"posix",
 "platform_machine":"aarch64","platform_python_implementation":"CPython","platform_release":"",
 "platform_system":"Android","platform_version":"","python_full_version":"3.14.6",
 "python_version":"3.14","sys_platform":"android"}
extras=manifest["lock"]["candidate"]["extras"]+["audio-io"]
report={"schema_version":1,"status":"running","scope":"Host metadata simulation only; not native runtime validation",
 "native_runtime_executed":False,"network_accessed":False,"wheels_installed":False,
 "parser":{"version":packaging.__version__,"module":packaging.__file__,"wheel":pin(parser)},
 "original_scan":pin(out/"original-parser-scan.json"),"helper":source_before,
 "marker_environment":environment,"selected_extras":extras,"versions":expected,
 "all_metadata_count":len(all_distributions),"all_requirement_count":total,"selected_distribution_count":len(selected),
 "selected_requirement_count":sum(len(dist.requires or []) for dist in selected.values()),
 "build_only_excluded":"setuptools","original_source_binding":binding,"adaptations":adapted,
 "platform_release_version_policy":"Blank values are simulation assumptions, not observed device facts; the sole release marker is branch-inactive under sys_platform=android. Repeat checks vary release below.",
 "platform_implementation_source":pin(subset/"tools/python/data/data/com.termux/files/usr/lib/python3.14/platform.py"),
 "source_inputs_before":inputs}
try:
 parsing={}
 with patch.object(packaging.markers,"default_environment",return_value=environment),patch.object(native.platform,"python_version",return_value="3.14.6"):
  graph=native.dependency_graph(selected,expected,extras,direct_url_binding=binding,parse_evidence=parsing)
  second={}
  assert native.dependency_graph(selected,expected,extras,direct_url_binding=binding,parse_evidence=second)==graph
  assert second==parsing
  pm_names={"packaging","tomli-w","truststore","ruamel-yaml"}
  pm_expected={name:expected[name] for name in pm_names}
  pm_graph=native.dependency_graph({name:selected[name] for name in pm_names},pm_expected,[])
 release_checks=[]
 for value in ["16","android-unobserved-release"]:
  with patch.object(packaging.markers,"default_environment",return_value={**environment,"platform_release":value}),patch.object(native.platform,"python_version",return_value="3.14.6"):
   assert native.dependency_graph(selected,expected,extras,direct_url_binding=binding)==graph
  release_checks.append({"platform_release":value,"active_graph_identical":True})
 report.update(status="passed",active_edge_count=len(graph),active_dependency_edges=graph,
               requirement_parsing=parsing,deterministic_repetition=True,
               private_manager={"versions":pm_expected,"active_dependency_edges":pm_graph,"direct_url_binding_supplied":False},
               platform_release_insensitivity=release_checks)
except Exception as exc:
 report.update(status="failed",error={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()})
finally:
 report["source_inputs_after"]={name:pin(subset/name) for name in inputs}
 report["source_inputs_unchanged"]=report["source_inputs_after"]==inputs
 report["helper_after"]=pin(repo/"scripts/prepare_audio_device_environment.py")
 assert report["source_inputs_unchanged"] and report["helper_after"]==source_before
 (out/"metadata-simulation-1.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({key:report[key] for key in ["status","all_metadata_count","all_requirement_count","selected_distribution_count","selected_requirement_count","marker_environment","selected_extras"]},indent=2))
 print(json.dumps({"active_edge_count":report.get("active_edge_count"),"error":report.get("error"),
                   "receipt":pin(out/"metadata-simulation-1.json")},indent=2))
raise SystemExit(0 if report["status"]=="passed" else 1)
