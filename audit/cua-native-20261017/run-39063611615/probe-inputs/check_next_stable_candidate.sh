#!/usr/bin/env bash
# Upgrade the immutable published package to a disposable same-version candidate.
# No release, signed-feed change, or physical device mutation occurs.
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  export PREFIX=/data/data/com.termux/files/usr
  export TMPDIR="$PREFIX/tmp"
  export PATH="$PREFIX/bin:${PATH:-/usr/bin:/bin}"
  mkdir -p "$TMPDIR"
  umask 022
  trap 'find /evidence -uid "$(id -u)" -type d -exec chmod a+rx {} +; find /evidence -uid "$(id -u)" -type f -exec chmod a+r {} +' EXIT
  dpkg --force-not-root --force-script-chrootless --install /fixtures/baseline.deb
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = 0.22.2-1
  hermes_test_home="$(mktemp -d "$TMPDIR/hermes-next-stable-XXXXXX")"
  export HERMES_HOME="$hermes_test_home/state"
  mkdir -p "$HERMES_HOME/profiles/review"
  printf '%s\n' 'model:' '  default: preserved-provider/model' > "$HERMES_HOME/config.yaml"
  printf '%s\n' 'This file represents existing user session data.' > "$HERMES_HOME/session-preservation.txt"
  printf '%s\n' 'AUDIT_SENTINEL=preserve-me' > "$HERMES_HOME/profiles/review/.env"
  sha256sum "$HERMES_HOME/config.yaml" "$HERMES_HOME/session-preservation.txt" \
    "$HERMES_HOME/profiles/review/.env" > /evidence/USER-STATE-BEFORE.sha256
  dpkg --force-not-root --force-script-chrootless --install /fixtures/candidate.deb
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = 0.22.2-1
  sha256sum -c /evidence/USER-STATE-BEFORE.sha256

  root="$PREFIX/lib/hermes-agent"
  export HERMES_RUNTIME_DIR="$root/tools"
  export PYTHONPATH="$root/app"
  export LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib"
  "$root/venv/bin/python" /probes/scripts/check_next_stable_lifecycle.py "$root" /evidence
  sha256sum -c /evidence/USER-STATE-BEFORE.sha256
  echo NEXT_STABLE_UPGRADE_AND_COLD_CACHE_OK
  exit 0
fi

[[ $# == 2 ]] || { echo "usage: $0 CANDIDATE_DEB OUT" >&2; exit 2; }
candidate="$(realpath "$1")"
mkdir -p "$2"
out="$(realpath "$2")"
packaging="$(cd "$(dirname "$0")/.." && pwd)"
image="$(python3 -c 'import json; print(json.load(open("manifest/release.json"))["termux_image"])')"
[[ "$image" =~ ^termux/termux-docker@sha256:[a-f0-9]{64}$ ]]
test "$(dpkg-deb -f "$candidate" Package)" = hermes-agent
test "$(dpkg-deb -f "$candidate" Version)" = 0.22.2-1
fixture="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-next-stable-fixture-XXXXXX")"
baseline="$fixture/baseline.deb"
curl -fL --retry 6 --retry-all-errors \
  https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.22.2-20261016.1/hermes-agent_0.22.2-1_aarch64.deb \
  -o "$baseline"
printf '%s  %s\n' deb163351554ca03f7104f91a50f4f8dc4d9247ce0cf5f2cca2608be3b319add "$baseline" | sha256sum -c -
chmod a+r "$baseline" "$candidate"
chmod 0777 "$out"
docker run --rm --platform linux/arm64 --user 1000:1000 \
  -v "$baseline:/fixtures/baseline.deb:ro" -v "$candidate:/fixtures/candidate.deb:ro" \
  -v "$packaging:/probes:ro" -v "$out:/evidence" \
  "$image" bash /probes/scripts/check_next_stable_candidate.sh --in-container \
  2>&1 | tee "$out/lifecycle.log"
