#!/usr/bin/env bash
# Unpublished standalone Tiktoken build and complete original base runtime.
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
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 -B - "$packaging" "$out" "$image" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("advertised source head differs")
if json.loads((root / "manifest/release.json").read_bytes())["termux_image"] != sys.argv[3]:
    raise SystemExit("review the native image pin")
lock = json.loads((root / "scripts/neutts_tiktoken_lock.json").read_bytes())
names = {
    "scripts/compatibility_probe_neutts_tiktoken.sh", "scripts/compatibility_probe_neutts_tiktoken.py",
    "scripts/prepare_neutts_tiktoken.py", "scripts/neutts_tiktoken_lock.json",
    "tests/test_neutts_tiktoken.py", ".github/workflows/neutts-tiktoken-component.yml",
    "scripts/compatibility_probe_neutts_rust.py", "scripts/prepare_neutts_rust_sources.py",
    "scripts/neutts_rust_sources_lock.json", "scripts/compatibility_probe_neutts.sh",
    "scripts/compatibility_probe_neutts.py", "scripts/prepare_neutts_core_python.py",
    "scripts/neutts_core_python_lock.json", "scripts/prepare_neutts_apt_snapshot.py",
    "scripts/neutts_apt_snapshot.sh", "scripts/validate_neutts_apt_python.py",
    "scripts/neutts_apt_python_metadata.json", "audit/neutts-runtime-index-20261017/InRelease",
    "audit/neutts-runtime-index-20261017/Packages.gz",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
}
names.update(pin["path"] for pin in lock["references"].values())
for relative in ("vendor/termux-preparation", "audit/neutts-tiktoken-preparation-20261020"):
    names.update(path.relative_to(root).as_posix() for path in (root / relative).rglob("*") if path.is_file())
receipt = {
    "schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
    "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)},
    "purpose": "Original reviewed Tiktoken lock build and isolated seven-distribution base runtime",
    "approved_lock_capture_commit": lock["reviewed_capture_commit"],
    "original_sources_or_metadata_modified": False, "model_downloaded": False,
    "complete_engine_admitted": False, "release_output": False,
}
with (out / "TIKTOKEN-PROBE-INPUTS.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, sort_keys=True, indent=2)
    stream.write("\n")
PY
  python3 -B "$packaging/scripts/prepare_neutts_apt_snapshot.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --out "$out/foundation-apt-inputs"
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/prepare_neutts_tiktoken.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --cache "$packaging/audit/neutts-tiktoken-preparation-20261020" \
    --out "$out/tiktoken-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-tiktoken-${GITHUB_RUN_ID:-local}-$$"
  finish_host() { docker rm -f "$container" >/dev/null 2>&1 || true; }
  trap finish_host EXIT
  timeout --signal=TERM --kill-after=20s 65m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 6g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/foundation-apt-inputs:/out/foundation-apt-inputs:ro" \
    -v "$out/tiktoken-inputs:/out/tiktoken-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_tiktoken.sh --in-container --out /out \
    2>&1 | tee "$out/tiktoken-native-probe.log"
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
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV _PYTHON_HOST_PLATFORM LD_PRELOAD APT_CONFIG
umask 022
mkdir -p "$TMPDIR"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/TIKTOKEN-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"
stage=original-tiktoken-and-regex
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_tiktoken.py \
  --inputs "$out/tiktoken-inputs" --apt-archives "$out/tiktoken-inputs/apt-archives" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" --out "$out/tiktoken-component"
stage=complete
echo "TIKTOKEN_ORIGINAL_LOCK_AND_SEVEN_DISTRIBUTION_NATIVE_OPERATIONS_PASSED"
