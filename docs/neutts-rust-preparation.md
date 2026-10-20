# NeuTTS Rust component preparation

This is preparation for the next stable Termux release. It creates fresh, disposable build and test environments. It does not change the released Debian package, normal installer selection, production patches, main branch, or release version.

## What is covered

| Component | Exact source | Build route | Runtime gate in this preparation |
|---|---|---|---|
| Maturin | 1.15.0 | Original Setuptools bootstrap, full Python PEP517 backend and native CLI | Exact six-distribution build environment, installed wheel files, CLI ELF and version |
| hf-xet | 1.6.0 | Original Maturin/PyO3 source, default features retained, existing native-tls feature added | Real file hashing; public token-refresh API against trusted, untrusted, and wrong-hostname local TLS fixtures |
| Safetensors | 0.8.0 | Original Maturin/PyO3 source | Native F32 buffer and file serialization, exact round-trip, corrupt-input rejection |
| Tokenizers | 0.22.2 | Original Maturin/PyO3 source, onig and esaxx defaults retained | Exact built wheel and AArch64 ELF; complete installed runtime waits for the reviewed PyYAML and LibYAML handoff |
| Tiktoken | 0.14.0 | Separate native Cargo lock capture, reviewed and saved in `c1ea01d` | Native source build, installation and tokenizer operation remain pending |

Maturin is a build tool. The other four entries are runtime components. The source archives contain four original Cargo locks: Maturin's lock and the hf-xet, Safetensors, and Tokenizers locks. Tiktoken's published source archive contains no Cargo.lock. The originals and every source-file digest are recorded in [the preparation lock](../scripts/neutts_rust_sources_lock.json) and [the source inspection](../audit/neutts-rust-routes-20261017/source-cargo-inspection.json).

The four original locks contain a union of **804 distinct registry package/version identities**. This includes optional, development, build, and other-target entries. It is not a count of active Android dependencies or disabled features. The native runner separately records Cargo's target-filtered resolve graph, enabled features, build logs, and finished ELF dependencies. It keeps the original locks unchanged. See [the closure design](../audit/neutts-rust-routes-20261017/maturin-pep517-cargo-closure-design.json).

## Exact reconstruction inputs

The host preparer reads the fixed lock, downloads exact official archives, and verifies every hash before exporting source. It executes no Cargo or source backend.

The locked stage contains four complete source trees, 804 original .crate archives, a directory-source export, and five exact Python build wheels: Setuptools 83.0.0, Packaging 26.0, Wheel 0.46.3, setuptools-rust 1.13.0, and semantic-version 2.10.0. Cargo's directory-source checksum file is generated only after independently verifying the original archive. Verification compares every exported file with those original bytes. Changing both a source file and its Cargo checksum file cannot authorize the change.

Both stages include the exact **47-package APT closure** and frozen InRelease/Packages.gz pair. The unchanged scientific foundation supplies 27 of those packages. The later request selects 20 compiler and test-tool packages outside that foundation; the recorded native APT plan contains 15 new installations and five same-version reinstalls. The sole addition to the original 46-package closure is `openssl-tool` 1:3.6.5, required by the existing TLS certificate controls; it uses the same signed snapshot and depends exactly on the already pinned OpenSSL library version. Rust and its aarch64-linux-android standard library are 1.99.1. The APT Maturin CLI is excluded because it does not supply the Python PEP517 distribution. The actual package identities are in [the toolchain design](../audit/neutts-rust-routes-20261017/apt-toolchain-design.json) and [the APT Maturin inspection](../audit/neutts-rust-routes-20261017/maturin-apt-byte-inspection.json).

The native runner asks APT to authenticate the saved index using its configured Termux trust store. It verifies the acquired InRelease and decompressed index, every retained archive's control and hash, and the proposed installation. It rejects removals, unexpected additions, upgrades, or omissions. Installation uses a fresh writable cache copied from verified read-only archives.

The compiler and TLS libraries are checked against original APT payload bytes. The runner requires real CPython 3.14.6, Bionic, AArch64, and UID 1000. It compiles and executes an Android API 24 probe before passing that confirmed level to Maturin. It uses the original libpython3.so ABI3 stub, which links libpython3.14.so. It uses no PYTHONHOME, Python-platform override, ABI compatibility override, or finished-wheel retagging. See [the ABI linkage inspection](../audit/neutts-rust-routes-20261017/python-apt-abi-linkage-inspection.json).

## Full Maturin bootstrap

