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
  # The native container may write evidence as root; the host uploader must read it.
  chmod -R a+rX "$OUT" 2>/dev/null || true
  if [[ -x "$work/agent-browser" ]]; then
    env -u LD_LIBRARY_PATH "$work/agent-browser" --session hermes-compat close >/dev/null 2>&1 || true
  fi
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
mkdir -p "$PREFIX/etc/apt/sources.list.d"
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

# Exercise the proposed product route against the installed payload's real PM
# runtime. These source overlays exist only in this disposable probe container.
cp -R "$SOURCE/pm/." "$HERMES_PROBE_PAYLOAD/app/pm/"
for relative in hermes_cli/browser_runtime.py tools/browser_tool_install.py tools/browser_tool_session.py; do
  cp "$SOURCE/$relative" "$HERMES_PROBE_PAYLOAD/app/$relative"
done
export HERMES_HOME="$work/pm-home" HERMES_RUNTIME_DIR="$HERMES_PROBE_PAYLOAD/tools"
export PYTHONPATH="$HERMES_PROBE_PAYLOAD/app" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export AGENT_BROWSER_PROFILE="$work/pm-profile"
mkdir -p "$HERMES_HOME" "$AGENT_BROWSER_PROFILE"
# Browser Use CLI is the upstream default when browser-harness is installed.
# This probe intentionally exercises the built-in browser_* surface, selected by
# the documented "off" backend (it disables Browser Use CLI, not local browsing).
cat > "$HERMES_HOME/config.yaml" <<'YAML'
browser:
  backend: "off"
YAML
"$HERMES_PROBE_PAYLOAD/venv/bin/python" -B - "$work" "$OUT" "$port" <<'PY'
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

import pm
from hermes_cli.browser_runtime import chromium_executable
from tools import browser_tool_install as install
from tools import browser_tool_session as session
from tools import browser_use_cli

work, out = map(Path, sys.argv[1:3])
port = int(sys.argv[3])
assert sys.platform == "android" and os.geteuid() == 1000
assert pm.current_target() == "linux-arm64-bionic"
pm.ensure("agent-browser", explicit=True)
driver = install._find_agent_browser(validate=False)
installed = pm.installed_package("agent-browser")
assert installed is not None and installed.binary == Path(driver)
assert pm.installed_package("chromium") is None, "APT Chromium must not be recorded as a PM-owned artifact"
chromium = chromium_executable()
assert chromium == os.environ["PREFIX"] + "/bin/chromium-browser", chromium
backend = browser_use_cli.get_browser_backend()
browser_use_mode = browser_use_cli.is_browser_use_cli_mode()
ready = install.check_browser_requirements()
(out / "browser-pm-preflight.json").write_text(json.dumps({
    "target": pm.current_target(), "uid": os.geteuid(),
    "driver": driver, "chromium": chromium, "chromium_owner": "Termux APT",
    "browser_backend": backend, "browser_use_cli_mode": browser_use_mode,
    "built_in_browser_readiness": ready,
}, indent=2) + "\n")
assert backend == "off" and not browser_use_mode, "the isolated profile must select the built-in browser surface"
assert ready, "the product readiness gate must advertise the proven local browser"
socket_dir = work / "pm-sockets"
socket_dir.mkdir(mode=0o700)
env = session._agent_browser_command_env(str(socket_dir))
session._apply_chromium_sandbox_args(env)
assert env["AGENT_BROWSER_EXECUTABLE_PATH"] == chromium
assert "LD_LIBRARY_PATH" not in env
assert "LD_LIBRARY_PATH" in os.environ, "the Python parent must keep its own library environment"
assert env["AGENT_BROWSER_ARGS"] == "--no-sandbox,--disable-dev-shm-usage"

def command(name, *args):
    result = subprocess.run(
        [driver, "--session", "hermes-pm", "--json", *args], env=env,
        capture_output=True, text=True, check=True, timeout=90,
    )
    (out / ("pm-browser-" + name + ".json")).write_text(result.stdout)
    parsed = json.loads(result.stdout)
    assert parsed.get("success") is True, parsed
    return parsed

