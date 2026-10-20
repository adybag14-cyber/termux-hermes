# Android PortAudio discovery in the full Hermes audio environment

The exact native full-Hermes preparation passed before sounddevice failed to find
PortAudio. This preparation fix addresses that specific library-discovery
failure. Its 164 focused host tests pass; the next native reconstruction and
physical microphone/VAD checks remain separate gates.

## Observed cause

[Native run 39077868541](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39077868541)
retained the full original exception: OSError, “PortAudio library not found,” at
sounddevice.py line 72. The probe had already exercised native NumPy and cffi and
loaded the exact owned PortAudio and OpenSL ES objects by absolute path.

The exact packaged CPython ctypes.util source uses generic POSIX discovery. Its
search depends on ldconfig, gcc/cc, ld.lld or llvm-objdump. Those compiler tools
are absent from the isolated packaged runtime. Loading the library first does
not make that discovery function return a filename. The saved failure occurred
before PortAudio initialization, so it is not evidence of a microphone hardware
or permission failure.

The [original failure audit](../audit/audio-hermes-native-20261017/run-39077868541.json)
and [source diagnosis](../audit/audio-sounddevice-discovery-20261017/source-diagnosis.json)
bind this analysis to the actual original payload inventory and traceback.

## Exact compatibility change

The [patch](../patches/next-stable/sounddevice-android-discovery.patch) adds a
fallback only when all original library lookups return None and sys.platform is
exactly android. It asks Android's real loader to resolve libportaudio.so through
the runtime's existing library search path.

An existing successful lookup still wins. The original dlopen call, real loading
errors, PortAudio initialization and the rest of the module remain unchanged.
This does not replace ctypes.util globally or add compiler tools to the runtime.

| Item | Original | Prepared derivative |
| --- | --- | --- |
| Distribution | sounddevice 0.5.5 | sounddevice 0.5.5 |
| Wheel tag | py3-none-any | py3-none-any |
| Wheel bytes | 32,807 | 130,096 |
| Wheel SHA-256 | 30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f | b98585045e53173f589267e8ee543f034ba4229b0696ec32032b9f5f5637caf7 |
| Changed member bodies | — | sounddevice.py and its RECORD |
| Other member bodies | Six | All six preserved exactly |

The deterministic derivative uses stored ZIP entries, avoiding differences
between host compression libraries. This accounts for its larger container
size. Version, dependency declarations, tags and the original MIT license are
unchanged. The original wheel remains in the reconstruction inputs and as a
small pinned regression fixture.

## Canonical package-manager provenance

The preparer first lets the unchanged canonical package manager create its
catalog from the original wheel. That records the actual locked registry-wheel
URL, original download SHA and source fingerprint. It then derives the new wheel,
changes only the Sounddevice row's installed wheel size/SHA and recomputes the
catalog descriptor.

All 100 original catalog rows and the NumPy row remain identical. The original
uv.lock and package-manager API are preserved. The derived wheel therefore
retains truthful original-wheel provenance and cannot be mistaken for a wheel
built from the separate source archive.

The canonical application environment is built fresh and offline from that
catalog at its final path. The probe checks the exact installed patched source
before attempting a real sounddevice import. Discovery and loader errors still
fail the gate; actual PortAudio initialization errors retain their own
diagnostics.

## Verified and remaining checks

The focused host suite passes **164 tests, zero failures and zero skips** when
the original canonical PM source fixture is supplied. It exercises the actual
source loader block with controlled library calls, independently applies the
patch with Git, checks every original/derived RECORD entry, preserves all other
module AST and verifies canonical selection against the original locked wheel.

An independent review recomputed the same wheel bytes and checked all original
member/provenance bindings. These checks do not execute native PortAudio.

The [native workflow](../.github/workflows/audio-hermes-preparation.yml) carries
the exact new patch in its offline reconstruction bundle and will prepare/probe
twice at independent final paths. Successful dependency preparation or device
enumeration does not establish physical capture or VAD. A real Android
microphone test still needs the user's device and the relevant permission.

This is preparation for the next stable version. No Debian release, package
version, main-branch installer or APT publication is changed.
