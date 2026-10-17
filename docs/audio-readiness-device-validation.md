# Audio readiness and physical-device validation

Prepared on 2026-10-17. This is a separate robustness experiment; no microphone was accessed while preparing it.

## What is fixed, and what is still unproved

The standalone [audio-readiness patch](../patches/next-stable/audio-readiness.patch) turns an optional library's import-time native initialization failure into a readable diagnostic, retaining the original exception and message. It also rejects a populated PortAudio inventory that contains only output devices. Missing Python modules and a missing PortAudio shared library retain their existing diagnostics; empty or failed forwarded-audio inventories retain their existing handling. This patch does not provide an Android audio framework or establish microphone/VAD support.

The [native audio record](../audit/native-probes-9fcd31c-20261017/audio-summary.json) proves NumPy 2.4.3 arithmetic, FFT and internal LAPACK with both the build runtime and original package libraries. The same run failed PortAudio initialization with error -9999. Its mapped OpenSL ES object was the official libandroid-stub wrapper, and the container lacked the actual Android framework library and recorded Binder/audio services. The relationship to the engine error is an inference from those measured facts and the pinned wrapper source. Actual device initialization, microphone permission, capture, and silence stopping remain unproved.

The verified 635ec13 full candidate still selects seven extras and does not include `audio-io`. Changing `voice.capture_backend` alone does not supply NumPy or sounddevice. The experiment remains separate from the released package and main compatibility patch; no physical device installation has been performed.

## Device access observed on 2026-10-17

The [sanitized device-access record](../audit/device-audio-access-20261017.json), captured at 20:01 UTC, records Android **API level 36** and the **arm64-v8a** ABI on the attached physical device. These runtime identifiers are now known; no persistent device identifier was retained.

| Observation | Consequence for the follow-up |
|---|---|
| Package inventory lists `com.termux` and `com.termux.x11`; the package follow-up identifies Termux `0.118.0` (code 118, minimum SDK 21, target SDK 28). | Termux is present. The generic Android package installer record does not prove its distribution channel; the installed Hermes payload also still needs to be identified in the intended session. |
| The Termux package dump contains no `android.permission.RECORD_AUDIO` entry. | This does not establish the complete shared-UID permission or app-ops state. Check actual microphone permission in the intended app context before a take. |
| The same inventory does not list `com.termux.api`. | The Termux:API companion is unavailable in the observed package inventory. This affects the Termux:API path, not the separately staged sounddevice/PortAudio path. |
| `run-as com.termux id` fails with `package not debuggable`. | This ADB command cannot launch the probe as the installed Termux app. A foreground Termux session remains the documented execution context; app-context execution has not yet been established. |

This inventory does not prove microphone permission, PortAudio initialization, capture, or VAD. It establishes no isolated audio environment and does not change any audio gate. The local PCM/VAD test below does not require the Termux:API backend; that backend is a separate check and cannot prove silence autostop.

## Isolated software for the device test

The separate [bundle builder](../scripts/prepare_audio_device_bundle.py) and
[native recreation helper](../scripts/prepare_audio_device_environment.py) use
a [frozen input lock](../scripts/audio_device_bundle_lock.json). They prepare
the verified candidate from packaging source
`635ec13c9d0f264f508d1bdbaa7670d4eaa00787`, candidate run
[39057745675](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39057745675).
The selected package is 222,096,792 bytes with SHA-256
`2d5435d0fb19fa9f8ed0a5da5c66cabf59585a8e8bcd35ad2ebf9cb161f5e810`.

**Native recreation verification: pending.** The
[isolated audio workflow](../.github/workflows/audio-device-staging.yml) builds
the transfer bundle, recreates it at two distinct final paths with networking
disabled, and records assembly separately from audio initialization. No physical
installation or microphone check has been performed.

The transfer directory contains `payload.tar.gz`, `manifest.json`,
`prepare.sh` and `BUNDLE-RECEIPT.json`. It includes the candidate's tools,
runtime libraries, application source and complete wheel catalog; the two
production audio-readiness changes; the frozen audio additions; and the
recreation and validation helpers. Its input manifest records every retained
payload member and the exact before/after hashes of
`tools/voice_mode.py` and `tools/voice_mode_capture.py`.

The installer creates fresh private PM and application environments at the
chosen final path. It preserves the candidate's 100 installed distribution
versions and adds NumPy 2.4.3 and sounddevice 0.5.5, for 102 application
distributions. The 102-wheel transfer catalog includes the unused build-support
setuptools wheel; the application inventory comprises 101 dependency wheels
and the source-layout Hermes metadata. No existing venv or PM environment is
copied into the transfer bundle.

