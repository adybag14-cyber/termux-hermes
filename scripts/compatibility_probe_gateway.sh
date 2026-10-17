#!/usr/bin/env bash
# Native next-stable probe only: isolated fixture services, no messenger sessions.
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
: "${PREFIX:?}" "${HERMES_PROBE_PAYLOAD:?}"
[[ "$(id -u)" = 1000 ]] || { echo "Gateway proof must run as Termux app UID1000" >&2; exit 1; }
mkdir -p "$OUT"
work="$(mktemp -d "$PREFIX/tmp/hg.XXXXXX")"
cleanup() {
  chmod -R a+rX "$OUT" 2>/dev/null || true
  if [[ -f "$work/cleanup-complete" ]]; then rm -rf "$work"; else echo "Retained gateway fixture evidence at $work" >&2; fi
}
trap cleanup EXIT
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 install -y termux-services
env -u LD_LIBRARY_PATH dpkg-query -W -f='${Package} ${Version}\n' termux-services runit > "$OUT/gateway-packages.txt"
export PYTHONPATH="$SOURCE" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export HERMES_RUNTIME_DIR="$HERMES_PROBE_PAYLOAD/tools"
"$HERMES_PROBE_PAYLOAD/venv/bin/python" -B - "$OUT" "$work" <<'PY'
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import signal
import sys
import time

from hermes_cli import gateway, gateway_runit as runit
from hermes_constants import reset_hermes_home_override, set_hermes_home_override

out, work = map(Path, sys.argv[1:])
assert sys.platform == "android" and gateway.is_termux()
assert os.geteuid() == 1000
assert runit.available()
fixture = work / "fixture.py"
fixture.write_text(
    "from pathlib import Path\n"
    "import json, os, signal\n"
    "home=Path(os.environ['HERMES_HOME'])\n"
    "record={'uid':os.geteuid(),'pid':os.getpid(),'home':str(home),"
    "'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]}\n"
    "def finish(*args):\n"
    "    (home/'stopped.json').write_text(json.dumps(record))\n"
    "    raise SystemExit(0)\n"
    "signal.signal(signal.SIGTERM, finish)\n"
    "staging=home/'ready.tmp'\n"
    "staging.write_text(json.dumps(record))\n"
    "staging.replace(home/'ready.json')\n"
    "while True: signal.pause()\n"
)
fixture_command = [
    str(Path(os.environ["PREFIX"]) / "bin" / "env"),
    "LD_LIBRARY_PATH=" + os.environ.get("LD_LIBRARY_PATH", ""),
    sys.executable, "-I", str(fixture),
]
homes = [work / "profile a's space", work / "other root" / "profile a's space"]
for home in homes:
    home.mkdir(parents=True)
    (home / "config.yaml").write_text("gateway:\n  multiplex_profiles: false\n")
events = []


@contextmanager
def profile(home):
    old = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    token = set_hermes_home_override(home)
    try:
        yield
    finally:
        reset_hermes_home_override(token)
        if old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = old


def command(verb, **flags):
    args = SimpleNamespace(gateway_command=verb, **flags)
    gateway.gateway_command(args)


def ready(service, *, different=None):
    deadline = time.monotonic() + 15
    while True:
        try:
            record = json.loads((service.home / "ready.json").read_text())
        except (OSError, ValueError):
            record = None
        state = service.state()
        if record and record["pid"] == state.pid and record["pid"] != different:
            assert record["uid"] == 1000 and record["home"] == str(service.home)
            events.append({"event": "ready", "service": service.path.name, **record})
            return record
        if time.monotonic() >= deadline:
            raise AssertionError(f"fixture did not become ready: {state}")
        time.sleep(0.1)


def still_same_process(record):
    try:
        current = Path(f"/proc/{record['pid']}/stat").read_text().rsplit(")", 1)[1].split()[19]
        return current == record["start_ticks"]
    except FileNotFoundError:
        return False


services = []
try:
    for i, home in enumerate(homes):
        with profile(home):
            assert gateway._service_backend() == "runit"
            service = runit.current()
            services.append(service)
            # Substitute only the workload. Backend discovery, service generation,
            # ownership checks, facade dispatch and real sv lifecycle stay intact.
            with patch.object(runit, "command_for_service", return_value=fixture_command):
                command("install", force=True, start_now=False, start_on_login=(i == 0))
            assert service.state().installed and not service.state().running
            assert (service.path / "down").exists() is (i != 0)
            command("start")
            ready(service)
            snapshot = gateway.get_gateway_runtime_snapshot()
            assert snapshot.service_running and snapshot.manager == "Termux runit"
            command("status")
    first, second = services
    assert first.path != second.path
    first_record, second_record = ready(first), ready(second)
    with profile(first.home):
        command("restart")
        restarted = ready(first, different=first_record["pid"])
        assert not still_same_process(first_record)
        assert second.state().pid == second_record["pid"]
        # Prove native crash supervision on this exact owned fixture PID.
        proc = Path(f"/proc/{restarted['pid']}")
        assert str(fixture).encode() in (proc / "cmdline").read_bytes().split(b"\0")
        assert b"HERMES_HOME=" + str(first.home).encode() in (proc / "environ").read_bytes().split(b"\0")
        assert still_same_process(restarted)
        os.kill(restarted["pid"], signal.SIGKILL)
        recovered = ready(first, different=restarted["pid"])
        command("stop")
        assert not first.state().running and not still_same_process(recovered)
        assert second.state().pid == second_record["pid"]
        command("uninstall")
        assert not first.path.exists()
        assert second.state().pid == second_record["pid"]
    with profile(second.home):
        command("stop")
        command("uninstall")
        assert not second.path.exists() and not still_same_process(second_record)
    (out / "gateway-runit-evidence.json").write_text(json.dumps({
        "platform": sys.platform, "uid": os.geteuid(), "events": events,
        "lifecycle": ["install-no-start", "start", "status", "restart", "crash-respawn", "stop", "uninstall"],
        "independent_homes": [str(home) for home in homes],
        "same_profile_basename_isolated": True,
        "login_policy_separate_from_start_now": True,
        "shared_service_daemon_stopped": False,
        "scope": "Native Termux runit and product gateway dispatch with harmless fixture workers; no Android force-stop persistence claim.",
    }, indent=2) + "\n")
    (out / "gateway-probe-passed.txt").write_text(
        "Termux UID1000 runit: install/start/status/restart/crash recovery/stop/uninstall and isolated profile homes passed.\n"
    )
finally:
    failures = []
    for service in services:
        log = service.home / "logs" / "gateway-runit.log"
        if log.exists():
            (out / (service.path.name + ".log")).write_bytes(log.read_bytes())
        try:
            service.uninstall()
        except Exception as exc:
            failures.append(str(exc))
    if failures:
        raise AssertionError("Fixture service cleanup failed: " + "; ".join(failures))
    (work / "cleanup-complete").touch()
PY
