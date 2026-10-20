#!/usr/bin/env bash
# Unpublished original 116-dependency runtime; NeuTTS engine admission remains excluded.
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
  host_work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-complete-host.XXXXXX")"
  container=
  monitor_pid=
  finish_host() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
    if [[ -n "$monitor_pid" ]]; then wait "$monitor_pid" 2>/dev/null || true; fi
    rm -rf -- "$host_work"
  }
  trap finish_host EXIT
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 -B - "$packaging" "$out" "$image" <<'PY_INPUTS'
import hashlib, importlib.util, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("Advertised source head differs")
if json.loads((root / "manifest/release.json").read_text())["termux_image"] != sys.argv[3]:
    raise SystemExit("Review the immutable native image pin")
lock = json.loads((root / "scripts/neutts_complete_runtime_lock.json").read_text())
names = {pin["path"] for pin in lock["source_files"]}
names.update(p["origin"]["retained_path"] for p in lock["packages"] if p["origin"]["kind"] == "native-handoff")
names.update((
    ".github/workflows/neutts-complete-runtime.yml",
    "scripts/compatibility_probe_neutts_complete_runtime.sh", "scripts/compatibility_probe_neutts_complete_runtime.py",
    "scripts/prepare_neutts_complete_runtime.py", "scripts/neutts_complete_runtime_lock.json",
    "scripts/compatibility_probe_neutts.sh", "scripts/compatibility_probe_neutts.py",
    "scripts/prepare_neutts_core_python.py", "scripts/fetch_compatibility_candidate.py",
))
receipt = {
    "schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
    "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)},
    "purpose": "Unchanged scientific foundation and complete complete NeuTTS dependency 116-node/183-edge runtime",
    "container_contract": {"cpus": 2, "memory_bytes": 6442450944, "pids": 512, "timeout_minutes": 60},
    "default_speech_model_downloaded": False, "release_output": False,
    "production_admission_changed": False,
}
(out / "COMPLETE-PROBE-INPUTS.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY_INPUTS
  python3 -B "$packaging/scripts/prepare_neutts_apt_snapshot.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --out "$out/foundation-apt-inputs"
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/fetch_compatibility_candidate.py" --out "$host_work/candidate"
  mkdir "$out/main-candidate-proof"
  for receipt in candidate-receipt.json CANDIDATE-IDENTITY.json venv-selection.json; do
    cp -- "$host_work/candidate/$receipt" "$out/main-candidate-proof/$receipt"
  done
  python3 -B "$packaging/scripts/prepare_neutts_complete_runtime.py" \
    --foundation-inputs "$out/foundation-apt-inputs" \
    --main-deb "$host_work/candidate/hermes-agent_0.22.2-1_aarch64.deb" \
    --cache "$out/python-wheelhouse" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --cache "$packaging/audit/neutts-tokenizers-runtime-preparation-20261020/apt-archives" \
    --cache "$packaging/audit/neutts-complete-runtime-preparation-20261020/apt-archives" \
    --out "$out/complete-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  docker image inspect "$image" > "$out/COMPLETE-SOURCE-IMAGE.json"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-complete-${GITHUB_RUN_ID:-local}-$$"
  docker create --name "$container" --platform linux/arm64 --network bridge --user 1000:1000 \
    --cpus 2 --memory 6g --pids-limit 512 --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/foundation-apt-inputs:/out/foundation-apt-inputs:ro" \
    -v "$out/complete-inputs:/out/complete-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_complete_runtime.sh --in-container --out /out \
    > "$out/COMPLETE-CONTAINER-ID.txt"
  timeout --signal=TERM --kill-after=20s 60m docker start --attach "$container" \
    > "$out/complete-native-probe.log" 2>&1 &
  monitor_pid=$!
  ready=false
  for ((attempt=0; attempt<3000; attempt++)); do
    if [[ -f "$out/COMPLETE-NETWORK-READY.json" ]]; then ready=true; break; fi
    if ! kill -0 "$monitor_pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    cat "$out/complete-native-probe.log"
    echo "Native setup did not reach the offline public runtime barrier" >&2
    exit 1
  fi
  docker network disconnect bridge "$container"
  docker inspect "$container" > "$out/COMPLETE-DISCONNECTED-CONTAINER.json"
  python3 -B - "$out" <<'PY_NETWORK'
import hashlib, json, pathlib, re, sys
out = pathlib.Path(sys.argv[1])
container_id = (out / "COMPLETE-CONTAINER-ID.txt").read_text().strip()
values = json.loads((out / "COMPLETE-DISCONNECTED-CONTAINER.json").read_text())
if (not re.fullmatch(r"[0-9a-f]{64}", container_id) or len(values) != 1
        or values[0].get("Id") != container_id
        or values[0]["NetworkSettings"]["Networks"] != {} or values[0]["State"]["Running"] is not True):
    raise SystemExit("Container still connected or not running")
lock_sha = hashlib.sha256((out / "complete-inputs/neutts_complete_runtime_lock.json").read_bytes()).hexdigest()
ready = json.loads((out / "COMPLETE-NETWORK-READY.json").read_bytes())
if ready != {"schema_version": 1, "status": "ready-for-network-disconnect", "lock_sha256": lock_sha}:
    raise SystemExit("Original complete runtime barrier differs")
value = {"schema_version": 1, "status": "disconnected", "container": values[0],
         "container_id": container_id, "remaining_networks": {}, "lock_sha256": lock_sha,
         "inspect_sha256": hashlib.sha256((out / "COMPLETE-DISCONNECTED-CONTAINER.json").read_bytes()).hexdigest(),
         "release_output": False}
temporary = out / ".COMPLETE-NETWORK-OFFLINE.tmp"
temporary.write_text(json.dumps(value, indent=2) + "\n")
temporary.rename(out / "COMPLETE-NETWORK-OFFLINE.json")
PY_NETWORK
  set +e
  wait "$monitor_pid"
  attached_status=$?
  set -e
  monitor_pid=
  cat "$out/complete-native-probe.log"
  native_status="$(docker inspect "$container" --format '{{.State.ExitCode}}')"
  [[ "$attached_status" == 0 && "$native_status" == 0 ]]
  docker inspect "$container" > "$out/COMPLETE-COMPLETED-CONTAINER.json"
  python3 -B - "$out/COMPLETE-COMPONENT-RESULT.json" <<'PY_RESULT'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
if (value.get("status") != "passed" or value.get("stage") != "complete"
        or value.get("actual_runtime_distribution_count") != 116 or value.get("active_edge_count") != 183
        or value.get("wheel_count") != 105 or value.get("apt_python_payloads") != 11
        or value.get("neutts_engine_installed") is not False or value.get("release_output") is not False):
    raise SystemExit("Complete complete NeuTTS dependency native gate did not pass")
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
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV _PYTHON_HOST_PLATFORM LD_PRELOAD CMAKE_TOOLCHAIN_FILE NUMBA_DISABLE_JIT APT_CONFIG
umask 022
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-complete.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s,"release_output":false}\n' \
    "$stage" "$status" > "$out/COMPLETE-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"
