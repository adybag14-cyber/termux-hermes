# NeuTTS runtime preparation routes

Updated 20 October 2026. Native component results below remain separate from
complete NeuTTS admission and real model/synthesis behavior.

## Frozen scope

This preparation preserves the complete declared NeuTTS 1.4.1 base plus `llama` dependency graph: **117 distributions and 194 active dependency edges**. It includes the Torchtune and Librosa dependency chains. Existing package versions, dependency declarations, and NeuTTS's `>=3.10,<3.14` interpreter bound remain unchanged.

The route manifest is `scripts/neutts_runtime_closure_design.json` (SHA-256 `d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68`). It copies all 194 active edges and records the exact source evidence for each distribution. It is a preparation design, not an installable lock or a production compatibility decision. The underlying graph is `audit/neutts-engine-closure-20261017/dependency-candidate.json`, SHA-256 `673d878e6fdc6fca65dfb40f8af8cade74e627b4d45f48ca995bc337cf445f06`.

## Artifact routes

| Route | Distributions | Evidence and remaining gate |
|---|---:|---|
| Reuse exact main catalog wheels | 37 | Actual wheel bytes, every CRC and RECORD digest, metadata, and catalog identities verified. Native wheel ABI and shared-library ownership must still be checked against the separate APT Python. |
| Additional existing core wheels | 6 | Exact filelock, fsspec, MarkupSafe, mpmath, NetworkX and SymPy pins retained. Three other core packages overlap the main route. |
| Existing foundation APT distributions | 6 | llvmlite, NumPy, SciPy, soxr, Torch and torchaudio. Torchcodec remains an additional required APT dependency outside the 117-node Python graph. |
| Previously validated CPU component wheels | 2 | Numba 0.67.0 and llama-cpp-python 0.3.36 passed native run 39064666810. Bind the final saved archive receipts before runtime reuse. |
| Existing native build-input wheel | 1 | Diskcache 5.6.3, unchanged. |
| Official APT extensions | 5 | PyArrow, lxml, msgpack, Pillow and psutil pass native run 39084149423: signed inputs, original metadata/tags, exact library provenance and real operations. |
| Public pure Python wheels | 45 | Exact original archives, CRC/RECORD and metadata are verified and saved. Operations remain for packages without a passed native component gate. Multiprocess retains its exact Python 3.14 wheel. |
| Patched pure Python sources | 2 | NeuCodec 0.0.4 and Phonemizer 3.3.0 preserve dependency metadata. Phonemizer's source wheel and complete public-wrapper runtime pass; real NeuCodec model operations remain. |
| Official Android wheel | 1 | XXHash 4.0.1's exact `cp314-cp314-android_24_arm64_v8a` archive, RECORD, metadata and ELF identity are verified; all seven native operation/provenance cases pass in run 39434727829. |
| Source/native builds | 12 | Regex and all six C/C++ source/runtime components have earlier native proofs. The engine wheel/bundled C ABI now pass. The standalone Tiktoken wheel builds, while its Regex retry, remaining Rust runtimes and complete integration remain incomplete. |
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

The published package still has nine restrictions. Seven repairs belong to
unpublished preparation candidates; complete NeuTTS and physical microphone/VAD
remain the two outstanding feature gates.

#### Verified b8 component results and current 4a95a07 checkpoint

The published baseline remains **9 restrictions / 7 repairs with native
preparation evidence / 2 incomplete features**. The complete NeuTTS engine and
physical microphone/VAD have not been certified.

| Exact native gate | Verified result | Limit retained |
| --- | --- | --- |
| [Engine wheel, 39434727788](../audit/neutts-engine-wheel-native-20261020/run-39434727788/REVIEW.json) | Original backend build, all 392 wheel members and CRC/RECORD checks, 117 dictionaries and all 14 bundled eSpeak C ABI cases pass. | The engine was neither installed nor imported. Its original Python >=3.10,<3.14 bound remains unchanged; no speech synthesis or Python 3.14 admission is claimed. |
| [APT extensions, 39434727717](../audit/neutts-apt-extensions-native-20261020/run-39434727717/REVIEW.json) | All five groups pass actual operations; strict original requirements and provenance pass for 12 APT distributions, with 893 regular files and 34 native files unchanged. | Raw pip still exits 1 for the 12 original legacy-tag diagnostics. No metadata or tag is rewritten. |
| [XXHash, 39434727829](../audit/neutts-xxhash-native-20261020/run-39434727829/REVIEW.json) | All seven cases pass: real import, four fixed-vector algorithm groups, streaming/seed/copy/reset and actual mapped-library provenance. | This validates the unchanged 4.0.1 Android wheel, not complete NeuTTS. |

These three b8 artifacts were each downloaded in full and checked against their
whole size/hash and every member's CRC, size and SHA-256. They supersede the
pending retry descriptions in the historical checkpoint below.

