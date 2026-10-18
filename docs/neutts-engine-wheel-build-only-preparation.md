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

The patch also propagates compilation-database export so the native gate can inspect actual nested commands. It preserves the existing local-source hook and default upstream Git revision, all eSpeak feature options, language selection, data generation, source files, installation rules, and the original empty nested build-type default. The native compiler remains responsible for executing the data-generation tools.

## Required native evidence

The manual/path-filtered workflow first reruns the unchanged seven-case scientific foundation. It then verifies the original compiler archives, exact installed interpreter and pip files, and the immutable Docker image identity.

The build uses an isolated venv without system site packages or a private pip installation. Exact APT pip installs only the three hash-pinned backend wheels offline. Before and after the backend runs, the gate checks the actual visible three-distribution inventory, original installed source and metadata bytes, the generated installation RECORD, and both active dependency edges.

The backend must request no additional unprepared build dependency and emit one genuinely supported Android wheel. The gate records the parent and child CMake caches, both native CMake system records, and the actual nested compilation database. Every recorded nested compile command must use the selected compiler, API 24 and ARMv8-A flags, position-independent code and both original eSpeak source flags. Conflicting target flags, response files, foreign compiler paths, source escapes and missing speech-library compilation are rejected.

The wheel must preserve all six package Python source files and the eight speaker-reference files selected by upstream installation rules. Its three eSpeak library filenames must have the same bytes as the actual nested install, and its complete language-data tree must match generated output while preserving original voice/language source files. CRC, RECORD, filename and internal wheel tags, generator identity, metadata, original license assets, ELF architecture headers and every payload member are checked.

Fourteen fresh-process C ABI cases then use the library and data extracted from that exact wheel: five original language fixtures, two repeatable IPA cases, five relocated-package cases, invalid voice handling and missing-data initialization failure. These cases do not call audio synthesis. The existing Phonemizer wrapper proof remains a separate component; this gate does not claim a full engine import or inference result.

## Host validation completed

The source preparation replay passed with all 56 NeuTTS entries, all eSpeak inputs and the exact three-wheel closure. Five real CMake acquisition/configuration cases passed: the original loss of parent target flags was reproduced, three patched propagation configurations passed, and the default source revision remained unchanged.

Those CMake fixtures use `LANGUAGES NONE` explicitly and do not claim compiler or Android ABI execution. The focused host suite passed 42 tests and 61 subtests with no skips. It covers dependency omissions, original metadata and source identity, path/interpreter preservation, conflicting compiler settings, wheel corruption and unexpected payloads, complete generated data, and image/source provenance. Synthetic ELF headers in unit fixtures exercise structural rejection only. Shell syntax and workflow parsing also passed.

The exact source pins, file hashes and raw validation receipts are saved under `audit/neutts-engine-wheel-preparation-20261017/`. Native execution has not been performed for this new gate at the source-preparation checkpoint. Review and save the gate before launching it; preserve a failed result without turning a build-only success into Python 3.14 or full-engine admission.
