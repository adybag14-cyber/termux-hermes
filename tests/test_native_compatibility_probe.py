"""Frozen graph selection must retain shared and requested-extra dependencies."""
from copy import deepcopy

import pytest

from scripts.probe_native_compatibility import locked_closure

ANDROID = {
    "implementation_name": "cpython", "implementation_version": "3.14.6",
    "os_name": "posix", "platform_machine": "aarch64", "platform_release": "",
    "platform_system": "Linux", "platform_version": "", "python_version": "3.14",
    "python_full_version": "3.14.6", "sys_platform": "android",
    "platform_python_implementation": "CPython", "extra": "",
}


def package(name, **kwargs):
    return {"name": name, "version": "1.0", "source": {"registry": "https://pypi.org/simple"}, **kwargs}


def lock_fixture():
    matrix = [{"name": n, "marker": "sys_platform == 'android' or sys_platform == 'linux'"}
              for n in ("aiohttp", "aiohttp-socks", "aiosqlite", "asyncpg")]
    matrix.append({"name": "mautrix", "extra": ["encryption"]})
    return {"package": [
        package("hermes-agent", dependencies=[{"name": "unrelated-core"}, {"name": "nemo-relay"}],
                **{"optional-dependencies": {"matrix": matrix, "uvloop": [{"name": "uvloop"}]}}),
        package("unrelated-core"),
        package("nemo-relay"),
        package("uvloop"),
        package("aiohttp", dependencies=[{"name": "shared"}]),
        package("aiohttp-socks"),
        package("aiosqlite"),
        package("asyncpg"),
        package("mautrix", dependencies=[{"name": "shared"}], **{"optional-dependencies": {
            "encryption": [{"name": "python-olm"}, {"name": "pycryptodome"}],
            "unselected": [{"name": "not-selected"}],
        }}),
        package("python-olm", dependencies=[{"name": "cffi"}]),
        package("pycryptodome"),
        package("shared"),
        package("cffi"),
        package("not-selected"),
    ]}


def test_matrix_closure_preserves_encryption_and_shared_deps_without_whole_core():
    graph = locked_closure(lock_fixture(), "matrix", ANDROID)
    assert set(graph) == {"aiohttp", "aiohttp-socks", "aiosqlite", "asyncpg",
                          "mautrix", "python-olm", "pycryptodome", "cffi", "shared"}


def test_nemo_probe_starts_at_its_core_edge_without_other_core_packages():
    assert list(locked_closure(lock_fixture(), "nemo", ANDROID)) == ["nemo-relay"]


def test_excluded_group_fails_instead_of_reporting_empty_success():
    lock = lock_fixture()
    lock["package"][0]["optional-dependencies"]["uvloop"][0]["marker"] = "sys_platform != 'android'"
    with pytest.raises(ValueError, match="target-excluded"):
        locked_closure(lock, "uvloop", ANDROID)


def test_missing_encryption_subgraph_is_rejected():
    lock = lock_fixture()
    lock["package"][0]["optional-dependencies"]["matrix"][-1].pop("extra")
    with pytest.raises(ValueError, match="incomplete"):
        locked_closure(lock, "matrix", ANDROID)


def test_ambiguous_versions_do_not_silently_take_last_lock_row():
    lock = lock_fixture()
    other = package("uvloop")
    other["version"] = "2.0"
    lock["package"].append(other)
    with pytest.raises(ValueError, match="Ambiguous"):
        locked_closure(lock, "uvloop", ANDROID)


def test_resolution_markers_select_actual_android_variant():
    lock = lock_fixture()
    uvloop = next(p for p in lock["package"] if p["name"] == "uvloop")
    uvloop["resolution-markers"] = ["sys_platform == 'android'"]
    other = deepcopy(uvloop)
    other["version"] = "2.0"
    other["resolution-markers"] = ["sys_platform != 'android'"]
    lock["package"].append(other)
    assert locked_closure(lock, "uvloop", ANDROID)["uvloop"]["version"] == "1.0"


