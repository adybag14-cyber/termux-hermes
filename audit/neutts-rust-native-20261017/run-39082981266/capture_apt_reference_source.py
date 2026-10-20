import base64, concurrent.futures, datetime, hashlib, json, pathlib, subprocess
root=pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
out=root/"audit/neutts-rust-native-20261017/run-39082981266/apt-reference-source"
out.mkdir(parents=True,exist_ok=True)
def api(endpoint): return json.loads(subprocess.check_output(["gh","api",endpoint],cwd=root,stderr=subprocess.PIPE,timeout=20))
tag=api("repos/Debian/apt/git/tags/9f13a18744ccbe058433597cce17a44b90930635")
assert tag["tag"]=="3.0.3" and tag["object"]["type"]=="commit"
commit=tag["object"]["sha"]
paths=["apt-pkg/acquire-item.cc","apt-pkg/contrib/strutl.cc"]
def capture(path):
    obj=api("repos/Debian/apt/contents/"+path+"?ref="+commit)
    assert obj["path"]==path and obj["encoding"]=="base64"
    body=base64.b64decode(obj["content"],validate=False)
    assert len(body)==obj["size"]
    dest=out/pathlib.Path(path).name
    if dest.exists(): assert dest.read_bytes()==body
    else: dest.write_bytes(body)
    text=body.decode("utf-8")
    lines=text.splitlines()
    needles=["StoreFilename = QuoteString", 'QuoteString(Version.VerStr()', 'QuoteString(Version.Arch()', "string QuoteString(", 'hex = "0123456789abcdef"']
    selected=set()
    for i,line in enumerate(lines):
        if any(n in line for n in needles): selected.update(range(max(0,i-3),min(len(lines),i+30)))
    print(json.dumps({"path":path,"relevant_lines":[{"line":i+1,"text":lines[i]} for i in sorted(selected)]},ensure_ascii=True))
    return {"path":dest.relative_to(root).as_posix(),"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),"upstream_path":path,"blob_sha":obj["sha"]}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: files=list(pool.map(capture,paths))
receipt={"schema":"read-only-apt-cache-semantics-reference/v1","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"upstream":"https://github.com/Debian/apt","reference_tag":"3.0.3","commit_sha":commit,"tag_object_sha":tag["sha"],"scope":"Upstream cache naming source reference; exact native behavior is separately observed in run39082981266. This does not assert the container APT version.","files":files}
(out/"reference-source.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(receipt))
