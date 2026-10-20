# Compatibility audit: Hermes Termux 0.22.2-1

Published-package census: **17 October 2026**. Preparation checkpoint: **20 October 2026**. This document describes the actual published
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

**Seven of the nine restrictions now have repairs with passing native checks in unpublished preparation candidates. The published package remains unchanged.**
The main candidate covers **uvloop, Matrix, Nemo Relay, local managed browser,
Bot Desktop, and managed gateway service**. Its separate CUA-augmented package
also passes **all eleven standalone and seven packaged-default computer-use
checks**, same-version reinstall, a fresh published-to-candidate upgrade, user
state preservation, optional installation without compilers, and repeated
environment reuse. These computer-use results concern the owned foreground virtual X11
desktop; they do not certify arbitrary Android phone UI control.

NeuTTS's scientific foundation, Numba/Llama CPU, complete eSpeak/Phonemizer,
TorchAO NF4, five APT extensions and six C/C++ dependency components now have
native successes. The engine wheel and bundled C ABI also pass, along with
standalone XXHash. The complete 25-package Tokenizers runtime now has independently
verified native success. Tiktoken's seven-package runtime and the locked Rust
build/base operations also have independently reviewed native evidence, as does
Perth's complete 43-package public watermark runtime. Its measured synthetic-signal
API behavior carries no watermark-quality claim. **The corrected 116-package
combined run 39458842068 at 2d4408f passes all eleven operation groups and final
integrity, library and network checks.** Its [complete artifact/source review](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/NATIVE-SUCCESS-REVIEW.json)
also passes. The three preceding failures remain documented
below. Engine admission, default initialization and synthesis remain unproved. Full Hermes
audio preparation now passes at two fresh paths,
each with 101 application distributions and 6,906 owned files. Physical microphone
capture and silence/VAD auto-stop still need a real Android device. These are
the two remaining complete feature gates; the baseline count remains nine.

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
| NeuTTS local speech engine | NeuTTS 1.4.1 declares Python >=3.10,<3.14; the Hermes lock excludes its full group under CPython 3.14.6. Its PyPI release has platform wheels but no sdist; exact public source exists. | Prepare a separate complete, pinned native runtime. Fix the actual Android Llama loader, native build invocation, NeuCodec Hub compatibility and Phonemizer library discovery. Keep the original engine exclusion until complete runtime and synthesis validation support changing it. | The scientific foundation, CPU, Phonemizer, APT extensions, engine wheel/C ABI and XXHash pass their separate native gates. The complete 25-package/29-edge Tokenizers and seven-package/six-edge Tiktoken runtimes are independently verified, alongside Rust builds and actual HF-Xet/Safetensors/TLS operations. Perth's complete 43/50 public-watermark runtime also passes independent review, within its explicit API-only quality limit. The original 116-dependency/183-edge environment now passes all eleven actual operation groups and final inventory/RECORD, mapped-library and disconnected-network checks in run 39458842068; independent whole-artifact/source review also passes. Original NeuTTS Python bounds remain unchanged; no engine or synthesis is certified. |

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
| Default native computer use | The default CUA driver rejects Android; the MCP dependency does not supply a native backend. | The separate CUA-augmented candidate now passes [the complete native workflow](../audit/cua-native-20261017/run-39063611615.json): 11 standalone and 7 registered-Hermes checks with normal bundled PM discovery and omitted delivery mode. Foreground is resolved before approval; absent approvers, explicit background requests and background-only grants are refused. Three once approvals, real image/input oracles, viewer leases, cleanup, reinstall, fresh published-package upgrade and compiler-free optional install/reuse pass. The candidate contains the other six repairs and retains the same package version. Scope is its owned foreground virtual X11 desktop. Android phone UI, AT-SPI trees, encrypted history and parallel uinput/background input remain uncertified. |
| Bot Desktop | Virtual display host is Linux-only. | Added a local Termux Xvnc/Xfce adapter, prefix-aware runtime paths and screenshot capture through scrot. Desktop/remote-provider regressions pass, including real resolver result types. Native ARM UID 1000 validation passed: Xfce, an 800x600 RFB framebuffer, private Xauthority/socket permissions, no TCP display listener, real product screenshot capture and cleanup. |
| Managed gateway service | Service install/start/uninstall paths reject Termux/APT provenance. Manual foreground/background gateway paths remain available. | Added a per-home Termux runit adapter with owned service directories, separate start-now/login policy, graceful stop and crash supervision. Twenty-four gateway tests pass. Native ARM install/start/status/restart/stop/crash-respawn/uninstall checks also passed, including same-basename home isolation and preservation of the shared supervisor. |
| Recorder silence auto-stop | The Termux:API recorder does not provide the sounddevice VAD/silence path. Manual stop remains available. | Added explicit auto, sounddevice and termux-api capture selection with accurate diagnostics. The PCM path retains the existing VAD implementation. The full [two-path Hermes audio preparation](../audit/audio-hermes-native-20261018/run-39084612542.json) now passes canonical dependency, payload, CFFI and NumPy checks. PortAudio initialization remains unavailable alongside eight absent measured Android framework/Binder paths; no stream was started, and physical microphone/VAD remains unverified. Termux:API itself has no PCM stream for this VAD path. A separate [audio-readiness patch](../patches/next-stable/audio-readiness.patch) catches import-time PortAudio failures and rejects output-only device inventories. The [device guide](audio-readiness-device-validation.md) preserves the remaining physical capture/VAD gate. |

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