| New runtime wheel | Bytes | SHA-256 |
|---|---:|---|
| `numpy-2.4.3-cp314-cp314-android_24_arm64_v8a.whl` | 7180471 | `4b1840a7d73d6111604b22102e58b551a670db579164e0ddede3e78733fd68d4` |
| `sounddevice-0.5.5-py3-none-any.whl` | 32807 | `30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f` |

Those two wheels come from the original audio component
[run 39043935925](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39043935925),
artifact `12104898993`. That workflow remains a recorded audio failure.
Its [build receipt](../audit/native-probes-9fcd31c-20261017/audio-build-probe.json)
also contains a different CFFI build with the same filename/version. The new
bundle deliberately retains the candidate's CFFI SHA-256
`196cd52f8b5ac753e947e1267381ddf9616a41033f310a05993b96c6262b52e1`;
it does not replace it with the historical audio CFFI
`36977e26001a7f4da546fda9fd8715ff6e81e6661d02eb28bc5f2ee0f235f9b2`.
The duplicate pycparser and setuptools inputs also leave the original catalog
bytes unchanged.

The additional library is official Termux `portaudio` version `19.07.00-3`:
`libportaudio.so.2`, 61,976 bytes, SHA-256
`116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073`.
The isolated libraries also include the pinned official OpenSL ES forwarding
wrapper. It forwards to the platform's `/system/lib64/libOpenSLES.so`; it
does not supply a real Android audio framework itself. A physical success must
record the actual mapped framework library and usable input device. The
container's unavailable audio diagnostic cannot substitute for those observations.

The fresh application environment also receives an owned `sitecustomize.py`.
The pinned Python's generic PortAudio finder relies on a linker or compiler and
does not directly search `LD_LIBRARY_PATH`. This small adapter maps only the
exact library name `portaudio` to the private, size- and SHA-verified
`libportaudio.so.2`; all other lookups use Python's original finder. Its bytes
and activation are verified in the generated environment receipt. It leaves the
original sounddevice wheel unchanged and retains real native loading and
PortAudio initialization.

The installer rejects existing or noncanonical destinations, overlap with the
installed Hermes payload, changed bundle bytes and inherited Python platform
overrides. It uses the included pinned Python rather than requiring a user
Python installation. Each resulting `bin/audio-python` launcher is bound to
its absolute destination and receipt. Recreate at a new destination when needed;
moving a prepared environment does not satisfy the receipt. The launcher fixes
`HERMES_HOME` to `<destination>/state/profile`, places caches and temporary
files under `state`, removes ambient Python/native-library overrides, and
uses the isolated payload's library paths. The user's real `HOME` is retained.

## Device facts: no recording

For the later device session, use a native foreground Termux session. The following commands only report the selected runtime facts and current recorder status; `-i` does not start recording. The API level and ABI can be compared with the dated inventory above. Run the last two Termux:API-specific commands only when that backend is being checked and its matching companion app and CLI helper are available; otherwise retain the observed absence and continue only with the separately prepared sounddevice path.

```bash
# Run in the foreground Termux app, not in proot, Docker, or an SSH shell.
/system/bin/getprop ro.product.model
/system/bin/getprop ro.build.version.release
/system/bin/getprop ro.build.version.sdk
uname -m
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' hermes-agent termux-api portaudio libandroid-stub
command -v termux-microphone-record
timeout 10s termux-microphone-record -i
```

Also report the Termux app version and installation channel (F-Droid, official GitHub, or another channel), the Termux:API add-on's version/channel if installed, and whether Android microphone permission is granted. Termux and its add-ons must use compatible signatures; do not uninstall an existing app to answer this question. The [official Termux:API README](https://github.com/termux/termux-api/blob/master/README.md) documents this requirement. No API key, full environment dump, account details, or recording needs to be shared.

## Recreate the environment in foreground Termux

Use the complete transfer artifact from the isolated audio workflow and verify
its published artifact digest before using the extracted directory. The
installer verifies its embedded manifest and payload hashes. Choose a fresh
directory under the Termux app's private home; its parent must already exist.
The existing installed Hermes payload is not an input to this launcher.

