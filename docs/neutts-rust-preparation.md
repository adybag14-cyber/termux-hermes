# NeuTTS Rust component preparation

This is preparation for the next stable Termux release. It creates fresh, disposable build and test environments. It does not change the released Debian package, normal installer selection, production patches, main branch, or release version.

## What is covered

| Component | Exact source | Build route | Runtime gate in this preparation |
|---|---|---|---|
| Maturin | 1.15.0 | Original Setuptools bootstrap, full Python PEP517 backend and native CLI | Exact six-distribution build environment, installed wheel files, CLI ELF and version |
| hf-xet | 1.6.0 | Original Maturin/PyO3 source, default features retained, existing native-tls feature added | Real file hashing; public token-refresh API against trusted, untrusted, and wrong-hostname local TLS fixtures |
| Safetensors | 0.8.0 | Original Maturin/PyO3 source | Native F32 buffer and file serialization, exact round-trip, corrupt-input rejection |
| Tokenizers | 0.22.2 | Original Maturin/PyO3 source, onig and esaxx defaults retained | Exact built wheel and AArch64 ELF; complete installed runtime waits for the separate PyYAML output |
| Tiktoken | 0.14.0 | Separate native Cargo lock capture first | No source build or installation until the newly captured lock is reviewed and saved |

Maturin is a build tool. The other four entries are runtime components. The source archives contain four original Cargo locks: Maturin's lock and the hf-xet, Safetensors, and Tokenizers locks. Tiktoken's published source archive contains no Cargo.lock. The originals and every source-file digest are recorded in [the preparation lock](../scripts/neutts_rust_sources_lock.json) and [the source inspection](../audit/neutts-rust-routes-20261017/source-cargo-inspection.json).

The four original locks contain a union of **804 distinct registry package/version identities**. This includes optional, development, build, and other-target entries. It is not a count of active Android dependencies or disabled features. The native runner separately records Cargo's target-filtered resolve graph, enabled features, build logs, and finished ELF dependencies. It keeps the original locks unchanged. See [the closure design](../audit/neutts-rust-routes-20261017/maturin-pep517-cargo-closure-design.json).

## Exact reconstruction inputs

The host preparer reads the fixed lock, downloads exact official archives, and verifies every hash before exporting source. It executes no Cargo or source backend.

The locked stage contains four complete source trees, 804 original .crate archives, a directory-source export, and five exact Python build wheels: Setuptools 83.0.0, Packaging 26.0, Wheel 0.46.3, setuptools-rust 1.13.0, and semantic-version 2.10.0. Cargo's directory-source checksum file is generated only after independently verifying the original archive. Verification compares every exported file with those original bytes. Changing both a source file and its Cargo checksum file cannot authorize the change.

Both stages include the exact **46-package APT closure** and frozen InRelease/Packages.gz pair. The unchanged scientific foundation supplies 27 of those packages; 19 compiler additions are installed afterward. Rust and its aarch64-linux-android standard library are 1.99.1. The APT Maturin CLI is excluded because it does not supply the Python PEP517 distribution. The actual package identities are in [the toolchain design](../audit/neutts-rust-routes-20261017/apt-toolchain-design.json) and [the APT Maturin inspection](../audit/neutts-rust-routes-20261017/maturin-apt-byte-inspection.json).

The native runner asks APT to authenticate the saved index using its configured Termux trust store. It verifies the acquired InRelease and decompressed index, every retained archive's control and hash, and the proposed installation. It rejects removals, unexpected additions, upgrades, or omissions. Installation uses a fresh writable cache copied from verified read-only archives.

The compiler and TLS libraries are checked against original APT payload bytes. The runner requires real CPython 3.14.6, Bionic, AArch64, and UID 1000. It compiles and executes an Android API 24 probe before passing that confirmed level to Maturin. It uses the original libpython3.so ABI3 stub, which links libpython3.14.so. It uses no PYTHONHOME, Python-platform override, ABI compatibility override, or finished-wheel retagging. See [the ABI linkage inspection](../audit/neutts-rust-routes-20261017/python-apt-abi-linkage-inspection.json).