### Current native component checkpoint (20 October 2026)

The result remains **9 published restrictions / 7 repairs with native
preparation evidence / 2 incomplete features**. The new successes establish more
of NeuTTS's original dependency runtime. Complete engine admission and physical
microphone/VAD are still separate, unfinished feature gates.

**Current combined gate:** [run 39458842068](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39458842068)
at **2d4408f** passes all eleven actual operation groups, the original
116-distribution/183-edge closure and final inventory/RECORD, native-library
ownership and disconnected-network checks. Its child receipt has been
independently verified against the [complete artifact and source review](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/NATIVE-SUCCESS-REVIEW.json).
Engine import, default initialization and complete model/synthesis behavior
remain unmeasured under the unchanged Python bound. The three failed attempts
below are historical results.

#### Native results and evidence strength

| Exact native gate | Result and practical meaning | Evidence and limit |
| --- | --- | --- |
| [Tokenizers runtime, 39447721557](../audit/neutts-tokenizers-runtime-native-20261020/run-39447721557/REVIEW.json) | The complete original **25-distribution/29-edge** environment passes. WordPiece IDs, Unicode offsets, serialization, BPE training and batches, local HTTP/YAML/Hub behavior, HF-Xet hashing and Safetensors TensorSpec/corrupt-input checks all run successfully. | Whole artifact and all 247 members independently checked. All 25 wheels, 775 inner members, 750 original RECORD payload hashes and 44 loaded APT library byte comparisons pass. The 825-file installed inventory is identical before/after; isolated pip check exits zero. |
| [Tiktoken runtime, 39446824110](../audit/neutts-tiktoken-native-20261020/run-39446824110/NATIVE-REVIEW.json) | The original Tiktoken/Regex backend builds and complete **seven-distribution/six-edge** environment pass. Six literal CoreBPE vectors, Unicode, batch, binary-token and special-token APIs exercise the real native extension. | All 2,280 artifact members, both native wheel RECORDs/original metadata, 80 source inputs and 39 mapped APT library bytes independently checked. The 151-file inventory is unchanged; no vocabulary or speech model is downloaded. |
| [Public Perth runtime, 39446824120](../audit/neutts-perth-native-20261020/run-39446824120/NATIVE-REVIEW.json) | The complete **43-distribution/50-edge** runtime passes with the original bundled public checkpoint. Real watermark apply/decode and SoundFile FLOAT-WAV roundtrips execute at 24/32 kHz; auxiliary native/JIT operations pass. | All 274 artifact members and 52 source inputs independently checked; 19,937 installed files are unchanged. Native ownership verifies 162 extension and 148 APT library mappings. Low detection confidences and zero rounded detections remain explicit; these synthetic-signal checks do not certify watermark quality. |
| [Rust builds/base operations, 39446837699](../audit/neutts-rust-native-20261020/run-39446837699/REVIEW.json) | Four original native wheels build. The exact two-distribution HF-Xet/Safetensors runtime passes real file hashing, TensorSpec serialization and three corrupt-input checks. Actual HF TLS accepts the trusted fixture and rejects an unknown CA and wrong host before HTTP. | Whole 765,103,959-byte artifact/all 47,629 members and the 53-member small handoff checked. Original metadata, 55 wheel RECORD payloads, 35 source inputs and 34 mapped APT libraries verified; all 24 installed files are unchanged. Tokenizers operations use their separate reviewed 25-node gate. |
| [Engine wheel, 39434727788](../audit/neutts-engine-wheel-native-20261020/run-39434727788/REVIEW.json) | Original backend build, all **392 wheel members**, **117 dictionaries** and all **14 bundled eSpeak C ABI cases** pass. | Whole artifact verified. The engine was neither installed nor imported; its original Python **>=3.10,<3.14** bound remains unchanged. |
| [APT extensions, 39434727717](../audit/neutts-apt-extensions-native-20261020/run-39434727717/REVIEW.json) | PyArrow, lxml, MsgPack, Pillow and psutil operations pass. Strict original requirements/provenance pass for **12 APT distributions**, with 893 files and 34 native files unchanged. | Whole artifact verified. Raw pip's 12 original legacy-tag diagnostics remain; no metadata or tag is rewritten. |
| [XXHash, 39434727829](../audit/neutts-xxhash-native-20261020/run-39434727829/REVIEW.json) | All **seven cases** pass, including fixed vectors, streaming, seed/copy/reset and actual mapped-library provenance. | Whole artifact verified for the unchanged 4.0.1 Android wheel. This is a dependency result, not an engine or synthesis result. |

