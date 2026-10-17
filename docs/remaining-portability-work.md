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

The bounded next step is to choose and certify one runtime arrangement:

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
device permissions. A potential native X11 driver build should be evaluated
against the virtual desktop on its own terms.

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
remain unchanged. Source preparation, the adapted platform backend compilation,
and an owned-PTY check against Android's installed ioctl header have passed.
The driver now compiles and links natively. The Android shared-memory adapter
uses the existing kernel syscall where Bionic does not export the libc wrapper;
native descriptor, shared-mapping, keymap and error-path checks passed. The first
linked run stopped before Xfwm4 startup because the private test bus rejected
method replies and signals. A narrow correction restores the standard D-Bus
session receive policy and adds a real request/reply gate. That correction
passed: the native driver now starts, registers 60 MCP tools and captures the
exact 320x240 client window with independently checked colors. The default
background click returned an unverifiable effect and produced no fixture event.
The next probe explicitly requests the documented foreground XTest route; no
background-input certification is claimed.
[Native progress records](../audit/cua-native-20261017/) preserve the exact tested
inputs, real failure messages and completed PTY proof.

The experiment checks a private, owned Xvnc desktop using real MCP operations
and independent fixture observations. Its scope includes screenshot capture,
keyboard and mouse events, scrolling, clipboard transfer, window geometry, and
cleanup. It remains separate from Hermes PM admission and the complete package
candidate. Encrypted history still requires a supported secure credential store;
its existing failure behavior is preserved. TigerVNC does not provide the
parallel uinput devices expected by CUA's multiple-pointer implementation.
Android phone application control still requires an Android-specific backend.

A [separate Hermes integration patch](../patches/next-stable/cua-hermes-integration.patch)
allows an explicitly selected native Termux X11 executable. It leaves the full
runtime manifest check, action approval gate and viewer lease in place. The
[native integration helper](../scripts/compatibility_probe_cua_hermes.py) uses the
real registered tool and product Bot Desktop, with exact fixture image/input
observations, three one-action foreground approvals, refusal without an approver,
viewer takeover/hand-back, and owned cleanup. Its [candidate fetcher](../scripts/fetch_compatibility_candidate.py)
verifies the already-proven package and source identities before the test. These
files are prepared and reviewed; native Hermes integration is still pending and
the experimental patch is not included in the full main candidate.

## Microphone silence detection

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

## Stable-release prerequisites

The compatibility preparation is saved independently from the released recipe.
The current same-version candidate passed the complete native package and
optional-install lifecycle gate; its [saved evidence](../audit/candidate-lifecycle-e271e92-20261017/summary.json)
records the exact tested inputs. A future stable release must keep that gate
passing for its final source and complete the Android device checks. This branch does not
publish a release or promote the candidate into the signed APT feed.
