#!/usr/bin/env bash
# Candidate-only native Android probe; never builds or publishes a release.
set -euo pipefail
SOURCE= OUT=
while (($#)); do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "usage: $0 --source source --out evidence" >&2; exit 2 ;;
  esac
done
: "${SOURCE:?--source is required}" "${OUT:?--out is required}"
: "${PREFIX:?}" "${HERMES_PROBE_PYTHON:?}" "${HERMES_PROBE_PAYLOAD:?}"
mkdir -p "$OUT"
work="$(mktemp -d "$PREFIX/tmp/hb.XXXXXX")"
server_pid=
cleanup() {
  if [[ -x "$work/agent-browser" ]]; then
    env -u LD_LIBRARY_PATH "$work/agent-browser" --session hermes-compat close >/dev/null 2>&1 || true
  fi
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
printf '%s\n' 'deb https://packages.termux.dev/apt/termux-x11 x11 main' > "$PREFIX/etc/apt/sources.list.d/hermes-browser-probe.list"
env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 install -y chromium
dpkg-query -W -f='${Package} ${Version}\n' chromium > "$OUT/chromium-package.txt"

# Use only the exact archive already pinned by Hermes. Select its static ARM64 CLI,
# avoiding both the glibc binary and the Node wrapper's unsupported-Android branch.
"$HERMES_PROBE_PYTHON" -B - "$SOURCE" "$work" "$OUT" <<'PY'
from pathlib import Path
import hashlib, json, struct, sys, tarfile, urllib.request
source, work, out = map(Path, sys.argv[1:])
row = json.loads((source / "pm/lock.json").read_text())["packages"]["agent-browser"]
artifact = row["artifacts"]["any"]
with urllib.request.urlopen(artifact["url"], timeout=60) as response:
    data = response.read()
actual = hashlib.sha256(data).hexdigest()
assert actual == artifact["sha256"], (actual, artifact["sha256"])
archive = work / "agent-browser.tgz"
archive.write_bytes(data)
with tarfile.open(archive) as bundle:
    raw = bundle.extractfile("package/bin/agent-browser-linux-musl-arm64").read()
assert raw[:4] == b"\x7fELF" and raw[4:6] == bytes((2, 1))
assert struct.unpack_from("<H", raw, 18)[0] == 183
phoff = struct.unpack_from("<Q", raw, 32)[0]
phsize, phnum = struct.unpack_from("<HH", raw, 54)
types = [struct.unpack_from("<I", raw, phoff + i * phsize)[0] for i in range(phnum)]
assert 3 not in types and 2 not in types, "candidate must have no ELF interpreter or dynamic linkage"
binary = work / "agent-browser"
binary.write_bytes(raw)
binary.chmod(0o755)
(out / "agent-browser-artifact.json").write_text(json.dumps({
    "version": row["version"], "archive_url": artifact["url"],
    "archive_sha256": actual, "binary_sha256": hashlib.sha256(raw).hexdigest(),
    "elf_machine": 183, "elf_interpreter": False, "dynamic_linkage": False,
}, indent=2) + "\n")
PY
export AGENT_BROWSER_SOCKET_DIR="$work/sockets" AGENT_BROWSER_PROFILE="$work/profile"
mkdir -p "$AGENT_BROWSER_SOCKET_DIR" "$AGENT_BROWSER_PROFILE"
export TMPDIR="$work"
env -u LD_LIBRARY_PATH "$work/agent-browser" --version | tee "$OUT/agent-browser-version.txt"
env -u LD_LIBRARY_PATH "$PREFIX/bin/chromium-browser" --version | tee "$OUT/chromium-version.txt"

mkdir -p "$work/site"
cat > "$work/site/index.html" <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Hermes Android browser probe</title></head>
<body><h1>Hermes loopback probe</h1><button id="change" onclick="document.getElementById('result').textContent='Clicked successfully'">Change result</button><p id="result">Before click</p></body></html>
HTML
"$HERMES_PROBE_PYTHON" -B - "$work/site" "$work/port" > "$OUT/http-server.log" 2>&1 <<'PY' &
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
import sys
site, port_file = sys.argv[1:]
server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=site))
Path(port_file).write_text(str(server.server_port))
server.serve_forever()
PY
server_pid=$!
"$HERMES_PROBE_PYTHON" -B - "$work/port" <<'PY'
from pathlib import Path
import sys, time
deadline = time.monotonic() + 15
while not Path(sys.argv[1]).is_file():
    if time.monotonic() >= deadline:
        raise SystemExit("loopback fixture did not start")
    time.sleep(0.1)
PY
port="$(cat "$work/port")"
browser() {
  # The browser uses current APT libraries; the Python bundle's scoped libraries
  # must not override its newer native dependency closure.
  env -u LD_LIBRARY_PATH "$work/agent-browser" --session hermes-compat \
    --executable-path "$PREFIX/bin/chromium-browser" \
    --args '--no-sandbox,--disable-dev-shm-usage' --json "$@"
}
browser open "http://127.0.0.1:$port/" | tee "$OUT/browser-open.json"
browser snapshot -i | tee "$OUT/browser-snapshot-before.json"
browser click '#change' | tee "$OUT/browser-click.json"
browser eval "document.getElementById('result').textContent" | tee "$OUT/browser-eval.json"
browser screenshot "$OUT/browser-loopback.png" | tee "$OUT/browser-screenshot.json"
browser close | tee "$OUT/browser-close.json"
"$HERMES_PROBE_PYTHON" -B - "$OUT" <<'PY'
from pathlib import Path
import json, sys
out = Path(sys.argv[1])
for name in ("browser-open", "browser-snapshot-before", "browser-click", "browser-eval", "browser-screenshot", "browser-close"):
    result = json.loads((out / (name + ".json")).read_text())
    assert result.get("success") is True, (name, result)
result = json.loads((out / "browser-eval.json").read_text())
assert result["data"]["result"] == "Clicked successfully", result
assert (out / "browser-loopback.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
(out / "browser-probe-passed.txt").write_text("Native Termux ARM64 static CLI and APT Chromium: navigation, snapshot, click, evaluation, screenshot, close passed. No physical Android display was tested.\n")
PY
