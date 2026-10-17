#!/usr/bin/env bash
# Preparation-only six-component experiment, with the original seven-case foundation.
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
  host_work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-neutts-nonrust-host.XXXXXX")"
  container=
  finish_host() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
    rm -rf -- "$host_work"
  }
  trap finish_host EXIT
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 - "$packaging" "$out" "$image" <<'PY_INPUTS'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("Advertised source head differs")
if json.loads((root / "manifest/release.json").read_text())["termux_image"] != sys.argv[3]:
    raise SystemExit("Review the native image pin")
names = (
    ".github/workflows/neutts-nonrust-components.yml",
    "scripts/compatibility_probe_neutts_nonrust.sh", "scripts/compatibility_probe_neutts_nonrust.py",
    "scripts/prepare_neutts_nonrust_runtime.py", "scripts/neutts_nonrust_runtime_lock.json",
    "scripts/neutts_nonrust_operations.py", "patches/next-stable/sentencepiece-bounded-build.patch",
    "scripts/compatibility_probe_neutts.sh", "scripts/compatibility_probe_neutts.py",
    "scripts/prepare_neutts_core_python.py", "scripts/neutts_core_python_lock.json",
    "scripts/validate_neutts_apt_python.py", "scripts/neutts_apt_python_metadata.json",
    "scripts/prepare_neutts_native_sources.py", "scripts/neutts_native_sources_lock.json",
    "scripts/compatibility_probe_neutts_native.py",
    "scripts/prepare_phonemizer_runtime.py", "scripts/phonemizer_runtime_lock.json",
    "scripts/compatibility_probe_phonemizer.py", "scripts/extract_phonemizer_catalog.py",
    "scripts/fetch_compatibility_candidate.py", "scripts/neutts_runtime_closure_design.json",
    "audit/neutts-runtime-index-20261017/InRelease",
    "audit/neutts-runtime-index-20261017/Packages.gz",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
)
receipt = {
    "schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
    "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
    "purpose": "Unchanged full scientific foundation, six independent exact native builds and complete runtime subsets",
    "container_contract": {"cpus": 2, "memory_bytes": 6442450944, "pids": 512, "timeout_minutes": 100},
    "model_downloaded": False, "speech_synthesis_tested": False, "release_output": False,
    "production_admission_changed": False,
}
(out / "NONRUST-PROBE-INPUTS.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY_INPUTS
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/fetch_compatibility_candidate.py" --out "$host_work/candidate"
  mkdir "$out/main-candidate-proof"
  for receipt in candidate-receipt.json CANDIDATE-IDENTITY.json venv-selection.json; do
    cp -- "$host_work/candidate/$receipt" "$out/main-candidate-proof/$receipt"
  done
  python3 -B "$packaging/scripts/extract_phonemizer_catalog.py" \
    --deb "$host_work/candidate/hermes-agent_0.22.2-1_aarch64.deb" \
    --deb-bytes 222089768 \
    --deb-sha256 1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a \
    --lock "$packaging/scripts/phonemizer_runtime_lock.json" --out "$out/main-selected"
  python3 -B "$packaging/scripts/prepare_neutts_nonrust_runtime.py" \
    --main-wheelhouse "$out/main-selected/wheels" \
    --main-catalog "$out/main-selected/main-bundled-wheels.json" \
    --cache "$out/python-wheelhouse" --out "$out/nonrust-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-nonrust-${GITHUB_RUN_ID:-local}-$$"
  timeout --signal=TERM --kill-after=20s 100m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 6g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/nonrust-inputs:/out/nonrust-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_nonrust.sh --in-container --out /out \
    2>&1 | tee "$out/nonrust-native-probe.log"
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
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV CMAKE_TOOLCHAIN_FILE _PYTHON_HOST_PLATFORM LD_PRELOAD
umask 022
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-nonrust.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/NONRUST-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"

stage=exact-archive-download
"$PREFIX/bin/python" -I -B - /probes/scripts "$out/nonrust-inputs" <<'PY_VERIFY'
import hashlib, importlib.util, pathlib, sys
scripts, inputs = map(pathlib.Path, sys.argv[1:3])
path = scripts / "prepare_neutts_nonrust_runtime.py"
if hashlib.sha256(path.read_bytes()).hexdigest() != "16298ad398312c6894bb0972bfc357232bf3bf04df57a593fc8b4413f542cbbf":
    raise SystemExit("Reviewed non-Rust input verifier changed")
spec = importlib.util.spec_from_file_location("_nonrust_shell_prepare", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
lock, receipt = module.verify_inputs(inputs)
if len(lock["build_apt"]["packages"]) != 51:
    raise SystemExit("Retained archive scope differs")
print("NONRUST_EXACT_INPUTS_VERIFIED: six sources, fifteen wheels, fifty-one APT pins")
PY_VERIFY
mkdir -p "$work/archives/partial"
archive_count=0
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  [[ "$name" =~ ^[a-z0-9][a-z0-9+.-]*$ && "$sha" =~ ^[0-9a-f]{64}$ && "$bytes" =~ ^[0-9]+$ ]]
  [[ "$archive_path" == pool/main/* && "$archive_path" != *..* && "$archive_path" == *.deb ]]
  destination="$work/archives/$(basename "$archive_path")"
  [[ ! -e "$destination" ]]
  curl --proto '=https' --proto-redir '=https' --fail --show-error --silent --location \
    --retry 4 --retry-all-errors --connect-timeout 20 --max-time 180 --max-filesize "$bytes" \
    --output "$destination" "https://packages.termux.dev/apt/termux-main/$archive_path"
  [[ "$(wc -c < "$destination")" == "$bytes" ]]
  printf '%s  %s\n' "$sha" "$destination" | sha256sum --check --status
  archive_count=$((archive_count + 1))
done < "$out/nonrust-inputs/build-apt-closure.tsv"
[[ "$archive_count" == 51 ]]
stage=independent-native-components
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_nonrust.py \
  --inputs "$out/nonrust-inputs" --apt-archives "$work/archives" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" --out "$out/nonrust-components"
stage=complete
echo "NEUTTS_NONRUST_COMPONENTS_PASSED: six builds and complete isolated runtime operations"
