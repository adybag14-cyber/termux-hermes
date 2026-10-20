from pathlib import Path
import hashlib,importlib.metadata,json,sys
root=Path(sys.argv[1])
out=Path(sys.argv[2])
before={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
import setuptools.build_meta
dynamic=setuptools.build_meta.get_requires_for_build_wheel(config_settings={})
after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
report={"schema_version":1,"scope":"Host metadata-only replay of original backend; no build_wheel or Cargo called","dynamic_requirements":dynamic,"backend_distributions":sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions()),"changed_original_files":[{"path":k,"before":v,"after":after.get(k)} for k,v in before.items() if after.get(k)!=v],"added_files":[k for k in after if k not in before]}
out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
