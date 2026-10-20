# Successful native public Perth runtime review

## Exact native run

The complete public Perth runtime passed on native ARM64 Android/Termux at source commit `73525752755f990926243396f34f5ba8e6148a03`.

- Run: [39446824120](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39446824120), job `118710822208`, first attempt.
- Original GitHub artifact: `12275718653`, `termux-neutts-public-perth-component`.
- Whole artifact: **321,313,068 bytes**, SHA-256 `c9961ed9dfac7177d1aa79e805b38769caf329afbcdd0f9535715fecfa5302dd`.
- All **274 ZIP members** passed actual CRC, uncompressed size and SHA-256 verification. The complete compact inventory and download proof are retained here. The original ZIP remains at the durable workspace path recorded in `FULL-DOWNLOAD-VERIFIED.json`.
- All **52 recorded source inputs**, totaling 23,923,215 bytes, independently match Git blobs at the exact executed commit.

Original GitHub APIs, the full job log, original native receipts, APT/install diagnostics, complete declared/install manifests and raw native mappings are preserved byte-for-byte under this audit directory. `SELECTED-ORIGINAL-MEMBERS.json` binds the selected files to the full original artifact. `NATIVE-REVIEW.json` records the subsequent independent semantic review; the earlier preliminary verification receipts retain their original chronological scope.

## Complete original runtime

The isolated runtime contains exactly **43 distributions and 50 active declared dependency edges**: 36 exact wheels and seven complete original APT Python payloads. The independent review rechecks every selected wheel's CRCs, RECORD rows and exact metadata hashes, and recomputes the full original requirements, Python bounds and active edges. Original wheel and APT metadata are preserved. The before/after native inventory verifies **19,937 site files**, and **5,456 installed wheel RECORD rows** remain unchanged. Global site packages were invisible.

All seven unchanged scientific foundation cases passed first. Native APT authenticated the retained original signed index. Only the two required original packages, `libyaml=0.2.5-5` and `python-msgpack=1.2.3`, were installed/reinstalled after the foundation. The exact package plan and before/after inventories reject other additions, removals or version changes. The original inherited GMP library was verified without reinstalling or upgrading it. No compiler was installed for this runtime gate. Foundation support distributions pip and Torchcodec remain separately disclosed outside the 43-node graph.

The original raw pip check exits 1 because seven original APT wheels retain their upstream Termux `android_aarch64` tags. Its complete diagnostic output is preserved. The required independent checks establish no missing/conflicting dependency, complete original file provenance, unchanged metadata and actual native operations. No wheel metadata or supported-tag list was rewritten to hide that output.

## Actual public checkpoint and SoundFile repair

The runtime used the original public bundled checkpoint, **37,429,684 bytes**, SHA-256 `a15bce457ebc53ce5e6c9c3f11df78cf7ee2bf9cdab0a798902135b4c4027670`, saved at step 250000. The measured load used `torch.load(weights_only=True, map_location='cpu')`, produced **59 finite CPU state tensors**, and passed strict original model-state loading. The real public `perth.PerthImplicitWatermarker` received the original model through `run_name=None`, `perth_net=model`, `device='cpu'`.

The resource derivative remains SHA-256 `b38db439e790d1bd0fd78eca9ce1c0ab9660ff4c6c0106abd0414b0816e2ce81`. The SoundFile Android discovery derivative remains SHA-256 `ad4f764ecc142ab5a9e05a0d61fda83ddf190fb7d59ca3c0da094be6229ee992`. Their dependency metadata and original checkpoint bytes are unchanged.

The actual Android `ctypes` lookup returned `None`; the narrow product fallback then selected `libsndfile.so`. The runtime measured libsndfile 1.2.2 and mapped the original `libsndfile=1.2.2-3` payload. Its archive SHA-256 is `1e1fb77b14ec26f3ff6ded069e9ec816ab7535ae5d074122c6727b0f59d8aff3`; the actual 439,352-byte library is SHA-256 `079263392fddcdd975f2d452f6fd654e26f199fda1c85e08d67fedfbb4b55825`, SONAME `libsndfile.so`. The independent review rereads that exact original DEB data member and matches the native mapping.

## Measured public operations

Both inputs are deterministic one-second, nonzero, mono float32 waveforms composed from 220 Hz and 659 Hz sinusoids. Actual in-memory SoundFile FLOAT-WAV roundtrips preserved every input float32 byte. Public watermark application returned finite, changed float32 output of the original shape and left the input unchanged. Actual decoding returned finite scalar confidences and the original rounded values.

| Sample rate | Samples | FLOAT-WAV bytes | Clean confidence | Watermarked confidence | Rounded clean / watermarked | Maximum absolute signal change |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 24,000 Hz | 24,000 | 96,080 | 0.014827917329967022 | 0.05456528440117836 | 0 / 0 | 0.027484895661473274 |
| 32,000 Hz | 32,000 | 128,080 | 0.014591598883271217 | 0.05193989723920822 | 0 / 0 | 0.027387283742427826 |

The low confidences and zero rounded detections are preserved explicitly. The gate applies the original finite/shape/API contract and asserts no invented quality threshold. Detection quality remains unassessed by these synthetic-signal compatibility operations. The 24 kHz path exercised the original Librosa/Soxr resampling during application and SciPy resampling during decoding.

Real auxiliary operations also passed: Audioop, CFFI, MsgPack, LibYAML, MarkupSafe, CharsetNormalizer, Scikit-learn prediction, Numba nopython JIT and Torchaudio resampling. JIT remained enabled. The raw results are retained in `artifact/PERTH-RUNTIME-RESULT.json`.

## Native ownership and offline boundary

The original runtime verified **162 actual native mappings across 14 runtime distributions**, **148 APT-owned native library mappings from 25 owners**, and five exact image-owned AOSP libraries. The independent review binds the mapped identities back to the original wheel/APT manifests and retained archive hashes. Original raw `/proc/self/maps` bytes and the classified mapping ledger are retained. No global Python site-package library entered the isolated runtime.

The exact container ID, pinned image, UID1000, two CPUs, 6 GiB memory and 512-PID limit are bound in the retained host inspection. The Docker bridge was disconnected before the public runtime. Both before and after measurements show only loopback, no runtime network route and the same disconnected-container receipt.

This is evidence for the complete original public Perth dependency closure, original public watermark checkpoint and measured synthetic-audio API behavior. Default speech models were not downloaded, no microphone or physical audio device was used, the NeuTTS engine was not installed, its Python bound was unchanged, and production admission/release flags remain false.
