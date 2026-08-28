#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

SOURCE_TREE="${1:?Hermes source tree is required}"
PACKAGING_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${2:?Output directory is required}"
SOURCE_COMMIT="${3:?Hermes source commit is required}"
PACKAGE_VERSION="${4:?package version is required}"
WHEELHOUSE_TAG="${5:?wheelhouse release tag is required}"
WHEELHOUSE_SUMS_SHA256="${6:?wheelhouse SHA256SUMS digest is required}"
SOURCE_REPOSITORY="${HERMES_SOURCE_REPOSITORY:-NousResearch/hermes-agent}"
WHEELHOUSE_REPOSITORY="${HERMES_WHEELHOUSE_REPOSITORY:-adybag14-cyber/termux-hermes}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
BUILD_HOME="${TMPDIR:-$PREFIX/tmp}/hermes-agent-deb-home"
APP="$PREFIX/lib/hermes-agent/app"
WHEELHOUSE="$BUILD_HOME/wheelhouse"

case "$SOURCE_COMMIT" in *[!0-9a-f]*|'') echo "Invalid source commit" >&2; exit 1;; esac
case "$WHEELHOUSE_TAG" in *[!0-9A-Za-z._-]*|'') echo "Invalid wheelhouse tag" >&2; exit 1;; esac
case "$WHEELHOUSE_SUMS_SHA256" in
  *[!0-9a-f]*|'') echo "Invalid wheelhouse SHA-256" >&2; exit 1;;
esac
[ "${#WHEELHOUSE_SUMS_SHA256}" -eq 64 ] || { echo "Invalid wheelhouse SHA-256 length" >&2; exit 1; }

rm -rf "$BUILD_HOME" "$APP"
mkdir -p "$OUTPUT_DIR" "$APP" "$WHEELHOUSE"

# A rotating mirror can briefly expose mismatched package generations. Release
# construction uses Termux's official primary repository for coherent metadata.
printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > \
  "$PREFIX/etc/apt/sources.list"
apt-get update
apt-get install -y ca-certificates curl git gnupg
bash <(curl -fsSL --retry 5 --retry-all-errors \
  https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh)
apt-get install -y python3.13 uv

test "$(git -C "$SOURCE_TREE" rev-parse HEAD)" = "$SOURCE_COMMIT"
cp -a "$SOURCE_TREE/." "$APP/"
rm -rf "$APP/.git"
printf 'apt\n' > "$APP/.install_method"

BASE_URL="https://github.com/$WHEELHOUSE_REPOSITORY/releases/download/$WHEELHOUSE_TAG"
curl -fL --retry 6 --retry-all-errors \
  "$BASE_URL/SHA256SUMS" -o "$WHEELHOUSE/SHA256SUMS"
printf '%s  %s\n' "$WHEELHOUSE_SUMS_SHA256" "$WHEELHOUSE/SHA256SUMS" | sha256sum -c -

wheel_count=0
while read -r checksum filename; do
  case "$filename" in
    *.whl)
      case "$filename" in */*|*..*) echo "Unsafe wheelhouse filename: $filename" >&2; exit 1;; esac
      curl -fL --retry 6 --retry-all-errors "$BASE_URL/$filename" -o "$WHEELHOUSE/$filename"
      printf '%s  %s\n' "$checksum" "$WHEELHOUSE/$filename" | sha256sum -c -
      wheel_count=$((wheel_count + 1))
      ;;
  esac
done < "$WHEELHOUSE/SHA256SUMS"
[ "$wheel_count" -eq 10 ] || { echo "Expected 10 native wheels, got $wheel_count" >&2; exit 1; }

uv venv --python "$PREFIX/bin/python3.13" "$APP/venv"
VENV_PY="$APP/venv/bin/python"
uv pip install --python "$VENV_PY" \
  --requirements "$PACKAGING_ROOT/audit/resolved.txt" \
  --constraint "$PACKAGING_ROOT/audit/lock-constraints.txt" \
  --find-links "$WHEELHOUSE" \
  --only-binary :all:
uv pip install --python "$VENV_PY" --no-deps --editable "$APP"
uv pip check --python "$VENV_PY"

cat > "$PREFIX/bin/hermes" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec "$APP/venv/bin/hermes" "\$@"
EOF
chmod 0755 "$PREFIX/bin/hermes"

"$PREFIX/bin/hermes" --version
"$VENV_PY" - <<'PY'
import importlib

for module in (
    "hermes_cli",
    "psutil",
    "yaml",
    "cffi",
    "PIL",
    "pydantic_core",
    "cryptography",
    "jiter",
    "rpds",
    "mcp",
    "httpx2",
    "snowballstemmer",
    "telegram",
):
    importlib.import_module(module)
print("Hermes 0.20.6 native packaged-runtime import smoke passed")
PY

find "$APP" -type d -name __pycache__ -prune -exec rm -rf {} + || true
find "$APP" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete || true

HERMES_VERSION="$($VENV_PY -c 'from hermes_cli import __version__; print(__version__)')"
test "$HERMES_VERSION" = "${PACKAGE_VERSION%%+*}"

"$PREFIX/bin/python3.13" "$PACKAGING_ROOT/scripts/package_hermes_agent.py" \
  --app "$APP" \
  --launcher "$PREFIX/bin/hermes" \
  --version "$PACKAGE_VERSION" \
  --hermes-version "$HERMES_VERSION" \
  --source-commit "$SOURCE_COMMIT" \
  --source-repository "$SOURCE_REPOSITORY" \
  --wheelhouse-repository "$WHEELHOUSE_REPOSITORY" \
  --wheelhouse-tag "$WHEELHOUSE_TAG" \
  --wheelhouse-sha256sums "$WHEELHOUSE_SUMS_SHA256" \
  --output-dir "$OUTPUT_DIR"

(cd "$OUTPUT_DIR" && sha256sum hermes-agent_*.deb > SHA256SUMS)
