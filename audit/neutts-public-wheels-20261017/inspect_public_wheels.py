"""Verify frozen public NeuTTS wheels without importing their package code."""
from __future__ import annotations
import argparse, collections, concurrent.futures, hashlib, importlib.util, json
from pathlib import Path
import struct, time, traceback, urllib.request, zipfile
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.tags import compatible_tags

DESIGN_SHA = "d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68"
HELPER_SHA = "0f5db491b6a2d2cbe13e908fe24613b62f9db38ac2f0d33968328c499038a9a1"
ROUTES = {"public_pure_wheel_pending_verification", "official_android_wheel_pending_verification"}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, "Existing evidence differs: " + str(path)
    else:
        with path.open("xb") as stream: stream.write(raw)
def save(path, value): write_new(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
def req_key(text):
    r = Requirement(text)
    return (canonicalize_name(r.name), tuple(sorted(canonicalize_name(x) for x in r.extras)),
            str(r.specifier), r.url or "", str(r.marker) if r.marker else "")
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
def acquire(node, directory, deadline, caches):
    pin = node["artifact"]; dest = directory / pin["filename"]
    assert pin["url"].startswith("https://files.pythonhosted.org/packages/")
    assert pin["packagetype"] == "bdist_wheel" and pin["yanked"] is False
    assert Path(pin["filename"]).name == pin["filename"]
    for cache in caches:
        candidate = cache / pin["filename"]
        if candidate.exists():
            assert candidate.is_file() and not candidate.is_symlink()
            value = candidate.read_bytes()
            assert len(value) == pin["bytes"] and sha(value) == pin["sha256"]
            write_new(dest, value)
            break
    if not dest.exists():
        req = urllib.request.Request(pin["url"], headers={"User-Agent": "termux-hermes-frozen-wheel-audit", "Accept-Encoding": "identity"})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response, dest.open("xb") as stream:
            assert response.status == 200
            size = 0
            while chunk := response.read(256 * 1024):
                assert time.monotonic() < deadline
                size += len(chunk); assert size <= pin["bytes"]
                stream.write(chunk)
    raw = dest.read_bytes()
    assert len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], node["name"]
    return dest
