"""Read-only bounded artifact retrieval and complete member verification."""
import concurrent.futures,datetime,gzip,hashlib,json,pathlib,stat,subprocess,sys,time,urllib.request,urllib.error,urllib.parse,zipfile
sys.stdout.reconfigure(encoding="utf-8")
base=pathlib.Path(sys.argv[1])
run_id=int(sys.argv[2]);artifact_id=int(sys.argv[3]);size=int(sys.argv[4]);expected_sha=sys.argv[5]
assert (run_id,artifact_id,size,expected_sha)==(39450032929,12278206483,416408782,"d39ff082c5ee1de4c0b2c9363e74db976927bff6afe8eee570d4805e44862b9e")
assert base.name=="run-39450032929"
def retain(name,raw):
 p=base/name
 if p.exists():assert p.read_bytes()==raw, "Existing original differs: "+name
 else:p.write_bytes(raw)
 return {"path":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
api_jobs=[
("RUN-TERMINAL.json","repos/adybag14-cyber/termux-hermes/actions/runs/39450032929"),
("JOBS-TERMINAL.json","repos/adybag14-cyber/termux-hermes/actions/runs/39450032929/jobs?filter=all&per_page=100"),
("ARTIFACTS-TERMINAL.json","repos/adybag14-cyber/termux-hermes/actions/runs/39450032929/artifacts?per_page=100"),
("JOB-118722085474.log","repos/adybag14-cyber/termux-hermes/actions/jobs/118722085474/logs")]
def api_fetch(row):
 name,endpoint=row
 p=base/name
 raw=p.read_bytes() if p.exists() else subprocess.check_output(["gh","api",endpoint])
 return {"endpoint":endpoint,**retain(name,raw)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 fetched=list(pool.map(api_fetch,api_jobs))
run=json.loads((base/"RUN-TERMINAL.json").read_bytes())
jobs=json.loads((base/"JOBS-TERMINAL.json").read_bytes())
artifacts=json.loads((base/"ARTIFACTS-TERMINAL.json").read_bytes())
head="88e2810572a85f1050909ee8373527e983927766"
assert run["id"]==run_id and run["head_sha"]==head and run["conclusion"]=="failure" and run["run_attempt"]==1
job=[j for j in jobs["jobs"] if j["id"]==118722085474]
assert len(job)==1 and job[0]["head_sha"]==head and job[0]["conclusion"]=="failure"
item=[a for a in artifacts["artifacts"] if a["id"]==artifact_id]
assert len(item)==1 and item[0]["size_in_bytes"]==size and item[0]["digest"]=="sha256:"+expected_sha
assert item[0]["workflow_run"]["id"]==run_id and item[0]["workflow_run"]["head_sha"]==head
receipt={"schema":"original-native-failure-api-fetch/v1","run_id":run_id,"job_id":118722085474,"head_sha":head,"artifact_id":artifact_id,"files":fetched,"read_only_github":True,"release_output":False}
retain("FETCH-RECEIPT.json",(json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode())
started=time.monotonic();block=8*1024*1024
parts=base/"whole-ranges";parts.mkdir(exist_ok=True)
prefix=base/"artifact.zip.partial"
prefix_bytes=prefix.stat().st_size if prefix.exists() else 0
if prefix.exists():
 assert prefix_bytes<=size
 with prefix.open("rb") as stream:
  for i in range(prefix_bytes//block):
   raw=stream.read(block);assert len(raw)==block
   path=parts/f"{i:03d}.bin"
   if path.exists():assert path.read_bytes()==raw
   else:path.write_bytes(raw)
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
token=subprocess.check_output(["gh","auth","token"],stderr=subprocess.DEVNULL,text=True).strip()
request=urllib.request.Request(f"https://api.github.com/repos/adybag14-cyber/termux-hermes/actions/artifacts/{artifact_id}/zip",
 headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
try:
 urllib.request.build_opener(NoRedirect).open(request,timeout=30)
 raise RuntimeError("Expected authenticated archive redirect")
except urllib.error.HTTPError as error:
 if error.code!=302:raise RuntimeError("GitHub archive request status "+str(error.code)) from None
 url=error.headers["Location"]
del token,request
parsed=urllib.parse.urlparse(url)
assert parsed.scheme=="https" and parsed.hostname and (
 parsed.hostname.endswith(".blob.core.windows.net") or
 parsed.hostname.endswith(".githubusercontent.com") or
 parsed.hostname.endswith(".actions.githubusercontent.com"))
count=(size+block-1)//block
def fetch(i):
 start=i*block;end=min(size,(i+1)*block)-1;length=end-start+1;path=parts/f"{i:03d}.bin"
 if path.exists():
  assert path.stat().st_size==length
  return
 for attempt in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"Range":f"bytes={start}-{end}"}),timeout=60) as response:
    assert response.status==206 and response.headers["Content-Range"]==f"bytes {start}-{end}/{size}"
    raw=response.read(length+1)
   assert len(raw)==length
   temp=parts/f"{i:03d}.tmp";temp.write_bytes(raw);temp.replace(path)
   return
  except Exception:
   if attempt==2:raise RuntimeError("Artifact range failed: "+str(i)) from None
   time.sleep(1+attempt)
print(json.dumps({"stage":"parallel-ranges","run_id":run_id,"range_count":count,"workers":12,"cached":len(list(parts.glob("*.bin"))),"preserved_prefix_bytes":prefix_bytes}),flush=True)
completed=0
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
 for future in concurrent.futures.as_completed([pool.submit(fetch,i) for i in range(count)]):
  future.result();completed+=1
  if completed%8==0 or completed==count:print(json.dumps({"run_id":run_id,"completed_ranges":completed,"total_ranges":count}),flush=True)
path=base/"artifact.zip";assert not path.exists()
hash_value=hashlib.sha256()
with path.open("xb") as stream:
 for i in range(count):
  raw=(parts/f"{i:03d}.bin").read_bytes();hash_value.update(raw);stream.write(raw)
assert path.stat().st_size==size and hash_value.hexdigest()==expected_sha
rows=[]
with zipfile.ZipFile(path) as archive:
 entries=archive.infolist();assert 1<=len(entries)<=10000
 assert len({i.filename for i in entries})==len(entries)
 assert sum(i.file_size for i in entries)<3_000_000_000
 for item in entries:
  name=pathlib.PurePosixPath(item.filename)
  assert item.orig_filename==item.filename and not name.is_absolute()
  assert ".." not in name.parts and "\\" not in item.filename and ":" not in item.filename and "\0" not in item.filename
  assert name.as_posix()==item.filename.rstrip("/")
  assert stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR)
  assert not item.flag_bits&1 and item.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)
  assert item.file_size<512*1024*1024
  digest=hashlib.sha256();total=0
  with archive.open(item) as stream:
   while chunk:=stream.read(1024*1024):digest.update(chunk);total+=len(chunk)
  assert total==item.file_size
  rows.append({"path":item.filename,"bytes":total,"compressed_bytes":item.compress_size,
               "sha256":digest.hexdigest(),"crc32":f"{item.CRC:08x}","compression":item.compress_type,
               "unix_mode":item.external_attr>>16})
