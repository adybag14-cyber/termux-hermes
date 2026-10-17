# NeuTTS default GGUF feasibility on native Termux


## Current native status

The initial source-only checkpoint below is retained as historical analysis.
[Native run 39064666810](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39064666810)
has since built and tested the patched Llama binding and Numba on Bionic
AArch64/Python 3.14.6, after all seven scientific foundation cases passed.
Llama backend initialization, default model/context parameters, CPU capability
reporting and exact loaded libraries passed; Numba executed real nopython JIT
and generalized-vector operations.
[The complete result](../audit/neutts-native-20261017/run-39064666810.json)
preserves the wheel identities, commands and raw native observations.

These results establish the tested CPU components. A complete installed
NeuTTS engine, authorized model weights, reference encoding and generated
speech remain separate work. The current
[117-distribution runtime preparation](neutts-runtime-preparation.md) and
[remaining portability work](remaining-portability-work.md) track that status.


Status: **source review and an isolated loader experiment; NeuTTS is not admitted
to the managed package graph**. This work does not change the published package,
the main Hermes compatibility patch, the NeuTTS probe, or its dependency locks.
It does not establish native inference, model compatibility, or audio-device
support.

The exact source and artifact identities are recorded in
[`neutts-default-gguf-source-20261017.json`](../audit/neutts-default-gguf-source-20261017.json).
Artifact metadata and archives whose bytes were actually inspected are identified
separately there.

## The default path that must eventually work