The Tokenizers result is tied to source
**8995678c0e20c117bbab9830b919e49ba0689a5d**: all 79 recorded inputs match both
their SHA-256 ledger and that exact source tree. Its actual native target is
Android API 24/AArch64/Python 3.14.6, with only loopback available during the
operations. The original [CI evidence](../audit/neutts-tokenizers-runtime-native-20261020/run-39447721557/ci/ci-push-original-job-log.txt)
at the same source records **1,241 tests and 577 additional subtests passing,
with 84 skips**, in 28.34 seconds. This includes the Linux preparation check
under a private umask; duplicate push/PR results are not added together.

#### Complete dependency environment: all eleven groups pass

The complete preparation binds **105 actual wheels and 11 original APT Python
payloads** into the original **116-distribution/183-edge dependency graph**.
It excludes only NeuTTS and its 11 outgoing edges from the original 117/194
design. Every selected dependency version, original requirement and the engine's
**Python >=3.10,<3.14** bound remain unchanged.

The first two native attempts stopped before operation groups ran, and both
failures remain recorded:

1. [Run 39450032929](../audit/neutts-complete-runtime-native-20261020/run-39450032929/FAILURE-REVIEW.json)
   at 88e2810 exposed the complete preparer's missing safe_relative adapter.
   The [interface correction](../audit/neutts-complete-runtime-native-20261020/interface-fix/INDEPENDENT-INTERFACE-REVIEW.json),
   saved at 11f7bb6, passed 21 tests and 41 subtests. The additional generic
   fatal stderr line did not establish a native library defect.
2. [Run 39452440876](../audit/neutts-complete-runtime-native-20261020/run-39452440876/full-artifact-review/NATIVE-FAILURE-REVIEW.json)
   at 11f7bb6 then reached strict installed-file verification. Einx 0.4.3 and
   Phonemizer 3.3.0 packaged different documentation bytes at the same
   docs/source/conf.py destination. The independent full input census found
   exactly this one duplicate target. The unchanged byte check correctly
   rejected the overwrite; no operation group passed in that attempt.

