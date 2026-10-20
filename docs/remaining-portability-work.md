# Remaining portability work: speech and Android device integration

Updated 20 October 2026. The audited release has **nine explicit compatibility
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
| Phonemizer discovery | The repair passes 30 focused tests. Explicit existing library paths no longer trigger an unnecessary Bionic-incompatible dlinfo import. All 55 other original source files and dependency metadata remain unchanged. | The complete 23-package runtime now passes native public-wrapper phonemization, stress/punctuation, Regex and RPDS operations; complete NeuTTS inference remains unproved. |

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
additional completed executable slice is the 23-distribution Phonemizer subset,
including a real Regex build, the patched Phonemizer wheel and exact native
eSpeak library/data. The passing eSpeak C ABI result is recorded separately from the passing real
Phonemizer package import and public-wrapper phonemization.

The [complete Phonemizer input preparation](phonemizer-runtime-preparation.md)
now passes 69 host checks with all real-artifact fixtures supplied. Its 23 nodes
and 26 active dependency edges were independently recomputed. The exact eSpeak
source also has a reviewed CMake repair for the explicit Sonic-OFF setting;
all four real configuration regression cases passed. The
[integrated native runner](../audit/neutts-espeak-integration-v2-20261017.json)
builds eSpeak, tests its C ABI and full language data, then builds Regex and
patched Phonemizer and runs the real public wrapper. It retains the original
44 compiler archives plus the original pip archive needed for runtime
provenance. The native wrapper now passes as described below; complete NeuTTS engine
compatibility remains a separate gate.

The first [native eSpeak/Phonemizer run](../audit/neutts-espeak-native-20261017/run-39068675792.json)
passed the seven scientific foundation gates but stopped during source
extraction, before compilation. Its sole compatibility-header symlink lives in a
directory with no regular files, so that parent had never been created. The
[one-line extractor correction](../audit/neutts-espeak-source-extraction-fix-20261017/SOURCE-EXTRACTION-FIX.json)
now creates the verified parent. Two focused host tests pass, reproducing the
original missing-directory error and checking all 2,606 source entries, the sole
24-byte link and the target's containment after correction. Exact POSIX link
following and the native C ABI/public-wrapper gates were deferred at that checkpoint.
The complete failed artifact and all 190 member hashes are preserved.

The [next native run](../audit/neutts-espeak-native-20261017/run-39071928457.json)
passes all **14 eSpeak C ABI checks**, including relocation and negative controls,
with all 371 language-data files and 117 pronunciation dictionaries preserved.
Its whole 54,767,182-byte artifact and all 641 member hashes were independently
verified. The wrapper stage then built the pure Phonemizer wheel but failed to
move it across the separate temporary/output filesystems, before Regex or the
23-package public API gate. The [reviewed transfer fix](../audit/phonemizer-wheel-transfer-fix-20261017/WHEEL-TRANSFER-FIX.json)
copies the already-verified bytes into an exclusive new destination and verifies
both size and hash. All 48 focused preparation/transfer tests pass with no skips.
The [successful retry, 39073138135](../audit/neutts-espeak-native-20261017/run-39073138135.json),
now passes all seven foundation cases, all 14 C ABI checks, both source wheel
builds, and the real public Phonemizer API in its complete 23-distribution runtime.
The 26 active dependency edges and 1,756 original installed file hashes are
verified. Public phonemization, stress removal, punctuated batches, Regex
Unicode/grapheme/fuzzy behavior and RPDS persistent maps pass; dlinfo is retained
as a dependency but is not imported on the explicit-library path. The runtime's
raw pip check exits zero. Root verified the complete 55,254,989-byte artifact and
all 654 members; the earlier failures remain preserved.

### Current native component checkpoint (20 October 2026)

The published package still has nine restrictions. Seven repairs belong to
unpublished preparation candidates; complete NeuTTS and physical microphone/VAD
remain the two outstanding feature gates.

