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

**Seven of the nine restrictions now have repairs with passing native checks.**
The main candidate covers **uvloop, Matrix, Nemo Relay, local managed browser,
Bot Desktop, and managed gateway service**. Its separate CUA-augmented package
also passes **all eleven standalone and seven packaged-default computer-use
checks**, same-version reinstall, a fresh published-to-candidate upgrade, user
state preservation, optional installation without compilers, and repeated
environment reuse. These computer-use results concern the owned virtual X11
desktop; they do not certify arbitrary Android phone UI control.

NeuTTS's scientific foundation and its native Numba/Llama CPU components now
pass. Its complete engine dependency environment, codec/model behavior and
synthesis remain separate gates. Microphone/VAD still needs a complete isolated
audio preparation and real Android audio services. Source repairs and preparation
for these two remaining restrictions continue below; neither is counted as a
fully repaired feature. The baseline count remains nine.

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
| NeuTTS local speech engine | NeuTTS 1.4.1 declares Python >=3.10,<3.14; the Hermes lock excludes its full group under CPython 3.14.6. Its PyPI release has platform wheels but no sdist; exact public source exists. | Prepare a separate complete, pinned native runtime. Fix the actual Android Llama loader, native build invocation, NeuCodec Hub compatibility and Phonemizer library discovery. Keep the original engine exclusion until complete runtime and synthesis validation support changing it. | All seven scientific-foundation gates pass. [Run 39064666810](../audit/neutts-native-20261017/run-39064666810.json) also builds both exact native wheels and passes installed-input verification, Numba nopython JIT/workqueue operations, and Llama backend initialization/cleanup with verified mapped libraries. NeuCodec and Phonemizer patches pass 34 and 30 focused host tests respectively. The full [117-package/194-edge dependency review](neutts-engine-closure.md) is a metadata witness, not an installable lock. Remaining native runtime, codec and model tests are explicit; no engine or synthesis is certified. |

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
| Default native computer use | The default CUA driver rejects Android; the MCP dependency does not supply a native backend. | The separate CUA-augmented candidate now passes [the complete native workflow](../audit/cua-native-20261017/run-39063611615.json): 11 standalone and 7 registered-Hermes checks with normal bundled PM discovery and omitted delivery mode. Foreground is resolved before approval; absent approvers, explicit background requests and background-only grants are refused. Three once approvals, real image/input oracles, viewer leases, cleanup, reinstall, fresh published-package upgrade and compiler-free optional install/reuse pass. The candidate contains the other six repairs and retains the same package version. Scope is its owned virtual X11 desktop. Android phone UI, AT-SPI trees, encrypted history and parallel uinput/background input remain uncertified. |
| Bot Desktop | Virtual display host is Linux-only. | Added a local Termux Xvnc/Xfce adapter, prefix-aware runtime paths and screenshot capture through scrot. Desktop/remote-provider regressions pass, including real resolver result types. Native ARM UID 1000 validation passed: Xfce, an 800x600 RFB framebuffer, private Xauthority/socket permissions, no TCP display listener, real product screenshot capture and cleanup. |
| Managed gateway service | Service install/start/uninstall paths reject Termux/APT provenance. Manual foreground/background gateway paths remain available. | Added a per-home Termux runit adapter with owned service directories, separate start-now/login policy, graceful stop and crash supervision. Twenty-four gateway tests pass. Native ARM install/start/status/restart/stop/crash-respawn/uninstall checks also passed, including same-basename home isolation and preservation of the shared supervisor. |
| Recorder silence auto-stop | The Termux:API recorder does not provide the sounddevice VAD/silence path. Manual stop remains available. | Added explicit auto, sounddevice and termux-api capture selection with accurate diagnostics. The PCM path retains the existing VAD implementation. Exact NumPy 2.4.3 built and passed native numerical checks with both build and original payload libraries. PortAudio loaded, but measured runtime evidence shows only the Termux OpenSL ES wrapper: the actual Android audio framework, Binder devices and audio services are absent. Engine initialization failed in that environment; microphone/VAD remains unverified. Termux:API itself has no PCM stream for this VAD path. A separate [audio-readiness patch](../patches/next-stable/audio-readiness.patch) catches import-time PortAudio failures and rejects output-only device inventories. The [device guide](audio-readiness-device-validation.md) preserves the remaining physical capture/VAD gate. |

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

