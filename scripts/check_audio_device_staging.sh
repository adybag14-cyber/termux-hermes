#!/usr/bin/env bash
# Validate this isolated audio preparation in the pinned native ARM container.
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  [[ "$#" == 1 ]] || { echo "Unexpected container arguments" >&2; exit 2; }
  [[ "$(id -u)" == 1000 ]] || { echo "Native validation requires UID 1000" >&2; exit 2; }
  case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM64 required" >&2; exit 2 ;; esac
  export PREFIX=/data/data/com.termux/files/usr
  [[ -d "$PREFIX/tmp" && -w "$PREFIX/tmp" ]] || { echo "Termux temporary parent unavailable" >&2; exit 2; }
  audio_roots=(
    "$PREFIX/tmp/hermes-audio-validation-a"
    "$PREFIX/tmp/hermes audio validation b"
  )
  preserve_evidence() {
    local number=0 audio_root evidence name
    for audio_root in "${audio_roots[@]}"; do
      number=$((number + 1))
      [[ -d "$audio_root" ]] || continue
      evidence="/evidence/environment-$number"
      mkdir -p "$evidence"
      chmod 0755 "$evidence"
      for name in assembly-receipt environment-manifest native-validation audio-diagnostic; do
        if [[ -f "$audio_root/staging/$name.json" && ! -L "$audio_root/staging/$name.json" ]]; then
          cp "$audio_root/staging/$name.json" "$evidence/$name.json"
          chmod 0644 "$evidence/$name.json"
        fi
      done
    done
  }
  trap preserve_evidence EXIT
  index=0
  for audio_root in "${audio_roots[@]}"; do
    index=$((index + 1))
    evidence="/evidence/environment-$index"
    mkdir "$evidence"
    chmod 0755 "$evidence"
    bash /bundle/prepare.sh "$audio_root"
    audio_python="$audio_root/bin/audio-python"
    helper="$audio_root/staging/prepare_audio_device_environment.py"
    "$audio_python" "$helper" validate --root "$audio_root"
    timeout --signal=TERM --kill-after=5s 60s \
      "$audio_python" -m hermes_cli.main --help \
      > "$evidence/hermes-cli-help.stdout" 2> "$evidence/hermes-cli-help.stderr"
    [[ -s "$evidence/hermes-cli-help.stdout" ]]
    chmod 0644 "$evidence/hermes-cli-help.stdout" "$evidence/hermes-cli-help.stderr"
    "$audio_python" "$helper" diagnose --root "$audio_root"
    # Recheck the complete owned environment after CLI startup and diagnosis.
    "$audio_python" "$helper" validate --root "$audio_root"
    for name in assembly-receipt environment-manifest native-validation audio-diagnostic; do
      [[ -f "$audio_root/staging/$name.json" && ! -L "$audio_root/staging/$name.json" ]]
      cp "$audio_root/staging/$name.json" "$evidence/$name.json"
      chmod 0644 "$evidence/$name.json"
    done
  done
  # Use the reviewed interpreter to index the two observed recreation results.
  "${audio_roots[0]}/bin/audio-python" - /evidence "${audio_roots[@]}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

