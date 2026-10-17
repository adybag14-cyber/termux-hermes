#!/usr/bin/env bash
# Unpublished CUA source-port experiment against one owned virtual X11 fixture.
set -Eeuo pipefail

mode=host
if [[ $# -gt 0 && "$1" == --in-container ]]; then mode=container; shift; fi
SOURCE= OUT= CANDIDATE_DIR=
while (($#)); do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --candidate-dir) CANDIDATE_DIR="$2"; shift 2 ;;
    *) echo "usage: $0 [--in-container] --source SOURCE --out OUT [--candidate-dir VERIFIED_CANDIDATE]" >&2; exit 2 ;;
  esac
done
[[ -n "$SOURCE" && -n "$OUT" ]] || exit 2

if [[ "$mode" == host ]]; then
  case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM64 host required" >&2; exit 2 ;; esac
  packaging="$(cd "$(dirname "$0")/.." && pwd)"
  SOURCE="$(realpath "$SOURCE")"
  mkdir -p "$OUT" "$packaging/.cua-native-cache"
  OUT="$(realpath "$OUT")"
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 "$packaging/scripts/prepare_cua_termux_source.py" \
    --source "$SOURCE" --patch "$packaging/patches/next-stable/cua-driver.patch" \
    --out "$OUT" --verify-prepared
  if [[ -n "$CANDIDATE_DIR" ]]; then
    CANDIDATE_DIR="$(realpath "$CANDIDATE_DIR")"
    python3 "$packaging/scripts/prepare_cua_assembly_source.py" --out "$OUT/assembly-source"
  fi
  python3 - "$packaging" "$OUT" "$image" "$CANDIDATE_DIR" <<'PY'
import hashlib, json, os, pathlib, runpy, shutil, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
paths = ("scripts/compatibility_probe_cua.sh", "scripts/prepare_cua_termux_source.py",
         "patches/next-stable/cua-driver.patch", ".github/workflows/cua-termux-probe.yml",
         "scripts/compatibility_probe_cua_hermes.py", "scripts/fetch_compatibility_candidate.py",
         "patches/next-stable/cua-hermes-integration.patch",
         "scripts/prepare_cua_assembly_source.py", "scripts/prepare_cua_hermes_candidate.py",
         "scripts/run_cua_packaged_probe.py")
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
advertised = os.environ.get("CUA_PROBE_HEAD_SHA", head)
if advertised != head:
    raise SystemExit("advertised probe head does not match the actual packaging checkout")
receipt = {
    "schema_version": 1, "purpose": "unpublished isolated native CUA virtual-X11 experiment",
    "run_id": os.environ.get("GITHUB_RUN_ID"), "head_sha": head,
    "workflow_sha": os.environ.get("GITHUB_SHA"), "builder_image": sys.argv[3],
    "native_architecture": "aarch64",
    "inputs": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    "hermes_pm_cua_admission_changed": bool(sys.argv[4]), "release_output": False,
    "main_candidate_modified": False, "prepared_cua_candidate_requested": bool(sys.argv[4]),
    "hermes_integration_requested": bool(sys.argv[4]),
}
if sys.argv[4]:
    candidate = pathlib.Path(sys.argv[4])
    api = runpy.run_path(str(root / "scripts/compatibility_probe_cua_hermes.py"))
    verified = api["read_candidate_receipt"](candidate / "candidate-receipt.json")
    package = candidate / verified["package"]["file"]
    if package.stat().st_size != verified["package"]["bytes"] or api["digest"](package) != verified["package"]["sha256"]:
        raise SystemExit("mounted candidate package differs from the verified receipt")
    evidence = out / "hermes-candidate"
    evidence.mkdir()
    for name in ("candidate-receipt.json", "CANDIDATE-IDENTITY.json", "venv-selection.json"):
        shutil.copyfile(candidate / name, evidence / name)
    assembly = out / "assembly-source/SOURCE.json"
    receipt["canonical_assembly_source"] = {
        "receipt_sha256": api["digest"](assembly), "source": json.loads(assembly.read_text()),
    }
    receipt["hermes_candidate"] = {
        "receipt_sha256": api["digest"](candidate / "candidate-receipt.json"),
        "run_id": verified["run_id"], "head_sha": verified["head_sha"],
        "artifact": verified["artifact"], "package": verified["package"],
    }
(out / "CUA-PROBE-INPUTS.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY
  chmod 0777 "$OUT" "$packaging/.cua-native-cache"
  # Actions restores files as the runner UID; only this task-owned cache is changed.
  sudo chown -hR 1000:1000 -- "$packaging/.cua-native-cache"
  # Checkout can create runner-private promisor metadata. This isolated public
  # component checkout must remain verifiable after the UID1000 container copy.
  [[ -d "$SOURCE/.git" ]]
  find "$SOURCE/.git" -type f -exec chmod a+r {} +
  find "$SOURCE/.git" -type d -exec chmod a+rx {} +
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  candidate_mount=() candidate_args=()
  if [[ -n "$CANDIDATE_DIR" ]]; then
    candidate_mount=(-v "$CANDIDATE_DIR:/candidate:ro" -v "$OUT/assembly-source:/assembly-source:ro")
    candidate_args=(--candidate-dir /candidate)
  fi
  docker run --rm --platform linux/arm64 --user 1000:1000 \
    --tmpfs /bin:mode=1777 \
    -v "$SOURCE:/source:ro" -v "$packaging:/probes:ro" -v "$OUT:/out" \
    -v "$packaging/.cua-native-cache:/cache" "${candidate_mount[@]}" \
    "$image" bash /probes/scripts/compatibility_probe_cua.sh \
      --in-container --source /source --out /out "${candidate_args[@]}" \
    2>&1 | tee "$OUT/cua-native-probe.log"
  exit 0
fi

[[ "$(id -u)" == 1000 ]] || { echo "Termux probe must run as UID 1000" >&2; exit 2; }
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR="$PREFIX/tmp"
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
unset LD_LIBRARY_PATH LD_PRELOAD PYTHONPATH PYTHONHOME
mkdir -p "$TMPDIR" "$OUT"
work="$(mktemp -d "$TMPDIR/cua-probe.XXXXXX")"
stage=setup
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$OUT/CUA-EXIT.json"
  find "$OUT" /cache -xdev -uid "$(id -u)" -type f -exec chmod a+r {} + 2>/dev/null || true
  find "$OUT" /cache -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} + 2>/dev/null || true
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT
umask 077
printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=5 update
apt-get -y -o Dpkg::Options::=--force-confnew dist-upgrade
apt-get -y --no-remove install x11-repo
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=5 update
desktop_packages=()
if [[ -n "$CANDIDATE_DIR" ]]; then
  # Complete product Bot Desktop dependencies, before native cache identity is read.
  desktop_packages=(xfce4-panel xfdesktop xfce4-settings xfce4-terminal xorg-xsetroot scrot)
fi
apt-get -y --no-remove install rust clang make pkg-config git python binutils \
  libx11 libxi libxtst tigervnc xfwm4 dbus xorg-xauth xorg-xdpyinfo xorg-xprop \
  xorg-setxkbmap ttf-dejavu "${desktop_packages[@]}"
[[ -e /bin/sh ]] || ln -s "$PREFIX/bin/sh" /bin/sh
dpkg-query -W -f='${Package}\t${Version}\n' > "$OUT/CUA-PACKAGES.tsv"
rustc -vV > "$OUT/CUA-RUSTC.txt"
clang --version > "$OUT/CUA-CLANG.txt"

cp -a "$SOURCE" "$work/source"
python /probes/scripts/prepare_cua_termux_source.py \
  --source "$work/source" --patch /probes/patches/next-stable/cua-driver.patch \
  --out "$OUT" --verify-prepared
# Cache namespaces bind the real installed Rust compiler, target, lock and reviewed
# inputs. Cargo still validates all source fingerprints and locked registry hashes.
cache_key="$(python - "$OUT" "$work/source" <<'PY'
import hashlib, pathlib, sys
out, source = map(pathlib.Path, sys.argv[1:])
h = hashlib.sha256(b"aarch64-linux-android\0")
receipt = __import__("json").loads((out / "CUA-SOURCE-RECEIPT.json").read_text())
for value in (receipt["source_commit"], receipt["source_patch_sha256"], receipt["preparer_sha256"]):
    h.update(value.encode())
for path in (out / "CUA-RUSTC.txt", out / "CUA-CLANG.txt", out / "CUA-PACKAGES.tsv",
             source / "libs/cua-driver/rust/Cargo.lock"):
    h.update(path.read_bytes())
print(h.hexdigest())
PY
)"
export CARGO_HOME="/cache/cargo"
export CARGO_TARGET_DIR="/cache/$cache_key/target"
mkdir -p "$CARGO_HOME" "$CARGO_TARGET_DIR"
printf '%s\n' "$cache_key" > "$OUT/CUA-CACHE-KEY.txt"
export CARGO_BUILD_JOBS=2 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false
export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="$PREFIX/bin/clang"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ANDROID_API_LEVEL=24 CONFIG_SHELL="$PREFIX/bin/sh"
stage=tty-abi
cat > "$work/cua-tty-abi.c" <<'C'
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Same Android request used by platform-linux/src/tty.rs. */
_Static_assert((unsigned int)TIOCGPTN == 0x80045430U, "Android TIOCGPTN ABI mismatch");
int main(void) {
    int master = posix_openpt(O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (master < 0 || grantpt(master) || unlockpt(master)) {
        perror("owned PTY setup");
        return 2;
    }
    unsigned int number = 0;
    char path[128], *end = NULL;
    if (ioctl(master, (int)0x80045430U, &number) ||
        ptsname_r(master, path, sizeof(path))) {
        perror("owned PTY number");
        return 3;
    }
    const char *base = strrchr(path, '/');
    if (!base) return 4;
    unsigned long expected = strtoul(base + 1, &end, 10);
    if (end == base + 1 || *end || expected != number) return 5;
    if (close(master)) return 6;
    int ordinary = open("/dev/null", O_RDONLY | O_CLOEXEC);
    if (ordinary < 0) return 7;
    errno = 0;
    int result = ioctl(ordinary, (int)0x80045430U, &number);
    int saved_errno = errno;
    if (close(ordinary) || result != -1 || saved_errno != ENOTTY) return 8;
    puts("{\"request_u32\":2147767344,\"pty_number_agrees_with_ptsname_r\":true,"
         "\"non_master_rejected\":true}");
    return 0;
}
C
clang "$work/cua-tty-abi.c" -o "$work/cua-tty-abi"
"$work/cua-tty-abi" > "$OUT/CUA-TTY-ABI.json"

stage=memfd-abi
cat > "$work/cua-memfd-abi.c" <<'C'
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/memfd.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

static int fail(const char *what, int code, int fd, void *map) {
    int saved_errno = errno;
    if (map != MAP_FAILED) munmap(map, 4096);
    if (fd >= 0) close(fd);
    errno = saved_errno;
    perror(what);
    return code;
}

int main(void) {
    int fd = (int)syscall(SYS_memfd_create, "cua-probe-shm", MFD_CLOEXEC);
    void *map = MAP_FAILED;
    if (fd < 0) return fail("memfd syscall", 2, fd, map);
    int flags = fcntl(fd, F_GETFD);
    if (flags < 0 || !(flags & FD_CLOEXEC))
        return fail("memfd close-on-exec", 3, fd, map);
    if (ftruncate(fd, 4096)) return fail("memfd size", 4, fd, map);
    map = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) return fail("memfd mapping", 5, fd, map);
    const char first[] = "cua-memfd-mapping";
    char observed[sizeof(first)];
    memcpy(map, first, sizeof(first));
    if (pread(fd, observed, sizeof(observed), 0) != sizeof(observed) ||
        memcmp(first, observed, sizeof(first)))
        return fail("shared mapping to fd", 6, fd, map);
    const char second[] = "cua-memfd-fd";
    if (pwrite(fd, second, sizeof(second), 0) != sizeof(second) ||
        memcmp(second, map, sizeof(second)))
        return fail("fd to shared mapping", 7, fd, map);
    if (munmap(map, 4096)) return fail("memfd unmap", 8, fd, map);
    map = MAP_FAILED;
    int closed_fd = fd;
    if (close(fd)) return fail("memfd close", 9, -1, map);
    fd = -1;
    errno = 0;
    if (fcntl(closed_fd, F_GETFD) != -1 || errno != EBADF)
        return fail("closed memfd", 10, fd, map);

    fd = (int)syscall(SYS_memfd_create, "cua-probe-keymap", MFD_CLOEXEC);
    if (fd < 0) return fail("keymap memfd", 11, fd, map);
    flags = fcntl(fd, F_GETFD);
    if (flags < 0 || !(flags & FD_CLOEXEC))
        return fail("keymap close-on-exec", 12, fd, map);
    const char keymap[] = "cua-probe-keymap";
    char readback[sizeof(keymap)];
    if (write(fd, keymap, sizeof(keymap) - 1) != sizeof(keymap) - 1 ||
        write(fd, "", 1) != 1 || lseek(fd, 0, SEEK_SET) != 0 ||
        read(fd, readback, sizeof(readback)) != sizeof(readback) ||
        memcmp(keymap, readback, sizeof(keymap)))
        return fail("keymap write terminator seek read", 13, fd, map);
    closed_fd = fd;
    if (close(fd)) return fail("keymap close", 14, -1, map);
    fd = -1;
    errno = 0;
    if (fcntl(closed_fd, F_GETFD) != -1 || errno != EBADF)
        return fail("closed keymap", 15, fd, map);

    errno = 0;
    long invalid_fd = syscall(SYS_memfd_create, "cua-probe-invalid", UINT_MAX);
    int error = errno;
    if (invalid_fd != -1 || error != EINVAL) {
        if (invalid_fd >= 0) close((int)invalid_fd);
        errno = error;
        return fail("invalid memfd flags must preserve EINVAL", 16, -1, map);
    }
    printf("{\"syscall_number\":%ld,\"close_on_exec\":true,"
           "\"shared_mapping_fd_roundtrip\":true,"
           "\"keymap_write_nul_seek_read\":true,\"owned_fds_closed\":true,"
           "\"invalid_flags_return_minus_one_einval\":true}\n",
           (long)SYS_memfd_create);
    return 0;
}
C
clang "$work/cua-memfd-abi.c" -o "$work/cua-memfd-abi"
"$work/cua-memfd-abi" > "$OUT/CUA-MEMFD-ABI.json"

stage=compile
cargo build --locked --no-default-features -p cua-driver \
  --manifest-path "$work/source/libs/cua-driver/rust/Cargo.toml" \
  --target aarch64-linux-android 2>&1 | tee "$OUT/cua-cargo-build.log"
mkdir -p "$OUT/bin"
cp "$CARGO_TARGET_DIR/aarch64-linux-android/debug/cua-driver" "$OUT/bin/cua-driver"
chmod 0755 "$OUT/bin/cua-driver"
readelf -h -l -d "$OUT/bin/cua-driver" > "$OUT/CUA-ELF.txt"
readelf --version-info "$OUT/bin/cua-driver" > "$OUT/CUA-ELF-VERSIONS.txt"

cat > "$work/cua-fixture.c" <<'C'
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    Display *d = XOpenDisplay(NULL);
    if (!d) return 2;
    int screen = DefaultScreen(d);
    Window root = RootWindow(d, screen);
    Window w = XCreateSimpleWindow(d, root, 120, 100, 320, 240, 0, 0, 0x224466);
    XStoreName(d, w, "Owned Termux CUA fixture");
    Atom utf8 = XInternAtom(d, "UTF8_STRING", False);
    const char title[] = "Owned Termux CUA fixture";
    XChangeProperty(d, w, XInternAtom(d, "_NET_WM_NAME", False), utf8, 8,
                    PropModeReplace, (const unsigned char *)title, sizeof(title) - 1);
    XClassHint hint = {"termux-cua-fixture", "TermuxCuaFixture"};
    XSetClassHint(d, w, &hint);
    unsigned long pid = (unsigned long)getpid();
    XChangeProperty(d, w, XInternAtom(d, "_NET_WM_PID", False),
                    XInternAtom(d, "CARDINAL", False), 32, PropModeReplace,
                    (const unsigned char *)&pid, 1);
    XSelectInput(d, w, ExposureMask | KeyPressMask | ButtonPressMask | StructureNotifyMask);
    GC gc = XCreateGC(d, w, 0, NULL);
    XMapWindow(d, w);
    XFlush(d);
    setvbuf(stdout, NULL, _IOLBF, 0);
    printf("{\"event\":\"ready\",\"pid\":%lu,\"window_id\":%lu}\n", pid, w);
    for (;;) {
        XEvent e;
        XNextEvent(d, &e);
        if (e.type == Expose && e.xexpose.count == 0) {
            XWindowAttributes a;
            XGetWindowAttributes(d, w, &a);
            XSetForeground(d, gc, 0x224466);
            XFillRectangle(d, w, gc, 0, 0, a.width / 2, a.height);
            XSetForeground(d, gc, 0x55cc88);
            XFillRectangle(d, w, gc, a.width / 2, 0, a.width - a.width / 2, a.height);
            XSync(d, False);
            printf("{\"event\":\"paint\",\"width\":%d,\"height\":%d}\n", a.width, a.height);
        } else if (e.type == ConfigureNotify) {
            XWindowAttributes a;
            int x, y;
            Window child;
            XGetWindowAttributes(d, w, &a);
            XTranslateCoordinates(d, w, root, 0, 0, &x, &y, &child);
            printf("{\"event\":\"geometry\",\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}\n",
                   x, y, a.width, a.height);
        } else if (e.type == KeyPress) {
            char chars[64];
            KeySym key;
            int count = XLookupString(&e.xkey, chars, sizeof(chars), &key, NULL);
            printf("{\"event\":\"key\",\"hex\":\"");
            for (int i = 0; i < count; ++i) printf("%02x", (unsigned char)chars[i]);
            puts("\"}");
        } else if (e.type == ButtonPress) {
            printf("{\"event\":\"button\",\"button\":%u,\"x\":%d,\"y\":%d}\n",
                   e.xbutton.button, e.xbutton.x, e.xbutton.y);
        }
    }
}
C
clang -O0 "$work/cua-fixture.c" -o "$work/cua-fixture" \
  -I"$PREFIX/include" -L"$PREFIX/lib" -lX11

stage=behavior
python - "$OUT" "$work" <<'PY'
import collections, hashlib, json, os, pathlib, selectors, signal, stat
import struct, subprocess, sys, time, zlib

out, work = map(pathlib.Path, sys.argv[1:])
assert sys.platform == "android" and os.getuid() == 1000, (sys.platform, os.getuid())
binary = out / "bin/cua-driver"
elf = binary.read_bytes()
assert elf[:5] == b"\x7fELF\x02" and struct.unpack_from("<H", elf, 18)[0] == 183
assert "Name: GLIBC_" not in (out / "CUA-ELF-VERSIONS.txt").read_text()
prefix = pathlib.Path(os.environ["PREFIX"])
env = dict(os.environ)
for key, relative in (("XDG_RUNTIME_DIR", "runtime"), ("XDG_CACHE_HOME", "cache"),
                      ("XDG_STATE_HOME", "state"), ("XDG_CONFIG_HOME", "config")):
    path = work / relative
    path.mkdir(mode=0o700)
    env[key] = str(path)
env["XDG_DATA_DIRS"] = str(prefix / "share")
env["XAUTHORITY"] = str(work / "Xauthority")
env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(work / "bus")
env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
env["CUA_LOG"] = "warn"
for key in ("WAYLAND_DISPLAY", "CUA_DRIVER_PERMISSION_MODE",
            "CUA_DRIVER_CAPABILITY_MANIFEST_FILE"):
    env.pop(key, None)
display = next(n for n in range(90, 121)
               if not (prefix / f"tmp/.X11-unix/X{n}").exists())
env["DISPLAY"] = f":{display}"
authority = work / "Xauthority"
authority.touch(mode=0o600)
subprocess.run(["xauth", "-f", str(authority), "add", env["DISPLAY"],
                "MIT-MAGIC-COOKIE-1", os.urandom(16).hex()],
               env=env, check=True, timeout=10)
children, handles, transcript = [], [], []
receipt = {
    "schema_version": 1, "scope": "owned Termux Xvnc/Xfwm4/Xlib virtual desktop",
    "platform": sys.platform, "uid": os.getuid(),
    "binary_sha256": hashlib.sha256(elf).hexdigest(),
    "authorization_mode": "standard", "phone_ui_certified": False,
    "history_admitted": False, "parallel_uinput_claimed": False,
    "background_input_certified": False,
    "accessibility_tree_certified": False, "hermes_pm_cua_admission_changed": False,
    "checks": ["native-aarch64-bionic-elf"], "status": "started",
}

def spawn(name, args, pipe=False):
    log = (out / f"cua-{name}.log").open("wb")
    handles.append(log)
    child = subprocess.Popen(
        args, env=env, stdin=subprocess.PIPE if pipe else subprocess.DEVNULL,
        stdout=subprocess.PIPE if pipe else log, stderr=log, start_new_session=True)
    children.append((name, child))
    return child

def until(check, label, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("timed out: " + label)

def events():
    path = out / "cua-fixture.log"
    result = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # The fixture can be midway through one line.
    return result

def listening_inet(pid):
    sockets = set()
    for fd in pathlib.Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        if target.startswith("socket:["):
            sockets.add(target[8:-1])
    matches = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in pathlib.Path(table).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A" and fields[9] in sockets:
                matches.append({"table": table, "address": fields[1]})
    return matches

def png_colors(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed, dimensions = 8, bytearray(), None
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        assert zlib.crc32(kind + body) & 0xffffffff == expected_crc
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            assert 0 < width <= 800 and 0 < height <= 600
            assert depth == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0)
            dimensions = width, height, 3 if color == 2 else 4
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            break
        offset += 12 + length
    assert dimensions is not None
    width, height, channels = dimensions
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    assert len(raw) == height * (stride + 1)
    previous = bytearray(stride)
    counts = collections.Counter()
    for row_index in range(height):
        start = row_index * (stride + 1)
        filtering = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        assert filtering in range(5)
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            above = previous[i]
            upper_left = previous[i - channels] if i >= channels else 0
            if filtering == 1:
                predictor = left
            elif filtering == 2:
                predictor = above
            elif filtering == 3:
                predictor = (left + above) // 2
            elif filtering == 4:
                p = left + above - upper_left
                pa, pb, pc = abs(p - left), abs(p - above), abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else above if pb <= pc else upper_left
            else:
                predictor = 0
            row[i] = (row[i] + predictor) & 255
        counts.update(tuple(row[i:i + 3]) for i in range(0, stride, channels))
        previous = row
    for rgb in ((0x22, 0x44, 0x66), (0x55, 0xcc, 0x88)):
        assert counts[rgb] > width * height // 5, (rgb, counts[rgb], width, height)
    return width, height

class Rpc:
    def __init__(self, process):
        self.process, self.pending, self.counter = process, b"", 0
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ)

    def request(self, method, params):
        self.counter += 1
        request = {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params}
        self.process.stdin.write(json.dumps(request).encode() + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if not line.strip():
                    continue
                response = json.loads(line)
                if response.get("id") != self.counter:
                    continue
                transcript.append({"request": request, "response": response})
                assert "error" not in response, response
                return response["result"]
            if self.selector.select(max(0, deadline - time.monotonic())):
                chunk = os.read(self.process.stdout.fileno(), 65536)
                assert chunk, "CUA stdio closed before its JSON-RPC response"
                self.pending += chunk
                assert len(self.pending) <= 16 * 1024 * 1024
        raise AssertionError("CUA RPC timed out: " + method)

    def call(self, name, **arguments):
        result = self.request("tools/call", {
            "name": name, "arguments": {"session": "termux-fixture", **arguments}})
        assert not result.get("isError", False), result
        return result

rpc = None
failure = None
try:
    bus_config = work / "dbus.conf"
    # Match the ordinary session-bus send/receive policy from D-Bus 1.16.2
    # bus/session.conf.in; authentication and the private socket stay local.
    bus_config.write_text(
        '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" '
        '"http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">\n'
        '<busconfig><type>session</type><listen>' + env["DBUS_SESSION_BUS_ADDRESS"] +
        '</listen><auth>EXTERNAL</auth><policy context="default">'
        '<allow send_destination="*" eavesdrop="true"/>'
        '<allow eavesdrop="true"/><allow own="*"/>'
        '</policy></busconfig>')
    spawn("dbus", ["dbus-daemon", "--nofork", "--nopidfile", "--config-file=" + str(bus_config)])
    until(lambda: (work / "bus").exists(), "private D-Bus socket")
    bus_reply = subprocess.run(
        ["dbus-send", "--session", "--type=method_call", "--print-reply",
         "--reply-timeout=3000", "--dest=org.freedesktop.DBus",
         "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
        env=env, capture_output=True, text=True, timeout=5)
    (out / "CUA-DBUS-ROUNDTRIP.json").write_text(json.dumps({
        "returncode": bus_reply.returncode, "stdout": bus_reply.stdout,
        "stderr": bus_reply.stderr}, indent=2) + "\n")
    assert bus_reply.returncode == 0 and "org.freedesktop.DBus" in bus_reply.stdout, (
        "private session-bus reply failed", bus_reply.returncode, bus_reply.stderr)
    receipt["checks"].append("private-session-bus-method-roundtrip")
    xvnc = spawn("xvnc", ["Xvnc", env["DISPLAY"], "-geometry", "800x600", "-depth", "24",
                         "-SecurityTypes", "None", "-rfbport", "-1",
                         "-rfbunixpath", str(work / "rfb.sock"), "-rfbunixmode", "0600",
                         "-nolisten", "tcp", "-auth", str(authority)])
    def display_ready():
        return subprocess.run(["xdpyinfo"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=5).returncode == 0
    until(display_ready, "private X11 display")
    assert not listening_inet(xvnc.pid), "owned Xvnc unexpectedly listens on an Internet socket"
    assert stat.S_IMODE((work / "rfb.sock").stat().st_mode) == 0o600
    assert stat.S_IMODE(authority.stat().st_mode) == 0o600
    receipt["checks"].append("private-authenticated-x11-unix-only")
    spawn("xfwm4", ["xfwm4", "--compositor=off", "--sm-client-disable"])
    def wm_ready():
        result = subprocess.run(["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"],
                                env=env, capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and "window id #" in result.stdout
    until(wm_ready, "owned Xfwm4 manager")
    fixture = spawn("fixture", [str(work / "cua-fixture")])
    ready = until(lambda: next((e for e in events() if e.get("event") == "ready"), None),
                  "fixture window")
    assert ready["pid"] == fixture.pid
    until(lambda: any(e.get("event") == "paint" for e in events()), "fixture colors")
    target = {"pid": fixture.pid, "window_id": ready["window_id"]}
    receipt["fixture"] = target
    driver = spawn("driver", [str(binary), "mcp", "--direct", "--no-overlay"], pipe=True)
    rpc = Rpc(driver)
    rpc.request("initialize", {})
    tools = rpc.request("tools/list", {})
    names = sorted(t["name"] for t in tools["tools"])
    required = {"get_window_state", "click", "type_text", "clipboard_write",
                "clipboard_read", "set_window_frame", "scroll"}
    assert required <= set(names), sorted(required - set(names))
    (out / "CUA-TOOL-NAMES.json").write_text(json.dumps(names, indent=2) + "\n")
    receipt["tool_count"] = len(names)
    receipt["checks"].append("real-linux-tool-registry")
    screenshot = out / "cua-fixture.png"
    rpc.call("get_window_state", **target, include_screenshot=True,
             screenshot_out_file=str(screenshot), max_elements=20, max_depth=4)
    width, height = png_colors(screenshot)
    receipt["screenshot"] = {"width": width, "height": height,
                             "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()}
    receipt["checks"].append("screenshot-png-independent-two-color-oracle")
    # The owned visible fixture uses the documented foreground XTest route.
    # Background non-delivery: audit/cua-native-20261017/run-39051490364.json.
    rpc.call("click", **target, x=80, y=60, button="left", delivery_mode="foreground")
    until(lambda: any(e.get("event") == "button" and e["button"] == 1 and
                      e["x"] == 80 and e["y"] == 60 for e in events()),
          "real fixture button event at requested client coordinates")
    receipt["checks"].append("click-observed-by-xlib-fixture")
    before_scroll = len(events())
    rpc.call("scroll", **target, x=80, y=60, direction="down", by="line",
             amount=2, delivery_mode="foreground")
    def scroll_events():
        return [e for e in events()[before_scroll:] if e.get("event") == "button"]
    until(lambda: len(scroll_events()) >= 2, "real XTEST scroll detents")
    time.sleep(0.2)
    observed_scroll = scroll_events()
    assert len(observed_scroll) == 2 and all(
        e["button"] == 5 and e["x"] == 80 and e["y"] == 60 for e in observed_scroll
    ), observed_scroll
    receipt["checks"].append("scroll-two-exact-xlib-wheel-events")
    typed = "termux-cua-input"
    rpc.call("type_text", **target, text=typed, delivery_mode="foreground")
    def received_text():
        return b"".join(bytes.fromhex(e["hex"]) for e in events()
                        if e.get("event") == "key").decode("ascii") == typed
    until(received_text, "real XTEST text received by fixture")
    receipt["checks"].append("foreground-text-exact-keypress-oracle")
    clipboard = "termux-cua-clipboard"
    rpc.call("clipboard_write", text=clipboard)
    clip = rpc.call("clipboard_read", include_text=True)["structuredContent"]
    assert clip["supported"] is True and clip["text"] == clipboard, clip
    receipt["checks"].append("clipboard-exact-roundtrip")
    requested = {"x": 40, "y": 60, "width": 400, "height": 200}
    rpc.call("set_window_frame", **target, **requested)
    until(lambda: any(e.get("event") == "geometry" and
                      all(e[k] == v for k, v in requested.items()) for e in events()),
          "independent client-root geometry")
    receipt["checks"].append("window-frame-independent-xlib-readback")
    receipt["status"] = "passed"
except BaseException as exc:
    failure = exc
    receipt["status"], receipt["error"] = "failed", repr(exc)
finally:
    cleanup, cleanup_errors = [], []
    if rpc is not None:
        rpc.selector.close()
        try:
            rpc.process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    for name, child in reversed(children):
        try:
            if child.poll() is None:
                if os.getpgid(child.pid) != child.pid:
                    raise AssertionError("owned child changed its process group")
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            cleanup.append({"name": name, "pid": child.pid, "returncode": child.returncode})
            if child.returncode is None:
                raise AssertionError("owned child remains alive")
        except BaseException as exc:
            cleanup_errors.append({"name": name, "error": repr(exc)})
    for handle in handles:
        handle.close()
    receipt["cleanup"] = cleanup
    receipt["cleanup_errors"] = cleanup_errors
    if cleanup_errors:
        receipt["status"] = "failed"
    else:
        receipt["checks"].append("all-owned-child-processes-reaped")
    (out / "CUA-BEHAVIOR.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (out / "cua-mcp-transcript.json").write_text(json.dumps(transcript, indent=2) + "\n")
if failure is not None:
    raise failure
assert receipt["status"] == "passed", receipt
(out / "cua-probe-passed.txt").write_text(
    "Native Bionic CUA virtual-X11 registry, screenshot, click, scroll, text, clipboard, geometry and cleanup passed.\n"
    "This does not certify phone UI, AT-SPI trees, parallel/uinput or encrypted history.\n")
PY
if [[ -n "$CANDIDATE_DIR" ]]; then
  stage=hermes-packaged-default
  python -B /probes/scripts/run_cua_packaged_probe.py /probes "$OUT" "$work" "$CANDIDATE_DIR"
fi
stage=completed