#### Fresh retries at d215961 and bounded follow-up fixes

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
| [Six C/C++ dependencies, 39429636032](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636032) | API confirms completed workflow success. | Independent verification of its complete new artifact is pending; the older detailed proof below remains separately identified. |
| [Five APT extensions, 39429635899](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429635899) | Host acquisition failed with HTTP 404 after foundation inputs were prepared, before Docker. | Five additional exact original archives were recovered; a retry is required. |
| [Engine wheel, 39429636253](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636253) | Native CMake and backend build passed; wheel-content validation rejected the original Russian dictionary above the shared 2 MiB member guard. | The engine-only correction is host-validated; its native retry remains pending. |
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

| Gate | Current result | Remaining limit |
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
and a 25-node/41-edge Android-filtered graph. Native wheel construction and
tokenizer operations remain. Its uploaded vendor tree also requires hidden
files to be reconstructed from the exact original crates.

[The Rust run](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084939992)
built and exercised Maturin's native CLI and full PEP517 backend before its
HF-Xet identity verifier rejected two legitimate crates: the `hf_xet` root
and its `hf-xet` backing dependency. The recovered narrow identity correction
has 155 passing Windows host tests and is saved in commit `c2a817b`;
a passing native retry is still required.
Both native-TLS selections, Reqwest/no-HTTP3 and OpenSSL checks remain required.
No HF TLS operation, Safetensors operation or complete Tokenizers runtime is
certified by the failed run.

[The engine wheel run](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084452780)
completed its backend, then failed a nested CMake verifier. Exact CMake 4.4.4
initializes the nested Android build type to `RelWithDebInfo`, while the verifier
expected an empty value. Parent `Release` and API 24/ARMv8 flags were observed
intact. The [narrow expectation correction](../audit/neutts-engine-wheel-cmake-fix-20261020/REVIEW.json)
is saved in `d26e601`, with 50 focused tests and 78 additional subtests passing,
no skips, and exact CMake module/native-cache fixtures. It changes no engine
source, API/architecture flags or Python bound. Complete native wheel admission,
installation and engine import still require a passing retry.

The [standalone XXHash gate](../audit/neutts-xxhash-preparation-20261020/HOST-REVIEW.json)
is prepared against the unchanged original 4.0.1 Android wheel: **21 host tests
and 19 subtests pass, with no skips**. Its independent native hash-operation
job is pending.

The [Perth resource-only derivative](../scripts/prepare_neutts_perth_resource.py)
replaces obsolete `pkg_resources` resource lookup with `pathlib`.
Version, dependency metadata, embedded checkpoint and all other 26 wheel
members are preserved; **12 host tests and two subtests pass, with no skips**,
and the source change has passed peer review. Full native Perth watermark
validation remains pending; Librosa, scikit-learn and Soundfile remain required.

Exact output handoffs between components and the complete 117-distribution
runtime still need completion. Model execution additionally needs authorized
access to the exact gated weights and reference audio with its transcript.
The original NeuTTS Python upper bound is unchanged; no Python 3.14 production
admission follows from these component preparations.

The earlier saved [host CI, 39086773257](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39086773257),
for source `c1ea01d`, passed **999 tests with 80 skips and 72 additional subtests**
on Python 3.14.8. These are separate from the native component gates above.

The exact eSpeak source's optional Sonic fetch is covered by the reviewed
explicit-OFF guard and native phonemization probe described above. This
component gate does not use Android audio devices or download speech models.

### Exact model access and eventual engine gate

The model audit fixes the default model revisions and files. Unauthenticated
HEAD requests to the two default Neuphonic weight files returned HTTP 401 with
`GatedRepo`; the W2V-BERT weight endpoint was public. The three advertised
weight sizes total 4,009,627,472 bytes. These are advertised identities and sizes,
not proof that the weight bodies have been downloaded and checked. Reference
audio and its matching transcript are also needed for the engine gate.

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

### Earlier audio preparation checkpoints

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
retains the successful builds and that failed final check.

