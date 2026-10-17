# NeuTTS runtime preparation routes

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
| Official APT extensions | 5 | PyArrow, lxml, msgpack, Pillow and psutil. All five archive and control identities and declared Python requirements verified; native signature, provenance, original-tag diagnostics and operations remain required. |
| Public pure Python wheels | 45 | Exact artifact candidates recorded; downloads, RECORD/metadata verification, and actual operations remain. Multiprocess uses its exact Python 3.14 wheel. |
| Patched pure Python sources | 2 | NeuCodec 0.0.4 and Phonemizer 3.3.0; independently reviewed patches preserve dependency metadata. Actual wheels must be built and verified. |
| Official Android wheel | 1 | XXHash 4.0.1 has an exact `cp314-cp314-android_24_arm64_v8a` candidate. Verify bytes and native behavior before use. |
| Source/native builds | 12 | Exact sources and declared build requirements inspected. Build-tool/Cargo closures and compilation remain. |
| **Total** | **117** | No graph nodes omitted. |

The actual main catalog contains 100 wheels, 38 of which have exact version matches in the engine graph. Their archive hashes and complete declared requirement sets were independently checked. Pillow uses the official APT route, leaving 37 selected main wheels and avoiding a second OpenJPEG/native provenance route. Main MarkupSafe 3.0.3 and psutil 8.0.0 do not match the frozen graph and are not reused.

The original 68,318-byte main catalog has SHA-256 `d2dc66575cf8aa5ef828e5e536b4d55b8801143101b7e608f6fb4878c2397904`. Its exact records, including original source fingerprints, are preserved under `audit/neutts-runtime-reuse-20261017/`.

## Five APT extensions and archive drift

The selected roots are `python-pyarrow=26.0.0-2`, `python-lxml=6.1.3`, `python-msgpack=1.2.3`, `python-pillow=12.3.0`, and `python-psutil=7.2.2-2`. Their package dependency closure contains **78 packages and 151 edges**. After the existing 122-package foundation and 44-package compiler closure are accounted for, **18 archives totalling 14,043,104 bytes** remain:

apache-orc, libarrow-cpp, libgcrypt, libgpg-error, libimagequant, liblz4, libraqm, libre2, libsnappy, libxslt, openjpeg, python-lxml, python-msgpack, python-pillow, python-psutil, python-pyarrow, thrift and utf8proc.

The fresh official InRelease/Packages pair was fetched at 20:05 UTC on 2026-10-17. Packages.gz SHA-256 `dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6`, 727,968 bytes, matches the SHA256 section in InRelease SHA-256 `249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901`. This is a host hash-binding check; native OpenPGP verification remains a required gate.

The index differs from the earlier native snapshot. **All 122 foundation and all 44 compiler archive identities still match** by package, version, architecture, size, SHA-256 and repository filename. No existing archive has drifted. The native APT solver must still verify the exact complete plan with no unrecorded dependency substitutions.

All five extension .deb archives were actually downloaded and inspected. Their control fields match the pinned index, and their original METADATA requirements match the frozen graph. Their original WHEEL tags use `android_aarch64`: four use CPython 3.14 tags, while psutil uses `cp36-abi3-android_aarch64`. Those tags are preserved. The existing foundation's provenance approach must be extended with exact archive/control/installed-file evidence and real operations; filename resemblance or a metadata rewrite cannot establish compatibility.

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

The frozen NumPy 2.5.4 and SciPy 1.18.1 satisfy the scientific build bounds above. Current official APT metadata offers Maturin 1.15.0, Rust 1.99.1 and LibYAML 0.2.5-5. Those are availability observations; their additional dependency archives, Cargo inputs and Python build tools still need exact closure verification. No blanket foundation rebuild or version change is implied.

## First executable slice: real Phonemizer wrapper

Phonemizer's complete selected runtime subset has **23 distributions and 26 active dependency edges**. It requires no model files and no Torch/NumPy installation.

The nine exact main wheel reuses are attrs, jsonschema, jsonschema-specifications, python-dateutil, referencing, rpds-py, six, termcolor and typing-extensions. The twelve public pure wheels are Babel, cloudpickle, csvw, dlinfo, isodate, joblib, language-tags, pyparsing, rdflib, rfc3986, segments and uritemplate. The remaining two packages are native-built Regex 2026.9.10 and the patched Phonemizer 3.3.0 wheel.

The preparer will verify every artifact, RECORD entry and declaration before staging. Native preparation will use isolated build and runtime environments under the exact APT Python 3.14.6, preserve all declared runtime requirements, and build Regex with the frozen compiler and Setuptools. The runtime must verify all 23 installed distributions and all 26 active edges, run actual native Regex and RPDS operations, and execute the public `phonemizer.phonemize` API using the separately verified eSpeak shared library and data. The explicit-library route must complete without importing dlinfo.

The sibling eSpeak component's C ABI test and the Python wrapper test are distinct evidence. Host patch regression tests do not prove native ABI compatibility, and this slice does not prove NeuTTS synthesis or admit the feature to production.

## Access and completion boundary

No access blocker was found for the selected public model-free source and dependency artifacts. Concrete work remains: freeze build-tool inputs, compile the missing sources, validate the separate APT Python ABI and library ownership, and exercise actual package operations.

Full default NeuTTS synthesis additionally requires authorized access to the exact gated GGUF and NeuCodec repositories documented in `docs/neutts-engine-closure.md`, and reference audio plus its transcript. The authorized public Resemble-Perth dependency wheel includes an embedded checkpoint; any later download must record those checkpoint bytes explicitly. No watermark behavior, precision setting, dependency declaration or model path is changed by this preparation.
