"""Capture a completed, exact-head compatibility run without changing GitHub."""
import argparse, concurrent.futures, hashlib, json, pathlib, subprocess, urllib.error, urllib.parse, urllib.request, zipfile

REPO = "adybag14-cyber/termux-hermes"
def digest(raw): return hashlib.sha256(raw).hexdigest()
def gh(endpoint):
    return subprocess.check_output(["gh", "api", endpoint], timeout=15)
def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            if path.name.endswith("-api.json"):
                save(path.with_name(path.stem + "-" + digest(raw)[:16] + path.suffix), raw)
            else: raise RuntimeError("existing evidence differs: " + path.name)
    else: path.write_bytes(raw)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=int)
    parser.add_argument("expected_head")
    args = parser.parse_args()
    base = pathlib.Path(__file__).parent / "apt-extensions-native-evidence-20261018" / str(args.run_id)
    base.mkdir(parents=True, exist_ok=True)
    run_raw = gh(f"repos/{REPO}/actions/runs/{args.run_id}")
    run = json.loads(run_raw)
    assert run["id"] == args.run_id and run["head_sha"] == args.expected_head
    assert run["status"] == "completed" and run["path"] == ".github/workflows/neutts-apt-extensions.yml"
    save(base / "run-api.json", run_raw)
    jobs_raw = gh(f"repos/{REPO}/actions/runs/{args.run_id}/jobs")
    jobs = json.loads(jobs_raw)["jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == "completed"
    save(base / "jobs-api.json", jobs_raw)
    log = gh(f"repos/{REPO}/actions/jobs/{jobs[0]['id']}/logs")
    save(base / "native-job.log", log)
    api = gh(f"repos/{REPO}/actions/runs/{args.run_id}/artifacts")
    save(base / "artifacts-api.json", api)
    artifacts = json.loads(api)["artifacts"]
    assert len(artifacts) == 1 and artifacts[0]["name"] == "termux-neutts-apt-extensions"
    a = next(x for x in artifacts if x["name"] == "termux-neutts-apt-extensions")
    assert not a["expired"]
    assert a["workflow_run"]["head_sha"] == args.expected_head
    assert a["digest"].startswith("sha256:") and 0 < a["size_in_bytes"] < 512 * 1024 * 1024
    target = base / "artifact.zip"
    if target.exists():
        assert target.stat().st_size == a["size_in_bytes"] and digest(target.read_bytes()) == a["digest"][7:]
    else:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=10).strip()
        assert a["archive_download_url"] == f"https://api.github.com/repos/{REPO}/actions/artifacts/{a['id']}/zip"
        request = urllib.request.Request(a["archive_download_url"], headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "User-Agent": "termux-hermes-compatibility-audit"})
        try:
            urllib.request.build_opener(NoRedirect).open(request, timeout=10)
            raise RuntimeError("expected authenticated artifact redirect")
        except urllib.error.HTTPError as exc:
            assert exc.code in (301, 302, 303, 307, 308)
            url = exc.headers["Location"]
        parsed = urllib.parse.urlparse(url)
        assert parsed.scheme == "https" and not parsed.username and not parsed.password
        assert parsed.hostname.endswith((".blob.core.windows.net", ".actions.githubusercontent.com", ".githubusercontent.com"))
        size, step = a["size_in_bytes"], 4 * 1024 * 1024
        ranges = [(start, min(start + step, size) - 1) for start in range(0, size, step)]
        def fetch(bounds):
            first, last = bounds
            dest = base / f"chunk-{first:09d}-{last:09d}.bin"
            if dest.exists():
                assert dest.stat().st_size == last - first + 1
                return dest
            req = urllib.request.Request(url, headers={"Range": f"bytes={first}-{last}", "User-Agent": "termux-hermes-compatibility-audit"})
            with urllib.request.urlopen(req, timeout=15) as response:
                assert response.status == 206 and response.headers.get("Content-Range") == f"bytes {first}-{last}/{size}"
                raw = response.read(last - first + 2)
            assert len(raw) == last - first + 1
            save(dest, raw)
            return dest
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            chunks = list(pool.map(fetch, ranges))
        raw = b"".join(p.read_bytes() for p in chunks)
        assert len(raw) == size and digest(raw) == a["digest"][7:]
        save(target, raw)
    members = []
    with zipfile.ZipFile(target) as z:
        items = z.infolist()
        assert len(items) < 10000 and sum(x.file_size for x in items) < 512 * 1024 * 1024
        assert len({x.filename for x in items}) == len(items)
        assert z.testzip() is None
        for item in items:
            rel = pathlib.PurePosixPath(item.filename)
            assert not rel.is_absolute() and ".." not in rel.parts and "\\" not in item.filename
            assert not item.is_dir() and not item.flag_bits & 1
            assert ((item.external_attr >> 16) & 0o170000) != 0o120000
            raw = z.read(item)
            retained = not ("/sources/" in item.filename or "/wheels/" in item.filename or item.filename.endswith((".whl", ".deb", ".tar.gz", ".tar.xz", ".crate", ".so")) or "/bundle/" in item.filename or item.filename.startswith("native-inputs/artifacts/"))
            if retained: save(base / "extracted" / item.filename, raw)
            members.append({"name": item.filename, "bytes": len(raw), "sha256": digest(raw), "crc": item.CRC, "extracted": retained})
    verified = {
        "run_id": args.run_id, "head_sha": args.expected_head, "job_id": jobs[0]["id"],
        "conclusion": run["conclusion"], "artifact_id": a["id"],
        "artifact_bytes": a["size_in_bytes"], "artifact_sha256": a["digest"][7:],
        "method": "Authenticated GitHub API redirect, anonymous HTTPS byte ranges, full digest reassembly and every ZIP member CRC.",
        "all_member_crc_verified": True, "members": members,
        "native_job_log": {"bytes": len(log), "sha256": digest(log)},
    }
    save(base / "verified-artifact.json", (json.dumps(verified, indent=2) + "\n").encode())
    results = {}
    for path in sorted((base / "extracted").rglob("*RESULT.json")):
        name = path.relative_to(base / "extracted").as_posix()
        result = json.loads(path.read_bytes())
        results[name] = {k: result.get(k) for k in ("status", "stage", "exit_code", "error")}
        if "cases" in result:
            results[name]["case_count"] = len(result["cases"])
    print(json.dumps({"identity": {k: v for k, v in verified.items() if k != "members"},
                      "member_count": len(members), "retained_count": sum(r["extracted"] for r in members),
                      "results": results}, indent=2))
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"capture_status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)
