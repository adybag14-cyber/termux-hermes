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

Six of these restrictions have repairs in the main candidate with passing native
checks: **uvloop, Matrix, Nemo Relay, local managed browser, Bot Desktop, and
managed gateway service**. The separate CUA foreground-X11 experiment now passes
both standalone and real Hermes integration checks; it remains outside that
candidate and requires an explicitly selected external driver. The separate
NeuTTS scientific dependency experiment passes all six native cases, while pip
wheel tagging, the full speech engine and physical microphone/VAD retain their
stated limits. The baseline count remains nine.

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
| Package build commit | `25e82b34c019bcac4127d4519d5498e73de87c1d` |
| Release tag commit | `7c272cfeeb6cbb387d9993acad3130a258b95fdb` |
| Runtime | Bundled CPython 3.14.6; `cp314`; `android_24_arm64_v8a` |
| Explicit selection | `acp`, `cron`, `mcp`, `telegram`, `termux` |
| Installed / Android-admitted distributions | 81 / 81; zero missing; zero version mismatches |
| Native source-build distributions in baseline | 14 |
| Complete resolved export | 95 rows; 14 excluded by target markers |
| Reusable dependency material in package | No `uv-cache/`, `wheelhouse/`, or `.whl` files |
| PM selection receipt | Explicit feature list exists; `tools/facts.json` lacks venv state |

The package build, release tag and subsequent packaging main are distinct commits;
[release identity evidence](../audit/release-boundary-20261017.json) records each
against the unchanged published asset.

The package's `pyproject.toml` and `uv.lock` match this upstream release.
The released adapters change packaging/build behavior. The census compares
optional dependencies and platform gates with the installed package metadata,
`RESOLVED.txt`, feature facts, and runtime source guards. The machine-readable
result is [compatibility-0.22.2-1.json](../audit/compatibility-0.22.2-1.json).

### Reproduce the package census

[released-package-census.json](../audit/released-package-census.json) contains the
complete observed inventory, all 55 optional group declarations and their target
markers, the admitted/excluded resolved rows, source digests and PM facts. Generate
it from the published package and its RESOLVED.txt:

```sh
python scripts/audit_release_compatibility.py \
  --package /path/to/hermes-agent_0.22.2-1_aarch64.deb \
  --resolved /path/to/RESOLVED.txt \
  --output /tmp/hermes-release-census.json
```

