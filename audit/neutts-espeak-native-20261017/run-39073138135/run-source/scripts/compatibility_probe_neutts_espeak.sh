#!/usr/bin/env bash
# Unpublished native eSpeak C ABI and separate complete Phonemizer experiment.
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
  host_work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-neutts-espeak-host.XXXXXX")"
  container=
  finish_host() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
    rm -rf -- "$host_work"
  }
  trap finish_host EXIT
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 - "$packaging" "$out" "$image" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("advertised source head differs")
if json.loads((root / "manifest/release.json").read_text())["termux_image"] != sys.argv[3]:
    raise SystemExit("review the native image pin")
names = (
    "scripts/compatibility_probe_neutts_espeak.sh", "scripts/compatibility_probe_neutts_espeak.py",
    "scripts/prepare_neutts_espeak_source.py", "scripts/neutts_espeak_source_lock.json",
    "scripts/check_neutts_espeak_cmake.py", "patches/next-stable/espeak-ng-explicit-off-sonic.patch",
    "scripts/compatibility_probe_neutts.sh", "scripts/compatibility_probe_neutts.py",
    "scripts/prepare_neutts_core_python.py", "scripts/neutts_core_python_lock.json",
    "scripts/validate_neutts_apt_python.py", "scripts/neutts_apt_python_metadata.json",
    "scripts/prepare_neutts_native_sources.py", "scripts/neutts_native_sources_lock.json",
    "scripts/compatibility_probe_neutts_native.py", ".github/workflows/neutts-espeak-component.yml",
    "scripts/fetch_compatibility_candidate.py", "scripts/extract_phonemizer_catalog.py",
    "scripts/prepare_phonemizer_runtime.py", "scripts/phonemizer_runtime_lock.json",
    "scripts/compatibility_probe_phonemizer.py", "patches/next-stable/phonemizer-lazy-dlinfo.patch",
    "audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv",
)
receipt = {"schema_version": 1, "head_sha": head, "workflow_ref_commit": os.environ.get("GITHUB_SHA"),
           "run_id": os.environ.get("GITHUB_RUN_ID"), "native_image": sys.argv[3],
           "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
           "purpose": "separate pinned eSpeak C ABI and complete installed Phonemizer API gates",
           "model_downloaded": False, "synthesis_tested": False, "release_output": False}
(out / "ESPEAK-PROBE-INPUTS.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY
  python3 -B "$packaging/scripts/prepare_neutts_core_python.py" \
    --lock "$packaging/scripts/neutts_core_python_lock.json" --out "$out/python-wheelhouse"
  python3 -B "$packaging/scripts/prepare_neutts_espeak_source.py" --out "$out/espeak-inputs"
  python3 -B "$packaging/scripts/check_neutts_espeak_cmake.py" \
    --inputs "$out/espeak-inputs" --out "$out/configure-regression"
  python3 -B "$packaging/scripts/fetch_compatibility_candidate.py" --out "$host_work/candidate"
  mkdir "$out/phonemizer-candidate-proof"
  for receipt in candidate-receipt.json CANDIDATE-IDENTITY.json venv-selection.json; do
    cp -- "$host_work/candidate/$receipt" "$out/phonemizer-candidate-proof/$receipt"
  done
  python3 -B "$packaging/scripts/extract_phonemizer_catalog.py" \
    --deb "$host_work/candidate/hermes-agent_0.22.2-1_aarch64.deb" \
    --deb-bytes 222089768 \
    --deb-sha256 1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a \
    --lock "$packaging/scripts/phonemizer_runtime_lock.json" --out "$out/phonemizer-main"
  python3 -B "$packaging/scripts/prepare_phonemizer_runtime.py" \
    --lock "$packaging/scripts/phonemizer_runtime_lock.json" \
    --main-wheelhouse "$out/phonemizer-main/wheels" \
    --main-catalog "$out/phonemizer-main/main-bundled-wheels.json" \
    --patch "$packaging/patches/next-stable/phonemizer-lazy-dlinfo.patch" \
    --out "$out/phonemizer-inputs"
  chmod 0777 "$out"
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-espeak-${GITHUB_RUN_ID:-local}-$$"
  timeout --signal=TERM --kill-after=20s 45m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 6g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    -v "$out/python-wheelhouse:/out/python-wheelhouse:ro" \
    -v "$out/espeak-inputs:/out/espeak-inputs:ro" \
    -v "$out/phonemizer-inputs:/out/phonemizer-inputs:ro" \
    "$image" bash /probes/scripts/compatibility_probe_neutts_espeak.sh --in-container --out /out \
    2>&1 | tee "$out/espeak-native-probe.log"
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
work="$(mktemp -d "$TMPDIR/neutts-espeak.XXXXXX")"
stage=foundation
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/ESPEAK-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out "$out"
stage=compiler-archive-download
mkdir -p "$work/archives/partial"
specs=()
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  specs+=("$name=$version")
done < "$out/espeak-inputs/build-apt-closure.tsv"
[[ "${#specs[@]}" == 44 ]]
apt-get -o Acquire::Retries=5 -o Dpkg::Options::=--force-confnew \
  -o Dir::Cache::archives="$work/archives" -y --no-install-recommends --no-remove \
  --download-only --reinstall install "${specs[@]}"
shopt -s nullglob
archives=("$work/archives/"*.deb)
[[ "${#archives[@]}" == 44 ]]
stage=native-espeak
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_neutts_espeak.py \
  --inputs "$out/espeak-inputs" --apt-archives "$work/archives" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" --out "$out/espeak-component"
echo "NEUTTS_ESPEAK_C_ABI_AND_DATA_PASSED"
stage=python-pip-provenance-download
(
  cd "$work/archives"
  apt-get -o Acquire::Retries=5 download python-pip=26.2.1
)
stage=phonemizer-archive-union
"$PREFIX/bin/python" -I -B - /probes/scripts "$work/archives" "$out" <<'PY_PIP_UNION'
import hashlib, importlib.util, json, pathlib, sys
scripts, archives, out = map(pathlib.Path, sys.argv[1:4])
def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def require(condition, message):
    if not condition:
        raise RuntimeError(message)
helper_path = scripts / "validate_neutts_apt_python.py"
require(sha(helper_path) == "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29",
        "Reviewed APT metadata verifier changed")
spec = importlib.util.spec_from_file_location("_phonemizer_union_apt", helper_path)
apt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apt)
metadata = apt.load_manifest(scripts / "neutts_apt_python_metadata.json")
native_path = scripts / "neutts_native_sources_lock.json"
require(sha(native_path) == "a06e595179fad6f437ca95210d685beb339baa0867cd527dba5f5083d94b36ce",
        "Original compiler lock changed")
