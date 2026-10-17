# NeuTTS full default engine closure: next stable preparation

Status: source and metadata audit, 17 October 2026. No model payloads were downloaded. This audit does not certify synthesis, latency, memory use, or the complete engine on Android.

## What Hermes actually requests

The released Hermes helper `tools/neutts_synth.py` selects `neuphonic/neutts-air-q4-gguf`, CPU execution, and the full `neuphonic/neucodec` codec. It requires a reference recording and its transcript, calls `encode_reference`, then `infer`, and writes 24 kHz audio. The investigated NeuTTS source is version 1.4.1 at commit `b7a3427d0d25e20e8b9e92cbaae688f732916baf`. The default engine class and other optional backends do not change this Hermes-selected path.

The full codec constructor loads Wav2Vec2-BERT for semantic reference encoding, an acoustic encoder and finite scalar quantizer, and a Vocos-based decoder. NeuCodec 0.0.4 explicitly requests `pytorch_model.bin`; the larger `model.safetensors` in the same repository is a different artifact and is excluded from this default tally. The ONNX decoder branch does not establish compatibility of reference encoding.

Source evidence: [Hermes helper](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/neutts_synth.py), [NeuTTS source](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/neutts/neutts.py), and the exact NeuCodec 0.0.4 source identity recorded in the accompanying audit.

## Exact model closure and verified access boundary

| Repository | Immutable revision | Selected weight file | Advertised bytes | License in public model metadata | Unauthenticated HEAD |
| --- | --- | --- | ---: | --- | --- |
| neuphonic/neutts-air-q4-gguf | `0f54a5513ee49708713e49c5122c274df2737047` | `neutts-air-Q4_0.gguf` | 527,054,304 | Apache-2.0 | 401, GatedRepo |
| neuphonic/neucodec | `a940021324df13a07f44185f0a17c6dac3698179` | `pytorch_model.bin` | 1,160,509,432 | Apache-2.0 | 401, GatedRepo |
| facebook/w2v-bert-2.0 | `da985ba0987f70aaeb84a80f2851cfac8c697a7b` | `model.safetensors` | 2,322,063,736 | MIT | 302 with matching linked size and SHA-256 |

These three weight files total **4,009,627,472 bytes (about 3.734 GiB)**. Public metadata also identifies codec `config.json` and `meta.yaml`, and Wav2Vec2-BERT `config.json` and `preprocessor_config.json`. Their exact sizes and Git blob identities are in the audit. GGUF repository `meta.yaml` is recorded as an additional small repository asset.

The model API responses are saved byte-for-byte. Their advertised LFS SHA-256 values are recorded separately from the hashes of those API responses. The weight hashes have **not** been verified against downloaded weight bytes.

At 19:23 UTC on 17 October, bounded HEAD requests to the immutable URLs returned `401 GatedRepo` for both Neuphonic weights. No authorization was supplied, no redirects were followed, and zero response-body bytes were read. The public API describes both repositories as gated and their access forms request affiliation and role information. The Wav2Vec2-BERT request returned a redirect with the expected commit, linked size and linked SHA-256; its payload was not downloaded either.

To run actual default synthesis later, the authorized operator must already have, or obtain, legitimate access to both Neuphonic repositories. An existing authorized cache containing the exact required artifacts could also be used. The operator must supply their own truthful access information and handle credentials through the normal secure workflow. Reference audio and its matching transcript are also required by the Hermes helper. This preparation neither accepts model gates nor changes the engine to another model.

