# Original APT extension prerequisite for NeuTTS

The preparation and host regressions are complete. Native execution remains a
separate required gate. This work preserves the original package versions,
dependency declarations and Android wheel tags; it does not admit a NeuTTS engine
or publish a Hermes package.

## Exact scope

The five routes come from the unchanged 117-distribution runtime design and its
frozen APT closure. Their Python versions satisfy the original requirements.

| Distribution | Original Termux package | Required native operations |
| --- | --- | --- |
| PyArrow 26.0.0 | python-pyarrow 26.0.0-2 | NumPy zero-copy conversion, IPC stream and file roundtrip, memory mapping, compute filtering/aggregation, Dataset filtering and projection |
| lxml 6.1.3 | python-lxml 6.1.3 | XML parsing, XPath selection and XSLT transformation with external access disabled |
| Msgpack 1.2.3 | python-msgpack 1.2.3 | Actual compiled encoder/decoder, independent wire-byte oracle and incremental streaming |
| Pillow 12.3.0 | python-pillow 12.3.0 | Actual native imaging core, PNG encode/decode and independently checked nearest-neighbor resize |
| psutil 7.2.2 | python-psutil 7.2.2-2 | The process's own PID, PPID, UID, executable, name, memory, threads and CPU times |

The exact original archives contain **893 regular files, one documentation
symlink and 34 AArch64 ELF files**. The preparation verifier reads and hashes every
original file and records the symlink target and mode. It does not unpack or run
an APT package recipe.

The source identity and archive evidence are bound by
[scripts/neutts_apt_extensions_lock.json](../scripts/neutts_apt_extensions_lock.json),
derived from:

- [The unchanged runtime design](../scripts/neutts_runtime_closure_design.json).
- [The 78-package, 151-edge APT closure](../audit/neutts-runtime-reuse-20261017/apt-extension-closure-design.json).
- [Original archive, metadata and ELF inspection](../audit/neutts-runtime-reuse-20261017/apt-extension-byte-inspection.json).
- [The original 122-package foundation](../audit/neutts-native-20261017/run-39058569758/NEUTTS-PINNED-APT.tsv).
- [The frozen signed repository snapshot](../audit/neutts-runtime-index-20261017/InRelease).

## Installation and provenance boundaries

The five roots require **18 selected packages**, totaling **14,043,104 compressed
bytes**, beyond the original 122-package foundation. These additions are derived
against the foundation alone. The driver does not request the separate 44-package
compiler closure.

The native gate retains **84 exact provenance archives**, totaling **126,542,852
bytes**. This is the 78-package extension closure plus the six original scientific
APT distributions outside that closure. Those extra archives allow the unchanged
APT provenance validator to verify the original seven distributions alongside the
five extensions. Only the 18 selected additions are install targets.

After the unchanged seven-case scientific foundation passes, the gate:

1. Checks the exact archive set, complete SHA-256 identities, controls and signed
   index membership.
2. Reauthenticates the exact frozen InRelease and Packages.gz through native APT's
   configured Termux trust store and fresh isolated list files.
3. Simulates a download-free installation and requires all 18 exact names and
   versions. Removals, purges, extra packages, version changes and omissions fail.
4. Installs the same reviewed selection, then compares the **whole** before/after
   DPKG state. A selected package already installed at the exact version is
   recorded as a reinstall; it is not counted as new.
5. Checks all 84 installed package controls, the complete original file lists and
   modes of the five roots, their metadata and all 34 original native files.
6. Runs the five operation groups as separate bounded native processes and checks
   every actual mapped native library against its original APT archive or the
   separately pinned image runtime.
7. Rechecks the original five-package files after the operations.

The archive parser selects full package/version/architecture/path identities from
the signed index. The actual snapshot contains 3,011 package rows and 3,008 package
names; unrelated additional versions remain valid records.

## The retained pip failure

The new helper binds exactly **12** APT distributions in its own frozen manifest.
It calls the original validator's generic provenance and requirements functions.
The original validator's seven-name constants, manifest hash and loader remain
unchanged.

The original WHEEL platform spelling remains android_aarch64. Four new packages
carry cp314-cp314 tags; psutil carries cp36-abi3. Nothing rewrites those tags or
modifies pip's supported-tag set.

The native gate requires the raw pip check to exit **1** with exactly the twelve
original platform-tag failures. A separate receipt must establish consistent
Python requirements, actual interpreter/ABI compatibility and exact APT ownership.
The raw pip result is always recorded as failed. An unknown thirteenth failure,
a missing dependency or altered metadata is a gate failure.

## The pinned image's AOSP libraries

The unchanged foundation's native mapping evidence includes five libraries under
usr/opt/aosp/lib64: libc++, libc, libdl, liblog and libm. Their owner is aosp-libs.
They are part of the pinned container image's runtime.

The new gate binds those five exact paths, hashes, byte counts and ownership to
the original foundation evidence, verifies them against the fresh foundation and
checks the actual mapped copies. Their authority is recorded separately from
the signed Termux snapshot archives. There is no general exception for arbitrary
files in usr/opt, /system or /apex. Unknown mappings retain their exact offending
path and the complete raw /proc/self/maps in the failed case evidence.

## Review and execution

The host fixture regression command is:

~~~sh
NEUTTS_APT_EXTENSIONS_INPUTS=/absolute/path/to/prepared-inputs \
  python3 -B -m unittest discover -s tests -p test_neutts_apt_extensions.py -v
~~~

The completed cached replay passed **33 tests with zero skips**. It includes
actual archive and metadata verification, fresh output preparation, the real
multiversion index, incorrect archive/control/ELF identities, exact installation
planning, whole-state drift, unknown mappings and preservation of a real failed
child's diagnostic. Host checks do not execute the Android extensions.

The [dedicated preparation audit](../audit/neutts-apt-extensions-preparation-20261017.json)
records the exact fixture, logs, source identities and limits.

The native entry point on an ARM64 Linux host is:

~~~sh
bash scripts/compatibility_probe_neutts_apt_extensions.sh \
  --out probe-results/neutts-apt-extensions
~~~

The [workflow](../.github/workflows/neutts-apt-extensions.yml) has manual dispatch
and a narrow preparation-branch push trigger. It uses read-only repository
permissions, the original pinned image, UID 1000, two CPUs, 6 GiB of memory and a
40-minute container limit. It preserves evidence even after failure.

A native pass requires the original seven-case foundation, the twelve-distribution
provenance/requirements receipt, all five operation receipts, original-file checks
before and after execution, and the explicit mapping evidence. Passing these
prerequisites does not prove the complete 117-node runtime, NeuTTS synthesis,
model access, training, device audio or production packaging.
