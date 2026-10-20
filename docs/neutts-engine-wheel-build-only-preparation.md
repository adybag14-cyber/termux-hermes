# NeuTTS engine wheel: build-only preparation

This gate prepares the exact NeuTTS 1.4.1 source for a native Android wheel build and checks the eSpeak library and language data inside the resulting wheel. It does not install or import the engine, widen its Python version range, fetch external model weights, run inference, or change package-manager admission. A successful result is named `passed-build-and-bundled-cabi-only`.

The original project metadata still requires Python `>=3.10, <3.14`. The experiment uses the existing native CPython 3.14.6 build toolchain through the PEP 517 backend directly. Producing a wheel before full synthesis is useful source and packaging evidence; its unchanged metadata continues to exclude installation on Python 3.14. No pip compatibility override or retagging is used.

## Exact inputs and preserved scope

| Input | Selection |
| --- | --- |
| NeuTTS | 1.4.1, commit `b7a3427d0d25e20e8b9e92cbaae688f732916baf`, original archive 3,037,279 bytes |
| eSpeak NG | commit `69bfd1efde0236654ccc117a28d04aef27673a30`, original archive 18,493,532 bytes |
| Build Python closure | scikit-build-core 1.1.1, packaging 26.0, pathspec 1.1.1; exactly three distributions and two active dependency edges |
| Python wheel bytes | 425,144 bytes, identical records and artifacts to the already tested native compiler preparation |
| Compiler inputs | Original 44 exact APT archives and 19 compiler additions, unchanged |
| Additional retained archive | Already-installed python-pip 26.2.1, download only, for full interpreter/pip provenance |
| Native target | Bionic aarch64, Android API 24, ARMv8-A, two jobs, six GiB address-space limit |
| External model access | None; all original source assets remain included, including its small bundled speaker reference tensors |

All 56 original NeuTTS source paths remain present. The source wheel preparation changes only `CMakeLists.txt` on top of the existing offline eSpeak source hook; the other 55 entries, including `pyproject.toml`, remain byte-identical. All 2,606 eSpeak source entries remain, including its original header symlink and the previously reviewed explicit-OFF Sonic acquisition guard.

The project retains all nine base requirements, all six optional requirement entries across its three extras, the original author and description, and the complete original README in generated metadata. The build dependency lock retains every declared conditional and optional requirement; only the two dependencies active in the actual default build environment are installed.

## Source correction

The upstream nested eSpeak CMake invocation replaces C and C++ flags with two hardcoded source-specific flags. That discards the parent Android API and architecture flags. The new companion patch passes the selected parent C/C++ compiler paths, C/C++ flags, and executable/shared/module linker settings into the nested build while appending the two original eSpeak flags.

The patch also propagates compilation-database export so the native gate can inspect actual nested commands. It preserves the existing local-source hook and default upstream Git revision, all eSpeak feature options, language selection, data generation, source files, installation rules, and the nested build type selected by the pinned native CMake platform initializer. The native compiler remains responsible for executing the data-generation tools.

## Required native evidence

The manual/path-filtered workflow first reruns the unchanged seven-case scientific foundation. It then verifies the original compiler archives, exact installed interpreter and pip files, and the immutable Docker image identity.

The build uses an isolated venv without system site packages or a private pip installation. Exact APT pip installs only the three hash-pinned backend wheels offline. Before and after the backend runs, the gate checks the actual visible three-distribution inventory, original installed source and metadata bytes, the generated installation RECORD, and both active dependency edges.

The backend must request no additional unprepared build dependency and emit one genuinely supported Android wheel. The gate records the parent and child CMake caches, both native CMake system records, and the actual nested compilation database. Every recorded nested compile command must use the selected compiler, API 24 and ARMv8-A flags, position-independent code and both original eSpeak source flags. Conflicting target flags, response files, foreign compiler paths, source escapes and missing speech-library compilation are rejected.

