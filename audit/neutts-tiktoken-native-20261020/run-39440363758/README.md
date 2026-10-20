# Original Tiktoken native failure and bounded verifier correction

Run 39440363758 at 4a95a07086a0b88d209485ac7a01cdd40e268f40 built and verified the original Tiktoken wheel, then failed before the original Regex backend was invoked. The exact Regex pyproject declares setuptools > 77.0.3; its previously reviewed lock uses canonical setuptools>77.0.3. The new verifier had compared those strings literally.

The correction compares parsed PEP 508 declarations after verifying the original source file hashes. It does not rewrite the source, dependency requirement, lock, selected backend, Cargo inputs, Python bounds or package version. Actual-source regression tests also reject changed requirements, extras, markers, backend paths and equivalent text rewritten into the immutable original source.

ARTIFACT-REVIEW.json records the complete original ZIP size and SHA-256, all 2,264 regular member CRC/size/SHA-256 checks and the bounded retained members. FULL-MEMBER-INVENTORY.json.gz preserves that complete inventory. The artifact includes the raw failed child stderr, original pyprojects, passed Tiktoken build/Cargo/ELF receipts and original built Tiktoken wheel. REVIEW.json binds the failed run to the exact committed executing sources and the corrected host checks.

The corrected aggregate native gate remains required: Regex has not yet built in this gate, and the complete seven-distribution Tiktoken runtime has not yet executed. This is neither full NeuTTS admission nor a release. Raw evidence is protected from Git text normalization by the local .gitattributes file.
