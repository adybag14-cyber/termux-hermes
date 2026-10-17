#!/usr/bin/env bash
# Verify streamed recovery of the exact candidate before its public release.
# Usage: bash scripts/check_bundle_recovery.sh DEB VERSION INSTALLER
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  expected_version="$2"
  export PREFIX=/data/data/com.termux/files/usr
  export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
  export TMPDIR="$PREFIX/tmp"
  mkdir -p "$TMPDIR"
  printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
  apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
  # Retain the aged base so the installer must repair its incompatible GPG
  # crypto library itself. Fresh-base validation runs in the native build.

  python_deb=/fixtures/python_3.13.15_aarch64.deb
  python_deps="$(dpkg-deb -f "$python_deb" Depends)"
  if [[ -n "$python_deps" ]]; then apt-get satisfy -y "$python_deps"; fi
  dpkg --force-not-root --force-script-chrootless --install "$python_deb"
  apt-mark hold python
  python_before="$(sha256sum "$PREFIX/bin/python3.13")"
  test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'

  # Create a real configuration through the new CLI, then reproduce the old
  # interrupted dpkg state. User data remains outside both package trees.
  dpkg --force-not-root --force-script-chrootless --install /candidate/package.deb
  hermes config set model.max_tokens 65536
  printf 'RECOVERY_SENTINEL=preserve-me\n' > "$HOME/.hermes/.env"
  env_before="$(sha256sum "$HOME/.hermes/.env")"
  mkdir -p "$HOME/.hermes/hermes-agent/.git"
  : > "$HOME/.hermes/hermes-agent/.git/index.lock"
  # The ordinary installer path must work: metadata is consistent, but the
  # old libgcrypt is too old for current GPG despite its unversioned dependency.
  apt-get -s install ncurses ncurses-ui-libs >/dev/null
  dpkg --force-not-root --force-script-chrootless --remove hermes-agent
  dpkg --force-not-root --force-script-chrootless --unpack /fixtures/hermes-agent_0.20.6+termux1_aarch64.deb
  test "$(dpkg-query -W -f='${db:Status-Status}' hermes-agent)" = unpacked

  # Only transport URLs differ from the reviewed installer. Its package
  # version and checksum remain unchanged and were verified on the host.
  python3.13 -u /candidate/range_server.py /candidate > "$TMPDIR/recovery-http.log" 2>&1 &
  server_pid=$!
  trap 'kill "$server_pid" 2>/dev/null || true; timeout 20s hermes gateway stop >/dev/null 2>&1 || true' EXIT
  ready=false
  for attempt in {1..30}; do
    if curl -fsS http://127.0.0.1:8765/install.sh -o /dev/null; then ready=true; break; fi
    sleep 0.2
  done
  "$ready"

  filename="hermes-agent_${expected_version}_aarch64.deb"
  apt_partial="$PREFIX/var/cache/apt/archives/partial/$filename"
  mkdir -p "$(dirname "$apt_partial")"
  curl -fsS --range 0-1048575 http://127.0.0.1:8765/package.deb -o "$apt_partial"
  test "$(wc -c < "$apt_partial")" = 1048576

  dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libgcrypt)" lt 1.12.0
  recovery_url=http://127.0.0.1:8765/install.sh
  curl -fsS "$recovery_url" | HERMES_RECOVERY_INSTALL_URL="$recovery_url" bash \
    2>&1 | tee "$TMPDIR/candidate-recovery.log"
  ! grep -F 'Termux mirror package skew detected' "$TMPDIR/candidate-recovery.log"
  dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libgcrypt)" ge 1.12.0
  grep -Fx 'RANGE bytes=1048576-' "$TMPDIR/recovery-http.log"
  test "$(sha256sum "$HOME/.hermes/.env")" = "$env_before"
  test -e "$HOME/.hermes/hermes-agent/.git/index.lock"
  test "$(hermes config get model.max_tokens --json)" = 8192
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = "$expected_version"
  test "$(dpkg-query -W -f='${db:Status-Status}' hermes-agent)" = installed
  test "$(dpkg-query -W -f='${db:Status-Status}' python)" = installed
  test "$(sha256sum "$PREFIX/bin/python3.13")" = "$python_before"
  test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'
  ! dpkg-query -W -f='${db:Status-Status}' python3.13 2>/dev/null | grep -Fx installed
  test -z "$(dpkg --audit)"
  cache="${XDG_CACHE_HOME:-$HOME/.cache}/hermes-recovery/$filename"
  test ! -e "$cache"
  test ! -e "$cache.part"
  test ! -e "$apt_partial"
  echo CANDIDATE_STREAMED_RECOVERY_OK
  exit 0
