# Termux Hermes Immutable Wheelhouse

This repository builds the native Python wheels required by the Hermes Agent
Termux profile so phones can install binary wheels instead of compiling C and
Rust packages locally.

## Locked target

- Hermes source: `adybag14-cyber/hermes-agent@72f6ab2b183fa94d5f3f33bf105cacf6418c3447`
- Termux app: official GitHub build `v0.118.3`
- Python: `3.13.14` from the immutable `termux-aarch64-20260719.9.1` release
- Architecture: `aarch64`
- Wheel platform: `android_24_arm64_v8a`
- Dependency profile: Hermes `termux`

Every source distribution URL, version and SHA-256 is stored in
[`manifest/wheels.json`](manifest/wheels.json). A release is never updated in
place: the workflow refuses to publish when its tag already exists.

## Emulator audit result

The official Termux app was installed in an Android 15/API 35 emulator on
Windows. Hermes resolved to 91 exact packages under native Android Python 3.13.
Eighty-one already had a compatible universal/Android-installable wheel. The
following ten packages had no Android wheel on PyPI for any architecture and
therefore require native builds:

| Package | Version | Backend | Locked source SHA-256 |
| --- | ---: | --- | --- |
| cffi | 2.0.0 | setuptools/C | `44d1b5909021139fe36001ae048dbdde8214afa20200eda0f64c068cac5d5529` |
| cryptography | 46.0.7 | maturin/Rust+CFFI | `e4cfd68c5f3e0bfdad0d38e023239b96a2fe84146481852dffbcca442c245aa5` |
| jiter | 0.13.0 | maturin/Rust | `f2839f9c2c7e2dffc1bc5929a510e14ce0a946be9365fd1219e7ef342dae14f4` |
| MarkupSafe | 3.0.3 | setuptools/C | `722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698` |
| Pillow | 12.2.0 | setuptools/C | `a830b1a40919539d07806aa58e1b114df53ddd43213d9c8b75847eee6c0182b5` |
| psutil | 7.2.2 | setuptools/C + Android patch | `0746f5f8d406af344fd547f1c8daa5f5c33dbc293bb8d6a16d80b4bb88f59372` |
| pydantic-core | 2.46.4 | maturin/Rust | `62f875393d7f270851f20523dd2e29f082bcc82292d66db2b64ea71f64b6e1c1` |
| PyYAML | 6.0.3 | setuptools/Cython/libyaml | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` |
| rpds-py | 0.30.0 | maturin/Rust | `dd8ff7cf90014af0c0f787eea34794ebf6415242ee1d6fa91eaba725cc441e84` |
| ruamel.yaml.clib | 0.2.15 | setuptools/Cython | `46e4cc8c43ef6a94885f72512094e482114a8a706d3c555a34ed4b0d20200600` |

The raw 91-package compatibility evidence is retained in
[`audit/emulator-audit.json`](audit/emulator-audit.json), with the exact
resolver output in [`audit/resolved.txt`](audit/resolved.txt).

## Build design

The `Build immutable arm64 wheelhouse` workflow runs on an arm64 Ubuntu runner,
boots an arm64 Android emulator, installs the exact Termux APK, and executes all
builds inside Termux. The builder:

1. verifies the pinned Python `.deb` and every PyPI sdist before extraction;
2. rejects traversal, symlink and device members in source archives;
3. builds serially with pinned setuptools, Cython, pybind11 and maturin versions;
4. patches psutil's Android platform detection;
5. emits or normalizes PEP 738 Android wheel tags;
6. rewrites `WHEEL` and `RECORD` correctly when normalization is required;
7. verifies package/version/tag, ZIP integrity and native extension presence;
8. installs the complete 91-package graph with `--only-binary :all:` in a clean venv;
9. imports every native package and runs `uv pip check`;
10. publishes wheels, `index.json`, and `SHA256SUMS` under a new immutable release tag.

## Run locally in native aarch64 Termux

```bash
git clone https://github.com/adybag14-cyber/termux-hermes.git
cd termux-hermes
bash scripts/termux_build.sh "$PWD"
```

The complete wheelhouse is written to
`~/termux-hermes-build/wheelhouse/`. This build is intentionally resource-heavy;
normal users should consume the published release assets instead.

## Refreshing the lock

Do not edit package versions without rerunning the emulator audit against an
exact Hermes commit. A refresh must update together:

- `audit/resolved.txt`
- `audit/emulator-audit.json`
- `audit/build-metadata.json`
- `manifest/wheels.json`
- this README table

The compatibility audit can be rerun inside Termux with:

```bash
python3.13 scripts/audit_pypi.py \
  --resolved audit/resolved.txt \
  --output audit/refreshed-emulator-audit.json
```

A new wheelhouse must use a new release tag. Existing release assets must never
be replaced.
