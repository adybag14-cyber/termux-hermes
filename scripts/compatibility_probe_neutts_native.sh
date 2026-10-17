#!/usr/bin/env bash
# Disposable source/component experiment. No models, synthesis or PM admission.
set -euo pipefail
: "${PREFIX:?Run inside the native Termux foundation container}"
[[ "$PREFIX" == /data/data/com.termux/files/usr ]]
[[ "$(id -u)" == 1000 ]]
[[ "$(uname -m)" == aarch64 ]]
umask 022
export PATH="$PREFIX/bin"
export LD_LIBRARY_PATH="$PREFIX/lib"
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV LLAMA_CPP_LIB GGML_BACKEND_PATH
export PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
exec "$PREFIX/bin/python" -I -B \
  "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/compatibility_probe_neutts_native.py" "$@"
