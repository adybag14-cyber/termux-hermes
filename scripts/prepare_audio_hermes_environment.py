#!/usr/bin/env python3
"""Prepare an isolated Hermes + audio-io environment from exact unpublished inputs.

Fetch mode runs on the host. Prepare mode runs on native Termux with the exact
candidate interpreter. No Debian package is installed or built, no user profile is
selected, and no microphone is opened. A fresh PM environment is built at its
final path. A CI venv is evidence, never a phone installer.
"""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import types
from urllib.request import urlopen
import zipfile

PREFIX = Path("/data/data/com.termux/files/usr")
INSTALLED = PREFIX / "lib/hermes-agent"
TARGET = "linux-arm64-bionic"
UPSTREAM = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
IMAGE = "termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303"
BASE_EXTRAS = ["acp", "cron", "matrix", "mcp", "telegram", "termux", "uvloop"]
EXTRAS = sorted([*BASE_EXTRAS, "audio-io"])
CATALOG_SHA = "d2dc66575cf8aa5ef828e5e536b4d55b8801143101b7e608f6fb4878c2397904"
UV_LOCK_SHA = "72abb87a634769baaf30830cd317892053c6e15f8e9519b085524fa0ed542829"
PM_LOCK_SHA = "49b79259220160f147255078a19af541a5f328d3871c8041cc1eb909d19eb549"
PYPROJECT_SHA = "7ee8c02a9eb624c8fe2c718ba0f69a573d55e5223f3297bb3439afa2dd275547"
PATCH_SHA = "82b92d5095ceabc05f0200569da1cc16b861c77b166095982b05d57940573db7"
PATCH_BYTES = 8470
PATCH_PATHS = {
    "tools/voice_mode.py", "tools/voice_mode_capture.py",
    "tests/tools/test_voice_wsl_pipewire.py", "tests/tools/test_voice_audio_readiness.py",
}
PRODUCTION_FILES = {"tools/voice_mode.py", "tools/voice_mode_capture.py"}
AUDIO_SOURCE_FILES = {
    "tools/voice_mode.py": (70749, "2080ba077ec94146d06cbd704a7e21763e5cf37f4221561145b4c45de6a78a58"),
    "tools/voice_mode_capture.py": (7542, "492c013f8473acdd58dff027ffc4f787347dc27524e801692bf32efe67516d60"),
    "tests/tools/test_voice_wsl_pipewire.py": (2233, "3ac8ad669799f3c23b1bfda02996619e7f71d8ed08c58a80fd61234981870be0"),
    "tests/tools/test_voice_audio_readiness.py": (3281, "d94b5bc0db75dff255c4f1ef5cd155d5605ce907d2606c2e71052457b5c470ef"),
}
NEW_SOURCE_FILES = {"tests/tools/test_voice_audio_readiness.py"}
MARKER_PATCH_RELATIVE = "patches/next-stable/audio-pm-marker-bytecode.patch"
MARKER_PATCH_BYTES = 533
MARKER_PATCH_SHA = "f4e63265aa3a71ceb0f69f11f7876a7e32e1f7e8a0704de5c8df96860e3aa390"
MARKER_SOURCE_FILE = "pm/bundled_wheels.py"
MARKER_SOURCE_BEFORE = (16412, "53cb1f02d52a601bc796a6b1156dd57510de8aaba892bd70b8b65c4faa15a975")
MARKER_SOURCE_AFTER = (16418, "f3e49e498184a212d02a5c4dcaeb1e0b529b15ebc01bfd752463159f24616a35")
SOURCE_FILES = {**AUDIO_SOURCE_FILES, MARKER_SOURCE_FILE: MARKER_SOURCE_AFTER}
ASSEMBLY = {
    "scripts/build/agent.py": (8754, "f59ed0dc39a37814a43f2465e1391311a3ce8203e42a69257e58db6f3cda3652"),
    "scripts/build/inputs.py": (5846, "36fb218726fce97505d7dfd50002046bb9c19b25c0b7cc546bae0b9c586083d9"),
    "scripts/build/launchers.py": (4861, "cf5c225ded65193042a330f69b217a5ffcd5201032cca9e288cebea681cb37b3"),
    "scripts/build/launcher_wrapper.py": (6327, "bfab043b63b8faa588ea1fa6f9143ff33b319df71ef6a7e3855f8574c2b07155"),
    "scripts/bundles/payload.py": (7974, "ab2fb59a2face83a92121af5e09e68b04c3abe3301261248cdf0c8a2cca9ae98"),
}
SHARED_FETCH_SHA = "dc075415b46e14f3f09fb6a889fdf38279564b2f2e6e6008b21232545d1d6d8a"
AUDIO_RUN = 39043935925
AUDIO_HEAD = "9fcd31cbd1e10cf9ffdd88c28ab95824ee13700b"
AUDIO_ARTIFACT = 12104898993
AUDIO_BYTES = 11408114
AUDIO_SHA = "e30a93fb8d503a020091c3c853b17b361fa6f833afb0a506742f138f8e1ec511"
AUDIO_ARCHIVE = "audio-artifact-12104898993.zip"
STUB_FILE = "libandroid-stub_30-2_aarch64.deb"
STUB_BYTES = 26788
STUB_SHA = "74087792a86e3f90772627f2217797e422e5d5fc47f24ad825fc3bbb539a667a"
STUB_URL = "https://packages.termux.dev/apt/termux-main/pool/main/liba/libandroid-stub/" + STUB_FILE
OPENSLES_SHA = "87c61d872767541e332783d85f70bfdc1b2d48e373ef3025380345171bac4db9"
OPENSLES_BYTES = 11480
PLATFORM_NAMESPACE_FILE = "libtermux-platform-ns.so"
PLATFORM_NAMESPACE_BYTES = 6552
PLATFORM_NAMESPACE_SHA = "6c39c6a3318accd5e34f4f2c9e5c9e14eed113fb3a92e8c0be86006dc9256e34"
PORTAUDIO_SHA = "116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073"
PORTAUDIO_FILES = ["libportaudio.so", "libportaudio.so.2", "libportaudio.so.2.0.0"]
NEW_WHEELS = [
    "numpy-2.4.3-cp314-cp314-android_24_arm64_v8a.whl",
    "sounddevice-0.5.5-py3-none-any.whl",
]

SOUNDDEVICE_FILE = "sounddevice-0.5.5-py3-none-any.whl"
SOUNDDEVICE_PATCH_RELATIVE = "patches/next-stable/sounddevice-android-discovery.patch"
SOUNDDEVICE_PATCH_PIN = (556, "7f655d5547c715ed62941d4b3bb5f0d87657a8fcede7dddb277e9afa516cf2e7")
SOUNDDEVICE_SOURCE_BEFORE = (111663, "5f871d3a3ccc52d737e4507d25f785ec414da87115c0048d6b538d872792bce7")
SOUNDDEVICE_SOURCE_AFTER = (111841, "7013191cabd99bbd5980fdf2d4c14ac65aeeb89c6effb5112289993806e8d49c")
SOUNDDEVICE_WHEEL_AFTER = (130096, "b98585045e53173f589267e8ee543f034ba4229b0696ec32032b9f5f5637caf7")
SOUNDDEVICE_ORIGIN = {
    "kind": "registry-wheel", "registry": "https://pypi.org/simple",
    "url": "https://files.pythonhosted.org/packages/1e/0a/478e441fd049002cf308520c0d62dd8333e7c6cc8d997f0dda07b9fbcc46/"
           "sounddevice-0.5.5-py3-none-any.whl",
    "sha256": "30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f",
}

# The exact e271 payload contains one unresolved documentation link. Preserve its
# original bytes and report that limitation; this is not a general missing-link
# allowance. The source inventory is captured immediately after verified .deb
# extraction, before any audio preparation changes.
BASELINE_MISSING_DOCUMENTATION_LINK = {
    "path": "tools/ffmpeg/data/data/com.termux/files/usr/share/doc/ffmpeg/copyright",
    "target": "../../LICENSES/GPL-3.0.txt",
    "missing_destination": "tools/ffmpeg/data/data/com.termux/files/usr/share/LICENSES/GPL-3.0.txt",
    "original_inventory_sha256": "dade6143af33f29c3d219578e68683269c1664f036e556f8399ff8a225be48b6",
    "preserved_license": {
        "path": "runtime-libs/share/LICENSES/GPL-3.0.txt",
        "bytes": 35149,
        "sha256": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    },
}

SHARED_WHEELS = {
    "cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl": (201386, "026bdab93fdadca4ddf85071c35736ec1b98b1cec575d2bf9280684940642165"),
    "pycparser-3.0-py3-none-any.whl": (48172, "b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992"),
}