The fresh build environment initially contains only the five selected Python build distributions. The original backend reads its original source declarations and runs its original minimal Cargo arguments, --no-default-features and --locked. Cargo uses the verified directory source with offline mode enabled.

The resulting Maturin wheel is checked, installed as the sixth distribution, and verified. Its actual Python backend and native CLI are then used for the three locked runtime builds. The APT command alone is not treated as a Python backend.

Two upstream frontend differences are recorded explicitly. The uploaded Maturin sdist metadata normalizes a Tomli marker to python_full_version; its official Setuptools bootstrap emits the original python_version marker from pyproject.toml. Both originals remain in the lock, and this bootstrap must preserve the authored dependency declarations. Its RustBin also makes Setuptools emit the real CPython interpreter/ABI tag. The expected source-built tag is cp314-cp314-android_24_arm64_v8a. The finished wheel is never rewritten to Maturin's separately published py3-none tags. These expectations come from the unchanged original backend source. Run 39084939992 subsequently confirmed the original bootstrap metadata, actual native wheel tag, installed six-distribution backend environment, and CLI version; its later HF-Xet graph failure is documented below. See [the metadata record](../audit/neutts-rust-routes-20261017/maturin-bootstrap-metadata-declarations.json) and [the bootstrap tag record](../audit/neutts-rust-routes-20261017/maturin-official-bootstrap-tag.json).

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

The original index Filename, version, URL, size, hash, and archive bytes remain exact. The other 44 archive basenames are unchanged. The mapping rejects duplicate names, case aliases, traversal, and pre-encoded source identities. The generic source/wheel path checker still rejects colons. At that checkpoint, the native writable cache used the original index basename. The later native APT cache correction below records why an epoch package instead needs APT's quoted basename; the verified input cache remains untouched.

The new host regressions exercise both actual stage download plans twice in fresh outputs, all 46 original frozen identities, verified cache reuse, original request URLs, and the native copy contract. See [the recorded native failure](../audit/neutts-rust-native-20261017/run-39076217343/epoch-basename-failure-analysis.json) and [the correction receipt](../audit/neutts-rust-native-20261017/run-39076217343/epoch-basename-fix-preparation.json). The original 57-test preparation receipt remains a historical checkpoint.

## Second native attempt and signed-index selection

The retry, [run 39077868589](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39077868589), reached native Termux in both stages. All seven scientific foundation cases passed. Both stages then stopped in the saved APT index parser, before the later Rust-specific APT signature check, compiler installation, Cargo resolution, or Rust wheel builds. The earlier scientific foundation had already recorded its own signed APT authentication.

The exact frozen index contains 3,011 target rows for 3,008 package names. Carapace, Chezmoi, and MPD each retain two versions. Requiring every package name in that whole repository to be unique incorrectly rejected those valid rows. All 46 selected build packages have exactly one row for their frozen name, version, and architecture, with their exact original Filename, size, and SHA256.

The parser now retains those original rows and selects each frozen identity explicitly. Missing selections, repeated selected rows, conflicting selected archive metadata, and repeated selected fields fail. Additional versions remain in the original repository bytes. The signed InRelease, Packages.gz, configured APT trust store, insecure-repository prohibitions, and comparison with the exact APT-acquired bytes remain unchanged.

The original error was reproduced through the original signed_snapshot function on the actual saved index before the correction. New regressions run the corrected selector on that same 3,011-row snapshot, exercise mixed-version and conflicting selections, and replay the full signed_snapshot path with controlled native-command fixtures. Those host fixtures verify the preserved byte and command contracts; actual native APT authentication remains a native retry gate. See [the separate failure receipt](../audit/neutts-rust-native-20261017/run-39077868589/selected-index-failure-analysis.json).

## Third native attempt and compiler input verification

The next retry, [run 39079732704](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39079732704), passed the Rust-specific native signed-index check and installed all 19 original compiler additions in both stages. Rust 1.99.1 and Cargo 1.99.1 reported their native `aarch64-linux-android` host. Clang 21.1.8 compiled the Android API 24 control, and the resulting native executable returned `24`.

Both stages then failed while verifying the original compiler/runtime files. The old message combined missing-file and escaped-path conditions and did not identify the offending path. Inspection of all original archives showed that `bin/openssl` was the only requested path missing from the 46-package closure: Termux packages the command separately from the OpenSSL libraries. The exact `openssl-tool` archive is 278,628 bytes, SHA256 `91b6fd0e86f2585447a44c42a496e8c4da364ff3d7b13bec236a7e65be108109`, and declares `openssl (= 1:3.6.5)`. Its original AArch64 executable links the already pinned `libssl.so.3` and `libcrypto.so.3`, plus Android's `libc.so`.

