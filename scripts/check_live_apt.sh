#!/usr/bin/env bash
# Run inside the pinned native Termux image after the release reaches signed APT.
# Usage: bash scripts/check_live_apt.sh PACKAGE_VERSION INSTALLER_COMMIT
set -Eeuo pipefail

expected_version="${1:?package version required}"
installer_commit="${2:?installer commit required}"
[[ "$installer_commit" =~ ^[a-f0-9]{40}$ ]] || {
  echo 'The public installer must be pinned to a full Git commit' >&2
  exit 2
}
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
test "$(dpkg --print-architecture)" = aarch64
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export TMPDIR="$PREFIX/tmp"
mkdir -p "$TMPDIR"
root="$PREFIX/lib/hermes-agent"
filename="hermes-agent_${expected_version}_aarch64.deb"

package_status() {
  dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null || true
}

validate_installed() {
  test "$(package_status hermes-agent)" = installed
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = "$expected_version"
  test -z "$(dpkg-query -W -f='${Depends}' hermes-agent)"
  grep -Fx apt "$root/app/.install_method"
  for name in hermes hermes-agent hermes-acp; do
    test -L "$PREFIX/bin/$name"
    test "$(readlink "$PREFIX/bin/$name")" = "../lib/hermes-agent/bin/$name"
    test -x "$PREFIX/bin/$name"
  done
  test -f "$root/pm-runtime/pm-runtime.json"
  hermes --version
  hermes chat --help >/dev/null
  hermes-acp --check
  if hermes update > "$TMPDIR/live-apt-update.txt" 2>&1; then
    echo 'APT-managed hermes update unexpectedly succeeded' >&2
    exit 1
  else
    update_status=$?
  fi
  test "$update_status" = 2
  grep -F 'pkg upgrade hermes-agent' "$TMPDIR/live-apt-update.txt"

  # Match the packaged launcher without changing the system Python environment.
  env LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib" \
    HERMES_RUNTIME_DIR="$root/tools" PYTHONPATH="$root/app" \
    "$root/venv/bin/python" -B - <<'PY'
import importlib
import sys
import pm
from hermes_cli.config import detect_install_method
from pm.features import read_features

assert sys.version_info[:2] == (3, 14), sys.version
assert detect_install_method() == "apt"
for module in (
    "ctypes", "ssl", "sqlite3", "bz2", "lzma", "zlib", "hashlib", "readline",
    "hermes_cli", "cli", "run_agent", "tui_gateway.server", "psutil",
    "_cffi_backend", "PIL._imaging", "_pillow_heif", "pydantic_core",
    "cryptography", "jiter", "rpds", "mcp", "httpx2", "snowballstemmer",
    "telegram", "croniter", "acp", "ruamel.yaml", "httptools", "watchfiles",
    "resvg_py",
):
    importlib.import_module(module)
assert read_features() == ["acp", "cron", "mcp", "telegram", "termux"]
issues = pm.check()
assert not issues, issues
print("Live signed APT Python 3.14, native imports, and Termux profile passed")
PY
  test -z "$(dpkg --audit)"
}

# Refresh the complete rolling base before current GPG or repository setup.
printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
apt-get -o Acquire::Retries=5 -o Dpkg::Options::="--force-confnew" dist-upgrade -y
setup_script="$TMPDIR/hermes-apt-setup.sh"
curl -fsSL --retry 5 --retry-all-errors \
  https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh \
  -o "$setup_script"
bash "$setup_script"
rm -f "$setup_script"

# This is the public signed repository path, not a directly installed artifact.
pkg install -y hermes-agent
validate_installed
test "$(package_status python)" != installed
echo LIVE_SIGNED_APT_INSTALL_OK

# Preserve real user configuration and a stale legacy checkout lock while
# reproducing the interrupted transaction that the public installer repairs.
hermes config set model.max_tokens 65536
printf 'RECOVERY_SENTINEL=preserve-me\n' > "$HOME/.hermes/.env"
env_before="$(sha256sum "$HOME/.hermes/.env")"
mkdir -p "$HOME/.hermes/hermes-agent/.git"
: > "$HOME/.hermes/hermes-agent/.git/index.lock"
pkg uninstall -y hermes-agent
test "$(package_status hermes-agent)" != installed

# New self-contained bundles install neither side-by-side Python package.
# Only remove a legacy dependency when it is actually present.
legacy_python_packages=()
for package in python3.13 python3.13-ensurepip-wheels; do
  if [[ "$(package_status "$package")" == installed ]]; then
    legacy_python_packages+=("$package")
  fi
