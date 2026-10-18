# Audio wrapper namespace dependency

## Confirmed failure and repair

The first complete Hermes audio environment in
[run 39080859246](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39080859246)
passed canonical environment assembly: a fresh manager and application, 101
application distributions, 6,906 wheel-owned files and a 102-wheel catalog with
all 100 original rows preserved. The Sounddevice Android discovery derivative
was installed with its exact reviewed bytes and original registry identity.

The runtime probe then rejected this mapped external dependency:

    /data/data/com.termux/files/usr/lib/libtermux-platform-ns.so

The retained failure is a provenance failure. The probe had progressed beyond
Sounddevice discovery and readiness handling, but this run did not preserve the
precise PortAudio initialization result before failing. It does not establish
complete audio readiness, and the second reconstruction was not reached.

The unchanged, already pinned libandroid-stub 30-2 archive contains the missing
dependency. Direct inspection of both original ELF dynamic tables proves:

| Original member | Bytes | SHA-256 | DT_NEEDED |
| --- | ---: | --- | --- |
| libOpenSLES.so | 11,480 | 87c61d872767541e332783d85f70bfdc1b2d48e373ef3025380345171bac4db9 | libc.so, libdl.so, libtermux-platform-ns.so |
| libtermux-platform-ns.so | 6,552 | 6c39c6a3318accd5e34f4f2c9e5c9e14eed113fb3a92e8c0be86006dc9256e34 | libc.so, libdl.so |

Both are AArch64 ELF64 little-endian objects from the original 26,788-byte
archive, SHA-256
74087792a86e3f90772627f2217797e422e5d5fc47f24ad825fc3bbb539a667a.
The namespace bytes also match the earlier native scientific-foundation receipt.

The preparer now validates both original members and both destination paths
before copying either library into its new owned payload. It rejects changed or
missing members, archive drift, collisions and changes to existing runtime
libraries. The probe loads the owned namespace first and requires the exact
owned PortAudio, wrapper and namespace mapping hashes. The external prefix
allowlist is unchanged. Before applying provenance checks, it now saves actual
initialization and mapped-object observations, so any later failure retains its
earlier diagnostic.

## Validation and remaining gate

All 173 focused host tests passed with zero skips. Nine new cases exercise the
actual small original archive and the dependency, collision, corruption and
payload-preservation boundaries. The independent review verified both original
ELF dependency lists, all three source-file hashes and the unchanged catalog,
native error handling and mapping restrictions.

An earlier host command timed out while unrelated trivial execution commands
also stalled; that attempt has no test result. The completed retry's raw log and
XML are retained. No native library was loaded by the host fixture tests.

The next native run must reconstruct and probe two independent full environments
with the new owned namespace member. Physical microphone permission, real PCM
capture, silence stopping, duration limits and cleanup still require Android
audio services and an owner-initiated device check. This preparation creates no
release, changes no package version and does not certify microphone/VAD.

Evidence:
[original native failure](../audit/audio-hermes-native-20261018/run-39080859246.json),
[repair and host review](../audit/audio-platform-namespace-20261018.json).

## Subsequent native observation

The namespace repair is confirmed by the owned-library checks in
[run 39083065999](../audit/audio-hermes-native-20261018/run-39083065999.json).
That run retained the actual PortAudio initialization error before a later
container-platform provenance failure. The exact follow-up is documented in
[audio-image-platform-boundary.md](audio-image-platform-boundary.md); the original
failed run above remains a failure and physical VAD remains untested.
