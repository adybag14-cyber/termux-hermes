"""Capture exact failed Rust native artifacts; credentials and redirect URLs stay in memory."""
from __future__ import annotations
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = "adybag14-cyber/termux-hermes"
RUN_ID = 39082981266
HEAD = "123e70ee7ec9ff97b2cc82a05c13794d98e3e4b5"
ROOT = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT = ROOT / "audit/neutts-rust-native-20261017/run-39082981266"
BASE = ROOT.parent / "neutts-rust-native-evidence-20261017" / str(RUN_ID)
EXPECTED = {
    12119747428: ("termux-neutts-rust-tiktoken-lock", 257951988, "c13dc2444ec54eaab34e51b85a9ce38d4debd826db31d9ba8d5b1b510f7b1ca5"),
    12119921806: ("termux-neutts-rust-locked-build", 559778211, "552da20e4f4cb9448a7a46596d9700adf367c0b92ad54f0f32f7b570d82bb0fa"),
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError("Existing captured bytes differ: " + path.name)
    else:
        with path.open("xb") as stream:
            stream.write(raw)

def gh(endpoint):
    return subprocess.check_output(["gh", "api", endpoint], timeout=25, stderr=subprocess.PIPE)

def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def obtain_redirect(artifact):
    expected = f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip"
    if artifact["archive_download_url"] != expected:
        raise RuntimeError("Unexpected artifact API origin")
    token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=10,
                                    stderr=subprocess.PIPE).strip()
    req = urllib.request.Request(expected, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "User-Agent": "termux-hermes-rust-evidence"})
    try:
        urllib.request.build_opener(NoRedirect()).open(req, timeout=15)
        raise RuntimeError("Expected authenticated artifact redirect")
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise RuntimeError("Artifact API did not redirect") from None
        target = exc.headers["Location"]
    parsed = urllib.parse.urlsplit(target)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or not parsed.hostname or not parsed.hostname.endswith((
                ".blob.core.windows.net", ".actions.githubusercontent.com", ".githubusercontent.com"))):
        raise RuntimeError("Unexpected signed-download origin")
    return target

def acquire(artifact):
    identity = artifact["id"]
    _, size, digest = EXPECTED[identity]
    target = BASE / f"artifact-{identity}-assembled.zip"
    if target.exists():
        if target.stat().st_size != size or sha_file(target) != digest:
            raise RuntimeError("Existing assembled archive differs")
        return target
    url = obtain_redirect(artifact)
    step = 4 * 1024 * 1024
    chunk_dir = BASE / f"artifact-{identity}-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    ranges = [(first, min(first + step, size) - 1) for first in range(0, size, step)]
    def fetch(bounds):
        first, last = bounds
        path = chunk_dir / f"{first:010d}-{last:010d}.bin"
        if path.exists():
            if path.stat().st_size != last - first + 1:
                raise RuntimeError("Existing range length differs")
            return path
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={
                    "Range": f"bytes={first}-{last}", "User-Agent": "termux-hermes-rust-evidence"})
                # The anonymous signed-origin request never receives the GitHub credential.
                with urllib.request.urlopen(req, timeout=20) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {first}-{last}/{size}":
                        raise RuntimeError("Range response identity differs")
                    raw = response.read(last - first + 2)
                if len(raw) != last - first + 1:
                    raise RuntimeError("Incomplete range")
                save(path, raw)
                return path
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise RuntimeError(f"Range transfer failed after three attempts at byte {first}") from None
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        chunks = list(pool.map(fetch, ranges))
    pending = target.with_suffix(".pending")
    if pending.exists():
        if pending.stat().st_size == size and sha_file(pending) == digest:
            pending.replace(target)
            return target
        raise RuntimeError("Existing incomplete assembled file needs explicit review")
    with pending.open("xb") as output:
        for chunk in chunks:
            with chunk.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    if pending.stat().st_size != size or sha_file(pending) != digest:
        raise RuntimeError("Whole artifact size or SHA256 differs")
    pending.replace(target)
    return target