out = Path(sys.argv[1])
cases = []
for number, root in enumerate(sys.argv[2:], 1):
    folder = out / f"environment-{number}"
    receipts = {}
    for path in sorted(folder.glob("*.json")):
        raw = path.read_bytes()
        data = json.loads(raw)
        assert isinstance(data, dict), path.name
        receipts[path.name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert set(receipts) == {
        "assembly-receipt.json", "environment-manifest.json",
        "native-validation.json", "audio-diagnostic.json",
    }
    diagnostic = json.loads((folder / "audio-diagnostic.json").read_bytes())
    assert diagnostic["schema_version"] == 1
    assert diagnostic["root"] == root
    assert diagnostic["protocol_valid"] is True
    assert diagnostic["status"] in ("audio-unavailable", "audio-initialized")
    for key in ("readiness", "device_readiness", "microphone_accessed",
                "recording_tested", "vad_tested", "device_stream_opened"):
        assert diagnostic[key] is False, key
    cli_outputs = {}
    for name in ("hermes-cli-help.stdout", "hermes-cli-help.stderr"):
        raw = (folder / name).read_bytes()
        cli_outputs[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert cli_outputs["hermes-cli-help.stdout"]["bytes"] > 0
    cases.append({
        "root": root,
        "assembly_and_validation_exit_codes": [0, 0, 0],
        "diagnostic_command_exit_code": 0,
        "diagnostic_outcome_is_separate_from_assembly": True,
        "hermes_cli_smoke": {
            "command": ["bin/audio-python", "-m", "hermes_cli.main", "--help"],
            "exit_code": 0,
            "timeout_seconds": 60,
            "outputs": cli_outputs,
            "full_immutable_validation_passed_after_startup": True,
        },
        "receipts": receipts,
        "audio_diagnostic": diagnostic,
    })
assert len(cases) == 2 and len({case["root"] for case in cases}) == 2
result = {
    "schema_version": 1,
    "status": "passed",
    "purpose": "Two fresh isolated full Hermes audio environment recreations",
    "native_environment_count": len(cases),
    "recreated_at_distinct_final_paths": True,
    "second_destination_contains_spaces": " " in cases[1]["root"],
    "copied_virtual_environment": False,
    "container_network": "none",
    "physical_device_tested": False,
    "microphone_accessed": False,
    "recording_tested": False,
    "vad_tested": False,
    "main_candidate_changed": False,
    "release_created": False,
    "cases": cases,
}
target = out / "AUDIO-STAGING-RESULT.json"
target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
target.chmod(0o644)
print(json.dumps({key: result[key] for key in (
    "status", "native_environment_count", "recreated_at_distinct_final_paths",
    "second_destination_contains_spaces", "microphone_accessed", "vad_tested",
)}, indent=2))
PY
  exit 0
fi

[[ "$#" == 2 ]] || { echo "Usage: $0 BUNDLE_DIRECTORY NEW_EVIDENCE_DIRECTORY" >&2; exit 2; }
case "$(uname -m)" in aarch64|arm64) ;; *) echo "Run the validation on a native ARM64 host" >&2; exit 2 ;; esac
packaging="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bundle="$(realpath -- "$1")"
[[ -d "$bundle" && -f "$bundle/prepare.sh" && -f "$bundle/manifest.json" && -f "$bundle/payload.tar.gz" ]]
[[ ! -e "$2" && ! -L "$2" ]] || { echo "Evidence destination already exists" >&2; exit 2; }
mkdir -- "$2"
out="$(realpath -- "$2")"
image="$(python3 - "$packaging" <<'PY'
import json
from pathlib import Path
import re
import sys
repo = Path(sys.argv[1])
lock = json.loads((repo / "scripts/audio_device_bundle_lock.json").read_bytes())
image = lock["builder_image"]
assert re.fullmatch(r"termux/termux-docker@sha256:[a-f0-9]{64}", image)
assert json.loads((repo / "manifest/release.json").read_bytes())["termux_image"] == image
print(image)
PY
)"
python3 - "$packaging" "$bundle" "$out" "$image" <<'PY'
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

repo, bundle, out = map(Path, sys.argv[1:4])
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
if os.environ.get("GITHUB_SHA"):
    assert os.environ["GITHUB_SHA"] == head
inputs = [
    ".github/workflows/audio-device-staging.yml",
    "scripts/prepare_audio_device_bundle.py",
    "scripts/prepare_audio_device_environment.py",
    "scripts/audio_device_bundle_lock.json",
    "scripts/check_audio_device_staging.sh",
    "scripts/fetch_compatibility_candidate.py",
    "tests/test_audio_device_staging.py",
    "patches/next-stable/audio-readiness.patch",
    "manifest/release.json",
]
def record(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"bytes": path.stat().st_size, "sha256": digest}
source_inputs = {name: record(repo / name) for name in inputs}
for name, measured in source_inputs.items():
    committed = subprocess.check_output(["git", "show", head + ":" + name], cwd=repo)
    assert len(committed) == measured["bytes"]
    assert hashlib.sha256(committed).hexdigest() == measured["sha256"], name
receipt = {
    "schema_version": 1,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "head_sha": head,
    "repository": "adybag14-cyber/termux-hermes",
    "run_id": os.environ.get("GITHUB_RUN_ID"),
    "builder_image": sys.argv[4],
    "container_network": "none",
    "source_inputs": source_inputs,
    "all_source_bytes_match_exact_git_commit": True,
    "bundle_files": {name: record(bundle / name) for name in (
        "payload.tar.gz", "manifest.json", "prepare.sh", "BUNDLE-RECEIPT.json"
    )},
    "physical_device_tested": False,
    "microphone_accessed": False,
    "release_created": False,
}
(out / "AUDIO-STAGING-INPUTS.json").write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n"
)
PY
cp -- "$bundle/BUNDLE-RECEIPT.json" "$out/BUNDLE-RECEIPT.json"
chmod 0777 "$out"
docker pull "$image"
[[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
docker image inspect "$image" > "$out/BUILDER-IMAGE.json"
container="hermes-audio-staging-${GITHUB_RUN_ID:-local}-$$"
finish_host() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap finish_host EXIT
timeout --signal=TERM --kill-after=20s 20m docker run --rm --name "$container" \
  --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 4g --pids-limit 512 \
  --network none \
  -v "$packaging:/probes:ro" -v "$bundle:/bundle:ro" -v "$out:/evidence" \
  "$image" bash /probes/scripts/check_audio_device_staging.sh --in-container \
  2>&1 | tee "$out/native-staging.log"