def test_audio_probe_uses_audio_io_extra_and_preserves_cffi_transitive_dependency():
    lock = lock_fixture()
    lock["package"][0]["optional-dependencies"]["audio-io"] = [
        {"name": "numpy"}, {"name": "sounddevice"},
    ]
    lock["package"].extend([
        package("numpy"), package("sounddevice", dependencies=[{"name": "cffi"}]), package("pycparser"),
    ])
    next(p for p in lock["package"] if p["name"] == "cffi")["dependencies"] = [{"name": "pycparser"}]
    assert set(locked_closure(lock, "audio", ANDROID)) == {"numpy", "sounddevice", "cffi", "pycparser"}


@pytest.mark.parametrize("message, expected", [
    ('dlopen failed: library "libOpenSLES.so" not found', "environment-limited"),
    ("libOpenSLES.so: cannot open shared object file: No such file or directory", "environment-limited"),
    ("PortAudio library not found", "failed"),
    ('cannot locate symbol "new_function" referenced by "libOpenSLES.so"', "failed"),
    ("Error initializing PortAudio: Internal PortAudio error", "failed"),
    ("Error initializing PortAudio: Unanticipated host error [PaErrorCode -9999]: Initializing engine failed", "failed"),
])
def test_only_missing_android_audio_library_is_environment_limited(message, expected):
    from scripts.probe_native_compatibility import audio_failure_status
    assert audio_failure_status(OSError(message)) == expected


def test_direct_portaudio_runtime_library_dependencies_are_accounted_for(tmp_path, monkeypatch):
    from scripts.probe_native_compatibility import inspect_native_linkage

    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "numpy-core.so").write_bytes(b"\x7fELFfixture")
    payload = tmp_path / "payload"
    (payload / "runtime-libs").mkdir(parents=True)
    (payload / "runtime-libs" / "libc++_shared.so").write_bytes(b"fixture")
    added = tmp_path / "added-runtime-libs"
    added.mkdir()
    (added / "libportaudio.so").write_bytes(b"\x7fELFfixture")

    def patchelf(args, **kwargs):
        if args[1] == "--print-rpath":
            return ""
        if args[-1].endswith("libportaudio.so"):
            return "libOpenSLES.so\nlibc++_shared.so\n"
        return "libc.so\nlibunexpected-compiler-runtime.so\n"

    monkeypatch.setattr("scripts.probe_native_compatibility.subprocess.check_output", patchelf)
    result = inspect_native_linkage(environment, payload, added)
    assert result["undeclared_runtime_libraries"] == ["libunexpected-compiler-runtime.so"]
    portaudio = next(row for row in result["extensions"] if row["extension"] == "added-runtime-libs/libportaudio.so")
    assert portaudio["needed"]["libOpenSLES.so"]["kind"] == "android-system-abi"
    assert portaudio["needed"]["libc++_shared.so"]["kind"] == "original-payload"
    assert [row["name"] for row in result["declared_added_runtime_libraries"]] == ["libportaudio.so"]


def test_audio_map_evidence_selects_only_loaded_audio_objects():
    from scripts.probe_native_compatibility import audio_mapped_libraries

    maps = "\n".join([
        "100-200 r-xp 0000 00:00 1 /data/lib/libportaudio.so.2.0.0",
        "200-300 r--p 0000 00:00 1 /data/lib/libportaudio.so.2.0.0",
        "300-400 r-xp 0000 00:00 2 /data/lib/libOpenSLES.so",
        "400-500 r-xp 0000 00:00 3 /system/lib64/libOpenSLES.so",
        "500-600 r-xp 0000 00:00 4 /private/unrelated.so",
        "600-700 rw-p 0000 00:00 0 [heap]",
    ])
    assert audio_mapped_libraries(maps) == [
        "/data/lib/libOpenSLES.so", "/data/lib/libportaudio.so.2.0.0", "/system/lib64/libOpenSLES.so",
    ]


