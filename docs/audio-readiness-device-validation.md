# Audio readiness and physical-device validation

Prepared on 2026-10-17. This is a separate robustness experiment; no microphone was accessed while preparing it.

## What is fixed, and what is still unproved

The standalone [audio-readiness patch](../patches/next-stable/audio-readiness.patch) turns an optional library's import-time native initialization failure into a readable diagnostic, retaining the original exception and message. It also rejects a populated PortAudio inventory that contains only output devices. Missing Python modules and a missing PortAudio shared library retain their existing diagnostics; empty or failed forwarded-audio inventories retain their existing handling. This patch does not provide an Android audio framework or establish microphone/VAD support.

The [native audio record](../audit/native-probes-9fcd31c-20261017/audio-summary.json) proves NumPy 2.4.3 arithmetic, FFT and internal LAPACK with both the build runtime and original package libraries. The same run failed PortAudio initialization with error -9999. Its mapped OpenSL ES object was the official libandroid-stub wrapper, and the container lacked the actual Android framework library and recorded Binder/audio services. The relationship to the engine error is an inference from those measured facts and the pinned wrapper source. Actual device initialization, microphone permission, capture, and silence stopping remain unproved.

The successful e271 full candidate still selects seven extras and does not include `audio-io`. Changing `voice.capture_backend` alone does not supply NumPy or sounddevice. This guide does not authorize or perform an installation, add an extra to the released package, or change the main compatibility patch.

## Device access observed on 2026-10-17

The [sanitized device-access record](../audit/device-audio-access-20261017.json), captured at 20:01 UTC, records Android **API level 36** and the **arm64-v8a** ABI on the attached physical device. These runtime identifiers are now known; no persistent device identifier was retained.

| Observation | Consequence for the follow-up |
|---|---|
| Package inventory lists `com.termux` and `com.termux.x11`; the package follow-up identifies Termux `0.118.0` (code 118, minimum SDK 21, target SDK 28). | Termux is present. The generic Android package installer record does not prove its distribution channel; the installed Hermes payload also still needs to be identified in the intended session. |
| The Termux package dump contains no `android.permission.RECORD_AUDIO` entry. | This does not establish the complete shared-UID permission or app-ops state. Check actual microphone permission in the intended app context before a take. |
| The same inventory does not list `com.termux.api`. | The Termux:API companion is unavailable in the observed package inventory. This affects the Termux:API path, not the separately staged sounddevice/PortAudio path. |
| `run-as com.termux id` fails with `package not debuggable`. | This ADB command cannot launch the probe as the installed Termux app. A foreground Termux session remains the documented execution context; app-context execution has not yet been established. |

This inventory does not prove microphone permission, PortAudio initialization, capture, or VAD. It establishes no isolated audio environment and does not change any audio gate. The local PCM/VAD test below does not require the Termux:API backend; that backend is a separate check and cannot prove silence autostop.

## Exact software prerequisites before a phone test

A packager must first supply a separately reviewed, freshly assembled PM environment for native Android ARM64/Python 3.14, plus a copy of the prepared Hermes source with this patch applied. Keep the installed package and its environment unchanged. Reuse the exact candidate's reviewed base runtime and wheel catalog, then add the locked audio closure in the isolated environment; do not copy the CI venv to the phone or substitute system Python packages. This full device-test environment and its installer/receipt have not yet been prepared or certified.

The launcher below resolves `AUDIO_PAYLOAD` to the existing `$PREFIX/lib/hermes-agent` directory. Its receipt must bind that payload to the selected candidate's source, package digest and runtime-library hashes, as well as the new environment's complete wheel manifest and patched source. If the existing payload does not match, prepare a separately reviewed launcher pointing to an isolated copy of the selected payload before using these blocks. An unrelated installed payload is not a substitute for this prerequisite.

The existing component proof is [run 39043935925](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39043935925), artifact `12104898993`; the [build receipt](../audit/native-probes-9fcd31c-20261017/audio-build-probe.json) records these exact files. The runtime closure has four packages; the fifth retained wheel is build support.

| Artifact | Bytes | SHA-256 | Role |
|---|---:|---|---|
| `cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl` | 201386 | `36977e26001a7f4da546fda9fd8715ff6e81e6661d02eb28bc5f2ee0f235f9b2` | Runtime |
| `numpy-2.4.3-cp314-cp314-android_24_arm64_v8a.whl` | 7180471 | `4b1840a7d73d6111604b22102e58b551a670db579164e0ddede3e78733fd68d4` | Runtime, built with internal BLAS/LAPACK fallback |
| `pycparser-3.0-py3-none-any.whl` | 48172 | `b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992` | Runtime |
| `sounddevice-0.5.5-py3-none-any.whl` | 32807 | `30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f` | Runtime |
| `setuptools-83.0.0-py3-none-any.whl` | 1008090 | `29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3` | Retained build support |

The recorded additional runtime library is official Termux `portaudio` version `19.07.00-3`: `libportaudio.so.2`, 61976 bytes, SHA-256 `116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073`; its SONAME aliases contain the same bytes. It needs `libc.so`, `libm.so`, and `libOpenSLES.so`. The phone must provide the real working Android audio framework, not merely an importable wrapper. The probe records the actual mapped paths, owners and hashes, including the system OpenSL ES object if the wrapper loads it. Do not install a fabricated replacement or relax the initialization check.

