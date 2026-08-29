#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

INSTALL_URL='https://raw.githubusercontent.com/adybag14-cyber/termux-hermes/main/install.sh'

# A program launched by a streamed `curl | bash` installer shares the script's
# input pipe and can accidentally consume commands that Bash has not read yet.
# Materialize the installer first so pkg, apt, and Hermes always get /dev/null.
if [ "${HERMES_RECOVERY_FILE_RUN:-0}" != 1 ] && [ -z "${BASH_SOURCE[0]:-}" ]; then
  bootstrap_dir="${TMPDIR:-/data/data/com.termux/files/usr/tmp}"
  mkdir -p "$bootstrap_dir"
  bootstrap="$(mktemp "$bootstrap_dir/hermes-recovery.XXXXXX")"
  trap 'rm -f "$bootstrap"' EXIT
  curl -fsSL --retry 6 --retry-all-errors "$INSTALL_URL" -o "$bootstrap"
  if HERMES_RECOVERY_FILE_RUN=1 bash "$bootstrap" </dev/null; then
    bootstrap_status=0
  else
    bootstrap_status=$?
  fi
  rm -f "$bootstrap"
  trap - EXIT
  exit "$bootstrap_status"
fi

EXPECTED_PREFIX=/data/data/com.termux/files/usr
PRIMARY_SOURCE='deb https://packages.termux.dev/apt/termux-main stable main'
PACKAGE_VERSION='0.20.6+termux1'
PACKAGE_FILENAME="hermes-agent_${PACKAGE_VERSION}_aarch64.deb"
PACKAGE_SHA256='8d54e0339b382c102b653486298bc8cf65abefa71cff38de8b43acf6e849a652'
PACKAGE_RELEASE_URL="https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.20.6-20260828.1/hermes-agent_0.20.6%2Btermux1_aarch64.deb"
PACKAGE_ORACLE_URL="http://144.21.61.111/termux/pool/main/$PACKAGE_FILENAME"
MIN_PACKAGE_VERSION="$PACKAGE_VERSION"
RECOVERY_MAX_TOKENS="${HERMES_RECOVERY_MAX_TOKENS:-8192}"

fail() { printf 'Hermes recovery failed: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

verify_package() {
  [ -f "$1" ] &&
    printf '%s  %s\n' "$PACKAGE_SHA256" "$1" | sha256sum -c - >/dev/null 2>&1
}

file_size() {
  if [ -f "$1" ]; then
    wc -c < "$1"
  else
    printf 0
  fi
}

download_verified_package() {
  cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/hermes-recovery"
  complete="$cache_dir/$PACKAGE_FILENAME"
  partial="$complete.part"
  apt_partial="$PREFIX/var/cache/apt/archives/partial/$PACKAGE_FILENAME"
  mkdir -p "$cache_dir"

  if verify_package "$complete"; then
    printf '%s\n' "$complete"
    return 0
  fi
  rm -f "$complete"

  if [ ! -e "$partial" ] && [ -s "$apt_partial" ]; then
    cp "$apt_partial" "$partial"
    printf "Recovered %s bytes from APT's interrupted package download.\n" \
      "$(file_size "$partial")" >&2
  fi

  if verify_package "$partial"; then
    mv -f "$partial" "$complete"
    printf '%s\n' "$complete"
    return 0
  fi

  for package_url in "$PACKAGE_RELEASE_URL" "$PACKAGE_ORACLE_URL"; do
    partial_bytes="$(file_size "$partial")"
    printf 'Downloading %s (resuming from %s bytes)...\n' \
      "$PACKAGE_FILENAME" "$partial_bytes" >&2
    if curl -fL --http1.1 --continue-at - \
      --connect-timeout 20 \
      --retry 20 --retry-delay 3 --retry-max-time 1800 \
      --retry-all-errors --retry-connrefused \
      --output "$partial" "$package_url"; then
      if verify_package "$partial"; then
        mv -f "$partial" "$complete"
        printf '%s\n' "$complete"
        return 0
      fi
      printf 'Downloaded bytes failed the pinned SHA-256 check; trying the alternate source.\n' >&2
      rm -f "$partial"
    else
      partial_bytes="$(file_size "$partial")"
      printf 'Transfer stopped at %s bytes; trying the alternate source with the same partial file.\n' \
        "$partial_bytes" >&2
    fi
  done

  if verify_package "$partial"; then
    mv -f "$partial" "$complete"
    printf '%s\n' "$complete"
    return 0
  fi
  partial_bytes="$(file_size "$partial")"
  fail "package transfer is still incomplete at $partial_bytes bytes; rerun the same curl command to resume it"
}

[ "${PREFIX:-}" = "$EXPECTED_PREFIX" ] || fail "run this inside the official Termux app"
[ "$(dpkg --print-architecture 2>/dev/null || true)" = aarch64 ] || \
  fail "only Termux aarch64 is currently supported"
case "$RECOVERY_MAX_TOKENS" in
  ''|*[!0-9]*) fail "HERMES_RECOVERY_MAX_TOKENS must be a positive integer";;
