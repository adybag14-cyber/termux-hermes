#!/usr/bin/env bash
# Candidate-only native Termux virtual desktop proof. No Android phone UI or release operations.
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
mkdir -p "$OUT" "$PREFIX/etc/apt/sources.list.d"
work="$(mktemp -d "$PREFIX/tmp/hd.XXXXXX")"
cleanup() {
  chmod -R a+rX "$OUT" 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export HERMES_HOME="$work/profile" HERMES_RUNTIME_DIR="$HERMES_PROBE_PAYLOAD/tools"
export PYTHONPATH="$SOURCE" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$work"
mkdir -p "$HERMES_HOME"
cat > "$HERMES_HOME/config.yaml" <<'YAML'
terminal:
  backend: local
bot_desktop:
  placement: gateway
  geometry: "800x600"
YAML
"$HERMES_PROBE_PAYLOAD/venv/bin/python" -B - "$OUT" <<'PY'
from pathlib import Path
import base64
import io
import json
import os
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time

from PIL import Image
from plugins.computer_use.cua import CuaDriverProvider
from tools.bot_desktop import install, runtime, termux, thumbnail

out = Path(sys.argv[1])
assert sys.platform == "android" and termux.is_termux()
assert os.geteuid() == 1000, "desktop APT proof must run as the Termux app user (UID1000)"
assert runtime.is_supported_host()
assert runtime.package_manager() == "termux"
assert runtime.installable()
assert not CuaDriverProvider().is_available(), "a virtual X11 desktop must not advertise an Android phone driver"
(out / "desktop-install-command.txt").write_text(runtime.install_command() + "\n")


def no_password():
    raise AssertionError("Termux APT must run as the app user, without asking for sudo")


assert install.install_packages(ask_password=no_password, on_line=lambda line: print(line, flush=True)) == 0
assert not runtime.missing_binaries(), runtime.missing_binaries()
packages = subprocess.run(
    ["dpkg-query", "-W", "-f=${Package} ${Version}\n", *termux.PACKAGES],
    check=True, capture_output=True, text=True, env=termux.system_env(os.environ),
)
(out / "desktop-packages.txt").write_text(packages.stdout)


def exact(sock, size):
    chunks = []
    while size:
        part = sock.recv(size)
        if not part:
            raise RuntimeError("RFB server closed before the frame was complete")
        chunks.append(part)
        size -= len(part)
    return b"".join(chunks)


def rfb_frame(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(15)
        stream.connect(str(path))
        version = exact(stream, 12)
        assert version == b"RFB 003.008\n", version
        stream.sendall(version)
        offered = exact(stream, exact(stream, 1)[0])
        assert 1 in offered, offered
        stream.sendall(b"\x01")
        assert exact(stream, 4) == b"\x00\x00\x00\x00"
        stream.sendall(b"\x01")  # shared viewer; do not eject a human client
        header = exact(stream, 24)
        width, height = struct.unpack("!HH", header[:4])
        name_len = struct.unpack("!I", header[20:])[0]
        assert 0 < width <= 3840 and 0 < height <= 2160 and name_len <= 65536
        name = exact(stream, name_len).decode("utf-8", "replace")
        pixel_format = struct.pack("!BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        stream.sendall(b"\x00\x00\x00\x00" + pixel_format)
        stream.sendall(struct.pack("!BBHi", 2, 0, 1, 0))  # SetEncodings: raw
        stream.sendall(struct.pack("!BBHHHH", 3, 0, 0, 0, width, height))
        assert exact(stream, 1) == b"\x00", "expected a framebuffer update"
        count = struct.unpack("!xH", exact(stream, 3))[0]
        assert 0 < count <= 256
        image = Image.new("RGB", (width, height))
        pixels = 0
        for _ in range(count):
            x, y, w, h, encoding = struct.unpack("!HHHHi", exact(stream, 12))
            assert encoding == 0 and x + w <= width and y + h <= height
            raw = exact(stream, w * h * 4)
            image.paste(Image.frombytes("RGB", (w, h), raw, "raw", "BGRX"), (x, y))
            pixels += w * h
        assert pixels == width * height, (pixels, width, height)
        return image, {"version": version.decode().strip(), "name": name, "width": width, "height": height,
                       "raw_pixels": pixels, "security_type": 1}


def listening_inet(pid):
    inodes = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            link = os.readlink(fd)
        except FileNotFoundError:
            continue
        if link.startswith("socket:["):
            inodes.add(link[8:-1])
    listeners = []
    for name in ("tcp", "tcp6"):
        for line in Path(f"/proc/net/{name}").read_text().splitlines()[1:]:
            columns = line.split()
            if len(columns) >= 10 and columns[3] == "0A" and columns[9] in inodes:
                listeners.append({"table": name, "local": columns[1], "inode": columns[9]})
    return listeners


started = None
try:
    started = runtime.start(wait_seconds=45)
    assert started.running and started.installed and started.supported, started.as_dict()
    (out / "desktop-start-status.json").write_text(json.dumps(started.as_dict(), indent=2) + "\n")
    published = runtime.published_env()
    native_env = termux.system_env({**os.environ, **published})
    deadline = time.monotonic() + 25
    while True:
        wm = subprocess.run(
            ["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"], env=native_env,
            check=False, capture_output=True, text=True, timeout=5,
        )
        if "window id #" in wm.stdout:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("Xfce window manager did not claim the desktop: " + wm.stdout + wm.stderr)
        time.sleep(0.2)
    (out / "desktop-window-manager.txt").write_text(wm.stdout)
    socket_path = runtime.rfb_socket_path()
    assert socket_path is not None and stat.S_ISSOCK(socket_path.stat().st_mode)
    assert stat.S_IMODE(socket_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(runtime.state_dir().stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(published["XAUTHORITY"]).stat().st_mode) == 0o600
    xvnc_pid = runtime._x_lock_pid(int(started.display.lstrip(":")))
    assert xvnc_pid is not None
    listeners = listening_inet(xvnc_pid)
    assert not listeners, listeners
    frame, rfb = rfb_frame(socket_path)
    frame.save(out / "desktop-rfb.png")
    preview = thumbnail.thumbnail_data_url()
    assert preview and preview.startswith("data:image/jpeg;base64,")
    jpeg = base64.b64decode(preview.split(",", 1)[1], validate=True)
    image = Image.open(io.BytesIO(jpeg))
    image.load()
    assert image.width > 0 and image.height > 0 and image.format == "JPEG"
    (out / "desktop-thumbnail.jpg").write_bytes(jpeg)
    evidence = {
        "platform": sys.platform, "uid": os.geteuid(), "rfb": rfb,
        "rfb_socket_mode": "0600", "profile_state_mode": "0700", "xauthority_mode": "0600",
        "xvnc_listening_inet": listeners, "thumbnail_dimensions": list(image.size),
        "native_android_phone_control": False,
        "scope": "Private Termux Xvnc/Xfce desktop; no physical Android UI, touch, microphone, or speaker test.",
    }
    (out / "desktop-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
finally:
    log = runtime.state_dir() / "launcher.log"
    if log.exists():
        shutil.copyfile(log, out / "desktop-launcher.log")
    runtime.stop()
    assert runtime._launcher_pid() is None, "the owned desktop launcher survived stop"
    if started is not None:
        assert not Path(started.socket).exists(), "the owned RFB socket survived stop"
(out / "desktop-probe-passed.txt").write_text(
    "Native Termux Xvnc/Xfce: install, start, private RFB framebuffer, X11 thumbnail, no TCP listener, and stop passed.\n"
)
PY
