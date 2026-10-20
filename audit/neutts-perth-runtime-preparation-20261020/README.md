# Complete public Perth runtime preparation

## Status and scope

This directory preserves reviewed inputs and host verification for a standalone
public Perth watermark operation gate. The native gate has been implemented but
has not yet been executed at this checkpoint. A successful host check is not a
native Perth result, a NeuTTS engine result, a speech quality assessment, or
production admission.

The original proposed runtime contains exactly **43 distributions and 50 active
declared dependency edges**, with no selected extras. The unchanged scientific
foundation also exposes base pip and Torchcodec; those two support distributions
are reported separately and are absent from the isolated Perth environment.
Original dependency declarations, package versions, Python bounds, and APT
metadata are preserved.

| Input authority | Isolated distributions | Treatment |
| --- | ---: | --- |
| Original scientific foundation wheels | 9 | Exact original wheels and RECORD |
| Original foundation APT Python packages | 6 | Complete original Python payloads and metadata |
| Proven unpublished Hermes candidate catalog | 8 | Exact selected wheels from the unchanged 100-wheel catalog |
| Original public wheels, including the Perth resource derivative | 15 | Original declared metadata; one separately reviewed resource-path derivative |
| Retained native NumBa, Audioop, PyYAML, and Scikit-learn wheels | 4 | Original complete wheel bodies, metadata, RECORD, native members, and licenses |
| Original signed APT MsgPack | 1 | Complete original Python payload and metadata |
| **Total** | **43** | **36 wheels plus seven APT Python payloads** |

The exact graph is in `declared-runtime-closure.json`. The executable lock is
`scripts/neutts_perth_runtime_lock.json`; it contains full wheel inventories,
complete APT Python manifests, the selected graph, and original supporting
source hashes. Full requirements are checked, including inactive extra clauses.
The runtime recomputes the 43-node/50-edge active closure under the actual native
Android CPython environment and verifies every original Python constraint.

## Native wheel provenance

The four retained wheels are copied unchanged from successful earlier native
component outputs. Their complete source artifacts were independently rehashed
before selected ZIP members were read. Selected members were CRC checked; this
does not claim that every unrelated member of either large source ZIP was
extracted or executed.

| Source artifact | Original bytes | Whole SHA-256 |
| --- | ---: | --- |
| CPU run 39429636156, artifact 12267109267 | 393,991,853 | dbc5c2504eb655c5cedfee597b04d25c4c219c47957af3e2747c2f6ca9bedb7b |
| Non-Rust run 39429636032, artifact 12268796130 | 277,193,670 | 730dd4a9e70b359a399f249ba78e24a58cf5f7eb663bb57e00938e45b72a87d2 |

The retained wheels total 17,481,715 bytes:

| Distribution | Version | Wheel bytes |
| --- | --- | ---: |
| NumBa | 0.67.0 | 2,805,585 |
| Audioop LTS | 0.2.2 | 26,275 |
| PyYAML | 6.0.3 | 128,787 |
| Scikit-learn | 1.9.1 | 14,521,068 |

`handoff/` retains the exact original source/input/component receipts. The lock
binds those receipts and each whole wheel. `HOST-INPUT-REVIEW.json` records the
intake checks. The wheels retain their original license and notice members;
their contents were not repackaged, trimmed, or re-signed.

## Original APT and complete payload bounds

The native shell first runs all seven unchanged scientific foundation cases
against the same immutable ARM64 Termux image and the original authenticated
122-package signed snapshot. It reopens that authenticated snapshot before
installing only the original libyaml 0.2.5-5 and python-msgpack 1.2.3 packages.
The before/after installed-package inventory must show no other change. The
simulation rejects removals, added packages, duplicate identities, missing
requested packages, and version drift. Installation requires the verified
native APT archive cache and uses `--no-download`.

The original libgmp 6.3.0-2 archive is retained for provenance of the already
installed image package. The gate verifies its image-baseline record, current
owner/version, and exact library bytes; it does not install or upgrade GMP.
The compiler toolchain is not installed for this runtime gate.

A dedicated hash-bound reader handles the original large Torch and llvmlite
Python payloads. Its limits are local to this new reader: 128 MiB per member,
256 MiB total expanded data per archive, and 25,000 data members. Original
Torch contains a 123,615,448-byte libtorch_cpu.so; original llvmlite contains
a 112,487,040-byte libllvmlite.so. The reader validates original archive and
control identity, every tar header, types and paths, uniqueness, the complete
site payload, file bytes/modes, and original METADATA/WHEEL/RECORD. Shared wheel
and APT reader limits remain unchanged.

The fixture in `fixtures/` is the unchanged original 61,724-byte signed MsgPack
archive. Tests bind it to the retained signed snapshot and verify the complete
13-file Python payload. Explicitly synthetic hostile AR/tar and candidate-stream
fixtures test refusal paths; they are not represented as native evidence.