def test_audio_host_evidence_reports_only_fixed_framework_and_service_observations(tmp_path):
    from scripts.probe_native_compatibility import android_audio_host

    (tmp_path / "dev").mkdir()
    (tmp_path / "dev/binder").write_text("regular fixture, not a binder device")
    (tmp_path / "system/bin").mkdir(parents=True)
    (tmp_path / "system/bin/audioserver").write_text("fixture")
    proc = tmp_path / "proc"
    for pid, name in (("1", "audioserver"), ("2", "servicemanager"), ("3", "private-app")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "comm").write_text(name + "\n")
    result = android_audio_host(root=tmp_path, proc=proc)
    assert result["paths"]["/dev/binder"] == {"exists": True, "character_device": False}
    assert result["paths"]["/system/lib64/libOpenSLES.so"] == {"exists": False}
    assert result["audio_service_process_names"] == ["audioserver", "servicemanager"]
    assert "private-app" not in str(result)


def test_audio_initialization_failure_keeps_real_object_hash_and_origin_evidence(tmp_path, monkeypatch):
    import hashlib
    import json
    import subprocess
    from scripts import probe_native_compatibility as probe

    library = tmp_path / "libOpenSLES.so"
    library.write_bytes(b"exact mapped object fixture")
    maps = tmp_path / "maps"
    maps.write_text("fixture map")
    out = tmp_path / "audio-host.json"
    held = object()
    monkeypatch.setattr(probe, "load_audio_for_evidence",
                        lambda: ({"ctypes_dlopen": "loaded", "requested_library": "libportaudio.so"}, held))
    monkeypatch.setattr(probe, "android_audio_host", lambda: {"paths": {}, "audio_service_process_names": []})
    monkeypatch.setattr(probe, "audio_mapped_libraries", lambda _: [str(library)])
    monkeypatch.setenv("LD_LIBRARY_PATH", "parent-python-libraries")

    def package_owner(args, **kwargs):
        assert args == ["dpkg-query", "-S", str(library)]
        assert "LD_LIBRARY_PATH" not in kwargs["env"]
        return subprocess.CompletedProcess(args, 0, "libandroid-stub: " + str(library) + "\n", "")

    monkeypatch.setattr(probe.subprocess, "run", package_owner)
    write_evidence = probe.write_audio_host_evidence
    monkeypatch.setattr(probe, "write_audio_host_evidence",
                        lambda path, load: write_evidence(path, load, maps=maps))

    def initialize():
        raise RuntimeError("Error initializing PortAudio: Initializing engine failed")

    monkeypatch.setattr(probe, "_inspect_audio_devices", initialize)
    with pytest.raises(RuntimeError, match="Initializing engine failed"):
        probe.inspect_audio_devices(out)
    evidence = json.loads(out.read_text())
    assert evidence["ctypes_dlopen"] == "loaded"
    assert evidence["libraries"] == [{
        "path": str(library), "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "size": library.stat().st_size, "package_query_exit": 0,
        "package_owner": "libandroid-stub: " + str(library),
    }]
    assert probe.os.environ["LD_LIBRARY_PATH"] == "parent-python-libraries"
    assert evidence["hardware_capture_tested"] is False


def test_component_metadata_records_checkout_instead_of_workflow_merge_commit(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    import subprocess
    import sys

    script = (Path(__file__).resolve().parents[1] / "scripts/probe_native_compatibility.sh").read_text(encoding="utf-8")
    invocation = '''python3 - "$out" "$group" "$TERMUX_IMAGE" "$deb_sha" "$packaging" <<'PY'
'''
    program = script.split(invocation, 1)[1].split("\nPY\n", 1)[0]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run([
        "git", "-C", str(checkout), "-c", "user.name=Provenance fixture",
        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "--allow-empty", "-qm", "fixture",
    ], check=True)
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    workflow_merge = "f" * 40
    assert head != workflow_merge
    monkeypatch.setenv("GITHUB_SHA", workflow_merge)
    out = tmp_path / "evidence"
    out.mkdir()
    # Execute the actual shell-owned metadata block away from the checkout.
    subprocess.run([
        sys.executable, "-c", program, str(out), "audio",
        "termux/termux-docker@sha256:" + "a" * 64, "b" * 64, str(checkout),
    ], cwd=tmp_path, check=True)
    record = json.loads((out / "PROBE-INPUTS.json").read_text(encoding="utf-8"))
    assert record["packaging_commit"] == head
    assert record["workflow_ref_commit"] == workflow_merge