AUDIO_MEMBERS = {
    "AUDIO-HOST-RUNTIME-PROBE.json": {
        "bytes": 1311,
        "sha256": "23dd1fd00abd9732844589c8764fa7c0ab922431d6136239b52e98ddbde26f19",
        "crc32": 3021044519
    },
    "AUDIO-RUNTIME-INPUTS.json": {
        "bytes": 1318,
        "sha256": "61cd76cdc76463b73819aeb7b310aaf6fb9005502a2c31b5f7f15362da7c5871",
        "crc32": 1972188791
    },
    "AUDIO-HOST-ORIGINAL-RUNTIME-PROBE.json": {
        "bytes": 1311,
        "sha256": "23dd1fd00abd9732844589c8764fa7c0ab922431d6136239b52e98ddbde26f19",
        "crc32": 3021044519
    },
    "BUILD-ADAPTATIONS.sha256": {
        "bytes": 581,
        "sha256": "a7b18a198c5128b59534bc610b237b0f55bb6cabb26d39b739c7bd6c695edbbe",
        "crc32": 1078011054
    },
    "BUILD-PROBE.json": {
        "bytes": 2024,
        "sha256": "0f7a719139998ec3f536cf3d01fa8310c4c29077305879da79269ceafd0516e7",
        "crc32": 197649443
    },
    "BUILD-RUNTIME-SHA256SUMS": {
        "bytes": 107,
        "sha256": "3ab7fa87e577554b9e33b9abbd4de0a51167ba41bd4a651c0df84d9ccb0b11ca",
        "crc32": 1946480625
    },
    "NATIVE-LINKAGE.json": {
        "bytes": 12794,
        "sha256": "630c17b01e1e252fcba04475865b90afd65981ac1b74a9af5de2c38c9b1d9887",
        "crc32": 1478869519
    },
    "NUMPY-ORIGINAL-RUNTIME-PROBE.json": {
        "bytes": 662,
        "sha256": "92f6618f400db6722e3e8286351d818a048ea4343baaff32a19eb5b09d35af79",
        "crc32": 1197861944
    },
    "NUMPY-RUNTIME-PROBE.json": {
        "bytes": 662,
        "sha256": "92f6618f400db6722e3e8286351d818a048ea4343baaff32a19eb5b09d35af79",
        "crc32": 1197861944
    },
    "ORIGINAL-RUNTIME-PROBE.json": {
        "bytes": 987,
        "sha256": "67a1c10f1be5760c134a5cae0505962704012e6d51a63e8b441d3ff58bd77944",
        "crc32": 3281731238
    },
    "PROBE-INPUTS.json": {
        "bytes": 410,
        "sha256": "d167768553ca08f680ea1c88d2b188164440f470f8119f59dd9e2c834b7126b8",
        "crc32": 2880976863
    },
    "PROBE-PYPROJECT.toml": {
        "bytes": 42858,
        "sha256": "7ee8c02a9eb624c8fe2c718ba0f69a573d55e5223f3297bb3439afa2dd275547",
        "crc32": 1309948807
    },
    "PROBE-UV.lock": {
        "bytes": 1203717,
        "sha256": "72abb87a634769baaf30830cd317892053c6e15f8e9519b085524fa0ed542829",
        "crc32": 3570219434
    },
    "RUNTIME-PROBE.json": {
        "bytes": 978,
        "sha256": "653fab8e8ac7d84efbd7d98c6f7cd1f3fadd9e05b24e2e9a633ce83064202e44",
        "crc32": 2238880350
    },
    "TERMUX-PACKAGES.tsv": {
        "bytes": 2223,
        "sha256": "29263d77a82cfd75484c3ff5212aa2098e58ffc83140d1d6ebd0928a251578ba",
        "crc32": 3224843613
    },
    "added-runtime-libs/libportaudio.so": {
        "bytes": 61976,
        "sha256": "116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073",
        "crc32": 2935650766
    },
    "added-runtime-libs/libportaudio.so.2": {
        "bytes": 61976,
        "sha256": "116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073",
        "crc32": 2935650766
    },
    "added-runtime-libs/libportaudio.so.2.0.0": {
        "bytes": 61976,
        "sha256": "116ff3e80f1b29042cad96e3f923d25dfe5325420d4b5140653fa2226ba47073",
        "crc32": 2935650766
    },
    "build-runtime-libs/libc++_shared.so": {
        "bytes": 1423696,
        "sha256": "05bef9d3901910c3ff8ab450b03bc8b28383d363a2290f2f7b9aed7331ea6ff7",
        "crc32": 182175236
    },
    "build-set.txt": {
        "bytes": 11,
        "sha256": "8f95c9691403792f5ef4b23304ac6c71a45313a44b5566490efb4ab4fc6cb63a",
        "crc32": 3132900520
    },
    "native-probe.log": {
        "bytes": 51290,
        "sha256": "1b3a092b9cad91cafc9863072243b1d81393da9a158d233605556b20f38fe31c",
        "crc32": 2924846399
    },
    "requirements.txt": {
        "bytes": 59,
        "sha256": "5294c23be817593f6d70e71a1cac985986e2771d4f6811d23d628f50cf25b71b",
        "crc32": 3997936124
    },
    "resolved.txt": {
        "bytes": 71,
        "sha256": "918eb03ff3bc8007423f998c0e92f72f1bd20e51b021e45772c52706e35289fd",
        "crc32": 3462595853
    },
    "wheelhouse/cffi-2.1.1-cp314-cp314-android_24_arm64_v8a.whl": {
        "bytes": 201386,
        "sha256": "36977e26001a7f4da546fda9fd8715ff6e81e6661d02eb28bc5f2ee0f235f9b2",
        "crc32": 2318612342
    },
    "wheelhouse/numpy-2.4.3-cp314-cp314-android_24_arm64_v8a.whl": {
        "bytes": 7180471,
        "sha256": "4b1840a7d73d6111604b22102e58b551a670db579164e0ddede3e78733fd68d4",
        "crc32": 693738865
    },
    "wheelhouse/pycparser-3.0-py3-none-any.whl": {
        "bytes": 48172,
        "sha256": "b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992",
        "crc32": 2508215293
    },
    "wheelhouse/setuptools-83.0.0-py3-none-any.whl": {
        "bytes": 1008090,
        "sha256": "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3",
        "crc32": 2443557234
    },
    "wheelhouse/sounddevice-0.5.5-py3-none-any.whl": {
        "bytes": 32807,
        "sha256": "30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f",
        "crc32": 3639104039
    }
}


class PreparationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PreparationError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def pinned(path, size, digest):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "input is not a regular file: " + path.name)
    require(path.stat().st_size == size and sha256(path) == digest, "input identity differs: " + path.name)
    return {"file": path.name, "bytes": size, "sha256": digest}


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict), "expected a JSON object")
    return value


def write_json(path, value):
    path = Path(path)
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o644)
    return {"file": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def contained(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative,
            "invalid payload path")
    require(not PurePosixPath(relative).is_absolute()
            and all(p not in ("", ".", "..") for p in relative.split("/")), "unsafe payload path")
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()), "path escapes owned payload")
    return path