The isolated environment preserves the original seven APT android_aarch64
WHEEL tags. Raw pip check must emit only the exact known legacy-platform-tag
diagnostics for those seven distributions. Separate mandatory checks validate
the actual interpreter/ABI convention, unchanged requirements, original file
payloads, and native operations. A different pip failure remains a failure.

## Library inspection and runtime isolation

`APT-ELF-DYNAMIC-STRING-REVIEW.json` and `APT-STATIC-ELF-REVIEW.json` record static
inspection of all 137 native files in the seven original APT Python payloads.
`NATIVE-WHEEL-STATIC-ELF-REVIEW.json` records all 83 native members in the four
retained wheels. No native binary was executed by those host inspections.

The shared `neutts_runtime_elf.py` reader examines actual bounded ELF64 bytes
without readelf or a compiler. It verifies AArch64/little-endian identity,
program headers, dynamic-table/string bounds, dependencies, paths, size, and
SHA-256. The largest actual dynamic string table is 3,135,249 bytes in original
Torch, within the unchanged 4 MiB reader limit.

`TORCH-ISOLATED-LOADER-REVIEW.json` records five original Torch APT symlinks from
the global Termux library directory to global Python package libraries. To keep
the runtime evidence specific to the copied environment, the child explicitly
prefers its verified torch/lib directory before the ordinary Termux library
directory. Every mapping from global Python site-packages is rejected. No
library body, ELF header, package metadata, or upstream loader code is rewritten.

The runtime verifies all mapped isolated extensions against their wheel/APT
file manifests. Every global APT library is bound to its original signed archive,
installed owner/version, actual file bytes, and static ELF identity. The five
reviewed image-owned AOSP libraries are verified separately against the immutable
image identity, file hashes, and package ownership. The original APT libsndfile
must actually be mapped for the Soundfile operation to pass.

## Public operation contract

The only Perth wheel change is the separately reviewed resource-path derivative.
Its original 37,429,684-byte public bundled checkpoint and hparams are unchanged.
`PERTH-PUBLIC-API-CLOSURE-REVIEW.json` independently checks the exact source/API
contract and original dependency graph.

The native child must:

1. Create a real isolated environment containing exactly the selected 43
   distributions, with no global Python site and unchanged original metadata.
   Every installed file and original/rewritten wheel RECORD is checked before
   and after operations.
2. Perform real Audioop, CFFI, MarkupSafe, Charset Normalizer, MsgPack, libyaml,
   Scikit-learn, NumBa nopython JIT, and Torchaudio operations. JIT is enabled,
   with private NumBa/Librosa/cache/temp directories outside the environment.
3. Round-trip deterministic nonzero mono float32 waveforms through real
   Soundfile/libSndFile in-memory FLOAT WAV at 24 kHz and 32 kHz, requiring exact
   float bits, shape, and sample rate.
4. Construct the unchanged public model from the original safe-loaded YAML,
   load the original checkpoint using
   `torch.load(weights_only=True, map_location="cpu")`, require its original
   saved step, and load the complete original state with `strict=True`.
5. Use the actual public
   `perth.PerthImplicitWatermarker(run_name=None, perth_net=model, device="cpu")`
   for both rates. The watermark must be finite float32, preserve shape, change
   the waveform, and leave the input unchanged. Real clean/watermarked decoding
   must produce finite scalar confidence in [0,1] and consistent rounded output.

The gate records measured confidence and waveform hashes. It does not invent a
watermark quality threshold or claim speech-model inference. The original
distribution version 1.0.1 and module version 1.0.0 discrepancy remains visible.

## Offline native workflow and evidence boundary

The workflow uses the existing immutable ARM64 image, user 1000, two CPUs,
6 GiB memory, and a 512-process limit. Inputs and repository mounts are read-only.
The unchanged scientific foundation and exact extra-APT setup complete first.
The host then disconnects the container's actual Docker network and publishes
the inspected container identity. The runtime requires no Docker networks, only
loopback interfaces, no IPv4 route, and the unchanged resource/user/image
contract. It repeats the network check after operations.

The workflow has only `contents: read` and `actions: read`; the latter allows
fetching the exact previously proven unpublished Hermes candidate. Its whole
.deb identity and selected catalog members are verified before use. Host
preparation here used the already verified catalog and exact eight wheel copies;
the native workflow will also exercise the full candidate-stream intake.
Synthetic streaming tests cover exact selection and malformed or missing input
refusal without claiming that they are release artifacts.

`FINAL-HOST-VERIFICATION.json` records the final host checks and exact prepared
input receipt. This checkpoint contains no actual PERTH-COMPONENT-RESULT.json
with native status passed. Native failures must retain the raw diagnostics and
remain failures until corrected with evidence.

No NeuTTS engine is installed, no engine Python bound changes, no default speech
weights or gated model are downloaded, no microphone is accessed, and no
production admission or release flag changes. The workflow produces reviewable
preparation evidence only.