try:
    command("open", "open", f"http://127.0.0.1:{port}/")
    command("snapshot", "snapshot", "-i")
    command("click", "click", "#change")
    result = command("eval", "eval", "document.getElementById('result').textContent")
    assert result["data"]["result"] == "Clicked successfully", result
    command("screenshot", "screenshot", str(out / "pm-browser-loopback.png"))
    assert (out / "pm-browser-loopback.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
finally:
    command("close", "close")
(out / "browser-pm-evidence.json").write_text(json.dumps({
    "target": pm.current_target(), "uid": os.geteuid(), "version": installed.version,
    "driver": driver, "driver_sha256": hashlib.sha256(Path(driver).read_bytes()).hexdigest(),
    "chromium": chromium, "chromium_owner": "Termux APT",
    "browser_backend": backend, "browser_surface": "built-in browser_*",
    "product_readiness": True, "pm_install_and_child_environment": True,
    "physical_android_display_tested": False,
}, indent=2) + "\n")
(out / "browser-pm-probe-passed.txt").write_text(
    "PM-managed static driver, actual Hermes discovery/readiness/environment, and APT Chromium completed the native loopback workflow.\n"
)
PY


# The normal default is browser_exec/browser-harness. It reaches the same PM
# driver through _resolve_managed_chromium_cdp and must work without a backend
# override, external CDP URL, or a separately selected provider.
printf '{}\n' > "$HERMES_HOME/config.yaml"
export AGENT_BROWSER_PROFILE="$work/default-profile"
mkdir -p "$AGENT_BROWSER_PROFILE"
"$HERMES_PROBE_PAYLOAD/venv/bin/python" -B - "$OUT" "$port" <<'PY'
from pathlib import Path
import importlib.metadata
import json
import os
import sys

import pm
from tools import browser_tool_install as install
from tools import browser_tool_lifecycle as lifecycle
from tools import browser_use_cli

out = Path(sys.argv[1])
port = int(sys.argv[2])
assert sys.platform == "android" and os.geteuid() == 1000
assert browser_use_cli.get_browser_backend() == ""
assert not os.environ.get("BU_CDP_WS") and not os.environ.get("BU_CDP_URL")
assert not os.environ.get("BROWSER_CDP_URL")
assert browser_use_cli.is_browser_use_cli_mode(), "browser_exec must be the default advertised surface"
assert not install.check_browser_requirements(), "built-in tools must stay hidden while browser_exec owns the surface"
assert browser_use_cli._find_cli() == [sys.executable, "-m", "browser_harness.run"]
(out / "browser-default-preflight.json").write_text(json.dumps({
    "target": pm.current_target(), "uid": os.geteuid(),
    "browser_backend": "", "browser_use_cli_mode": True,
    "built_in_browser_readiness": False,
    "harness_version": importlib.metadata.version("browser-harness"),
    "operator_cdp_override": False,
}, indent=2) + "\n")

screenshot = out / "browser-default-loopback.png"
# The pinned harness marks controlled tabs with a cosmetic horse-title prefix.
# Keep that product behavior and verify fixture identity through URL and DOM.
code = (
    "# Checking the native default browser\n"
    "import base64, json\n"
    "from pathlib import Path\n"
    f"new_tab({json.dumps(f'http://127.0.0.1:{port}/')})\n"
    "wait_for_load()\n"
    "title = js('document.title')\n"
    f"assert js('location.href') == {json.dumps(f'http://127.0.0.1:{port}/')}\n"
    "assert js(\"document.querySelector('h1').textContent\") == 'Hermes loopback probe'\n"
    "before = js(\"document.getElementById('result').textContent\")\n"
    "js(\"document.getElementById('change').click()\")\n"
    "after = js(\"document.getElementById('result').textContent\")\n"
    "assert title.removeprefix('🐴 ') == 'Hermes Android browser probe', title\n"
    "assert before == 'Before click', before\n"
    "assert after == 'Clicked successfully', after\n"
    "shot = cdp('Page.captureScreenshot', format='png')\n"
    f"Path({json.dumps(str(screenshot))}).write_bytes(base64.b64decode(shot['data']))\n"
    "print('HERMES_DEFAULT_BROWSER_OK ' + json.dumps({'title': title, 'before': before, 'after': after}))\n"
)
try:
    raw = browser_use_cli.browser_exec(code, session="compatdefault", timeout_s=90, task_id="compatdefault")
    result = json.loads(raw)
    (out / "browser-default-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result.get("success") is True, result
    assert result.get("exit_code") == 0, result
    assert "HERMES_DEFAULT_BROWSER_OK" in result.get("output", ""), result
    assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
finally:
    browser_use_cli.stop_harness_daemons()
    lifecycle.cleanup_all_browsers()
(out / "browser-default-probe-passed.txt").write_text(
    "Default browser_exec/browser-harness with no backend or CDP override used the managed local route and completed native navigation, DOM click/readback, CDP screenshot, and cleanup.\n"
)
PY
