"""Capture the exact completed Tiktoken native stage; credentials and redirect URLs stay in memory."""
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
RUN_ID = 39084939992
HEAD = "fe857011db52cccd3d7bede48523a77481d8fab9"
ROOT = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
AUDIT = ROOT / "audit/neutts-rust-native-20261017/run-39084939992"
BASE = ROOT.parent / "neutts-rust-native-evidence-20261017" / str(RUN_ID)
EXPECTED = {
    12119853598: ("termux-neutts-rust-tiktoken-lock", 270247477, "7c8fe4aabb20e0dcc6eb4f450c08a4ca087f0db0d734f55ba177d4e6d5a6b9c8"),
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
            captured_source = (len(member.parts) >= 4 and member.parts[:3]
                               == ("rust-components", "captured-tiktoken-inputs", "sources"))
            captured_crate = (len(member.parts) == 4 and member.parts[:3]
                              == ("rust-components", "captured-tiktoken-inputs", "crates"))
            input_cache = input_cache or captured_source or captured_crate
            proof = (item.filename.endswith((".log", ".json", ".tsv", ".txt", ".xml"))
                     and "/sources/" not in item.filename and "/vendor/" not in item.filename
                     and "/cargo-home/" not in item.filename
                     and not item.filename.startswith("rust-inputs/"))
            extracted = portable and (input_cache or proof)
            retained = portable and (proof or (captured_source and member.name == "Cargo.lock")) and len(raw) <= 16 * 1024**2
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
        "capture_modified_source_or_lock": False, "job_success_observed": job["conclusion"] == "success",
        "tiktoken_lock_requires_separate_review": True,
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
    if (run["id"] != RUN_ID or run["head_sha"] != HEAD or run["status"] not in ("in_progress", "completed")
            or run["path"] != ".github/workflows/neutts-rust-components.yml"):
        raise RuntimeError("Run identity/state differs")
    save(AUDIT / "run-api-tiktoken-capture.json", raw_run)
    raw_jobs = gh(f"repos/{REPO}/actions/runs/{RUN_ID}/jobs?per_page=100")
    jobs = json.loads(raw_jobs)["jobs"]
    if {j["id"] for j in jobs} != {117549405973,117549406160}:
        raise RuntimeError("Native stage identity set differs")
    selected_job = next(j for j in jobs if j["id"] == 117549406160)
    if selected_job["status"] != "completed" or selected_job["conclusion"] != "success":
        raise RuntimeError("Tiktoken capture stage is not completed successfully")
    save(AUDIT / "jobs-api-tiktoken-capture.json", raw_jobs)
    save(AUDIT / "job-117549406160.log", gh(f"repos/{REPO}/actions/jobs/117549406160/logs"))
    raw_artifacts = gh(f"repos/{REPO}/actions/runs/{RUN_ID}/artifacts?per_page=100")
    artifacts = json.loads(raw_artifacts)["artifacts"]
    selected = [a for a in artifacts if a["id"] in EXPECTED]
    if len(selected) != 1:
        raise RuntimeError("Expected completed Tiktoken artifact")
    save(AUDIT / "artifacts-api-tiktoken-capture.json", raw_artifacts)
    artifact = selected[0]
    name, size, digest = EXPECTED[artifact["id"]]
    if (artifact["name"] != name or artifact["size_in_bytes"] != size
            or artifact["digest"] != "sha256:" + digest or artifact["expired"]
            or artifact["workflow_run"]["head_sha"] != HEAD):
        raise RuntimeError("Artifact frozen identity differs")
    target = acquire(artifact)
    result = inspect(artifact, target, jobs)
    print(json.dumps(result), flush=True)
    save(AUDIT / "complete-tiktoken-stage-capture-summary.json", json_bytes({
        "schema": "exact-native-tiktoken-stage-artifact-capture/v1", "run_id": RUN_ID,
        "head_sha": HEAD, "completed_stage_only": True, "job_id": selected_job["id"],
        "job_conclusion": selected_job["conclusion"], "artifact": result,
        "new_cargo_lock_reviewed_or_admitted": False, "subsequent_tiktoken_build": False}))
    print(json.dumps({"status": "complete", "completed_stage_only": True}), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"capture_status": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