The historical component environment was `/out/environment/bin/python`, created through `pm.build_requirements_environment(..., wheelhouse=..., offline=True)`. That was a dependency-only environment, not the full Hermes application. For the full recorder test below, the packager must provide all frozen Hermes runtime dependencies as well, and bind the new environment's Python, complete wheel manifest, source and locks in a receipt. `AUDIO_ENV` below names this new environment; `AUDIO_SOURCE` names its separate patched source; `PROBE_SOURCE` names the reviewed packaging checkout. These task-local shell variables are not new Hermes configuration options.

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

## Non-recording native initialization and input inventory

After the separately reviewed environment is delivered and its receipt verified, use its exact interpreter with the original payload libraries and the declared official PortAudio package. This preserves the tested executable layout; it does not put a compiler's replacement libc++ ahead of the package runtime.

```bash
# These paths are supplied with the separately reviewed device-test environment.
: "${AUDIO_SOURCE:?Set the reviewed Hermes source path}"
: "${AUDIO_ENV:?Set the reviewed isolated audio environment path}"
: "${PROBE_SOURCE:?Set the reviewed packaging checkout path}"
AUDIO_PAYLOAD="$PREFIX/lib/hermes-agent"
AUDIO_PY="$AUDIO_ENV/bin/python"
test -x "$AUDIO_PY" && test -f "$AUDIO_SOURCE/tools/voice_mode.py"
export LD_LIBRARY_PATH="$AUDIO_PAYLOAD/tools/python$PREFIX/lib:$AUDIO_PAYLOAD/tools/node$PREFIX/lib:$AUDIO_PAYLOAD/tools/ffmpeg$PREFIX/lib:$AUDIO_PAYLOAD/runtime-libs/lib:$PREFIX/lib"
AUDIO_EVIDENCE="$(mktemp -d "$TMPDIR/hermes-audio-device.XXXXXX")"
chmod 700 "$AUDIO_EVIDENCE"
cd "$AUDIO_SOURCE"
"$AUDIO_PY" -c 'import sys, platform, importlib.metadata as m; assert sys.platform == "android"; assert platform.machine() in ("aarch64", "arm64"); assert sys.version_info[:2] == (3, 14); assert m.version("numpy") == "2.4.3"; assert m.version("sounddevice") == "0.5.5"; print(sys.executable, sys.version)'
```

Run the existing dependency/inventory probe:

```bash
"$AUDIO_PY" "$PROBE_SOURCE/scripts/probe_native_compatibility.py" \
  exercise --group audio --out "$AUDIO_EVIDENCE/AUDIO-DEVICE.json"
```

This opens no input stream and records no audio. It imports sounddevice (which initializes PortAudio), enumerates devices, and saves `AUDIO-DEVICE.json`, `NUMPY-AUDIO-DEVICE.json`, and `AUDIO-HOST-AUDIO-DEVICE.json`. A successful exit alone is insufficient: require `audio.input_device_status` to be `available`, inspect the default input and supported sample rate, and verify the real mapped audio-library provenance. Initialization errors remain failures. Android process visibility restrictions can limit service observations; an unreadable process inventory does not prove that the framework is absent.

## User-initiated local PCM/VAD check

Only the device owner should initiate this block after agreeing to a brief microphone test in a quiet private setting. It uses the real recorder factory and callback path, limits the take to ten seconds, disables streaming and all transcription, prints only numeric observations, and deletes its own temporary WAV. It does not run a model or send the take to an STT provider. The outer timeout is an additional cleanup bound; `shutdown()` releases the persistent input stream.

```bash
# This block is for a later user-initiated microphone test.
# It creates a temporary validation profile and never calls transcription.
mkdir "$AUDIO_EVIDENCE/profile"
cat > "$AUDIO_EVIDENCE/profile/config.yaml" <<'YAML'
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
HERMES_HOME="$AUDIO_EVIDENCE/profile" timeout --signal=INT --kill-after=3s 20s "$AUDIO_PY" - <<'PY'
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

## Remaining preparation for the device test

The available device already meets the observed ARM64/API identity part of the plan. The concrete follow-up is:

1. **Prepare the exact isolated software.** Deliver the full audio environment, patched source, selected candidate payload, launcher and digest receipt described above. This staging remains unfinished; the dependency-only CI environment is insufficient for the Hermes recorder check.
2. **Establish execution inside foreground Termux.** Use an owner-operated Termux session and the delivered launcher. Record the app version/channel, human-readable device model and Android release, installed Hermes payload identity, and existing microphone-permission state. The failed `run-as` route does not provide this entry point. Determine compatible Termux:API companion/helper versions only if that separate backend will be tested.
3. **Run the non-recording readiness gate.** Verify the receipt and exact interpreter, then require successful native initialization, a real input device and mapped audio-library provenance. Retain the numeric and provenance reports; an unavailable or output-only inventory remains a failed gate.
4. **Let the device owner initiate the bounded local PCM/VAD check.** After the readiness gate passes, use the local-only block above for speech followed by silence, distinguish silence stopping from the duration cap, and repeat to check reopen/cleanup. Retain the numeric result and shutdown observation; delete the temporary WAV as the block specifies.

Playback/audio focus, physical clipboard behavior and the normal Hermes UI remain separate checks. None is established by a successful local PCM/VAD result. The packager must finish software staging before requesting any brief microphone take from the device owner.