done
if (( ${#legacy_python_packages[@]} )); then
  pkg uninstall -y "${legacy_python_packages[@]}"
fi
for package in python3.13 python3.13-ensurepip-wheels; do
  test "$(package_status "$package")" != installed
done

# The existing system Python owns pydoc3.13; the old +termux1 package is left
# unpacked with its conflicting side-by-side dependency unsatisfied.
python_deb="$TMPDIR/python_3.13.15_aarch64.deb"
curl -fsSL --retry 6 --retry-all-errors \
  https://github.com/adybag14-cyber/termux-python/releases/download/termux-aarch64-20260824.43.1/python_3.13.15_aarch64.deb \
  -o "$python_deb"
printf '%s  %s\n' \
  c3038f512f3d95b5c3d4803f3cdd06b43fc09dcb415b3900bd048ef508fbffc3 \
  "$python_deb" | sha256sum -c -
python_deps="$(dpkg-deb -f "$python_deb" Depends)"
if [[ -n "$python_deps" ]]; then
  apt-get -o Acquire::Retries=5 satisfy -y "$python_deps"
fi
dpkg --force-not-root --force-script-chrootless --install "$python_deb"
apt-mark hold python
test "$(package_status python)" = installed
test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'
python_before="$(sha256sum "$PREFIX/bin/python3.13")"
python_owner="$(dpkg-query -S "$PREFIX/bin/python3.13")"
python_version="$(dpkg-query -W -f='${Version}' python)"
pydoc_before="$(sha256sum "$PREFIX/bin/pydoc3.13")"
pydoc_owner="$(dpkg-query -S "$PREFIX/bin/pydoc3.13")"

old_hermes="$TMPDIR/hermes-agent_0.20.6+termux1_aarch64.deb"
curl -fsSL --retry 6 --retry-all-errors \
  https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.20.6-20260828.1/hermes-agent_0.20.6%2Btermux1_aarch64.deb \
  -o "$old_hermes"
printf '%s  %s\n' \
  8d54e0339b382c102b653486298bc8cf65abefa71cff38de8b43acf6e849a652 \
  "$old_hermes" | sha256sum -c -
dpkg --force-not-root --force-script-chrootless --unpack "$old_hermes"
test "$(package_status hermes-agent)" = unpacked

recovery_cache="${XDG_CACHE_HOME:-$HOME/.cache}/hermes-recovery"
recovery_partial="$recovery_cache/$filename.part"
apt_partial="$PREFIX/var/cache/apt/archives/partial/$filename"
mkdir -p "$(dirname "$apt_partial")"
range_headers="$TMPDIR/live-apt-range.headers"
range_status="$(curl -fsSL --retry 6 --retry-all-errors --range 0-1048575 \
  --dump-header "$range_headers" --write-out '%{http_code}' \
  "http://144.21.61.111/termux/pool/main/$filename" -o "$apt_partial")"
test "$range_status" = 206
tr -d '\r' < "$range_headers" | grep -Ei '^Content-Range: bytes 0-1048575/[0-9]+$'
test "$(wc -c < "$apt_partial")" = 1048576

recovery_url="https://raw.githubusercontent.com/adybag14-cyber/termux-hermes/$installer_commit/install.sh"
recovery_log="$TMPDIR/live-apt-recovery.log"
trap 'timeout 20s hermes gateway stop >/dev/null 2>&1 || true' EXIT
curl -fsSL --retry 6 --retry-all-errors \
  "$recovery_url" | HERMES_RECOVERY_INSTALL_URL="$recovery_url" bash 2>&1 | tee "$recovery_log"
grep -F "Recovered 1048576 bytes from APT's interrupted package download." "$recovery_log"
grep -F "Downloading $filename (resuming from 1048576 bytes)..." "$recovery_log"
test "$(sha256sum "$HOME/.hermes/.env")" = "$env_before"
test -e "$HOME/.hermes/hermes-agent/.git/index.lock"
test "$(hermes config get model.max_tokens --json)" = 8192
test "$(package_status python)" = installed
test "$(sha256sum "$PREFIX/bin/python3.13")" = "$python_before"
test "$(dpkg-query -S "$PREFIX/bin/python3.13")" = "$python_owner"
test "$(dpkg-query -W -f='${Version}' python)" = "$python_version"
test "$(sha256sum "$PREFIX/bin/pydoc3.13")" = "$pydoc_before"
test "$(dpkg-query -S "$PREFIX/bin/pydoc3.13")" = "$pydoc_owner"
test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'
apt-mark showhold | grep -Fx python
for package in python3.13 python3.13-ensurepip-wheels; do
  test "$(package_status "$package")" != installed
done
test ! -e "$recovery_partial"
test ! -e "${recovery_partial%.part}"
test ! -e "$apt_partial"
validate_installed
echo LIVE_SIGNED_APT_STREAMED_RECOVERY_OK
