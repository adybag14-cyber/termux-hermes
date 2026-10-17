# NeuTTS: six non-Rust native dependency preparations

## Current result and scope

The six remaining non-Rust source routes are ready for native review and execution. **Host preparation and 48 focused host checks passed; native compilation and the new operation gates have not run.** This prepares the next stable version. No production admission rule or release output changes.

The work preserves the previously frozen 117-distribution / 194-active-edge NeuTTS candidate. These six roots close to exactly **14 runtime distributions and 10 active dependency edges**. The new lock retains every selected version, complete Requires-Dist / Requires-Python declaration and selected-extra marker for these parent nodes. The complete parent graph remains bound by SHA256 d8596ac31c12b042d76419712802e9787c092b32e66827cd64c720118be7ae68. No dependency is dropped or upgraded to an unrelated candidate.

All six experiments use publicly accessible exact PyPI artifacts and official Termux APT archives. There is **no model-access requirement for this preparation slice**. Its native build and behavior gates remain real work. Full NeuTTS synthesis separately requires the remaining complete software graph and authorized access to its gated model files; see [the full engine closure audit](neutts-engine-closure.md).

| Component | Exact version | Native build route | Complete runtime distributions | Required operation |
|---|---:|---|---:|---|
| audioop-lts | 0.2.2 | Setuptools, Clang, original stable ABI | 1 | Signed PCM scaling and streaming sample-rate conversion |
| PyCryptodomex | 3.24.1 | Setuptools, Clang, original stable ABI | 1 | AES known-answer vector, authenticated encryption/rejection, hash and integer arithmetic |
| PyYAML | 6.0.3 | Setuptools, Cython 3.2.5, actual LibYAML | 1 | C loader/dumper Unicode round trip and malformed-input error |
| SentencePiece | 0.2.2 | Setuptools, Pybind11, CMake and bounded Clang build | 1 | Train a small local tokenizer, normalize Unicode, serialize and round-trip |
| pandas | 3.0.6 | Meson-Python, Cython, original NumPy headers | 4 | Group reduction, NumPy interchange, leap day, Unicode strings and join |
| scikit-learn | 1.9.1 | Meson-Python, Cython, NumPy/SciPy, real OpenMP | 7 | Two-thread KMeans, SciPy linear solve, Joblib threads and Cloudpickle closure |

The runtime pure-wheel subset is cloudpickle 3.1.2, joblib 1.6.0, narwhals 2.27.1, python-dateutil 2.9.0.post0, six 1.17.0, threadpoolctl 3.7.0. pandas also includes the exact original APT NumPy payload; scikit-learn includes original APT NumPy and SciPy payloads. Its seven-node count includes Joblib's Cloudpickle edge. The combined fourteen-node gate runs only after all six independent gates pass.

## Exact source inputs

Every source archive was actually acquired and hash-verified before freezing the lock. All **7,787 regular files** were inventoried. Only SentencePiece's build_bundled.sh changes; the other **7,786 files** remain byte-identical to their source archives. The preparer and native runner verify the exported file bytes and executable bits.

