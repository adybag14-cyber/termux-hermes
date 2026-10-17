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
| The same inventory does not list `com.termux.api`. | The Termux:API companion is unavailable in the observed package inventory. The separate sounddevice/PortAudio path still requires verification of microphone permission and app-ops in the actual Termux app context. |
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

**Native recreation verification: passed; audio initialization remains unavailable.**
The [verified native staging record](../audit/audio-device-staging-20261017/run-39076074868/summary.json) binds
[run 39076074868](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076074868) and source
`09a945cff9e07243fb24e99d9a58a12d500eb18d`. The
[isolated audio workflow](../.github/workflows/audio-device-staging.yml) recreated
the bundle twice in the pinned ARM64/Bionic container under UID 1000 with
networking disabled. Both roots passed CLI startup, diagnostic handling and full
immutable validation afterward. No physical installation or microphone check
was performed.

The actual final destinations were
`/data/data/com.termux/files/usr/tmp/hermes-audio-validation-a` and
`/data/data/com.termux/files/usr/tmp/hermes audio validation b`; the second
exercise includes spaces in its final path.

| Measured check | First destination | Second destination |
|---|---|---|
| Assembly and explicit validation exit codes | `[0, 0, 0]` | `[0, 0, 0]` |
| Installed distributions / installed wheel checks / active dependency edges / PM distributions | 102 / 101 / 167 / 4 | 102 / 101 / 167 / 4 |
| Generated environment entries | 8,289 | 8,289 |
| CFFI sum; NumPy matrix/linalg behavior | 16; passed | 16; passed |
| CLI help exit; stdout bytes; stderr bytes | 0; 14,064; 0 | 0; 14,063; 0 |
| Diagnostic exit and protocol | 0; valid | 0; valid |
| Validation after diagnostics | Passed | Passed |

Both diagnostics report `audio-unavailable` and retain the original
`PortAudioError` code `-9999`. The actual private OpenSSL legacy provider loads,
and the mapped PortAudio, OpenSLES wrapper and namespace helper match their
frozen private copies. No undeclared ambient library mapping is admitted. A real
Android audio framework was not mapped, and no device stream was opened.
Readiness, microphone, recording and VAD flags remain false.

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

The same frozen `libandroid-stub 30-2` archive also supplies
`libtermux-platform-ns.so`, retained at
`runtime-libs/lib/libtermux-platform-ns.so`. The original OpenSLES wrapper names
this library as a bare ELF dependency; the native origin gate requires the
private copy. The helper exports `platform_dlopen` and needs only platform
`libc.so` and `libdl.so`. The [namespace input record](../audit/audio-device-staging-20261017/namespace-private-inputs-828e5d5e/summary.json)
binds both original members and confirms that adding the helper leaves the
wrapper, launcher routing, wheel catalog and mapped-library guard unchanged.
It does not add an Android framework implementation.

The [private OpenSSL input record](../audit/audio-device-staging-20261017/openssl-private-inputs-bd72d882/summary.json)
binds the original `1:3.6.5` archive's legacy provider and configuration to the
candidate's byte-identical `libcrypto.so.3` and `libssl.so.3`. Only the missing
provider/config inputs are added; the existing crypto libraries and the original
configuration bytes are preserved. Bootstrap and launcher code set
`OPENSSL_MODULES`, `OPENSSL_CONF` and `OPENSSL_CONF_INCLUDE` to the private
payload before Python starts and clear inherited engine/provider-disable
overrides. Native validation retains the mapped-library origin checks and
requires the actual legacy provider to be loaded. The archive is bound to the
frozen official input pin; this preparation does not claim a fresh APT signature
verification. Android/Bionic platform libraries remain external runtime inputs.

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

Use the complete **`hermes-isolated-audio-device-bundle`** artifact from
[run 39076074868](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076074868), artifact ID **12117830095**.
The verified ZIP is **319,506,282 bytes**, with SHA-256
`70eb95bac98f42cee655f7917b936eee185ed83483a972c4dbe7f5ba096a077e`.
Compare the complete downloaded ZIP's digest before extracting it. The verified
API receipt records expiry at `2026-10-31T22:51:07Z`; retain the verified archive
for the later device session before that date.