## Full Maturin bootstrap

The fresh build environment initially contains only the five selected Python build distributions. The original backend reads its original source declarations and runs its original minimal Cargo arguments, --no-default-features and --locked. Cargo uses the verified directory source with offline mode enabled.

The resulting Maturin wheel is checked, installed as the sixth distribution, and verified. Its actual Python backend and native CLI are then used for the three locked runtime builds. The APT command alone is not treated as a Python backend.

Two upstream frontend differences are recorded explicitly. The uploaded Maturin sdist metadata normalizes a Tomli marker to python_full_version; its official Setuptools bootstrap emits the original python_version marker from pyproject.toml. Both originals remain in the lock, and this bootstrap must preserve the authored dependency declarations. Its RustBin also makes Setuptools emit the real CPython interpreter/ABI tag. The expected source-built tag is cp314-cp314-android_24_arm64_v8a. The finished wheel is never rewritten to Maturin's separately published py3-none tags. These expectations come from the unchanged original backend source and still require confirmation by the actual native build. See [the metadata record](../audit/neutts-rust-routes-20261017/maturin-bootstrap-metadata-declarations.json) and [the bootstrap tag record](../audit/neutts-rust-routes-20261017/maturin-official-bootstrap-tag.json).

Every finished wheel must retain its exact version, Python requirement, and full runtime dependency declaration list, have a compatible native tag, and pass all CRC and RECORD checks. Native members must be AArch64 ELF files in the expected namespace. Installed environments are checked for exact visible distribution counts, original metadata, every wheel-owned file, permitted installer records, and absence of unowned site files.

## hf-xet TLS compatibility

Source inspection identified a likely runtime incompatibility in the default Rustls Android platform-verifier route: it expects JVM/Kotlin integration that this Termux Python extension does not initialize. The source supplies an existing native-tls feature. With that feature enabled, the selected Reqwest version chooses its native TLS backend while preserving hf-xet's other defaults. This source-grounded route still requires actual native validation. See [the TLS inspection](../audit/neutts-rust-routes-20261017/hf-xet-native-tls-source-inspection.json).

The native probe calls the actual public XetSession.new_file_download_group(token_refresh_url=...) method. The original route eagerly obtains that URL through build_http_client and DirectRefreshRouteTokenRefresher. The local endpoint returns the original JSON schema and a local:// CAS location. No model or file transfer is involved.

A trusted local certificate must complete the request. An untrusted issuer and a certificate for the wrong host must fail during certificate validation. Python's native SSL library independently validates each fixture. The Python control and HF Xet client use distinct server listeners, so a control alert cannot be mistaken for the tested client's alert. Negative HF gates require a certificate-related TLS alert and no successful handshake or HTTP request. An import error, timeout, unrelated socket error, or accepted invalid identity cannot count as a successful rejection.

Test certificates use an explicit owned OpenSSL request configuration. Private keys stay in temporary work; only public certificates and hashes are retained. The process-local test CA does not modify the production trust store. Certificate and hostname verification remain enabled.

## Separate Tiktoken lock capture

The second workflow stage uses the exact untouched Tiktoken sdist in a fresh source copy. It runs native cargo generate-lockfile, then cargo fetch --locked with real TLS validation. It rejects Git sources, alternate registries, unexpected local packages, and changes to original source files.

The stage retains every locked original registry archive, verifies generated checksums, exports an independently checked directory source, and replays cargo metadata --locked --offline for the native target. TIKTOKEN-LOCK-CAPTURE.json and captured-tiktoken-inputs preserve the new lock, archives, source copy, graph, and raw commands.

Successful capture means **captured-requires-review**. It does not mean Tiktoken was built or installed. A later preparation must explicitly freeze those newly observed identities after review.

## Remaining runtime boundary

The complete Tokenizers subset is the unchanged **25-node, 29-edge** selection from the full engine dependency audit. It retains Hugging Face Hub 1.31.0, fsspec[http]'s selected dependencies, and PyYAML 6.0.3. Its handoff SHA256 is 42d47b3fe4f8858d94d69a5216db1253e75d05437c9ffad42651369130252768.