```bash
# Run in foreground Termux after selecting the reviewed transfer directory.
: "${AUDIO_BUNDLE:?Set the extracted reviewed audio bundle directory}"
AUDIO_ROOT="$HOME/hermes-audio-validation-20261017"
bash "$AUDIO_BUNDLE/prepare.sh" "$AUDIO_ROOT"
AUDIO_PY="$AUDIO_ROOT/bin/audio-python"
AUDIO_SOURCE="$AUDIO_ROOT/app"
test -x "$AUDIO_PY" && test -f "$AUDIO_SOURCE/tools/voice_mode.py"
AUDIO_EVIDENCE="$(mktemp -d "$AUDIO_ROOT/state/device-check.XXXXXX")"
chmod 700 "$AUDIO_EVIDENCE"
cd "$AUDIO_SOURCE"
```

The resulting `staging/assembly-receipt.json` binds the candidate identity,
complete installed inventory, source manifest and environment receipt.
`staging/environment-manifest.json` records the generated PM/application
files and links. The launcher verifies those bindings before each command.
Mutable profile/cache files remain inside this experiment.

## Non-recording native initialization and input inventory

Use the delivered launcher and bundled helper. No separate packaging checkout,
manual `LD_LIBRARY_PATH` change, global PortAudio installation or CI venv is
needed for these commands.

```bash
"$AUDIO_PY" "$AUDIO_ROOT/staging/prepare_audio_device_environment.py" \
  validate --root "$AUDIO_ROOT"
"$AUDIO_PY" "$AUDIO_ROOT/staging/prepare_audio_device_environment.py" \
  diagnose --root "$AUDIO_ROOT"
cat "$AUDIO_ROOT/staging/audio-diagnostic.json"
```

The diagnostic opens no input stream and records no audio. It imports the
patched audio module, initializes PortAudio, and reports the actual library and
input inventory when initialization succeeds. A zero command exit means the
diagnostic protocol completed; it does not prove device readiness. The
receipt's `readiness` and `device_readiness` remain false because recording
and VAD have not been checked.

Before the owner starts a take, require `status=audio-initialized`,
`input_device_status=available`, and
`framework_input.real_android_framework_mapped=true`. Review the recorded
default input and `supported_input_formats`, including the supported sample
rate. These observations are prerequisites for the take; they do not by
themselves prove microphone capture or VAD.

A known PortAudio -9999 initialization failure is retained as
`audio-unavailable` with `input_device_status=initialization-unavailable`;
unexpected errors fail the command. The other input statuses are `unavailable`
(no usable default input), `unsupported` (known format, channel or rate
rejections), and `available` (format support). Missing or output-only devices
do not pass the input gate. Android process visibility restrictions can limit
observations; an unreadable process inventory does not establish that the
framework is absent.

## User-initiated local PCM/VAD check

Only the device owner should initiate this block after agreeing to a brief microphone test in a quiet private setting. It uses the real recorder factory and callback path, limits the take to ten seconds, disables streaming and all transcription, prints only numeric observations, and deletes its own temporary WAV. The launcher always uses `$AUDIO_ROOT/state/profile`; the block writes that experiment-only configuration instead of supplying an ignored `HERMES_HOME` override. It does not run a model or send the take to an STT provider. The outer timeout is an additional cleanup bound; `shutdown()` releases the persistent input stream.

```bash
# This block is for a later user-initiated microphone test.
# It configures only this isolated bundle's profile and never calls transcription.
test -d "$AUDIO_ROOT/state/profile"
cat > "$AUDIO_ROOT/state/profile/config.yaml" <<'YAML'
security:
  allow_lazy_installs: false
stt:
  enabled: false
  provider: none
  streaming: false
voice:
  capture_backend: sounddevice
  auto_tts: false
YAML
timeout --signal=INT --kill-after=3s 20s "$AUDIO_PY" - <<'PY'
import json
import threading
import time
import wave
from pathlib import Path

import pm
from tools import transcription_tools
from tools.voice_mode import AudioRecorder, create_audio_recorder

assert pm.available("audio-io"), "Stop: the reviewed optional audio environment is not ready"
stt = transcription_tools._load_stt_config()
assert stt.get("provider") == "none" and not stt.get("streaming", False)
recorder = create_audio_recorder()
assert isinstance(recorder, AudioRecorder)
recorder._silence_threshold = 200
recorder._silence_duration = 3.0
recorder._max_recording_seconds = 10.0
ended = threading.Event()
recording = None
try:
    recorder.start(on_silence_stop=ended.set)
    print("Microphone active: say a short non-private phrase, then stay quiet.", flush=True)
    if not ended.wait(12):
        raise RuntimeError("No bounded stop callback; the capture test failed")
    stopped_after = time.monotonic() - recorder._start_time
    speech_detected = recorder._has_spoken
    peak_rms = recorder._peak_rms
    recording = recorder.stop()
    if recording is None:
        raise RuntimeError("No usable speech recording; do not mark VAD as passed")
    with wave.open(recording, "rb") as audio:
        result = {
            "channels": audio.getnchannels(),
            "sample_width_bytes": audio.getsampwidth(),
            "sample_rate": audio.getframerate(),
            "audio_seconds": audio.getnframes() / audio.getframerate(),
            "callback_after_seconds": stopped_after,
            "speech_detected": speech_detected,
            "peak_rms": peak_rms,
            "stopped_before_duration_cap": stopped_after < 9.5,
            "transcription_called": False,
        }
    assert result["channels"] == 1 and result["sample_width_bytes"] == 2
    print(json.dumps(result, indent=2))
finally:
    recorder.shutdown()
    if recording:
        Path(recording).unlink(missing_ok=True)
PY
```