The wheel must preserve all six package Python source files and the eight speaker-reference files selected by upstream installation rules. Its three eSpeak library filenames must have the same bytes as the actual nested install, and its complete language-data tree must match generated output while preserving original voice/language source files. CRC, RECORD, filename and internal wheel tags, generator identity, metadata, original license assets, ELF architecture headers and every payload member are checked.

Fourteen fresh-process C ABI cases then use the library and data extracted from that exact wheel: five original language fixtures, two repeatable IPA cases, five relocated-package cases, invalid voice handling and missing-data initialization failure. These cases do not call audio synthesis. The existing Phonemizer wrapper proof remains a separate component; this gate does not claim a full engine import or inference result.

## Host validation completed

The source preparation replay passed with all 56 NeuTTS entries, all eSpeak inputs and the exact three-wheel closure. Five real CMake acquisition/configuration cases passed: the original loss of parent target flags was reproduced, three patched propagation configurations passed, and the default source revision remained unchanged.

Those CMake fixtures use `LANGUAGES NONE` explicitly and do not claim compiler or Android ABI execution. The focused host suite passed 42 tests and 61 subtests with no skips. It covers dependency omissions, original metadata and source identity, path/interpreter preservation, conflicting compiler settings, wheel corruption and unexpected payloads, complete generated data, and image/source provenance. Synthetic ELF headers in unit fixtures exercise structural rejection only. Shell syntax and workflow parsing also passed.

The exact source pins, file hashes and raw validation receipts for that initial checkpoint are saved under `audit/neutts-engine-wheel-preparation-20261017/`. The later native result and verifier correction are recorded below.

## Native result and verifier correction — 20 October 2026

[Run 39084452780](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084452780), source `4fe7b8f2d6e7d43de3457e372fe1285c0acd14d3`, completed the backend and the isolated build-environment checks. Its emitted wheel was 10,869,139 bytes, SHA-256 `6813696b028e1d11aa25d423d45e9ad782d6a2bc91ccd139bf4859c98ae04091`. The subsequent actual nested-toolchain verifier failed because it expected an empty `CMAKE_BUILD_TYPE`. This failed run did not reach complete wheel-content/data or bundled C ABI admission.

The original pinned CMake 4.4.4 APT archive contains an Android initialization module that sets `CMAKE_BUILD_TYPE_INIT` to `RelWithDebInfo` before its native-Android early return. Its unchanged configuration initializer uses that default unless the caller explicitly sets a build type. The actual parent cache records `Release`; the actual nested cache records `RelWithDebInfo`. API 24, ARMv8-A and the original common/source flags remain in the recorded commands.

The correction changes only the lock's expected nested value, the preparer's lock digest, and the verifier's comparison. It does not add a source or backend build-type override. Parent `Release`, compiler paths, target flags, the original source patch, all metadata, all dependency archives and the original Python bound remain unchanged.

[The retained correction evidence](../audit/neutts-engine-wheel-cmake-fix-20261020/REVIEW.json) binds the original 49,728,270-byte artifact (SHA-256 `4d7250c50477155e6f2331f11adaa6a8bf755075ffaa8fc3fbb1d153bcb4330f`) and all 237 original ZIP member identities. It also binds the exact 10,645,092-byte CMake APT archive and the three original module bodies. Tests retain the actual caches, native CMake system records, compilation database and old verifier.

The updated focused suite passes **50 tests and 78 subtests with no skips**. Eight new tests reproduce the old rejection, accept the unchanged native records after correction, reject missing/incorrect build types and altered target/compiler settings, and execute the three unchanged CMake 4.4.4 module bodies with real host CMake 4.2.1. Recorded POSIX path replay is explicitly lexical; it does not prove native filesystem resolution. Module execution does not repeat native compilation.

A fresh native workflow must still pass the complete wheel-content, language-data and all fourteen bundled C ABI checks. Neither this host correction nor the failed backend run establishes an installed engine, Python 3.14 admission, model inference or synthesis.
