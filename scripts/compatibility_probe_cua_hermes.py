#!/usr/bin/env python3
"""Exercise real Hermes computer_use against one owned native Termux X11 fixture.

Invoke with the SHA-verified candidate's <payload>/venv/bin/python, preserving its
bundle loader environment. --source is a separate Hermes checkout with the
experimental cua-hermes-integration.patch applied. The caller provisions the
product Bot Desktop package set and passes the standalone probe's Xlib fixture.
--candidate-receipt names the verified fetch receipt, beside its two unchanged
raw JSON files. The exact candidate/run/artifact is pinned below, and its native
catalog, locks, and feature selection are checked against the running payload.
This helper installs nothing and must run before that fixture is removed.

Scope: provider/registry admission, the normal MCP backend, private Bot Desktop
pixels and input, one-action fixture approvals, and viewer lease refusal.
Android phone UI, AT-SPI content, history/preview, and physical devices are not
certified by this experiment.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any

SOURCE_FILES = (
    "plugins/computer_use/__init__.py", "plugins/computer_use/cua/__init__.py",
    "tools/computer_use_tool.py", "tools/registry.py", "tools/computer_use/tool.py",
    "tools/computer_use/cua_backend.py", "tools/computer_use/cua_backend_platform.py",
    "tools/computer_use/cua_backend_driver.py", "tools/computer_use/cua_backend_session.py",
    "tools/computer_use/cua_backend_capture.py", "tools/computer_use/cua_backend_input.py",
    "tools/computer_use/permissions.py", "tools/approval.py", "tools/approval_context.py",
    "tools/bot_desktop/runtime.py", "tools/bot_desktop/termux.py", "tools/bot_desktop/lease.py",
    "tools/bot_desktop/launcher.sh",
    "pm/lock.json", "uv.lock", "pyproject.toml",
)
PAYLOAD_FILES = ("manifest.json", "bundled-wheels.json", "enabled-features.json", "app/uv.lock", "app/pm/lock.json")
LEFT_RGB, RIGHT_RGB = (0x22, 0x44, 0x66), (0x55, 0xCC, 0x88)
SHA256 = re.compile(r"[a-f0-9]{64}")
FOREGROUND_NOTICE = " [FOREGROUND — briefly raises the window / changes focus]"


class ProbeFailure(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pin_executable(path: Path, expected: str | None = None) -> dict[str, Any]:
    require(path.is_file() and os.access(path, os.X_OK), f"not an executable file: {path}")
    with path.open("rb") as stream:
        header = stream.read(20)
    require(header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\xb7\x00",
            f"expected a native little-endian AArch64 ELF: {path}")
    actual = digest(path)
    if expected is not None:
        require(SHA256.fullmatch(expected) is not None, "driver SHA-256 must be 64 lowercase hex digits")
        require(actual == expected, "native driver SHA-256 differs from the reviewed standalone build")
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def file_identity(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: digest(root / name) for name in names}


# This experiment deliberately consumes the already-proven candidate; changing it
# requires a new reviewed source/receipt pin, not accepting arbitrary same-version .debs.
CANDIDATE = {
    "repository": "adybag14-cyber/termux-hermes",
    "run_id": 39048514731,
    "head_sha": "e271e922a2e71fd18591c45e9b98b8c7f9fffe02",
    "artifact_id": 12107225801,
    "artifact_sha256": "c49f41590424520b99136800b7ba9fa41f3ab3926d418131cdf686da812d849b",
    "package_sha256": "1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a",
}
CANDIDATE_RAW_FILES = {
    "identity": ("CANDIDATE-IDENTITY.json", "bd45eceb7ffecf4e892243f6e964fd28337f1be20abee39435d934cc768fb5a5"),
    "native_selection": ("venv-selection.json", "5d7eef31190f9152c3b8005f3c9cc8bb05a69fdb57b883c648edcfe4db2cf1ce"),
}


def read_candidate_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == 1
            and data.get("status") == "verified", "candidate fetch receipt is not verified schema 1")
    for name in ("repository", "run_id", "head_sha"):
        require(data.get(name) == CANDIDATE[name], f"candidate receipt {name} differs from the proven candidate")
    artifact, package = data.get("artifact", {}), data.get("package", {})
    require(artifact.get("id") == CANDIDATE["artifact_id"] and artifact.get("name") == "hermes-termux-next-stable-candidate"
            and artifact.get("sha256") == CANDIDATE["artifact_sha256"], "candidate artifact identity differs")
    require(package.get("file") == "hermes-agent_0.22.2-1_aarch64.deb" and package.get("bytes") == 222089768
            and package.get("sha256") == CANDIDATE["package_sha256"], "candidate package identity differs")
    for key, (name, sha256) in CANDIDATE_RAW_FILES.items():
        entry = data.get(key, {})
        require(entry.get("file") == name and entry.get("sha256") == sha256, f"candidate {key} raw identity differs")
        raw_path = path.parent / name
        require(digest(raw_path) == sha256, f"candidate {key} raw bytes differ")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        require({k: v for k, v in entry.items() if k not in {"file", "sha256", "zip_member"}} == raw,
                f"candidate {key} fields differ from the verified raw file")
    return data


def verify_native_selection(selection: dict[str, Any], payload_hashes: dict[str, str],
                            source_hashes: dict[str, str], manifest: dict[str, Any], features: Any) -> None:
    require(selection.get("target") == "linux-arm64-bionic", "candidate selection target is not native Bionic")
    require(selection.get("bundled_wheels") == {"path": "bundled-wheels.json", "sha256": payload_hashes["bundled-wheels.json"]}
            and manifest.get("bundled_wheels") == selection["bundled_wheels"],
            "actual candidate wheel catalog differs from the verified native selection")
    for field, payload_name, source_name in (("uv_lock_sha256", "app/uv.lock", "uv.lock"),
                                            ("pm_lock_sha256", "app/pm/lock.json", "pm/lock.json")):
        require(payload_hashes[payload_name] == selection.get(field) == source_hashes[source_name],
                f"candidate or experimental source {field} differs from the tested native selection")
    require(features == {"schema": 1, "extras": selection.get("extras")}, "candidate's exact selected extras differ")


def json_object(value: Any) -> dict[str, Any]:
    result = json.loads(value) if isinstance(value, str) else value
    require(isinstance(result, dict), "registered handler returned a non-object result")
    return result


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    require(path.stat().st_size <= 1024 * 1024, "owned fixture event log exceeded its bounded size")
    text = path.read_text(encoding="utf-8")
    # stdout is line buffered; the writer can still be between write() calls.
    complete = text.splitlines() if text.endswith("\n") else text.splitlines()[:-1]
    events = [json.loads(line) for line in complete]
    require(all(isinstance(event, dict) and isinstance(event.get("event"), str) for event in events),
            "fixture emitted a malformed completed JSONL event")
    return events


def input_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event["event"] in {"key", "button"}]


def require_button_events(events: list[dict[str, Any]], *, button: int, count: int, x: int, y: int) -> None:
    wanted = [{"event": "button", "button": button, "x": x, "y": y}] * count
    require(input_events(events) == wanted, f"fixture input differed from exact button oracle: {input_events(events)!r}")


def require_text_events(events: list[dict[str, Any]], expected: str) -> None:
    inputs = input_events(events)
    require(all(event["event"] == "key" for event in inputs), "text action emitted an unexpected button event")
    try:
        delivered = b"".join(bytes.fromhex(event["hex"]) for event in inputs).decode("ascii")
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ProbeFailure(f"invalid XLookupString key event: {exc}") from exc
    require(delivered == expected, f"fixture text differs: expected {expected!r}, observed {delivered!r}")


def capture_evidence(result: Any, out: Path) -> dict[str, Any]:
    """Validate the actual tool-result image, independently of driver ok/metadata."""
    from PIL import Image

    body = json_object(result)
    require(body.get("_multimodal") is True, f"capture did not return the native image envelope: {body!r}")
    images = [part for part in body.get("content", []) if part.get("type") == "image_url"]
    require(len(images) == 1, "capture must contain exactly one image")
    url = images[0].get("image_url", {}).get("url", "")
    match = re.fullmatch(r"data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=\r\n]+)", url)
    require(match is not None, "capture image is not an inline PNG/JPEG")
    raw = base64.b64decode(match.group(2), validate=True)
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        image = source.convert("RGB")
        require(source.format == ("PNG" if match.group(1) == "image/png" else "JPEG"), "capture MIME disagrees with its bytes")
        require(image.size == (320, 240), f"capture is not the owned 320x240 client: {image.size}")
        samples = {"left": image.getpixel((80, 120)), "right": image.getpixel((240, 120))}
        # The normal vision backend may request JPEG quality 85.
        for name, expected in (("left", LEFT_RGB), ("right", RIGHT_RGB)):
            require(all(abs(a - b) <= 8 for a, b in zip(samples[name], expected)),
                    f"capture lacks the independently specified {name} fixture color: {samples}")
    suffix = ".png" if match.group(1) == "image/png" else ".jpg"
    path = out / ("hermes-cua-fixture" + suffix)
    path.write_bytes(raw)
    return {"file": path.name, "sha256": digest(path), "bytes": len(raw),
            "dimensions": [320, 240], "sample_rgb": samples, "tool_meta": body.get("meta")}


def wait_until(predicate, label: str, *, seconds: float = 15.0):
    deadline = time.monotonic() + seconds
    while True:
        result = predicate()
        if result:
            return result
        require(time.monotonic() < deadline, f"timed out waiting for {label}")
        time.sleep(0.05)


def inet_listeners(pid: int) -> list[dict[str, str]]:
    inodes = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            link = os.readlink(fd)
        except FileNotFoundError:
            continue
        if link.startswith("socket:["):
            inodes.add(link[8:-1])
    result = []
    for table in ("tcp", "tcp6"):
        for line in Path(f"/proc/net/{table}").read_text().splitlines()[1:]:
            columns = line.split()
            if len(columns) >= 10 and columns[3] == "0A" and columns[9] in inodes:
                result.append({"table": table, "local": columns[1], "inode": columns[9]})
    return result


class TransportLog(logging.Handler):
    """Observe the real transport's fallback diagnostics without replacing it."""
    def __init__(self) -> None:
        super().__init__()
        self.fallbacks: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "CLI transport" in message or "falling back to CLI" in message:
            self.fallbacks.append(message)


