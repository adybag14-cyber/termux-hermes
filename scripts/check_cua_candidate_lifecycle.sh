#!/usr/bin/env bash
# Fresh runtime-only upgrade/optional-install gate for the unpublished CUA package.
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  export PREFIX=/data/data/com.termux/files/usr
  export TMPDIR="$PREFIX/tmp"
  export PATH="$PREFIX/bin:${PATH:-/usr/bin:/bin}"
  export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
  mkdir -p "$TMPDIR"
  trap 'find /evidence -uid "$(id -u)" -type d -exec chmod a+rx {} +; find /evidence -uid "$(id -u)" -type f -exec chmod a+r {} +' EXIT
  [[ "$(id -u)" == 1000 ]]
  [[ "$(dpkg-deb -f /fixtures/candidate.deb Depends)" == 'libx11, libxi' ]]
  [[ -z "$(dpkg-deb -f /fixtures/candidate.deb Pre-Depends)" ]]
  printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
  apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=5 update
  # Both packages and their transitive runtime closure are in termux-main.
  apt-get -y --no-install-recommends --no-remove install libx11 libxi
  dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > /evidence/CUA-RUNTIME-APT.tsv
  bash /probes/scripts/check_next_stable_candidate.sh --in-container
  # Existing lifecycle checks build-tool absence and repeated optional reuse.
  # Loading --version also verifies ELF dependencies without a desktop install.
  driver="$PREFIX/lib/hermes-agent/tools/cua-driver-0.21.0-linux-arm64-bionic/cua-driver"
  "$driver" --version > /evidence/CUA-DRIVER-VERSION.txt
  echo CUA_SAME_VERSION_UPGRADE_AND_RUNTIME_ONLY_OPTIONAL_REUSE_PASSED
  exit 0
fi

[[ $# == 2 ]] || { echo "usage: $0 PREPARED_CUA_DIR NEW_OUT" >&2; exit 2; }
prepared="$(realpath "$1")"
[[ ! -e "$2" ]]
mkdir -p "$2"
out="$(realpath "$2")"
packaging="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$prepared" "$out" "$packaging" <<'PY'
import hashlib, json, pathlib, subprocess, sys
prepared, out, root = map(pathlib.Path, sys.argv[1:])
receipt = json.loads((prepared / "prepared-cua-receipt.json").read_bytes())
assert receipt["schema_version"] == 1 and receipt["status"] == "prepared-candidate"
assert receipt["published"] is False and receipt["version_bumped"] is False
assert receipt["package"]["file"] == "hermes-agent_0.22.2-1_aarch64-cua-candidate.deb"
package = prepared / receipt["package"]["file"]
raw = package.read_bytes()
assert len(raw) == receipt["package"]["bytes"]
assert hashlib.sha256(raw).hexdigest() == receipt["package"]["sha256"]
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
assert receipt["packaging_commit"] == head
names = ("scripts/check_cua_candidate_lifecycle.sh", "scripts/check_next_stable_candidate.sh",
         "scripts/check_next_stable_lifecycle.py")
report = {
    "schema_version": 1, "scope": "unpublished CUA candidate fresh runtime-only upgrade and optional-install lifecycle",
    "head_sha": head, "run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
    "prepared_receipt_sha256": hashlib.sha256((prepared / "prepared-cua-receipt.json").read_bytes()).hexdigest(),
    "package": receipt["package"],
    "inputs": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in names},
    "published": False, "physical_device_tested": False,
}
(out / "CUA-LIFECYCLE-INPUTS.json").write_text(json.dumps(report, indent=2) + "\n")
PY
candidate="$prepared/hermes-agent_0.22.2-1_aarch64-cua-candidate.deb"
image="$(python3 -c 'import json; print(json.load(open("manifest/release.json"))["termux_image"])')"
[[ "$image" =~ ^termux/termux-docker@sha256:[a-f0-9]{64}$ ]]
fixture="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-cua-lifecycle-XXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT
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
  "$image" bash /probes/scripts/check_cua_candidate_lifecycle.sh --in-container \
  2>&1 | tee "$out/lifecycle.log"
