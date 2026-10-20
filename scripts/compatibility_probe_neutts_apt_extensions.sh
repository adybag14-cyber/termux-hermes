#!/usr/bin/env bash
# Preparation-only original APT extensions; never a release or engine admission.
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
  python3 -B - "$packaging" "$out" "$image" <<'PY_INPUTS'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("Advertised source head differs")
if json.loads((root / "manifest/release.json").read_text())["termux_image"] != sys.argv[3]:
    raise SystemExit("Review the native image pin")
lock = json.loads((root / "scripts/neutts_apt_extensions_lock.json").read_bytes())
names = (
    "scripts/prepare_neutts_apt_snapshot.py", "scripts/neutts_apt_snapshot.sh",
    ".github/workflows/neutts-apt-extensions.yml",
    "scripts/compatibility_probe_neutts_apt_extensions.sh",
    "scripts/compatibility_probe_neutts_apt_extensions.py",
    "scripts/prepare_neutts_apt_extensions.py", "scripts/neutts_apt_extensions_lock.json",
    *lock["source_pins"],
    lock["extension_image_runtime"]["source_evidence"]["path"],
    "audit/neutts-runtime-index-20261017/InRelease",
    "audit/neutts-runtime-index-20261017/Packages.gz",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
)
receipt = {
    "schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
    "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
    "container_contract": {"cpus": 2, "memory_bytes": 6442450944, "pids": 512, "timeout_minutes": 40},
    "scope": "Unchanged seven-case foundation and five original APT extension operation groups",
    "apt_closure_packages": 78, "additional_packages": 18, "provenance_archives": 84,
    "compiler_requested": False, "metadata_modified": False, "model_downloaded": False,
    "engine_installed": False, "production_admission_changed": False, "release_output": False,
}
with (out / "APT-EXTENSIONS-PROBE-INPUTS.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
PY_INPUTS
  python3 -B "$packaging/scripts/prepare_neutts_apt_snapshot.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" \
    --out "$out/foundation-apt-inputs"
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/prepare_neutts_apt_extensions.py" \
    --cache "$packaging/vendor/termux-preparation/apt-archives" --out "$out/apt-extension-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-apt-extensions-${GITHUB_RUN_ID:-local}-$$"
  timeout --signal=TERM --kill-after=20s 40m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 6g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/foundation-apt-inputs:/out/foundation-apt-inputs:ro" \
    -v "$out/apt-extension-inputs:/out/apt-extension-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_apt_extensions.sh --in-container --out /out \
    2>&1 | tee "$out/apt-extensions-native-probe.log"
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
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV CMAKE_TOOLCHAIN_FILE _PYTHON_HOST_PLATFORM LD_PRELOAD NEUTTS_NATIVE_COMPONENTS
umask 022
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-apt-extensions.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/APT-EXTENSIONS-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"

stage=exact-input-verification
"$PREFIX/bin/python" -I -B - /probes/scripts "$out/apt-extension-inputs" <<'PY_VERIFY'
import hashlib, importlib.util, pathlib, sys
scripts, inputs = map(pathlib.Path, sys.argv[1:3])
path = scripts / "prepare_neutts_apt_extensions.py"
if hashlib.sha256(path.read_bytes()).hexdigest() != "42db2e03b89d08e05ac72de9615c585f5425488639968b746f56cf5d29aeb64f":
    raise SystemExit("Reviewed APT extension input verifier changed")
spec = importlib.util.spec_from_file_location("_apt_extensions_shell_prepare", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
lock, receipt = module.verify_inputs(inputs)
if len(lock["apt"]["provenance_packages"]) != 84 or len(lock["apt"]["additional_names"]) != 18:
    raise SystemExit("Retained archive/install scope differs")
print("APT_EXTENSION_INPUTS_VERIFIED: 5 original archives, 893 files, 34 ELF files, 18 additions")
PY_VERIFY

stage=exact-provenance-archive-download
mkdir -p "$work/archives/partial"
archive_count=0
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  [[ "$name" =~ ^[a-z0-9][a-z0-9+.-]*$ && "$sha" =~ ^[0-9a-f]{64}$ && "$bytes" =~ ^[0-9]+$ ]]
  [[ "$archive_path" == pool/main/* && "$archive_path" != *..* && "$archive_path" == *.deb ]]
  destination="$work/archives/$(basename "$archive_path")"
  [[ ! -e "$destination" ]]
  cached="$out/apt-extension-inputs/archives/$(basename "$archive_path")"
  retained_name="$(basename "$archive_path")"
  retained_name="${retained_name//:/%3A}"
  retained="/probes/vendor/termux-preparation/apt-archives/$retained_name"
  if [[ -e "$cached" || -L "$cached" ]]; then
    [[ -f "$cached" && ! -L "$cached" ]]
    cp -- "$cached" "$destination"
  elif [[ -e "$retained" || -L "$retained" ]]; then
    [[ -f "$retained" && ! -L "$retained" ]]
    cp -- "$retained" "$destination"
  else
    curl --proto '=https' --proto-redir '=https' --fail --show-error --silent --location \
      --retry 4 --retry-all-errors --connect-timeout 20 --max-time 180 --max-filesize "$bytes" \
      --output "$destination" "https://packages.termux.dev/apt/termux-main/$archive_path"
  fi
  [[ "$(wc -c < "$destination")" == "$bytes" ]]
  printf '%s  %s\n' "$sha" "$destination" | sha256sum --check --status
  archive_count=$((archive_count + 1))
done < "$out/apt-extension-inputs/apt-provenance-pins.tsv"
[[ "$archive_count" == 84 ]]

stage=five-original-apt-extension-operations
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_apt_extensions.py \
  --inputs "$out/apt-extension-inputs" --apt-archives "$work/archives" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" --out "$out/apt-extension-components"
stage=complete
echo "NEUTTS_APT_EXTENSIONS_PASSED: five original native extensions and exact twelve-distribution provenance"