fi

[[ $# == 3 ]] || { echo "usage: $0 DEB VERSION INSTALLER" >&2; exit 2; }
deb="$(realpath "$1")"
version="$2"
installer="$(realpath "$3")"
# The prior production smoke exposed GPG's libgcrypt 1.11.2 incompatibility
# in this exact image. Do not pre-upgrade it or substitute the newer build base.
recovery_image=termux/termux-docker@sha256:3aed9c7fbcf9195a9919deaad418da006232864a779fb4f322d68a34887a2e15
case "$(uname -m)" in aarch64|arm64) ;; *) echo 'Native ARM runner required' >&2; exit 1;; esac
[[ -s "$deb" && -s "$installer" ]]
test "$(dpkg-deb -f "$deb" Package)" = hermes-agent
test "$(dpkg-deb -f "$deb" Version)" = "$version"
test "$(dpkg-deb -f "$deb" Architecture)" = aarch64
scratch="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-recovery-candidate.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
cp "$deb" "$scratch/package.deb"

python3 - "$installer" "$scratch/install.sh" "$deb" "$version" <<'PY'
import hashlib, re, sys
from pathlib import Path
source, output, deb = map(Path, sys.argv[1:4])
text = source.read_text()
def constant(name):
    match = re.search(r"^" + name + r"=(['\"])(.*?)\1$", text, re.M)
    if not match:
        raise SystemExit(f"Missing installer constant: {name}")
    return match[2]
with deb.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
assert constant("PACKAGE_VERSION") == sys.argv[4], "installer version differs from candidate"
assert constant("PACKAGE_SHA256") == digest, "installer SHA-256 differs from candidate"
for name in ("PACKAGE_RELEASE_URL", "PACKAGE_ORACLE_URL"):
    text, count = re.subn(r"^" + name + r"=.*$", name + '="http://127.0.0.1:8765/package.deb"', text, flags=re.M)
    assert count == 1
output.write_text(text, encoding="utf-8")
PY

cat > "$scratch/range_server.py" <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/install.sh", "/package.deb"):
            self.send_error(404)
            return
        path = root / self.path[1:]
        size = path.stat().st_size
        header = self.headers.get("Range")
        start, end = 0, size - 1
        if header:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", header)
            if not match:
                self.send_error(416)
                return
            start = int(match[1])
            end = min(int(match[2]) if match[2] else end, end)
            if start > end:
                self.send_error(416)
                return
            print("RANGE " + header, flush=True)
        self.send_response(206 if header else 200)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                self.wfile.write(block)
                remaining -= len(block)

HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
PY

fixtures="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/termux-hermes-fixtures"
mkdir -p "$fixtures"
fetch_fixture() {
  local name="$1" sha="$2" url="$3"
  if ! printf '%s  %s\n' "$sha" "$fixtures/$name" | sha256sum -c - >/dev/null 2>&1; then
    curl -fL --retry 6 --retry-all-errors "$url" -o "$fixtures/$name"
  fi
  printf '%s  %s\n' "$sha" "$fixtures/$name" | sha256sum -c -
}
fetch_fixture python_3.13.15_aarch64.deb \
  c3038f512f3d95b5c3d4803f3cdd06b43fc09dcb415b3900bd048ef508fbffc3 \
  https://github.com/adybag14-cyber/termux-python/releases/download/termux-aarch64-20260824.43.1/python_3.13.15_aarch64.deb
fetch_fixture hermes-agent_0.20.6+termux1_aarch64.deb \
  8d54e0339b382c102b653486298bc8cf65abefa71cff38de8b43acf6e849a652 \
  https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.20.6-20260828.1/hermes-agent_0.20.6%2Btermux1_aarch64.deb
chmod -R a+rX "$scratch" "$fixtures"

docker run --rm --platform linux/arm64 --privileged --security-opt seccomp=unconfined \
  -v "$scratch:/candidate:ro" -v "$fixtures:/fixtures:ro" \
  -v "$(realpath "$0"):/check-recovery.sh:ro" \
  "$recovery_image" bash /check-recovery.sh --in-container "$version"