def elf_facts(raw):
    assert len(raw) >= 64 and raw[:6] == b"\x7fELF\x02\x01"
    assert struct.unpack_from("<H", raw, 16)[0] == 3
    assert struct.unpack_from("<H", raw, 18)[0] == 183
    offset = struct.unpack_from("<Q", raw, 32)[0]
    stride, count = struct.unpack_from("<HH", raw, 54)
    assert stride == 56 and 0 < count < 1024 and offset + stride * count <= len(raw)
    programs = [struct.unpack_from("<IIQQQQQQ", raw, offset + i * stride) for i in range(count)]
    dynamic = [p for p in programs if p[0] == 2]; assert len(dynamic) == 1
    p = dynamic[0]; assert p[2] + p[5] <= len(raw) and p[5] % 16 == 0
    entries = []
    for at in range(p[2], p[2] + p[5], 16):
        tag, value = struct.unpack_from("<qQ", raw, at)
        if tag == 0: break
        entries.append((tag, value))
    else: raise ValueError("Unterminated ELF dynamic table")
    addresses = [v for k, v in entries if k == 5]
    sizes = [v for k, v in entries if k == 10]
    assert len(addresses) == len(sizes) == 1 and sizes[0] > 0
    loads = [p for p in programs if p[0] == 1 and p[3] <= addresses[0] and addresses[0] + sizes[0] <= p[3] + p[5]]
    assert len(loads) == 1
    start = loads[0][2] + addresses[0] - loads[0][3]
    assert start + sizes[0] <= len(raw)
    strings = raw[start:start + sizes[0]]
    def string(index):
        assert 0 <= index < len(strings)
        end = strings.index(b"\0", index)
        return strings[index:end].decode("utf-8", "strict")
    result = {"class": 64, "endianness": "little", "type": 3, "machine": 183}
    for tag, name in ((1, "needed"), (14, "soname"), (15, "rpath"), (29, "runpath")):
        result[name] = [string(v) for k, v in entries if k == tag]
    assert not any(x in {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2"} or "musl" in x for x in result["needed"])
    return result
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, action="append", default=[])
    args = parser.parse_args()
    root, out = args.repo.resolve(), args.out.absolute()
    assert not out.exists()
    caches = tuple(p.resolve() for p in args.cache)
    assert all(p.is_dir() and not out.is_relative_to(p) and not p.is_relative_to(out) for p in caches)
    design_path = root / "scripts/neutts_runtime_closure_design.json"
    helper_path = root / "scripts/prepare_neutts_rust_sources.py"
    assert sha(design_path.read_bytes()) == DESIGN_SHA
    assert sha(helper_path.read_bytes()) == HELPER_SHA
    design = json.loads(design_path.read_bytes())
    nodes = [n for n in design["nodes"] if n["route"] in ROUTES]
    assert len(nodes) == 46 and sum(n["route"] == "public_pure_wheel_pending_verification" for n in nodes) == 45
    assert len({n["name"] for n in nodes}) == len(nodes)
    out.mkdir(parents=True); (out / "downloads").mkdir()
    write_new(out / "frozen-wheel-verifier.py", helper_path.read_bytes())
    spec = importlib.util.spec_from_file_location("_frozen_public_wheel_helper", out / "frozen-wheel-verifier.py")
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    deadline = time.monotonic() + 600
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda n: acquire(n, out / "downloads", deadline, caches), nodes))
    verified, failures, owners = [], [], collections.defaultdict(list)
    for node, path in zip(nodes, paths):
        try:
            pin = {k: node["artifact"][k] for k in ("filename", "bytes", "sha256", "url")}
            facts = helper.wheel_facts(path, artifact=pin)
            assert (facts["name"], facts["version"]) == (node["name"], node["version"])
            filename_name, filename_version, _, filename_tags = parse_wheel_filename(path.name)
            assert (str(filename_name), str(filename_version)) == (node["name"], node["version"])
            assert set(map(str, filename_tags)) == set(facts["wheel"]["tags"])
            assert str(SpecifierSet(facts["requires_python"] or "")) == str(SpecifierSet(node["requires_python"] or ""))
            assert sorted(map(req_key, facts["requires_dist"])) == sorted(map(req_key, node["requires_dist"]))
            manifest, embedded, native = [], [], []
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
                for info in archive.infolist():
                    if info.is_dir(): continue
                    raw = archive.read(info)
                    row = {"path": info.filename, "bytes": len(raw), "sha256": sha(raw)}
                    manifest.append(row); owners[info.filename].append({"name": node["name"], "sha256": row["sha256"]})
                    if raw.startswith(b"\x7fELF"):
                        native.append({**row, "elf": elf_facts(raw)})
                    if info.filename.lower().endswith((".pt", ".pth", ".ckpt", ".pt.tar", ".pth.tar", ".ckpt.tar", ".safetensors", ".onnx", ".gguf")):
                        embedded.append(row)
                    if info.filename in {facts["wheel"][k] for k in ("metadata_member", "wheel_member", "record_member")}:
                        write_new(out / "text" / node["name"] / Path(info.filename).name, raw)
                    if node["name"] == "resemble-perth" and info.filename.endswith(".py"):
                        write_new(out / "text" / node["name"] / "source" / info.filename, raw)
            if node["route"] == "public_pure_wheel_pending_verification":
                assert facts["wheel"]["root_is_purelib"] and not native and not facts["native_members"]
                assert all(t.abi == "none" and t.platform == "any" for t in filename_tags)
                target_tags = set(compatible_tags(python_version=(3, 14), interpreter="cp314",
                                                  platforms=["android_24_arm64_v8a"]))
                assert filename_tags & target_tags, "Pure wheel has no compatible Python3.14 tag"
            else:
                assert node["name"] == "xxhash" and node["version"] == "4.0.1"
                assert facts["wheel"]["root_is_purelib"] is False
                assert facts["wheel"]["tags"] == ["cp314-cp314-android_24_arm64_v8a"]
                assert len(native) == len(facts["native_members"]) == 1
                assert native[0]["path"].startswith("xxhash/") and native[0]["path"].endswith(".so")
            manifest.sort(key=lambda x: x["path"])
            save(out / "text" / node["name"] / "MEMBER-FILES.json", manifest)
            row = {"route": node["route"], "original_metadata_witness_matches": True,
                   "metadata_source": node["metadata_source"], "facts": facts,
                   "native_elf_members": native, "embedded_checkpoint_members": embedded,
                   "member_manifest_sha256": sha((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())}
            verified.append(row); save(out / "text" / node["name"] / "VERIFIED.json", row)
            print(json.dumps({"name": node["name"], "status": "verified", "files": len(manifest), "embedded_checkpoint_files": len(embedded)}), flush=True)
        except Exception as exc:
            failure = {"name": node["name"], "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            failures.append(failure); save(out / "text" / node["name"] / "FAILURE.json", failure)
            print(json.dumps({"name": node["name"], "status": "failed", "type": type(exc).__name__, "message": str(exc)}), flush=True)
    collisions = {k: v for k, v in owners.items() if len(v) > 1}
    result = {"schema_version": 1, "status": "verified-original-wheel-inputs" if not failures else "failed",
              "frozen_design_sha256": DESIGN_SHA, "frozen_helper_sha256": HELPER_SHA,
              "original_pure_wheel_count": 45, "official_android_wheel_count": 1,
              "artifact_bytes": sum(n["artifact"]["bytes"] for n in nodes),
              "verified": verified, "failures": failures, "overlapping_member_paths": collisions,
              "package_code_imported": False, "native_runtime_tested": False,
              "complete_engine_admitted": False, "default_speech_model_weights_downloaded": False,
              "public_watermark_checkpoint_present": any(r["embedded_checkpoint_members"] for r in verified),
              "original_torchao_is_not_runtime_admitted": True,
              "runtime_torchao_gate": "audit/neutts-torchao-native-20261017/run-39076217293.json",
              "release_output": False}
    save(out / "VERIFIED-PUBLIC-WHEELS.json", result)
    print(json.dumps({"status": result["status"], "verified": len(verified), "failed": len(failures), "collision_count": len(collisions), "out": str(out)}))
    return 1 if failures else 0
if __name__ == "__main__":
    raise SystemExit(main())