The complete archive replay also exposed two legitimate Rust files above the original 64,000,000-byte member limit. The probe still verifies both files, with individual bounds tied to the unchanged Rust archive SHA256, exact member path, exact size, and body digest:

| Original Rust member | Bytes | SHA256 |
|---|---:|---|
| `libcore-500d6d8d30fe7938.rmeta` | 67,004,390 | `5c60ac0728315ea04853686a48e6376d8a6d7d88c1e0c82bfd27d6976ef18bd5` |
| `librustc_driver-d4b3d460e526cc9c.so` | 78,088,296 | `342ce378f61409244f48dcd26d69c3db919fa1c104896e5a3f646fd34b9ecd63` |

Every other member retains the 64,000,000-byte bound. Whole-archive hashes, original control identity, unique ownership, and installed-file byte comparisons remain required. The path report now records each original path and resolved target before admission and distinguishes a missing file, a path outside the prefix, a non-regular file, and a resolution error.

The exact 47-archive union covers all 89 original requested paths: 14 fixed compiler/TLS inputs and 75 regular files from the native Rust library directory, resolving to 88 unique regular files. The [corrected production-parser replay](../audit/neutts-rust-native-20261017/run-39079732704/compiler-input-corrected-archive-replay.json) verifies every original archive/control and all 88 file bodies, with no reader or limit mocks. Every original archive record, source file, Cargo lock, Python build wheel and runtime dependency remains unchanged. The existing trusted-certificate, untrusted-certificate and wrong-hostname TLS controls remain required. This failed native run did not reach Cargo resolution, a Rust source build, or the HF TLS case.

Both complete failed-run artifacts are retained with whole SHA256 and every ZIP-member CRC/SHA256. See [the original failure and archive diagnosis](../audit/neutts-rust-native-20261017/run-39079732704/compiler-input-failure-analysis.json), [the full requested-path inventory](../audit/neutts-rust-native-20261017/run-39079732704/compiler-input-archive-review-attempt3.json), and [the correction checkpoint](../audit/neutts-rust-native-20261017/run-39079732704/compiler-input-fix-preparation.json). The native retry remains a separate gate.

## Native APT cache naming correction

[Run 39082981266](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39082981266), at exact commit `123e70ee7ec9ff97b2cc82a05c13794d98e3e4b5`, passed all seven foundation cases, native authentication of the unchanged signed snapshot, all 47 archive identities, and the exact APT plan of 15 new packages plus five same-version reinstalls in both stages. Installation then failed with the same retained diagnostic:

    E: Internal Error, Pathname to install is not absolute 'openssl-tool_1%3a3.6.5_aarch64.deb'

The temporary cache contained the original pool basename with a colon. APT constructs its cache basename from package, version and architecture, and quotes the epoch colon using lowercase hexadecimal. This behavior is observed in the actual native error and matches [the captured upstream APT source](../audit/neutts-rust-native-20261017/run-39082981266/apt-reference-source/reference-source.json). That upstream reference is not a claim about the container's APT version.

Only the owned native cache copy now receives APT's expected basename:

| Identity | Signed pool basename | Preserved portable input basename | Native APT cache basename |
|---|---|---|---|
| Existing foundation CA package | `ca-certificates_1:2026.09.25_all.deb` | `ca-certificates_1%3A2026.09.25_all.deb` | `ca-certificates_1%3a2026.09.25_all.deb` |
| Existing foundation OpenSSL library | `openssl_1:3.6.5_aarch64.deb` | `openssl_1%3A3.6.5_aarch64.deb` | `openssl_1%3a3.6.5_aarch64.deb` |
| Newly required OpenSSL executable | `openssl-tool_1:3.6.5_aarch64.deb` | `openssl-tool_1%3A3.6.5_aarch64.deb` | `openssl-tool_1%3a3.6.5_aarch64.deb` |

The earlier installation did not exercise an epoch-bearing addition: the CA and OpenSSL library packages were already present in the foundation and are absent from the 20-package compiler/test request. The correction preserves that selection. It does not reinstall the foundation to avoid the error, change a version, change signed metadata, or enable downloads.