The [third native run, 39070305665](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39070305665),
again built both environments, then detected additional interpreter caches.
The canonical UV environment deliberately removes ambient Python flags, and its
bundle restoration explicitly compiles bytecode. A real host reproduction of
that canonical operation produced 50 caches in an owned copied interpreter.
The [reviewed normalization](../audit/audio-hermes-native-20261017/run-39070305665/generated-tool-bytecode-normalization.json)
checks every new cache's CPython format, exact original source, header and
recursive code equality against a fresh compile. It archives every verified
cache byte before removal and restores the complete original Python inventory.
Baseline files and caches remain unchanged, and the final full-payload comparison
is unchanged. The following native run uses seven stage inventories to identify where caches
first appear. All 90 focused host tests pass with no skips in the
[independent root replay](../audit/audio-hermes-native-20261017/run-39070305665/root-normalization-review.json);
the actual UV host reproduction also restored all original entries after
archiving and removing its 50 new cache files and six new directories.

The [fourth native run, 39072170354](../audit/audio-hermes-native-20261017/run-39072170354.json),
now confirms that normalization: all 50 new caches and six new directories were
archived/removed, no original files changed, the complete original Python
inventory was restored, and the unchanged payload-change oracle passed. The
stage inventories locate cache creation at the canonical application build.

The final link check then found the exact preexisting missing FFmpeg copyright
destination. Of 77 post-build links, 76 have present destinations and one retains
that original documentation gap. The reviewed correction separately reports
the missing documentation, binds it to the complete original inventory and
unchanged GPL text, and leaves every executable/library containment and
existence check in place. It makes no payload repair. All 118 focused host
tests pass with no skips, including all 90 earlier cases.

### Current complete audio environment

[Run 39084612542](../audit/audio-hermes-native-20261018/run-39084612542.json)
passes the final link and dependency gates at independently constructed
`/out/prepared` and `/out/reconstructed` paths. Each has 101 application
distributions/6,906 wheel-owned files, four PM distributions/75 owned files,
and 102 catalog rows including all 100 original rows. Canonical construction,
source/payload/metadata/link/library checks, CFFI and NumPy arithmetic, FFT,
LAPACK and matrix multiplication pass. All 199 focused host checks passed
before the native run.

Selected catalog, source patches and wheel results agree across the two paths.
Path-specific bytecode and environment metadata differ; full-environment
byte-for-byte equality is not claimed. Both probes record PortAudio error -9999,
`Initializing engine failed`, with all eight measured Android framework/Binder
paths absent. Neither opens a microphone stream. Physical PCM capture, silence
detection and automatic stopping remain untested.

The complete [offline device inputs](../audit/audio-hermes-native-20261018/device-inputs-39084612542.json)
contain the exact candidate, original audio inputs, wrapper, source helpers,
patches and reconstruction scripts, rather than a copied CI venv. The ZIP is
233,720,666 bytes, SHA-256
`794cef032430d5dea92a316872cd2d7a6015ec854e4c15a38999c880b6b37177`;
all 21 members and 20 manifest entries were checked. Its Actions expiry is
17 November 2026 at 00:56:38 UTC. The separate native-proof ZIP is 67,968,381
bytes, SHA-256
`92c6c20e54c93ba5bd9ddb51affe4775ec01cc1970ad93a9990759e2f6236e43`;
all 186 members were checked. Their retained success evidence is saved locally
in commit `9877b37` after Devbox access returned.

The [device guide](audio-readiness-device-validation.md) supplies fresh-path
reconstruction, non-recording readiness checks and a later owner-initiated
bounded PCM/VAD test with private profile, cache and recording directories.
No physical device result is inferred from container dependency success.

## Stable-release boundary

The compatibility preparation is saved independently from the released recipe.
The six-repair [main candidate lifecycle](../audit/candidate-lifecycle-e271e92-20261017/summary.json)
and seven-repair CUA-augmented lifecycle have passed their stated native gates.
A future stable release must validate its final complete source and runtime
selection, satisfy the remaining engine/device requirements, and receive the
appropriate release authorization.

This preparation does not publish a release, bump the version, merge the release
branch or promote a candidate into the signed APT feed.