For a successful silence-stop observation, speak for about one or two seconds, then remain quiet for about three seconds. Require real speech detection, nontrivial recorded PCM, and stopping before the ten-second cap; reaching the cap does not prove VAD. Repeat as a new explicit take to check reopen/cleanup, then check a manual stop in the normal product UI if that UI is part of the intended release. On denial of microphone permission, expect a clean unavailable/error result; grant permission only deliberately and retry. Verify the Android microphone indicator clears after shutdown. Background capture, Bluetooth/headset routing, wake words, streaming STT and full duplex are separate unproved scopes.

## Termux:API and the normal Hermes UI

`voice.capture_backend` accepts `auto`, `termux-api`, or `sounddevice`. `auto` prefers the available Termux:API backend. Termux:API records encoded audio and supports manual stopping and a duration cap; it intentionally reports `supports_silence_autostop=False`, so it cannot establish the PCM/VAD claim.

If a user separately wants to verify the normal CLI with their existing chosen STT provider, record the current configuration first, then set `voice.capture_backend` to the intended backend, `voice.max_recording_seconds` to `10`, `voice.silence_duration` to `3`, `voice.submit_mode` to `draft`, `voice.auto_tts` to `false`, and `stt.streaming` to `false` through `hermes config set <key> <value>`. Start `hermes`, use `/voice status`, then `/voice on`; only pressing the displayed record shortcut (default Ctrl+B) starts a take. `/voice off` releases the recorder. The CLI transcribes after stop even in draft mode, so this UI check may send audio to the user's configured provider and requires their separate choice. It is not required for the local-only PCM/VAD test above.

## Host preparation proof

The separate [preparation record](../audit/audio-readiness-preparation-20261017.json) binds the patch, source trees, canonical commands and exact raw stdout/stderr bytes (base64 plus SHA-256). Baseline: upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`, four released patches, and main compatibility patch `77ac41bc11a6facd928f4cef577642b9eeb042ce3da7d820478aa49e1d98fa1e`; staged tree `f49c77b666cef7fd5235cdd786556908527b532e`. Audio patch SHA-256: `82b92d5095ceabc05f0200569da1cc16b861c77b166095982b05d57940573db7`; replay tree `aa90e9a6eca74835dacc2dc55f376bddfd499c25`.

The unchanged baseline produced three failures and one passing control. On the fixed source, the new file passed four cases, the existing selector suite passed fourteen cases (three Linux-only WSL cases were skipped on Windows), and two selected existing missing-library cases passed. These are separate runs; the red and green runs overlap and are not added together. One expanded attempt hit a 65-second outer timeout before a summary was retained, and no test result is claimed for that attempt. No native microphone or device installation was performed.

## Remaining device work

The available device meets the dated ARM64/API identity observation. The
software preparation is tracked by the isolated audio workflow above; native
recreation verification is still pending in this draft.

1. **Establish foreground Termux execution.** Use the owner-operated app
   session and the reviewed bundle. The failed ADB `run-as` route does not
   provide that context. Confirm the app's distribution channel, installed
   Hermes identity and existing microphone-permission state. Determine compatible
   Termux:API companion/helper versions only for that separate backend.
2. **Recreate and check the isolated environment.** Use a fresh private
   destination and its generated launcher. Inspect the complete assembly receipt,
   then require successful initialization, a usable input device and real
   mapped framework provenance.
3. **Let the device owner initiate the bounded local PCM/VAD check.**
   Use the local-only block above for speech followed by silence, distinguish
   silence stopping from the duration cap, and repeat to check reopen/cleanup.
   Retain numeric results and the shutdown observation; delete the temporary
   WAV as the block specifies.

Playback/audio focus, physical clipboard behavior and the normal Hermes UI
remain separate checks. None is established by a successful local PCM/VAD result.