The [standalone CUA success record](../audit/cua-native-20261017/run-39052290704.json)
binds its native result to head `3e63be4a65dcb0d6d2c0c2fec86f94546fbba8ed`
and the authenticated Actions artifact. It preserves the exact archive
reconstruction method, the real Xlib observations, the earlier background-input
failure and the still-degraded accessibility result. This proof does not exercise
Hermes' registered tool, action approvals or viewer lease.

The later [real Hermes integration success](../audit/cua-native-20261017/run-39056267366.json)
does exercise the registered tool, standard action approvals, a real viewer lease
and cleanup. It records three distinct once approvals, the requested (80,60)
click/scroll coordinates and 19 exact typed bytes. All 29,809 original candidate
file/symlink entries were unchanged across the experiment. This earlier result used an
explicit driver and explicit foreground input. The later packaged-default gate
below covers normal bundled-driver selection and omitted input delivery mode.

The [complete NeuTTS foundation result](../audit/neutts-native-20261017/run-39058569758.json)
records all seven passing foundation gates, all 2,829 verified installed wheel
files, the exact seven retained APT wheel-tag diagnostics, and successful Python
and APT dependency validation. The validator, collector and wheel preparation
passed 113 focused host tests before that native run. The [engine source review](neutts-default-gguf-feasibility.md)
records the exact Numba, llama, codec, eSpeak and model requirements; the later
CPU result below supersedes its initial native-build-pending checkpoint.

The later [complete packaged CUA result](../audit/cua-native-20261017/run-39063611615.json)
binds the source patch `8bbfddbb...` and head `5cace91...` to the
same-version augmented package with SHA-256
`2b4c01a400622c45cf0f0f7af39fa5cdca4b37e311cebb71cdbacc770aa4f529`.
All 32,515 prepared payload entries remain unchanged during its probes and
reinstall. A fresh runtime-only container installs the exact published baseline,
upgrades to that candidate, verifies all three state fixtures twice, preserves
100 initial distributions, adds the two exact optional dependencies, and reuses
the completed environment. Its 56-member Actions artifact was fully reconstructed
and verified; the earlier [host chmod failure](../audit/cua-native-20261017/run-39062805143.json)
remains recorded.

The [native speech CPU result](../audit/neutts-native-20261017/run-39064666810.json)
at head `954a439...` passes the repeated seven foundation gates and all
three additional component cases. Numba 0.67.0 compiles and executes actual
nopython JIT and workqueue operations. Matching llama-cpp-python 0.3.36 initializes
and frees its native backend, reports the real AUTO load mode and CPU
capabilities, and verifies its loaded libraries. No model is loaded or inference
performed. The [earlier Llama probe failure](../audit/neutts-native-20261017/run-39063611598.json)
and [the exact API correction](../audit/neutts-llama-load-mode-probe-fix-20261017.json)
are preserved.

The [NeuCodec Hub adapter](neucodec-hub1-compatibility.md) and
[Phonemizer dlinfo repair](phonemizer-android-dlinfo-compatibility.md) preserve
their declared dependencies and expose actual errors. Their focused host tests
cover 34 and 30 cases. The [full engine dependency and model audit](neutts-engine-closure.md)
records every declared runtime edge, the unchanged Python upper bound and the
two exact default Neuphonic weight downloads that require authenticated model
access. Public metadata and advertised sizes are not downloaded-weight proof.

The separate [Hermes preparation receipt](../audit/cua-hermes-preparation-20261017.json)
links the [canonical host tests](../audit/cua-hermes-host-tests-20261017.json).
Their first run passed 58 tests with three host-specific skips; the final
readiness run passed 14 tests and repeated seven earlier cases. These are separate
runs, not an aggregate count. The production patch was unchanged between them.
Separate packaging [CI run 39052294622](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39052294622)
passed 209 tests in 1.53 seconds on merge checkout
`e6fd5fcfb260ab72ef77e87f109c51aa69444a34`, for branch head
`3e63be4a65dcb0d6d2c0c2fec86f94546fbba8ed`; the preparation receipt retains
the API identity and exact checkout/test log evidence.

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