The [packaging correction](../audit/neutts-complete-runtime-native-20261020/docs-collision-fix/README.md)
is saved at **3f1f404c72addb91f1d4937342c20e555be58a58**. It moves Einx's
unchanged documentation into its own share/doc/einx-0.4.3/source/conf.py through
the standard wheel data scheme and regenerates RECORD. All runtime code,
metadata, licenses, versions and requirements are preserved; Phonemizer is
unchanged. Original and derived wheels plus the
[131-member comparison](../audit/neutts-complete-runtime-preparation-20261020/einx-docs/EINX-DOCS-RELOCATION.json)
remain available. The derivative is reproduced and verified during preparation
and every input verification.

The new preflight maps all 105 wheels and 11 APT payloads into one
prefix-relative namespace and verifies **28,936 unique file targets**. It
rejects any duplicate owner, including identical bytes, aliases through wheel
data schemes and file/directory conflicts. Its result is bound into the
[prepared input receipt](../audit/neutts-complete-runtime-native-20261020/docs-collision-fix/COMPLETE-PREPARED-INPUTS.json).
The [focused and independent checks](../audit/neutts-complete-runtime-native-20261020/docs-collision-fix/independent-review/INDEPENDENT-FROZEN-GUARD-REVIEW.json)
each pass **25 tests and 48 subtests, with no skips**; these separate runs are
not added together.

An [independent real offline pip installation](../audit/neutts-complete-runtime-native-20261020/docs-collision-fix/independent-review/INDEPENDENT-EINX-INSTALL-REVIEW.json)
uses an explicit Android-style install scheme inside an actual private host
venv. The unchanged shared validators verify **181 original payloads, all 188
installed RECORD rows, 186 site files and two distributions**, with both original
documentation files at distinct paths. This proves the installer layout and
byte preservation on the host. It does not execute Android package operations.
The native probe changes only its preparer hash; its existing file, metadata,
RECORD and library checks remain intact.

The next [native run 39456043425](../audit/neutts-complete-runtime-native-20261020/run-39456043425/full-artifact-review/NATIVE-FAILURE-REVIEW.json)
at 3f1f404 passes the original 116-node/183-edge closure, the initial
**29,140-file installed inventory** and all **13,818 installed wheel RECORD
rows**. It then completes **ten actual operation groups**: foundation/audio,
the selected C/C++ data/tokenizer operations, HF-Xet, Safetensors, local
Hub/HTTP/YAML, Tokenizers, Tiktoken, Phonemizer, Llama CPU context and public
Perth watermark operations. The Llama context check does not perform inference.

**Historical run 39456043425 fails final integration.** Torchtune imports TorchAO, whose
int8_sdpa_lowering module refers to the removed
torch._inductor.kernel.flex_attention path. The original traceback identifies
this missing module beneath Torchtune's misleading "torchao not installed"
wrapper message. Exact signed Torch source places both real helpers,
construct_strides and maybe_realize, in torch._inductor.kernel.flex.common.
The [guarded TorchAO correction](../audit/neutts-complete-runtime-native-20261020/torchao-api-fix/README.md)
is saved and pushed at **2d4408fea01af1721e3caca612624002a20c4494**.
It retains the old import for older Torch and falls back only when the missing
module is exactly that old path. Ordinary ImportError, unrelated
ModuleNotFoundError and a missing new provider still propagate. Only the one
compiler-import source member and truthful RECORD change; all other 420 wheel
members, metadata, licenses, versions and requirements are byte-identical.
No helper implementation, registration or operation is replaced or skipped.

The [independent source and derivative review](../audit/neutts-complete-runtime-native-20261020/torchao-api-fix/independent-review/INDEPENDENT-TORCHAO-DERIVATIVE-REVIEW.json)
verifies both whole wheel archives/RECORDs and all 26 directly reached imported
symbols in 11 exact Torch modules. Focused and independent suites each pass
**30 tests and 54 subtests, with no skips**. The fresh
[full preparation](../audit/neutts-complete-runtime-native-20261020/torchao-api-fix/HOST-VALIDATION.json)
verifies the 105 wheels, 11 APT Python payloads and original 122-archive
foundation; all 28,936 targets remain uniquely owned.

