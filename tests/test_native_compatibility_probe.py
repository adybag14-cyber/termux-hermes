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
