# NeuCodec original-wheel compatibility preparation

## Outcome and boundary

The exact original NeuCodec 0.0.4 universal wheel is available from the official
[PyPI version metadata](https://pypi.org/pypi/neucodec/0.0.4/json). The freshly
retrieved 6,807-byte metadata response has SHA-256
`de742fcebf32ebc633a5d66907b4d7f840381c71c371541c904b68a049d22263`,
identical to the metadata already recorded in the frozen runtime graph.

This preparation applies the existing reviewed
`patches/next-stable/neucodec-hub1-download.patch` directly to the original
wheel's `neucodec/model.py`. It updates the wheel's RECORD and preserves all
18 other members byte for byte. It does not require a new build backend,
regenerate package metadata, install a runtime, or execute a model.

The complete native dependency gate must still import the actual NeuCodec
classes with their original dependencies. This host preparation does not claim
that native import, codec execution, gated model access, or a speech model has
passed. No production admission or release is changed. NeuCodec's original
Python requirement is `>=3.10,<4.0`; the separate NeuTTS engine's narrower Python
bound remains unchanged.

## Exact inputs and derivative

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Original universal wheel | 27,800 | 9c7c9d374d9ea92b2069953906570c748beb95e969e402c6c6a47f88ed6c17f4 |
| Original source archive | 23,072 | 994c9367b691b96c30247ebe5f3d9b7088411ff640b8df2f0dd9e1efe39f6f42 |
| Existing complete reviewed patch | 14,750 | 77a1e6e0685e9b30e9abde7ecd7386b446179d2a2b72796ab452c663e5bc8df9 |
| Prepared derivative wheel | 87,563 | 73fa4fd88856aaec3eba2b701a32916939acb54099279a8478732daaf16f7b96 |

The original metadata, wheel, and source archive are retained under `original/`.
The exact derivative is retained under `derived/`. Their original complete
licenses remain included. The source and wheel metadata are preserved as
supplied, including upstream descriptions and license declarations.

`ORIGINAL-WHEEL-SOURCE-REVIEW.json` records the complete equivalence check:

- All 16 packaged Python files are identical between the original wheel and
  original source archive.
- The 4,505-byte wheel METADATA is byte-identical to the original PKG-INFO,
  SHA-256 `939c1a0fea3d6cb66624c0cc686a2f92ea63c479984384bd1f697dc4cdc872be`.
- The original full LICENSE is identical in the wheel and source archive.
- The original `pyproject.toml` remains unchanged, including its eight runtime
  dependencies and original unpinned build-system declaration.
- The wheel's original `py3-none-any`, purelib, and `poetry-core 2.2.1` generator
  fields are preserved as original provenance. No new Poetry build is claimed.

The eight original dependencies, including the exact
`vector-quantize-pytorch==1.17.8` requirement, remain unchanged. The derivative
keeps the original version and filename; its complete hash and preparation
receipt identify the compatibility source change.

## Patch application and verifier

`scripts/prepare_neucodec_wheel.py` and
`scripts/neucodec_wheel_lock.json` bind the original graph, exact official
metadata, complete wheel/source inventories, full reviewed patch, and complete
derivative. The preparer uses only retained local inputs and the Python standard
library. It verifies every archive before interpreting or copying its contents.

The patch verifier checks the exact two-file patch, seven original-source hunks,
one added-test hunk, every old/new offset and context line, and the complete
resulting source inventory. Only `model.py` changes among the 20 original source
files. The 11,180-byte added regression test is retained in the prepared source
review tree and is not added to the wheel.

Wheel validation requires exactly 20 regular file entries, exact normalized
paths, supported compression, no encryption, individual member hashes, and a
complete independently checked RECORD. Source validation requires exactly 20
original regular archive members, original modes, no links or duplicate paths,
exact headers and content hashes. Both readers retain finite limits of 64 KiB
per member and 256 KiB total; complete input archives are capped at 1 MiB.
No shared archive limits are changed.

Fixed ZIP fields, original member ordering, and stored members make the entire
derivative deterministic. Every preparation reconstructs the wheel from the
original and checks its complete expected hash. The prepared directory and
receipt have exact inventories; extra files, directories, modified source,
altered receipt flags, or unrelated wheel changes are rejected.

To reconstruct or verify the prepared inputs:

```sh
python scripts/prepare_neucodec_wheel.py --out /fresh/path/neucodec-inputs
python scripts/prepare_neucodec_wheel.py --verify /fresh/path/neucodec-inputs
```

The optional `--wheel` argument accepts only the exact original wheel bytes.
Preparation never fetches model weights or changes runtime dependencies.

## Host verification

The focused suite passes 14 tests plus 40 subtests, with no failures, errors or
skips. It verifies full source/wheel equivalence, exact reproducibility,
unchanged metadata/licenses, correct RECORD entries, independently malformed ZIP
headers, links, compression, duplicate/escaped paths, archive bounds, source
header/type/mode validation, patch target/context/offset rejection, and exact
prepared receipts. A network-disabled test confirms preparation needs no network.

One focused test executes all 34 regression cases already included in the
reviewed patch, using their explicitly documented recording fixtures. It also
executes the original unpatched source against the modern Hub signature and
requires the original unexpected-proxy-argument failure. Those source-isolated
tests check API dispatch and error propagation; they do not claim actual model
construction, checkpoint loading, network downloads, or native codec behavior.

`HOST-TESTS.xml` and `HOST-VERIFICATION.json` bind the test outcome and exact
implementation hashes. `NEUCODEC-WHEEL-PREPARED.json` records the verified
prepared handoff. The independent boundary review is retained separately; the
actual complete dependency gate remains the native execution boundary.
