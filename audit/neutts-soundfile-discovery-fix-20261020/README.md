# SoundFile Android system-library discovery correction

## Measured native failure

Native Perth run 39440363735 at source commit
4a95a07086a0b88d209485ac7a01cdd40e268f40 passed all seven unchanged scientific
foundation cases, installed the isolated 43-distribution environment, validated
all 50 active dependency edges and Python bounds, and passed the auxiliary real
Numba/LLVM JIT, Torchaudio, Scikit-learn, Audioop, CFFI, libyaml, MsgPack,
MarkupSafe and Charset Normalizer operations.

It then failed while importing original SoundFile0.13.1, before loading the public
watermark checkpoint or running SoundFile WAV I/O. The actual error was
`sndfile library not found using ctypes.util.find_library`.

The whole 321,202,922-byte source artifact was independently rehashed as
`32195276aad39eb49026bad6b726cdef75073d245e3dabbafa717e68020c6eab`.
Its 267-member inventory contains the original retained dependency archives and
raw receipts. The bounded selected files under `native-failure/` were CRC
checked and are listed by exact size/hash in `NATIVE-FAILURE-REVIEW.json`.
This is failure evidence, not a successful public watermark result.

The native after-install inventory proves the original libsndfile1.2.2-3
aarch64 package was installed. Its 223,576-byte archive matches the original
signed snapshot SHA-256
`1e1fb77b14ec26f3ff6ded069e9ec816ab7535ae5d074122c6727b0f59d8aff3`.
The actual library is a regular 439,352-byte AArch64 file at
`/data/data/com.termux/files/usr/lib/libsndfile.so`, with the same SONAME and
SHA-256 `079263392fddcdd975f2d452f6fd654e26f199fda1c85e08d67fedfbb4b55825`.
The whole original archive, including its license material, is retained here.

## Product source correction

SoundFile first tries a packaged native library, then ctypes library discovery,
then a platform-specific explicit system filename. The original explicit
fallback covers Darwin, Windows and Linux but omits Android. The measured
interpreter reports `sys.platform == "android"`; ctypes discovery returned
None, and the unsupported-platform branch re-raised before attempting the
existing system libsndfile filename.

The patch adds Android only to the existing explicit filename condition:

`elif _sys.platform in ('linux', 'android'):`

It leaves the packaged Linux-library branch unchanged, so Android cannot select
a packaged GNU/Linux library through this correction. The ordinary
`_ffi.dlopen("libsndfile.so")` call performs the actual load. Successful ctypes
discovery still takes precedence. A missing or incompatible native library
still raises its normal error. No Python ctypes source is patched, no library
handle is injected, no import is bypassed, and no new native package is installed.

The original Python ctypes utility is retained only as diagnostic source
context, taken from the unchanged exact Python3.14.6-1 archive already retained
under the repository's preparation archive cache. It is not modified or used to
replace the native standard library.

## Exact derivative

| Item | Bytes | SHA-256 |
| --- | ---: | --- |
| Original SoundFile0.13.1 wheel | 25,751 | a23c717560da2cf4c7b5ae1142514e0fd82d6bbd9dfc93a50423447142f2c445 |
| One-line source patch | 376 | f0487e9019c2f30df408e61a274a584589a332caa31029c37b7068c518ebdb53 |
| Deterministic derivative wheel | 90,959 | ad4f764ecc142ab5a9e05a0d61fda83ddf190fb7d59ca3c0da094be6229ee992 |

The wheel keeps its original filename and version; the complete derivative hash
and source provenance distinguish it. Only `soundfile.py` and its truthful
RECORD change. The six other members are byte-identical, including METADATA,
WHEEL, LICENSE and the CFFI definitions. All original dependency declarations,
Python bounds, tags and package identity remain unchanged. Stored ZIP members
and fixed archive fields make the complete result reproducible across hosts.

`scripts/prepare_neutts_soundfile.py` verifies the original complete wheel,
source patch, exact derived member inventory, complete RECORD and prepared
receipt. `scripts/neutts_soundfile_lock.json` binds the original public catalog,
both complete wheel identities, every original/derived member, the patch, and
the exact original libsndfile package.

## Host checks and native retry boundary

Host regression tests execute the actual original and patched loader branches
with explicitly simulated platform/lookup/FFI responses. They reproduce the
original Android failure, verify the new filename fallback, preserve successful
ctypes and packaged Linux behavior, and require normal missing-library failure.
These dispatch tests do not claim actual native library loading or audio I/O.

Additional checks verify exact wheel reproducibility, unchanged metadata and
licenses, independent RECORD integrity, malformed input/receipt refusal, the
original signed libsndfile archive and actual AArch64 SONAME, and the retained
native failure's passed and failed stages. The final combined SoundFile, Perth,
and static ELF host suite passes 62 tests plus 232 subtests with zero failures
or skips. `HOST-VERIFICATION.json` binds the final source hashes and full
43-node/50-edge input re-verification.

The Perth preparer now reconstructs and verifies the SoundFile derivative and
requires exact equality between that result and the wheel installed in its
isolated environment. The original two extra-APT installs, all scientific cases,
offline container boundary, library ownership/hash checks, strict checkpoint
loading, and real 24/32 kHz public API operations remain mandatory. The probe
records the explicit fallback library name separately from the unsuccessful
ctypes lookup.

At this checkpoint the corrected native retry is pending. There is no claim
that SoundFile WAV I/O, the public watermark checkpoint, the NeuTTS engine, or a
device/gated speech model passed. No production admission or release changes.
