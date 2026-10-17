# Compatibility audit: Hermes Termux 0.22.2-1

Audit date: **17 October 2026**. This document describes the actual published
`hermes-agent_0.22.2-1_aarch64.deb` and the preparation work for a future stable
release. **This branch does not publish a release, change the version, or change
the public installer pins.** Candidate results below are updated as evidence arrives.

## What is disabled?

There are **four explicitly excluded dependency groups** in this release:
**uvloop, Matrix, NeuTTS, and Nemo Relay**. A separate runtime audit identifies
**five more restricted product capabilities**: local managed browser, default
native computer use, Bot Desktop, managed gateway service integration, and
microphone silence auto-stop. That is **nine named capability restrictions** under
the counting rule below.

The audit also found three broken Android adapter paths (text clipboard, audio
playback, and microphone maximum duration), and a missing native dependency cache
that affects later optional-feature installation. These are tracked as defects,
rather than inflating the count of explicitly disabled features.

The package selects a small `termux` dependency profile. An unselected optional
SDK is **not evidence of Android incompatibility**. All **81 Android-admitted
locked application distributions are installed at their exact versions**: there
is no missing package within the selected release graph. The exclusion happens
before that graph is installed.

## Exact baseline and evidence

| Input | Audited value |
| --- | --- |
| Published package | [hermes-agent_0.22.2-1_aarch64.deb](https://github.com/adybag14-cyber/termux-hermes/releases/download/hermes-agent-termux-0.22.2-20261016.1/hermes-agent_0.22.2-1_aarch64.deb) |
| Package SHA-256 | `deb163351554ca03f7104f91a50f4f8dc4d9247ce0cf5f2cca2608be3b319add` |
| Upstream release | [v0.22.2](https://github.com/NousResearch/hermes-agent/tree/d923a5eb487a17c0a68801bba9ef0f56c81040a8) |
| Exact upstream commit | `d923a5eb487a17c0a68801bba9ef0f56c81040a8` |
| Packaging main baseline | `91e096aec63aafd55700675e07148285522dcc70` |
| Runtime | Bundled CPython 3.14.6; `cp314`; `android_24_arm64_v8a` |
| Explicit selection | `acp`, `cron`, `mcp`, `telegram`, `termux` |
| Installed / Android-admitted distributions | 81 / 81; zero missing; zero version mismatches |
| Native source-build distributions in baseline | 14 |
| Complete resolved export | 95 rows; 14 excluded by target markers |
| Reusable dependency material in package | No `uv-cache/`, `wheelhouse/`, or `.whl` files |
| PM selection receipt | Explicit feature list exists; `tools/facts.json` lacks venv state |

The package's `pyproject.toml` and `uv.lock` match this upstream release.
The released adapters change packaging/build behavior. The census compares
optional dependencies and platform gates with the installed package metadata,
`RESOLVED.txt`, feature facts, and runtime source guards. The machine-readable
result is [compatibility-0.22.2-1.json](../audit/compatibility-0.22.2-1.json).

### Counting rules

- Count a named capability once, even when multiple packages block it.
  AgentBrowser and Chromium together block one local managed-browser capability.
- The `computer-use` extra contains an MCP client; the missing native CUA backend
  is the same computer-use restriction, not another feature.
- Aggregate extras such as `all`, `voice`, and `termux-all` are aliases.
- A smaller default bundle, an opt-in engine, or a touch-friendly TUI default
  does not itself disable a feature.
- Importability is weaker evidence than complete backend behavior. Native
  container success is weaker evidence than microphone, clipboard, and display
  behavior on a physical Android device.

## Four dependency exclusions

| Capability | Released restriction and actual cause | Proposed next-stable remedy | Current evidence |
| --- | --- | --- | --- |
| uvloop event-loop acceleration | Android marker excludes uvloop 0.22.1. Its setup backend runs shell/configure commands assuming a conventional Unix shell path; the old preconfigure workaround is overwritten by setup.py's later copy/configure sequence. Standard asyncio remains available. | Verify the exact locked source archive, patch the commands actually executed to use Termux's `CONFIG_SHELL`, and admit Android aarch64. Supply the resulting wheel through the reusable bundle cache. | Source-hook behavioral tests pass; native ARM TCP/task/shutdown probe pending. |
| Matrix messaging with encryption | Five requirements and the PM extra gate admit Linux only. The encrypted backend's python-olm 3.2.16 builds an older vendored libolm with CMake compatibility assumptions. | Preserve bundled static libolm, set the CMake compatibility policy as in Termux's libolm recipe, and admit Android aarch64 for the complete encrypted dependency group. Bundle reusable native wheels. | Source-hook and closure tests pass; native Olm/Megolm, AES, asyncpg, HTTP and SQLite probes pending. |
| Nemo Relay | Core platform marker excludes Android. The 0.10.0 Rust source unconditionally requests a vendored protoc binary whose platform table lacks Android, ignoring the available system `PROTOC`. The old builder also silently skipped Nemo if it reached the build list. | Verify the locked sdist, honor the system protoc executable, remove the silent omission paths, and require Nemo in completeness checks. | Source preparation and missing-wheel regression pass; inspected native API smoke passes on Windows; Android Rust/native probe pending. |
| NeuTTS local speech engine | Locked NeuTTS 1.4.1 requires Python >=3.10 and <3.14. Its published release has platform wheels but **no source distribution**; the closure also needs native Torch/Torchaudio, codec and inference libraries. This package uses Python 3.14.6 on Bionic. | Retain the honest exclusion. A compatible upstream build/source release and complete Android native dependency closure, or a separately managed supported runtime, is needed before enabling it. | Exact PyPI release metadata inspected; merely removing the Python marker cannot produce a compatible engine. |

The uvloop, Olm and Nemo adapters reject unexpected source bytes or changed build
hooks. They do not bypass checksums or substitute unpinned upstream branches.
Only Android **aarch64** is newly admitted; other existing platform restrictions
remain unchanged. The proposed lock was regenerated through Hermes PM; package
versions did not change.

Primary dependency evidence: [uvloop 0.22.1 metadata](https://pypi.org/pypi/uvloop/0.22.1/json),
[python-olm 3.2.16 metadata](https://pypi.org/pypi/python-olm/3.2.16/json),
[Nemo Relay 0.10.0 metadata](https://pypi.org/pypi/nemo-relay/0.10.0/json),
[NeuTTS 1.4.1 metadata](https://pypi.org/pypi/neutts/1.4.1/json), and
[Termux libolm recipe](https://github.com/termux/termux-packages/blob/master/packages/libolm/build.sh).
The reviewed exact source digests are also embedded in the preparation helpers.

## Five additional runtime restrictions

| Capability | Published behavior | Preparation status |
| --- | --- | --- |
| Local managed browser | PM has no Bionic artifact for either AgentBrowser or Chromium. Remote browser/CDP paths are distinct and can remain usable. | Probe the locked static musl ARM64 AgentBrowser executable with official Termux Chromium, including real navigation, interaction, and screenshot. Do not declare Chromium managed until its binary/library closure is accounted for. |
| Default native computer use | Default CUA driver rejects Android. Having the MCP dependency does not supply this native backend. | Inspect the driver and display/input requirements before proposing a bounded Android port. |
| Bot Desktop | Virtual display host is Linux-only. | Inspect its window-system and process requirements. A remote Linux desktop is a different backend from a local Android desktop. |
| Managed gateway service | Service install/start/uninstall paths reject Termux/APT provenance. Manual foreground/background gateway paths remain available. | Investigate a Termux runit adapter with native service lifecycle semantics. |
| Recorder silence auto-stop | The Termux:API recorder does not provide the sounddevice VAD/silence path. Manual stop remains available. | Investigate the recorder API limitations. Maximum duration is a separate defect and has a tested fix below. |

Source guards: upstream [pm/packages.py](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/pm/packages.py),
[CUA backend](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/computer_use/cua_backend.py),
[Bot Desktop runtime](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/bot_desktop/runtime.py),
[gateway lifecycle](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/hermes_cli/gateway.py),
and [voice mode](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/voice_mode.py).

## Defects fixed or being repaired

### Android clipboard, playback, and recording duration

The proposed Python and terminal UI clipboard adapters use Termux:API's text
clipboard commands when available. Existing terminal escape/manual fallbacks
remain usable.

The Android playback adapter handles `termux-media-player` as an asynchronous
player: it waits for completion, supports interruption/stop, and handles errors.
Stopping this player does not accidentally request installation of the optional
`audio-io` dependency group.

The recorder now passes the requested maximum duration to Termux:API and also
uses a cancellable deadline callback while preserving the active Hermes context.
This does not pretend to implement silence-based VAD.

Focused verification: **32 Python tests** and **25 terminal UI clipboard tests**
passed, including existing recording-limit and playback environment behavior.
Real clipboard permission, microphone permission, audio focus, and speaker
behavior still require a physical device.

### Optional-feature installation with an empty cache

The release includes the already-installed native packages, but no reusable wheel
cache and no PM venv-state receipt. Adding a small pure-Python SDK can make PM
construct a new environment and rebuild the whole native core graph on the phone.
The Termux source adaptations run during packaging; normal lazy PM installation
does not automatically apply those adaptations.

The preparation is adding a reusable wheel catalog owned by PM. Reuse must bind
the exact wheel hash, package version, and original registry/Git source identity.
A changed lock source must never reuse an unrelated wheel with the same version.
The frozen current selection determines which wheels apply; optional SDKs still
use the ordinary resolver and their exact lock entries. A cold-cache regression
must prove that the core native wheels survive installing an additional feature.

This also provides the installation path for the proposed uvloop and Matrix
wheels. Removing their platform markers without shipping reusable native wheels
would expose the same failing source-build path on the phone.

## Complete census of all 55 optional groups

| Category | Count | Groups |
| --- | ---: | --- |
| Explicitly selected | 5 | acp, cron, mcp, telegram, termux |
| Dependencies already supplied by core | 4 | doc-extract, pty, vision, web |
| Partial: client present, default native backend unavailable | 1 | computer-use |
| Unselected aggregate aliases | 5 | all, termux-all, messaging, voice, wake |
| Explicit compatibility exclusions | 4 | uvloop, matrix, neutts, nemo-relay |
| Deliberately opt-in even on supported desktop platforms | 1 | kittentts |
| Other unselected SDK/engine groups; absence does not prove incompatibility | 35 | anthropic, audio-io, azure-identity, bedrock, daytona, ddgs, dingtalk, discord, edge-tts, exa, fal, feishu, firecrawl, google, google-chat, google-meet, mistral, modal, otlp, parallel-web, piper, silk, slack, sms, stt-whisper, teams, trace-upload, tts-premium, vercel, vertex, wake-openwakeword, wake-porcupine, wake-sherpa, wecom, youtube |
| **Total** | **55** | Each name occurs once. |

The 35 unselected groups are not all certified for native Android by this census.
Several contain substantial audio/ML dependencies and need their own target
builds when selected. Hermes' broad aliases are not reliable proof of full feature
installation: for example, the messaging anchor can be satisfied by Telegram
without Slack or Discord, and the computer-use anchor can be satisfied by MCP
without a CUA driver. The explicit selected-extra receipt is authoritative.

## Other omissions and platform choices

The package does not ship a built web dashboard asset directory or an Electron
desktop runtime. These are front-end packaging omissions, not evidence that
FastAPI, the HTTP gateway, image processing, document extraction, or PTY support
are absent. Those core dependencies are present.

The terminal UI is built and enabled. Mouse mode off, inline terminal buffer,
ASCII prompt/narrow layout behavior, and fast echo off are terminal/touch defaults
rather than removed features. Deferred prefetch avoids provisioning unsupported
native tools at startup. APT owns application updates, so `hermes update`
correctly delegates to `pkg upgrade hermes-agent`. Docker-dependent local
execution still needs a host that supports Docker.

## Validation and release boundary

[Probe next-stable Termux compatibility](../.github/workflows/compatibility-probes.yml)
runs four native ARM lanes against the immutable released package and the proposed
source patch. It has read-only repository permissions and uploads candidate
diagnostics/wheels only. It does not construct or publish a new release.

The probes check locked dependency closure, hashed sources, offline wheel
installation, meaningful native behavior, ELF runtime linkage, and a second
behavior pass using the original payload library path. Build-tool libraries must
not accidentally conceal a missing package runtime dependency.

Passing a component probe is recorded as **candidate-built**. It does not certify
the complete next-stable package, optional-install lifecycle, external account
credentials, or physical device permissions. Those are separate validation gates.

The changes live in [patches/next-stable/compatibility.patch](../patches/next-stable/compatibility.patch),
applied after the four released v0.22.2 packaging patches. The normal release
workflow selects only the existing top-level patches, so this preparation cannot
silently change the current release recipe. Future stable promotion must be
explicitly reviewed and authorized.
