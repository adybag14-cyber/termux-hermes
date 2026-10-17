# Remaining portability work: local ML and Android device integration

This note records the limits that remain after the prepared compatibility fixes.
It is not a claim that these capabilities are impossible on Android.

## NeuTTS 1.4.1

The engine is excluded by the managed Python version, not just the Android OS
marker. The published package and the public source both declare Python
>=3.10,<3.14; the audited Hermes package uses CPython 3.14.6.
The PyPI release supplies platform wheels but no source distribution.
The public source is available and still declares version 1.4.1, so a source port
can be considered without pretending an sdist exists.

Hermes declares the exact NeuTTS version, but its current resolver environment
is Python >=3.14. The resulting uv.lock contains no resolved NeuTTS, NeuCodec,
Torchaudio, librosa, or llama-cpp-python package records. The Torch and ONNX
Runtime records mentioned below come from other selected or optional graphs;
they are not a complete locked NeuTTS closure. A separate engine environment
would need its own exact dependency resolution and native validation. The
[upstream resolver configuration](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/pyproject.toml)
and the audited lock establish this distinction.

Primary sources:

- [Exact PyPI release metadata](https://pypi.org/pypi/neutts/1.4.1/json).
- [Public source at the reviewed version declaration](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/pyproject.toml).
- [Official Termux PyTorch recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/python-torch/build.sh).
- [Official Termux Torchaudio recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/python-torchaudio/build.sh).
- [Official Termux SciPy recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/python-scipy/build.sh).

Official Termux already builds native PyTorch and Torchaudio. Their existence is
evidence that Android ML support is feasible; it does not make their current
versions interchangeable with Hermes' frozen Python dependency graph. The
recipes inspected on 17 October 2026 declare PyTorch 2.14.1, Torchaudio 2.11.0
and SciPy 1.18.1. The [reviewed recipe pins](../audit/termux-recipe-pins-20261017.json)
record the immutable source commit and file digests. Hermes' current lock
contains PyTorch 2.14.0, while the NeuTTS
dependency group is excluded for the managed interpreter. No Android wheel for
the locked PyTorch or ONNX Runtime entries is present in that lock.

The earlier version of the separate scientific dependency experiment
**passed all six native behavior cases** in
[run 39055874446](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39055874446)
at exact head `d439e8100bc89dbfe681fc03aa22017f175b8b2d`. The
[verified result](../audit/neutts-native-20261017/run-39055874446.json)
binds all 122 pinned APT archives, the exact supplemental Python artifacts from
the upstream lock, the real Termux system interpreter, mapped AArch64 libraries,
and each independent child-process receipt.

| Component | Native behavior observed |
| --- | --- |
| Torch 2.14.1 | Exact CPU convolution and matrix multiplication results. |
| Torchaudio 2.11.0 | 24 kHz to 16 kHz resampling; 1,600 output samples with mean absolute error 0.0002513. |
| TorchCodec 0.17.0 | Decoded the 16 kHz PCM fixture into 1,600 samples with zero maximum error. |
| NumPy 2.5.4 / SciPy 1.18.1 | Linear-system solution and FFT matched their numerical oracles. |
| llvmlite 0.49.0 | Real Android AArch64 MCJIT execution returned the expected 23.0. |
| Soxr 1.1.0 | Resampling produced 1,600 samples with mean absolute error 2.1722e-7. |

The first run, [39053355817](../audit/neutts-native-20261017/run-39053355817.json),
stopped Torch, Torchaudio and TorchCodec at missing `typing_extensions`, while
the other three cases passed. The supplemental dependency repair then completed
the installed metadata graph and actual MarkupSafe/Jinja2 escaping checks.
[Run 39055038031](../audit/neutts-native-20261017/run-39055038031/verification.json)
still failed before native cases because pip rejected the seven original APT
scientific distributions' `android_aarch64` WHEEL tags.

That pip compatibility issue is **still unresolved**. The final probe records
`dependency_closure_passed=true` and `scientific_behavior_passed=true`, alongside
`pip_check_passed=false`. Diagnostic continuation requires exactly the seven
observed unsupported-platform messages, expected versions, and original WHEEL
file hashes from the pinned APT archives. Missing dependencies, version conflicts
or any other pip error stop the probe. No wheel tags are rewritten and no
interpreter platform is spoofed.

### Stricter provenance preparation

The [active experiment](../scripts/compatibility_probe_neutts.sh) now incorporates
the incoming preparation through commit
`19ab7a1ce9f496dd8dd291d19e3818bb5f878048`. Its frozen nine-wheel closure
uses official native MarkupSafe 3.0.4; the earlier passing experiment used an
upstream MarkupSafe 3.0.3 source fallback. These are different inputs.

The added validator binds the original APT archives and package identities,
installed interpreter and metadata bytes, all recorded pip source files and
their unique package ownership, the installed dependency inventory and
Requires-Python requirements. Diagnostic continuation still requires the exact
seven original pip platform-tag failures, with interpreter and ABI checks.
It does not rewrite metadata or supported tags. A SymPy installed-file check now
accounts for its wheel data-directory installation path.

Fresh native validation of this combined implementation is pending. The
[reconciliation record](../audit/neutts-provenance-reconciliation-20261017.json)
preserves the older six-case proof under its original inputs and records the new
validation separately. The [GGUF feasibility study](neutts-default-gguf-feasibility.md)
and isolated llama-cpp-python Android loader patch remain source preparation,
outside the main package candidate and without a native inference claim.

This disposable Termux system-Python experiment records the rolling base upgrade
separately from the pinned dependency archives. Its
[native workflow](../.github/workflows/neutts-termux-probe.yml) does not install
NeuTTS, change Hermes PM, validate synthesis or alter the current engine
exclusion. Its successful scientific measurements do not establish the complete
NeuTTS dependency closure or compatibility with the bundled Hermes interpreter.

The engine still needs one certified runtime arrangement:

1. Port the exact NeuTTS source and its native codec/inference closure to the
   managed CPython ABI, then adjust the Python requirement only after actual
   synthesis works; or
2. Give the engine a separately managed, supported interpreter and native
   dependency environment, with subprocess lifecycle and output validation.

Either route needs actual synthesis with reference audio, model/codec loading,
phonemization, streaming where offered, and cleanup after cancellation. Simply
removing the marker, importing a different Python's system packages, or pointing
the bundled interpreter at an APT site-packages directory would not establish
that compatibility. No such shortcut is part of this preparation.

## Local computer use

The pinned CUA driver release for Linux ARM64 is a glibc executable with
interpreter /lib/ld-linux-aarch64.so.1. Its Linux backend assumes desktop
display/input facilities, including X11/Wayland and accessibility services.

[Reviewed CUA driver source](https://github.com/trycua/cua/tree/cua-driver-rs-v0.21.0/libs/cua-driver/rust).

The prepared remote-provider routing fix lets an Android client select an
explicitly configured remote Linux desktop. The Termux Bot Desktop adapter
provides a separate local virtual X11 display. These are useful capabilities,
but neither supplies Android Accessibility/MediaProjection control of arbitrary
phone apps. A phone UI backend requires that Android integration and its explicit
device permissions. The native X11 driver has now been evaluated
against the virtual desktop, as recorded below.

### Isolated native X11 source-port experiment

The preparation includes a candidate-only source port for CUA's existing virtual
X11 desktop backend. Its source is pinned to commit
`70db98d1bcd92890d778f4978e0eb107a4b66c1b` (CUA 0.21.0), with original
Cargo.lock SHA-256
`27b025bc4fd81074cf18ae614597bec5b7c9d8ea99b2a7aaf45072aec72c64ce`.
The [source preparer](../scripts/prepare_cua_termux_source.py) verifies the clean
Git checkout and both exact registry archives before applying
[the reviewed patch](../patches/next-stable/cua-driver.patch).

The driver/SDK platform configuration admits Android to the existing X11 code.
Two local crate adapters enable clipboard-rs's Unix X11 implementation and align
x11rb-protocol's socket location with Termux's PREFIX/tmp. Both retain their
locked versions; the preparer verifies that all 602 other Cargo package records
remain unchanged. The standalone native probe now **passes all eleven checks** in
[run 39052290704](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39052290704)
at head `3e63be4a65dcb0d6d2c0c2fec86f94546fbba8ed`. Its
[success record](../audit/cua-native-20261017/run-39052290704.json) preserves
the source/input receipts, native linking and PTY/shared-memory ABI proof, a
private D-Bus round trip, all 60 real standalone MCP tool names, and owned cleanup.

The independent Xlib fixture verified a 320x240 screenshot with its two painted
colors, one foreground click at client coordinates (80,60), exactly two scroll
events, the exact typed text, and client geometry (40,60,400,200). Clipboard
write/read returned the exact fixture string. The driver reported input effects
as unverifiable; success was established by the actual fixture events, not that
transport response alone.

The [earlier default-background attempt](../audit/cua-native-20261017/run-39051490364.json)
returned an unverifiable effect and produced no click event. That path remains
uncertified. The successful foreground run also retained a degraded accessibility
response because the private bus lacks org.a11y.Bus; its fallback window element
is not an AT-SPI-tree proof. [Native progress records](../audit/cua-native-20261017/)
retain the actual failures and subsequent bounded corrections.

The experiment checks a private, owned Xvnc desktop using real MCP operations
and independent fixture observations. Its scope includes screenshot capture,
keyboard and mouse events, scrolling, clipboard transfer, window geometry, and
cleanup. It remains separate from Hermes PM admission and the complete package
candidate. Encrypted history still requires a supported secure credential store;
its existing failure behavior is preserved. TigerVNC does not provide the
parallel uinput devices expected by CUA's multiple-pointer implementation.
Android phone application control still requires an Android-specific backend.

### Native Hermes integration completed

The [separate Hermes integration patch](../patches/next-stable/cua-hermes-integration.patch)
now **passes the real registered Hermes tool path** in
[run 39056472835](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39056472835)
at exact head `37bf89d09a2a68a41585389d59b19e5e583c1f23`.
The [verified result](../audit/cua-hermes-resume-20261017/run-39056472835.json)
preserves the complete artifact digest, inner preparation and helper receipts,
actual Xlib events and the screenshot. All three completion signals passed:
native preparation, the Hermes helper, and the outer completed/exit-zero receipt.

The test installs the already-proven same-version candidate, copies its trimmed
`app/` tree into a private directory, and applies only this experimental patch.
The candidate's own managed Python executes the registered `computer_use`
handler against the external Bionic driver and real product Bot Desktop.
The complete installed payload and experimental source remained unchanged after
execution. All 12 changed source-file hashes match the host-validated reference
tree `d2cfed7c6e84682ce2c8656215226cff2778e1d2`; the trimmed installed app
is not claimed to equal the full-source Git tree.

Two concrete integration defects are repaired:

- Before a desktop exists, manifest discovery now launches the native driver with
  Termux's system libraries while preserving the managed Python parent's bundled
  loader environment. The actual pre-desktop driver contract passed.
- Scroll coordinates are forwarded when the live driver advertises either the
  existing coordinate capability or both schema properties `x` and `y`.
  The native driver advertises the two properties without the legacy capability.
  Its independently recorded wheel events now land at the requested `(80,60)`;
  the prior run delivered them at `(160,120)`.

The integration also proved a 320x240 two-color capture, the exact click, exactly
two scroll ticks, and the full text `hermes-native-input`. Each input received
one separate `once` approval; requests without an approver and reuse of a
consumed approval were refused. A real viewer lease blocked both input and
capture until hand-back. Product session release, the fixture and observed owned
child processes, the virtual desktop and the private workspace were cleaned up.

[Canonical loader tests](../audit/cua-hermes-resume-20261017/host-tests.json)
passed **73 tests with three macOS-only skips**.
[Scroll regression evidence](../audit/cua-hermes-resume-20261017/scroll-source-tests.json)
shows the new case failing before the fix and the final focused run passing
**31 tests**. These are separate runs and are not added together. The broader
computer-use file had the same **83 passes, three failures and one skip** before
and after the fix. Those three Windows fixture failures also reproduced before
the loader change: an extensionless shell fixture, an unescaped Windows path in
JSON, and a fixture that removes the home-directory environment. Their actual
failures remain in the record.

All eight [scoped lint checks](../audit/cua-hermes-resume-20261017/scoped-lint.json)
passed for the final integration diff, including pinned Ruff and the unmodified
code-health engine with zero blocking or advisory findings. This is scoped lint,
not a claim that the entire all-tree checker lane ran. The earlier
[58/14-test preparation evidence](../audit/cua-hermes-host-tests-20261017.json)
and [failed native runs](../audit/cua-hermes-resume-20261017/) remain historical
records.

This completed integration still requires an explicitly selected external driver
and foreground delivery. The driver and experimental adapter are **outside the
main package candidate and default PM admission**. Default background input,
AT-SPI trees, secure encrypted history and Android phone-app control retain the
limits described above. This result therefore does not increase the six
main-candidate repairs or change the nine-restriction baseline count.

## Microphone silence detection

The [final full component run](../audit/native-probes-635ec13-20261017/summary.json)
again fails at PortAudio initialization on implementation commit `635ec13`.
NumPy's four numerical checks pass in both runtime contexts, and the PortAudio
library loads. The observed container still lacks the actual Android audio
framework and Binder services; hardware capture remains untested. The overall
component workflow retains its audio failure, alongside six passing non-audio
lanes, and its complete failed-job log is saved.

Termux:API records a finalized audio file; it does not expose the live PCM stream
used by Hermes' sounddevice silence detector. The prepared capture selector
exposes the existing PCM backend explicitly and keeps Termux:API as an
independent choice. It does not substitute Android speech recognition for the
user's configured transcription provider.

[Official Termux PortAudio recipe](https://github.com/termux/termux-packages/blob/ae877f2c6a2b2318abeb43699d6ec5f619c216a6/packages/portaudio/build.sh).

That recipe uses an OpenSL ES backend and requires Android's real libOpenSLES.so.
It disables ALSA, JACK, OSS and PulseAudio backends. The native audio probe
therefore records two separate results: exact NumPy wheel/numerical behavior,
and actual PortAudio loading/device enumeration. A container missing Android's
audio framework must remain environment-limited, with no fabricated audio device
or library. The diagnostic run now verifies that specific boundary: native
NumPy passes with both library environments, the mapped OpenSL ES object is the
Termux libandroid-stub wrapper, and the real Android framework/Binder/audio
services are absent. PortAudio initialization remains failed and no microphone
capability is admitted from this container result. See the [captured audio
evidence](../audit/native-probes-9fcd31c-20261017/audio-summary.json) and the
[reviewed wrapper source](https://github.com/termux/termux-packages/blob/11ae750781a261b8df328697b12d66d75b72e5da/packages/libandroid-stub/libOpenSLES-wrapper.c).
Physical microphone permission, capture, VAD thresholds, maximum
duration, playback/audio focus and cancellation remain device gates.

A separate [audio-readiness repair](audio-readiness-device-validation.md) has
passing host contract tests for PortAudio initialization failures and output-only
device inventories; its [preparation record](../audit/audio-readiness-preparation-20261017.json)
retains the source and test evidence. It remains outside the main candidate.
The proven candidate does not select `audio-io`: a complete isolated Hermes
audio environment and its installation receipt must be prepared before physical
capture/VAD validation. These diagnostics do not supply the missing Android audio
framework or certify microphone access.

## Stable-release prerequisites

The compatibility preparation is saved independently from the released recipe.
The current same-version candidate passed the complete native package and
optional-install lifecycle gate; its [saved evidence](../audit/candidate-lifecycle-e271e92-20261017/summary.json)
records the exact tested inputs. A future stable release must keep that gate
passing for its final source and complete the Android device checks. This branch does not
publish a release or promote the candidate into the signed APT feed.