Hermes v0.22.2's `tools/neutts_synth.py` chooses
`neuphonic/neutts-air-q4-gguf`, the full `neuphonic/neucodec` codec, and a supplied
reference WAV plus transcript. NeuTTS 1.4.1 at
[`b7a3427d0d25e20e8b9e92cbaae688f732916baf`](https://github.com/neuphonic/neutts/tree/b7a3427d0d25e20e8b9e92cbaae688f732916baf)
loads the reference through Librosa as 16 kHz mono audio, encodes it with Torch,
generates speech tokens through llama-cpp-python, and decodes a 24 kHz waveform.

Full NeuCodec 0.0.4 constructs both its acoustic encoder and
`facebook/w2v-bert-2.0` semantic model. That model is an additional weight input,
alongside the GGUF and codec checkpoint. The ONNX codec branches are decoder-only:
they do not implement this reference encoder. A preencoded-reference or ONNX
decoder experiment must not stand in for the existing default.

See the engine's
[`encode_reference`, `_load_codec`, and `_decode`](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/neutts/neutts.py)
and [NeuCodec 0.0.4 metadata](https://pypi.org/pypi/neucodec/0.0.4/json).

## Source findings and bounded candidates

These versions are reviewed candidates unless explicitly pinned by NeuTTS. They
are not a complete independently resolved engine closure.

| Component | Finding | Remaining gate |
| --- | --- | --- |
| NeuTTS 1.4.1 | Declares Python `>=3.10,<3.14`; pins Librosa 0.11.0, Transformers 5.1.0 and Perth 1.0.1. | An explicit reviewed Python 3.14 source port; no production marker removal from this review. |
| Numba 0.67.0 | Its source allows Python 3.14, llvmlite `>=0.49.0dev0,<0.50`, and NumPy `<2.6`. Existing APT Python 3.14.6, llvmlite 0.49.0 and NumPy 2.5.4 fit. No general Android CPU-JIT exclusion was found. | Native extension build and real JIT/gufunc behavior. No official Android wheel was listed. Optional TBB/OpenMP can be disabled for a first CPU gate. |
| Librosa 0.11.0 | The actual reference-loading path uses SoundFile/Audioread, SciPy, Soxr and Numba; its default resampler is `soxr_hq`. | Exercise a known local PCM fixture through `load(sr=16000, mono=True)`; freeze its declared Python 3.14 dependencies too. |
| scikit-learn 1.9.1 | Required by stock Librosa, though not directly called by this load path. Its Python/NumPy/SciPy ranges fit the APT stack. | Native Meson build; preserve Cython `>=3.1.2,<3.2.6`, meson-python `>=0.17.1,<0.22`, NumPy `<2.6`, SciPy `<1.19`. OpenMP is optional. |
| NeuCodec 0.0.4 | Real reference encoding uses Wav2Vec2-BERT, acoustic/semantic encoders, FSQ and Vocos. | Actual codec primitive operations, then frozen model-weight proof. Transformers remains necessary. |
| TorchAO 0.12.0 / Torchtune 0.3.1 | Official `py3-none-any` wheels were byte-verified and contain no native members. NeuCodec's relevant code only imports Torchtune's pure-Torch RoPE. Package initialization nevertheless imports wider training/quantization code. | Test the official pure wheels with APT Torch 2.14.1 before proposing any native TorchAO build or dependency fork. |
| llama-cpp-python 0.3.36 | Its shared-library loader rejects CPython's literal `android` platform. Matching vendored llama.cpp documents Android/Termux builds. | The isolated patch admits Android to the existing `.so` branch. Host tests cover discovery only; matching native libraries and their ABI remain untested. |
| eSpeak NG | NeuTTS pins commit `69bfd1efde0236654ccc117a28d04aef27673a30`, bundles its library/data, and disables audio-output backends. | Build this exact dependency and check phonemes. System eSpeak fallback may change phonemes and is not the faithful default. |
| Perth 1.0.1 | PyPI reports no runtime requirements, while repository requirements pin incompatible older Torch and include unrelated tooling. Its implicit watermarker actually uses Torch/audio/SciPy/Librosa/YAML and a bundled checkpoint. | Freeze that runtime path separately. Preserve upstream's explicit warning when watermarking is unavailable. No checkpoint was downloaded in this review. |

Primary build metadata:
[Numba](https://pypi.org/pypi/numba/0.67.0/json),
[Librosa](https://pypi.org/pypi/librosa/0.11.0/json),
[scikit-learn](https://github.com/scikit-learn/scikit-learn/blob/1.9.1/pyproject.toml),
[TorchAO](https://pypi.org/pypi/torchao/0.12.0/json),
[Torchtune](https://pypi.org/pypi/torchtune/0.3.1/json),
[llama-cpp-python](https://github.com/abetlen/llama-cpp-python/blob/1652066e0af45f2313b339670ef9555e8a54e545/pyproject.toml),
[eSpeak integration](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/CMakeLists.txt),
[Perth source](https://github.com/resemble-ai/Perth/tree/d6cc38cc9ab9da71c6b64d8c741bc13049eb881e).

Do not run the Termux eSpeak package recipe on a device: that recipe explicitly
rejects on-device packaging because it deletes prefix files. An isolated build
of the engine's pinned CMake dependency is a different route.

## Small lazy-import opportunities

The exact engine can defer `AutoTokenizer`/`AutoModelForCausalLM` to the non-GGUF
branch and import only the selected codec class. Librosa can be imported inside
`encode_reference`, but remains required when that method runs. NeuCodec can
defer `DistillCodecEncoder` until the distilled codec is selected.

Torchtune eagerly imports training modules to expose a RoPE implementation that
itself needs only Torch and typing. A lazy-export change is worth considering
only against an observed failure and focused behavior tests. Copying RoPE into a
codec fork would require preserved licensing, exact provenance and equivalence
tests. Omitting original distribution requirements does not create a valid
stock dependency closure.

## Separate Android loader experiment

The experimental patch
[`llama-cpp-python-android-loader.patch`](../patches/next-stable/llama-cpp-python-android-loader.patch)
targets only llama-cpp-python 0.3.36, commit
`1652066e0af45f2313b339670ef9555e8a54e545`. Its vendored llama.cpp commit is
`0c1e57098bba43ac29e6e3b677cdceebdd22334f`.

The production change admits literal `sys.platform == "android"` to the existing
Unix `.so` lookup. It does not alter global platform identity or substitute an
APT libllama for the binding's matching ABI. Focused tests use upstream's pytest
conventions with mocked library loading. Their exact result and scope are in the
audit receipt; they are not native Bionic execution evidence.

## Next useful native gate

First build exact Numba against the existing APT NumPy/llvmlite, then test real CPU
JIT and Librosa's reference-WAV path. Independently build the patched
llama-cpp-python with its matching vendored libraries and check wrapper
initialization without a model. The vendored
[Android build instructions](https://github.com/ggml-org/llama.cpp/blob/0c1e57098bba43ac29e6e3b677cdceebdd22334f/docs/android.md)
provide a bounded CPU route with optional OpenMP/llamafile disabled.

A subsequent codec gate should exercise actual RoPE, FSQ, SDPA and spectral
operations before changing training-package initialization. Full synthesis needs
frozen GGUF, codec, Wav2Vec2-BERT, reference audio/transcript and eSpeak identities,
plus Perth's checkpoint if watermarking is claimed, followed by the actual
Hermes helper and a valid 24 kHz waveform. Each of these remains an explicit
future gate.