The native gate now also checks that TorchAO's imported objects are the actual
current Torch exports, verifies their exact source hash, and exercises literal
contiguous/transposed strides and optional/SymPy realization. Those new native
checks pass in corrected run 39458842068, whose actual child result is summarized below.

In historical run 39456043425, the final integration group did not pass;
after-operation inventory/RECORD and loaded-library ownership checks were
**not reached**.
The [complete historical failure artifact](../audit/neutts-complete-runtime-native-20261020/run-39456043425/full-artifact-review/NATIVE-FAILURE-REVIEW.json)
has now been independently verified: all **760 members** of the
416,393,127-byte archive pass size, CRC and SHA-256 checks. This strengthens the
record of the failed run; it does not turn that result into a pass.
**The corrected [combined native run 39458842068](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39458842068)
at 2d4408f passes all eleven actual operation groups** (job 118752673393).
The original 116-distribution/183-edge closure passes; all **29,140 installed
site files** and **13,818 RECORD rows across 105 wheels** are identical before
and after. Final native-library ownership passes with **246 mapped extensions**,
and the container is disconnected before and after operations. Final integration
imports the real NeuCodec class and Torchtune/TorchAO and exercises the new real
Torch helper identity, source and literal behavior checks. The gate installs and
verifies the entire selected environment; its eleven operation groups do not
certify every public API of every distribution. The NeuCodec check imports its
real class without loading a codec model or exercising encode/decode.

The [independent complete-artifact review](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/NATIVE-SUCCESS-REVIEW.json)
passes all **763 members** of the 416,333,967-byte archive and matches all
**122 recorded source inputs** to exact commit 2d4408f. The actual child receipt
and complete final inventory/network evidence are retained. The reviewer rehashes
all 246 loaded extensions and 178 APT libraries, plus the original Torch helper
source: **425 original members**, using verified wheels and 55 exact APT archives.
Six image files match the pinned manifest, and ten eSpeak copies match their
original asset. This is a verified dependency-operation result; it does not
install/admit NeuTTS, change its Python bound, load speech models or prove synthesis.

Raw pip check still exits **1** with **eleven original APT platform-tag
diagnostics** and no missing or conflicting declared requirements. The strict
original-requirement and native-provenance checks pass. Original metadata and
supported tags are not rewritten to obtain a nominal pip pass.

The latest [retained host CI at 2d4408f](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/HOST-CI-REVIEW.json)
passes **1,271 tests and 631 additional subtests, with 84 skips**, in
19.65 seconds (push job 118752672409). The separate
[PR CI run 39458856008](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39458856008)
also passes the same counts in 25.00 seconds (job 118752722094). These duplicate
runs are not added together. Input-selected skips in the other PR workflows
are expected planner results, not additional native passes.

The [saved 3f1f404 CI](../audit/neutts-complete-runtime-native-20261020/run-39456043425/full-artifact-review/HOST-CI-REVIEW.json)
remains historical evidence: 1,266 tests and 625 subtests passed, with 84 skips
(push 35.10 seconds; PR 25.21 seconds). The earlier
[11f7bb6 CI](../audit/neutts-complete-runtime-native-20261020/docs-collision-fix/host-ci-11f7bb6/REVIEW.json)
and [88e2810 CI](../audit/neutts-complete-runtime-native-20261020/run-39450032929/host-ci-88e2810/original-job-log.txt)
also remain preserved. Host CI does not change any failed native outcome.

The [NeuCodec wheel preparation](../audit/neucodec-wheel-preparation-20261020/INDEPENDENT-WHEEL-REVIEW.json)
preserves original metadata, license and its 20-member inventory, changing only
model.py and its truthful RECORD. Its 14 tests and 40 subtests pass, including
the earlier 34 adapter cases. Native codec/model behavior remains a later gate;
source packaging does not demonstrate inference.

Remaining work is to assess engine admission under its unchanged Python
requirement and validate
engine import, default initialization, codec/model behavior and actual synthesis.
No Python 3.14-specific engine defect has been proved by the bounded static review;
the declared upper bound remains the actual admission boundary.

