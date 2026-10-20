# NeuTTS runtime preparation routes

Updated 20 October 2026. Native component results below remain separate from
complete NeuTTS admission and real model/synthesis behavior.

**Current combined gate:** [run 39458842068](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39458842068)
at **2d4408f** passes all eleven actual operation groups, the original
116-distribution/183-edge closure and final inventory/RECORD, native-library
ownership and disconnected-network checks. Its child receipt has been
independently verified against the [complete artifact and source review](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/NATIVE-SUCCESS-REVIEW.json).
Engine import, default initialization and complete model/synthesis behavior
remain unmeasured under the unchanged Python bound. The three failed attempts
below are historical results.

## Frozen scope

This preparation preserves the complete declared NeuTTS 1.4.1 base plus `llama` dependency graph: **117 distributions and 194 active dependency edges**. It includes the Torchtune and Librosa dependency chains. Existing package versions, dependency declarations, and NeuTTS's `>=3.10,<3.14` interpreter bound remain unchanged.

The route manifest is `scripts/neutts_runtime_closure_design.json` (SHA-256 `d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68`). It copies all 194 active edges and records the exact source evidence for each distribution. It is a preparation design, not an installable lock or a production compatibility decision. The underlying graph is `audit/neutts-engine-closure-20261017/dependency-candidate.json`, SHA-256 `673d878e6fdc6fca65dfb40f8af8cade74e627b4d45f48ca995bc337cf445f06`.

## Artifact routes

| Route | Distributions | Evidence and remaining gate |
|---|---:|---|
| Reuse exact main catalog wheels | 37 | Actual wheel bytes, every CRC and RECORD digest, metadata, and catalog identities verified. The combined native gate now checks the selected installed inputs and actually loaded extension/library ownership against the separate APT Python; unexercised APIs remain outside its scope. |
| Additional existing core wheels | 6 | Exact filelock, fsspec, MarkupSafe, mpmath, NetworkX and SymPy pins retained. Three other core packages overlap the main route. |
| Existing foundation APT distributions | 6 | llvmlite, NumPy, SciPy, soxr, Torch and torchaudio. Torchcodec remains an additional required APT dependency outside the 117-node Python graph. |
| Previously validated CPU component wheels | 2 | Numba 0.67.0 and llama-cpp-python 0.3.36 passed native run 39064666810. Their exact archive receipts are bound in the complete input lock and exercised by the combined native gate. |
| Existing native build-input wheel | 1 | Diskcache 5.6.3, unchanged. |
| Official APT extensions | 5 | PyArrow, lxml, msgpack, Pillow and psutil pass native run 39084149423: signed inputs, original metadata/tags, exact library provenance and real operations. |
| Public pure Python wheels | 45 | Exact original archives, CRC/RECORD and metadata are verified and saved. Operations remain for packages without a passed native component gate. Multiprocess retains its exact Python 3.14 wheel. |
| Patched pure Python sources | 2 | NeuCodec 0.0.4 now has a verified original-wheel derivative preserving metadata/license and all members except model.py/RECORD. Phonemizer 3.3.0's source wheel and complete public-wrapper runtime pass. Actual NeuCodec model operations remain. |
| Official Android wheel | 1 | XXHash 4.0.1's exact `cp314-cp314-android_24_arm64_v8a` archive, RECORD, metadata and ELF identity are verified; all seven native operation/provenance cases pass in run 39434727829. |
| Source/native builds | 12 | The six C/C++ components and engine wheel/bundled C ABI pass. Tokenizers25 independently passes with real HF-Xet/Safetensors operations. Tiktoken/Regex and locked Rust builds/base operations now have independently reviewed native success. The corrected complete116 run passes all eleven groups and final integrity/provenance checks, with independent whole-artifact/source review complete; its three earlier failures and narrow fixes remain recorded below. |
| **Total** | **117** | No graph nodes omitted. |

The actual main catalog contains 100 wheels, 38 of which have exact version matches in the engine graph. Their archive hashes and complete declared requirement sets were independently checked. Pillow uses the official APT route, leaving 37 selected main wheels and avoiding a second OpenJPEG/native provenance route. Main MarkupSafe 3.0.3 and psutil 8.0.0 do not match the frozen graph and are not reused.

