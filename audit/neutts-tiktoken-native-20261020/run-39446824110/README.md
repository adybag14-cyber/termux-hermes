# Successful native Tiktoken component review

## Exact run and retained evidence

The standalone Tiktoken gate passed on native ARM64 Android/Termux at source commit `73525752755f990926243396f34f5ba8e6148a03`.

- Run: [39446824110](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39446824110), job `118710822103`, first attempt.
- Original GitHub artifact: `12276642938`, `termux-neutts-tiktoken-component`.
- Whole artifact: **450,996,004 bytes**, SHA-256 `83b2ae7c5058a7fee3d3637a8f6bef535096512d84abce1de5cb46db79e22ca7`.
- Every one of its **2,280 ZIP members** passed actual CRC, uncompressed size and SHA-256 verification. The complete member inventory is retained in `FULL-MEMBER-INVENTORY.json.gz`; the original ZIP remains at the durable workspace path in `FULL-DOWNLOAD-VERIFIED.json`.
- Every one of the **80 recorded source inputs**, totaling 59,799,115 bytes, independently matches its Git blob at the exact executed commit. See `EXECUTED-SOURCE-BINDINGS.json`.

Original GitHub run/job/artifact API responses and the full job log are preserved byte-for-byte. `SELECTED-ORIGINAL-MEMBERS.json` binds the selected raw artifact files to the complete inventory. `NATIVE-REVIEW.json` is the subsequent semantic review; the preliminary download and source-binding receipts intentionally preserve the state they recorded before that review.

## Original build and metadata

The actual original Setuptools backend built Tiktoken 0.14.0 and Regex 2026.9.10 on CPython 3.14.6/Android API24. Its five-distribution build environment was isolated and verified. No finished wheel retagging, backend source patch, original dependency edit or platform override was used.

The original Tiktoken source had no packaged Cargo.lock. The separately reviewed lock from the previous native capture remained exact (`44c9797be677b8af84478a3d54d09ac34d5a654e4ed8ee3e36a871415bc3dd80`). All **27 original registry archives and 1,863 unpacked registry files** match the frozen checksums. Real `cargo metadata --locked --offline` matched the original target graph: **25 packages, 24 registry packages and 41 edges**. The backend used the exact offline directory source and the approved lock was rechecked afterward.

Only the two previously measured working-copy `*.egg-info/SOURCES.txt` regenerations were permitted: original Setuptools adds the already present `setup.cfg` entry. The remaining 35 Tiktoken and 21 Regex original source files stayed byte-identical. The complete 58-file prepared input set remained unchanged. This is not permission for arbitrary generated metadata or source changes.

Both native wheels retain byte-identical original sdist `PKG-INFO` as their `METADATA`, unchanged packaged Python sources and original licenses. The independent review verifies every wheel member, every RECORD row and each actual ELF. Tiktoken retains its original `>=3.9` Python bound and optional Blobfile requirement; Regex retains `>=3.10`. The separate NeuTTS engine Python bound is unaffected.

| Native wheel | Bytes | SHA-256 |
| --- | ---: | --- |
| `tiktoken-0.14.0-cp314-cp314-android_24_arm64_v8a.whl` | 1,128,536 | `f16a657657a1541295e7147264299359fd17ba6c76777206def9c608a9f1dc9f` |
| `regex-2026.9.10-cp314-cp314-android_24_arm64_v8a.whl` | 301,470 | `e3e63545e7ef7c274cb8e196e078dabc6067b5d5cdfddac814a8c1a245a827da` |

These exact original native outputs are retained under `artifact/tiktoken-component/wheels/`.

## Actual runtime operations

The complete original base runtime contains exactly **seven distributions and six active dependency edges**, with no selected extras: Tiktoken 0.14.0, Regex 2026.9.10, Requests 2.33.0, Certifi 2026.5.20, IDNA 3.19, urllib3 2.7.0 and CharsetNormalizer 3.5.1. Global site packages were invisible. The before/after inventory verifies 151 installed site files and unchanged original metadata.

The public `tiktoken.Encoding` constructed a real native `CoreBPE`. Its literal 258-entry vocabulary contains every single byte, the `ab` merge and one explicit special token. Six fixed vectors cover empty text, merges, whitespace/newlines and multibyte Unicode. Native encode/decode, two-thread batch operations, binary single-token methods, default special-token rejection and explicit allowed-special semantics all passed. Real Regex Unicode graphemes and local Requests/IDNA/urllib3/CharsetNormalizer/Certifi operations also passed. Connection and DNS audit hooks were active; no vocabulary or model was downloaded.

All **four actually mapped native extensions**—Tiktoken, Regex and the two CharsetNormalizer extensions—matched their exact wheel members, AArch64 ELF64 identity and direct `libpython3.14.so` linkage. **Thirty-nine mapped APT library files** matched their original archive payloads and installed owners. The independent review additionally reads those exact DEB control/data members and checks the retained mapping hashes. Android platform mappings remain explicitly separate from APT ownership.

## Foundation and scope

All seven unchanged scientific foundation cases passed first: Python dependencies, Torch, Torchaudio, Torchcodec, SciPy, llvmlite and Soxr. Native APT authenticated the retained signed index without insecure exceptions; the frozen toolchain plan and original archive hashes were checked. The original raw pip-check diagnostics are preserved alongside the separate APT metadata/requirement validation. A successful component result does not silently rewrite the raw pip output.

This evidence establishes the standalone original Tiktoken base runtime and its measured local tokenization operations. It does not install or admit the whole NeuTTS engine, execute a speech model, certify a physical device/audio path, or create a release. The exact machine-readable scope flags remain false in the original receipts and the independent review.
