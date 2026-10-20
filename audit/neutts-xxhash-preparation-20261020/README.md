# Standalone XXHash native operation preparation

This directory preserves the unchanged XXHash 4.0.1 Android wheel already selected by the original NeuTTS public wheel lock and closure witness. It also preserves the original upstream tests used as the fixed-vector oracle. This is preparation evidence; it does not claim that the Android wheel has passed the new native job.

The wheel is 43,747 bytes, SHA-256
`af05a3f650220a6c59fa0ad2410249f2d2470a05225807c378fb67458693f8df`.
Its sole native extension is the original AArch64 Bionic ELF. Its package version, archive bytes, METADATA, WHEEL, original RECORD, license, requirements, member inventory and native payload are unchanged. It declares no Python dependencies.

## Primary oracle

`FIXTURES.json` records the exact wheel identity, source URLs, source sizes and SHA-256 hashes. Upstream tag `v4.0.1` resolves through tag object `850c26b8c2944fb74b155d9f8532e5306cc1e8b4` to commit
`e2c1bcf1e1d86c4e3d43e4d412dccb521498ea88`.
The four original test files and BSD license under `upstream/` were fetched at that commit and checked against their Git blob identities.

Twelve independent fixed vectors cover XXH32, XXH64, XXH3-64 and XXH3-128 on byte string `b'a'` with seeds zero, one and the applicable unsigned maximum. The gate checks integer, big-endian byte and hexadecimal digests; one-shot and streaming calls; copy isolation; reset retaining the seed; and unsigned seed wrapping. A separate 65,798-byte deterministic fixture checks long-input streaming, copy and reset consistency. That longer fixture is explicitly API consistency, not an independent fixed-vector oracle. The original XXH128 aliases and rejection of unencoded strings are also checked.

## Gate boundary

The new `neutts-xxhash-component.yml` workflow uses the existing pinned Termux image on a native ARM64 runner, UID 1000 and Python 3.14.6. The unchanged seven-case scientific foundation and signed frozen APT inputs must pass first.

The XXHash step creates a new venv without system site-packages and installs only the exact retained wheel, without dependency resolution or compilation. It checks every original installed file against the archive, separately validates pip's rewritten installation RECORD and direct URL receipt, and rejects unowned files or distributions. The actually imported extension must be the verified wheel member. Its four mapped dependencies must match the passed foundation's paths, bytes, hashes and APT owners. APT provenance is rechecked after the operation, and the installed package set must remain unchanged.

The preparer reuses the unchanged foundation wheel verifier. One explicit inventory adapter is necessary: the original public witness hashes sorted member names without a final newline; the foundation helper hashes them with one. Both encodings are independently checked against their fixed digests. No artifact, requirement or original witness is rewritten.

## Host validation and remaining work

`HOST-REVIEW.json` and the saved pytest output record the bounded host integrity checks. These include corrupt archives, changed installed ELF or metadata despite a rewritten RECORD, false origins, extra import hooks, duplicate or false RECORD rows, changed mapped dependency identities, failed children, timeouts and rejection of a non-Android host. The fixed-vector constants are checked directly against the preserved original upstream tests.

Only a successful new native workflow can establish actual Android operation success. This component gate does not install the complete NeuTTS engine, fetch model weights, record audio, change production admission, create a candidate release or modify the published package.