The separate non-Rust gate owns the PyYAML wheel. Until its exact passed wheel and receipt exist, this preparation does not claim a complete Tokenizers runtime or four-component engine environment. The two-distribution HF Xet/Safetensors environment covers their complete base dependencies. Optional NumPy, Torch, and other framework integrations remain separate gates.

## First native attempt and APT cache correction

The first two-stage workflow, [run 39076217343](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076217343), failed during host input acquisition. The generic safe-path checker rejected the epoch colon in two original Debian filenames. Docker, the scientific foundation, Cargo, and native component cases had not started.

The preparer now derives a reversible owned cache name for those two archives:

| Original signed-index basename | Owned portable cache basename |
|---|---|
| `ca-certificates_1:2026.09.25_all.deb` | `ca-certificates_1%3A2026.09.25_all.deb` |
| `openssl_1:3.6.5_aarch64.deb` | `openssl_1%3A3.6.5_aarch64.deb` |

The original index Filename, version, URL, size, hash, and archive bytes remain exact. The other 44 archive basenames are unchanged. The mapping rejects duplicate names, case aliases, traversal, and pre-encoded source identities. The generic source/wheel path checker still rejects colons. Only the native writable APT cache receives a copy under the original index basename; the verified input cache remains untouched.

The new host regressions exercise both actual stage download plans twice in fresh outputs, all 46 original frozen identities, verified cache reuse, original request URLs, and the native copy contract. See [the recorded native failure](../audit/neutts-rust-native-20261017/run-39076217343/epoch-basename-failure-analysis.json) and [the correction receipt](../audit/neutts-rust-native-20261017/run-39076217343/epoch-basename-fix-preparation.json). The original 57-test preparation receipt remains a historical checkpoint.

## Running and reading results

After source review, the preparation-only workflow can run both stages or one selected stage. It uses the pinned native Termux Docker image on an ARM64 runner, UID 1000, two CPUs, six GiB of memory, and bounded timeouts. Its permissions only read repository contents.

Equivalent ARM64 host entry points:

    bash scripts/compatibility_probe_neutts_rust.sh \
      --stage locked-build --out probe-results/rust-locked-build

    bash scripts/compatibility_probe_neutts_rust.sh \
      --stage tiktoken-lock --out probe-results/rust-tiktoken-lock

Both require fresh outputs. The workflow retains all preparation inputs and actual native result files even after a failure. Component checkpoints retain completed wheel results if a later component fails. Subprocess stdout and stderr are preserved on errors and timeouts.

Host evidence currently covers 69 focused integrity checks with no skips, all 744 original source files, 11 cached registry archives containing 2,474 files, and an actual 12-file directory-source export. The real export exposed a cross-platform path-ordering mismatch. The verifier now sorts canonical POSIX path strings while retaining every original file and checksum comparison. The remaining 793 registry archives are checksum-frozen for native preparation acquisition.

Final review also exercised the production APT archive parser against the exact cached Python 3.14.6-1 archive. A missing standard-library import was captured as a real host failure, corrected, and replayed against both original libpython payload hashes. A separate regression executes the installed-wheel inventory and its adapter with actual wheel bytes and Python distribution metadata. See [the archive replay](../audit/neutts-rust-routes-20261017/archive-parser-exact-apt-replay.json).

These host checks claim no Cargo resolution, native source build, native HF TLS success, or four-component runtime admission. See [the updated source/cache receipt](../audit/neutts-rust-native-20261017/run-39076217343/exact-cached-source-and-crate-gate.json) and the correction receipt for exact file and test hashes.

## Primary format references

Cargo documents directory sources and checksum files in its [source-replacement reference](https://doc.rust-lang.org/cargo/reference/source-replacement.html). Its [vendor documentation](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html) and [generate-lockfile documentation](https://doc.rust-lang.org/cargo/commands/cargo-generate-lockfile.html) describe the frozen/offline and explicit lock-generation boundaries. Independent archive and full-file verification remains authoritative.
