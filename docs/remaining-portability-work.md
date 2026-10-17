# Remaining portability work: speech and Android device integration

Updated 17 October 2026. The audited release has **nine explicit compatibility
restrictions**. Seven have repairs with native evidence, including the complete
CUA-augmented candidate. **NeuTTS and physical microphone/VAD remain incomplete.**
This document separates completed repairs from the work still needed for those
two capabilities. No package version, published release or APT feed is changed.

## NeuTTS 1.4.1

### What the original exclusion means

NeuTTS 1.4.1 declares Python >=3.10,<3.14. The released Hermes package uses
CPython 3.14.6 on Android/Bionic. Hermes declares NeuTTS as an optional dependency,
but its resolver environment is Python >=3.14; the current lock contains no
resolved complete NeuTTS group. Existing Torch or ONNX Runtime records from other
optional groups do not constitute that missing environment.

PyPI supplies platform wheels for this NeuTTS release, but no source distribution.
The exact public Git source exists and still declares 1.4.1. The source port uses
that source identity; it does not invent an sdist or borrow another interpreter's
site-packages.

Primary references are the [exact PyPI metadata](https://pypi.org/pypi/neutts/1.4.1/json),
[reviewed NeuTTS source declaration](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/pyproject.toml)
and [Hermes resolver configuration](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/pyproject.toml).

### Completed scientific and CPU work

| Layer | Verified result | Practical limit |
| --- | --- | --- |
| Scientific foundation | All seven gates pass: exact Python/APT dependencies and installed-file provenance, Torch computation, Torchaudio resampling, Torchcodec decoding an owned PCM WAV, SciPy operations, llvmlite JIT and soxr resampling. | A separate Termux system-Python environment; the complete NeuTTS engine is not installed. |
| Numba 0.67.0 | Exact native source wheel builds. Nopython JIT returns the expected result, and the parallel workqueue generalized-ufunc test returns the exact matrix. | CPU behavior only; no speech synthesis claim. |
| llama-cpp-python 0.3.36 | Exact source and matching vendored llama.cpp build with the Android loader repair. Backend initialization/free, real default parameters, CPU capability calls and mapped-library verification pass. | No model is loaded; token generation and synthesis are not tested. |
| NeuCodec Hub adapter | The source adapter passes 34 focused tests and retains revision, token, cache, local-files-only and error behavior. Unsupported per-call proxy settings fail before the download. | Real codec/model operations still need the complete native environment and weights. |
| Phonemizer discovery | The repair passes 30 focused tests. Explicit existing library paths no longer trigger an unnecessary Bionic-incompatible dlinfo import. All 55 other original source files and dependency metadata remain unchanged. | Exact eSpeak native library/data and the real public Phonemizer wrapper remain separate gates. |

The [first complete foundation run](../audit/neutts-native-20261017/run-39058569758.json)
verifies all 2,829 installed files from nine Python wheels, native MarkupSafe,
474 APT provenance files and the exact 122-archive input set. Pip's original
seven APT wheel-tag diagnostics remain in the raw evidence. The
[strict validator](../scripts/validate_neutts_apt_python.py) recognizes only the
reviewed legacy tag spelling after checking original archives and dependency
metadata; no wheel metadata or interpreter tag table is rewritten.

The [complete native CPU run](../audit/neutts-native-20261017/run-39064666810.json)
at head `954a439549f9b5f6dbf0e4b192b78c47514dbea5` repeats all seven
foundation gates, then verifies the 44-archive compiler closure, builds both
native wheels and passes `installed_inputs`, `numba` and `llama`.
It installs 14 new compiler packages and reinstalls five exact packages from
verified archives, with no package removal or upgrade in that compiler step.
The native experiment uses two compiler/JIT threads and records its resource
bounds. Its 151,552,762-byte artifact and all 4,669 members were checked.

Two actual failures are preserved. [Run 39062163081](../audit/neutts-native-20261017/run-39062163081.json)
failed before compilation because an unnecessary Android platform override broke
CPython's supported-tag calculation. The corrected invocation uses the native
interpreter's own Android platform. [Run 39063611598](../audit/neutts-native-20261017/run-39063611598.json)
built both wheels and passed Numba, but its Llama test tried to record an obsolete
`use_mmap` field. The [reviewed probe correction](../audit/neutts-llama-load-mode-probe-fix-20261017.json)
checks the exact pinned `load_mode == LLAMA_LOAD_MODE_AUTO` field and measures
mmap capability separately. The subsequent whole CPU gate passes; neither failed
run has been relabeled.

See the [default-engine source review](neutts-default-gguf-feasibility.md),
[NeuCodec change](neucodec-hub1-compatibility.md) and
[Phonemizer change](phonemizer-android-dlinfo-compatibility.md) for source pins,
patches, tests and their individual limits.

### Complete runtime graph and remaining builds

The [full dependency and model audit](neutts-engine-closure.md) records a
**117-distribution, 194-active-edge metadata witness**. It retains the complete
declared Torchtune and Librosa dependencies. There are no selected-version
conflicts. NeuTTS's original Python upper bound is the sole Python-requirement
failure at 3.14.6.

This witness is **not an installable lock**. Native build requirements, exact
wheel/API/ELF compatibility and the expanded APT library closure need their own
preparation and execution. Exact compatible wheels from the already-verified
candidate can be reused only by matching both source identity and wheel bytes.
An available PyPI version or an Android filename alone does not prove runtime
compatibility.

The [frozen runtime routes](neutts-runtime-preparation.md) bind exact artifacts
and the separately [saved APT index pair](../audit/neutts-runtime-index-20261017/SAVED-FILES.json).
Preparation is now executing these routes. It will use the separate
scientific APT interpreter and preserve the published Hermes runtime. The first
additional executable slice is the complete 23-distribution Phonemizer subset,
including a real Regex build, the patched Phonemizer wheel and exact native
eSpeak library/data. A C-ABI-only eSpeak result will remain distinct from real
Phonemizer package import and public-wrapper phonemization.

The [complete Phonemizer input preparation](phonemizer-runtime-preparation.md)
now passes 69 host checks with all real-artifact fixtures supplied. Its 23 nodes
and 26 active dependency edges were independently recomputed. The exact eSpeak
source also has a reviewed CMake repair for the explicit Sonic-OFF setting;
all four real configuration regression cases passed. The
[integrated native runner](../audit/neutts-espeak-integration-v2-20261017.json)
will build eSpeak, test its C ABI and full language data, then build Regex and
patched Phonemizer and run the real public wrapper. It retains the original
44 compiler archives plus the original pip archive needed for runtime
provenance. These complete preparations do not yet establish a native wrapper
pass or complete NeuTTS engine compatibility.

The first [native eSpeak/Phonemizer run](../audit/neutts-espeak-native-20261017/run-39068675792.json)
passed the seven scientific foundation gates but stopped during source
extraction, before compilation. Its sole compatibility-header symlink lives in a
directory with no regular files, so that parent had never been created. The
[one-line extractor correction](../audit/neutts-espeak-source-extraction-fix-20261017/SOURCE-EXTRACTION-FIX.json)
now creates the verified parent. Two focused host tests pass, reproducing the
original missing-directory error and checking all 2,606 source entries, the sole
24-byte link and the target's containment after correction. Exact POSIX link
following and the native C ABI/public-wrapper gates remain for the retry.
The complete failed artifact and all 190 member hashes are preserved.

The exact eSpeak source also attempts an optional Sonic fetch even when the
caller explicitly disables Sonic. A small explicit-OFF guard and a native
phonemization probe are being prepared. This work does not use Android audio
devices or download speech models.

### Exact model access and eventual engine gate

The model audit fixes the default model revisions and files. Unauthenticated
HEAD requests to the two default Neuphonic weight files returned HTTP 401 with
`GatedRepo`; the W2V-BERT weight endpoint was public. The three advertised
weight sizes total 4,009,627,472 bytes. These are advertised identities and sizes,
not proof that the weight bodies have been downloaded and checked.

| Model | Exact reviewed revision | Access result |
| --- | --- | --- |
| `neuphonic/neutts-air-q4-gguf` | `0f54a5513ee49708713e49c5122c274df2737047` | Default GGUF requires authenticated model access. |
| `neuphonic/neucodec` | `a940021324df13a07f44185f0a17c6dac3698179` | Codec weight requires authenticated model access. |
| `facebook/w2v-bert-2.0` | `da985ba0987f70aaeb84a80f2851cfac8c697a7b` | Public weight endpoint; body not downloaded by the access audit. |

The [retained access observations](../audit/neutts-engine-closure-20261017/model-head-access.json)
record zero model body bytes. Account-specific model access must come from the
user's authorized account; gate forms cannot be completed using invented
affiliation or role information.

Once the complete native environment and authorized weights are available, the
engine gate must exercise reference-audio encoding, phonemization, the actual
GGUF generation path, codec decoding, watermark behavior, valid 24 kHz PCM output,
cancellation/cleanup and observed memory use. Only then can a wider Python
requirement and normal Hermes admission be justified. Metadata edits or import
success alone are insufficient.

## Local computer use

### Complete packaged virtual-X11 result

The original Linux ARM64 CUA release is a glibc executable. The prepared native
Bionic port uses exact CUA source commit
`70db98d1bcd92890d778f4978e0eb107a4b66c1b` and preserves all 602 unrelated
Cargo package records. Two small pinned crate adapters provide the existing X11
clipboard implementation and Termux socket path.

The separate [CUA-augmented candidate](cua-candidate-preparation.md) now passes
[the complete native workflow](../audit/cua-native-20261017/run-39063611615.json)
at head `5cace91a4253642d2597c7712b7cf119ade8d892`:

- All 11 standalone X11 checks and seven real registered-Hermes checks pass.
- Normal PM discovery loads the sealed source-built driver without an override.
- Omitted delivery mode resolves to foreground before approval. No approver,
  an explicit background request, or a background-only grant cannot authorize
  that foreground input.
- Three distinct once approvals lead to independently observed click, scroll and
  typed-text events. Actual pixels, window geometry, viewer leases and cleanup
  are checked.
- All 32,515 prepared payload entries remain unchanged during probes and
  same-version reinstall.
- A fresh container installs the exact published package, upgrades to the
  candidate, preserves three user-state hashes, installs the two exact optional
  packages with no native compiler, and reuses that environment on repetition.

The package retains version 0.22.2-1 and the original 100-wheel catalog. It adds
the owned native driver and official `libx11`/`libxi` runtime dependencies.
Its SHA-256 is
`2b4c01a400622c45cf0f0f7af39fa5cdca4b37e311cebb71cdbacc770aa4f529`.
It is an unpublished Actions candidate, based on the already-proven six-repair
main candidate. This completes the seventh repaired restriction in the audited
scope. The [first packaged run's host permission error](../audit/cua-native-20261017/run-39062805143.json)
is preserved alongside the successful retry.

### Scope that remains outside this result

The port controls its owned virtual X11 desktop. It does not supply Android
Accessibility or MediaProjection control of arbitrary phone applications.

Explicit background input remains refused because its earlier native experiment
produced no independently observed input effect. The fallback accessibility
window element is not an AT-SPI tree. Encrypted history requires a supported
credential store, and the TigerVNC desktop does not supply the parallel uinput
devices needed for multiple pointers. These limitations are recorded within the
computer-use capability; they are not silently counted as additional completed
features.

The [earlier standalone result](../audit/cua-native-20261017/run-39052290704.json)
and [explicit-driver Hermes result](../audit/cua-native-20261017/run-39056267366.json)
remain available as historical evidence. Their narrower checks are superseded
for normal packaged discovery by the complete gate above.

## Microphone silence detection

Termux:API records a finalized file. It does not expose the live PCM stream used
by Hermes' sounddevice silence detector. The repaired selector makes the existing
PCM backend explicit while keeping Termux:API available independently; it does
not substitute Android speech recognition for the configured transcription
provider.

The original audio experiment builds exact NumPy 2.4.3 and passes numerical
checks using both build and original package libraries. PortAudio loads its
Termux OpenSL ES wrapper, but that container lacks Android's real audio
framework, Binder devices and audio services. Initialization fails there, so it
does not certify a microphone or VAD. The
[retained native audio evidence](../audit/native-probes-9fcd31c-20261017/audio-summary.json),
[official PortAudio recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/portaudio/build.sh)
and [reviewed wrapper source](https://github.com/termux/termux-packages/blob/11ae750781a261b8df328697b12d66d75b72e5da/packages/libandroid-stub/libOpenSLES-wrapper.c)
establish that boundary.

The [audio-readiness patch](../patches/next-stable/audio-readiness.patch) preserves
the actual import-time PortAudio error and rejects an output-only device
inventory as microphone readiness. Its
[source/test receipt](../audit/audio-readiness-preparation-20261017.json) records
the reviewed behavior.

The [initial audio preparer](../audit/audio-hermes-environment-preparation-20261017.json)
passed 39 focused host tests and full four-path source replay. Its first complete
native run, [39067100543](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39067100543),
stopped before manager construction because the build-cache verifier expected
versioned tool directories while the packaged payload records flat python/uv
entries. The narrow [packaged-tool correction](../audit/audio-hermes-native-20261017/run-39067100543/packaged-tool-verification-fix.json)
preserves the original lock, facts, tree digests, link policy and environment
checks. It passes 56 focused host tests with no skips, including 17 cases using
the actual canonical PM classes. The [independent root review](../audit/audio-hermes-packaged-tool-root-review-20261017.json)
records the same result.

The next [native run, 39068675759](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39068675759),
successfully built both canonical environments at the first final path: the
application contains 101 selected distributions and the manager contains four.
All 100 original catalog entries are retained alongside the two audio additions.
Its strict final payload check then detected new interpreter cache files. The
canonical marker helper used isolated Python, which ignores the environment's
bytecode setting. A separate [one-line source patch](../patches/next-stable/audio-pm-marker-bytecode.patch)
adds the explicit no-bytecode flag to that helper. The actual canonical
subprocess regression demonstrates 25 original cache files versus zero after
the patch, with identical interpreter facts. All 62 focused tests pass with no
skips in both the agent and [independent root run](../audit/audio-hermes-native-20261017/run-39068675759/marker-bytecode-root-review.json).
The [failure and correction record](../audit/audio-hermes-native-20261017/run-39068675759/marker-bytecode-failure-fix.json)
retains the successful builds and the failed final check; no cache cleanup or
relaxed payload comparison conceals the write.

A complete native retry must still pass the final integrity check, execute the
audio dependency probe, and repeat construction at a second independent path.
Both environments are built fresh through canonical APIs from the exact main
candidate and original wheel catalog. The original candidate, installed payload,
lock files and existing wheels must remain unchanged. The workflow preserves a
reconstruction-input bundle separately from build/probe evidence; each phone
must construct its own environment at its final private destination.

After that staging gate, the [device guide](audio-readiness-device-validation.md)
covers the remaining physical tests: real microphone permission and PCM capture,
silence timing/VAD, maximum duration, interruption/cancellation, playback/audio
focus and cleanup. Container dependency success must stay separate from an
actual Android capture result.

## Stable-release boundary

The compatibility preparation is saved independently from the released recipe.
The six-repair [main candidate lifecycle](../audit/candidate-lifecycle-e271e92-20261017/summary.json)
and seven-repair CUA-augmented lifecycle have passed their stated native gates.
A future stable release must validate its final complete source and runtime
selection, satisfy the remaining engine/device requirements, and receive the
appropriate release authorization.

This preparation does not publish a release, bump the version, merge the release
branch or promote a candidate into the signed APT feed.
