#!/usr/bin/env bash
# Upgrade the previous published package in a real native Termux userspace.
# Usage: TERMUX_IMAGE=<digest> bash scripts/check_bundle_upgrade.sh DEB VERSION
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  expected_version="$2"
  export PREFIX=/data/data/com.termux/files/usr
  export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
  export TMPDIR="$PREFIX/tmp"
  mkdir -p "$TMPDIR"
  printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
  apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
  apt-get -o Acquire::Retries=5 -o Dpkg::Options::="--force-confnew" dist-upgrade -y
  apt-get -o Acquire::Retries=5 install -y ripgrep

  python_deb=/fixtures/python_3.13.15_aarch64.deb
  old_deb=/fixtures/hermes-agent_0.20.6+termux2_aarch64.deb
  for package in "$python_deb" "$old_deb"; do
    dependencies="$(dpkg-deb -f "$package" Depends)"
    if [[ -n "$dependencies" ]]; then apt-get satisfy -y "$dependencies"; fi
    dpkg --force-not-root --force-script-chrootless --install "$package"
    if [[ "$package" == "$python_deb" ]]; then apt-mark hold python; fi
  done
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = 0.20.6+termux2
  test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'
  hermes --version
  test -f "$PREFIX/bin/hermes"
  test ! -L "$PREFIX/bin/hermes"
  dpkg-query -S "$PREFIX/bin/hermes" | grep -F 'hermes-agent:'

  hermes config set model.max_tokens 65536
  printf 'UPGRADE_SENTINEL=preserve-me\n' > "$HOME/.hermes/.env"
  mkdir -p "$HOME/.hermes/hermes-agent/.git"
  : > "$HOME/.hermes/hermes-agent/.git/index.lock"
  env_before="$(sha256sum "$HOME/.hermes/.env")"
  config_before="$(sha256sum "$HOME/.hermes/config.yaml")"
  python_before="$(sha256sum "$PREFIX/bin/python3.13")"
  python_owner="$(dpkg-query -S "$PREFIX/bin/python3.13")"
  python_version="$(dpkg-query -W -f='${Version}' python)"
  rg_before="$(sha256sum "$PREFIX/bin/rg")"
  rg_owner="$(dpkg-query -S "$PREFIX/bin/rg")"
  rg_version="$(dpkg-query -W -f='${Version}' ripgrep)"

  # Exercise dpkg's real old-to-new maintainer-script transition. In
  # particular, the old owned launcher must become the new owned symlink.
  dpkg --force-not-root --force-script-chrootless --install /candidate/package.deb
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = "$expected_version"
  test "$(dpkg-query -W -f='${db:Status-Status}' hermes-agent)" = installed
  test "$(sha256sum "$HOME/.hermes/.env")" = "$env_before"
  test "$(sha256sum "$HOME/.hermes/config.yaml")" = "$config_before"
  test -e "$HOME/.hermes/hermes-agent/.git/index.lock"
  test "$(sha256sum "$PREFIX/bin/python3.13")" = "$python_before"
  test "$(dpkg-query -S "$PREFIX/bin/python3.13")" = "$python_owner"
  test "$(dpkg-query -W -f='${Version}' python)" = "$python_version"
  apt-mark showhold | grep -Fx python
  test "$(sha256sum "$PREFIX/bin/rg")" = "$rg_before"
  test "$(dpkg-query -S "$PREFIX/bin/rg")" = "$rg_owner"
  test "$(dpkg-query -W -f='${Version}' ripgrep)" = "$rg_version"
  test "$(python3.13 -c 'import sys; print(sys.version_info[:2])')" = '(3, 13)'
  rg --version
  test -z "$(dpkg --audit)"
  for name in hermes hermes-agent hermes-acp; do
    test -L "$PREFIX/bin/$name"
    test "$(readlink "$PREFIX/bin/$name")" = "../lib/hermes-agent/bin/$name"
    test -x "$PREFIX/bin/$name"
  done

  hermes --version
  hermes chat --help >/dev/null
  hermes-acp --check
  test "$(hermes config get model.max_tokens --json)" = 65536
  test "$(sha256sum "$HOME/.hermes/.env")" = "$env_before"
  if hermes update > "$TMPDIR/upgrade-refusal.log" 2>&1; then
    echo 'APT updater unexpectedly succeeded' >&2
    exit 1
  else
    update_status=$?
  fi
  test "$update_status" = 2
  grep -F 'pkg upgrade hermes-agent' "$TMPDIR/upgrade-refusal.log"

  root="$PREFIX/lib/hermes-agent"
  env LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib" \
    PYTHONPATH="$root/app" HERMES_RUNTIME_DIR="$root/tools" "$root/venv/bin/python" -B - <<'PY'
import importlib
import sys
import pm
from pm.features import read_features
assert sys.version_info[:2] == (3, 14), sys.version
for module in (
    "cli", "run_agent", "tui_gateway.server", "psutil", "_cffi_backend",
    "PIL._imaging", "_pillow_heif", "pydantic_core", "cryptography", "jiter",
    "rpds", "mcp", "httpx2", "snowballstemmer", "telegram", "croniter", "acp",
    "ruamel.yaml", "httptools", "watchfiles", "resvg_py",
):
    importlib.import_module(module)
assert read_features() == ["acp", "cron", "mcp", "telegram", "termux"]
assert not pm.check(), pm.check()
print("Upgraded Python 3.14 runtime and complete Termux profile passed")
PY
  echo LEGACY_TO_BUNDLED_UPGRADE_OK
  exit 0
fi

[[ $# == 2 ]] || { echo "usage: $0 DEB VERSION" >&2; exit 2; }
deb="$(realpath "$1")"
version="$2"
[[ "${TERMUX_IMAGE:-}" =~ ^termux/termux-docker@sha256:[a-f0-9]{64}$ ]] || {
  echo 'TERMUX_IMAGE must name the pinned official image digest' >&2; exit 2;
}
case "$(uname -m)" in aarch64|arm64) ;; *) echo 'Native ARM runner required' >&2; exit 1;; esac
[[ -s "$deb" ]]
test "$(dpkg-deb -f "$deb" Package)" = hermes-agent
test "$(dpkg-deb -f "$deb" Version)" = "$version"
test "$(dpkg-deb -f "$deb" Architecture)" = aarch64
test -z "$(dpkg-deb -f "$deb" Depends)"

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
fetch_fixture hermes-agent_0.20.6+termux2_aarch64.deb \
  4e87ebff34c92498b8fe7474a0d74d7aa8e34d0cc02ccc5df8fab2cca3e417af \
  https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.20.6-20260829.1/hermes-agent_0.20.6%2Btermux2_aarch64.deb
chmod -R a+rX "$fixtures"
docker run --rm --privileged --security-opt seccomp=unconfined \
  -v "$deb:/candidate/package.deb:ro" -v "$fixtures:/fixtures:ro" \
  -v "$(realpath "$0"):/check-upgrade.sh:ro" \
  "$TERMUX_IMAGE" bash /check-upgrade.sh --in-container "$version"
