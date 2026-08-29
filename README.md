# Termux Hermes Immutable Wheelhouse

This repository builds the native Python wheels required by the Hermes Agent
Termux profile so phones can install binary wheels instead of compiling C and
Rust packages locally.

## One-command install and recovery

For an existing native Termux aarch64 installation—including an interrupted
Git update with a stale `.git/index.lock`—run:

```bash
curl -fsSL --retry 6 --retry-all-errors https://raw.githubusercontent.com/adybag14-cyber/termux-hermes/main/install.sh | bash
```

The recovery path verifies the signed APT repository, repairs upstream Termux
mirror skew only when package simulation proves it is broken, downloads the
latest immutable `hermes-agent` package with resumable transfers and two
independent sources, preserves `~/.hermes`, migrates the configuration, caps
OpenRouter output at 8,192 tokens to avoid unaffordable 32K–65K requests,
verifies that future updates use `pkg upgrade`, and restarts the gateway without
requiring users to paste a multi-line shell fragment.

The package download prefers the immutable GitHub release asset, falls back to
the Oracle APT origin, and verifies the pinned package SHA-256 before local APT
installation. It also recovers an existing APT partial download when present,
including bytes left by a failed `pkg install`. An interrupted transfer remains in
`~/.cache/hermes-recovery/` so rerunning the same one-line command resumes the
existing bytes instead of starting the 63.9 MB download again. A successful
installation removes that cache file.

Set `HERMES_RECOVERY_MAX_TOKENS` before the command to choose a different
positive output cap.

## Native `pkg install hermes-agent` package

This repository also builds a complete native Termux `.deb` for Hermes Agent. The package is not a thin Python wheel: it contains the full Hermes runtime/source assets and a prevalidated CPython 3.13 virtual environment produced by the existing immutable Android wheelhouse flow. The package is stamped as an APT-managed install, so `hermes update` does not mutate package-owned files and instead directs users to `pkg upgrade hermes-agent`.

The signed third-party repository is enabled once with:

```bash
curl -fsSL https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh | bash
```

Then Hermes and the companion native packages are ordinary Termux packages:

```bash
pkg install hermes-agent
pkg install wrangler
pkg install python3.13
```

Repository signing fingerprint:

```text
EAD24A2124EFA7393A78B7B14699F966313F7A6B
```

`build-hermes-package.yml` builds on a native ARM GitHub runner in the pinned official Termux Docker userspace, installs Hermes through the native installer, validates the runtime imports, assembles the `.deb`, and installs that `.deb` into a second clean Termux container before an immutable GitHub release may be published. `apt-hermes-smoke.yml` separately validates installation from the live signed APT repository.

The public APT repository is a contributor-operated distribution/proving path. It does **not** replace the separate upstream requirement that canonical Hermes Termux binary artifacts eventually be built and released by NousResearch-owned CI.

## Locked target

- Hermes source: `NousResearch/hermes-agent@5fc308a70719a83cccdbba4c0e39c23f5a8239d5` (`v2026.8.27`, Hermes 0.20.6)
- Audited runtime: official Termux app GitHub build `v0.118.3` on Android 15/API 35
- ARM build environment: official `termux/termux-docker` image pinned to `sha256:3aed9c7fbcf9195a9919deaad418da006232864a779fb4f322d68a34887a2e15`
- Python: `3.13.15` from the immutable `termux-aarch64-20260824.43.1` release
- Architecture: `aarch64`
- Wheel platform: `android_24_arm64_v8a`
- Dependency profile: Hermes `termux`

Every source distribution URL, version and SHA-256 is stored in
[`manifest/wheels.json`](manifest/wheels.json). A release is never updated in
place: the workflow refuses to publish when its tag already exists.

## Current native wheel set

The current Hermes Termux lock resolves to 74 exact packages under Python 3.13.
Ten packages require Android-native wheels from this repository; the remaining
packages are satisfied by compatible binary or universal wheels during the
binary-only verification install. The native set is:

