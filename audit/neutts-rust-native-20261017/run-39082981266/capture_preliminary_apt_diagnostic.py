"""Read only bounded diagnostic members while the full exact archive capture runs.
Member CRCs are checked, but whole-artifact verification remains explicitly pending.
"""
from __future__ import annotations
import datetime, hashlib, io, json, pathlib, runpy, urllib.request, zipfile
HERE = pathlib.Path(__file__).resolve().parent
capture = runpy.run_path(str(HERE / "capture_exact_rust_artifacts.py"), run_name="capture_reference_only")
artifact_id = 12119747428
artifacts = json.loads((HERE / "artifacts.json").read_bytes())["artifacts"]
artifact = next(a for a in artifacts if a["id"] == artifact_id)
name, size, digest = capture["EXPECTED"][artifact_id]
assert artifact["name"] == name and artifact["size_in_bytes"] == size
assert artifact["digest"] == "sha256:" + digest
assert artifact["workflow_run"]["head_sha"] == capture["HEAD"]
url = capture["obtain_redirect"](artifact)

class RangeReader(io.RawIOBase):
    def __init__(self): self.pos, self.total, self.calls = 0,0,0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self,offset,whence=0):
        target = offset if whence == 0 else self.pos + offset if whence == 1 else size + offset
        if target < 0 or target > size: raise ValueError("Bounded evidence seek")
        self.pos = target
        return target
    def read(self,count=-1):
        count = size-self.pos if count < 0 else min(count,size-self.pos)
        if count == 0: return b""
        if count > 16*1024*1024 or self.total+count > 32*1024*1024 or self.calls >= 30:
            raise RuntimeError("Bounded diagnostic range exceeded")
        first,last=self.pos,self.pos+count-1
        req=urllib.request.Request(url,headers={"Range":f"bytes={first}-{last}","User-Agent":"termux-hermes-rust-diagnostic"})
        with urllib.request.urlopen(req,timeout=15) as response:
            if response.status != 206 or response.headers.get("Content-Range") != f"bytes {first}-{last}/{size}":
                raise RuntimeError("Diagnostic range response differs")
            raw=response.read(count+1)
        if len(raw) != count: raise RuntimeError("Diagnostic range length differs")
        self.pos += count; self.total += count; self.calls += 1
        return raw

def main():
    reader=RangeReader()
    rows=[]
    with zipfile.ZipFile(reader) as archive:
        names=archive.namelist()
        if len(names) != len(set(names)): raise RuntimeError("Duplicate ZIP member")
        selected=[n for n in names if "rust-apt-install" in n or n.endswith("RUST-COMPONENTS-RESULT.json") or n.endswith("rust-apt-simulate.stdout.log")]
        if not 3 <= len(selected) <= 10: raise RuntimeError("Unexpected diagnostic member set")
        for name in selected:
            member=pathlib.PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name: raise RuntimeError("Unsafe diagnostic name")
            info=archive.getinfo(name)
            if info.file_size > 3*1024*1024 or info.flag_bits&1: raise RuntimeError("Invalid diagnostic member")
            raw=archive.read(info)
            out=HERE/"preliminary-range-proof"/pathlib.Path(*member.parts)
            capture["save"](out,raw)
            row={"member":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"crc32":f"{info.CRC:08x}",
                 "path":out.relative_to(capture["ROOT"]).as_posix()}
            rows.append(row)
            print(json.dumps({"member":name,"text":raw.decode("utf-8","replace")},ensure_ascii=True))
    receipt={"schema":"bounded-native-rust-diagnostic-range-capture/v1","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "run_id":capture["RUN_ID"],"head_sha":capture["HEAD"],"artifact_id":artifact_id,
             "artifact_expected_sha256":digest,"whole_artifact_verified":False,
             "whole_artifact_capture":"separate detached exact complete archive capture in progress",
             "member_crc_verified":True,"range_bytes_read":reader.total,"range_requests":reader.calls,"members":rows}
    capture["save"](HERE/"preliminary-range-proof.json",capture["json_bytes"](receipt))
    print(json.dumps(receipt))
if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__}))
        raise SystemExit(1)