raw=(json.dumps(rows,sort_keys=True,separators=(",",":"))+"\n").encode()
inventory=base/"FULL-MEMBER-INVENTORY.json.gz";inventory.write_bytes(gzip.compress(raw,mtime=0))
proof={"schema":"native-artifact-complete-verification/v1","run_id":run_id,
"head_sha":"88e2810572a85f1050909ee8373527e983927766","artifact_id":artifact_id,
"whole_archive_verified":True,"bytes":size,"sha256":hash_value.hexdigest(),
"member_count":len(rows),"all_members_crc_size_sha256_verified":True,
"uncompressed_bytes":sum(x["bytes"] for x in rows),
"inventory_json_bytes":len(raw),"inventory_json_sha256":hashlib.sha256(raw).hexdigest(),
"inventory_gzip_bytes":inventory.stat().st_size,"inventory_gzip_sha256":hashlib.sha256(inventory.read_bytes()).hexdigest(),
"range_block_bytes":block,"range_count":count,"range_workers":12,"preserved_sequential_prefix_bytes":prefix_bytes,
"verified_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"elapsed_seconds":round(time.monotonic()-started,3),
"path":str(path),"native_receipts_not_yet_semantically_reviewed":True,"release_output":False}
(base/"FULL-DOWNLOAD-VERIFIED.json").write_bytes((json.dumps(proof,indent=2,sort_keys=True)+"\n").encode())
print(json.dumps(proof),flush=True)