The original 68,318-byte main catalog has SHA-256 `d2dc66575cf8aa5ef828e5e536b4d55b8801143101b7e608f6fb4878c2397904`. Its exact records, including original source fingerprints, are preserved under `audit/neutts-runtime-reuse-20261017/`.

## Five APT extensions and archive drift

The selected roots are `python-pyarrow=26.0.0-2`, `python-lxml=6.1.3`, `python-msgpack=1.2.3`, `python-pillow=12.3.0`, and `python-psutil=7.2.2-2`. Their package dependency closure contains **78 packages and 151 edges**. After the existing 122-package foundation and 44-package compiler closure are accounted for, **18 archives totalling 14,043,104 bytes** remain:

apache-orc, libarrow-cpp, libgcrypt, libgpg-error, libimagequant, liblz4, libraqm, libre2, libsnappy, libxslt, openjpeg, python-lxml, python-msgpack, python-pillow, python-psutil, python-pyarrow, thrift and utf8proc.

The fresh official InRelease/Packages pair was fetched at 20:05 UTC on 2026-10-17. Packages.gz SHA-256 `dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6`, 727,968 bytes, matches the SHA256 section in InRelease SHA-256 `249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901`. The later native gate authenticates this same snapshot with the configured Termux trust store; the original host hash binding remains separate evidence.

At the original **17 October acquisition checkpoint**, the index differed from the earlier native snapshot, but **all 122 foundation and all 44 compiler archive identities matched** by package, version, architecture, size, SHA-256 and repository filename. The statement that no existing archive had drifted described those captured bytes and that checkpoint. Several rolling pool URLs later disappeared; the 20 October recoveries below retain their exact original bytes and pins. The successful native APT gate verifies the exact complete plan with no unrecorded dependency substitutions.

All five extension .deb archives were actually downloaded and inspected. Their control fields match the pinned index, and their original METADATA requirements match the frozen graph. Their original WHEEL tags use `android_aarch64`: four use CPython 3.14 tags, while psutil uses `cp36-abi3-android_aarch64`. Those tags are preserved. [Native run 39084149423](../audit/neutts-apt-extensions-native-20261018/run-39084149423.json) passes all seven foundation cases and all five extension operations, checking the exact 18-archive installation plan and all 893 original files, one link and 34 ELF files. Every observed mapping has exact retained APT or pinned-image ownership. PyArrow's extra ICU image member is separately verified without broadening the original five-file foundation policy. Raw pip retains twelve original legacy-tag diagnostics; the independent requirements/provenance gate passes without rewriting WHEEL or METADATA.

## Twelve exact source/native routes

All eleven PyPI sdists listed below have been obtained and SHA-256 verified. NeuTTS uses the exact already inspected source commit. Archive pins and the original build-file texts and hashes are saved in `audit/neutts-runtime-reuse-20261017/twelve-source-build-requirements.json`.

| Source | Exact version | Declared build requirements and native route |
|---|---|---|
| audioop-lts | 0.2.2 | Setuptools backend and C compiler; preserve its CPython limited-ABI behavior. |
| hf-xet | 1.6.0 | Maturin `>=1.7,<2`; Rust workspace and PyO3 0.29. |
| NeuTTS | 1.4.1, commit `b7a3427d0d25e20e8b9e92cbaae688f732916baf` | scikit-build-core `>=0.9`, CMake `>=3.26`, exact eSpeak source/data. Requires-Python `>=3.10,<3.14` remains unchanged. |
| pandas | 3.0.6 | meson-python `>=0.17.1,<1`, Meson `>=1.2.1,<2`, wheel, Cython `>3.1.0,<4`, NumPy `>=2,!=2.5.0`, versioneer[toml]. |
| PyCryptodomex | 3.24.1 | Setuptools backend and C compiler. Preserve the Cryptodome namespace. |
| PyYAML | 6.0.3 | Its `_pyyaml_pep517` backend, Setuptools, Cython `>=3.0` for Python 3.14. Preserve the native LibYAML extension. |
| Regex | 2026.9.10 | Setuptools `>77.0.3` and C compiler; existing Setuptools 83.0.0 satisfies the bound. |
| Safetensors | 0.8.0 | Maturin `>=1,<2`, Rust and PyO3 0.28. |
| scikit-learn | 1.9.1 | meson-python `>=0.17.1,<0.22`, Cython `>=3.1.2,<3.2.6`, NumPy `>=2,<2.6`, SciPy `>=1.10,<1.19`. |
| SentencePiece | 0.2.2 | Setuptools `>=61`, wheel, pybind11 `>=2.12`, CMake/C++ bundled source. |
| Tiktoken | 0.14.0 | Setuptools `>=62.4`, wheel, setuptools-rust `>=1.5.2`, Rust and PyO3 0.29.2. |
| Tokenizers | 0.22.2 | Maturin `>=1,<2`, Rust and PyO3 0.26. |

