# Audio readiness and physical-device validation

Prepared on 2026-10-17; updated 2026-10-20. This is a separate robustness experiment; no microphone was accessed while preparing it.

## What is fixed, and what is still unproved

The 20 October checkpoint remains **nine published restrictions, seven
native-validated unpublished repairs and two incomplete features**. The
[compatibility audit](compatibility-0.22.2-1.md#remaining-native-runtime-work)
now includes independently reviewed Tokenizers25, Tiktoken7 and locked Rust
native results and the complete public Perth runtime's measured API operations.
The complete 116-package gate now has a reviewed documentation relocation
after two pre-operation failures. Its original 105 wheels/11 APT payloads map
to 28,936 unique file targets; actual offline host installation and 25 tests
plus 48 subtests pass. The next native run passes ten actual operation groups but fails final
integration at a moved TorchAO/PyTorch helper import. Its guarded correction
is saved at 2d4408f and independently passes 30 tests plus 54 subtests.
Corrected run 39458842068 passes all eleven operation groups and final integrity,
library and disconnected-network checks. Its [independent whole-artifact and
source review](../audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review/NATIVE-SUCCESS-REVIEW.json)
also passes. These software results do not establish
physical capture, permission, silence stopping or VAD. NeuTTS engine admission,
default initialization and actual synthesis remain unmeasured alongside the
later physical-device checks.
No command in this guide was executed as part of this checkpoint.

The standalone [audio-readiness patch](../patches/next-stable/audio-readiness.patch) turns an optional library's import-time native initialization failure into a readable diagnostic, retaining the original exception and message. It also rejects a populated PortAudio inventory that contains only output devices. Missing Python modules and a missing PortAudio shared library retain their existing diagnostics; empty or failed forwarded-audio inventories retain their existing handling. This patch does not provide an Android audio framework or establish microphone/VAD support.

The [native audio record](../audit/native-probes-9fcd31c-20261017/audio-summary.json) proves NumPy 2.4.3 arithmetic, FFT and internal LAPACK with both the build runtime and original package libraries. The same run failed PortAudio initialization with error -9999. Its mapped OpenSL ES object was the official libandroid-stub wrapper, and the container lacked the actual Android framework library and recorded Binder/audio services. The relationship to the engine error is an inference from those measured facts and the pinned wrapper source. Actual device initialization, microphone permission, capture, and silence stopping remain unproved.

The successful e271 full candidate still selects seven extras and does not include `audio-io`. Changing `voice.capture_backend` alone does not supply NumPy or sounddevice. This guide does not authorize or perform an installation, add an extra to the released package, or change the main compatibility patch.

## Exact software prerequisites before a phone test

The full [Hermes audio preparation](../audit/audio-hermes-native-20261018/run-39084612542.json)
now passes two independent fresh native constructions. Each contains 101
application distributions and 6,906 wheel-owned files, four PM distributions
and 75 wheel-owned files, and 102 catalog rows preserving all 100 original rows.
Source, payload, metadata, links, CFFI and NumPy operations pass. Selected wheel
results agree; path-specific bytecode and metadata differ, so whole-environment
hash equality is not claimed. Both container attempts report PortAudio error
-9999, `Initializing engine failed`, and all eight measured framework/Binder
paths absent. No stream or microphone was opened.

Use the [complete offline input bundle](../audit/audio-hermes-native-20261018/device-inputs-39084612542.json)
from [run 39084612542, artifact 12119969057](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39084612542/artifacts/12119969057).
Its exact ZIP is 233,720,666 bytes, SHA-256
`794cef032430d5dea92a316872cd2d7a6015ec854e4c15a38999c880b6b37177`.
All 21 ZIP members and 20 manifest entries were independently verified. The
recorded Actions expiry is 17 November 2026 at 00:56:38 UTC. The separate
67,968,381-byte native evidence ZIP has SHA-256
`92c6c20e54c93ba5bd9ddb51affe4775ec01cc1970ad93a9990759e2f6236e43`;
all 186 members were checked. Both retained receipts are saved locally in
commit `9877b37`.

Construct on the actual native ARM64 Termux device, at a new private final
destination. The bundle contains the exact candidate, original assembly
helpers, audio inputs, wrapper and patches. It does not contain a copied CI
venv. The command extracts into owned paths without installing the DEB or
replacing the installed Hermes environment. Choose fresh input/output paths
for every reconstruction; do not move the completed environment.

```bash
# Set AUDIO_BUNDLE_ZIP to the verified complete input ZIP on this device.
AUDIO_INPUTS="$HOME/hermes-audio-inputs-20261020"
AUDIO_CHECK="$HOME/hermes-audio-device-20261020"
(
  set -Eeuo pipefail
  : "${AUDIO_BUNDLE_ZIP:?Set the complete offline reconstruction ZIP path}"
  test "$PREFIX" = /data/data/com.termux/files/usr
  test "$(uname -m)" = aarch64
  test "$(wc -c < "$AUDIO_BUNDLE_ZIP")" -eq 233720666
  printf '%s  %s\n' \
    794cef032430d5dea92a316872cd2d7a6015ec854e4c15a38999c880b6b37177 \
    "$AUDIO_BUNDLE_ZIP" | sha256sum -c -
  test ! -e "$AUDIO_INPUTS" && test ! -L "$AUDIO_INPUTS"
  test ! -e "$AUDIO_CHECK" && test ! -L "$AUDIO_CHECK"
  umask 077
  mkdir "$AUDIO_INPUTS"
  unzip -q "$AUDIO_BUNDLE_ZIP" -d "$AUDIO_INPUTS"
  cd "$AUDIO_INPUTS"
  bash scripts/run_audio_hermes_preparation.sh --native \
    candidate audio-inputs patches/next-stable/audio-readiness.patch \
    "$AUDIO_CHECK" prepare-and-probe
)
```

Stop if preparation fails. Its canonical probe imports dependencies and
enumerates audio metadata without recording. A successful preparation exit
does not imply input readiness; inspect the exact probe receipts below.
The probe intentionally refuses to overwrite an existing receipt, so rebuild
at another fresh final path when a new readiness observation is needed.

The historical dependency-only component proof is [run 39043935925](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39043935925), artifact `12104898993`; the [build receipt](../audit/native-probes-9fcd31c-20261017/audio-build-probe.json) records these exact files. The runtime closure has four packages; the fifth retained wheel is build support.

| Artifact | Bytes | SHA-256 | Role |
|---|---:|---|---|
| `cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl` | 201386 | `36977e26001a7f4da546fda9fd8715ff6e81e6661d02eb28bc5f2ee0f235f9b2` | Runtime |
| `numpy-2.4.3-cp314-cp314-android_24_arm64_v8a.whl` | 7180471 | `4b1840a7d73d6111604b22102e58b551a670db579164e0ddede3e78733fd68d4` | Runtime, built with internal BLAS/LAPACK fallback |
| `pycparser-3.0-py3-none-any.whl` | 48172 | `b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992` | Runtime |
| `sounddevice-0.5.5-py3-none-any.whl` | 32807 | `30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f` | Runtime |
| `setuptools-83.0.0-py3-none-any.whl` | 1008090 | `29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3` | Retained build support |

The recorded additional runtime library is official Termux `portaudio` version `19.07.00-3`: `libportaudio.so.2`, 61976 bytes, SHA-256 `116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073`; its SONAME aliases contain the same bytes. It needs `libc.so`, `libm.so`, and `libOpenSLES.so`. The phone must provide the real working Android audio framework, not merely an importable wrapper. The probe records the actual mapped paths, owners and hashes, including the system OpenSL ES object if the wrapper loads it. Do not install a fabricated replacement or relax the initialization check.

The original Sounddevice wheel above remains a source input. Canonical preparation
applies only the reviewed Android library-discovery change to `sounddevice.py`
and its RECORD. The derived wheel is 130,096 bytes, SHA-256
`b98585045e53173f589267e8ee543f034ba4229b0696ec32032b9f5f5637caf7`.
Its original dependencies, metadata, tags, license and six other members remain
unchanged. Loader and PortAudio initialization errors remain visible.

The older `/out/environment/bin/python` proof was dependency-only. The complete
recorder environment now uses the fresh canonical payload, app and application
venv shown below. Canonical assembly writes and verifies `hermes-agent.pth`,
binding the interpreter to its owned application source even under `-I`.
The task-local `AUDIO_*` shell variables are not new Hermes settings.

## Device facts: no recording

Use a native foreground Termux session. The following commands only report the selected runtime facts and current recorder status; `-i` does not start recording. If Termux:API is absent, report that result and stop that command path.

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

After successful reconstruction, use only that final payload's interpreter and
libraries. The receipt check below does not start or enumerate a new stream;
it reads the non-recording probe already produced by `prepare-and-probe`.

```bash
: "${AUDIO_CHECK:?Set the successful fresh final preparation path}"
AUDIO_PAYLOAD="$AUDIO_CHECK/payload"
AUDIO_SOURCE="$AUDIO_PAYLOAD/app"
AUDIO_ENV="$AUDIO_PAYLOAD/venv"
AUDIO_PY="$AUDIO_ENV/bin/python"
AUDIO_EVIDENCE="$(mktemp -d "$PREFIX/tmp/hermes-audio-device.XXXXXX")"
chmod 700 "$AUDIO_EVIDENCE"
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV HERMES_PYTHON __HERMES_ACTIVATED
export HERMES_INSTALL_ROOT="$AUDIO_SOURCE"
export HERMES_PYTHON_SRC_ROOT="$AUDIO_SOURCE"
export HERMES_RUNTIME_DIR="$AUDIO_PAYLOAD/tools"
export LD_LIBRARY_PATH="$AUDIO_PAYLOAD/tools/python$PREFIX/lib:$AUDIO_PAYLOAD/tools/node$PREFIX/lib:$AUDIO_PAYLOAD/tools/ffmpeg$PREFIX/lib:$AUDIO_PAYLOAD/runtime-libs/lib:$PREFIX/lib"
(
  set -Eeuo pipefail
  test -x "$AUDIO_PY"
  test -f "$AUDIO_SOURCE/tools/voice_mode.py"
  "$AUDIO_PY" -I -B - "$AUDIO_CHECK" <<'PY'
import json
import platform
import sys
from pathlib import Path

assert sys.platform == "android" and platform.machine() in ("aarch64", "arm64")
assert sys.version_info[:2] == (3, 14)
root = Path(sys.argv[1]).resolve(strict=True)
receipt = json.loads((root / "audio-environment-receipt.json").read_text())
assert receipt["final_path"] == str(root), "Reconstruct at the final path"
probe = json.loads((root / "evidence/audio-readiness-probe.json").read_text())
assert probe["dependency_readiness"] == "passed"
assert probe["initialization"]["status"] == "initialized", probe["initialization"]
assert probe["device_inventory_error"] is None
assert any(int(d.get("max_input_channels", 0)) > 0 for d in probe["device_inventory"])
print(json.dumps({"initialization": probe["initialization"],
                  "device_inventory": probe["device_inventory"],
                  "mapped_audio_libraries": probe["mapped_audio_libraries"]}, indent=2))
PY
)
```

Require initialized PortAudio, an actual input device and its supported sample
rate before proceeding. Inspect mapped audio-library paths and ownership in
the receipt. Initialization errors remain failures. Android visibility limits
can restrict process observations; an unreadable process inventory does not
prove that the framework is absent. Enumeration alone is not a capture pass.

## User-initiated local PCM/VAD check

Only the device owner should initiate this block after agreeing to a brief microphone test in a quiet private setting. It uses the real recorder factory and callback path, limits the take to ten seconds, disables streaming and all transcription, prints only numeric observations, and deletes its own temporary WAV. It does not run a model or send the take to an STT provider. The outer timeout bounds the test; normal cleanup calls `shutdown()` to release the persistent input stream. Forced termination can prevent Python cleanup, so inspect the private take directory afterward if the test was interrupted. Only the validated WAV path is deleted automatically.

```bash
# This block is for a later user-initiated microphone test.
# Every explicit take gets its own profile, cache and recording directory.
(
set -Eeuo pipefail
: "${AUDIO_EVIDENCE:?Complete the non-recording readiness check first}"
umask 077
AUDIO_TAKE="$(mktemp -d "$AUDIO_EVIDENCE/take.XXXXXX")"
mkdir -m 700 "$AUDIO_TAKE/profile" "$AUDIO_TAKE/tmp" "$AUDIO_TAKE/cache"
cat > "$AUDIO_TAKE/profile/config.yaml" <<'YAML'
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
HERMES_HOME="$AUDIO_TAKE/profile" \
TMPDIR="$AUDIO_TAKE/tmp" XDG_CACHE_HOME="$AUDIO_TAKE/cache" \
timeout --signal=INT --kill-after=3s 20s "$AUDIO_PY" -I -B - <<'PY'
import json
import os
import threading
import time
import wave
from pathlib import Path

import pm
from tools import transcription_tools, voice_mode
from tools.voice_mode import AudioRecorder, create_audio_recorder

private_tmp = Path(os.environ["TMPDIR"]).resolve(strict=True)
expected_recordings = private_tmp / "hermes_voice"
assert private_tmp.is_dir()
assert Path(voice_mode._TEMP_DIR).resolve() == expected_recordings
assert pm.available("audio-io"), "Stop: the reviewed optional audio environment is not ready"
stt = transcription_tools._load_stt_config()
assert stt.get("provider") == "none" and not stt.get("streaming", False)
recorder = create_audio_recorder()
assert isinstance(recorder, AudioRecorder)
recorder._silence_threshold = 200
recorder._silence_duration = 3.0
recorder._max_recording_seconds = 10.0
ended = threading.Event()
owned_recording = None
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
    candidate = Path(recording)
    if candidate.is_symlink():
        raise RuntimeError("Recording path is a symlink")
    candidate = candidate.resolve(strict=True)
    if candidate.parent != expected_recordings or not candidate.is_file():
        raise RuntimeError("Recording escaped the private validation directory")
    # Assign only after containment checks; cleanup cannot delete an unowned path.
    owned_recording = candidate
    with wave.open(str(owned_recording), "rb") as audio:
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
    try:
        recorder.shutdown()
    finally:
        if owned_recording is not None:
            owned_recording.unlink(missing_ok=True)
PY
)
```

For a successful silence-stop observation, speak for about one or two seconds, then remain quiet for about three seconds. Require real speech detection, nontrivial recorded PCM, and stopping before the ten-second cap; reaching the cap does not prove VAD. Repeat as a new explicit take to check reopen/cleanup, then check a manual stop in the normal product UI if that UI is part of the intended release. On denial of microphone permission, expect a clean unavailable/error result; grant permission only deliberately and retry. Verify the Android microphone indicator clears after shutdown. Background capture, Bluetooth/headset routing, wake words, streaming STT and full duplex are separate unproved scopes.

## Termux:API and the normal Hermes UI

`voice.capture_backend` accepts `auto`, `termux-api`, or `sounddevice`. `auto` prefers the available Termux:API backend. Termux:API records encoded audio and supports manual stopping and a duration cap; it intentionally reports `supports_silence_autostop=False`, so it cannot establish the PCM/VAD claim.

If a user separately wants to verify the normal CLI with their existing chosen STT provider, record the current configuration first, then set `voice.capture_backend` to the intended backend, `voice.max_recording_seconds` to `10`, `voice.silence_duration` to `3`, `voice.submit_mode` to `draft`, `voice.auto_tts` to `false`, and `stt.streaming` to `false` through `hermes config set <key> <value>`. Start `hermes`, use `/voice status`, then `/voice on`; only pressing the displayed record shortcut (default Ctrl+B) starts a take. `/voice off` releases the recorder. The CLI transcribes after stop even in draft mode, so this UI check may send audio to the user's configured provider and requires their separate choice. It is not required for the local-only PCM/VAD test above.

## Host preparation proof

The overall repository [CI run 39429636399](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39429636399)
at `d215961` passed 1,057 tests, 154 additional subtests and 80 skips.
That broad host run is separate from the focused audio counts below and from
physical microphone validation. The [20 October component checkpoint](remaining-portability-work.md#current-native-component-checkpoint-20-october-2026)
retains nine published restrictions, seven native-validated unpublished repairs
and two incomplete feature gates: complete NeuTTS and physical microphone/VAD.
No new microphone capture or VAD result is claimed; the two fresh-path audio
preparations above remain the measured software evidence.

The current preparer passed 199 focused host tests with no skips before the two
complete fresh-path native successes linked above. The following earlier patch
checks remain historical evidence; their overlapping counts are not aggregated.

The separate [preparation record](../audit/audio-readiness-preparation-20261017.json) binds the patch, source trees, canonical commands and exact raw stdout/stderr bytes (base64 plus SHA-256). Baseline: upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`, four released patches, and main compatibility patch `77ac41bc11a6facd928f4cef577642b9eeb042ce3da7d820478aa49e1d98fa1e`; staged tree `f49c77b666cef7fd5235cdd786556908527b532e`. Audio patch SHA-256: `82b92d5095ceabc05f0200569da1cc16b861c77b166095982b05d57940573db7`; replay tree `aa90e9a6eca74835dacc2dc55f376bddfd499c25`.

The unchanged baseline produced three failures and one passing control. On the fixed source, the new file passed four cases, the existing selector suite passed fourteen cases (three Linux-only WSL cases were skipped on Windows), and two selected existing missing-library cases passed. These are separate runs; the red and green runs overlap and are not added together. One expanded attempt hit a 65-second outer timeout before a summary was retained, and no test result is claimed for that attempt. No native microphone or device installation was performed.

## Information still needed from the device owner

Please identify the ARM64 Android device/model and Android release/API level, the native Termux version/channel, whether the matching Termux:API add-on is present, and whether you can later initiate a brief local microphone test with Android's microphone permission. Reconstruct the isolated audio environment described above and pass its non-recording readiness check before initiating a take. No model, token or recording upload is needed for that local check.
