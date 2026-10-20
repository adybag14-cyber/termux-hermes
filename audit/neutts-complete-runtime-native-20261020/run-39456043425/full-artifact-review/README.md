# Complete dependency runtime: third native failure

This is the independent full-artifact review of [run 39456043425](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39456043425), job 118743063748, at exact source `3f1f404c72addb91f1d4937342c20e555be58a58`. The overall result is **failure**. Ten operation groups completed; the final complete-dependency integration group failed during Torchtune's import of TorchAO.

## Artifact and executed-source integrity

Artifact `12280522718` is 416,393,127 bytes with SHA-256 `88d3f1e05cbb80d5d9f59dd4db4b5a38403d5762d53295177cb871b97b030bcd`. The complete archive was downloaded and independently hashed. All 760 members passed path, type, size, CRC, and SHA-256 checks; total uncompressed content is 444,261,527 bytes. The compact full inventory retains every member identity without adding the entire archive to Git.

The original workflow receipt records 118 source inputs totalling 83,576,032 bytes. Every blob was independently re-read from the exact executed Git commit and matched its recorded digest. All 105 wheel bodies and 142 APT archive bodies match the executed lock and original archive pins. Original raw GitHub APIs/logs, native setup/runtime receipts, input manifests, and exact failed-import source files are retained.

## Actual failure

The original traceback identifies:

`ModuleNotFoundError: No module named 'torch._inductor.kernel.flex_attention'`

Torchtune imports TorchAO, whose prototype Inductor lowering imports `construct_strides` and `maybe_realize` from that missing Torch module. Torchtune then wraps the error with its generic “torchao not installed” message. The completed installed inventory proves that TorchAO 0.12.0 is installed from the exact selected wheel; this is an import compatibility failure, not evidence of an absent distribution.

The original TorchAO lowering module and Torchtune initializer are preserved under `failure-import/`, with whole-wheel and member identities in `FAILED-IMPORT-SOURCE-BINDINGS.json`. This audit describes the failed source revision. It does not claim that any later repair succeeded.

## Checks completed before the failure

The seven scientific foundation cases passed. Native APT authenticated the original retained signed snapshot; the verified plan installed or reinstalled exactly 19 additional pinned packages. The before/after package inventory matches that plan, and inherited GMP was verified without reinstalling it. No compiler was installed.

The isolated runtime contained exactly 116 visible distributions: 105 wheels and 11 complete original APT Python payload copies. The first installed-file inventory verified 29,140 site files; the initial wheel RECORD check verified 13,818 rows across 105 wheels. Original APT records and metadata were unchanged. The actual Android CPython 3.14.6 declared-dependency check passed for 116 nodes and 183 active edges, including the original selected FSSPEC HTTP extra. Global site packages were hidden. Pip and Torchcodec remain explicitly disclosed foundation support outside this graph.

The relocated Einx documentation file was verified at `share/doc/einx-0.4.3/source/conf.py` with its original content hash. The installed inventory passed beyond the previous two failures.

The ten completed operation groups, in executed source order, are:

| Group | Retained measured scope |
| --- | --- |
| Foundation and audio | Real Numba JIT, CFFI, MsgPack, LibYAML, scikit-learn, Audioop and Torchaudio operations. |
| Non-Rust | AES/SHA/GCM and invalid-tag controls; Pandas data operations; SentencePiece training and roundtrip on a synthetic local corpus. |
| HF-Xet | Actual native file hashes for an original and modified local fixture. |
| Safetensors | TensorSpec serialization and file roundtrip, retained backing buffer, and three corrupt-input rejections. |
| Tokenizers | Real WordPiece literal vectors/offsets/batches and Byte-BPE training with Unicode roundtrips. |
| Hub, HTTP and YAML | Offline Hub cache-miss behavior, loopback-only HTTPX/AIOHTTP/FSSPEC requests, and actual PyYAML C API. |
| Tiktoken | Native CoreBPE with six fixed local vectors, literal vocabulary, special-token controls and threaded batch checks. |
| Phonemizer | Actual stressed/unstressed eSpeak output, RPDS and XXHash; bounded original-constructor lifetime retention recorded. |
| Llama CPU | Actual CPU backend and default-context inspection only; no model loaded and no inference tested. |
| Perth public watermark | Original public bundled checkpoint loaded safely on CPU with weights-only strict state; actual public API on deterministic mono float32 audio at 24 and 32 kHz, with in-memory WAV roundtrips. |

The Perth results prove that these operations ran. The clean and watermarked confidences remain recorded numerically; every rounded confidence is zero, and no quality threshold is asserted. These synthetic inputs do not certify speech synthesis, watermark quality, microphone/device audio, or gated speech-model behavior.

## Checks not reached

The complete-dependency integration result was not produced. Final native library mapping/provenance verification, after-operation installed inventory, after-operation RECORD checks, and the final network recheck were not reached. The ten completed results and the successful before-checks do not substitute for those final gates. Phonemizer's receipt records its intended lifetime-retention target, but that final mapping target was not reached in this run.

The host explicitly disconnected the exact container from Docker networking before the child. Both outer and child receipts report only loopback, with the original 2-CPU, 6-GiB, 512-PID and UID-1000 limits. The local HTTP operation used loopback. No external model download, engine installation, release output, or production admission change is claimed.

Raw `pip check` still exits 1 with exactly the 11 original APT platform-tag diagnostics. There are no missing/conflicting declared requirements in that output. Metadata and supported tags were not rewritten to turn this into a nominal pip pass.

## Host CI and historical preservation

Both original host CI runs associated with this source succeeded: push run 39456043334 and PR run 39456058818 each report 1,266 passed tests, 84 skips and 625 passed subtests. Raw terminal APIs and logs, with their exact summary lines and identities, are retained under `host-ci/`. Host CI success does not change the native failure outcome.

All 185 previously frozen files from runs 39450032929 and 39452440876 were independently checked and remain byte-for-byte unchanged. This directory is a separate historical audit.

`NATIVE-FAILURE-REVIEW.json` contains the full scoped interpretation, original operation results, exact input inventories and receipt hashes. `EXECUTED-SOURCE-BINDINGS.json` and `SELECTED-ORIGINAL-MEMBERS.json` identify source and original-member retention. The full verified archive remains outside the repository in the Devbox evidence workspace.

This review performed no additional native operations or tests and made no package, source, Git, workflow or release changes.