At source **4a95a07086a0b88d209485ac7a01cdd40e268f40**, both [push CI
39440363551](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39440363551)
and [PR CI 39440378190](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39440378190)
pass: **1,193 tests, 457 additional subtests and 84 skips**. The duplicate runs
are not added together, and their result does not certify later corrections.

The [HF linkage review](../audit/neutts-hf-python-linkage-20261020/REVIEW.json)
now verifies the entire 765,083,696-byte failed d215961 artifact and all 47,595
members. All four wheel builds completed before HF-Xet import failed on
_Py_FalseStruct. The exact Python runtime exports that symbol; HF's extension
omitted the libpython3.so forwarding-stub dependency. The HF-only scoped linker
correction preserves source, Cargo, ABI3 tags, TLS and versions; **170 host tests
pass with no skips**. [Corrected Rust run 39440363583](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39440363583)
advanced through actual HF import and file hashing, then failed because the
Safetensors 0.8 probe supplied the old nested-dictionary serialization shape
instead of TensorSpec. The probe is being adapted to the exact shipped API;
the complete Rust runtime still requires a passing retry.

[Standalone Tiktoken run 39440363758](../audit/neutts-tiktoken-native-20261020/run-39440363758/REVIEW.json)
built and verified the original Tiktoken wheel with the approved 27-crate lock,
then failed before Regex's backend because the verifier compared requirement
whitespace literally. The original source says "setuptools > 77.0.3"; its lock
has the equivalent canonical spelling. The correction compares parsed PEP 508
requirements while preserving exact source hashes and declarations. **35 host
tests and 50 subtests pass, no skips**; Regex construction and the complete
seven-distribution/six-edge runtime still require a successful native retry.

[Public Perth run 39440363735](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39440363735)
passed the foundation, exact 43-distribution/50-edge closure and auxiliary
operations, then failed at SoundFile library lookup before public watermark
validation. The [retained failure](../audit/neutts-soundfile-discovery-fix-20261020/NATIVE-FAILURE-REVIEW.json)
shows the original libsndfile installed. The [narrow Android fallback](../patches/next-stable/soundfile-android-library.patch)
preserves all eight wheel members except the source edit and truthful RECORD,
leaving version, metadata and Linux packaged-library behavior intact.
**62 focused tests and 232 subtests pass, no skips**; actual loading, WAV I/O,
watermark operations and final runtime provenance still require the native retry.

The complete **25-distribution/29-edge Tokenizers gate** is drafted, awaiting the
corrected native HF-Xet, Safetensors and Tokenizers wheels. Reconciliation and
execution of all **116 dependency distributions** remain public implementation
work. The full design remains 117 distributions including NeuTTS, with 194
active edges; it is not an installable or admitted Python 3.14 engine lock.
Exact gated weights, reference audio/transcript and later device tests are
additional requirements, not explanations for unfinished public dependency work.

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

## Complete Phonemizer public-wrapper slice

Phonemizer's complete selected runtime subset has **23 distributions and 26 active dependency edges**. It requires no model files and no Torch/NumPy installation.

The nine exact main wheel reuses are attrs, jsonschema, jsonschema-specifications, python-dateutil, referencing, rpds-py, six, termcolor and typing-extensions. The twelve public pure wheels are Babel, cloudpickle, csvw, dlinfo, isodate, joblib, language-tags, pyparsing, rdflib, rfc3986, segments and uritemplate. The remaining two packages are native-built Regex 2026.9.10 and the patched Phonemizer 3.3.0 wheel.

[Native run 39073138135](../audit/neutts-espeak-native-20261017/run-39073138135.json) passes both source wheel builds and the public `phonemizer.phonemize` API. It verifies all 23 distributions, 26 active edges and 1,756 original installed file hashes, with raw pip exit zero. Stress removal, punctuated batches, Regex Unicode/grapheme/fuzzy behavior and RPDS operations pass. The declared dlinfo package remains installed and is not imported on the explicit-library path. This also passes all 14 eSpeak C ABI checks while preserving 371 language-data files and 117 pronunciation dictionaries.

The sibling eSpeak component's C ABI test and the Python wrapper test are distinct evidence. Host patch regression tests do not prove native ABI compatibility, and this slice does not prove NeuTTS synthesis or admit the feature to production.

## Access and completion boundary

At the original **17 October acquisition checkpoint**, no access blocker was found for the selected public model-free source and dependency artifacts. This was not a continuing availability guarantee: rolling Termux URLs later returned HTTP 404, and twelve exact original archives have now been retained after recovery. Remaining work is to finish the Rust and XXHash operations, the complete Perth subset, corrected engine-wheel verification, exact component output handoffs and the full 117-distribution environment. Passing individual components does not remove the original Python upper bound.

Full default NeuTTS synthesis additionally requires authorized access to the exact gated GGUF and NeuCodec repositories documented in `docs/neutts-engine-closure.md`, and reference audio plus its transcript. The authorized public Resemble-Perth dependency wheel includes an embedded checkpoint; any later download must record those checkpoint bytes explicitly. No watermark behavior, precision setting, dependency declaration or model path is changed by this preparation.
