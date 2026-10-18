"""Read only the immutable native test image; no Docker execution or installation."""
import concurrent.futures,gzip,hashlib,json,pathlib,struct,tarfile,urllib.error,urllib.parse,urllib.request
BASE=pathlib.Path(__file__).parent/"apt-extensions-image-review-20261018"
IMAGE="termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303"
PREFIX="data/data/com.termux/files/usr/"
def sha(raw): return hashlib.sha256(raw).hexdigest()
def save(p,raw):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): assert p.read_bytes()==raw, p.name
    else: p.write_bytes(raw)
def main():
    manifest_raw=(BASE/"pinned-image-manifest.json").read_bytes()
    assert sha(manifest_raw)==IMAGE.split("sha256:")[1]
    manifest=json.loads(manifest_raw)
    config_raw=(BASE/"pinned-image-config.json").read_bytes()
    assert len(config_raw)==manifest["config"]["size"] and "sha256:"+sha(config_raw)==manifest["config"]["digest"]
    config=json.loads(config_raw)
    assert config["architecture"]=="arm64" and config["os"]=="linux"
    assert len(manifest["layers"])==len(config["rootfs"]["diff_ids"])==2
    token=json.loads(urllib.request.urlopen("https://auth.docker.io/token?service=registry.docker.io&scope=repository:termux/termux-docker:pull",timeout=15).read(32768))["token"]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw): return None
    layer_receipts=[]; files={}; metadata={}; inventories=[]
    for index,desc in enumerate(manifest["layers"]):
        assert desc["mediaType"]=="application/vnd.docker.image.rootfs.diff.tar.gzip"
        assert 0<desc["size"]<64*1024*1024
        layer=BASE/f"layer-{index}.tar.gz"
        if not layer.exists():
            req=urllib.request.Request("https://registry-1.docker.io/v2/termux/termux-docker/blobs/"+desc["digest"],headers={"Authorization":"Bearer "+token})
            try:
                with urllib.request.build_opener(NoRedirect).open(req,timeout=15) as f:
                    raw=f.read(desc["size"]+1)
                assert len(raw)==desc["size"] and "sha256:"+sha(raw)==desc["digest"]
                save(layer,raw)
            except urllib.error.HTTPError as e:
                assert e.code in (301,302,303,307,308)
                url=e.headers["Location"]; parsed=urllib.parse.urlparse(url)
                assert parsed.scheme=="https" and not parsed.username and not parsed.password
                assert parsed.hostname=="production.cloudfront.docker.com"
                size=desc["size"]; step=4*1024*1024
                ranges=[(start,min(start+step,size)-1) for start in range(0,size,step)]
                def fetch(bounds):
                    first,last=bounds
                    target=BASE/f"layer-{index}-chunk-{first:09d}-{last:09d}.bin"
                    if target.exists():
                        assert target.stat().st_size==last-first+1
                        return target
                    req=urllib.request.Request(url,headers={"Range":f"bytes={first}-{last}"})
                    with urllib.request.urlopen(req,timeout=20) as response:
                        assert response.status==206 and response.headers.get("Content-Range")==f"bytes {first}-{last}/{size}"
                        raw=response.read(last-first+2)
                    assert len(raw)==last-first+1
                    save(target,raw)
                    return target
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                    chunks=list(pool.map(fetch,ranges))
                raw=b"".join(p.read_bytes() for p in chunks)
                assert len(raw)==size and "sha256:"+sha(raw)==desc["digest"]
                save(layer,raw)
        raw=layer.read_bytes()
        assert len(raw)==desc["size"] and "sha256:"+sha(raw)==desc["digest"]
        uncompressed=hashlib.sha256(); expanded=0
        with gzip.open(layer,"rb") as f:
            while chunk:=f.read(1024*1024):
                expanded+=len(chunk); assert expanded<512*1024*1024
                uncompressed.update(chunk)
        assert "sha256:"+uncompressed.hexdigest()==config["rootfs"]["diff_ids"][index]
        inventory=[]; names=set(); whiteouts=[]
        with tarfile.open(layer,"r:gz") as t:
            for member in t:
                name=member.name.removeprefix("./")
                p=pathlib.PurePosixPath(name)
                assert not p.is_absolute() and ".." not in p.parts and "\\" not in name
                assert name not in names; names.add(name)
                row={"name":name,"type":member.type.decode("ascii"),"bytes":member.size,"mode":member.mode,"uid":member.uid,"gid":member.gid}
                if member.issym() or member.islnk(): row["linkname"]=member.linkname
                if p.name.startswith(".wh."): whiteouts.append(name)
                inventory.append(row)
                wanted_image=name.startswith(PREFIX+"opt/aosp/lib64/") or name==PREFIX+"opt/aosp/bin/linker64"
                wanted_metadata=name==PREFIX+"var/lib/dpkg/status" or (name.startswith(PREFIX+"var/lib/dpkg/info/aosp-libs.") and member.isfile())
                if wanted_image:
                    assert member.isfile(), name
                    blob=t.extractfile(member).read()
                    assert len(blob)==member.size
                    file_row={"path":"/"+name,"bytes":len(blob),"sha256":sha(blob),"mode":member.mode,"uid":member.uid,"gid":member.gid,"layer_index":index}
                    if blob[:4]==b"\x7fELF":
                        assert blob[4:7]==b"\x02\x01\x01"
                        etype,machine=struct.unpack_from("<HH",blob,16)
                        assert machine==183
                        file_row["elf"]={"class":64,"endianness":"little","machine":machine,"type":etype}
                    files[name]=file_row
                    save(BASE/"selected-image-files"/name,blob)
                if wanted_metadata:
                    blob=t.extractfile(member).read()
                    assert len(blob)==member.size
                    metadata[name]={"bytes":len(blob),"sha256":sha(blob),"layer_index":index}
                    save(BASE/"image-metadata"/name,blob)
        assert not whiteouts, whiteouts
        ledger=(json.dumps(inventory,indent=2,sort_keys=True)+"\n").encode()
        save(BASE/f"layer-{index}-member-inventory.json",ledger)
        layer_receipts.append({"index":index,"compressed":desc,"uncompressed_bytes":expanded,"diff_id":"sha256:"+uncompressed.hexdigest(),"members":len(inventory),"member_inventory_sha256":sha(ledger),"whiteouts":[]})
        inventories.append(inventory)
    assert not inventories[1], "Second layer must be empty; otherwise resolve overlay membership first"
    status_name=PREFIX+"var/lib/dpkg/status"
    status=(BASE/"image-metadata"/status_name).read_text()
    paragraphs=[p for p in status.split("\n\n") if p.startswith("Package: aosp-libs\n")]
    assert len(paragraphs)==1
    control={}
    for line in paragraphs[0].splitlines():
        if line.startswith((" ","\t")): continue
        key,sep,value=line.partition(": ")
        if sep: control[key]=value
    assert control["Package"]=="aosp-libs" and control["Architecture"]=="aarch64" and control["Status"]=="install ok installed"
    owner_list_name=PREFIX+"var/lib/dpkg/info/aosp-libs.list"
    owner_list=(BASE/"image-metadata"/owner_list_name).read_text().splitlines()
    for row in files.values():
        assert row["path"] in owner_list
        row["owner"]="aosp-libs"
        row["owner_version"]=control["Version"]
    icu=files[PREFIX+"opt/aosp/lib64/libicuuc.so"]
    assert "elf" in icu
    receipt={
      "schema_version":1,"status":"verified-immutable-image-members",
      "method":"Public OCI registry manifest/config identities, complete compressed layer SHA256 and uncompressed DiffIDs, exhaustive tar-member inventory and absence of overlay changes; no image execution",
      "image":IMAGE,"manifest":{"bytes":len(manifest_raw),"sha256":sha(manifest_raw)},
      "config":{"bytes":len(config_raw),"sha256":sha(config_raw),"architecture":config["architecture"],"os":config["os"]},
      "layers":layer_receipts,"image_package_control":control,"metadata":metadata,
      "image_native_files":sorted(files.values(),key=lambda r:r["path"]),
      "observed_missing_pin":icu,
      "native_component_admission":False,"image_executed":False,
      "signed_repository_archive_claim":False
    }
    payload=(json.dumps(receipt,indent=2,sort_keys=True)+"\n").encode()
    save(BASE/"PINNED-IMAGE-AOSP-MEMBERS.json",payload)
    print(json.dumps({"receipt":str(BASE/"PINNED-IMAGE-AOSP-MEMBERS.json"),"bytes":len(payload),"sha256":sha(payload),"layers":layer_receipts,"image_package_control":control,"observed_missing_pin":icu,"image_native_file_count":len(files)},indent=2))
if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__}))
        raise SystemExit(1)