Primary metadata: [GGUF](https://huggingface.co/api/models/neuphonic/neutts-air-q4-gguf?blobs=true), [NeuCodec](https://huggingface.co/api/models/neuphonic/neucodec?blobs=true), [Wav2Vec2-BERT](https://huggingface.co/api/models/facebook/w2v-bert-2.0?blobs=true). The immutable request URLs, selected headers, dates, raw metadata hashes and file identities are preserved in `audit/neutts-engine-closure-20261017/`.

## Python closure: all declared dependencies retained

A metadata-only candidate graph contains **117 distributions and 194 active dependency edges** for `neutts[llama]==1.4.1` under CPython 3.14.6 on Android/aarch64. It retains the complete declared NeuCodec, Torchtune, Datasets, Librosa and Hub graph. It does not delete training dependencies because the inference call appears to need only part of them.

The graph satisfies every active dependency version clause. One package's declared Python bound still fails: **NeuTTS 1.4.1 requires Python >=3.10,<3.14**. All other selected distributions permit this interpreter in their metadata; that says nothing about their import behavior, Bionic symbols, source builds or numerical behavior. Unused platform release/version fields inherited by the exploratory graph are omitted from the saved candidate environment; no requirement in the graph uses them.

This graph is a feasibility witness, not an installable lock. It records every selected version, all declared requirements, propagated extras, exact metadata response identity and relevant source/pure/Android artifact identities. It is separate from all existing package locks. The distribution count is not a count of disabled Hermes features. Build-system dependencies and transitive APT control dependencies are additional work outside the 117 Python distributions.

Important intersections are:

| Dependency group | Required intersection and consequence |
| --- | --- |
| NeuTTS / Transformers | NeuTTS retains exact Transformers 5.1.0. That requires Hub >=1.3,<2 and Tokenizers >=0.22,<=0.23.0. The metadata witness uses Tokenizers 0.22.2; the existing Hermes 0.23.1 preference does not satisfy this engine constraint. |
| NeuTTS / audio | Exact Librosa 0.11.0 and SoundFile 0.13.1 remain. SoundFile 0.14.0 from another environment cannot substitute for the declared exact pin. |
| Numba / scientific foundation | Numba 0.67.0 intersects the verified APT NumPy 2.5.4 and llvmlite 0.49.0. Pandas 3.0.6 requires NumPy >=2.3.3 on Python 3.14, also satisfied by 2.5.4. |
| Datasets / Hub / fsspec | Candidate Datasets 5.1.0 requires Hub >=1.31,<3, fsspec[http] >=2023.1,<=2026.7 and PyArrow >=24. The witness uses Hub 1.31.0, fsspec 2026.7.0 and PyArrow 26.0.0, satisfying Transformers' Hub <2 ceiling and preserving the foundation fsspec version. |
| Hub / Xet | Hub 1.31.0's aarch64 marker activates hf-xet. Turning off Xet transport at runtime does not remove this declared distribution requirement. The candidate retains hf-xet 1.6.0. |
| Librosa / removed stdlib audio modules | Python >=3.13 activates standard-aifc and standard-sunau; audioop-lts 0.2.2 is reached transitively. These remain in the graph. |

The exploratory preference for psutil 8.0.0 returned HTTP 404 from that exact public PyPI metadata URL. The witness selects 7.2.2, which also has a pinned Termux APT artifact. This is a separate environment choice and source-availability observation; it is not a conclusion that the already-tested Hermes package is broken.

## Concrete software work still possible without model access

The scientific foundation already has native evidence in Actions run **39058569758**. It covers its exact 122-APT/9-wheel closure and seven foundation gates; it does not cover the complete engine. Numba and llama.cpp components are being handled by their separate CPU gate. Their outcome must be recorded in the corresponding CPU evidence before being used as a prerequisite here.

The metadata graph has **21 distributions with neither a pure wheel nor an Android wheel in the inspected PyPI file lists**, excluding six already-covered scientific APT distributions. Five of those 21 have exact-version candidates in the pinned Termux index; two are the separate Numba/llama work. Fourteen therefore need a source-build or verified compatible artifact route beyond those two groups. This is an artifact availability classification, not 21 proven native failures. Pure wheels can still call incompatible native APIs, as the Phonemizer/dlinfo finding demonstrates.

| Next bounded work | Exact candidates and evidence | Required check |
| --- | --- | --- |
| Source repairs already identified | NeuCodec 0.0.4 Hub 1 download arguments; separate 34-case source regression preparation is saved. Phonemizer 3.3.0 eagerly imports dlinfo 2.0.0, which binds a symbol absent from Bionic. | Replay source patches and preserve all requirements. Phonemizer should defer dlinfo until its unresolved-library-path fallback; the explicit eSpeak path can then proceed without that import. |
| APT extension closure | python-pyarrow 26.0.0-2, python-lxml 6.1.3, python-msgpack 1.2.3, python-pillow 12.3.0, python-psutil 7.2.2-2 have exact index filenames, sizes, SHA-256 and Depends recorded. | Freeze and verify complete APT control dependencies, including libarrow-cpp =26.0.0-2, and exercise the actual native extension operations. Availability is not installed/runtime evidence. |
| Pandas and scikit-learn | Pandas 3.0.6 source bytes verified; scikit-learn 1.9.1 primary build specification inspected. Both can share meson-python >=0.17.1,<0.22 and Cython >=3.1.2,<3.2.6, with the existing NumPy/SciPy bounds. Pandas also needs Meson >=1.2.1,<2 and versioneer[toml]. | Freeze the full build dependency closure, compile against the same interpreter/scientific stack, then test numerical operations and the Librosa use path. No successful build is claimed. |
| Rust bindings | Verified source archives: hf-xet 1.6.0 (maturin, PyO3 0.29, abi3-py38); Tokenizers 0.22.2 (maturin, PyO3 0.26, abi3-py39); Safetensors 0.8.0 (maturin, PyO3 0.28, abi3-py310); Tiktoken 0.14.0 (setuptools-rust, PyO3 0.29.2). | Freeze cargo/toolchain dependencies and build Android artifacts, preserving the exact selected versions. abi3 declarations alone do not establish Bionic compatibility. |
| Other compiled or native-backed packages | Cffi 2.1.1, PyYAML 6.0.3, Regex 2026.9.10, SentencePiece 0.2.2, PyCryptodomex 3.24.1, RPDS-py 2026.6.3, plus verified audioop-lts 0.2.2 source. | Reuse only artifacts whose hash, Python ABI and native libraries match this separate interpreter, otherwise compile exact source and run functional checks. |
| Pure Python engine path | Torchtune 0.3.1, TorchAO 0.12.0 and all their declared dependencies remain. Librosa and Transformers remain exact engine versions. | Exercise model-free rotary embedding, tensor, tokenization, feature extraction and audio paths against the real native stack. Imports alone are insufficient. |
| NeuTTS and phonemizer packaging | Exact NeuTTS source uses scikit-build-core and CMake >=3.26, and pins eSpeak commit 69bfd1efde0236654ccc117a28d04aef27673a30, shared library plus data. | Build and exercise that exact eSpeak path and data; preserve enabled language assets. The index's eSpeak 1.52.0-1 is not the pinned source. Defer widening the NeuTTS Python bound until evidence supports that change. |

Scikit-learn's examined build constraints additionally require NumPy >=2,<2.6 and SciPy >=1.10,<1.19, which intersect the established NumPy 2.5.4/SciPy 1.18.1 foundation. Its [primary pyproject](https://github.com/scikit-learn/scikit-learn/blob/1.9.1/pyproject.toml) hash and the verified archive build specifications are recorded in the audit.

The narrow next sequence is to finish Numba/llama native gates, complete the two source compatibility patches, freeze the five APT extension routes and the remaining build dependencies, build the separate engine environment, and run model-free operations. This does not require accepting a model gate. Full reference encoding, default synthesis, waveform checks, peak memory and latency must wait for authorized model inputs and then run as an additional gate.

Changing to Python 3.13 would satisfy NeuTTS's published bound but would require rebuilding or replacing the CPython 3.14 scientific closure. It is not a simple way to reuse the current foundation. Keeping 3.14 and making a reviewed upstream-source port is a plausible preparation path, with the upper bound unchanged until its compatibility evidence exists.

## Watermark, precision and capacity

The exact engine calls Perth's implicit watermarker when available and preserves its existing visible warning on supported initialization failure paths. Resemble-Perth 1.0.1 declares no Python runtime dependencies in its package metadata, but its implementation uses the audio and tensor stack supplied by the rest of this closure. The inspected Perth tree contains `perth_net_250000.pth.tar` at 37,429,684 bytes. Its source tree Git blob identity is recorded; its payload was not downloaded. The published 1.0.1 wheel is 34,404,578 bytes and contains model assets, so it was not fetched during this no-model audit.

NeuTTS's exact CMake file also packages the four built-in 2E reference speaker assets. They are recorded from the source tree; they are not silently removed from the proposed build. NeuTTS and the Neuphonic model metadata use Apache-2.0, Perth uses MIT, and the pinned eSpeak source carries GPL-3.0. Distribution decisions must preserve the applicable upstream license material.

The GGUF serialized weight size does not describe the whole engine's memory. Wav2Vec2-BERT metadata alone reports 580,493,120 F32 parameters, or 2,321,972,480 tensor bytes. Its activations, the full codec, checkpoint loading, GGUF context/KV cache, allocator overhead and optional watermark add to that. The default CPU GGUF setup requests a 2,048-token context, batch and microbatch 512, zero GPU layers and memory locking. Actual peak resident memory and latency remain unmeasured.

For planning, an 8 GiB initial CPU test allowance is a conservative starting allocation, not a measured minimum or a hardware support promise. Staging duplicate copies of the three default weight files alone would require about 8.02 GB before packages and caches; actual cache layouts may share data. The test must preserve the normal codec precision, reference encoding and watermark behavior and measure memory directly. No lower-precision conversion or decoder shortcut is part of this preparation.

## Saved evidence

- `audit/neutts-engine-closure-20261017.json`: scope, source identities, model closure, graph summary, native routes and limits.
- `audit/neutts-engine-closure-20261017/dependency-candidate.json`: all 117 nodes and 194 active edges with exact metadata/artifact identities.
- The same directory contains the three raw model API responses, their receipts, the body-free HEAD record, pinned APT availability and verified source-build observations.

All files are next-stable preparation. This audit changes no package pin, interpreter requirement, dependency declaration, model behavior or release version.
