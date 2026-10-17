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