def inspect(artifact, target, raw_jobs):
    identity = artifact["id"]
    name, size, digest = EXPECTED[identity]
    external = BASE / ("extracted-" + name)
    retained_root = AUDIT / ("raw-" + name)
    members = []
    with zipfile.ZipFile(target) as archive:
        items = archive.infolist()
        if len(items) > 200000 or sum(i.file_size for i in items) > 6 * 1024**3:
            raise RuntimeError("Archive expansion exceeds evidence bound")
        names = set()
        for item in items:
            member = PurePosixPath(item.filename)
            if (item.filename in names or not member.parts or member.is_absolute()
                    or ".." in member.parts or "\\" in item.filename or item.flag_bits & 1
                    or stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK):
                raise RuntimeError("Unsafe or duplicate archive member")
            names.add(item.filename)
            if item.is_dir():
                continue
            raw = archive.read(item)  # ZipFile independently validates the member CRC.
            if len(raw) != item.file_size:
                raise RuntimeError("Member size differs")
            portable = all(":" not in p and p not in (".", "..") for p in member.parts)
            input_cache = (len(member.parts) >= 3 and member.parts[:2] in {
                ("rust-inputs", "archives"), ("rust-inputs", "crates"), ("rust-inputs", "wheels"),
                ("rust-inputs", "apt-archives"), ("rust-inputs", "snapshot")})
            input_cache = input_cache or item.filename == "rust-inputs/neutts_rust_sources_lock.json"
            proof = (item.filename.endswith((".log", ".json", ".tsv", ".txt", ".xml"))
                     and "/sources/" not in item.filename and "/vendor/" not in item.filename
                     and "/cargo-home/" not in item.filename
                     and not item.filename.startswith("rust-inputs/"))
            extracted = portable and (input_cache or proof)
            retained = portable and proof and len(raw) <= 16 * 1024**2
            if extracted:
                save(external.joinpath(*member.parts), raw)
            if retained:
                save(retained_root.joinpath(*member.parts), raw)
            members.append({"name": item.filename, "bytes": len(raw), "sha256": sha(raw),
                            "crc32": f"{item.CRC:08x}", "external_copy": extracted,
                            "git_audit_raw_copy": retained})
    job = next(j for j in raw_jobs if ("tiktoken-lock" if "tiktoken-lock" in name else "locked-build") in j["name"])
    result = {
        "schema": "exact-rust-native-artifact-capture/v1",
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "run_id": RUN_ID, "head_sha": HEAD, "job_id": job["id"], "job_conclusion": job["conclusion"],
        "artifact_id": identity, "artifact_name": name, "artifact_bytes": size, "artifact_sha256": digest,
        "artifact_path": str(target), "external_extracted_root": str(external),
        "method": "Authenticated exact GitHub artifact API redirect; anonymous HTTPS byte ranges; whole size/SHA256; every ZIP member CRC and SHA256.",
        "all_member_crc_verified": True, "all_member_sha256_recorded": True,
        "source_or_lock_changed": False, "native_success_claimed": False,
        "members": members,
    }
    receipt = AUDIT / f"verified-artifact-{identity}.json"
    save(receipt, json_bytes(result))
    return {"artifact_id": identity, "bytes": size, "sha256": digest, "member_count": len(members),
            "external_copies": sum(x["external_copy"] for x in members),
            "raw_audit_copies": sum(x["git_audit_raw_copy"] for x in members),
            "receipt": {"path": receipt.relative_to(ROOT).as_posix(),
                        "bytes": receipt.stat().st_size, "sha256": sha_file(receipt)}}

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    raw_run = gh(f"repos/{REPO}/actions/runs/{RUN_ID}")
    run = json.loads(raw_run)
    if (run["id"] != RUN_ID or run["head_sha"] != HEAD or run["status"] != "completed"
            or run["path"] != ".github/workflows/neutts-rust-components.yml"):
        raise RuntimeError("Run identity/state differs")
    save(AUDIT / "run-api-final.json", raw_run)
    raw_jobs = gh(f"repos/{REPO}/actions/runs/{RUN_ID}/jobs")
    jobs = json.loads(raw_jobs)["jobs"]
    if len(jobs) != 2 or any(j["status"] != "completed" for j in jobs):
        raise RuntimeError("Expected two completed native stages")
    save(AUDIT / "jobs-api-final.json", raw_jobs)
    raw_artifacts = gh(f"repos/{REPO}/actions/runs/{RUN_ID}/artifacts")
    artifacts = json.loads(raw_artifacts)["artifacts"]
    if {a["id"] for a in artifacts} != set(EXPECTED):
        raise RuntimeError("Artifact identity set differs")
    save(AUDIT / "artifacts-api-final.json", raw_artifacts)
    results = []
    for artifact in sorted(artifacts, key=lambda a: a["size_in_bytes"]):
        name, size, digest = EXPECTED[artifact["id"]]
        if (artifact["name"] != name or artifact["size_in_bytes"] != size
                or artifact["digest"] != "sha256:" + digest or artifact["expired"]
                or artifact["workflow_run"]["head_sha"] != HEAD):
            raise RuntimeError("Artifact frozen identity differs")
        target = acquire(artifact)
        result = inspect(artifact, target, jobs)
        results.append(result)
        print(json.dumps(result), flush=True)
    save(AUDIT / "complete-artifact-capture-summary.json", json_bytes({
        "schema": "exact-rust-native-complete-artifact-capture/v1", "run_id": RUN_ID,
        "head_sha": HEAD, "artifact_count": len(results), "artifacts": results}))
    print(json.dumps({"status": "complete", "artifacts": len(results)}), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"capture_status": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
