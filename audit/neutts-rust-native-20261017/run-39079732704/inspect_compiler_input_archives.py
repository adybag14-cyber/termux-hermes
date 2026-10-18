"""Read exact APT archives to diagnose every original native Rust compiler input."""
from __future__ import annotations
import ast
from collections import defaultdict
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import struct
import sys
import tarfile
from urllib.request import Request, urlopen
from email.parser import BytesParser
from email.policy import compat32

ROOT=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT=ROOT/"audit/neutts-rust-native-20261017/run-39079732704"
BASE=ROOT.parent/"neutts-rust-native-evidence-20261017/39079732704/supplemental-apt-inputs"
CACHE=ROOT.parent/"neutts-rust-native-evidence-20261017/39077868589/extracted-termux-neutts-rust-locked-build/rust-inputs/apt-archives"
PREFIX="/data/data/com.termux/files/usr"
BASELINE_LOCK_SHA="c72d8bfa5f9ae86205443b2c7c19892be77a2879ec7604ccd77aeda2a94775af"
BASELINE_RUNNER_SHA="a07d0ec7d1daf20491df69795c5f1ac8d10e7c2ea1e2b756c977c6783f8ce502"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        assert path.read_bytes()==raw, "Existing evidence differs"
    else:
        path.write_bytes(raw)

def json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()

def load_native():
    path=ROOT/"scripts/compatibility_probe_neutts_rust.py"
    raw=path.read_bytes()
    assert sha(raw)==BASELINE_RUNNER_SHA
    spec=importlib.util.spec_from_file_location("_rust_original_path_archive_review",path)
    native=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=native
    spec.loader.exec_module(native)
    return native,raw

def ar_parts(raw):
    assert raw[:8]==b"!<arch>\n"
    offset=8
    while offset<len(raw):
        header=raw[offset:offset+60]
        assert len(header)==60 and header[58:60]==b"\x60\n"
        size=int(header[48:58]); assert 0<=size<=len(raw)-offset-60
        name=header[:16].decode("ascii").strip().rstrip("/")
        value=raw[offset+60:offset+60+size]
        offset+=60+size+size%2
        yield name,value
    assert offset==len(raw)

def static_native_paths(source):
    function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=="native_controls")
    paths=[]
    def path_expr(node,variable=None,value=None):
        if isinstance(node,ast.Name) and node.id=="PREFIX": return PREFIX
        if isinstance(node,ast.Name) and node.id==variable: return value
        if isinstance(node,ast.Constant) and isinstance(node.value,str): return node.value
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
            return path_expr(node.left,variable,value)+"/"+path_expr(node.right,variable,value)
        raise AssertionError("Unexpected original path-expression shape")
    for node in function.body:
        value=None
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=="paths":
            value=node.value
        elif isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name) and node.target.id=="paths":
            value=node.value
        if isinstance(value,ast.List):
            paths.extend(path_expr(item) for item in value.elts)
        elif isinstance(value,ast.ListComp) and isinstance(value.generators[0].iter,ast.Tuple):
            assert len(value.generators)==1 and not value.generators[0].ifs
            gen=value.generators[0]
            paths.extend(path_expr(value.elt,gen.target.id,name) for name in ast.literal_eval(gen.iter))
        elif value is not None:
            assert isinstance(value,ast.ListComp) and isinstance(value.generators[0].iter,ast.Call)
            assert ast.unparse(value)=="[p for p in std.iterdir() if p.is_file() and (not p.is_symlink())]"
    assert len(paths)==14 and len(set(paths))==14
    return paths

def elf_identity(raw):
    assert raw[:6]==b"\x7fELF\x02\x01" and len(raw)>=64
    elf_type,machine=struct.unpack_from("<HH",raw,16)
    assert machine==183
    phoff=struct.unpack_from("<Q",raw,32)[0]
    phsize,phcount=struct.unpack_from("<HH",raw,54)
    assert phsize==56 and phoff+phsize*phcount<=len(raw)
    loads=[]; dynamic=[]
    for idx in range(phcount):
        ptype,flags,offset,virtual,physical,filesz,memsz,align=struct.unpack_from("<IIQQQQQQ",raw,phoff+idx*phsize)
        assert offset+filesz<=len(raw)
        if ptype==1: loads.append((virtual,offset,filesz))
        if ptype==2:
            for pos in range(offset,offset+filesz,16):
                tag,value=struct.unpack_from("<QQ",raw,pos)
                if tag==0: break
                dynamic.append((tag,value))
    tables=[v for t,v in dynamic if t==5]; lengths=[v for t,v in dynamic if t==10]
    assert len(tables)==len(lengths)==1
    offsets=[o+tables[0]-v for v,o,s in loads if v<=tables[0]<v+s]
    assert len(offsets)==1 and offsets[0]+lengths[0]<=len(raw)
    strings=raw[offsets[0]:offsets[0]+lengths[0]]
    needed=[]
    for tag,value in dynamic:
        if tag!=1: continue
        assert value<len(strings) and b"\0" in strings[value:]
        needed.append(strings[value:].split(b"\0",1)[0].decode("ascii"))
    return {"elf_class":64,"endianness":"little","machine":machine,"elf_type":elf_type,"needed":needed}