The [exact Hermes helper](../audit/neutts-default-gguf-source-20261017.json)
selects AIR-q4, the full NeuCodec and CPU execution. For this selected route,
both owner-supplied reference audio and its matching transcript are required.
The [three immutable model identities](neutts-engine-closure.md) cover the
gated AIR/NeuCodec weights and the public W2V-BERT model used by the real codec
constructor. The helper does not pass immutable revisions, so a later test
must bind actual authorized model bytes or a private cache to those identities;
metadata and body-free access observations are not downloaded-weight proof.
The public Perth gate uses its injected original model API; the engine's
default optional watermarker factory remains unmeasured. Physical microphone
capture and silence/VAD stopping require the separate native Android device check.

#### Preserved failures and narrow corrections

The [HF linkage investigation](../audit/neutts-hf-python-linkage-20261020/REVIEW.json)
preserves the failed d215961 run and its whole 765,083,696-byte artifact, including
all 47,595 members. HF's ABI3 extension omitted the libpython3.so forwarding
stub; the scoped linker repair preserves original source, Cargo, TLS, versions
and tags. The later 4a95a07 run reached HF import/hashing before the Safetensors
probe used an obsolete nested-dictionary argument. The
[TensorSpec probe correction](../audit/neutts-safetensors-api-fix-20261020/host-validation/HOST-VALIDATION.json)
uses the shipped 0.8 API and an owned backing buffer. The independently reviewed
Tokenizers25 result now passes both operations; the independently reviewed Rust
retry also verifies the real HF TLS behavior without disabling certificate checks.

The [earlier Tiktoken failure](../audit/neutts-tiktoken-native-20261020/run-39440363758/REVIEW.json)
built the original wheel before a verifier rejected equivalent whitespace in
Regex's Setuptools requirement. Parsed PEP 508 comparison fixes that verifier
without rewriting source, requirements or pins; 35 tests and 50 subtests passed
before the successful retry. The [earlier Perth failure](../audit/neutts-soundfile-discovery-fix-20261020/NATIVE-FAILURE-REVIEW.json)
found the original libsndfile installed but undiscoverable through SoundFile's
platform fallback. The Android-only filename addition preserves metadata and
Linux behavior; 62 focused tests and 232 subtests passed before the successful
public-watermark retry.

The earlier 4a95a07 CI result remains historical evidence: 1,193 tests and
457 additional subtests passed, with 84 skips. It is not combined with the
newer CI count, and none of the earlier failed native runs is relabeled.

#### Historical d215961 retries and bounded follow-up fixes

The following records preserve the earlier observations; the newer outcomes
above supersede their pending status without removing the original failures.

The [20 October CI run, 39429636399](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636399),
for saved source `d2159613a9a4a2c0bbd8d86bc2e8f9cb75987ff4`, passed
**1,057 tests, 154 additional subtests and 80 skips**. These host results are
separate from the native workflow conclusions below. The [fresh API/log
checkpoint](../audit/neutts-native-retry-d215961-20261020/REVIEW.json) covers these
eight completed non-Rust runs; it does not claim independent full-artifact
verification. The engine has its separate actual-wheel review below. Rust
requires its own artifact diagnosis.

| Fresh d215961 gate | Observed result | Next boundary |
| --- | --- | --- |
| [Scientific foundation, 39429636519](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636519) | Workflow succeeded. | Full engine/model integration remains. |
| [TorchAO, 39429635992](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429635992), [eSpeak/Phonemizer, 39429635986](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429635986), and [Numba/Llama CPU, 39429636156](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636156) | All three workflows succeeded again. | Component success does not certify codec/model/synthesis. |
| [Six C/C++ dependencies, 39429636032](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636032) | API confirms completed workflow success. | Independent verification of that complete new artifact was pending at this historical checkpoint; the older detailed proof remains separately identified. |
| [Five APT extensions, 39429635899](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429635899) | Host acquisition failed with HTTP 404 after foundation inputs were prepared, before Docker. | Five additional exact original archives were recovered; a retry is required. |
| [Engine wheel, 39429636253](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636253) | Native CMake and backend build passed; wheel-content validation rejected the original Russian dictionary above the shared 2 MiB member guard. | The engine-only correction was host-validated at this checkpoint; its later native wheel/C ABI pass is recorded above. |
| [Rust, 39429636237](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636237) | Tiktoken lock job `118650994583` succeeded. Locked-build job `118650993975` failed in the `rust-base-runtime-operations` child (exit 1). | The child cause remains under investigation; the parent log alone does not certify all four wheel builds or their operations. |

