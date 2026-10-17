# Complete Phonemizer runtime preparation

## Purpose and current evidence

This component prepares Phonemizer 3.3.0 with its complete selected runtime dependency graph: **23 distributions and 26 active dependency edges**. It provides the first model-free executable slice of the larger NeuTTS preparation. The source patch moves dlinfo discovery behind the existing unresolved-library fallback; the declared dlinfo dependency is retained.

The host preparation is verified. Actual archive extraction and source patch replay succeeded, and **69 host checks passed with no skips** on Windows CPython 3.14.2: 39 new input/provenance contract checks and the unchanged 30 Phonemizer patch regression cases. The sibling eSpeak preparation independently replayed extraction followed by preparation. These results do not establish native ABI compatibility. The real Android build and public-wrapper gate must run separately.

The frozen input lock is `scripts/phonemizer_runtime_lock.json`, 78,659 bytes, SHA-256 `48d43784778817bd4a907b63f11738ff910cafc6aac2eed6bc27349b6d5d8c82`. Exact wheel, source, patch, original main catalog and active dependency identities are contained in that file. Host receipts and raw test output are under `audit/phonemizer-runtime-preparation-20261017/`, with the summary in `audit/phonemizer-runtime-preparation-20261017.json`.

## Exact runtime and build inputs

| Route | Packages |
|---|---|
| Nine original main wheels | attrs 26.1.0; jsonschema 4.26.0; jsonschema-specifications 2025.9.1; python-dateutil 2.9.0.post0; referencing 0.37.0; rpds-py 2026.6.3; six 1.17.0; termcolor 3.3.0; typing-extensions 4.16.0 |
| Twelve verified public pure wheels | Babel 2.18.0; cloudpickle 3.1.2; csvw 4.1.0; dlinfo 2.0.0; isodate 0.7.2; joblib 1.6.0; language-tags 1.3.1; pyparsing 3.3.2; rdflib 7.6.0; rfc3986 1.5.0; segments 2.4.0; uritemplate 4.2.0 |
| Exact source builds | Regex 2026.9.10; Phonemizer 3.3.0 with the independently reviewed lazy-dlinfo patch |
| Separate build environment | Existing Setuptools 83.0.0 and Packaging 26.0 wheels; Setuptools's existing bundled wheel 0.46.3 implementation is retained |

The twelve public runtime wheels total 11,635,293 compressed bytes. All 21 prebuilt runtime wheels were read completely and verified by exact artifact hash, every ZIP CRC and RECORD digest, distribution identity, complete declared requirements and WHEEL metadata. The original 100-wheel main catalog is preserved unchanged. RPDS's native wheel must still prove its ABI against the separate APT Python.

Regex's exact 417,072-byte source archive has SHA-256 `1e321e2c84f0e52c457f5ea5944f796d6e8e09cb99738ea98dcc1bfe402a128d`; its backend requires Setuptools `>77.0.3`. Phonemizer's exact 88,564-byte source archive has SHA-256 `5e0c38122effe0b331a24e674aff256874ece169d70a9cf1120337b56f8e3d0c`; its backend requires Setuptools `>=61.0`. The prepared source export preserves all 55 other original Phonemizer files unchanged, modifies the reviewed API file, and includes the reviewed regression test.

## Host extraction and preparation

CI uses the existing e271 candidate identity and `scripts/fetch_compatibility_candidate.py`. The caller passes the exact fetched .deb size and SHA-256 from that frozen route:

```sh
python scripts/extract_phonemizer_catalog.py \
  --deb "$candidate_deb" --deb-bytes "$candidate_bytes" \
  --deb-sha256 "$candidate_sha256" \
  --lock scripts/phonemizer_runtime_lock.json \
  --out "$selected_main_inputs"

python scripts/prepare_phonemizer_runtime.py \
  --lock scripts/phonemizer_runtime_lock.json \
  --main-wheelhouse "$selected_main_inputs/wheels" \
  --main-catalog "$selected_main_inputs/main-bundled-wheels.json" \
  --patch patches/next-stable/phonemizer-lazy-dlinfo.patch \
  --out "$phonemizer_inputs"
```

The optional `--cache DIR` reuses already verified exact public wheels and source archives. A cache mismatch fails verification; it is not silently replaced. The extractor checks the complete .deb identity and streams its ar/data archive, writing only the nine selected regular wheel files and original catalog. The preparer uses fresh staging and refuses to overwrite existing output. No package is installed by these host tools.

The local rehearsal used the separately verified CUA run 39063611615 package, SHA-256 `2b4c01a400622c45cf0f0f7af39fa5cdca4b37e311cebb71cdbacc770aa4f529`. Its nine selected wheels and complete original catalog are byte-identical to the e271 inputs. Its source identity is recorded explicitly; it does not replace the CI fetcher's frozen e271 pin.

## Native gate and separation of evidence

After the unchanged seven-case scientific foundation and separate eSpeak C API component pass in the same disposable native environment, run:

```sh
"$PREFIX/bin/python" -I -B scripts/compatibility_probe_phonemizer.py \
  --inputs "$phonemizer_inputs" \
  --apt-archives "$retained_apt_archives" \
  --foundation-receipt "$foundation_receipt" \
  --espeak-receipt "$espeak_output/ESPEAK-COMPONENT-RESULT.json" \
  --espeak-library "$espeak_output/bundle/lib/libespeak-ng.so.1.52.0.1" \
  --espeak-data "$espeak_output/bundle/share/espeak-ng-data" \
  --out "$phonemizer_output"
```

The runner requires actual Bionic/aarch64 CPython 3.14.6, the exact existing 44-package compiler set, retained APT archive identities, and the passed foundation. It revalidates the two APT runtime archives, including the shipped pip source. The integrated driver retains exactly 45 archives: the original 44 compiler archives plus the already-installed python-pip 26.2.1 archive, downloaded only for provenance. The [v2 input review](../audit/neutts-espeak-integration-v2-20261017.json) records that correction. The Phonemizer runner performs no APT installation.

Build and runtime virtual environments are separate and exclude global site-packages. The exact APT pip manages them through its documented `--python` option, which supports environments without pip installed. This behavior is documented by [pip's official interpreter-management documentation](https://pip.pypa.io/en/stable/topics/python-option/); the source receipt is saved with this audit.

The backend hook must report the reviewed empty additional build-requirement set. An unexpected dynamic dependency stops the build. Native builds use the frozen Android API-24 compiler flags, preserve all source dependency declarations, and must emit directly supported original wheel tags. The runtime install contains exactly the 23 distributions, uses exact wheel hashes, retains unmodified raw pip-check output, and verifies installed file bytes and the complete dependency identities.

The real operations exercise Regex Unicode grapheme/property/fuzzy matching, an RPDS persistent-map update, and the public `phonemizer.phonemize` API. The API must use the verified explicit eSpeak library and data, preserve requested punctuation and stress behavior, return repeatable batch results, and complete without importing dlinfo. Phonemizer's existing per-wrapper temporary library copy is checked against the original library bytes. Imported Regex/RPDS native modules and mapped APT libraries are checked against their exact wheel/archive ownership.

The receipts `PHONEMIZER-COMPONENT-RESULT.json`, `PHONEMIZER-RUNTIME-RESULT.json` and `PHONEMIZER-BUILT-WHEELS.json` remain distinct from `ESPEAK-COMPONENT-RESULT.json`. No model file, audio synthesis, NeuTTS engine installation or production feature admission is part of this component. The larger 117-node engine graph and NeuTTS interpreter bound remain unchanged.
