# Native Termux audio preparation inputs

This is an offline reconstruction input bundle for an unpublished experiment.
It contains the exact main candidate, original 100-wheel catalog, two added
audio wheels, pinned official PortAudio/OpenSL ES inputs, the reviewed source
patches, and canonical PM/launcher preparation code. The original sounddevice
wheel is retained as an input; preparation applies the exact Android library
discovery patch and records the derived wheel with its original provenance.

On AArch64 Termux at the standard com.termux prefix, unpack this bundle in a
private app directory. Choose a NEW final output path; existing paths are
refused. From this bundle directory run:

    bash scripts/run_audio_hermes_preparation.sh --native       candidate audio-inputs patches/next-stable/audio-readiness.patch       "$HOME/hermes-audio-next-stable-20261017" prepare-and-probe

The command extracts the candidate into owned directories and creates fresh
canonical PM/application environments directly at the intended final path.
It never installs the .deb or replaces the installed Hermes environment.
Do not move the finished environment or copy a CI venv to the phone; repeat
preparation from these inputs at a new desired path.

The output run-hermes launcher owns its separate profile and cache.
The probe imports native dependencies and may enumerate device metadata.
It does not open or start a stream, record, play, or upload audio.
Android's real OpenSL ES framework/audio services and the appropriate
microphone permission are required for a later user-started capture/VAD
test. No successful VAD result is claimed by preparation or enumeration.

Both dependency preparation and PortAudio initialization have separate
receipts. Docker may pass complete dependency/integrity checks while
PortAudio reports the previously observed absent-framework error.

The immutable release, package version and main-branch installer pins are
unchanged. This bundle is not a new published release.