These are the four original native transfer files, distinct from local
preparation checkpoints:

| File | Bytes | SHA-256 |
|---|---:|---|
| `BUNDLE-RECEIPT.json` | 1,793 | `25600ea59dd332e14fc8367e05fd2053bfbf98d56dee48d172908a6f67fae8a6` |
| `manifest.json` | 5,643,711 | `a86e362fc62df905d3b2e77fca28dc28b5b8d23f4129aaa694552749b0596e15` |
| `payload.tar.gz` | 313,857,884 | `5606b977350eda8bf8d5586ed2ffe9f91212bc04f53112de35dcecaba8688d48` |
| `prepare.sh` | 2,392 | `b1f4f29ae7c2affeb64f7005753d5ab3c000676251324b4e3243e84d9e9cba36` |

The separate evidence artifact is ID **12116859683**, 4,557,184 bytes, SHA-256
`27ae65ccb029d62f34f2c7bdfb23d9d301166c9de7c141d8e581862a4bbd91f8`.
Its `AUDIO-STAGING-RESULT.json` is 27,038 bytes, SHA-256
`15f3b456789efd3d4c6302b373c6fcba2b08226f63a0e2c7e0ef6b7effb92634`.
Both entire ZIPs and every member were verified by digest and CRC. The
[successful staging record](../audit/audio-device-staging-20261017/run-39076074868/summary.json) links the original receipts and
source/manifest comparisons. The native manifest retains 25,275 entries and 102
wheels; the candidate identity, catalog and audio patch outputs remain unchanged.
`BUNDLE-RECEIPT.json` retains its preparation-time native/device booleans; the
later native result supplies the completed recreation proof.

The installer verifies its embedded manifest and payload hashes. Choose a fresh
directory under the Termux app's private home; its parent must already exist.
The existing installed Hermes payload is not an input to this launcher.

```bash
# Run in foreground Termux after selecting the reviewed transfer directory.
: "${AUDIO_BUNDLE:?Set the extracted reviewed audio bundle directory}"
AUDIO_ROOT="$(realpath -- "$HOME")/hermes-audio-validation-20261017"
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

If the owner separately chooses to verify the isolated CLI with an STT provider, record the configuration in `$AUDIO_ROOT/state/profile` first and configure the chosen provider in that isolated profile. Set `voice.capture_backend` to the intended backend, `voice.max_recording_seconds` to `10`, `voice.silence_duration` to `3`, `voice.submit_mode` to `draft`, `voice.auto_tts` to `false`, and `stt.streaming` to `false` through `"$AUDIO_PY" -m hermes_cli.main config set <key> <value>`. Start `"$AUDIO_PY" -m hermes_cli.main`, use `/voice status`, then `/voice on`; only pressing the displayed record shortcut (default Ctrl+B) starts a take. `/voice off` releases the recorder. The CLI transcribes after stop even in draft mode, so this UI check may send audio to the configured provider and requires the owner's separate choice. It is not required for the local-only PCM/VAD test above.

## Host preparation proof

The separate [preparation record](../audit/audio-readiness-preparation-20261017.json) binds the patch, source trees, canonical commands and exact raw stdout/stderr bytes (base64 plus SHA-256). Baseline: upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`, four released patches, and main compatibility patch `77ac41bc11a6facd928f4cef577642b9eeb042ce3da7d820478aa49e1d98fa1e`; staged tree `f49c77b666cef7fd5235cdd786556908527b532e`. Audio patch SHA-256: `82b92d5095ceabc05f0200569da1cc16b861c77b166095982b05d57940573db7`; replay tree `aa90e9a6eca74835dacc2dc55f376bddfd499c25`.