The [retained input cache](../vendor/termux-preparation/README.md) now contains
**twelve original archives**, following the first seven-archive recovery.
The five additions are apache-orc, libarrow-cpp, libre2, Pillow and PyArrow.
The [recovery receipt](../vendor/termux-preparation/apt-extension-recovery-provenance.json)
binds each to its original signed-index size, hash, control fields and license
members. Launcher/cache selection changed; original package pins, signatures
and dependency declarations did not. The earlier [d26e601 retry failures](../audit/neutts-retry-20261020/d26e601/SUMMARY.json)
remain acquisition failures before the corrected HF/engine verifiers.

The [engine dictionary correction](../audit/neutts-engine-wheel-member-bound-fix-20261020/REVIEW.json)
accepts only `neutts/espeak-ng-data/ru_dict` under a finite 16 MiB ceiling,
with the actual generated manifest, exact size/hash and complete ZIP CRC/RECORD
checks. Its original **8,733,078 bytes** are retained. The shared 2 MiB guard
for ordinary members remains unchanged. **106 core/engine tests and 111
additional subtests passed, with no skips.** Host review of the actual failed-run
wheel does not certify downstream native C ABI execution or engine installation.

#### Earlier component proofs retained

| Gate | Recorded earlier result | Remaining limit |
| --- | --- | --- |
| Scientific foundation and Numba/Llama CPU | [Seven foundation cases](../audit/neutts-native-20261017/run-39058569758.json) and [native JIT/workqueue/backend operations](../audit/neutts-native-20261017/run-39064666810.json) pass. | No Llama model inference or complete speech engine. |
| eSpeak/Phonemizer | [39073138135](../audit/neutts-espeak-native-20261017/run-39073138135.json) passes all 14 C ABI cases and the full 23-distribution, 26-edge public-wrapper environment. | Real codec/model integration remains. |
| TorchAO NF4 | [39076217293](../audit/neutts-torchao-native-20261017/run-39076217293.json) passes import, quantization, independent dequantization, public linear forward and input gradient. The narrow lazy import preserves the other 346 wheel members and metadata. | CPU component result; no weight training or full engine. |
| Five APT extensions | [39084149423](../audit/neutts-apt-extensions-native-20261018/run-39084149423.json) passes real PyArrow, lxml, MsgPack, Pillow and psutil operations and exact mapped-library ownership. All 893 original files, one link and 34 ELF files remain unchanged. | Raw pip retains 12 original legacy-tag diagnostics; the separate requirements/provenance gate passes. |
| Six C/C++ dependencies | [39086276183](../audit/neutts-nonrust-native-20261020/run-39086276183.json), at saved `9edb088`, passes audioop-lts, PyCryptodomex, PyYAML, SentencePiece, pandas and scikit-learn individually and in their complete 14-distribution, 10-edge union with 5,655 verified site files and global site-packages hidden. | Complete engine integration remains. |
| Full Hermes audio environment | [39084612542](../audit/audio-hermes-native-20261018/run-39084612542.json) passes two fresh canonical constructions: 101 application distributions/6,906 owned files and four PM distributions/75 owned files at each path. | PortAudio is unavailable in the measured container; no physical capture or VAD pass. |

The C/C++ repair invokes scikit-learn's unchanged version/Tempita helpers through
the selected native Python. It retains the original 51 build archives and
21 requested installation additions. The exact already-installed GMP archive
is added only for provenance verification, with no additional installation or
upgrade. All 127 focused host checks passed before the successful native retry.

