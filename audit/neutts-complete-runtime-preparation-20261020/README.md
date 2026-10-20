# Complete NeuTTS dependency environment preparation

This is preparation for the next stable Termux Hermes version. It does not publish a release or admit the NeuTTS engine.

## Exact scope

The frozen original NeuTTS 1.4.1 graph has 117 distributions and 194 active dependency links. This gate excludes only the engine distribution and its 11 outgoing links. Its one isolated native environment therefore contains **116 distributions and 183 active links: 105 exact wheels and 11 unchanged APT Python payloads**.

The original engine declaration remains **Python >=3.10,<3.14**. The actual dependency target remains Android CPython 3.14.6, AArch64, API 24. All original dependency clauses, optional-extra clauses and Python declarations are retained. The selected Fsspec HTTP extra is evaluated explicitly. Nine original distributions have no Requires-Python declaration; absence is retained and normalized only when checking specifier semantics.

The full input preparation has passed on the host. **The complete native runtime has not yet passed.** Individual component evidence is retained separately; a built wheel is not represented as a successful complete-runtime test.

## Reused inputs and bounded changes

The gate reuses the original main package's selected 37 wheels, original core/public wheels, exact official Android XXHash wheel, exact native build handoffs, and 11 complete original APT Python site payloads. It does not rebuild the dependency set.

The 15 original native or patched routes are Audioop LTS, HF Xet, llama-cpp-python, NeuCodec, Numba, Pandas, Phonemizer, PyCryptodomex, PyYAML, Regex, Safetensors, Scikit-learn, SentencePiece, Tiktoken and Tokenizers. Every handoff records its actual bytes and origin. Regex comes from the already passed original Phonemizer run 39073138135. The newer Rust and Tiktoken build artifacts are explicitly marked as requiring their independent complete runtime checks.

Perth and SoundFile replace two otherwise original pure wheels with deterministic, narrowly patched derivatives. Perth uses the reviewed package resource path fix. SoundFile permits Android in its existing explicit library fallback. NeuCodec uses the reviewed Hub compatibility patch applied to its exact original universal wheel. Their dependency metadata, Python declarations and licenses are preserved.

The native setup authenticates the original signed APT snapshot, retains the original 122-package foundation, and installs or reinstalls exactly 19 original extension packages with no downloads. LibGMP is verified as already installed and is not reinstalled. The complete provenance archive union is 142. Thirteen extra original archives, totalling 2,866,600 bytes, are retained here; the remaining extra archives reuse the existing vendor and Tokenizers caches.

## eSpeak asset handoff

The proven eSpeak library and all 371 data files are extracted from the exact reviewed engine wheel as assets only. No NeuTTS Python module or distribution metadata is extracted or installed. The source engine wheel hash is recorded in the lock. The original eSpeak GPL license is retained from the earlier verified Phonemizer artifact, alongside the source wheel's own license.

The real Phonemizer wrapper and both public phonemize calls are used unchanged. Its actual temporary library copies must match the reviewed library bytes, remain inside the owned runtime temporary directory, and appear in the recorded native memory maps.

A bounded gate-only profiling callback retains each actual, successfully initialized EspeakAPI instance until the mapped-library verification finishes. It matches only the exact original constructor code and class, permits at most 32 constructor calls, and restores the previous profiling state in a finally block. This includes the otherwise temporary wrappers created by availability, version and language checks. Without that retention, the original Android finalizer can delete a copied library file while it remains mapped. The receipt records the original constructor source identity and every retained copy's path, size and hash. Package source, public calls, results and metadata remain unchanged; deleted or unowned mappings remain failures.

## What the native gate must prove

The Docker container uses the pinned ARM64 Termux image, UID 1000, two CPUs, 6 GiB memory and a 512-process limit. After authenticated APT setup, the host disconnects the owned Docker bridge, inspects the actual running container, and issues a lock-bound receipt. The child verifies the image, hostname, resource limits, empty network attachment set, loopback-only interfaces and empty routing table.

A new virtual environment excludes the global Python site. It receives the 105 wheels using exact hashes with no index, dependency resolution or bytecode compilation. The 11 APT Python payloads are copied byte-for-byte with original metadata and RECORD files.

The runtime evaluates every original active dependency relationship and executes existing public native operations for audio, Numba/LLVM, scientific Python, HF Xet, Safetensors, Tokenizers, Tiktoken, Phonemizer, llama.cpp, and the bundled public Perth watermark checkpoint. It additionally checks Datasets/Arrow/Pandas interchange, Parquet, lxml, Pillow, psutil, Transformers configuration, Torch/NumPy interchange, and real Torchtune/NeuCodec imports without speech weights.

Installed distribution names, full metadata, owned files and rewritten wheel RECORDs are verified before and after those operations. Every mapped native library must match an exact wheel/APT payload, a signed original APT archive, one of six explicitly pinned image-owned files, the reviewed eSpeak asset, or an Android system path. Global Python payload mappings are rejected.

Raw pip check diagnostics are retained. The 11 original APT wheels use Termux's older android_aarch64 platform spelling, so their expected platform diagnostics are documented rather than suppressed or reported as a passing raw pip check. Actual interpreter/ABI compatibility, complete dependency metadata and native byte provenance are separate required checks.

## Boundaries

This gate does not install or import the NeuTTS engine, change its Python bound, obtain gated speech weights, invoke speech model downloads, exercise a microphone, or publish a package. Passing this dependency gate alone does not establish full NeuTTS speech synthesis compatibility.
