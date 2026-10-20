# NeuTTS offline source preparation

This change prepares the exact NeuTTS 1.4.1 source for a reproducible native wheel build. The published Hermes package and its version remain unchanged. It does not establish complete NeuTTS compatibility or enable NeuTTS in the production package.

## Source and change

The input is Neuphonic's commit `b7a3427d0d25e20e8b9e92cbaae688f732916baf`, whose Git tree is `45070163ccfdb42e71b8df21dcdf7c076edbd6aa`. The source archive contains 56 original files totaling 3,912,488 bytes. The preparer verifies the archive, the complete source manifest, the patch, and the resulting manifest. The independent regression also reconstructs the Git tree from the actual archive's blob bytes and executable modes.

Only `CMakeLists.txt` changes. The other 55 files, including package metadata, language assets, original sample data and license files, retain their original bytes. The resulting source contains the same 56 files and totals 3,913,233 bytes.

| Input | Identity |
| --- | --- |
| NeuTTS source archive | 3,037,279 bytes; SHA-256 `895875c31eba9020793ffe8ee58df20f50d9abc32fe745861754eb4b424cc3dd` |
| Source patch | `patches/next-stable/neutts-offline-espeak-source.patch`; SHA-256 `00c739983551d5498d36d4c245c9fc6839c5c08050e1a88e6f18847e11cec0b6` |
| Unchanged Python requirement | `>=3.10, <3.14` |
| Independently pinned eSpeak source | Commit `69bfd1efde0236654ccc117a28d04aef27673a30`; see `scripts/neutts_espeak_source_lock.json` |

The patch adds the optional CMake cache path `NEUTTS_ESPEAK_SOURCE_DIR`. When supplied, it must be an existing absolute directory containing `CMakeLists.txt`. CMake uses that local source without creating a Git clone or update operation. The UCD include paths follow the selected source directory. Without this setting, the original upstream Git repository and commit remain selected.

The path option itself does not authenticate arbitrary contents. A native build must first verify the separate eSpeak source lock and pass the resulting owned source directory. Existing build flags, enabled language dictionaries, installation rules and upstream sample assets remain unchanged in this patch.

## Preparation and replay

From the preparation checkout, create a new output directory:

```sh
python -B scripts/prepare_neutts_engine_source.py --out /path/to/new-engine-source-inputs
```

A previously downloaded exact archive can be supplied with `--archive /path/to/neutts-b7a3427d0d25e20e8b9e92cbaae688f732916baf.tar.gz`. The same size, SHA-256 and source checks apply. Existing output directories are rejected.

The output retains the exact archive and patch, the source lock, original and patched manifests, the prepared source tree and `PREPARED-NEUTTS-ENGINE-SOURCE.json`. It does not install a Python package, download model weights, or alter a Hermes environment.

## Verification completed

The focused root replay passed six tests with no skips, using the actual archive, CMake and Ninja. These cover rejection of a changed archive before source creation, complete source and Git-tree reconstruction, preservation of metadata and assets, rejection of changed metadata or sample bytes and of added code, and the real CMake source-selection regression.

The CMake regression contains five cases:

| Case | Required result |
| --- | --- |
| Original default | Original eSpeak Git repository and commit are selected. |
| Patched default | The same upstream repository and commit are selected. |
| Patched local source | Local source is selected, no Git clone is generated, and actual download/update targets complete offline. |
| Missing local source | Configuration fails. |
| Relative local source | Configuration fails. |

The harness suppresses compiler discovery so that these source-acquisition and configuration checks can run on the Windows devbox. Its small local CMake fixture tests acquisition behavior; it does not stand in for the real eSpeak source during a native build. These results therefore make no native compilation or engine inference claim.

A separate peer review independently matched all 56 original source blobs and modes to the primary Git tree and repeated the five CMake cases. The raw inputs, manifests, logs, root test XML, and independent review are retained in [the source-preparation audit](../audit/neutts-engine-source-preparation-20261017/). The machine-readable summary is [here](../audit/neutts-engine-source-preparation-20261017.json).

## Remaining native gates

The next build must propagate and prove the Android API 24 and ARMv8-A compiler settings through the nested eSpeak CMake invocation. The source hook deliberately retains upstream nested compiler flags; their behavior must be checked by the native build.

A successful wheel build must preserve the original metadata and all installed assets, verify the bundled library and dictionary data, and exercise the actual library. The already-passing [native eSpeak and Phonemizer workflow](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39073138135) is component evidence; the NeuTTS wheel has its own packaging and runtime checks.

Complete engine admission also requires the full selected dependency closure and the real reference-audio-to-generated-PCM pipeline. The current upstream Python upper bound remains in place while those checks are incomplete. The source patch does not bypass model access controls or establish microphone, playback, memory, or cancellation behavior.

## Primary source

The exact source is [Neuphonic NeuTTS at the selected commit](https://github.com/neuphonic/neutts/tree/b7a3427d0d25e20e8b9e92cbaae688f732916baf). The selected eSpeak source is [the upstream pinned commit](https://github.com/espeak-ng/espeak-ng/tree/69bfd1efde0236654ccc117a28d04aef27673a30).