The [successful C/C++ artifact](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39086276183/artifacts/12121660500)
is 101,675,672 bytes, SHA-256
`9fa19904c27a9e636f5598354dbe3a0527a1914dcccc968ef2dd6cc5e934c552`.
Its 8,024 members and all individual/combined receipts were independently checked
before the workspace reset. Artifact upload omitted ten hidden prepared-source
files, including PyCryptodomex's `.separate_namespace`: the export contains
7,777 of 7,787 expected source files. The ten-file, 28,335-byte supplement was
recovered separately from exact original sdists before the reset. The uploaded
tree alone is incomplete; reconstruct from the pinned original archives. The
[20 October recovery receipt](../audit/neutts-nonrust-native-20261020/run-39086276183.json)
rechecks the run identity and exact decoded job log; it does not claim a new
complete raw-archive capture.

The [Tiktoken lock review](../audit/neutts-rust-native-20261017/run-39084939992/TIKTOKEN-ROOT-REVIEW.json)
is saved in `c1ea01d`: 27 original registry archives, 36 unchanged project files,
and a 25-node/41-edge Android-filtered graph. At that earlier checkpoint,
native wheel construction and tokenizer operations remained unproved. Its uploaded vendor tree also requires hidden
files to be reconstructed from the exact original crates.

[The Rust run](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084939992)
built and exercised Maturin's native CLI and full PEP517 backend before its
HF-Xet identity verifier rejected two legitimate crates: the `hf_xet` root
and its `hf-xet` backing dependency. The recovered narrow identity correction
has 155 passing Windows host tests and is saved in commit `c2a817b`.
A passing native retry was still required at that historical checkpoint.
The later independently reviewed Rust and Tokenizers25 successes are recorded
above, including native-TLS, Reqwest/no-HTTP3, OpenSSL and actual HF/Safetensors
operations. The earlier failed run is not relabeled as a success.

[The engine wheel run](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084452780)
completed its backend, then failed a nested CMake verifier. Exact CMake 4.4.4
initializes the nested Android build type to `RelWithDebInfo`, while the verifier
expected an empty value. Parent `Release` and API 24/ARMv8 flags were observed
intact. The [narrow expectation correction](../audit/neutts-engine-wheel-cmake-fix-20261020/REVIEW.json)
is saved in `d26e601`, with 50 focused tests and 78 additional subtests passing,
no skips, and exact CMake module/native-cache fixtures. It changes no engine
source, API/architecture flags or Python bound. The later native wheel and
bundled C ABI success is recorded above; engine installation/import and full
runtime admission remain separate.

The [standalone XXHash gate](../audit/neutts-xxhash-preparation-20261020/HOST-REVIEW.json)
is prepared against the unchanged original 4.0.1 Android wheel: **21 host tests
and 19 subtests pass, with no skips**. The later seven-case native success is
recorded above.

The [Perth resource-only derivative](../scripts/prepare_neutts_perth_resource.py)
replaces obsolete `pkg_resources` resource lookup with `pathlib`.
Version, dependency metadata, embedded checkpoint and all other 26 wheel
members are preserved; **12 host tests and two subtests pass, with no skips**,
and the source change has passed peer review. The later complete public
Perth runtime passes in run 39446824120, retaining Librosa, scikit-learn and
SoundFile. Its measured synthetic-signal behavior does not certify watermark
quality or the engine's separate default watermarker factory.

These historical component preparations now supply exact inputs to the
116-dependency combined gate described above. NeuTTS itself remains outside
that environment. Its original Python upper bound is unchanged; dependency
success does not establish engine admission, default initialization or synthesis.
The selected Hermes AIR/full-NeuCodec route additionally needs the exact model
bytes, authorized gated access or an existing verified cache, and the owner's
reference audio with its matching transcript.

The earlier saved [host CI, 39086773257](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39086773257),
for source `c1ea01d`, passed **999 tests with 80 skips and 72 additional subtests**
on Python 3.14.8. These are separate from the native component gates above.

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