The frozen NumPy 2.5.4 and SciPy 1.18.1 satisfy the scientific build bounds above. The completed non-Rust route verifies exact compiler/scientific inputs and LibYAML 0.2.5-5. The Rust route freezes 47 compiler/TLS archives, including Rust 1.99.1, and builds Maturin 1.15.0's full Python PEP517 backend from original source; an APT executable alone is not treated as that backend. No blanket foundation rebuild or version change is implied.

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

## Complete Phonemizer public-wrapper slice

Phonemizer's complete selected runtime subset has **23 distributions and 26 active dependency edges**. It requires no model files and no Torch/NumPy installation.

The nine exact main wheel reuses are attrs, jsonschema, jsonschema-specifications, python-dateutil, referencing, rpds-py, six, termcolor and typing-extensions. The twelve public pure wheels are Babel, cloudpickle, csvw, dlinfo, isodate, joblib, language-tags, pyparsing, rdflib, rfc3986, segments and uritemplate. The remaining two packages are native-built Regex 2026.9.10 and the patched Phonemizer 3.3.0 wheel.

[Native run 39073138135](../audit/neutts-espeak-native-20261017/run-39073138135.json) passes both source wheel builds and the public `phonemizer.phonemize` API. It verifies all 23 distributions, 26 active edges and 1,756 original installed file hashes, with raw pip exit zero. Stress removal, punctuated batches, Regex Unicode/grapheme/fuzzy behavior and RPDS operations pass. The declared dlinfo package remains installed and is not imported on the explicit-library path. This also passes all 14 eSpeak C ABI checks while preserving 371 language-data files and 117 pronunciation dictionaries.

The sibling eSpeak component's C ABI test and the Python wrapper test are distinct evidence. Host patch regression tests do not prove native ABI compatibility, and this slice does not prove NeuTTS synthesis or admit the feature to production.

## Access and completion boundary

At the original **17 October acquisition checkpoint**, no access blocker was found for the selected public source and dependency artifacts. This was not a continuing availability guarantee: rolling Termux URLs later returned HTTP 404, and twelve exact original archives were retained after recovery. The combined gate additionally retains 13 original extension archives, preserving all selected versions and hashes. The current public gate passes the complete 116-dependency/183-edge environment and all eleven operation groups; independent whole-artifact/source review is complete. The separate Rust, Tiktoken, Perth and Tokenizers25 successes have completed independent artifact reviews linked above. NeuTTS itself remains excluded by its original Python upper bound. Passing its dependency environment does not remove that bound or demonstrate synthesis.

The selected Hermes AIR-q4/full-NeuCodec CPU route requires owner-supplied reference audio and its matching transcript. Its [immutable model closure](neutts-engine-closure.md) includes the gated AIR/NeuCodec weights and the public W2V-BERT model and feature extractor required by NeuCodec. Actual authorized bytes or a verified private cache must be bound to those recorded identities; body-free access metadata is not weight verification. Engine import, default initialization and synthesis remain unmeasured. The public Perth proof uses its original bundled checkpoint through the injected-model API, leaving the engine's default factory as a separate check. No watermark behavior, precision setting, dependency declaration or model path is changed by this preparation.