esac
[ "$RECOVERY_MAX_TOKENS" -gt 0 ] || fail "HERMES_RECOVERY_MAX_TOKENS must be positive"

mkdir -p "${TMPDIR:-$PREFIX/tmp}" "$HOME/.hermes/logs"
export DEBIAN_FRONTEND=noninteractive

step "Checking official Termux package consistency"
base_ok=true
apt-get -o Acquire::Retries=4 update </dev/null >/dev/null 2>&1 || base_ok=false
apt-get -s install ncurses ncurses-ui-libs </dev/null >/dev/null 2>&1 || base_ok=false
if ! $base_ok; then
  backup="$PREFIX/etc/apt/sources.list.hermes-recovery-$(date -u +%Y%m%dT%H%M%SZ).bak"
  [ ! -f "$PREFIX/etc/apt/sources.list" ] || cp -p "$PREFIX/etc/apt/sources.list" "$backup"
  printf '%s\n' "$PRIMARY_SOURCE" > "$PREFIX/etc/apt/sources.list"
  printf 'Termux mirror package skew detected; switched main repository to the official primary.\n'
  [ ! -f "$backup" ] || printf 'Previous source list saved at %s\n' "$backup"
  apt-get -o Acquire::Retries=5 update </dev/null
  pkg upgrade -y </dev/null
fi

step "Enabling the signed Hermes/Termux package repository"
bash <(curl -fsSL --retry 6 --retry-all-errors \
  https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh) </dev/null

step "Installing the latest verified Hermes Agent package"
installed="$(dpkg-query -W -f='${Version}' hermes-agent 2>/dev/null || true)"
if [ -z "$installed" ] || ! dpkg --compare-versions "$installed" ge "$MIN_PACKAGE_VERSION"; then
  package_file="$(download_verified_package)"
  apt-get \
    -o Acquire::Retries=8 \
    -o Acquire::http::Timeout=45 \
    -o Acquire::https::Timeout=45 \
    install -y "$package_file" </dev/null
  rm -f \
    "$package_file" \
    "$package_file.part" \
    "$PREFIX/var/cache/apt/archives/partial/$PACKAGE_FILENAME"
else
  printf 'hermes-agent %s is already installed.\n' "$installed"
fi
installed="$(dpkg-query -W -f='${Version}' hermes-agent)"
if ! dpkg --compare-versions "$installed" ge "$MIN_PACKAGE_VERSION"; then
  fail "repository returned hermes-agent $installed; expected at least $MIN_PACKAGE_VERSION"
fi
hash -r

step "Preserving configuration and applying the affordable OpenRouter output cap"
hermes config migrate </dev/null >/dev/null 2>&1 || true
hermes config set model.max_tokens "$RECOVERY_MAX_TOKENS" </dev/null

step "Verifying APT-managed update behavior"
version_output="$(hermes --version)"
printf '%s\n' "$version_output"
grep -Fx apt "$PREFIX/lib/hermes-agent/app/.install_method" >/dev/null
update_log="${TMPDIR:-$PREFIX/tmp}/hermes-apt-update-check.$$"
if hermes update >"$update_log" 2>&1; then
  rm -f "$update_log"
  fail "APT-managed hermes update unexpectedly tried to mutate its package"
fi
grep -F 'pkg upgrade hermes-agent' "$update_log" >/dev/null || {
  cat "$update_log" >&2
  rm -f "$update_log"
  fail "Hermes did not report the APT upgrade path"
}
rm -f "$update_log"

step "Restarting the gateway with one managed command"
timeout 20s hermes gateway stop >/dev/null 2>&1 || true
if ! timeout 30s hermes gateway start; then
  gateway_log="$HOME/.hermes/logs/gateway.log"
  nohup hermes gateway run >>"$gateway_log" 2>&1 </dev/null &
  gateway_pid=$!
  sleep 5
  kill -0 "$gateway_pid" 2>/dev/null || {
    tail -n 80 "$gateway_log" >&2 || true
    fail "gateway failed to start"
  }
  printf 'Gateway started in fallback mode as PID %s; log: %s\n' "$gateway_pid" "$gateway_log"
else
  hermes gateway status || true
fi

printf '\nHermes recovery complete. Package: %s; model.max_tokens: %s\n' \
  "$installed" "$RECOVERY_MAX_TOKENS"
