#!/usr/bin/env bash
# Unpublished complete original Tokenizers/Hub/fsspec subset; no engine admission.
set -Eeuo pipefail
mode=host
if [[ "${1:-}" == --in-container ]]; then mode=container; shift; fi
[[ $# == 2 && "$1" == --out ]] || { echo "usage: $0 [--in-container] --out NEW_DIR" >&2; exit 2; }
out="$2"

if [[ "$mode" == host ]]; then
  case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM64 host required" >&2; exit 2 ;; esac
  packaging="$(cd "$(dirname "$0")/.." && pwd)"
  [[ ! -e "$out" && ! -L "$out" ]] || { echo "Use a new evidence directory" >&2; exit 2; }
  mkdir -p "$out"
  out="$(realpath "$out")"
  container=
  monitor_pid=
  finish_host() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
    if [[ -n "$monitor_pid" ]]; then wait "$monitor_pid" 2>/dev/null || true; fi
  }
  trap finish_host EXIT
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 -B - "$packaging" "$out" "$image" <<'PY_INPUTS'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("Advertised source head differs")
if json.loads((root / "manifest/release.json").read_bytes())["termux_image"] != sys.argv[3]:
    raise SystemExit("Review the immutable native image pin")
lock = json.loads((root / "scripts/neutts_tokenizers_runtime_lock.json").read_bytes())
names = {
    ".github/workflows/neutts-tokenizers-runtime.yml",
    "scripts/compatibility_probe_neutts_tokenizers_runtime.sh",
    "scripts/compatibility_probe_neutts_tokenizers_runtime.py",
    "scripts/prepare_neutts_tokenizers_runtime.py", "scripts/neutts_tokenizers_runtime_lock.json",
    "scripts/neutts_tokenizers_operations.py", "tests/test_neutts_tokenizers_runtime.py",
    "scripts/neutts_runtime_elf.py", "tests/test_neutts_runtime_elf.py",
    "scripts/neutts_rust_operations.py",
    "scripts/prepare_neutts_nonrust_runtime.py", "scripts/compatibility_probe_neutts_nonrust.py",
    "scripts/prepare_phonemizer_runtime.py", "scripts/compatibility_probe_phonemizer.py",
    "scripts/phonemizer_runtime_lock.json", "scripts/neutts_native_sources_lock.json",
    "scripts/compatibility_probe_neutts.sh", "scripts/compatibility_probe_neutts.py",
    "scripts/compatibility_probe_neutts_native.py",
    "scripts/prepare_neutts_core_python.py", "scripts/neutts_core_python_lock.json",
    "scripts/prepare_neutts_apt_snapshot.py", "scripts/neutts_apt_snapshot.sh",
    "scripts/validate_neutts_apt_python.py", "scripts/neutts_apt_python_metadata.json",
    "audit/neutts-runtime-index-20261017/InRelease", "audit/neutts-runtime-index-20261017/Packages.gz",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
    lock["handoff"]["path"], lock["frozen_graph"]["path"],
}
names.update(p["input_path"] for p in lock["packages"])
names.update(p["input_path"] for p in lock["apt_archives"])
for relative in ("vendor/termux-preparation", "audit/neutts-tokenizers-runtime-preparation-20261020"):
    names.update(path.relative_to(root).as_posix() for path in (root / relative).rglob("*") if path.is_file())
receipt = {
    "schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
    "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)},
    "purpose": "Complete original 25-distribution/29-edge Tokenizers, Hub and fsspec[http] runtime",
    "container_contract": {"cpus": 2, "memory_bytes": 6442450944, "pids": 512, "timeout_minutes": 35},
    "engine_installed": False, "model_downloaded": False,
    "production_admission_changed": False, "release_output": False,
}
with (out / "TOKENIZERS-PROBE-INPUTS.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, sort_keys=True, indent=2)
    stream.write("\n")
PY_INPUTS
  python3 -B "$packaging/scripts/prepare_neutts_apt_snapshot.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --out "$out/foundation-apt-inputs"
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/prepare_neutts_tokenizers_runtime.py" \
    --repo "$packaging" --out "$out/tokenizers-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  docker image inspect "$image" > "$out/TOKENIZERS-SOURCE-IMAGE.json"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-tokenizers-${GITHUB_RUN_ID:-local}-$$"
  docker create --name "$container" --network bridge --platform linux/arm64 --user 1000:1000 \
    --cpus 2 --memory 6g --pids-limit 512 --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/foundation-apt-inputs:/out/foundation-apt-inputs:ro" \
    -v "$out/tokenizers-inputs:/out/tokenizers-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_tokenizers_runtime.sh --in-container --out /out \
    > "$out/TOKENIZERS-CONTAINER-ID.txt"
  timeout --signal=TERM --kill-after=20s 35m docker start --attach "$container" \
    > "$out/tokenizers-native-probe.log" 2>&1 &
  monitor_pid=$!
  ready=false
  for ((attempt=0; attempt<1800; attempt++)); do
    if [[ -f "$out/TOKENIZERS-NETWORK-READY.json" ]]; then ready=true; break; fi
    if ! kill -0 "$monitor_pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    cat "$out/tokenizers-native-probe.log"
    echo "Native setup did not reach the offline runtime barrier" >&2
    exit 1
  fi
  docker network disconnect bridge "$container"
  docker inspect "$container" > "$out/TOKENIZERS-DISCONNECTED-CONTAINER.json"
  python3 -B - "$out" <<'PY_NETWORK'
import hashlib, json, pathlib, re, sys
out = pathlib.Path(sys.argv[1])
container_id = (out / "TOKENIZERS-CONTAINER-ID.txt").read_text().strip()
values = json.loads((out / "TOKENIZERS-DISCONNECTED-CONTAINER.json").read_bytes())
ready = json.loads((out / "TOKENIZERS-NETWORK-READY.json").read_bytes())
lock_sha = hashlib.sha256((out / "tokenizers-inputs/neutts_tokenizers_runtime_lock.json").read_bytes()).hexdigest()
if (not re.fullmatch(r"[0-9a-f]{64}", container_id) or len(values) != 1
        or values[0]["Id"] != container_id or values[0]["State"]["Running"] is not True
        or values[0]["NetworkSettings"]["Networks"] != {}
        or ready != {"schema_version": 1, "status": "ready-for-network-disconnect", "lock_sha256": lock_sha}):
    raise SystemExit("Owned container is not disconnected/running or original runtime barrier differs")
value = {"schema_version": 1, "status": "disconnected", "container_id": container_id,
         "remaining_networks": {}, "lock_sha256": lock_sha,
         "inspect_sha256": hashlib.sha256((out / "TOKENIZERS-DISCONNECTED-CONTAINER.json").read_bytes()).hexdigest(),
         "release_output": False}
temporary = out / ".TOKENIZERS-NETWORK-OFFLINE.tmp"
with temporary.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, sort_keys=True, indent=2)
    stream.write("\n")
temporary.rename(out / "TOKENIZERS-NETWORK-OFFLINE.json")
PY_NETWORK
  set +e
  wait "$monitor_pid"
  attached_status=$?
  set -e
  monitor_pid=
  cat "$out/tokenizers-native-probe.log"
  native_status="$(docker inspect "$container" --format '{{.State.ExitCode}}')"
  [[ "$attached_status" == 0 && "$native_status" == 0 ]]
  docker inspect "$container" > "$out/TOKENIZERS-COMPLETED-CONTAINER.json"
  python3 -B - "$out" <<'PY_RESULT'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
value = json.loads((out / "tokenizers-component/TOKENIZERS-COMPONENT-RESULT.json").read_bytes())
end = json.loads((out / "TOKENIZERS-EXIT.json").read_bytes())
if (value.get("status") != "passed" or value.get("node_count") != 25 or value.get("edge_count") != 29
        or value.get("engine_installed") is not False or value.get("release_output") is not False
        or end.get("stage") != "complete" or end.get("exit_code") != 0):
    raise SystemExit("Complete original Tokenizers runtime gate did not pass")
PY_RESULT
  exit 0
fi

[[ "$(id -u)" == 1000 && "$(uname -m)" == aarch64 ]]
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR="$PREFIX/tmp"
export PATH="$PREFIX/bin:/system/bin:/system/xbin" LD_LIBRARY_PATH="$PREFIX/lib"
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV _PYTHON_HOST_PLATFORM LD_PRELOAD APT_CONFIG
umask 022
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-tokenizers.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s,"release_output":false}\n' \
    "$stage" "$status" > "$out/TOKENIZERS-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"
stage=authenticated-original-extra-apt
source /probes/scripts/neutts_apt_snapshot.sh
neutts_apt_snapshot_open "$out/foundation-apt-inputs" "$work/signed-apt" "$out/TOKENIZERS-FROZEN-APT"
stage=isolated-tokenizers-runtime
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_tokenizers_runtime.py \
  --inputs "$out/tokenizers-inputs" --out "$out/tokenizers-component" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" --image-receipt "$out/TOKENIZERS-PROBE-INPUTS.json"
stage=complete
echo "NEUTTS_TOKENIZERS_RUNTIME_PASSED: exact 25-distribution runtime and actual local operations"
