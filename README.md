# Hermes for Termux

This repository packages [Hermes Agent](https://github.com/NousResearch/hermes-agent)
for native **Termux aarch64**. Phones install a prepared Debian package; the C and
Rust dependencies are built and checked on native ARM GitHub Actions runners.

## Install or recover

Run this in Termux:

```bash
curl -fsSL --retry 6 --retry-all-errors https://raw.githubusercontent.com/adybag14-cyber/termux-hermes/main/install.sh | bash
```

The installer checks the signed package repository, downloads the reviewed
immutable package with resumable transfers, verifies its SHA-256, and repairs an
interrupted installation. It preserves `~/.hermes`, migrates existing
configuration, retains the established 8,192-token output cap, and restarts the
gateway. Set `HERMES_RECOVERY_MAX_TOKENS` to choose a different positive cap.

The current package bundles its own Python and native libraries under
`$PREFIX/lib/hermes-agent`. It can coexist with an existing Termux Python 3.13
or 3.14 installation. There is no need to replace the system Python to run Hermes.

For an installation already using the signed repository:

```bash
pkg update
pkg upgrade hermes-agent
```

Hermes remains owned by APT. `hermes update` explains that updates use
`pkg upgrade hermes-agent` and exits with status 2.

## Release target

The reviewed release inputs are in [manifest/release.json](manifest/release.json).

| Item | Target |
| --- | --- |
| Hermes | [v0.22.2](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.2) |
| Exact source | `d923a5eb487a17c0a68801bba9ef0f56c81040a8` |
| Debian package | `hermes-agent_0.22.2-1_aarch64.deb` |
| Architecture | aarch64 / arm64-v8a |
| Python | Bundled Termux CPython 3.14.6 |
| Wheel ABI and platform | `cp314`, `android_24_arm64_v8a` |
| Feature profile | Hermes `termux`: Telegram, cron, MCP and ACP |
| Build userspace | `termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303` |

The v0.22.2 package uses the upstream PM runtime and builds the Node terminal
interface. It includes Python, Node, npm, uv, FFmpeg, ripgrep, runtime shared
libraries, the application source and its native dependency environment.
The Python 3.13 wheelhouse from Hermes 0.20.6 is not used for this release.

The package layout is:

- `lib/hermes-agent/app`: application source and release stamp.
- `lib/hermes-agent/venv`: application dependency environment.
- `lib/hermes-agent/pm-runtime`: isolated package-manager environment.
- `lib/hermes-agent/tools`: bundled tool binaries.
- `lib/hermes-agent/runtime-libs`: the verified native library closure.
- `lib/hermes-agent/bin`: generated launchers; Termux's `bin` directory links to them.

The release stamp records the upstream tag and commit, `apt-termux`
distribution, and external update ownership. The separate package revision
`-1` follows the upstream Termux builder's Debian version format.

## Signed APT repository

Enable the contributor-operated repository once if you prefer to use APT directly:

```bash
curl -fsSL --retry 6 --retry-all-errors https://raw.githubusercontent.com/adybag14-cyber/termux-python/main/scripts/setup_apt_repo.sh | bash
pkg install hermes-agent
```

Repository signing fingerprint:

```text
EAD24A2124EFA7393A78B7B14699F966313F7A6B
```

The existing publisher imports verified, non-prerelease GitHub release assets,
checks their package metadata and GitHub SHA-256 digest, then publishes a signed
APT snapshot. Candidate Actions artifacts do not enter that feed. Published
releases and their assets are immutable.

This is an independent contributor distribution. The application comes from the
identified NousResearch release; the packaging adaptations and validation
evidence are maintained here.

## Build and release

[Build native Hermes Termux package](.github/workflows/build-hermes-package.yml)
uses the exact reviewed source and applies the checked patches in
[patches](patches). The build retains the full Termux feature profile and upgrades
the rolling build container before installing current build tools.

The workflow:

1. Confirms that the stable upstream tag resolves to the exact recorded commit.
2. Provisions the locked host toolchain through upstream PM.
3. Stages digest-verified bionic tools and runtime libraries. Upstream's public,
   content-addressed mirror supplies archived inputs removed from Termux's rolling pool.
4. Exports the frozen upstream dependency graph for the Termux profile.
5. Builds native wheels with the bundled target Python inside the pinned aarch64
   Termux userspace, then performs a complete offline dependency installation and
   native import checks.
6. Builds the terminal UI and assembles the canonical PM-based Debian bundle.
7. Installs the actual package into a fresh pinned container with networking
   disabled and checks CLI, ACP, native extensions, PM integrity, Node/npm,
   ripgrep, FFmpeg and the terminal UI's setup screen.
8. Upgrades a real installation of the previous package with existing Python
   3.13 and user configuration, then checks preserved state and launcher ownership.
9. Records the package and dependency provenance and uploads the
   `hermes-agent-termux-aarch64` candidate artifact.

This workflow creates a candidate without publishing it. Run it manually with:

```bash
gh workflow run build-hermes-package.yml --ref <reviewed-build-branch>
```

After it succeeds, use that candidate's checksum to update `install.sh` together
with the package version and immutable release URL. Review and merge those pins,
the updated live smoke and the release workflow. Then dispatch
[Publish verified Hermes Termux candidate](.github/workflows/publish-hermes-package.yml)
with the successful build's run ID and the new release tag:

```bash
gh workflow run publish-hermes-package.yml --ref main \
  -f build_run_id=<successful-native-run-id> \
  -f release_tag=<new-release-tag>
```

Promotion downloads that exact candidate without rebuilding it. It verifies the
successful run, package identity, upstream pins, checksums and installer pins;
reruns the existing-package upgrade; and tests the checked-in streamed recovery
installer with a real interrupted HTTP transfer. It then creates a draft release,
checks every uploaded asset's GitHub digest and size, and publishes the release.
An existing tag or release is rejected.

Each package release includes:

- `SHA256SUMS`: checksums of the Debian package and attached evidence.
- `BUILD-METADATA.json`: actual package hash, upstream and packaging commits,
  build image, source patch hashes and runtime contract inspection.
- `WHEELHOUSE-MANIFEST.json`: wheel hashes and the complete cache input identity.
- `RESOLVED.txt`: locked versions, target markers and source references.
- `RELEASE-PINS.json`: the reviewed release target.

The separate [live APT smoke](.github/workflows/apt-hermes-smoke.yml) verifies
installation through the signed public repository and interrupted-download
recovery. Release build validation and live APT validation are separate gates.

## Updating the target

Update the exact stable tag and commit together in `manifest/release.json`.
Review upstream runtime, Python ABI, PM and native dependency changes before
building. Refresh and review the build patches against that source. Do not infer
the release version from the upstream development value in `pyproject.toml`;
the verified stable tag and install stamp identify the release.

After a candidate passes the native gates, update the recovery package version,
immutable asset URL and SHA-256 together. The live smoke's expected version,
partial-download fixture and cache names must change with the release. The APT
publisher keeps the newest active package, so old active-pool URLs are not
permanent fixtures; historical packages should use immutable GitHub URLs.

## Historical builds and device evidence

The [Hermes 0.20.6 / CPython 3.13 build documentation](docs/legacy-cp313.md),
`manifest/wheels.json`, and existing `audit/` files describe the earlier
release line. The legacy wheelhouse workflow and scripts remain available to
reproduce that line. They are not evidence for v0.22.2.

The new release's native container validation does not by itself certify a
particular physical phone. Device-specific evidence, when collected, must name
the Android version, Termux app and tested package checksum.