The native helper validates the identity-to-filename mapping, rejects traversal and prequoted or duplicate aliases, checks every copied archive against its original digest, and records `rust-apt-cache-layout.json` before APT runs. The unchanged installation checks still require the exact plan and exact final package inventory. All source, Cargo, archive and Python dependency pins remain unchanged.

The [production staging replay](../audit/neutts-rust-native-20261017/run-39082981266/actual-native-cache-layout-production-replay.json) copied all 47 exact original archives, totaling 246,673,988 bytes, into a fresh host cache. It rechecked every input and output digest and refused reuse of the existing output. The 126-test focused suite covers both foundation and new epoch identities, invalid names, aliases, unchanged input bytes, and the existing installation, source, ABI and TLS controls. These were host validation results at that checkpoint. The following run, 39084939992, subsequently passed native APT installation and compiler controls in both stages.

Both complete failed-run artifacts are preserved: 817,730,199 bytes across 47,526 ZIP members, with whole-archive SHA256 and every member CRC/SHA256 checked. The initial small diagnostic extraction was reconciled byte-for-byte with the subsequently verified complete archive. See [the failure analysis](../audit/neutts-rust-native-20261017/run-39082981266/native-cache-failure-analysis.json) and [the correction checkpoint](../audit/neutts-rust-native-20261017/run-39082981266/native-cache-fix-preparation.json). This failed run did not reach compiler ABI controls, Cargo lock resolution, a Rust source build, or HF TLS behavior; no new Tiktoken Cargo.lock was produced.

## Successful Tiktoken capture and HF Cargo identity correction

[Run 39084939992](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084939992), bound to `fe857011db52cccd3d7bede48523a77481d8fab9`, completed the two native stages with different outcomes:

| Stage | Observed result | Boundary |
|---|---|---|
| Tiktoken lock capture | Successful native lock resolution, original archive fetch, and fresh offline Android metadata replay | Root review and exact input lock saved in `c1ea01d`; no native Tiktoken build or operation is certified |
| Locked builds | Native APT/compiler controls and the Maturin wheel, installed backend, and CLI passed; the HF-Xet Cargo identity assertion then failed | No HF-Xet, Safetensors, or Tokenizers runtime wheel was admitted by this run |

The Tiktoken stage preserved an exact 6,462-byte Cargo.lock with SHA256 `44c9797be677b8af84478a3d54d09ac34d5a654e4ed8ee3e36a871415bc3dd80`. Its 27 original registry archives total 5,589,389 bytes, and every archive digest equals the corresponding Cargo checksum. The captured lock contains 28 package identities including the original local Tiktoken package. Cargo's offline, target-filtered Android metadata resolves 25 packages and 41 edges, including 24 registry packages. This graph describes the captured Cargo resolution, not a completed wheel or runtime. The [lock review](../audit/neutts-rust-native-20261017/run-39084939992/TIKTOKEN-LOCK-REVIEW.json) and [independent root review](../audit/neutts-rust-native-20261017/run-39084939992/TIKTOKEN-ROOT-REVIEW.json) were saved in commit `c1ea01d2f06b77dfab14e2f50daf7d72b5ad18d8`. Both retain exact input identities; a separately pinned build and installed tokenizer operation remain required.

The unchanged Tiktoken source requests PyO3 `0.29.2`; the captured compatible selection is `0.29.3`, with the original `extension-module` and `macros` feature route. All 36 original Tiktoken files remain byte-identical. The host integrity replay reconstructed and checked all 1,863 original crate files plus 27 canonical checksum files from the original archives. It explicitly records the hidden-file omissions in GitHub's expanded vendor upload. See the [raw lock and input catalog](../audit/neutts-rust-native-20261017/run-39084939992/captured-tiktoken-exact-inputs.json), [independent reconstruction](../audit/neutts-rust-native-20261017/run-39084939992/tiktoken-canonical-reconstruction.json), and [separately frozen successful-stage review](../audit/neutts-rust-native-20261017/run-39084939992/TIKTOKEN-STAGE-FROZEN.json). The four original project Cargo locks and current preparation lock remain unchanged.

The locked-build failure is a package-identity error in the verifier. The exact 250-node Cargo output contains two distinct original local packages:

| Cargo package | Original manifest | Resolved role |
|---|---|---|
| `hf_xet` 1.6.0 | `hf_xet/Cargo.toml` | Cargo's resolve root and the Python extension |
| `hf-xet` 1.6.0 | `xet_pkg/Cargo.toml` | The extension's unconditional normal `xet_pkg` dependency |

