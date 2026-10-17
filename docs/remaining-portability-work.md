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

Primary sources:

- [Exact PyPI release metadata](https://pypi.org/pypi/neutts/1.4.1/json).
- [Public source at the reviewed version declaration](https://github.com/neuphonic/neutts/blob/b7a3427d0d25e20e8b9e92cbaae688f732916baf/pyproject.toml).
- [Official Termux PyTorch recipe](https://github.com/termux/termux-packages/blob/master/packages/python-torch/build.sh).
- [Official Termux Torchaudio recipe](https://github.com/termux/termux-packages/blob/master/packages/python-torchaudio/build.sh).
- [Official Termux SciPy recipe](https://github.com/termux/termux-packages/blob/master/packages/python-scipy/build.sh).

Official Termux already builds native PyTorch and Torchaudio. Their existence is
evidence that Android ML support is feasible; it does not make their current
versions interchangeable with Hermes' frozen Python dependency graph. The
recipes inspected on 17 October 2026 declare PyTorch 2.14.1, Torchaudio 2.11.0
and SciPy 1.18.1. Hermes' current lock contains PyTorch 2.14.0, while the NeuTTS
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

## Microphone silence detection

Termux:API records a finalized audio file; it does not expose the live PCM stream
used by Hermes' sounddevice silence detector. The prepared capture selector
exposes the existing PCM backend explicitly and keeps Termux:API as an
independent choice. It does not substitute Android speech recognition for the
user's configured transcription provider.

[Official Termux PortAudio recipe](https://github.com/termux/termux-packages/blob/master/packages/portaudio/build.sh).

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
A future stable release needs the complete candidate package lifecycle gate plus
device checks for the Android permission-dependent paths. This branch does not
publish a release or promote the candidate into the signed APT feed.