def inventory(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "inventory root is not a directory")
    result = {}
    def walk(directory):
        for path in sorted(directory.iterdir()):
            key = path.relative_to(root).as_posix()
            info = path.lstat()
            row = {"mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                row.update(kind="symlink", target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                row.update(kind="directory")
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                row.update(kind="file", bytes=info.st_size, sha256=sha256(path))
            else:
                raise PreparationError("special file in input: " + key)
            result[key] = row
    walk(root)
    return result


def inventory_sha(rows):
    return hashlib.sha256((json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def subtree(rows, prefix):
    return {n[len(prefix)+1:]: r for n, r in rows.items() if n.startswith(prefix + "/")}


def fresh_output(out, inputs=()):
    out = Path(out).absolute()
    require(not out.exists() and not out.is_symlink(), "output must be a new directory")
    for source in inputs:
        source = Path(source).resolve()
        require(not out.resolve().is_relative_to(source) and not source.is_relative_to(out.resolve()),
                "output overlaps an input or installed payload")
    return out.resolve()


def shared_fetch():
    path = Path(__file__).with_name("fetch_compatibility_candidate.py")
    require(path.is_file() and not path.is_symlink() and sha256(path) == SHARED_FETCH_SHA,
            "shared candidate verifier identity differs")
    name = "_audio_exact_candidate_fetch"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_candidate(directory):
    directory = Path(directory)
    shared = shared_fetch()
    receipt = json_object((directory / "candidate-receipt.json").read_bytes())
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "verified",
            "candidate receipt was not verified")
    pin = shared.PIN
    for key, expected in (("repository", pin.repository), ("run_id", pin.run_id), ("head_sha", pin.head_sha)):
        require(type(receipt.get(key)) is type(expected) and receipt[key] == expected, "candidate receipt mismatch: " + key)
    require(receipt.get("artifact") == {"id": pin.artifact_id, "name": pin.artifact_name,
                                     "bytes": pin.archive_size, "sha256": pin.archive_sha256},
            "candidate artifact identity differs")
    for entry in pin.entries:
        if entry.output:
            pinned(directory / entry.output, entry.size, entry.sha256)
    identity = json_object((directory / "CANDIDATE-IDENTITY.json").read_bytes())
    selection = json_object((directory / "venv-selection.json").read_bytes())
    require(identity == shared.IDENTITY and selection == shared.SELECTION, "candidate raw source/selection identity differs")
    for key, raw in (("identity", identity), ("native_selection", selection)):
        wrapped = receipt[key]
        require({k: v for k, v in wrapped.items() if k not in ("file", "sha256", "zip_member")} == raw,
                "candidate receipt differs from its raw record")
    deb = next(e for e in pin.entries if e.output == shared.IDENTITY["package"])
    require(receipt["package"] == {"file": deb.output, "bytes": deb.size, "sha256": deb.sha256,
                                 "zip_member": deb.member}, "candidate package receipt differs")
    return receipt


def safe_zip_member(info):
    return (
        info.filename and "\\" not in info.filename and ":" not in info.filename
        and not PurePosixPath(info.filename).is_absolute()
        and all(p not in ("", ".", "..") for p in info.filename.split("/"))
        and not info.is_dir() and not info.flag_bits & 1
        and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
        and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
    )


def verify_audio_archive(path, extract=None, *, expected_members=None, archive_pin=None):
    """Verify every raw member; only a fixed small allowlist is ever materialized."""
    members = AUDIO_MEMBERS if expected_members is None else expected_members
    size, digest = (AUDIO_BYTES, AUDIO_SHA) if archive_pin is None else archive_pin
    pinned(path, size, digest)
    outputs = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) == len(members) and {i.filename for i in infos} == set(members),
                "audio artifact member set differs")
        require(all(safe_zip_member(i) for i in infos), "unsafe audio artifact member")
        for info in infos:
            pin = members[info.filename]
            require(info.file_size == pin["bytes"] and info.CRC == pin["crc32"], "audio member metadata differs")
            data = archive.read(info)  # zipfile checks the actual CRC, including excluded evidence.
            require(len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"],
                    "audio member bytes differ")
            if extract is not None and (info.filename.startswith(("wheelhouse/", "added-runtime-libs/"))
                                        or info.filename in ("AUDIO-RUNTIME-INPUTS.json", "AUDIO-HOST-ORIGINAL-RUNTIME-PROBE.json",
                                                             "PROBE-INPUTS.json", "NUMPY-ORIGINAL-RUNTIME-PROBE.json")):
                target = contained(extract, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(data)
                target.chmod(0o644)
                outputs[info.filename] = pin
    return outputs


def read_limited(response, size):
    result = bytearray()
    while chunk := response.read(min(1024 * 1024, size + 1 - len(result))):
        result.extend(chunk)
        require(len(result) <= size, "download exceeds its exact size")
    require(len(result) == size, "download is incomplete")
    return bytes(result)


def fetch_inputs(out):
    out = fresh_output(out)
    shared = shared_fetch()
    client = shared.GitHubClient(os.environ.get("GH_TOKEN", ""))
    base = "repos/adybag14-cyber/termux-hermes/actions"
    run = client.metadata(f"{base}/runs/{AUDIO_RUN}")
    artifact = client.metadata(f"{base}/artifacts/{AUDIO_ARTIFACT}")
    for key, expected in (("id", AUDIO_RUN), ("head_sha", AUDIO_HEAD), ("status", "completed"),
                          ("conclusion", "failure"), ("path", ".github/workflows/compatibility-probes.yml")):
        require(type(run.get(key)) is type(expected) and run[key] == expected, "audio run metadata differs")
    for key, expected in (("id", AUDIO_ARTIFACT), ("name", "termux-compatibility-audio"),
                          ("size_in_bytes", AUDIO_BYTES), ("digest", "sha256:" + AUDIO_SHA), ("expired", False)):
        require(type(artifact.get(key)) is type(expected) and artifact[key] == expected, "audio artifact metadata differs")
    require(artifact.get("workflow_run", {}).get("id") == AUDIO_RUN
            and artifact["workflow_run"].get("head_sha") == AUDIO_HEAD
            and artifact["workflow_run"].get("repository_id") == 1305668154
            and artifact["workflow_run"].get("head_repository_id") == 1305668154, "audio artifact association differs")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".audio-fetch-", dir=out.parent) as temporary:
        stage = Path(temporary) / "verified"
        stage.mkdir()
        with client.artifact_stream(f"{base}/artifacts/{AUDIO_ARTIFACT}/zip") as stream:
            (stage / AUDIO_ARCHIVE).write_bytes(read_limited(stream, AUDIO_BYTES))
        verify_audio_archive(stage / AUDIO_ARCHIVE)
        with urlopen(STUB_URL, timeout=30) as response:
            require(response.status == 200, "official wrapper archive download failed")
            (stage / STUB_FILE).write_bytes(read_limited(response, STUB_BYTES))
        pinned(stage / STUB_FILE, STUB_BYTES, STUB_SHA)
        for name, (size, digest) in ASSEMBLY.items():
            url = "https://raw.githubusercontent.com/NousResearch/hermes-agent/" + UPSTREAM + "/" + name
            with urlopen(url, timeout=30) as response:
                require(response.status == 200 and response.geturl() == url, "canonical source response differs")
                data = read_limited(response, size)
            path = stage / "assembly" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            pinned(path, size, digest)
        receipt = {"schema_version": 1, "status": "verified-reconstruction-inputs",
                   "audio": {"run_id": AUDIO_RUN, "artifact_id": AUDIO_ARTIFACT, "head_sha": AUDIO_HEAD,
                             "bytes": AUDIO_BYTES, "sha256": AUDIO_SHA, "members": AUDIO_MEMBERS,
                             "historical_full_audio_lane": "failed"},
                   "opensles_archive": {"url": STUB_URL, "bytes": STUB_BYTES, "sha256": STUB_SHA,
                                        "package": "libandroid-stub", "version": "30-2"},
                   "canonical_source": {"repository": "NousResearch/hermes-agent", "commit": UPSTREAM, "files": ASSEMBLY},
                   "source_executed": False, "published_release": False}
        write_json(stage / "audio-inputs-receipt.json", receipt)
        for path in stage.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        stage.chmod(0o755)
        require(not out.exists(), "input output appeared during verification")
        stage.rename(out)
    return receipt


def patch_sections(raw):
    lines = raw.decode("utf-8").splitlines(keepends=True)
    sections = {}
    current = None
    for line in lines:
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/([A-Za-z0-9_./-]+) b/\1\n", line)
            require(match is not None, "patch renames or unsafe paths are forbidden")
            current = match[1]
            require(current not in sections and all(p not in ("", ".", "..") for p in current.split("/")),
                    "duplicate or unsafe patch path")
            sections[current] = []
        else:
            require(current is not None, "patch preamble is not supported")
        if current is not None:
            sections[current].append(line)
        require(not line.startswith(("GIT binary patch", "Binary files ", "rename ", "copy ", "deleted file mode",
                                     "old mode", "new mode")), "patch must only edit reviewed text")
    return sections


def apply_text_hunks(before, section):
    """Strict unified hunks, no fuzz/offset/rename or newline normalization."""
    source = before.decode("utf-8").splitlines(keepends=True)
    output, position, i, count = [], 0, 0, 0
    while i < len(section):
        line = section[i]
        if not line.startswith("@@ "):
            i += 1
            continue
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)\n$", line)
        require(match is not None, "invalid unified hunk header")
        old_count, new_count = int(match[2] or 1), int(match[4] or 1)
        old_start = int(match[1]) - (1 if old_count else 0)
        new_start = int(match[3]) - (1 if new_count else 0)
        require(position <= old_start <= len(source), "overlapping or out-of-range hunk")
        output.extend(source[position:old_start])
        require(len(output) == new_start, "new hunk offset differs")
        position = old_start
        i += 1
        old_seen = new_seen = 0
        while i < len(section) and not section[i].startswith("@@ "):
            item = section[i]
            require(item[:1] in (" ", "+", "-"), "unsupported patch line")
            if item[0] in (" ", "-"):
                require(position < len(source) and source[position] == item[1:], "patch context differs")
                position += 1
                old_seen += 1
            if item[0] in (" ", "+"):
                output.append(item[1:])
                new_seen += 1
            i += 1
        require(old_seen == old_count and new_seen == new_count, "hunk line count differs")
        count += 1
    require(count > 0, "patch section contains no hunks")
    output.extend(source[position:])
    return "".join(output).encode("utf-8")


def patch_app(app, patch):
    pinned(patch, PATCH_BYTES, PATCH_SHA)
    sections = patch_sections(patch.read_bytes())
    require(set(sections) == PATCH_PATHS, "audio patch path set differs")
    results = {}
    for name, (size, digest) in AUDIO_SOURCE_FILES.items():
        path = contained(app, name)
        if name in NEW_SOURCE_FILES:
            require(not path.exists() and not path.is_symlink(), "new patch source already exists")
            before = b""
        else:
            require(path.is_file() and not path.is_symlink(), "existing patch source is absent or symlinked")
            before = path.read_bytes()
        raw = apply_text_hunks(before, sections[name])
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, "patched source output differs")
        results[name] = raw
    # Validate every output before mutating even the caller-owned app.
    for name, raw in results.items():
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        (app / name).write_bytes(raw)
        (app / name).chmod(0o644)
    return {n: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for n, raw in results.items()}


def patch_marker_probe(app, patch):
    """Apply the exact canonical marker-probe correction to the owned app only."""
    pinned(patch, MARKER_PATCH_BYTES, MARKER_PATCH_SHA)
    sections = patch_sections(patch.read_bytes())
    require(set(sections) == {MARKER_SOURCE_FILE}, "marker patch path set differs")
    path = contained(app, MARKER_SOURCE_FILE)
    pinned(path, *MARKER_SOURCE_BEFORE)
    raw = apply_text_hunks(path.read_bytes(), sections[MARKER_SOURCE_FILE])
    size, digest = MARKER_SOURCE_AFTER
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
            "marker probe patched source output differs")
    path.write_bytes(raw)
    return {MARKER_SOURCE_FILE: {"bytes": size, "sha256": digest}}


def wheel_members(path):
    with zipfile.ZipFile(path) as wheel:
        infos = wheel.infolist()
        require(len(infos) == len({i.filename for i in infos}), "duplicate wheel member")
        result = {}
        for info in infos:
            if info.is_dir():
                continue
            require(safe_zip_member(info), "unsafe wheel member")
            result[info.filename] = hashlib.sha256(wheel.read(info)).hexdigest()
        return result



def verify_sounddevice_record(members):
    """Verify every original/derived member, including the RECORD self-entry."""
    record = "sounddevice-0.5.5.dist-info/RECORD"
    expected = {
        "_sounddevice.py", "sounddevice.py", record,
        "sounddevice-0.5.5.dist-info/licenses/LICENSE",
        "sounddevice-0.5.5.dist-info/METADATA", "sounddevice-0.5.5.dist-info/WHEEL",
        "sounddevice-0.5.5.dist-info/top_level.txt", "sounddevice-0.5.5.dist-info/zip-safe",
    }
    require(set(members) == expected, "sounddevice member set differs")
    rows = list(csv.reader(io.StringIO(members[record].decode("utf-8"), newline="")))
    require(all(len(row) == 3 for row in rows), "malformed sounddevice RECORD row")
    require(len(rows) == len(expected) and {row[0] for row in rows} == expected,
            "sounddevice RECORD member set differs")
    for name, digest, size in rows:
        if name == record:
            require(digest == size == "", "sounddevice RECORD self-entry differs")
        else:
            body = members[name]
            encoded = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode("ascii")
            require(digest == "sha256=" + encoded and size == str(len(body)),
                    "sounddevice RECORD bytes differ: " + name)
    return rows