| Package | Version | Backend | Locked source SHA-256 |
| --- | ---: | --- | --- |
| cffi | 2.0.0 | setuptools/C | `44d1b5909021139fe36001ae048dbdde8214afa20200eda0f64c068cac5d5529` |
| cryptography | 50.0.0 | maturin/Rust+CFFI | `eeac2acb5a20ed25e0ad6d1df9891a520b78b404266b6d11778f25d5d691a6c9` |
| jiter | 0.13.0 | maturin/Rust | `f2839f9c2c7e2dffc1bc5929a510e14ce0a946be9365fd1219e7ef342dae14f4` |
| MarkupSafe | 3.0.3 | setuptools/C | `722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698` |
| Pillow | 12.3.0 | setuptools/C | `3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce` |
| psutil | 7.2.2 | setuptools/C + Android patch | `0746f5f8d406af344fd547f1c8daa5f5c33dbc293bb8d6a16d80b4bb88f59372` |
| pydantic-core | 2.46.4 | maturin/Rust | `62f875393d7f270851f20523dd2e29f082bcc82292d66db2b64ea71f64b6e1c1` |
| PyYAML | 6.0.3 | setuptools/Cython/libyaml | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` |
| rpds-py | 0.30.0 | maturin/Rust | `dd8ff7cf90014af0c0f787eea34794ebf6415242ee1d6fa91eaba725cc441e84` |
| ruamel.yaml.clib | 0.2.15 | setuptools/Cython | `46e4cc8c43ef6a94885f72512094e482114a8a706d3c555a34ed4b0d20200600` |

The prior 91-package Android-emulator discovery snapshot is retained as historical
evidence in [`audit/emulator-audit.json`](audit/emulator-audit.json). It describes
the earlier lock and is not republished as evidence for a refreshed release. The
current exact 74-package resolver output is [`audit/resolved.txt`](audit/resolved.txt),
with direct requirements and lock constraints stored beside it.

## Build design

The `Build immutable arm64 wheelhouse` workflow runs on a native arm64 Ubuntu runner
and executes the build inside Termux's official aarch64 Docker image at a fixed
registry digest. Package discovery and final installation behavior were separately
verified in the official Termux v0.118.3 Android app. The builder:

1. verifies the pinned Python `.deb` and every PyPI sdist before extraction;
2. rejects traversal, symlink and device members in source archives;
3. builds serially with pinned setuptools, Cython, pybind11 and maturin versions;
4. patches psutil's Android platform detection;
5. emits or normalizes PEP 738 Android wheel tags;
6. rewrites `WHEEL` and `RECORD` correctly when normalization is required;
7. verifies package/version/tag, ZIP integrity and native extension presence;
8. installs the complete current 74-package graph with `--only-binary :all:` in a clean venv;
9. imports every native package and runs `uv pip check`;
10. records the exact installed Termux system package versions;
11. publishes wheels, `index.json`, `system-packages.txt`, and `SHA256SUMS` under a new immutable release tag.

## Run locally in native aarch64 Termux

```bash
git clone https://github.com/adybag14-cyber/termux-hermes.git
cd termux-hermes
bash scripts/termux_build.sh "$PWD"
```

The complete wheelhouse is written to
`~/termux-hermes-build/wheelhouse/`. This build is intentionally resource-heavy;
normal users should consume the published release assets instead.

The automated arm64 release build uses the official Termux Docker image by immutable
digest. The image exists specifically to run the Termux environment off-device; it
contains the Termux bootstrap and the AOSP/Bionic runtime components needed by the
Android-targeted Python toolchain.
The workflow invokes `scripts/termux_build.sh /workspace /build docker`; the explicit
mode keeps Docker validation independent of environment variables sanitized by the
Termux container entrypoint.

## Refreshing the lock

Do not edit package versions without regenerating the Termux requirements and
resolver inputs against an exact Hermes commit. A refresh must update together:

- `audit/direct.in`
- `audit/lock-constraints.txt`
- `audit/resolved.txt`
- `manifest/wheels.json`
- this README table

`audit/emulator-audit.json` and the older `audit/build-metadata.json` are retained
as historical evidence for the release that produced them; do not silently relabel
them as proof of a newer lock. Current compatibility metadata can be generated in
native Termux with:

```bash
python3.13 scripts/audit_pypi.py \
  --resolved audit/resolved.txt \
  --output audit/refreshed-emulator-audit.json
```

A new wheelhouse must use a new release tag. Existing release assets must never
be replaced.
