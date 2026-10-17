# Phonemizer 3.3.0: defer dlinfo discovery for the Android eSpeak path

Status: exact-source compatibility preparation, 17 October 2026. The saved patch is independently replayable. It has not been installed in a package or certified against a native Android eSpeak library.

## Concrete failure and scope

Phonemizer 3.3.0 imports `dlinfo` when its eSpeak API module is imported on any platform other than Windows. The declared dlinfo 2.0.0 package dispatches Android to its glibc implementation, which immediately resolves `libdl.dlinfo`. Bionic's public header and export map at commit `731631f300090436d7f5df80d50b6275c8c60a93` have no such declaration or exported symbol. A failure at that import prevents callers from reaching Phonemizer's already-existing explicit-path branch.

The exact NeuTTS 1.4.1 source locates its bundled eSpeak shared library and calls `EspeakWrapper.set_library` with that file path. Phonemizer's existing `_shared_library_path` can return an existing explicit path without any dlinfo lookup. The eager module import needlessly blocks that route.

The source evidence is reproducible from these primary artifacts:

| Source | Exact identity |
| --- | --- |
| [Phonemizer 3.3.0 source](https://files.pythonhosted.org/packages/c4/ff/3574c55a71b42ad6944a5bf0a7d59f0251ea2ba47e51a5c4005e32e9145c/phonemizer-3.3.0.tar.gz) | 88,564 bytes; SHA-256 `5e0c38122effe0b331a24e674aff256874ece169d70a9cf1120337b56f8e3d0c` |
| [dlinfo 2.0.0 source](https://files.pythonhosted.org/packages/85/8e/8f2f94cd40af1b51e8e371a83b385d622170d42f98776441a6118f4dd682/dlinfo-2.0.0.tar.gz) | SHA-256 `88a2bc04f51d01bc604cdc9eb1c3cc0bde89057532ca6a3e71a41f6235433e17` |
| [Bionic dlfcn.h](https://android.googlesource.com/platform/bionic/+/731631f300090436d7f5df80d50b6275c8c60a93/libc/include/dlfcn.h) | Decoded bytes SHA-256 `134558a19eaed3763c7f2b304b91637f67820363569571da67c3ac257f338d90` |
| [Bionic libdl exports](https://android.googlesource.com/platform/bionic/+/731631f300090436d7f5df80d50b6275c8c60a93/libdl/libdl.map.txt) | Decoded bytes SHA-256 `66f84b25cbf6548d0bf27eec414e872d51709be9a478281c49d54ded9d7f0823` |
| [NeuTTS phonemizer setup](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/neutts/phonemizers.py) | SHA-256 `737d1138839271f06bf762552de376f1c6816460bbf5855b51192b717d67d9cb` |

This is a source/API incompatibility finding. The symbol evidence and source tests do not replace a runtime check against the actual target Bionic library.

## Repair

`patches/next-stable/phonemizer-lazy-dlinfo.patch` removes the top-level dlinfo import and imports it inside the existing unresolved-path fallback, after the existing file-path check.

An explicit existing eSpeak path therefore succeeds through the same path resolver without importing dlinfo. An unresolved library name on Linux or macOS still calls the existing dlinfo implementation. Failures during fallback still produce the same public RuntimeError with suppressed underlying context. KeyboardInterrupt and SystemExit continue to propagate.

Windows keeps its existing behavior: it never imports dlinfo, even when a path cannot be resolved. An explicit guard inside the fallback feeds the same existing RuntimeError translation. This avoids introducing the import that upstream specifically excludes on Windows.

The patch changes one production file and adds one source-regression test file. All other 55 files from the exact 56-file source archive are byte-identical, including all package and dependency metadata. The dlinfo requirement remains. No native loader, model choice, precision, engine pin, watermark behavior or interpreter bound changes.

## Verification

The 30-case suite executes the entire production `api.py` and its actual `voice.py` source. It controls only the platform value and dlinfo import boundary. Its temporary files are path fixtures, not compiled shared libraries, and it does not call ctypes to load them.

| Evidence | Result |
| --- | --- |
| Exact upstream source with the new regression suite | 17 failed, 13 passed |
| Patch replayed into a fresh source tree | 30 passed |
| Ordinary Linux and macOS unresolved-name fallback controls | Passed |
| Explicit string/Path/relative-path cases, including paths with spaces | Passed |
| Missing package, missing symbol and discovery error translation | Passed |
| Windows import restriction and control-flow exception propagation | Passed |
| Apply and reverse-apply checks against a clean original index | Passed |
| All replayed file bytes compared to the isolated patched source | Matched |
| Whitespace check and Python 3.8 grammar parse | Passed |

The final patch is 10,102 bytes, SHA-256 `cd1406f9a005ac56fe24c2da491631d1842c404c4d71c99db5e01ba6fc92e7f5`. The original index tree is `1e6107e46d7cef4671d5f89b3b7b2577e4de16a2`; the replay tree is `2ee3fc844c23293f062fe67f1fdcb51075ddb9b3`. These are local Git tree identities; this preparation created no commit.

`audit/phonemizer-dlinfo-20261017.json` retains the exact source archive manifest, dependency metadata, Bionic retrieval receipts, changed source/test identities, replay checks and complete baseline/final test output. Early test harness cache warnings were removed by disabling pytest's cache provider; the final baseline and patched runs have no warnings.

## Remaining gate

Build the exact NeuTTS-pinned eSpeak source and its data, install a wheel built from this patch in the separate engine environment, then exercise actual phonemization on the target Android/aarch64 interpreter. Test both configured explicit-path use and a supported discovery control, and verify the bundled language data. A successful source regression does not certify phonemization or full NeuTTS synthesis. The model access and remaining software closure are documented separately in `docs/neutts-engine-closure.md`.

This is saved next-stable preparation. It does not publish a package or change the current release.
