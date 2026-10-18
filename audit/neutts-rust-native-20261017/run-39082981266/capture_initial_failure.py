from __future__ import annotations
import concurrent.futures, datetime, hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017")
OUT = ROOT / "audit/neutts-rust-native-20261017/run-39082981266"
OUT.mkdir(parents=True, exist_ok=True)
REPO = "repos/adybag14-cyber/termux-hermes"
EXPECTED_HEAD = "123e70ee7ec9ff97b2cc82a05c13794d98e3e4b5"
requests = {
    "run.json": f"{REPO}/actions/runs/39082981266",
    "jobs.json": f"{REPO}/actions/runs/39082981266/jobs?per_page=100",
    "artifacts.json": f"{REPO}/actions/runs/39082981266/artifacts?per_page=100",
    "job-117543618809.log": f"{REPO}/actions/jobs/117543618809/logs",
    "job-117543619025.log": f"{REPO}/actions/jobs/117543619025/logs",
}
def get(item):
    name, endpoint = item
    proc = subprocess.run(["gh", "api", endpoint], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=50)
    if proc.returncode:
        raise RuntimeError(f"GitHub read-only capture failed: {name}, exit={proc.returncode}")
    path = OUT / name
    if path.exists() and path.read_bytes() != proc.stdout:
        raise RuntimeError(f"Refuse replacing prior capture: {name}")
    path.write_bytes(proc.stdout)
    row = {"path":path.relative_to(ROOT).as_posix(), "bytes":len(proc.stdout), "sha256":hashlib.sha256(proc.stdout).hexdigest()}
    return name, proc.stdout, row
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    got = list(pool.map(get, requests.items()))
data = {name: body for name, body, _ in got}
run = json.loads(data["run.json"])
assert run["id"] == 39082981266 and run["head_sha"] == EXPECTED_HEAD
assert run["path"] == ".github/workflows/neutts-rust-components.yml"
jobs = json.loads(data["jobs.json"])
assert {j["id"] for j in jobs["jobs"]} == {117543618809,117543619025}
artifacts = json.loads(data["artifacts.json"])
summary = {
    "schema":"native-rust-initial-failed-run-capture/v1",
    "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "run":{key:run[key] for key in ("id","head_sha","status","conclusion","event","created_at","updated_at","path")},
    "artifacts":[{key:a.get(key) for key in ("id","name","size_in_bytes","digest","expired","created_at","updated_at","workflow_run")} for a in artifacts["artifacts"]],
    "files":[row for _,_,row in got]
}
receipt = OUT / "initial-failed-run-capture.json"
if receipt.exists(): raise RuntimeError("Refuse replacing existing receipt")
receipt.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(summary,ensure_ascii=True))
for name,body,_ in got:
    if name.endswith(".log"):
        lines=body.decode("utf-8","replace").splitlines()
        indexes=[i for i,line in enumerate(lines) if any(word in line for word in ("Traceback", "ProbeError", "Error:", "RuntimeError", "failed", "FAILED"))]
        selected=set()
        for i in indexes[-8:]:
            selected.update(range(max(0,i-3),min(len(lines),i+13)))
        print(json.dumps({"log":name,"tail_lines":[lines[i] for i in sorted(selected)]},ensure_ascii=True))