The inspector verifies the exact package SHA-256 before streaming its archive.
It installs nothing and executes no package code. The recorded source digests
also match the exact upstream commit. Capability classification remains a
source-reviewed judgment, distinct from distribution inventory.

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
| uvloop event-loop acceleration | Android marker excludes uvloop 0.22.1. Its setup backend runs shell/configure commands assuming a conventional Unix shell path; the old preconfigure workaround is overwritten by setup.py's later copy/configure sequence. Standard asyncio remains available. | Verify the exact locked source archive, patch the commands actually executed to use Termux's `CONFIG_SHELL`, and admit Android aarch64. Supply the resulting wheel through the reusable bundle cache. | Corrected native ARM TCP/task/shutdown job passed in run 39039959324, including original-payload runtime and successful artifact capture. |
| Matrix messaging with encryption | Five requirements and the PM extra gate admit Linux only. The encrypted backend's python-olm 3.2.16 builds an older vendored libolm with CMake compatibility assumptions and an incorrectly const-qualified pointer rejected by current Clang. | Preserve bundled static libolm, apply Termux's CMake policy and const-pointer corrections, and admit Android aarch64 for the complete encrypted dependency group. Bundle reusable native wheels. | Native ARM Olm/Megolm, AES, asyncpg codec, HTTP and SQLite probes passed with original payload libraries; no undeclared runtime libraries. |
| Nemo Relay | Core platform marker excludes Android. The 0.10.0 Rust source unconditionally requests a vendored protoc binary whose platform table lacks Android, ignoring the available system `PROTOC`. The old builder also silently skipped Nemo if it reached the build list. | Verify the locked sdist, honor the system protoc executable, remove the silent omission paths, and require Nemo in completeness checks. | Android Rust build, native plugin validation and scope/trace behavior passed in run 39039959324, including original-payload execution and successful artifact capture. |
| NeuTTS local speech engine | The declared NeuTTS 1.4.1 pin requires Python >=3.10 and <3.14; its full dependency group is excluded from the current resolved lock. Its published release has platform wheels but **no source distribution**; the closure also needs native Torch/Torchaudio, codec and inference libraries. This package uses Python 3.14.6 on Bionic. | Retain the honest exclusion. Public upstream source exists, but enabling this engine requires a supported Python/runtime arrangement plus the complete native Torch, codec and inference closure. No speculative marker-only enablement is made. | Exact PyPI/source requirements remain incompatible with managed Python 3.14.6. The separate [native scientific probe](../audit/neutts-native-20261017/run-39055874446.json) now passes all six Torch, Torchaudio, TorchCodec, SciPy, llvmlite and Soxr behavior cases with all 122 pinned APT archives and exact supplemental Python dependencies. Pip still rejects seven original APT WHEEL tags; that failure is explicitly retained. This does not install or admit NeuTTS, provide its complete engine closure, or certify synthesis. See [remaining portability work](remaining-portability-work.md#neutts-141). |

The uvloop, Olm and Nemo adapters reject unexpected source bytes or changed build
hooks. They do not bypass checksums or substitute unpinned upstream branches.
Only Android **aarch64** is newly admitted; other existing platform restrictions
remain unchanged. The proposed lock was regenerated through Hermes PM; package
versions did not change.

Primary dependency evidence: [uvloop 0.22.1 metadata](https://pypi.org/pypi/uvloop/0.22.1/json),
[python-olm 3.2.16 metadata](https://pypi.org/pypi/python-olm/3.2.16/json),
[Nemo Relay 0.10.0 metadata](https://pypi.org/pypi/nemo-relay/0.10.0/json),
[NeuTTS 1.4.1 metadata](https://pypi.org/pypi/neutts/1.4.1/json), and
[Termux libolm recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/libolm/build.sh).
The reviewed exact source digests are also embedded in the preparation helpers.

## Five additional runtime restrictions

| Capability | Published behavior | Preparation status |
| --- | --- | --- |
| Local managed browser | PM has no Bionic artifact for either AgentBrowser or Chromium. Remote browser/CDP paths are distinct and can remain usable. | Fixed and passed native ARM validation under UID 1000: raw static driver, real PM installation/discovery, built-in browser tools, and the default `browser_exec` handler with the backend unset. Navigation, exact loopback URL/heading, DOM interaction, PNG screenshot and product cleanup all passed. Product PM/discovery integration also passed 139 regression tests. Chromium remains an explicitly APT-owned dependency. See the [final browser evidence](../audit/native-probes-e20e8c4-20261017/browser-summary.json). |
| Default native computer use | Default CUA driver rejects Android. Having the MCP dependency does not supply this native backend. | Fixed the separate remote Linux provider routing bug. The isolated native CUA driver passed all eleven foreground-X11 checks in [run 39052290704](../audit/cua-native-20261017/run-39052290704.json): real MCP registration, independent screenshot/input/clipboard/geometry oracles, native ABI checks and cleanup. Default background input and AT-SPI trees remain uncertified. The [explicit-driver Hermes integration](../audit/cua-hermes-resume-20261017/run-39056472835.json) now passes native manifest discovery before desktop startup, the real registered tool, exact screenshot/click/scroll/text observations, three individual approvals, viewer-lease refusal and owned cleanup. The lost scroll coordinates and pre-desktop native loader are fixed. The driver and experimental adapter remain outside the main candidate and PM admission. Android phone UI requires an Android-specific backend. |
| Bot Desktop | Virtual display host is Linux-only. | Added a local Termux Xvnc/Xfce adapter, prefix-aware runtime paths and screenshot capture through scrot. Desktop/remote-provider regressions pass, including real resolver result types. Native ARM UID 1000 validation passed: Xfce, an 800x600 RFB framebuffer, private Xauthority/socket permissions, no TCP display listener, real product screenshot capture and cleanup. |
| Managed gateway service | Service install/start/uninstall paths reject Termux/APT provenance. Manual foreground/background gateway paths remain available. | Added a per-home Termux runit adapter with owned service directories, separate start-now/login policy, graceful stop and crash supervision. Twenty-four gateway tests pass. Native ARM install/start/status/restart/stop/crash-respawn/uninstall checks also passed, including same-basename home isolation and preservation of the shared supervisor. |
| Recorder silence auto-stop | The Termux:API recorder does not provide the sounddevice VAD/silence path. Manual stop remains available. | Added explicit auto, sounddevice and termux-api capture selection with accurate diagnostics. The PCM path retains the existing VAD implementation. Exact NumPy 2.4.3 built and passed native numerical checks with both build and original payload libraries. PortAudio loaded, but measured runtime evidence shows only the Termux OpenSL ES wrapper: the actual Android audio framework, Binder devices and audio services are absent. Engine initialization failed in that environment; microphone/VAD remains unverified. Termux:API itself has no PCM stream for this VAD path. A [separate readiness repair](audio-readiness-device-validation.md) has host contract proof for PortAudio failures and output-only device inventories. It remains outside the candidate, which does not select audio-io; a complete isolated audio environment is still required before device testing. |

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

The preparation now includes a reusable wheel catalog owned by PM. Reuse binds
the exact wheel hash, package version, and original registry/Git source identity.
A changed lock source must never reuse an unrelated wheel with the same version.
The frozen current selection determines which wheels apply; optional SDKs still
use the ordinary resolver and their exact lock entries. A real isolated-index regression proves that an intentionally unbuildable source dependency can be preserved from its verified wheel while an additional SDK installs with an empty cache.

The proposed packaging recipe includes a wheelhouse and generates a native
selection receipt during assembly. The receipt binds the actual Android target, seven selected extras, frozen input
hashes and catalog digest. The PM environment stamp includes that digest, so
corrected wheel bytes invalidate an older optional environment even when upstream
versions stay the same. Receipt, stamp and existing baked-selection tests pass
(22 tests). The complete candidate also passed native package assembly, fresh
offline install/reinstall, the terminal UI, CLI/tool checks, and actual replacement
of the published package while preserving configuration, session and profile
fixtures. Its optional-install check preserved all 100 initial candidate
distributions, then added exactly anthropic 0.87.0 and docstring-parser 0.18.0 with
an empty cache and no native build toolchain. Lock and wheel bytes stayed
unchanged; a repeated request reused the completed environment.

The [successful lifecycle evidence](../audit/candidate-lifecycle-e271e92-20261017/summary.json)
binds these results to exact source, package and workflow identities in
[run 39048514731](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39048514731).
The target wheelhouse contains 100 wheels, including pure-Python wheels.
The same-version package remains an Actions validation artifact. A separate
[inventory comparison](../audit/candidate-lifecycle-e271e92-20261017/release-to-candidate-inventory.json)
confirms all 81 published distributions remain at identical versions. The
candidate's 19 additional distribution records include the application's own
metadata record; they are not 19 additional user-facing features.

[Two initial assembly failures](../audit/candidate-assembly-20261017/summary.json)
identified a host script running outside PM's locked environment. The corrected
entry point now uses the existing PM runtime and preserves child failure status;
three focused assembly/handoff regressions passed. The source-side wheel-cache
verifier retained every input and content check during cache reuse.

The explicit capture-backend changes passed 101 voice-related tests, with 31
existing Linux/macOS cases skipped on the Windows host. This includes all 14 new
selector and diagnostic tests; it does not certify Android microphone hardware.

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

## Remaining native runtime work

[Remaining portability work](remaining-portability-work.md) records the verified
NeuTTS Python/native-ML mismatch, the distinction between remote/virtual desktop
support and a native Android phone UI driver, and the real OpenSL ES requirement
for microphone capture. These are explicit certification limits, not claims
that Android ports are impossible.

## Validation and release boundary

The [native Hermes integration record](../audit/cua-hermes-resume-20261017/run-39056472835.json)
binds the successful standalone and registered-tool results to exact head
`37bf89d09a2a68a41585389d59b19e5e583c1f23` and a fully SHA-256/CRC-verified
Actions artifact. The independent Xlib log confirms the requested coordinates
and text. Missing/consumed approvals and viewer takeover correctly block actions;
the installed candidate payload remains unchanged. The current patch is still
an external-driver experiment, separate from the main candidate.

The [native scientific result](../audit/neutts-native-20261017/run-39055874446.json)
records all six NeuTTS-adjacent dependency cases passing at
`d439e8100bc89dbfe681fc03aa22017f175b8b2d`. Its dependency closure passed,
while the original APT wheel tags still fail pip compatibility. The engine,
model loading and synthesis were not exercised.

The final source validation comprises
[73 loader tests with three host skips](../audit/cua-hermes-resume-20261017/host-tests.json),
a separate [31-test focused scroll run](../audit/cua-hermes-resume-20261017/scroll-source-tests.json),
and [eight passing scoped lint checks](../audit/cua-hermes-resume-20261017/scoped-lint.json).
Counts are not aggregated. Three broader Windows fixture failures reproduced
before both fixes; the detailed source record preserves them.

The [full component revalidation](../audit/native-probes-635ec13-20261017/summary.json)
at `635ec13c9d0f264f508d1bdbaa7670d4eaa00787` completed with **six passing lanes
and one failed audio lane**. The overall workflow conclusion is **failure**.
uvloop, Matrix, Nemo, browser, Bot Desktop and the runit gateway lifecycle pass
their native behavior checks. Audio again passes NumPy's four numerical cases
in both runtime contexts and loads PortAudio, but initialization fails with
`PaErrorCode -9999`. The actual Android OpenSL ES framework, Binder nodes and
audio services are absent; microphone capture was not tested. All seven
artifact archives were downloaded in full and verified by SHA-256, ZIP CRC and
member hashes. The failed job's complete original log is retained too.

The [implementation-commit CI](../audit/resume-ci-635ec13-20261017.json)
passed **291 tests** with no failures or skips in each of the separate push and
pull-request runs at `635ec13c9d0f264f508d1bdbaa7670d4eaa00787`. Compile, shell
syntax and JSON validation passed too. The [earlier combined CI](../audit/resume-ci-3414585-20261017.json)
and its separate Windows host run remain recorded at `3414585`; that host run
passed 287 tests with four host-specific skips. The [merge receipt](../audit/resume-integration-20261017.json)
records preserved concurrent preparation work and confirms that native-tested
inputs remain byte-identical. The earlier
[standalone](../audit/cua-native-20261017/run-39052290704.json) and
[host preparation](../audit/cua-hermes-host-tests-20261017.json) evidence remains
available with its original source bindings.

[Probe next-stable Termux compatibility](../.github/workflows/compatibility-probes.yml)
runs seven native ARM lanes against the immutable released package and the proposed
source patch. It has read-only repository permissions and uploads candidate
diagnostics/wheels only. It does not construct or publish a new release.

The probes check locked dependency closure, hashed sources, offline wheel
installation, meaningful native behavior, ELF runtime linkage, and a second
behavior pass using the original payload library path. Build-tool libraries must
not accidentally conceal a missing package runtime dependency.

Passing a component probe is recorded as **candidate-built**. The complete
package and optional-install lifecycle passed their separate native validation
gate. External account pairing and physical device permissions remain separate
checks; the container results do not certify those Android device paths.

The additional [gateway evidence](../audit/native-probes-4b3d121-20261017/gateway-summary.json) and
[audio evidence](../audit/native-probes-9fcd31c-20261017/audio-summary.json) bind their results to
their exact tested commits and candidate patch. Audio retains its failed PortAudio
admission while proving native NumPy and measuring the missing Android framework.
Its actual mapped OpenSL ES object belongs to libandroid-stub; the corresponding
real system library and audio/Binder services are absent.

The captured [native probe evidence](../audit/native-probes-20261017/summary.json)
binds the tested patch digest to GitHub run and artifact identities. Matrix checks
include encrypted bidirectional Olm messaging, Megolm, AES, native asyncpg codec,
loopback HTTP and SQLite. No external Matrix account or credential is needed for
these protocol/library checks; live account pairing remains a separate step.

[Validate next-stable Termux candidate](../.github/workflows/next-stable-candidate.yml)
also builds a disposable candidate package as an Actions artifact. It keeps the
existing version for upgrade testing and has no release or APT publication steps.
Its package is deliberately separate from the release-promotion artifact.

Native workflows select checks from the exact previous PR head when reliable
ancestry is available. Changes to source patches, pins, build helpers or lifecycle
checks require the corresponding native validation; unknown or replaced history
runs the full set. Documentation-only updates avoid rebuilding identical inputs.
Planner and worker checkouts use the same PR head. Standard CI still runs on each
push and pull request.

The changes live in [patches/next-stable/compatibility.patch](../patches/next-stable/compatibility.patch),
applied after the four released v0.22.2 packaging patches. The normal release
workflow selects only the existing top-level patches, so this preparation cannot
silently change the current release recipe. Future stable promotion must be
explicitly reviewed and authorized.
