from pathlib import Path
import importlib.util,io,tarfile,hashlib,json,struct,re
repo=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\termux-hermes-resume-20261017")
arc=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\audio-staging-input-audit-20261017\\libandroid-stub_30-2_aarch64.deb")
lock=json.loads((repo/"scripts/audio_device_bundle_lock.json").read_bytes())
spec=importlib.util.spec_from_file_location("p",repo/"scripts/prepare_audio_device_bundle.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.verify_file(arc,lock["opensles"]["archive"])
def elf(b):
 h=struct.unpack_from("<16sHHIQQQIHHHHHH",b)
 assert h[0][:6]==b"\x7fELF\x02\x01" and h[2]==183
 sh=[struct.unpack_from("<IIQQQQIIQQ",b,h[6]+i*h[11]) for i in range(h[12])]
 def data(s):return b[s[4]:s[4]+s[5]]
 def cstr(raw,off):return raw[off:raw.index(0,off)].decode()
 dyn=[]
 for s in sh:
  if s[1]!=6:continue
  st=data(sh[s[6]])
  for off in range(s[4],s[4]+s[5],16):
   tag,val=struct.unpack_from("<qQ",b,off)
   if tag in {1,14,15,29}:dyn.append({"tag":{1:"NEEDED",14:"SONAME",15:"RPATH",29:"RUNPATH"}[tag],"value":cstr(st,val)})
 syms=[]
 for s in sh:
  if s[1]!=11:continue
  st=data(sh[s[6]])
  for off in range(s[4],s[4]+s[5],s[9]):
   name,inf,other,idx,val,size=struct.unpack_from("<IBBHQQ",b,off)
   name=cstr(st,name)
   if name and (idx==0 or "platform_" in name):syms.append({"name":name,"defined":idx!=0})
 strings=[x.decode() for x in re.findall(rb"[ -~]{4,}",b) if any(k in x for k in (b"/system/",b"/apex/",b"/data/",b"dlopen",b"namespace"))]
 return {"machine":h[2],"dynamic":dyn,"symbols":syms,"loader_strings":strings}
report={"archive":{"size":arc.stat().st_size,"sha256":m.file_digest(arc)},"members":{}}
with tarfile.open(fileobj=io.BytesIO(m.deb_data(arc)),mode="r:*") as tf:
 for member in tf:
  if member.isfile() and member.name.endswith(".so"):
   raw=tf.extractfile(member).read()
   report["members"][member.name]={"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"elf":elf(raw)}
out=Path("C:\\Users\\adyba\\docker-chatgpt-devbox\\workspace\\audio-staging-input-audit-20261017\\platform-namespace-routing-20261017")
out.mkdir(exist_ok=True)
p=out/"frozen-stub-elf-trace.json";assert not p.exists();p.write_bytes((json.dumps(report,indent=2,sort_keys=True)+"\n").encode())
print(json.dumps({"receipt":str(p),"size":p.stat().st_size,"sha256":m.file_digest(p),"members":report["members"]}))
