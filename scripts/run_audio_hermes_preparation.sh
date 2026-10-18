#!/usr/bin/env bash
# Build an isolated full Hermes audio environment; never install a .deb or open a stream.
set -Eeuo pipefail

if [[ "${1:-}" == --native ]]; then
  [[ $# == 6 ]] || { echo "usage: $0 --native CANDIDATE AUDIO_INPUTS PATCH OUT MODE" >&2; exit 2; }
  candidate="$(realpath "$2")"
  audio_inputs="$(realpath "$3")"
  patch="$(realpath "$4")"
  out="$5"
  mode="$6"
  [[ "$mode" == prepare-and-probe || "$mode" == prepare-only ]] || exit 2
  [[ ! -e "$out" && ! -L "$out" ]] || { echo "Fresh output directory required." >&2; exit 2; }
  prefix=/data/data/com.termux/files/usr
  export PREFIX="$prefix" TMPDIR="$prefix/tmp" PYTHONDONTWRITEBYTECODE=1
  mkdir -p "$TMPDIR"
  bootstrap="$(mktemp -d "$TMPDIR/hermes-audio-bootstrap-XXXXXX")"
  trap 'rm -rf -- "$bootstrap"' EXIT
  deb="$candidate/hermes-agent_0.22.2-1_aarch64.deb"
  printf '%s  %s\n' 1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a "$deb" | sha256sum -c -
  dpkg-deb --extract "$deb" "$bootstrap"
  original="$bootstrap$prefix/lib/hermes-agent"
  python="$original/tools/python$prefix/bin/python3.14"
  export LD_LIBRARY_PATH="$original/tools/python$prefix/lib:$original/tools/node$prefix/lib:$original/tools/ffmpeg$prefix/lib:$original/runtime-libs/lib:$prefix/lib"
  unset PYTHONHOME PYTHONPATH VIRTUAL_ENV _PYTHON_HOST_PLATFORM
  scripts="$(cd "$(dirname "$0")" && pwd)"
  "$python" -I -B "$scripts/prepare_audio_hermes_environment.py" prepare \
    --candidate-dir "$candidate" --audio-inputs "$audio_inputs" --patch "$patch" --out "$out"
  if [[ "$mode" == prepare-and-probe ]]; then
    probe_args=(--environment "$out")
    if [[ -n "${HERMES_AUDIO_SOURCE_IMAGE:-}" ]]; then
      probe_args+=(--image-inspection "$HERMES_AUDIO_SOURCE_IMAGE")
    fi
    "$python" -I -B "$scripts/compatibility_probe_audio_hermes.py" "${probe_args[@]}"
  fi
  exit 0
fi

[[ $# == 4 ]] || { echo "usage: $0 CANDIDATE AUDIO_INPUTS PATCH OUT" >&2; exit 2; }
case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM runner required." >&2; exit 2;; esac
candidate="$(realpath "$1")"
audio_inputs="$(realpath "$2")"
patch="$(realpath "$3")"
[[ ! -e "$4" && ! -L "$4" ]] || { echo "Fresh output directory required." >&2; exit 2; }
mkdir -p "$4"
out="$(realpath "$4")"
chmod 0777 "$out"
packaging="$(cd "$(dirname "$0")/.." && pwd)"
image=termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303
docker pull "$image"
docker image inspect "$image" > "$out/AUDIO-SOURCE-IMAGE.json"
test "$(docker image inspect --format '{{.Architecture}}' "$image")" = arm64
# Host acquisition is complete. Both independent native preparations run offline.
docker run --rm --platform linux/arm64 --network none --user 1000:1000 \
  -e HERMES_AUDIO_SOURCE_IMAGE=/out/AUDIO-SOURCE-IMAGE.json \
  -v "$packaging:/probes:ro" -v "$candidate:/candidate:ro" -v "$audio_inputs:/audio-inputs:ro" \
  -v "$patch:/audio-readiness.patch:ro" -v "$out:/out" \
  "$image" bash /probes/scripts/run_audio_hermes_preparation.sh \
  --native /candidate /audio-inputs /audio-readiness.patch /out/prepared prepare-and-probe \
  2>&1 | tee "$out/native-audio-preparation.log"

# A second fresh final path proves reconstruction without reusing the first venv/cache.
docker run --rm --platform linux/arm64 --network none --user 1000:1000 \
  -e HERMES_AUDIO_SOURCE_IMAGE=/out/AUDIO-SOURCE-IMAGE.json \
  -v "$packaging:/probes:ro" -v "$candidate:/candidate:ro" -v "$audio_inputs:/audio-inputs:ro" \
  -v "$patch:/audio-readiness.patch:ro" -v "$out:/out" \
  "$image" bash /probes/scripts/run_audio_hermes_preparation.sh \
  --native /candidate /audio-inputs /audio-readiness.patch /out/reconstructed prepare-and-probe \
  2>&1 | tee "$out/native-audio-reconstruction.log"
python3 - "$out" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
first = json.loads((out/"prepared/audio-environment-receipt.json").read_text())
second = json.loads((out/"reconstructed/audio-environment-receipt.json").read_text())
for record in (first, second):
    assert record["status"] == "prepared-environment"
    assert record["canonical_build"]["application_built_fresh"]
    assert record["canonical_build"]["manager_built_fresh"]
assert first["catalog"] == second["catalog"]
assert first["source_patch"] == second["source_patch"]
assert first["canonical_build"]["application"] == second["canonical_build"]["application"]
assert first["canonical_build"]["manager"] == second["canonical_build"]["manager"]
(out/"reconstruction-comparison.json").write_text(json.dumps({
    "schema_version": 1, "status": "passed", "fresh_native_preparations": 2,
    "catalog_equal": True, "selected_distribution_and_wheel_file_results_equal": True,
    "source_patch_equal": True, "full_environment_hash_equal_claimed": False,
    "path_specific_bytecode_and_venv_metadata": "Expected to differ; each binds its own final path.",
    "microphone_accessed": False, "physical_vad": "not-tested", "published": False
}, indent=2) + "\n")
PY
