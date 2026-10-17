#!/usr/bin/env bash
# Candidate-only native compatibility probes. Never creates or publishes a .deb.
# Usage: bash scripts/probe_native_compatibility.sh GROUP PATCHED_SOURCE OUT
set -Eeuo pipefail

if [[ "${1:-}" == --in-container ]]; then
  group="$2"
  umask 022
  # Root-built evidence must remain readable by the Actions artifact uploader,
  # including diagnostics from a failed build and copied restrictive input files.
  trap 'find /out -type d -exec chmod a+rx {} +; find /out -type f -exec chmod a+r {} +' EXIT
  export PREFIX=/data/data/com.termux/files/usr
  export TMPDIR="$PREFIX/tmp"
  export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
  mkdir -p "$TMPDIR"
  printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
  env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 -o APT::Update::Error-Mode=any update
  env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 -o Dpkg::Options::="--force-confnew" dist-upgrade -y
  dpkg --force-not-root --force-script-chrootless --install /baseline/package.deb
  test "$(dpkg-query -W -f='${Version}' hermes-agent)" = 0.22.2-1

  root="$PREFIX/lib/hermes-agent"
  export HERMES_PROBE_PAYLOAD="$root"
  export HERMES_PROBE_PYTHON="$root/tools/python$PREFIX/bin/python3.14"
  export PATH="$root/tools/node$PREFIX/bin:$root/tools/npm$PREFIX/bin:$PREFIX/bin:$PATH"
  export LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib"
  export HERMES_PROBE_ORIGINAL_LD_LIBRARY_PATH="$LD_LIBRARY_PATH"
  export PYTHONDONTWRITEBYTECODE=1
  [[ -e /bin/sh ]] || ln -s "$PREFIX/bin/sh" /bin/sh
  "$HERMES_PROBE_PYTHON" -c 'import sys,platform; assert sys.platform=="android"; assert platform.machine() in ("aarch64","arm64"); assert sys.version_info[:2]==(3,14); print(sys.version)'
  if [[ "$group" == browser ]]; then
    bash /probes/scripts/compatibility_probe_browser.sh --source /source --out /out
    exit 0
  fi

  build_packages=(libc++ clang make git patchelf binutils pkg-config autoconf automake libtool
                  libandroid-posix-semaphore libandroid-support libffi openssl)
  if [[ "$group" == matrix ]]; then build_packages+=(cmake ninja); fi
  if [[ "$group" == nemo ]]; then build_packages+=(rust protobuf cmake ninja); fi
  env -u LD_LIBRARY_PATH apt-get -o Acquire::Retries=5 install -y "${build_packages[@]}"
  dpkg-query -W -f='${Package}\t${Version}\n' > /out/TERMUX-PACKAGES.tsv

  # Match the canonical builder's current libc++ without changing installed
  # payload bytes. This candidate runtime input is retained as explicit evidence.
  mkdir -p /out/build-runtime-libs
  cp "$PREFIX/lib/libc++_shared.so" /out/build-runtime-libs/
  sha256sum /out/build-runtime-libs/* > /out/BUILD-RUNTIME-SHA256SUMS
  export LD_LIBRARY_PATH="/out/build-runtime-libs:$LD_LIBRARY_PATH"
  export CONFIG_SHELL="$PREFIX/bin/sh"
  export CARGO_BUILD_JOBS=1 MAKEFLAGS=-j1 CMAKE_BUILD_PARALLEL_LEVEL=1
  export ANDROID_API_LEVEL=24
  export LDFLAGS="-L$root/tools/python$PREFIX/lib ${LDFLAGS:-}"
  export CFLAGS="-I$root/tools/python$PREFIX/include ${CFLAGS:-}"
  export RUSTFLAGS="-L$root/tools/python$PREFIX/lib ${RUSTFLAGS:-}"
  export PYO3_PYTHON="$HERMES_PROBE_PYTHON"
  export PROTOC="$PREFIX/bin/protoc" PROTOC_BIN_PATH="$PREFIX/bin/protoc"

  build_root="$(mktemp -d "$TMPDIR/hermes-compat-XXXXXX")"
  export HERMES_HOME="$build_root/home"
  export HERMES_RUNTIME_DIR="$build_root/tools"
  export UV_CACHE_DIR="$build_root/uv-cache"
  export PYTHONPATH=/source
  "$HERMES_PROBE_PYTHON" /source/scripts/termux/build_environment.py prepare-tools \
    --root "$build_root" --source-tools "$root/tools"
  # This is a separate, disposable build environment managed by PM. The
  # installed Hermes environment is never modified by the probe.
  . /source/scripts/termux/build_config.sh
  requirements=(--requirement pip==26.2.1 --requirement packaging==26.0)
  for requirement in "${TOOLCHAIN_PINS[@]}"; do requirements+=(--requirement "$requirement"); done
  "$HERMES_PROBE_PYTHON" -m pm.build_env --out "$build_root/build-venv" \
    --python "$HERMES_PROBE_PYTHON" "${requirements[@]}"
  "$build_root/build-venv/bin/python" -u /probes/scripts/probe_native_compatibility.py \
    build --group "$group" --source /source --out /out
  echo "NATIVE_COMPATIBILITY_PASSED: $group"
  exit 0
fi

[[ $# == 3 ]] || { echo "usage: $0 GROUP PATCHED_SOURCE OUT" >&2; exit 2; }
group="$1"
case "$group" in uvloop|matrix|nemo|browser) ;; *) echo "Unknown probe group: $group" >&2; exit 2;; esac
case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM runner required" >&2; exit 1;; esac
source="$(realpath "$2")"
mkdir -p "$3"
out="$(realpath "$3")"
packaging="$(cd "$(dirname "$0")/.." && pwd)"
test -f "$source/uv.lock"
test -f "$source/scripts/termux/compat_sources.py"
test -f "$source/scripts/termux/nemo_source.py"
TERMUX_IMAGE="$(python3 - "$packaging/manifest/release.json" <<'PY'
import json, re, sys
image = json.load(open(sys.argv[1]))["termux_image"]
assert re.fullmatch(r"termux/termux-docker@sha256:[a-f0-9]{64}", image)
print(image)
PY
)"
fixture_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/hermes-compat-fixture"
mkdir -p "$fixture_dir"
deb="$fixture_dir/hermes-agent_0.22.2-1_aarch64.deb"
deb_sha=deb163351554ca03f7104f91a50f4f8dc4d9247ce0cf5f2cca2608be3b319add
if ! printf '%s  %s\n' "$deb_sha" "$deb" | sha256sum -c - >/dev/null 2>&1; then
  curl -fL --retry 6 --retry-all-errors \
    https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.22.2-20261016.1/hermes-agent_0.22.2-1_aarch64.deb \
    -o "$deb"
fi
printf '%s  %s\n' "$deb_sha" "$deb" | sha256sum -c -
test "$(dpkg-deb -f "$deb" Package)" = hermes-agent
test "$(dpkg-deb -f "$deb" Version)" = 0.22.2-1
test "$(dpkg-deb -f "$deb" Architecture)" = aarch64
cp "$source/uv.lock" "$out/PROBE-UV.lock"
cp "$source/pyproject.toml" "$out/PROBE-PYPROJECT.toml"
python3 - "$out" "$group" "$TERMUX_IMAGE" "$deb_sha" <<'PY'
import json, os, sys
from pathlib import Path
out, group, image, sha = sys.argv[1:]
Path(out, "PROBE-INPUTS.json").write_text(json.dumps({
    "group": group, "builder_image": image, "baseline_package_sha256": sha,
    "baseline_package_version": "0.22.2-1", "packaging_commit": os.environ.get("GITHUB_SHA"),
    "purpose": "next-stable compatibility probe; no release output",
}, indent=2) + "\n")
PY
chmod 0777 "$out"
chmod a+r "$deb"
docker pull "$TERMUX_IMAGE"
test "$(docker image inspect --format '{{.Architecture}}' "$TERMUX_IMAGE")" = arm64
docker run --rm --platform linux/arm64 --user root --tmpfs /bin \
  -v "$source:/source:ro" -v "$packaging:/probes:ro" \
  -v "$deb:/baseline/package.deb:ro" -v "$out:/out" \
  "$TERMUX_IMAGE" bash /probes/scripts/probe_native_compatibility.sh --in-container "$group" \
  2>&1 | tee "$out/native-probe.log"