def main():
    native,source=load_native()
    lock_raw=(ROOT/"scripts/neutts_rust_sources_lock.json").read_bytes()
    assert sha(lock_raw)==BASELINE_LOCK_SHA
    lock=json.loads(lock_raw); existing=lock["build_apt"]["packages"]
    assert len(existing)==46
    snapshot=ROOT/"audit/neutts-runtime-index-20261017"
    snap={}
    for p in lock["build_apt"]["snapshot"]:
        raw=(snapshot/p["filename"]).read_bytes()
        assert len(raw)==p["bytes"] and sha(raw)==p["sha256"]
        snap[p["filename"]]=raw
    rows=[]
    for paragraph in gzip.decompress(snap["Packages.gz"]).split(b"\n\n"):
        entry=BytesParser(policy=compat32).parsebytes(paragraph)
        if entry.get("Package")=="openssl-tool" and entry.get("Version")=="1:3.6.5" and entry.get("Architecture")=="aarch64":
            rows.append((paragraph,entry))
    assert len(rows)==1
    raw_row,row=rows[0]
    for field in ("Package","Version","Architecture","Filename","Size","SHA256","Depends"):
        assert len(row.get_all(field))==1
    p={"architecture":"aarch64","bytes":278628,"depends":"openssl (= 1:3.6.5)",
       "filename":"pool/main/o/openssl-tool/openssl-tool_1:3.6.5_aarch64.deb",
       "in_foundation":False,"name":"openssl-tool","pre_depends":"",
       "sha256":"91b6fd0e86f2585447a44c42a496e8c4da364ff3d7b13bec236a7e65be108109",
       "url":"https://packages.termux.dev/apt/termux-main/pool/main/o/openssl-tool/openssl-tool_1:3.6.5_aarch64.deb",
       "version":"1:3.6.5"}
    for field,key in (("Package","name"),("Version","version"),("Architecture","architecture"),
                      ("Filename","filename"),("Size","bytes"),("SHA256","sha256"),("Depends","depends")):
        assert row[field]==str(p[key])
    openssl=next(x for x in existing if x["name"]=="openssl")
    assert openssl["version"]=="1:3.6.5" and p["depends"]=="openssl (= "+openssl["version"]+")"
    save(AUDIT/"openssl-tool-original-index-paragraph.txt",raw_row+b"\n")
    target=BASE/Path(p["filename"]).name.replace(":","%3A")
    if target.exists():
        raw=target.read_bytes()
    else:
        with urlopen(Request(p["url"],headers={"User-Agent":"termux-hermes-compiler-input-review"}),timeout=30) as response:
            assert response.geturl()==p["url"] and response.status==200
            raw=response.read(p["bytes"]+1)
        assert len(raw)==p["bytes"] and sha(raw)==p["sha256"]
        save(target,raw)
    assert len(raw)==p["bytes"] and sha(raw)==p["sha256"]
    pins=sorted([*existing,p],key=lambda p:p["name"])
    selection=native.verify_selected_apt_index(gzip.decompress(snap["Packages.gz"]),pins)
    table=defaultdict(list); controls={}
    for pin in pins:
        path=target if pin["name"]=="openssl-tool" else CACHE/Path(pin["filename"]).name.replace(":","%3A")
        raw=path.read_bytes()
        assert len(raw)==pin["bytes"] and sha(raw)==pin["sha256"]
        parts=list(ar_parts(raw))
        assert sum(name.startswith("data.tar.") for name,_ in parts)==1
        assert sum(name.startswith("control.tar.") for name,_ in parts)==1
        for name,value in parts:
            if not name.startswith(("data.tar.","control.tar.")): continue
            with tarfile.open(fileobj=io.BytesIO(value),mode="r|*") as archive:
                seen=set()
                for item in archive:
                    name_path="/"+item.name.removeprefix("./").lstrip("/")
                    assert name_path not in seen
                    seen.add(name_path)
                    if name.startswith("data.tar."):
                        if item.isdir(): continue
                        assert item.isfile() or item.issym() or item.islnk()
                        table[name_path].append({"package":pin["name"],"type":"file" if item.isfile() else "symlink" if item.issym() else "hardlink",
                                                 "bytes":item.size,"linkname":item.linkname})
                    elif item.name.removeprefix("./")=="control":
                        assert item.isfile()
                        control_raw=archive.extractfile(item).read()
                        m=BytesParser(policy=compat32).parsebytes(control_raw)
                        assert m["Package"]==pin["name"] and m["Version"]==pin["version"] and m["Architecture"]==pin["architecture"]
                        controls[pin["name"]]=control_raw
                        if pin["name"]=="openssl-tool":
                            assert m.get_all("Depends")==[pin["depends"]]
                            save(AUDIT/"openssl-tool-original-control.txt",control_raw)
    original=static_native_paths(source)
    std=PREFIX+"/lib/rustlib/aarch64-linux-android/lib"
    std_files=[path for path,entries in table.items() if str(PurePosixPath(path).parent)==std and any(x["type"]=="file" for x in entries)]
    assert std_files
    wanted=original+sorted(std_files)
    selected=[]; by_owner=defaultdict(set); baseline_missing=[]
    for path in wanted:
        current=path; chain=[]
        for _ in range(16):
            assert current.startswith(PREFIX+"/"), ("Escaped archive input",path,current)
            records=table.get(current,[])
            assert len(records)==1, ("Missing or multiply owned archive input",path,current,records)
            entry=records[0]
            if entry["type"]=="file": break
            assert entry["type"]=="symlink", ("Unexpected archive hardlink",path,current)
            chain.append({"path":current,**entry})
            current=posixpath.normpath(entry["linkname"] if entry["linkname"].startswith("/") else posixpath.join(posixpath.dirname(current),entry["linkname"]))
        else: raise AssertionError("Archive input link loop")
        by_owner[entry["package"]].add(current)
        row={"requested_path":path,"resolved_archive_path":current,"package":entry["package"],"bytes":entry["bytes"],"symlink_chain":chain}
        selected.append(row)
        if entry["package"]=="openssl-tool": baseline_missing.append(path)
    assert baseline_missing==[PREFIX+"/bin/openssl"]
    contents={}
    for owner,paths in sorted(by_owner.items()):
        pin=next(p for p in pins if p["name"]==owner)
        archive_path=target if owner=="openssl-tool" else CACHE/Path(pin["filename"]).name.replace(":","%3A")
        for path,value in native.ar_data_members(archive_path,pin,paths).items():
            contents[path]=value
    for row in selected:
        value=contents[row["resolved_archive_path"]]
        assert len(value)==row["bytes"]
        row["sha256"]=sha(value)
    executable=contents[PREFIX+"/bin/openssl"]
    identity=elf_identity(executable)
    assert identity["elf_type"]==3
    assert {"libssl.so.3","libcrypto.so.3"}.issubset(identity["needed"])
    for name in ("libssl.so.3","libcrypto.so.3"):
        assert len(table[PREFIX+"/lib/"+name])==1 and table[PREFIX+"/lib/"+name][0]["package"]=="openssl"
    result={"schema":"native-rust-original-compiler-input-archive-review/v1",
            "failed_run_id":39079732704,"failed_head_sha":"3109530049338f8a4fe063d5ad08bbae57f7e95f",
            "baseline_lock_sha256":BASELINE_LOCK_SHA,"baseline_runner_sha256":BASELINE_RUNNER_SHA,
            "existing_archive_count":46,"existing_archive_records_changed":False,"new_archive_count":1,
            "source_records_changed":False,"snapshot":lock["build_apt"]["snapshot"],
            "host_openpgp_verification_claimed":False,"selected_index":selection,
            "supplemental_archive":p,"supplemental_cache_path":str(target),
            "baseline_static_requested_paths_missing_from_original_archive_set":baseline_missing,
            "static_requested_path_count":len(original),"rust_standard_library_requested_path_count":len(std_files),
            "all_requested_paths_in_47_archive_set_verified":True,"requested_paths":selected,
            "openssl_tool_elf":identity,"native_install_or_execution_claimed":False}
    save(AUDIT/"compiler-input-archive-review.json",json_bytes(result))
    save(AUDIT/"openssl-tool-selected-input.json",json_bytes(p))
    print(json.dumps({k:v for k,v in result.items() if k!="requested_paths"},sort_keys=True))
    print(json.dumps({"receipt_bytes":(AUDIT/"compiler-input-archive-review.json").stat().st_size,
                      "receipt_sha256":sha((AUDIT/"compiler-input-archive-review.json").read_bytes()),
                      "path_count":len(selected),"resolved_file_count":len(contents)},sort_keys=True))

if __name__=="__main__":
    main()
