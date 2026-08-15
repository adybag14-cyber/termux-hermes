#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

SOURCE_TREE="${1:?Hermes source tree is required}"
PACKAGING_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${2:?Output directory is required}"
SOURCE_COMMIT="${3:?Hermes source commit is required}"
PACKAGE_VERSION="${4:?package version is required}"
SOURCE_REPOSITORY="${HERMES_SOURCE_REPOSITORY:-adybag14-cyber/hermes-agent}"
SOURCE_BRANCH="${HERMES_SOURCE_BRANCH:-fix/termux-native-install-update-v2}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
BUILD_HOME="${TMPDIR:-$PREFIX/tmp}/hermes-agent-deb-home"
APP="$PREFIX/lib/hermes-agent/app"

rm -rf "$BUILD_HOME" "$APP"
mkdir -p "$OUTPUT_DIR"

bash <(curl -fsSL https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh)
pkg install -y python3.13

export HERMES_HOME="$BUILD_HOME"
export HERMES_INSTALL_DIR="$APP"
export HERMES_REPO_URL="https://github.com/$SOURCE_REPOSITORY.git"
bash "$SOURCE_TREE/scripts/install-termux.sh" \
  --branch "$SOURCE_BRANCH" \
  --commit "$SOURCE_COMMIT" \
  --python "$PREFIX/bin/python3.13" \
  --skip-setup \
  --skip-browser \
  --no-skills \
  --non-interactive

"$PREFIX/bin/hermes" --version
"$APP/venv/bin/python" - <<'PY'
import importlib
for module in ("hermes_cli", "psutil", "yaml", "cffi", "PIL", "pydantic_core", "cryptography", "jiter", "rpds"):
    importlib.import_module(module)
print("Hermes native packaged-runtime import smoke passed")
PY

printf 'apt\n' > "$APP/.install_method"
rm -rf "$APP/.git" "$BUILD_HOME"
find "$APP" -type d -name __pycache__ -prune -exec rm -rf {} + || true
find "$APP" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete || true

HERMES_VERSION="$($APP/venv/bin/python -c 'from hermes_cli import __version__; print(__version__)')"
WHEELHOUSE_REPOSITORY="$($APP/venv/bin/python -c 'from hermes_cli.termux_wheelhouse import RELEASE_REPOSITORY; print(RELEASE_REPOSITORY)')"
WHEELHOUSE_TAG="$($APP/venv/bin/python -c 'from hermes_cli.termux_wheelhouse import RELEASE_TAG; print(RELEASE_TAG)')"
WHEELHOUSE_SUMS="$($APP/venv/bin/python -c 'from hermes_cli.termux_wheelhouse import SHA256SUMS_SHA256; print(SHA256SUMS_SHA256)')"

"$PREFIX/bin/python3.13" "$PACKAGING_ROOT/scripts/package_hermes_agent.py" \
  --app "$APP" \
  --launcher "$PREFIX/bin/hermes" \
  --version "$PACKAGE_VERSION" \
  --hermes-version "$HERMES_VERSION" \
  --source-commit "$SOURCE_COMMIT" \
  --source-repository "$SOURCE_REPOSITORY" \
  --wheelhouse-repository "$WHEELHOUSE_REPOSITORY" \
  --wheelhouse-tag "$WHEELHOUSE_TAG" \
  --wheelhouse-sha256sums "$WHEELHOUSE_SUMS" \
  --output-dir "$OUTPUT_DIR"

(cd "$OUTPUT_DIR" && sha256sum hermes-agent_*.deb > SHA256SUMS)