Both packages correctly resolve `native-tls`. The original predicate combined the two names and required one match, producing `HF native TLS feature did not resolve`. The same captured graph resolves Reqwest 0.13.2 with `native-tls`, excludes `http3`, and includes `openssl-sys` 0.9.117. The original source declarations and the entire failed output are preserved in the [failure analysis](../audit/neutts-rust-native-20261017/run-39084939992/HF-TLS-FAILURE-ANALYSIS.json).

The correction binds the extension to the exact resolve root, original manifest, Cargo name, and source version. It verifies the explicit normal dependency edge to the distinct backing package and its own original manifest, name, inherited workspace version, and `native-tls` feature. It retains the unique Reqwest/native-TLS/no-HTTP3 requirement and the OpenSSL dependency requirement. Source manifests, dependency declarations, defaults, PyO3 ABI features, build commands, and TLS certificate/hostname controls remain unchanged.

The 155-test host gate passes with no skips. Its new regression executes the prior predicate against the actual captured metadata and reproduces the original failure, then executes the corrected complete metadata validator against that same graph with host paths rebased. Negative controls reject incorrect roots, names, versions, manifests, missing or conditional dependency edges, altered source bytes, missing TLS features, duplicate Reqwest selections, HTTP3, missing OpenSSL, and unreviewed registry sources. The correction still requires a new native run; host graph replay is not a successful HF TLS behavioral test.

Both artifacts from this run are complete: 843,459,326 bytes across 49,445 ZIP members, with whole-archive SHA256 and every member CRC/SHA256 verified. The successful Tiktoken stage and failed locked-build stage have separate immutable capture receipts. No release, normal installer selection, or complete four-component runtime admission is produced by this checkpoint.

## Running and reading results

After source review, the preparation-only workflow can run both stages or one selected stage. It uses the pinned native Termux Docker image on an ARM64 runner, UID 1000, two CPUs, six GiB of memory, and bounded timeouts. Its permissions only read repository contents.

Equivalent ARM64 host entry points:

    bash scripts/compatibility_probe_neutts_rust.sh \
      --stage locked-build --out probe-results/rust-locked-build

    bash scripts/compatibility_probe_neutts_rust.sh \
      --stage tiktoken-lock --out probe-results/rust-tiktoken-lock

Both require fresh outputs. The workflow retains the exact downloaded reconstruction archives and actual native result files even after a failure. GitHub's artifact upload omits hidden paths from the unpacked source/vendor copies. Those partial unpacked copies are not an admitted preparation directory; reconstruct them from the complete original archives with the canonical preparer. Component checkpoints retain completed wheel results if a later component fails. Subprocess stdout and stderr are preserved on errors and timeouts.

Host evidence currently covers 155 focused integrity checks with no skips. The source/cache checkpoint covers all 744 original source files, 11 expanded registry archives containing 2,474 files, and an actual 12-file directory-source export. The real export exposed a cross-platform path-ordering mismatch. The verifier now sorts canonical POSIX path strings while retaining every original file and checksum comparison. Subsequent complete capture of the first native run preserves all 804 original registry archives with their exact frozen checksums. The [separate cache admission receipt](../audit/neutts-rust-native-20261017/run-39076217343/captured-original-input-cache-admission.json) distinguishes that archive-byte admission from the earlier expanded-source checks and records the then-missing 42 APT archives.

Final review also exercised the production APT archive parser against the exact cached Python 3.14.6-1 archive. A missing standard-library import was captured as a real host failure, corrected, and replayed against both original libpython payload hashes. A separate regression executes the installed-wheel inventory and its adapter with actual wheel bytes and Python distribution metadata. See [the archive replay](../audit/neutts-rust-routes-20261017/archive-parser-exact-apt-replay.json).

These host checks claim no Cargo resolution, native source build, native HF TLS success, or four-component runtime admission. See [the updated source/cache receipt](../audit/neutts-rust-native-20261017/run-39076217343/exact-cached-source-and-crate-gate.json) and the correction receipt for exact file and test hashes.

## Primary format references

Cargo documents directory sources and checksum files in its [source-replacement reference](https://doc.rust-lang.org/cargo/reference/source-replacement.html). Its [vendor documentation](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html) and [generate-lockfile documentation](https://doc.rust-lang.org/cargo/commands/cargo-generate-lockfile.html) describe the frozen/offline and explicit lock-generation boundaries. Independent archive and full-file verification remains authoritative.
