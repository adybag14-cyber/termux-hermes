#!/usr/bin/env bash
# Native build-only wheel preparation; no engine installation or release output.
set -Eeuo pipefail
mode=host
if [[ "${1:-}" == --in-container ]]; then mode=container; shift; fi
[[ $# == 2 && "$1" == --out ]] || { echo "usage: $0 [--in-container] --out NEW_DIR" >&2; exit 2; }
out="$2"

if [[ "$mode" == host ]]; then
  case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM64 host required" >&2; exit 2 ;; esac
  packaging="$(cd "$(dirname "$0")/.." && pwd)"
  [[ ! -e "$out" ]] || { echo "Use a new evidence directory" >&2; exit 2; }
  mkdir -p "$out"
  out="$(realpath "$out")"
  container=
  finish_host() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
  }
  trap finish_host EXIT
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 -B - "$packaging" "$out" "$image" <<'PY_SOURCE'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("advertised source head differs")
lock = json.loads((root / "scripts/neutts_engine_wheel_lock.json").read_bytes())
if lock["native_image"] != sys.argv[3] or json.loads((root / "manifest/release.json").read_bytes())["termux_image"] != sys.argv[3]:
    raise SystemExit("review the native image pin")
names = set(lock["helpers"]) | {
    "scripts/compatibility_probe_neutts_engine_wheel.sh",
    "scripts/compatibility_probe_neutts_engine_wheel.py",
    "scripts/prepare_neutts_engine_wheel.py", "scripts/neutts_engine_wheel_lock.json",
    "scripts/verify_neutts_engine_wheel.py", "scripts/check_neutts_engine_wheel_cmake.py",
    "patches/next-stable/neutts-propagate-espeak-toolchain.patch",
    ".github/workflows/neutts-engine-wheel.yml",
    "scripts/compatibility_probe_neutts.sh", "scripts/compatibility_probe_neutts.py",
    "scripts/prepare_neutts_apt_snapshot.py", "scripts/neutts_apt_snapshot.sh",
    "audit/neutts-runtime-index-20261017/InRelease", "audit/neutts-runtime-index-20261017/Packages.gz",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
}
receipt = {"schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
           "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
           "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)},
           "purpose": "Build-only exact NeuTTS wheel and its bundled eSpeak C ABI/data",
           "engine_install_performed": False, "python314_admission": False, "release_output": False}
(out / "ENGINE-WHEEL-PROBE-INPUTS.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
PY_SOURCE
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/prepare_neutts_apt_snapshot.py" --include-compiler \
    --cache "$packaging/vendor/termux-preparation/apt-archives" --out "$out/foundation-apt-inputs"
  python3 -B "$packaging/scripts/prepare_neutts_engine_wheel.py" --out "$out/engine-wheel-inputs"
  python3 -B "$packaging/scripts/check_neutts_engine_wheel_cmake.py" \
    --inputs "$out/engine-wheel-inputs" --out "$out/host-cmake-regression"
  find "$out" -type f -exec chmod a+r {} +
  find "$out" -type d -exec chmod a+rx {} +
  chmod a+rwx "$out"
  docker pull "$image"
  python3 -B - "$image" "$out" <<'PY_IMAGE'
import json, pathlib, subprocess, sys
rows = json.loads(subprocess.check_output(["docker", "image", "inspect", sys.argv[1]]))
if len(rows) != 1 or rows[0]["Architecture"] != "arm64" or rows[0]["Os"] != "linux" or sys.argv[1] not in rows[0]["RepoDigests"]:
    raise SystemExit("Pulled image identity differs")
row = rows[0]
pathlib.Path(sys.argv[2], "NATIVE-IMAGE-IDENTITY.json").write_text(json.dumps(
    {key: row[key] for key in ("Id", "RepoDigests", "Architecture", "Os")}, sort_keys=True, indent=2) + "\n")
PY_IMAGE
  container="hermes-engine-wheel-${GITHUB_RUN_ID:-local}-$$"
  timeout --signal=TERM --kill-after=20s 45m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 6g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/foundation-apt-inputs:/out/foundation-apt-inputs:ro" \
    -v "$out/engine-wheel-inputs:/out/engine-wheel-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_engine_wheel.sh --in-container --out /out \
    2>&1 | tee "$out/engine-wheel-native.log"
  exit 0
fi

[[ "$(id -u)" == 1000 && "$(uname -m)" == aarch64 ]]
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR="$PREFIX/tmp"
export PATH="$PREFIX/bin:/system/bin:/system/xbin"
export LD_LIBRARY_PATH="$PREFIX/lib"
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV ESPEAK_DATA_PATH CMAKE_TOOLCHAIN_FILE _PYTHON_HOST_PLATFORM LD_PRELOAD
umask 022
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-engine-wheel-driver.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/ENGINE-WHEEL-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT

bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"
stage=frozen-signed-compiler-apt
source /probes/scripts/neutts_apt_snapshot.sh
neutts_apt_snapshot_open "$out/foundation-apt-inputs" "$work/frozen-apt" "$out/ENGINE-WHEEL-FROZEN-APT"
stage=original-compiler-archive-cache
neutts_apt_stage_archives "$out/foundation-apt-inputs" "$out/engine-wheel-inputs/build-apt-closure.tsv" \
  "$work/compiler-archives" "$out/ENGINE-WHEEL-COMPILER-CACHE.tsv"
stage=already-installed-pip-provenance-cache
mkdir "$work/python-pip"
cp "$out/foundation-apt-inputs/apt-archives/python-pip_26.2.1_all.deb" \
  "$work/python-pip/python-pip_26.2.1_all.deb"
neutts_apt_file "$work/python-pip/python-pip_26.2.1_all.deb" 1190440 \
  92a9cb4b3c99dd20086f90fedc95c604eefc5bd0f88d1862690884474f82de44
stage=native-engine-wheel
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_engine_wheel.py \
  --inputs "$out/engine-wheel-inputs" --apt-archives "$work/compiler-archives" \
  --pip-archive "$work/python-pip/python-pip_26.2.1_all.deb" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" \
  --source-receipt "$out/ENGINE-WHEEL-PROBE-INPUTS.json" \
  --out "$out/engine-wheel-component"
stage=complete
echo "NEUTTS_WHEEL_AND_BUNDLED_ESPEAK_PASSED: original Python bound still excludes 3.14; engine import and synthesis remain separate"