The unchanged baseline produced three failures and one passing control. On the fixed source, the new file passed four cases, the existing selector suite passed fourteen cases (three Linux-only WSL cases were skipped on Windows), and two selected existing missing-library cases passed. These are separate runs; the red and green runs overlap and are not added together. One expanded attempt hit a 65-second outer timeout before a summary was retained, and no test result is claimed for that attempt. No native microphone or device installation was performed.

The later isolated staging helpers have a separate
[namespace host proof](../audit/audio-device-staging-20261017/namespace-private-inputs-828e5d5e/summary.json):
**196 passed, no failures or skips, in 1.22 seconds**, using Windows Python 3.14.2
and the exact frozen packaging 26.0 wheel. The full focused file includes seven
new namespace cases beyond the historical
[OpenSSL checkpoint's 189 passed in 3.97 seconds](../audit/audio-device-staging-20261017/openssl-private-inputs-bd72d882/summary.json).
Each run preserves its own source hashes and original stdout/stderr; these
overlapping counts are not added together. Neither correction ran a new full
Windows repository suite. The prepared bundle comparison preserves the candidate,
wheel catalog and audio patch outputs while retaining the original required
private library inputs. Its preparation receipt's native/device booleans remain
historical observations, separate from the later
[successful native recreation result](../audit/audio-device-staging-20261017/run-39076074868/summary.json).

## Isolated staging history

These four native attempts remain failed runs. Their completed steps are retained
without extending them to later phases or to physical audio readiness.

| Native run | Observed boundary | Source-bound correction or retained progress |
|---|---|---|
| [39068820175](../audit/audio-device-staging-20261017/run-39068820175/summary.json) | After PM and application installation, the dependency graph rejected the candidate's original active Hermes-to-psutil Git requirement. | The [exact psutil source binding](../audit/audio-device-staging-20261017/psutil-source-binding-7fad395/summary.json) maps only that frozen metadata edge to the pinned offline wheel. It does not fetch the URL or admit other URL dependencies. |
| [39070524219](../audit/audio-device-staging-20261017/run-39070524219/summary.json) | Requirement parsing rejected the original inactive KittenTTS URL spelling before graph validation completed. | The [exact parser adaptation](../audit/audio-device-staging-20261017/requirement-parser-f691d31/summary.json) handles the two original malformed optional declarations while preserving their raw bytes and rejecting activation. |
| [39072136395](../audit/audio-device-staging-20261017/run-39072136395/summary.json) | First-root validation rejected ambient OpenSSL `legacy.so`; no complete assembly or CLI receipt was produced. | The [private OpenSSL correction](../audit/audio-device-staging-20261017/openssl-private-inputs-bd72d882/summary.json) adds the matching original provider/config and fixes their routing before the first Python process. |
| [39074656769](../audit/audio-device-staging-20261017/run-39074656769/summary.json) | The first fresh environment assembled, passed explicit native validation of 102 distributions, and completed CLI help. Diagnostics then rejected ambient `libtermux-platform-ns.so`. | The [namespace correction and preserved diagnostic](../audit/audio-device-staging-20261017/namespace-private-inputs-828e5d5e/summary.json) retain the missing original member from the same frozen `libandroid-stub 30-2` archive. The earlier PortAudio `-9999` is inferred from retained `expected_portaudio_failure=true` and the frozen diagnostic source; the original exception text was replaced by the final origin-guard rejection. `protocol_valid` was false and the two-destination workflow did not complete. |

These corrections preserve the offline wheel graph, candidate CFFI bytes and
native origin guard. The [later revised-bundle native run](../audit/audio-device-staging-20261017/run-39076074868/summary.json)
passes complete recreation and diagnostic handling at both final destinations.
The original component matrix's audio failure and all physical microphone/VAD
gates are unchanged.

## Remaining device work

The available device meets the dated ARM64/API identity observation. The
complete isolated software and both native recreation receipts are now verified
in the container. The remaining work requires the actual foreground Termux app
context and a separately initiated physical-device check.

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