| Exact source | Archive bytes | SHA256 | Source files |
|---|---:|---|---:|
| audioop-lts 0.2.2 | 30,686 | `64d0c62d88e67b98a1a5e71987b7aa7b5bcffc7dcee65b635823dbdd0a8dbbd0` | 16 |
| pandas 3.0.6 | 4,667,686 | `66b07ef7315a31bfe1089cd3d71a7de781c9dca986762d0b4fe7c0ef17465d10` | 1,597 |
| pycryptodomex 3.24.1 | 4,934,627 | `09081666ffc599976c0b8b29caf2cf82212c0f05bed233c8f8ed53e4f6e1d356` | 623 |
| pyyaml 6.0.3 | 130,960 | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` | 641 |
| scikit-learn 1.9.1 | 7,786,908 | `629cada3e33e2b9bf376cdc7614a47a4140b8aedc1d836579e359736fbd82977` | 1,550 |
| sentencepiece 0.2.2 | 8,218,435 | `3d2b5e824b5622038dc7b490897efe05ebbbb9e7350fc142f3ecc8789ef9bdf6` | 3,360 |

Source archives and exported trees remain separate evidence. The preparer rejects existing output directories, unsupported archive members, altered patches and inconsistent source files. Its fresh export is committed atomically after complete input verification.

## Complete isolated build environment

The native runner creates an ordinary, GIL-enabled CPython 3.14 venv with system site-packages disabled. It installs nine exact pure build wheels and copies the complete two-distribution APT NumPy/SciPy Python payloads. Before each backend executes, the actual visible build inventory must match **11 distributions** and every static/dynamically returned build requirement must be satisfied by the frozen versions.

Setuptools 83.0.0 and Packaging 26.0 reuse prior selections. The seven other build wheels are newly selected below. Versioneer's declared toml extra remains accounted for; its old-Python tomli marker is inactive on Python 3.14 rather than deleted.

| Exact build wheel | Bytes | SHA256 |
|---|---:|---|
| cython 3.2.5 | 1,257,622 | `dc1c8cebb7df5bce37f5f8dc1e5bf04313272a5973d50a55c0ec76c83812911b` |
| meson 1.12.1 | 1,108,668 | `930bc7542cbd9f57009e182fd014eba48cf1a0180a7b9006d2d32d8f168d8b02` |
| meson-python 0.21.1 | 29,579 | `270bc9b78957c47e0aa1758ad616dba3f943d8f9cbdb944d318c3c1c7a49e4bd` |
| packaging 26.0 | 74,366 | `b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529` |
| pybind11 3.1.0 | 319,402 | `b8488090f8acffbcb6b5d6a85571a6827a0a2981ffb75e5a0b27b87c4a6b7dd0` |
| pyproject-metadata 0.12.1 | 23,452 | `f7162d580a96386a8eb096da06215f981f547d1490f03055ef99e323bc2da427` |
| setuptools 83.0.0 | 1,008,090 | `29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3` |
| versioneer 0.29 | 46,785 | `0f1a137bb5d6811e96a79bb0486798aeae9b9c6efc24b389659cebb0ee396cb9` |
| wheel 0.46.3 | 30,557 | `4b399d56c9d9338230118d705d9737a2a468ccca63d5e813e2a4fc7815d8bc4d` |

The host verifier checks each actual archive identity, every ZIP CRC and RECORD hash/size, metadata, tags and complete member inventory without executing package code. This includes Meson's two wheel data-scheme files under share/man and share/polkit-1. The new installed-byte verifier explicitly maps those files into the isolated prefix. An actual Meson 1.12.1 wheel replay verified **255 unchanged files and both external data files**; a modified data file was rejected.

## Focused portability changes and required native controls

### SentencePiece compiler flags and bounded jobs

The original 0.2.2 build script replaces CMAKE_CXX_FLAGS with its own four flags, losing the caller's Android API and ARM baseline arguments. It also calls nproc despite a requested CMake job limit. An exact original source fixture reproduces both behaviors in an argument-recording host test.

The patch prepends the caller's CXXFLAGS to the original four flags and uses a validated CMAKE_BUILD_PARALLEL_LEVEL, defaulting to two jobs. It preserves the other upstream CMake options, including packaged external normalization data. Tests cover the original failure, independent git-apply replay, default/explicit budgets, malformed budgets, retained flags and absence of an nproc call after the patch.

The native runner explicitly sets API 24 / ARMv8-A and two jobs. It verifies the generated CMake cache before accepting the wheel. The operation gate uses the actual packaged normalizer and a newly trained small local synthetic tokenizer to check standard full-width Unicode normalization, serialized model loading and tokenization round trips. No pretrained tokenizer or speech model is downloaded.

### Meson-Python's actual Android ELF path

Exact Meson-Python 0.21.1 requests a patchelf build dependency only in its Linux platform branch, while its RPATH implementation also uses patchelf for Android ELF files. This route supplies the actual official native program without suppressing RPATH handling or changing backend declarations.

Before either Meson component builds, a native control compiles a real small ELF library with an original RPATH, calls the unchanged backend's Android RPATH repair, checks the resulting path with the verified patchelf program and executes a known C function from the library. This native control remains pending.

### Required OpenMP and PyYAML acceleration

The exact official Clang archive already contains omp.h and static libomp.a. The runner verifies those installed bytes against the archive. Before scikit-learn builds, the actual C compiler must execute a two-thread OpenMP reduction. The installed scikit-learn must report compiled OpenMP and two effective threads, then pass KMeans and linear-regression operations with standard float64 tolerances. The experiment clears any SKLEARN_NO_OPENMP override.

PyYAML uses its upstream force-LibYAML and force-Cython controls. Its runtime must load the C extension, report LibYAML 0.2.5, and pass C loader/dumper and error-propagation tests. An unaccelerated fallback cannot satisfy this gate.

## Official APT archive closure

The new preparation retains **51 exact APT archives**: the unchanged 44 compiler archives plus seven needed for runtime/payload provenance and the new tools. Those seven retained additions total **20,135,812 bytes**. Every original compiler archive identity remains unchanged.

Only **two packages are new beyond the existing 141-package scientific-foundation/compiler union**:

| New official APT package | Archive bytes | Archive SHA256 |
|---|---:|---|
| LibYAML 0.2.5-5 | 46,500 | fad02df630fcee4219133112377965d119543a9d999dcbc6e19a2c1550bf2b60 |
| patchelf 0.19.2 | 82,924 | deec5bbdcd47d8f6751e76fa9faf49348783256c3c488c3638de240f1e61452a |

These add 129,424 archive bytes beyond the original union. The fresh container installs the original 19 compiler additions plus these two. Its exact APT plan rejects removals, unrelated additions, upgrades and omissions; the 30 already-installed packages in the retained closure must preserve their versions and architectures. All 51 archive hashes, sizes and Debian controls are checked before installation.

The saved official index inputs remain unchanged:

- InRelease: 14,016 bytes; SHA256 249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901.
- Packages.gz: 727,968 bytes; SHA256 dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6.

Host checks verify the signed-message SHA256 binding and exact selected archive rows. **Native APT must separately authenticate the saved index** using the unchanged configured trust store, without insecure/unauthenticated exceptions. The private index does not replace global source configuration. The index legitimately lists two versions of three unrelated packages, so matching uses the complete package/version/architecture/archive identity.

## Runtime isolation, original metadata and ABI evidence

Each component receives a separate venv containing its complete selected runtime subset. The runner verifies the actual visible distribution count, every installed wheel file, unchanged dependency declarations and absence of unowned site files. pandas and scikit-learn receive complete verified APT Python copies:

| Original APT distribution | Copied files | Copied bytes |
|---|---:|---:|
| NumPy 2.5.4 | 924 | 18,943,738 |
| SciPy 1.18.1 | 1,429 | 56,745,210 |

Original METADATA, WHEEL and RECORD remain byte-identical. The original legacy cp314-cp314-android_aarch64 wheel tag produces an actual nonzero pip-check result on the modern Android convention. Those exact diagnostics remain raw failures, and are never reported as a successful pip check. The runner separately requires matching CPython ABI, supported modern convention, exact APT archive/file provenance and no missing/conflicting declared dependency. Any additional pip diagnostic fails. No distribution is retagged.

Built wheels must retain their original backend-generated supported Android API24 tags: audioop's cp313-abi3, PyCryptodomex's cp37-abi3, and cp314-cp314 for the other four. No platform override or post-build retag is used.

After real operations, /proc/self/maps proves which wheel/APT extension bytes were loaded. The runner checks ELF64/AArch64 identities and loaded-library ownership and bytes against retained exact archives. Foreign GNU/Linux ABI dependencies and unverified mappings fail. Import success alone cannot satisfy a component.

## Workflow and remaining evidence

The [new workflow](../.github/workflows/neutts-nonrust-components.yml) has manual dispatch and narrow file-filtered pushes only on the preparation branch. It uses the same digest-pinned ARM64 Termux container, ordinary UID 1000, **two CPUs, six GiB, 512 processes and a 100-minute container timeout**, plus individual source-build timeouts. The GitHub token remains confined to host-side frozen-candidate retrieval.

Host preparation extracts the original catalog bytes through the existing exact e271 fetcher and bounded nine-wheel extractor. This slice preserves its selected main wheel bytes and original source identities. The original complete seven-case scientific foundation runs once before independent component execution.

Every component writes separate source-backend, built-wheel, installed-inventory, raw-pip and operation receipts. A failed component does not prevent other routes from being attempted after shared preflight succeeds. The combined fourteen-distribution / ten-edge operation gate runs only after all six independently pass. Shared foundation, signed-index, toolchain or environment failures stop before source execution and remain explicit.

The host audit records **48 passed / 0 failed / 0 skipped**, independent patch replay, shell/embedded-Python syntax checks, complete actual cached-input replay and the actual Meson data-mapping replay. Native execution of these new gates remains pending. Full 117-distribution assembly, speech synthesis, model access and production admission remain separate. NeuTTS's interpreter bound is unchanged.

## Frozen implementation identities

| New implementation input | Bytes | SHA256 |
|---|---:|---|
| `scripts/neutts_nonrust_runtime_lock.json` | 4,400,422 | `cf1c2453050f7a34e7aa733b1574a8ee3936f0e901293e21b5b6695a27b9a7a8` |
| `scripts/prepare_neutts_nonrust_runtime.py` | 23,622 | `16298ad398312c6894bb0972bfc357232bf3bf04df57a593fc8b4413f542cbbf` |
| `scripts/compatibility_probe_neutts_nonrust.py` | 52,988 | `c7d02db4494d8f6861fb1fb3ea7fba5a792e86bddc8db34fe003a69edadb8033` |
| `scripts/neutts_nonrust_operations.py` | 9,823 | `ce18cd98cdba38695b26fe36958e7621812a54601522acce1f9734451f55e368` |
| `scripts/compatibility_probe_neutts_nonrust.sh` | 8,387 | `b6716cd5d5c138bb32ad5c800298784a9f59e149550ab1be74aaef6a97e1b69d` |
| `.github/workflows/neutts-nonrust-components.yml` | 1,821 | `d3e2a77b599eea99352070332683a993faf7716a87f8a7b78f3a902dba45bbd3` |
| `patches/next-stable/sentencepiece-bounded-build.patch` | 893 | `22b79b03ef620a34ecac70a5ee500953cd1622f314373c0cae22e1d7359a42c3` |
| `tests/test_neutts_nonrust_preparation.py` | 22,521 | `5ef8e51514234e9bdd4ad4761fcde663818b97902d74376ef4385c530edbb98b` |
| `tests/fixtures/neutts_nonrust/sentencepiece_build_bundled.sh` | 797 | `9e220e130f5bec5b50dd7ddf5a6008300b7b6617e6b5d9261758abbe4210b6c5` |
| `tests/fixtures/neutts_nonrust/README.md` | 832 | `afaddcdc490546231e8e51b07f3595f97f71a4ed4bfea9a596fc58395ba6ef63` |

The complete report is [the non-Rust preparation audit](../audit/neutts-nonrust-preparation-20261017.json). Adjacent raw evidence retains source/backend inspections, exact new PyPI metadata, the preparation receipt, both host test runs and final mapping replay.

## Primary source inputs

- [audioop-lts 0.2.2 exact source archive](https://files.pythonhosted.org/packages/38/53/946db57842a50b2da2e0c1e34bd37f36f5aadba1a929a3971c5d7841dbca/audioop_lts-0.2.2.tar.gz)
- [pandas 3.0.6 exact source archive](https://files.pythonhosted.org/packages/e2/17/d7b106e05bfa642e8694451e7d3d759c6a241c5386a5d962e4f66c047e06/pandas-3.0.6.tar.gz)
- [pycryptodomex 3.24.1 exact source archive](https://files.pythonhosted.org/packages/f4/e7/50e72301e32acb73a314e663c2014e1ddefc019d5f434ff14ec89861d664/pycryptodomex-3.24.1.tar.gz)
- [pyyaml 6.0.3 exact source archive](https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz)
- [scikit-learn 1.9.1 exact source archive](https://files.pythonhosted.org/packages/d2/eb/eaf5e07fcc0da7149b0e084f24e54edd7441b9a89ce7e034032ae97fe3a0/scikit_learn-1.9.1.tar.gz)
- [sentencepiece 0.2.2 exact source archive](https://files.pythonhosted.org/packages/cc/33/ea3cb3839607eb175da835244a798f797f478c5ddf0e8ecdf57ea85a4c70/sentencepiece-0.2.2.tar.gz)

Build-wheel URLs and exact metadata identities are recorded in the lock and adjacent raw audit files. APT inputs come from [the official Termux main repository](https://packages.termux.dev/apt/termux-main/) and the saved signed snapshot.