compiler = json.loads(native_path.read_bytes())["build_apt"]["packages"]
require(len(compiler) == 44 and len({p["name"] for p in compiler}) == 44,
        "Original compiler closure is incomplete")
runtime = metadata["runtime"]["archives"]
require({p["package"] for p in runtime} - {p["name"] for p in compiler} == {"python-pip"},
        "Review an unexpected runtime archive outside the compiler closure")
pip_pin = next(p for p in runtime if p["package"] == "python-pip")
require((pip_pin["version"], pip_pin["architecture"], pip_pin["bytes"], pip_pin["sha256"]) ==
        ("26.2.1", "all", 1190440, "92a9cb4b3c99dd20086f90fedc95c604eefc5bd0f88d1862690884474f82de44"),
        "Original python-pip archive identity changed")
pins = [*compiler, {"name": pip_pin["package"], **pip_pin}]
selected, rows = set(), []
for pin in pins:
    matches = list(archives.glob(pin["name"] + "_*.deb"))
    require(len(matches) == 1, "Missing or ambiguous retained archive: " + pin["name"])
    path = matches[0]
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == pin["bytes"]
            and sha(path) == pin["sha256"], "Retained archive bytes changed: " + pin["name"])
    selected.add(path)
    rows.append({"name": pin["name"], "version": pin["version"], "architecture": pin["architecture"],
                 "path": str(path), "bytes": pin["bytes"], "sha256": pin["sha256"]})
require(len(selected) == 45 and selected == set(archives.glob("*.deb")),
        "Retained archive directory must be the exact 44 compiler archives plus python-pip")
wanted = {r["path"] for r in metadata["runtime"]["files"] if r["package"] == "python-pip"}
members = apt.inspect_archive(archives / pip_pin["filename"], pip_pin, wanted, include_pip=True)
for row in metadata["runtime"]["files"]:
    if row["package"] == "python-pip":
        raw = members[row["path"]]
        require(hashlib.sha256(raw).hexdigest() == row["sha256"]
                and ("bytes" not in row or len(raw) == row["bytes"]),
                "Pinned pip source or metadata member changed")
component = out / "espeak-component/ESPEAK-COMPONENT-RESULT.json"
require(json.loads(component.read_bytes()).get("status") == "passed",
        "The independent C ABI gate must pass before augmenting provenance archives")
receipt = {"schema_version": 1, "status": "verified-45-archive-union",
           "compiler_archive_count": 44, "compiler_lock_sha256": sha(native_path),
           "compiler_controls_scope": "Verified by the preceding unchanged eSpeak compiler gate.",
           "espeak_receipt_sha256": sha(component), "archive_count": 45, "archives": rows,
           "download_only_addition": pip_pin, "pip_control_verified": True,
           "pip_selected_source_files_verified": len(members), "apt_install_performed": False,
           "apt_reinstall_performed": False, "compiler_gate_changed": False}
with (out / "PHONEMIZER-APT-ARCHIVE-UNION.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, sort_keys=True, indent=2)
    stream.write("\n")
print("PHONEMIZER_APT_ARCHIVES_VERIFIED: unchanged 44 compiler archives plus exact python-pip")
PY_PIP_UNION
stage=native-phonemizer
"$PREFIX/bin/python" -I -B /probes/scripts/compatibility_probe_phonemizer.py \
  --inputs "$out/phonemizer-inputs" --apt-archives "$work/archives" \
  --foundation-receipt "$out/NEUTTS-CORE-RESULT.json" \
  --espeak-receipt "$out/espeak-component/ESPEAK-COMPONENT-RESULT.json" \
  --espeak-library "$out/espeak-component/bundle/lib/libespeak-ng.so.1.52.0.1" \
  --espeak-data "$out/espeak-component/bundle/share/espeak-ng-data" \
  --out "$out/phonemizer-component"
stage=complete
echo "PHONEMIZER_REAL_PUBLIC_API_PASSED: model synthesis remains a separate gate"