def patched_sounddevice_wheel(wheel, patch):
    """Derive one exact unpublished wheel without importing or rebuilding it."""
    pin = AUDIO_MEMBERS["wheelhouse/" + SOUNDDEVICE_FILE]
    pinned(wheel, pin["bytes"], pin["sha256"])
    pinned(patch, *SOUNDDEVICE_PATCH_PIN)
    with zipfile.ZipFile(wheel) as archive:
        infos = archive.infolist()
        require(len(infos) == 8 and len({i.filename for i in infos}) == 8
                and all(not i.is_dir() and safe_zip_member(i) for i in infos),
                "sounddevice archive member set or paths differ")
        original = {i.filename: archive.read(i) for i in infos}  # also checks every CRC
    rows = verify_sounddevice_record(original)
    before = original["sounddevice.py"]
    require((len(before), hashlib.sha256(before).hexdigest()) == SOUNDDEVICE_SOURCE_BEFORE,
            "original sounddevice source differs")
    sections = patch_sections(Path(patch).read_bytes())
    require(set(sections) == {"sounddevice.py"}, "sounddevice patch path set differs")
    source = apply_text_hunks(before, sections["sounddevice.py"])
    require((len(source), hashlib.sha256(source).hexdigest()) == SOUNDDEVICE_SOURCE_AFTER,
            "patched sounddevice source differs")
    members = dict(original)
    members["sounddevice.py"] = source
    for row in rows:
        if row[0] == "sounddevice.py":
            row[1] = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(source).digest()).rstrip(b"=").decode("ascii")
            row[2] = str(len(source))
    record = "sounddevice-0.5.5.dist-info/RECORD"
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    members[record] = stream.getvalue().encode("utf-8")
    verify_sounddevice_record(members)
    changed = {name for name in members if members[name] != original[name]}
    require(changed == {"sounddevice.py", record}, "sounddevice patch changed another member")
    result = io.BytesIO()
    # Stored members and explicit ZIP metadata make the exact bytes independent
    # of host zlib versions, filesystem modes and local clocks.
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, members[name])
    body = result.getvalue()
    require((len(body), hashlib.sha256(body).hexdigest()) == SOUNDDEVICE_WHEEL_AFTER,
            "derived sounddevice wheel differs")
    proof = {
        "original_wheel": {"bytes": pin["bytes"], "sha256": pin["sha256"]},
        "derived_wheel": {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()},
        "patch": {"file": SOUNDDEVICE_PATCH_RELATIVE, "bytes": SOUNDDEVICE_PATCH_PIN[0],
                  "sha256": SOUNDDEVICE_PATCH_PIN[1]},
        "source_before": {"bytes": len(before), "sha256": hashlib.sha256(before).hexdigest()},
        "source_after": {"bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()},
        "changed_members": sorted(changed), "unchanged_member_count": 6,
        "metadata_version_dependencies_tags_and_license_unchanged": True,
        "original_and_derived_records_verified": True,
        "original_members": {n: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                             for n, b in sorted(original.items())},
        "derived_members": {n: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                            for n, b in sorted(members.items())},
        "scope": "Android loader fallback only after all existing find_library candidates return None",
        "native_loading_and_PortAudio_initialization_errors_preserved": True,
        "published": False,
    }
    return body, proof


def patch_catalogued_sounddevice(payload, original, patch, descriptor):
    """Preserve canonical original-wheel provenance while binding derived bytes."""
    catalog_path = payload / "bundled-wheels.json"
    raw = catalog_path.read_bytes()
    before = json_object(raw)
    require(descriptor == {"path": "bundled-wheels.json", "sha256": hashlib.sha256(raw).hexdigest()},
            "canonical audio catalog descriptor differs")
    verify_catalog_union(original, before, sounddevice_patched=False)
    wheel_path = contained(payload, "wheelhouse/" + SOUNDDEVICE_FILE)
    body, proof = patched_sounddevice_wheel(wheel_path, patch)
    after = json_object(raw)
    row = next(row for row in after["wheels"] if row["file"] == "wheelhouse/" + SOUNDDEVICE_FILE)
    original_row = dict(row)
    row.update(size=SOUNDDEVICE_WHEEL_AFTER[0], sha256=SOUNDDEVICE_WHEEL_AFTER[1])
    verify_catalog_union(original, after)
    require({k for k in row if row[k] != original_row[k]} == {"size", "sha256"},
            "derived sounddevice origin or selection changed")
    encoded = (json.dumps(after, indent=2, sort_keys=True) + "\n").encode("utf-8")
    proof.update(
        catalog_original_row=original_row, catalog_derived_row=dict(row),
        catalog_before_sha256=hashlib.sha256(raw).hexdigest(),
        catalog_after_sha256=hashlib.sha256(encoded).hexdigest(),
        original_registry_wheel_source_and_fingerprint_preserved=True,
        original_100_catalog_rows_preserved=True,
    )
    # These two files belong to this invocation; all inputs and all checks above
    # are complete before changing either. No canonical PM API or lock is edited.
    wheel_path.write_bytes(body)
    catalog_path.write_bytes(encoded)
    pinned(wheel_path, *SOUNDDEVICE_WHEEL_AFTER)
    return {"path": "bundled-wheels.json", "sha256": hashlib.sha256(encoded).hexdigest()}, after, proof


def verify_base_catalog(payload):
    pinned(payload / "bundled-wheels.json", 68318, CATALOG_SHA)
    catalog = json_object((payload / "bundled-wheels.json").read_bytes())
    rows = catalog["wheels"]
    require(len(rows) == 100 and len({r["file"] for r in rows}) == 100, "main catalog count differs")
    require({p.name for p in (payload / "wheelhouse").iterdir()} == {Path(r["file"]).name for r in rows},
            "main wheelhouse contains missing or extra entries")
    for row in rows:
        path = contained(payload, row["file"])
        pinned(path, row["size"], row["sha256"])
        wheel_members(path)
    for name, (size, digest) in SHARED_WHEELS.items():
        pinned(payload / "wheelhouse" / name, size, digest)
    return catalog


def verify_catalog_union(before, after, *, sounddevice_patched=True):
    old = {r["file"]: r for r in before["wheels"]}
    new = {r["file"]: r for r in after["wheels"]}
    require(len(old) == 100 and len(before["wheels"]) == 100, "base catalog is not the exact 100-row set")
    require(len(new) == 102 and len(after["wheels"]) == 102, "audio catalog must contain 102 unique rows")
    require(set(new) - set(old) == {"wheelhouse/" + n for n in NEW_WHEELS}, "audio catalog additions differ")
    require(all(new.get(name) == row for name, row in old.items()), "original catalog row changed")
    for name in NEW_WHEELS:
        row = new["wheelhouse/" + name]
        pin = AUDIO_MEMBERS["wheelhouse/" + name]
        expected = SOUNDDEVICE_WHEEL_AFTER if name == SOUNDDEVICE_FILE and sounddevice_patched else (pin["bytes"], pin["sha256"])
        require((row["size"], row["sha256"]) == expected, "new audio wheel identity differs")
        if name == SOUNDDEVICE_FILE:
            fingerprint = hashlib.sha256(json.dumps(SOUNDDEVICE_ORIGIN, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            require(row.get("name") == "sounddevice" and row.get("version") == "0.5.5"
                    and row.get("source") == SOUNDDEVICE_ORIGIN
                    and row.get("source_fingerprint") == fingerprint,
                    "sounddevice original wheel provenance differs")
    return {"original_rows": 100, "additional_rows": 2, "total_rows": 102, "original_rows_preserved": True}


def native_environment(payload, work):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "HERMES_", "__HERMES", "UV_", "PIP_", "GIT_"))
           and k not in ("VIRTUAL_ENV", "LD_LIBRARY_PATH", "_PYTHON_HOST_PLATFORM",
                         "CC", "CXX", "AR", "CFLAGS", "CXXFLAGS", "LDFLAGS", "CPATH", "LIBRARY_PATH")}
    directories = [payload / ("tools/" + tool) / PREFIX.relative_to("/") / "lib"
                   for tool in ("python", "node", "ffmpeg")]
    directories += [payload / "runtime-libs/lib", PREFIX / "lib"]
    env.update(PREFIX=str(PREFIX), LD_LIBRARY_PATH=":".join(map(str, directories)),
               HERMES_HOME=str(work / "home"), HERMES_RUNTIME_DIR=str(payload / "tools"),
               HERMES_INSTALL_ROOT=str(payload / "app"), HERMES_PYTHON_SRC_ROOT=str(payload / "app"),
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               XDG_CACHE_HOME=str(work / "cache"), TMPDIR=str(work / "tmp"),
               XDG_DATA_HOME=str(work / "data"), XDG_CONFIG_HOME=str(work / "config"), PATH=str(PREFIX / "bin") + ":/system/bin",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    for name in ("home", "cache", "tmp"):
        (work / name).mkdir(parents=True, exist_ok=True)
    return env


def native_identity(payload=None):
    require(sys.flags.isolated and sys.dont_write_bytecode, "invoke the bundled Python with -I -B")
    require(sys.implementation.name == "cpython" and sys.version_info[:3] == (3, 14, 6),
            "exact candidate CPython 3.14.6 is required")
    require(os.name == "posix" and sys.platform == "android"
            and platform.machine().lower() in ("aarch64", "arm64"), "native Android AArch64 is required")
    require(not os.environ.get("PYTHONHOME"), "PYTHONHOME must not substitute a runtime")
    if payload is not None:
        require(Path(sys.executable).resolve().is_relative_to(payload / "tools/python"),
                "worker interpreter does not belong to the owned payload")
        require(Path(sys.base_prefix).resolve().is_relative_to(payload / "tools/python"),
                "worker base prefix escaped the owned payload")
    return {"version": sys.version, "platform": sys.platform, "machine": platform.machine(),
            "executable": sys.executable, "base_prefix": sys.base_prefix}


def run_logged(command, evidence, name, *, env=None, cwd=None, timeout=600):
    if env is None:
        env = dict(os.environ)
        for key in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            env.pop(key, None)
    try:
        result = subprocess.run(command, env=env, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (evidence / (name + ".stdout.log")).write_bytes(exc.stdout or b"")
        (evidence / (name + ".stderr.log")).write_bytes(exc.stderr or b"")
        raise PreparationError(f"{name} timed out; inspect the retained partial raw logs") from exc
    (evidence / (name + ".stdout.log")).write_bytes(result.stdout)
    (evidence / (name + ".stderr.log")).write_bytes(result.stderr)
    require(result.returncode == 0, f"{name} failed with exit {result.returncode}; inspect the retained raw logs")
    return result


def canonical_modules(source):
    for name, (size, digest) in ASSEMBLY.items():
        pinned(source / name, size, digest)
    for name, relative in (("scripts", "scripts"), ("scripts.build", "scripts/build"),
                           ("scripts.bundles", "scripts/bundles")):
        require(name not in sys.modules, "canonical assembly namespace was already loaded")
        module = types.ModuleType(name)
        module.__path__ = [str(source / relative)]
        sys.modules[name] = module
    loaded = {}
    for name, relative in (("scripts.build.inputs", "scripts/build/inputs.py"),
                           ("scripts.build.launchers", "scripts/build/launchers.py"),
                           ("scripts.build.agent", "scripts/build/agent.py"),
                           ("scripts.bundles.payload", "scripts/bundles/payload.py")):
        spec = importlib.util.spec_from_file_location(name, source / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


def extract_opensles(archive, destination, work):
    pinned(archive, STUB_BYTES, STUB_SHA)
    with tempfile.TemporaryDirectory(prefix="official-wrapper-", dir=work) as temporary:
        run_logged(["dpkg-deb", "--extract", str(archive), temporary], work, "extract-opensles")
        members = [
            ("libOpenSLES.so", OPENSLES_BYTES, OPENSLES_SHA, destination),
            (PLATFORM_NAMESPACE_FILE, PLATFORM_NAMESPACE_BYTES, PLATFORM_NAMESPACE_SHA,
             destination.with_name(PLATFORM_NAMESPACE_FILE)),
        ]
        # The original wrapper directly needs its sibling namespace library.
        # Validate both original members and both new destinations before copying.
        for name, size, digest, target in members:
            source = Path(temporary) / PREFIX.relative_to("/") / "lib" / name
            require(not source.is_symlink(), "official audio member is a symlink: " + name)
            pinned(source, size, digest)
            require(not target.exists() and not target.is_symlink(),
                    "owned audio library destination already exists: " + name)
        for name, _size, _digest, target in members:
            shutil.copyfile(Path(temporary) / PREFIX.relative_to("/") / "lib" / name, target)
            target.chmod(0o644)
    return {"archive_sha256": STUB_SHA, "package": "libandroid-stub", "version": "30-2",
            "library_sha256": OPENSLES_SHA, "library_bytes": OPENSLES_BYTES,
            "source_url": STUB_URL, "system_framework": "/system/lib64/libOpenSLES.so",
            "namespace_library": {"file": PLATFORM_NAMESPACE_FILE,
                                  "bytes": PLATFORM_NAMESPACE_BYTES, "sha256": PLATFORM_NAMESPACE_SHA,
                                  "needed": ["libc.so", "libdl.so"]},
            "wrapper_needed": ["libc.so", "libdl.so", PLATFORM_NAMESPACE_FILE],
            "method": "Both exact official wrapper/namespace members extracted into owned payload; no dpkg installation."}


def canonical_export(source, out, payload, cache, extras):
    """Use PM's own frozen-export selection with offline=True, without acquiring tools."""
    from pm.environment import managed_environment
    from pm.bundled_wheels import interpreter_markers, load_catalog
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    python = Path(sys.base_prefix) / "bin/python3.14"
    require(python.is_file() and python.resolve().is_relative_to(payload / "tools/python"),
            "canonical export interpreter escaped the payload")
    engine = managed_environment(payload / "venv", python=python, cache=cache,
                                 env=os.environ, offline=True, explicit=True, realize=False)
    selection = engine._selection_args(source, extras=extras, groups=(),
                                       all_extras=False, no_default_groups=False)
    args = ["export", "--frozen", "--python", str(python), *selection,
            "--no-emit-local", "--no-hashes", "--no-annotate", "--no-header",
            "--format", "requirements-txt", "--output-file", str(out)]
    result = engine._run(args, cwd=source, timeout=300)
    require(result.returncode == 0, "canonical frozen export failed: " + result.stderr[-800:])
    markers = interpreter_markers(python, os.environ)
    catalog = load_catalog()
    require(catalog is not None, "canonical PM did not find its own catalog")
    raw = out.read_text(encoding="utf-8")
    selected = catalog.select(raw, source / "uv.lock", markers)
    required = set()
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        req = Requirement(line)
        if req.marker is None or req.marker.evaluate(markers):
            required.add(canonicalize_name(req.name))
    require(required == {w.name for w in selected}, "frozen graph has an unbundled or ambiguous dependency")
    by_name = {row["name"]: row for row in catalog.rows}
    return {name: by_name[name] for name in sorted(required)}


def verify_installed(site, rows, payload):
    """Bind every installed distribution and wheel-owned file to the frozen selection."""
    from importlib.metadata import distributions
    from packaging.utils import canonicalize_name
    expected = {name: row["version"] for name, row in rows.items()}
    found = {}
    for dist in distributions(path=[str(site)]):
        name = canonicalize_name(dist.metadata["Name"])
        require(name not in found, "duplicate installed distribution: " + name)
        found[name] = dist.version
    require(found == expected, "installed distributions differ from the canonical frozen export")
    checked = 0
    for name, row in rows.items():
        wheel = contained(payload, row["file"])
        pinned(wheel, row["size"], row["sha256"])
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.endswith(".dist-info/RECORD"):
                    continue
                require(safe_zip_member(member), "unsafe installed wheel member")
                relative = member.filename
                parts = relative.split("/")
                if parts[0].endswith(".data"):
                    require(len(parts) > 2 and parts[1] in ("purelib", "platlib"),
                            "wheel has a data installation scheme requiring explicit review: " + relative)
                    relative = "/".join(parts[2:])
                path = contained(site, relative)
                require(path.is_file() and not path.is_symlink(), "wheel-owned installed file is missing: " + relative)
                raw = archive.read(member)
                require(path.read_bytes() == raw, "installed wheel-owned file differs: " + relative)
                checked += 1
    return {"distributions": expected, "distribution_count": len(expected),
            "wheel_owned_files_checked": checked, "record_rewritten_by_uv": True}


def verified_packaged_tools(*, source_store: Path, target: str, lock=None):
    """Read the pinned Python/UV closure in the published flat payload layout.

    PM's build-cache verifier requires versioned store entry names. Published
    payloads instead record the fixed python/uv names through record_tools.
    Retain every other canonical identity, tree, link, binary and environment
    check without writing facts, healing modes, acquiring or executing tools.
    """
    from types import MappingProxyType
    from pm.build_operations import VerifiedTools, _copy_links
    from pm.filesystem import long_root, native
    from pm.install import InstalledPackage, _identity, _lockfile
    from pm.lock import Facts
    from pm.package import InstallError, StatePackage
    from pm.registry import walk
    from pm.store import tree_digest

    if target != TARGET:
        raise InstallError("tools", "packaged audio tool verification requires the pinned target")
    packages = walk(["python", "uv"], target=target)
    if (len(packages) != 2 or {package.name for package in packages} != {"python", "uv"}
            or any(isinstance(package, StatePackage) or getattr(package, "pin_only", False)
                   for package in packages)):
        raise InstallError("tools", "packaged audio tool closure changed")
    source_store = Path(source_store).resolve()
    if not (source_store / "facts.json").is_file():
        raise InstallError("tools", "packaged source facts are missing")
    source_store = long_root(source_store)
    facts = Facts(source_store / "facts.json", strict=True)
    lock = lock if lock is not None else _lockfile()
    entries, envs = {}, []
    for package in packages:
        name = package.name
        version, identity = lock.version(name), _identity(lock, name, target)
        if not version or identity is None:
            raise InstallError(name, "packaged tool source has no original lock identity")
        fact = facts.get(name)
        # These two flat names are part of the exact admitted .deb layout.
        entry = source_store / name
        if (not fact or fact.get("entry") != name
                or entry.is_symlink() or not entry.is_dir()
                or not entry.resolve().is_relative_to(source_store)
                or not facts.installed(name, version, source_store, identity)
                or tree_digest(entry) != fact.get("digest")):
            raise InstallError(name, "packaged tool source failed fact or tree verification")
        _copy_links(package, entry)
        binary, env = package.binary(entry, target), package.env(entry, target)
        if (binary is None or not binary.is_file()
                or not binary.resolve().is_relative_to(entry)
                or facts.env_for(name, source_store) != env):
            raise InstallError(name, "packaged tool source failed binary or environment verification")
        entries[name] = InstalledPackage(Path(native(entry)), version, Path(native(binary)))
        envs.append(env)
    return VerifiedTools(MappingProxyType(entries), tuple(envs))



TOOL_PYTHON_PREFIX = "tools/python/"
TOOL_STDLIB_PREFIX = TOOL_PYTHON_PREFIX + "data/data/com.termux/files/usr/lib/python3.14/"
MAX_GENERATED_CACHE_FILES = 512
MAX_GENERATED_CACHE_BYTES = 32 * 1024 * 1024


def record_tool_caches(payload, evidence, stage):
    """Record bounded derived-cache state around canonical assembly stages."""
    require(re.fullmatch(r"[0-9]{2}-[a-z-]+", stage) is not None, "invalid cache evidence stage")
    rows = inventory(payload / "tools/python")
    selected = {name: row for name, row in rows.items() if "__pycache__" in PurePosixPath(name).parts}
    files = [name for name, row in selected.items() if row["kind"] == "file"]
    require(len(files) <= MAX_GENERATED_CACHE_FILES
            and sum(selected[name]["bytes"] for name in files) <= MAX_GENERATED_CACHE_BYTES,
            "generated tool bytecode exceeds its evidence bound")
    for name in files:
        with (payload / "tools/python" / name).open("rb") as stream:
            selected[name] = {**selected[name], "header_hex": stream.read(16).hex()}
    origins = {}
    for name in ("pm.environment", "pm.bundled_wheels", "pm.runtime_stage"):
        module = sys.modules.get(name)
        filename = getattr(module, "__file__", None)
        if filename:
            path = Path(filename)
            origins[name] = {"path": str(path), "sha256": sha256(path)}
    record = {"schema_version": 1, "stage": stage, "cache_tag": sys.implementation.cache_tag,
              "python": sys.version, "dont_write_bytecode": sys.dont_write_bytecode,
              "environment_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
              "base_prefix": sys.base_prefix, "cache_files": len(files),
              "cache_entries": selected, "canonical_module_origins": origins}
    write_json(evidence / ("tool-cache-" + stage + ".json"), record)
    return record


def _matching_code(actual, expected):
    """Compare compiled code recursively without executing either code object."""
    if type(actual) is not types.CodeType or type(expected) is not types.CodeType:
        return False
    fields = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
              "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames",
              "co_filename", "co_name", "co_qualname", "co_firstlineno", "co_linetable",
              "co_exceptiontable", "co_freevars", "co_cellvars")
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        return False
    if len(actual.co_consts) != len(expected.co_consts):
        return False
    for left, right in zip(actual.co_consts, expected.co_consts):
        if type(left) is types.CodeType or type(right) is types.CodeType:
            if not _matching_code(left, right):
                return False
        elif type(left) is not type(right) or left != right:
            return False
    return True


def normalize_generated_tool_bytecode(payload, original, evidence):
    """Remove only newly derived, fully recompiled caches from this owned output.

    Canonical UV assembly can create stdlib caches: PM deliberately excludes
    __pycache__ from a tool's content digest. This normalization restores the
    stricter package byte inventory. It never removes baseline entries, accepts
    arbitrary cache payloads, changes source bytes, or relaxes the final oracle.
    """
    require(sys.implementation.name == "cpython" and sys.implementation.cache_tag == "cpython-314"
            and sys.version_info[:2] == (3, 14) and sys.pycache_prefix is None,
            "tool cache normalization requires the selected CPython 3.14 format")
    python_root = payload / "tools/python"
    require(python_root.is_dir() and not python_root.is_symlink()
            and python_root.resolve() == python_root.absolute(), "unowned Python cache root")
    before = {name: row for name, row in original.items() if name.startswith(TOOL_PYTHON_PREFIX)}
    actual = {TOOL_PYTHON_PREFIX + name: row for name, row in inventory(python_root).items()}
    require(before and all(actual.get(name) == row for name, row in before.items()),
            "baseline Python source, tool file, mode, or cache changed before normalization")
    additions = {name: row for name, row in actual.items() if name not in before}
    directories, files = [], []
    for name, row in additions.items():
        require(name.startswith(TOOL_STDLIB_PREFIX), "new Python output is outside the exact stdlib")
        relative = PurePosixPath(name)
        if row["kind"] == "directory":
            require(relative.name == "__pycache__"
                    and "__pycache__" not in relative.parent.parts
                    and before.get(relative.parent.as_posix(), {}).get("kind") == "directory",
                    "unreviewed new cache directory")
            directories.append(name)
        else:
            require(row["kind"] == "file" and relative.parent.name == "__pycache__"
                    and "__pycache__" not in relative.parent.parent.parts,
                    "unreviewed new cache file or symlink")
            files.append(name)
    require(len(files) <= MAX_GENERATED_CACHE_FILES
            and sum(additions[name]["bytes"] for name in files) <= MAX_GENERATED_CACHE_BYTES,
            "generated tool bytecode exceeds its normalization bound")
    records = []
    for name in sorted(files):
        row = additions[name]
        path = contained(payload, name)
        require(path.resolve() == path.absolute() and 16 < row["bytes"] <= 8 * 1024 * 1024,
                "uncontained or oversized derived bytecode")
        match = re.fullmatch(r"(.+)\.cpython-314(?:\.opt-([12]))?\.pyc", path.name)
        require(match is not None, "unreviewed CPython cache filename")
        optimization = int(match[2] or "0")
        source = path.parent.parent / (match[1] + ".py")
        source_name = source.relative_to(payload).as_posix()
        expected_source = before.get(source_name)
        require(expected_source is not None and expected_source["kind"] == "file"
                and source.resolve() == source.absolute(), "cache has no exact original regular source")
        source_raw = source.read_bytes()
        require(len(source_raw) == expected_source["bytes"]
                and hashlib.sha256(source_raw).hexdigest() == expected_source["sha256"],
                "cache source differs from the original package")
        expected_name = importlib.util.cache_from_source(
            str(source), optimization="" if optimization == 0 else str(optimization),
        )
        require(Path(expected_name) == path, "cache path is not the canonical path for its source")
        raw = path.read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                "derived cache changed during validation")
        require(raw[:4] == importlib.util.MAGIC_NUMBER, "derived cache uses foreign Python magic")
        flags = struct.unpack_from("<I", raw, 4)[0]
        require(flags in (0, 1, 3), "derived cache has invalid PEP 552 flags")
        if flags == 0:
            mtime, size = struct.unpack_from("<II", raw, 8)
            require(mtime == int(source.stat().st_mtime) & 0xffffffff
                    and size == len(source_raw) & 0xffffffff,
                    "derived cache timestamp/size does not match its source")
            header = {"mode": "timestamp", "mtime": mtime, "source_size": size}
        else:
            require(raw[8:16] == importlib.util.source_hash(source_raw),
                    "derived cache source hash does not match")
            header = {"mode": "checked-hash" if flags == 3 else "unchecked-hash",
                      "source_hash": raw[8:16].hex()}
        stream = io.BytesIO(raw[16:])
        try:
            actual_code = marshal.load(stream)
        except (EOFError, ValueError, TypeError) as exc:
            raise PreparationError("derived cache is not valid Python code") from exc
        require(stream.read(1) == b"", "derived cache contains trailing payload")
        fresh = compile(source_raw, str(source), "exec", dont_inherit=True, optimize=optimization)
        require(_matching_code(actual_code, fresh), "derived cache differs from a fresh source compile")
        records.append({"path": name, "bytes": len(raw), "sha256": row["sha256"],
                        "mode": row["mode"], "header_hex": raw[:16].hex(),
                        "header": header, "optimization": optimization,
                        "source": source_name, "source_bytes": len(source_raw),
                        "source_sha256": expected_source["sha256"],
                        "code_filename": actual_code.co_filename,
                        "fresh_compile_equal": True})
    # No removal begins until every new entry and every baseline entry passes.
    require(all(any(PurePosixPath(name).parent.as_posix() == directory for name in files)
                for directory in directories), "unexplained empty new cache directory")
    planned = {"schema_version": 1, "status": "validated-before-normalization",
               "scope": "newly derived CPython stdlib caches in this invocation's owned payload only",
               "python": sys.version, "cache_tag": sys.implementation.cache_tag,
               "magic_hex": importlib.util.MAGIC_NUMBER.hex(), "files": records,
               "directories": sorted(directories), "baseline_entries_removed": 0,
               "source_files_changed": 0, "original_python_inventory_sha256": inventory_sha(before)}
    write_json(evidence / "validated-generated-tool-bytecode.json", planned)
    for record in records:
        path = contained(payload, record["path"])
        saved = evidence / "generated-tool-bytecode" / record["path"]
        saved.parent.mkdir(parents=True, exist_ok=True)
        with saved.open("xb") as stream:
            stream.write(path.read_bytes())
        require(saved.stat().st_size == record["bytes"] and sha256(saved) == record["sha256"]
                and sha256(path) == record["sha256"], "cache changed before owned removal")
        path.unlink()
    for name in sorted(directories, key=lambda value: len(PurePosixPath(value).parts), reverse=True):
        contained(payload, name).rmdir()
    after = {TOOL_PYTHON_PREFIX + name: row for name, row in inventory(python_root).items()}
    require(after == before, "normalization did not restore every original Python entry exactly")
    result = {**planned, "status": "normalized",
              "removed_files": len(records), "removed_directories": len(directories),
              "final_python_inventory_sha256": inventory_sha(after),
              "exact_original_python_inventory_restored": True}
    write_json(evidence / "normalized-generated-tool-bytecode.json", result)
    return result


def bootstrap_worker(request):
    payload = Path(request["payload"])
    native_identity(payload)
    sys.path.insert(0, str(payload / "app"))
    import pm
    from pm.paths import repo_root
    require(repo_root().resolve() == payload / "app", "bootstrap imported another PM")
    verified_packaged_tools(source_store=payload / "tools", target=TARGET)
    record_tool_caches(payload, Path(request["evidence"]), "00-before-manager")
    manager = pm.stage_manager_runtime(
        python=Path(sys.executable), destination=payload / "pm-runtime",
        project=payload / "app/pm", offline=True, wheelhouse=payload / "wheelhouse",
        cache=Path(request["state"]) / "cache/pm-build",
    )
    record_tool_caches(payload, Path(request["evidence"]), "01-after-manager")
    run_logged([str(manager), "-I", "-B", str(Path(__file__).resolve()),
                "--application-worker", request["request_path"]],
               Path(request["evidence"]), "canonical-application-build",
               env=os.environ, timeout=1800)


def application_worker(request):
    payload, evidence, state = Path(request["payload"]), Path(request["evidence"]), Path(request["state"])
    native_identity(payload)
    sys.path.insert(0, str(payload / "app"))
    import pm
    from pm.bundled_wheels import write_catalog
    from pm.environment import managed_environment
    from pm.features import write_features
    from pm.lock import Facts
    from pm.packages import Venv
    from pm.paths import repo_root
    from pm.store import current_target
    require(repo_root().resolve() == payload / "app" and current_target() == TARGET, "wrong staged PM authority")
    record_tool_caches(payload, evidence, "02-application-entry")
    original = json_object((evidence / "original-bundled-wheels.json").read_bytes())
    descriptor = write_catalog(payload, wheelhouse=payload / "wheelhouse",
                               lock_paths=(payload / "app/uv.lock", payload / "app/pm/uv.lock"))
    descriptor, catalog, sounddevice_derivative = patch_catalogued_sounddevice(
        payload, original, Path(request["sounddevice_patch"]), descriptor)
    write_json(evidence / "sounddevice-android-derivative.json", sounddevice_derivative)
    union = verify_catalog_union(original, catalog)
    manifest = json_object((payload / "manifest.json").read_bytes())
    manifest["bundled_wheels"] = descriptor
    (payload / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    app_rows = canonical_export(payload / "app", evidence / "application-requirements.txt",
                                payload, state / "cache/export-app", EXTRAS)
    manager_rows = canonical_export(payload / "app/pm", evidence / "manager-requirements.txt",
                                    payload, state / "cache/export-manager", [])
    record_tool_caches(payload, evidence, "03-after-exports")
    python = contained(payload, manifest["runtime"]["storePython"])
    require(python.resolve().is_relative_to(payload / "tools/python"), "base interpreter escaped the owned payload")
    target = payload / "venv"
    executable = pm.build_environment(
        source=payload / "app", out=target, python=python, cache=state / "cache/application-build",
        env=os.environ, extras=EXTRAS, groups=(), all_extras=False,
        no_install_project=True, frozen=True, sealed=True, offline=True, explicit=True, timeout=1500,
    )
    record_tool_caches(payload, evidence, "04-after-application-build")
    require(Path(executable).parent.parent == target, "canonical PM returned another environment")
    site = target / "lib/python3.14/site-packages"
    manager_site = payload / "pm-runtime/lib/python3.14/site-packages"
    app_check = verify_installed(site, app_rows, payload)
    manager_check = verify_installed(manager_site, manager_rows, payload)
    modules = canonical_modules(Path(request["assembly"]))
    seal = modules["scripts.bundles.payload"]
    marker = seal.seal_pm_runtime(payload, python)
    stamp = Venv(payload / "app").expected_stamp(EXTRAS, plugin_dirs=[],
                                               bundled_wheels_sha256=descriptor["sha256"])
    facts_before = json_object((payload / "tools/facts.json").read_bytes())
    Facts(payload / "tools/facts.json").record_state("venv", stamp, EXTRAS)
    facts_after = json_object((payload / "tools/facts.json").read_bytes())
    # Only canonical venv selection may change in this output-owned tools metadata.
    require({k: v for k, v in facts_before.items() if k != "packages"} ==
            {k: v for k, v in facts_after.items() if k != "packages"}
            and {k: v for k, v in facts_before["packages"].items() if k != "venv"} ==
                {k: v for k, v in facts_after["packages"].items() if k != "venv"}
            and facts_after["packages"]["venv"] == {"stamp": stamp, "extras": EXTRAS},
            "canonical selection changed a tool fact or failed to record the new venv")
    inputs = modules["scripts.build.inputs"]
    manifest = modules["scripts.build.agent"].assemble(inputs.AgentInputs(
        project=payload / "app/pyproject.toml", code=payload / "app", repo="app",
        placement="contained", target=TARGET, python=python, site_packages=site,
        environment=target, pm_runtime=payload / "pm-runtime", tools=payload / "tools",
        resources={name: payload / "app" / name for name in inputs.RESOURCE_ENV},
        stamp=payload / "app/install-stamp.json", features=write_features(EXTRAS, payload),
    ), payload)
    manifest["bundled_wheels"] = descriptor
    (payload / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Assembly writes the source-layout metadata and source binding through its own API.
    require((site / "hermes-agent.pth").read_text().strip() ==
            Path(os.path.relpath(payload / "app", site)).as_posix(), "canonical source binding differs")
    require((payload / "pm-runtime" / marker["python"]).resolve() == python.resolve(), "PM runtime interpreter differs")
    require(Venv(payload / "app").expected_stamp(EXTRAS, plugin_dirs=[],
                                               bundled_wheels_sha256=descriptor["sha256"]) == stamp,
            "final canonical dependency selection differs")
    record_tool_caches(payload, evidence, "05-after-assembly")
    original_payload = json_object((evidence / "original-payload-inventory.json").read_bytes())["files"]
    normalization = normalize_generated_tool_bytecode(payload, original_payload, evidence)
    verified_packaged_tools(source_store=payload / "tools", target=TARGET)
    record_tool_caches(payload, evidence, "06-after-normalization")
    write_json(evidence / "canonical-build.json", {
        "status": "passed", "target": TARGET, "extras": EXTRAS, "catalog": descriptor,
        "catalog_union": union, "application": app_check, "manager": manager_check,
        "sounddevice_derivative": sounddevice_derivative,
        "pm_runtime_marker": marker, "selection_stamp": stamp,
        "final_payload": str(payload), "interpreter": native_identity(payload),
        "application_built_fresh": True, "manager_built_fresh": True,
        "generated_tool_bytecode": normalization,
        "canonical_api": "pm.stage_manager_runtime + pm.build_environment + canonical agent assembly/seal_pm_runtime",
        "build_environment_arguments": {"frozen": True, "offline": True, "explicit": True,
                                       "sealed": True, "no_install_project": True, "all_extras": False},
        "project_binding": "Canonical agent source-layout .dist-info and hermes-agent.pth",
        "runtime_count_policy": "102 catalog files; only each canonical frozen export belongs in its own runtime.",
    })


def allowed_changes(before, after):
    """Reject any change outside the deliberately owned staging surface."""
    exact = {"manifest.json", "bundled-wheels.json", "enabled-features.json", "tools/facts.json", "native-wheels.json"}
    exact.update("app/" + p for p in SOURCE_FILES)
    exact.update("wheelhouse/" + p for p in NEW_WHEELS)
    exact.update("runtime-libs/lib/" + p for p in [*PORTAUDIO_FILES, "libOpenSLES.so", PLATFORM_NAMESPACE_FILE])
    changed = {}
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        require(name in exact or name.startswith(("venv/", "pm-runtime/", "bin/"))
                or name in ("venv", "pm-runtime", "bin"),
                "unreviewed staged payload change: " + name)
        changed[name] = {"before": before.get(name), "after": after.get(name)}
    for name, row in before.items():
        if name.startswith("wheelhouse/"):
            require(after.get(name) == row, "original wheel bytes or mode changed")
        if name.startswith("tools/") and name != "tools/facts.json":
            require(after.get(name) == row, "original bundled tool changed")
        if name.startswith("runtime-libs/"):
            require(after.get(name) == row, "original runtime library changed")
    return changed


def verify_links(payload, original=None):
    """Validate working links and separately report the exact inherited doc gap."""
    payload = Path(payload)
    rows = inventory(payload)
    root = payload.resolve()
    links, missing_documentation = {}, {}
    for name, row in rows.items():
        if row["kind"] != "symlink":
            continue
        path = payload / name
        require(not os.path.isabs(row["target"]), "payload link is absolute: " + name)
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise PreparationError("payload link cannot be resolved: " + name) from exc
        require(resolved.is_relative_to(root), "payload link is not contained: " + name)
        if path.exists():
            links[name] = row["target"]
            continue

        pin = BASELINE_MISSING_DOCUMENTATION_LINK
        require(name == pin["path"] and original is not None,
                "payload link target is missing: " + name)
        require(inventory_sha(original) == pin["original_inventory_sha256"],
                "baseline missing documentation source inventory differs")
        require(original.get(name) == row and row["target"] == pin["target"],
                "baseline missing documentation link changed")
        destination = root / pin["missing_destination"]
        require(pin["missing_destination"] not in original
                and pin["missing_destination"] not in rows
                and resolved == destination and destination.resolve() == destination
                and not destination.exists() and not destination.is_symlink(),
                "baseline missing documentation destination differs")
        license_pin = pin["preserved_license"]
        license_row = rows.get(license_pin["path"])
        require(license_row is not None and license_row == original.get(license_pin["path"])
                and license_row["kind"] == "file"
                and license_row["bytes"] == license_pin["bytes"]
                and license_row["sha256"] == license_pin["sha256"],
                "baseline preserved license differs")
        pinned(payload / license_pin["path"], license_pin["bytes"], license_pin["sha256"])
        missing_documentation[name] = {
            "target": row["target"],
            "missing_destination": pin["missing_destination"],
            "status": "preexisting-missing-documentation-target",
            "working": False,
            "original_link_preserved": True,
            "original_inventory_sha256": pin["original_inventory_sha256"],
            "preserved_license": dict(license_pin),
        }
    return {"contained_links": links, "baseline_missing_documentation_links": missing_documentation}


def prepare(options):
    native_identity()
    candidate, audio, patch = options.candidate_dir.resolve(), options.audio_inputs.resolve(), options.patch.resolve()
    marker_patch = Path(__file__).resolve().parents[1] / MARKER_PATCH_RELATIVE
    sounddevice_patch = Path(__file__).resolve().parents[1] / SOUNDDEVICE_PATCH_RELATIVE
    out = fresh_output(options.out, (candidate, audio, patch, marker_patch, sounddevice_patch, INSTALLED))
    candidate_receipt = verify_candidate(candidate)
    pinned(patch, PATCH_BYTES, PATCH_SHA)
    pinned(marker_patch, MARKER_PATCH_BYTES, MARKER_PATCH_SHA)
    pinned(sounddevice_patch, *SOUNDDEVICE_PATCH_PIN)
    verify_audio_archive(audio / AUDIO_ARCHIVE)
    pinned(audio / STUB_FILE, STUB_BYTES, STUB_SHA)
    for name, (size, digest) in ASSEMBLY.items():
        pinned(audio / "assembly" / name, size, digest)
    input_before = {"candidate": inventory(candidate), "audio": inventory(audio), "patch_sha256": sha256(patch),
                    "supplemental_patch_sha256": sha256(marker_patch),
                    "sounddevice_patch_sha256": sha256(sounddevice_patch)}
    installed_before = inventory(INSTALLED) if INSTALLED.is_dir() else None
    out.mkdir(parents=True)  # Exclusive ownership begins here; never move this final path.
    evidence, state, payload = out / "evidence", out / "state", out / "payload"
    evidence.mkdir()
    state.mkdir()
    status = {"schema_version": 1, "status": "preparing", "published": False, "microphone_accessed": False,
              "final_path": str(out), "candidate": candidate_receipt,
              "preparer_sha256": sha256(Path(__file__)),
              "probe_sha256": sha256(Path(__file__).with_name("compatibility_probe_audio_hermes.py"))}
    try:
        with tempfile.TemporaryDirectory(prefix="candidate-extract-", dir=out) as temporary:
            run_logged(["dpkg-deb", "--extract", str(candidate / candidate_receipt["package"]["file"]), temporary],
                       evidence, "extract-candidate", timeout=300)
            extracted = Path(temporary) / INSTALLED.relative_to("/")
            require(extracted.is_dir(), "candidate has no canonical payload")
            extracted.rename(payload)  # Before either new environment is built.
        before = inventory(payload)
        write_json(evidence / "original-payload-inventory.json", {"files": before})
        original = verify_base_catalog(payload)
        shutil.copyfile(payload / "bundled-wheels.json", evidence / "original-bundled-wheels.json")
        for name, digest in (("app/uv.lock", UV_LOCK_SHA), ("app/pm/lock.json", PM_LOCK_SHA),
                             ("app/pyproject.toml", PYPROJECT_SHA)):
            require(sha256(payload / name) == digest, "candidate source lock or project differs")
        source = patch_app(payload / "app", patch)
        source.update(patch_marker_probe(payload / "app", marker_patch))
        unpack = out / "verified-audio"
        unpack.mkdir()
        verify_audio_archive(audio / AUDIO_ARCHIVE, unpack)
        # Keep the candidate's cffi wheel; a different ZIP timestamp must not replace it.
        main_cffi = payload / "wheelhouse" / next(n for n in SHARED_WHEELS if n.startswith("cffi-"))
        old_cffi = unpack / "wheelhouse" / main_cffi.name
        cffi_members = wheel_members(main_cffi)
        require(cffi_members == wheel_members(old_cffi), "main/audio cffi wheel payload members differ; review required")
        for name in NEW_WHEELS:
            target = payload / "wheelhouse" / name
            require(not target.exists(), "audio wheel collides with the base catalog")
            shutil.copyfile(unpack / "wheelhouse" / name, target)
            target.chmod(0o644)
        for name in PORTAUDIO_FILES:
            target = payload / "runtime-libs/lib" / name
            require(not target.exists() and not target.is_symlink(), "PortAudio collides with a base runtime library")
            shutil.copyfile(unpack / "added-runtime-libs" / name, target)
            target.chmod(0o644)
        opensles = extract_opensles(audio / STUB_FILE, payload / "runtime-libs/lib/libOpenSLES.so", evidence)
        native_wheels = json.loads((payload / "native-wheels.json").read_bytes())
        require(isinstance(native_wheels, list) and all(isinstance(n, str) for n in native_wheels)
                and len(set(native_wheels)) == len(native_wheels) and "numpy" not in native_wheels,
                "original native wheel list differs")
        (payload / "native-wheels.json").write_text(json.dumps([*native_wheels, "numpy"]) + "\n", encoding="utf-8")
        manifest = json_object((payload / "manifest.json").read_bytes())
        python = contained(payload, manifest["runtime"]["storePython"])
        require(python.resolve().is_relative_to(payload / "tools/python"), "candidate interpreter escapes the payload")
        # These are copies created by this invocation, never the input/installed environments.
        for name in ("venv", "pm-runtime"):
            root = payload / name
            require(root.is_dir() and not root.is_symlink(), "candidate runtime is missing or symlinked")
            shutil.rmtree(root)
        request = {"payload": str(payload), "state": str(state), "evidence": str(evidence),
                   "assembly": str(audio / "assembly"), "request_path": str(evidence / "build-request.json"),
                   "sounddevice_patch": str(sounddevice_patch)}
        write_json(Path(request["request_path"]), request)
        env = native_environment(payload, state)
        run_logged([str(python), "-I", "-B", str(Path(__file__).resolve()),
                    "--bootstrap-worker", request["request_path"]], evidence, "canonical-preparation",
                   env=env, timeout=2100)
        after = inventory(payload)
        write_json(evidence / "post-build-payload-inventory.json", {"files": after})
        changes = allowed_changes(before, after)
        link_report = verify_links(payload, before)
        write_json(evidence / "payload-links.json", link_report)
        gate = json_object((evidence / "canonical-build.json").read_bytes())
        require(gate["status"] == "passed" and gate["catalog_union"]["total_rows"] == 102, "canonical build did not pass")
        require(input_before == {"candidate": inventory(candidate), "audio": inventory(audio), "patch_sha256": sha256(patch),
                    "supplemental_patch_sha256": sha256(marker_patch),
                    "sounddevice_patch_sha256": sha256(sounddevice_patch)},
                "reconstruction inputs changed during preparation")
        require(installed_before == (inventory(INSTALLED) if INSTALLED.is_dir() else None),
                "installed payload changed during preparation")
        write_json(evidence / "prepared-payload-inventory.json", {"files": after})
        # This entrypoint always owns its profile/cache and uses the canonical payload launcher.
        launcher = (
            "#!/data/data/com.termux/files/usr/bin/sh\nset -eu\n"
            'root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
            'unset HERMES_INSTALL_ROOT HERMES_RUNTIME_DIR HERMES_PYTHON HERMES_PYTHON_SRC_ROOT __HERMES_ACTIVATED PYTHONHOME PYTHONPATH VIRTUAL_ENV\n'
            'export HERMES_HOME="$root/state/home"\n'
            'export XDG_CACHE_HOME="$root/state/cache"\n'
            'export XDG_DATA_HOME="$root/state/data"\n'
            'export XDG_CONFIG_HOME="$root/state/config"\n'
            'exec "$root/payload/bin/hermes" "$@"\n'
        )
        (out / "run-hermes").write_text(launcher, encoding="utf-8")
        (out / "run-hermes").chmod(0o755)
        status.update(status="prepared-environment", preparation_integrity="passed",
                      native_audio_initialization="not-probed", physical_vad="not-tested",
                      source_patch={"sha256": PATCH_SHA, "bytes": PATCH_BYTES, "applied_source_files": source,
                                    "production_paths": sorted(PRODUCTION_FILES),
                                    "supplemental_patch": {"file": MARKER_PATCH_RELATIVE,
                                                           "bytes": MARKER_PATCH_BYTES,
                                                           "sha256": MARKER_PATCH_SHA,
                                                           "source_before": MARKER_SOURCE_BEFORE,
                                                           "source_after": MARKER_SOURCE_AFTER},
                                    "audio_patch_source_reference": {"baseline": "f49c77b666cef7fd5235cdd786556908527b532e",
                                                              "replay": "aa90e9a6eca74835dacc2dc55f376bddfd499c25"}},
                      catalog=gate["catalog"], extras=EXTRAS, canonical_build=gate,
                      sounddevice_derivative=gate["sounddevice_derivative"],
                      original_inventory_sha256=inventory_sha(before),
                      prepared_inventory_sha256=inventory_sha(after),
                      payload_changes=changes, contained_links=link_report["contained_links"],
                      baseline_missing_documentation_links=link_report["baseline_missing_documentation_links"],
                      generated_tool_bytecode=gate["generated_tool_bytecode"],
                      cffi_reuse={"main_wheel_sha256": sha256(main_cffi), "audio_wheel_sha256": sha256(old_cffi),
                                 "uncompressed_members_identical": len(cffi_members)},
                      runtime_additions={"portaudio_sha256": PORTAUDIO_SHA, "opensles": opensles},
                      installed_payload_preserved=True, reconstruction_inputs_preserved=True,
                      phone_reconstruction="Run the same preparer on native Termux at the desired fresh final path; do not copy the CI venv.",
                      launch="./run-hermes; isolated profile rooted at this output's state/home")
        write_json(out / "audio-environment-receipt.json", status)
        return status
    except BaseException as exc:
        status.update(status="failed", failure_type=type(exc).__name__, failure=str(exc),
                      physical_vad="not-tested", native_audio_initialization="not-probed")
        write_json(out / "audio-environment-failure.json", status)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("fetch-inputs", "prepare"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--audio-inputs", type=Path)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--bootstrap-worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--application-worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.bootstrap_worker:
            bootstrap_worker(json_object(args.bootstrap_worker.read_bytes()))
        elif args.application_worker:
            application_worker(json_object(args.application_worker.read_bytes()))
        elif args.mode == "fetch-inputs":
            require(args.out is not None, "--out is required")
            fetch_inputs(args.out)
        else:
            require(args.mode == "prepare" and all((args.out, args.candidate_dir, args.audio_inputs, args.patch)),
                    "prepare needs --out, --candidate-dir, --audio-inputs and --patch")
            prepare(args)
    except (PreparationError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("Audio environment preparation failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
