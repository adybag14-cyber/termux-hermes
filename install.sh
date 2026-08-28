#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

EXPECTED_PREFIX=/data/data/com.termux/files/usr
PRIMARY_SOURCE='deb https://packages.termux.dev/apt/termux-main stable main'
MIN_PACKAGE_VERSION='0.20.6+termux1'
RECOVERY_MAX_TOKENS="${HERMES_RECOVERY_MAX_TOKENS:-8192}"

fail() { printf 'Hermes recovery failed: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

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
apt-get -o Acquire::Retries=4 update >/dev/null 2>&1 || base_ok=false
apt-get -s install ncurses ncurses-ui-libs >/dev/null 2>&1 || base_ok=false
if ! $base_ok; then
  backup="$PREFIX/etc/apt/sources.list.hermes-recovery-$(date -u +%Y%m%dT%H%M%SZ).bak"
  [ ! -f "$PREFIX/etc/apt/sources.list" ] || cp -p "$PREFIX/etc/apt/sources.list" "$backup"
  printf '%s\n' "$PRIMARY_SOURCE" > "$PREFIX/etc/apt/sources.list"
  printf 'Termux mirror package skew detected; switched main repository to the official primary.\n'
  [ ! -f "$backup" ] || printf 'Previous source list saved at %s\n' "$backup"
  apt-get -o Acquire::Retries=5 update
  pkg upgrade -y
fi

step "Enabling the signed Hermes/Termux package repository"
bash <(curl -fsSL --retry 6 --retry-all-errors \
  https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh)

step "Installing the latest verified Hermes Agent package"
pkg install -y hermes-agent
installed="$(dpkg-query -W -f='${Version}' hermes-agent)"
if ! dpkg --compare-versions "$installed" ge "$MIN_PACKAGE_VERSION"; then
  fail "repository returned hermes-agent $installed; expected at least $MIN_PACKAGE_VERSION"
fi
hash -r

step "Preserving configuration and applying the affordable OpenRouter output cap"
hermes config migrate >/dev/null 2>&1 || true
hermes config set model.max_tokens "$RECOVERY_MAX_TOKENS"

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