stage=authenticated-original-extra-apt
source /probes/scripts/neutts_apt_snapshot.sh
neutts_apt_snapshot_open "$out/foundation-apt-inputs" "$work/signed-apt" "$out/complete-signed-snapshot"
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_complete_runtime.py --phase setup \
  --inputs "$out/complete-inputs" --foundation-inputs "$out/foundation-apt-inputs" \
  --out "$out" --work "$work" --apt-archives "$work/apt-cache" \
  --image-receipt "$out/COMPLETE-PROBE-INPUTS.json"
stage=awaiting-offline-runtime
 "$PREFIX/bin/python" -I -B - "$out" <<'PY_READY'
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[1])
value = {"schema_version": 1, "status": "ready-for-network-disconnect",
         "lock_sha256": hashlib.sha256((out / "complete-inputs/neutts_complete_runtime_lock.json").read_bytes()).hexdigest()}
temporary = out / ".COMPLETE-NETWORK-READY.tmp"
temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
temporary.rename(out / "COMPLETE-NETWORK-READY.json")
PY_READY
for ((attempt=0; attempt<120; attempt++)); do
  [[ ! -f "$out/COMPLETE-NETWORK-OFFLINE.json" ]] || break
  sleep 1
done
[[ -f "$out/COMPLETE-NETWORK-OFFLINE.json" ]]
stage=isolated-public-complete-runtime
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_complete_runtime.py \
  --inputs "$out/complete-inputs" --foundation-inputs "$out/foundation-apt-inputs" \
  --out "$out" --work "$work" --apt-archives "$work/apt-cache" \
  --image-receipt "$out/COMPLETE-PROBE-INPUTS.json"
stage=complete
echo "NEUTTS_COMPLETE_DEPENDENCIES_PASSED: original 116 dependencies and actual public native APIs"