class FixtureApproval:
    """One explicit callback answer for one pre-armed, known fixture action."""
    def __init__(self, child: subprocess.Popen, records: list[dict[str, Any]]) -> None:
        self.child, self.records, self.pending = child, records, None

    def arm(self, action: str, summary: str) -> None:
        require(self.pending is None, "a previous fixture approval is still armed")
        self.pending = (action, "computer_use: " + summary + FOREGROUND_NOTICE)

    def __call__(self, command: str, description: str, **kwargs) -> str:
        require(self.child.poll() is None, "owned fixture exited before approval")
        require(self.pending is not None, "unexpected or repeated approval request")
        action, expected_command = self.pending
        self.pending = None  # even a mismatched prompt consumes this answer
        require(command == expected_command, f"unexpected approval target: {command!r}")
        require(description == f"Allow computer_use to perform `{action}`?", "unexpected approval scope")
        self.records.append({"action": action, "command": command, "description": description,
                             "choice": "once", "fixture_pid": self.child.pid})
        return "once"


def configure_environment(work: Path, payload: Path) -> Path:
    # All state belongs to this new disposable profile, including the driver's
    # ordinary history/preferences. No history or consent preference is disabled.
    for key, name in (("HOME", "home"), ("HERMES_HOME", "profile"), ("TMPDIR", "tmp"),
                      ("XDG_RUNTIME_DIR", "run"), ("XDG_CONFIG_HOME", "config"),
                      ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        path = work / name
        path.mkdir(mode=0o700)
        os.environ[key] = str(path)
    for key in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY",
                "HERMES_CUA_DRIVER_CMD", "HERMES_YOLO_MODE", "HERMES_GATEWAY_SESSION",
                "HERMES_EXEC_ASK", "HERMES_SESSION_PLATFORM", "HERMES_CRON_SESSION",
                "HERMES_SINGLE_QUERY_SESSION", "CUA_DRIVER_PERMISSION_MODE",
                "CUA_DRIVER_CAPABILITY_MANIFEST", "CUA_DRIVER_SOCKET"):
        os.environ.pop(key, None)
    os.environ.update(HERMES_RUNTIME_DIR=str(payload / "tools"), TERMINAL_ENV="local",
                      PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    home = work / "profile"
    (home / "config.yaml").write_text(
        "terminal:\n  backend: local\nbot_desktop:\n  placement: gateway\n  geometry: '800x600'\n"
        "computer_use:\n  backend: cua\n  permission_mode: standard\n  no_overlay: true\n  cua_telemetry: false\n"
        "approvals:\n  mode: manual\nsecurity:\n  allow_lazy_installs: false\n"
        "model:\n  provider: openai\n  default: gpt-4o\nagent:\n  image_input_mode: native\n",
        encoding="utf-8",
    )
    return home


def run_probe(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.geteuid() == 1000,
            "invoke with the candidate's native Bionic application interpreter as Termux UID1000")
    source, driver, fixture, out = (Path(getattr(args, key)).resolve() for key in ("source", "driver", "fixture", "out"))
    payload = Path(sys.prefix).resolve().parent
    require(Path(sys.prefix).resolve().name == "venv" and (payload / "tools").is_dir(),
            "interpreter must be the verified candidate's payload/venv/bin/python")
    require((payload / "app/.install_method").read_text().strip() == "apt", "candidate must retain sealed APT provenance")
    require(not source.is_relative_to(payload), "--source must be separate from the immutable candidate payload")
    before_source, before_payload = file_identity(source, SOURCE_FILES), file_identity(payload, PAYLOAD_FILES)
    manifest = json.loads((payload / "manifest.json").read_text())
    candidate_receipt_path = Path(args.candidate_receipt).resolve()
    candidate_receipt = read_candidate_receipt(candidate_receipt_path)
    verify_native_selection(candidate_receipt["native_selection"], before_payload, before_source, manifest,
                            json.loads((payload / "enabled-features.json").read_text()))
    receipt["candidate_receipt"] = {"path": str(candidate_receipt_path), "sha256": digest(candidate_receipt_path),
                                    "verified": candidate_receipt}
    receipt["driver"] = pin_executable(driver, args.driver_sha256)
    receipt["fixture_executable"] = pin_executable(fixture)
    receipt["interpreter"] = {"executable": sys.executable, "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                              "version": sys.version, "executable_sha256": digest(Path("/proc/self/exe"))}
    receipt["payload"] = {"root": str(payload), "file_sha256": before_payload}
    receipt["source"] = {"root": str(source), "file_sha256": before_source}
    require(not any(name in sys.modules for name in ("hermes_constants", "tools.computer_use.tool", "pm")),
            "Hermes was imported before the isolated source/profile were selected")
    prefix = Path(os.environ.get("PREFIX", ""))
    require(prefix.is_absolute() and (prefix / "tmp").is_dir(), "native Termux PREFIX/tmp is required")
    work = Path(tempfile.mkdtemp(prefix="hc.", dir=prefix / "tmp"))
    fixture_child = None
    runtime = lease = approval = tool = context = None
    session_token = interactive_token = None
    owned_children, fixture_streams = [], []
    session_id, viewer_id = "cua-hermes-fixture", "owned-cua-probe-viewer"
    desktop = None
    logger = logging.getLogger("tools.computer_use.cua_backend")
    transport_log = TransportLog()
    logger.addHandler(transport_log)
    completed = False
    try:
        configure_environment(work, payload)
        os.chdir(source)
        sys.path.insert(0, str(source))
        import mcp
        import PIL
        import psutil
        from hermes_platform.host.runtime import is_termux
        from plugins.computer_use import get_active_provider
        from tools.bot_desktop import lease, placement, runtime, termux
        from tools import approval, approval_context as context
        from tools.computer_use import cua_backend, permissions, tool
        from tools.computer_use.cua_backend_driver import cua_driver_runtime_contract_status
        import tools.computer_use_tool  # real discovery registration
        from tools.registry import registry

        require(is_termux(), "the actual platform resolver must identify Termux")
        for module in (runtime, tool, cua_backend, permissions):
            require(Path(module.__file__).resolve().is_relative_to(source), "product module loaded outside --source")
        for module in (mcp, PIL, psutil):
            require(Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
                    f"{module.__name__} did not load from the candidate application environment")
        receipt["dependencies"] = {name: importlib.metadata.version(name) for name in ("mcp", "Pillow", "psutil")}
        where = placement.resolve()
        require(where.where == placement.GATEWAY and where.backend == "local", "probe desktop placement is not local")
        session_token = context.set_current_session_key(session_id)
        interactive_token = context.set_hermes_interactive_context(False)
        require(not approval.is_approval_bypass_active_for_session(session_id), "approval bypass is active")
        require(not lease.human_holds(), "new profile unexpectedly has a human lease")
        require(not get_active_provider().is_available(), "default PM path unexpectedly advertises a Termux CUA artifact")
        os.environ["HERMES_CUA_DRIVER_CMD"] = str(driver)
        require(get_active_provider().is_available(), "explicit Termux provider is unavailable")
        require(registry.is_toolset_available("computer_use"), "computer_use is not exposable through the real registry")
        require(any(row["function"]["name"] == "computer_use" for row in registry.get_definitions({"computer_use"})),
                "provider availability did not expose the registered tool definition")
        receipt["availability"] = {"default_without_override": False, "explicit_provider": True, "registered_toolset": True}
        require(not runtime.published_env(), "the fresh profile already has a published desktop")
        parent_loader_path = os.environ.get("LD_LIBRARY_PATH")
        require(parent_loader_path and str(payload) in parent_loader_path,
                "the candidate Python must retain its actual bundled loader path")
        before_desktop_env = cua_backend.sanitized_cua_driver_env()
        require("LD_LIBRARY_PATH" not in before_desktop_env,
                "native CUA inherited the candidate loader path before desktop startup")
        early_contract = cua_driver_runtime_contract_status(str(driver))
        require(early_contract.get("ready") is True,
                f"native driver manifest failed before desktop startup: {early_contract}")
        require(os.environ.get("LD_LIBRARY_PATH") == parent_loader_path,
                "pre-desktop native CUA inspection changed the parent Python loader environment")
        receipt["pre_desktop_runtime_contract"] = early_contract
        receipt["checks"].append("pre-desktop-native-driver-uses-system-libraries")
        require(runtime.is_supported_host() and not runtime.missing_binaries(),
                f"caller must provision product Bot Desktop packages: {runtime.missing_binaries()}")
        desktop = runtime.start(wait_seconds=45)
        require(desktop.running and desktop.supported and desktop.installed, f"product desktop did not start: {desktop.as_dict()}")
        published = runtime.published_env()
        require(all(published.get(name) for name in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS")),
                "product desktop has not published its complete environment")
        child_env = cua_backend.sanitized_cua_driver_env()
        require(all(child_env.get(key) == value for key, value in published.items()), "driver environment missed the product desktop")
        socket_path = runtime.rfb_socket_path()
        require(socket_path is not None and stat.S_ISSOCK(socket_path.stat().st_mode), "product RFB socket is missing")
        require(stat.S_IMODE(socket_path.stat().st_mode) == 0o600 and stat.S_IMODE(runtime.state_dir().stat().st_mode) == 0o700,
                "product desktop is not private")
        xvnc_pid = runtime._x_lock_pid(int(desktop.display.lstrip(":")))
        require(xvnc_pid is not None and not inet_listeners(xvnc_pid), "owned Xvnc exposes a TCP listener")
        receipt["desktop"] = {**desktop.as_dict(), "published": published, "xvnc_pid": xvnc_pid, "tcp_listeners": []}
        contract = cua_driver_runtime_contract_status(str(driver))
        receipt["runtime_contract"] = contract
        require(contract.get("ready") is True, f"actual driver runtime manifest failed: {contract}")
        event_path = out / "hermes-cua-fixture.jsonl"
        fixture_streams = [event_path.open("wb"), (out / "hermes-cua-fixture.stderr").open("wb")]
        fixture_child = subprocess.Popen([str(fixture)], stdin=subprocess.DEVNULL, stdout=fixture_streams[0],
                                         stderr=fixture_streams[1], env=termux.system_env({**os.environ, **published}))

        def events():
            require(fixture_child.poll() is None, f"owned fixture exited with {fixture_child.returncode}")
            return read_events(event_path)

        ready = wait_until(lambda: next((row for row in events() if row["event"] == "ready"), None), "owned fixture")
        require(type(ready.get("pid")) is int and ready["pid"] == fixture_child.pid
                and type(ready.get("window_id")) is int and ready["window_id"] > 0, "fixture identity does not match its child")
        wait_until(lambda: any(row.get("event") == "paint" and row.get("width") == 320 and row.get("height") == 240 for row in events()),
                   "owned fixture paint")
        target = {"pid": ready["pid"], "window_id": ready["window_id"]}
        receipt["fixture"] = target

        def managed_window():
            result = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"], env=termux.system_env({**os.environ, **published}),
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
            require(result.returncode == 0, "product window manager inspection failed: " + result.stderr)
            return hex(target["window_id"]).lower() in re.findall(r"0x[0-9a-f]+", result.stdout.lower())
        wait_until(managed_window, "Xfce to manage the owned fixture")
        receipt["readiness"] = permissions.computer_use_status()
        require(receipt["readiness"].get("ready") is True, f"product readiness did not pass: {receipt['readiness']}")

        def dispatch(label: str, arguments: dict[str, Any]) -> Any:
            require(fixture_child.poll() is None, "fixture exited before registered-handler call")
            result = registry.dispatch("computer_use", arguments, session_id=session_id)
            body = json_object(result)
            record = {"label": label, "arguments": arguments,
                      "result": {key: value for key, value in body.items() if key != "content"}}
            receipt["calls"].append(record)
            return result

        def unchanged_inputs(before: list[dict[str, Any]]) -> None:
            time.sleep(0.25)  # bounded negative observation; never replay an input
            require(input_events(events()) == before, "a refused operation changed the owned fixture")

        before = input_events(events())
        denied = json_object(dispatch("no-approver", {"action": "type", "text": "must-not-land", "delivery_mode": "foreground"}))
        require("requires approval" in str(denied.get("error", "")), f"missing approver was not refused: {denied}")
        unchanged_inputs(before)
        receipt["checks"].append("no-approver-input-refused")

        windows = json_object(dispatch("list-windows", {"action": "list_windows"})).get("windows", [])
        require(sum(row.get("pid") == target["pid"] and row.get("window_id") == target["window_id"] for row in windows) == 1,
                "real registered handler did not find the exact owned fixture")
        captured = dispatch("capture", {"action": "capture", "mode": "vision", **target})
        receipt["capture"] = capture_evidence(captured, out)
        receipt["checks"].append("registered-handler-exact-window-and-pixels")

        # Read-only observation of the backend created by registry.dispatch.
        backend = tool._backends.get(tool._scoped_sid(session_id))
        require(isinstance(backend, cua_backend.CuaDriverBackend) and backend.permission_mode == "standard",
                "registered handler did not create the actual standard backend")
        require(backend._session._started and isinstance(backend._session._session, mcp.ClientSession)
                and backend._session.capabilities_discovered, "actual persistent MCP handshake/capability discovery is absent")
        generation = backend._session._transport_generation
        drivers = []
        for process in psutil.Process().children(recursive=True):
            try:
                if process.is_running() and Path(process.exe()).resolve() == driver:
                    drivers.append(process)
            except psutil.NoSuchProcess:
                continue
        require(len(drivers) == 1 and "mcp" in drivers[0].cmdline(), "expected exactly one actual native MCP child")
        driver_process = drivers[0]
        receipt["transport"] = {"kind": "real MCP stdio", "pid": driver_process.pid,
                                "create_time": driver_process.create_time(), "argv": driver_process.cmdline(),
                                "generation": generation, "capability_version": backend._session.capability_version}
        require("--no-overlay" in driver_process.cmdline(), "the normal MCP invocation did not disable its overlay")
        require("--grant" not in driver_process.cmdline() and "unrestricted" not in driver_process.cmdline(),
                "probe driver has a launch grant or permission bypass")

        callback = FixtureApproval(fixture_child, receipt["approvals"])

        def approved_action(label: str, args: dict[str, Any], summary: str, observe) -> None:
            require(backend._active_pid == target["pid"] and backend._active_window_id == target["window_id"],
                    "approval target is not the exact owned fixture")
            before = len(events())
            callback.arm(args["action"], summary)
            token = context.set_hermes_interactive_context(True)
            tool.set_approval_callback(callback)
            try:
                result = json_object(dispatch(label, args))
            finally:
                tool.set_approval_callback(None)
                context.reset_hermes_interactive_context(token)
            require(callback.pending is None, "the action did not request its one-time approval")
            require(result.get("ok") is True, f"native action did not succeed: {result}")
            def observed():
                try:
                    observe(events()[before:])
                    return True
                except ProbeFailure:
                    return False
            wait_until(observed, "exact fixture input delivery")
            time.sleep(0.15)
            observe(events()[before:])
            require(not approval.is_approved(session_id, f"cua:{args['action']}:foreground"), "once approval persisted a grant")
            require(backend._active_pid == target["pid"] and backend._active_window_id == target["window_id"],
                    "input sticky target escaped the owned fixture")

        approved_action("click", {"action": "click", "coordinate": [80, 60], "delivery_mode": "foreground"},
                        "click at (80, 60)", lambda rows: require_button_events(rows, button=1, count=1, x=80, y=60))
        approved_action("scroll", {"action": "scroll", "coordinate": [80, 60], "direction": "down", "amount": 2,
                                  "delivery_mode": "foreground"},
                        "scroll down x2", lambda rows: require_button_events(rows, button=5, count=2, x=80, y=60))
        typed = "hermes-native-input"
        approved_action("type", {"action": "type", "text": typed, "delivery_mode": "foreground"},
                        f"type {typed!r}", lambda rows: require_text_events(rows, typed))
        require(len(receipt["approvals"]) == 3, "approved actions did not each receive exactly one once decision")
        receipt["checks"].append("three-once-approvals-with-independent-input-oracles")

        before = input_events(events())
        denied = json_object(dispatch("once-not-reusable", {"action": "type", "text": "still-must-not-land", "delivery_mode": "foreground"}))
        require("requires approval" in str(denied.get("error", "")), "a once approval became reusable")
        unchanged_inputs(before)

        acquired = lease.acquire(viewer_id, reason="Owned-fixture takeover denial test")
        require(acquired.holder == lease.HUMAN and acquired.viewer_id == viewer_id, "real viewer lease was not acquired")
        receipt["lease"] = {"acquired_epoch": acquired.epoch, "viewer_id": viewer_id}
        for label, arguments in (
            ("lease-blocks-input", {"action": "click", "coordinate": [80, 60], "delivery_mode": "foreground"}),
            ("lease-blocks-capture", {"action": "capture", "mode": "vision", **target}),
        ):
            denied = json_object(dispatch(label, arguments))
            require(denied.get("code") == "human_has_control" and not denied.get("_multimodal"),
                    f"real viewer lease did not refuse {label}")
        unchanged_inputs(before)
        released = lease.release(viewer_id)
        require(released.holder == lease.AGENT and released.epoch > acquired.epoch, "same-viewer hand-back failed")
        receipt["lease"]["released_epoch"] = released.epoch
        after_release = json_object(dispatch("after-hand-back", {"action": "list_windows"}))
        require(any(row.get("pid") == target["pid"] and row.get("window_id") == target["window_id"]
                    for row in after_release.get("windows", [])), "registered handler did not recover after hand-back")
        receipt["checks"].append("real-viewer-lease-blocks-input-and-capture")
        require(backend._session._transport_generation == generation and driver_process.is_running(),
                "native MCP child was replaced during the probe")
        require(not transport_log.fallbacks, f"the MCP proof fell back to CLI: {transport_log.fallbacks}")
        require(digest(driver) == receipt["driver"]["sha256"], "driver changed during execution")
        require(file_identity(source, SOURCE_FILES) == before_source, "Hermes source changed during execution")
        require(file_identity(payload, PAYLOAD_FILES) == before_payload, "sealed candidate inputs changed during execution")
        completed = True
    except Exception as exc:
        receipt["operation_error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        errors = []
        try:
            import psutil
            owned_children = psutil.Process().children(recursive=True)
        except Exception as exc:
            errors.append(f"owned-child census: {exc}")
        if tool is not None:
            tool.set_approval_callback(None)
            try:
                receipt["cleanup"]["session_released"] = tool.release_computer_use_session(session_id)
            except Exception as exc:
                errors.append(f"product session release: {exc}")
        if lease is not None:
            try:
                require(lease.release(viewer_id).holder == lease.AGENT, "owned viewer lease survived hand-back")
            except Exception as exc:
                errors.append(f"owned viewer hand-back: {exc}")
        if fixture_child is not None:
            try:
                if fixture_child.poll() is None:
                    fixture_child.terminate()
                fixture_child.wait(timeout=5)
                receipt["cleanup"]["fixture_reaped"] = True
            except Exception as exc:
                errors.append(f"fixture reap: {exc}")
        for stream in fixture_streams:
            stream.close()
        if runtime is not None:
            try:
                log = runtime.state_dir() / "launcher.log"
                if log.exists():
                    shutil.copyfile(log, out / "hermes-cua-desktop.log")
                runtime.stop()
                require(runtime._launcher_pid() is None, "product desktop launcher survived stop")
                if desktop is not None:
                    require(not Path(desktop.socket).exists(), "product RFB socket survived stop")
                receipt["cleanup"]["desktop_stopped"] = True
            except Exception as exc:
                errors.append(f"product desktop stop: {exc}")
        if approval is not None:
            try:
                approval.clear_session(session_id)
            except Exception as exc:
                errors.append(f"approval session cleanup: {exc}")
        if context is not None:
            if interactive_token is not None:
                context.reset_hermes_interactive_context(interactive_token)
            if session_token is not None:
                context.reset_current_session_key(session_token)
        if owned_children:
            _, survivors = psutil.wait_procs(owned_children, timeout=6)
            survivors = [p for p in survivors if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]
            if survivors:
                errors.append(f"product cleanup left owned children: {[p.pid for p in survivors]}")
                # These exact process identities were observed as our descendants;
                # never signal a global driver, X server, or another profile.
                for process in survivors:
                    try:
                        process.kill()
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.Error as exc:
                        errors.append(f"owned child {process.pid} cleanup: {exc}")
                psutil.wait_procs(survivors, timeout=3)
        logger.removeHandler(transport_log)
        receipt["transport_fallbacks"] = transport_log.fallbacks
        receipt["cleanup"]["errors"] = errors
        shutil.rmtree(work)
        receipt["cleanup"]["private_workspace_removed"] = not work.exists()
        require(not errors, "cleanup failed: " + "; ".join(errors))
    require(completed, "probe did not complete all native operations")
    receipt["checks"].append("product-session-desktop-and-owned-child-cleanup")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "driver", "driver-sha256", "fixture", "out", "candidate-receipt"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / "hermes-cua-result.json"
    require(not result_path.exists(), "use a new evidence directory; do not overwrite a previous probe result")
    receipt: dict[str, Any] = {
        "schema_version": 1, "status": "running", "scope": "private native Termux X11 through real Hermes computer_use",
        "android_phone_ui_tested": False, "at_spi_content_tested": False, "history_preview_tested": False,
        "physical_device_tested": False, "model_calls_requested": False, "checks": [], "calls": [], "approvals": [], "cleanup": {},
    }
    start = time.monotonic()
    try:
        run_probe(args, receipt)
        receipt["status"] = "passed"
    except Exception as exc:
        receipt.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        traceback.print_exc()
    finally:
        receipt["elapsed_seconds"] = round(time.monotonic() - start, 3)
        result_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "result": str(result_path)}), flush=True)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
