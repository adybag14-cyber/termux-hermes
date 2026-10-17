"""Host negative controls for the native oracle, never a claim of native execution."""
from __future__ import annotations

import base64
import csv
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import sysconfig
from types import FunctionType, SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_components_tested", ROOT / "scripts/compatibility_probe_neutts_native.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_exact_no_download_apt_plan():
    probe.validate_apt_plan("Inst clang (21.1.8-3 Termux)\nInst cmake (4.4.4 Termux)\n",
                            ["clang", "cmake"])


@pytest.mark.parametrize("plan", [
    "Inst clang (21)\nInst cmake (4)\nInst unrelated (99)\n",
    "Inst clang (21)\n",
    "Inst clang (21)\nInst cmake (4)\nRemv python [3.14]\n",
    "Inst clang (21)\nInst clang (21)\nInst cmake (4)\n",
])
def test_unreviewed_apt_change_or_omission_fails(plan):
    with pytest.raises(probe.ProbeError):
        probe.validate_apt_plan(plan, ["clang", "cmake"])


@pytest.mark.parametrize("name,mode", [
    ("../outside", stat.S_IFREG), ("/absolute", stat.S_IFREG),
    ("x\\y", stat.S_IFREG), ("x", stat.S_IFLNK),
])
def test_unsafe_built_wheel_paths_fail(name, mode):
    info = zipfile.ZipInfo(name)
    info.external_attr = (mode | 0o644) << 16
    with pytest.raises(probe.ProbeError):
        probe.safe_wheel_path(info)


def fake_numba_wheel(tmp_path, *, tag="cp314-cp314-android_24_arm64_v8a",
                     machine=183, extra_native=None, corrupt_record=False):
    path = tmp_path / ("numba-0.67.0-" + tag + ".whl")
    header = bytearray(64)
    header[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", header, 18, machine)
    prefix = "numba-0.67.0.dist-info"
    files = {
        "numba/np/ufunc/workqueue.cpython-314-aarch64-linux-android.so": bytes(header),
        prefix + "/METADATA": b"Metadata-Version: 2.1\nName: numba\nVersion: 0.67.0\n"
                               b"Requires-Dist: llvmlite<0.50,>=0.49.0dev0\n"
                               b"Requires-Dist: numpy<2.6,>=1.22\n\n",
        prefix + "/WHEEL": ("Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: " + tag + "\n").encode(),
    }
    if extra_native:
        files[extra_native] = bytes(header)
    rows = []
    for name, raw in files.items():
        digest = base64.urlsafe_b64encode(bytes.fromhex(probe.sha_bytes(raw))).decode().rstrip("=")
        rows.append([name, "sha256=" + digest, str(len(raw))])
    if corrupt_record:
        rows[0][1] = "sha256=" + "A" * 43
    record = prefix + "/RECORD"
    rows.append([record, "", ""])
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    files[record] = stream.getvalue().encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    return path


@pytest.fixture
def lock():
    return json.loads((ROOT / "scripts/neutts_native_sources_lock.json").read_bytes())


@pytest.fixture
def android_tags(monkeypatch):
    from pip._vendor.packaging import tags
    selected = tags.parse_tag("cp314-cp314-android_24_arm64_v8a")
    monkeypatch.setattr(tags, "sys_tags", lambda: iter(selected))


def test_modern_native_wheel_record_and_workqueue_identity(tmp_path, lock, android_tags):
    path = fake_numba_wheel(tmp_path)
    row = probe.verify_built_wheel(path, "numba", lock)
    assert row["tag"] == "cp314-cp314-android_24_arm64_v8a"
    assert len(row["native_members"]) == 1


@pytest.mark.parametrize("settings", [
    {"tag": "cp314-cp314-android_aarch64"},
    {"machine": 62},
    {"corrupt_record": True},
    {"extra_native": "numba/np/ufunc/omppool.cpython-314-aarch64-linux-android.so"},
    {"extra_native": "numba/np/ufunc/tbbpool.cpython-314-aarch64-linux-android.so"},
])
def test_foreign_legacy_or_unrequested_wheel_fails(tmp_path, lock, android_tags, settings):
    with pytest.raises(probe.ProbeError):
        probe.verify_built_wheel(fake_numba_wheel(tmp_path, **settings), "numba", lock)


def foundation(tmp_path, lock, monkeypatch):
    provenance = tmp_path / "NEUTTS-APT-PYTHON-VALIDATION.json"
    provenance.write_text('{"status":"requirements-and-provenance-passed"}\n')
    rows = []
    for name in sorted(probe.FOUNDATION_CASES):
        child = tmp_path / ("neutts-" + name + ".json")
        child.write_text(json.dumps({"schema_version": 1, "component": name, "status": "passed"}))
        rows.append({"component": name, "status": "passed", "exit_code": 0, "timed_out": False,
                     "receipt": child.name, "receipt_sha256": probe.sha_file(child)})
    result = {"schema_version": 1, "status": "passed", "uid": 1000,
              "python": {"platform": "android", "prefix": str(probe.PREFIX),
                         "executable": {"sha256": "actual-python"}},
              "apt_archive_hashes_checked_before_install": True, "engine_installed": False,
              "model_downloaded": False, "pm_admission_changed": False,
              "apt_python_validation": {
                  "status": "requirements-and-provenance-passed", "exit_code": 0,
                  "metadata_ledger_sha256": lock["foundation"]["apt_metadata_ledger_sha256"],
                  "receipt": provenance.name, "sha256": probe.sha_file(provenance)},
              "pip_check": {"exit_code": 1}, "cases": rows}
    actual_hash = probe.sha_file
    executable = Path("/proc/self/exe").resolve()
    monkeypatch.setattr(probe, "sha_file", lambda p: "actual-python" if p == executable else actual_hash(p))
    path = tmp_path / "NEUTTS-CORE-RESULT.json"
    path.write_text(json.dumps(result))
    return path, result


def test_full_foundation_and_raw_pip_failure_are_bound(tmp_path, lock, monkeypatch):
    path, _ = foundation(tmp_path, lock, monkeypatch)
    result = probe.validate_foundation(path, lock)
    assert result["case_count"] == 7 and result["raw_pip_exit_code"] == 1


@pytest.mark.parametrize("change", ["missing", "failed", "tampered", "ledger"])
def test_failed_or_stale_foundation_cannot_start_build(tmp_path, lock, monkeypatch, change):
    path, result = foundation(tmp_path, lock, monkeypatch)
    if change == "missing":
        result["cases"].pop()
    elif change == "failed":
        result["cases"][0]["exit_code"] = 1
    elif change == "tampered":
        (tmp_path / result["cases"][0]["receipt"]).write_text('{"status":"passed"}')
    else:
        result["apt_python_validation"]["metadata_ledger_sha256"] = "0" * 64
    path.write_text(json.dumps(result))
    with pytest.raises(probe.ProbeError):
        probe.validate_foundation(path, lock)


@pytest.mark.parametrize("returncode,claimed,expected", [
    (0, "passed", "passed"), (1, "passed", "failed"), (0, "failed", "failed"),
    (-11, "passed", "failed"),
])
def test_child_exit_and_receipt_must_both_pass(tmp_path, lock, monkeypatch, returncode, claimed, expected):
    def run(command, **kwargs):
        (tmp_path / "native-numba.json").write_text(json.dumps({
            "schema_version": 1, "component": "numba", "status": claimed,
            "behavior": {"real_native_fixture": "host control only"},
            "mapped_libraries": [{"path": "/fixture"}]}))
        return subprocess.CompletedProcess(command, returncode, b"", b"diagnostic")

    monkeypatch.setattr(probe.subprocess, "run", run)
    row = probe.execute_case("numba", Path("python"), lock, tmp_path, tmp_path, {})
    assert row["status"] == expected
    if returncode == -11:
        assert row["termination_signal"] == 11


def test_child_timeout_is_retained_as_failure(tmp_path, lock, monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 180, output=b"partial", stderr=b"failure")

    monkeypatch.setattr(probe.subprocess, "run", run)
    row = probe.execute_case("numba", Path("python"), lock, tmp_path, tmp_path, {})
    assert row["status"] == "failed" and row["exit_code"] == 124 and row["timed_out"]
    assert (tmp_path / "native-numba.stdout.log").read_bytes() == b"partial"


def test_oracle_exception_is_nonzero_even_when_library_collection_succeeds(tmp_path, lock, monkeypatch):
    monkeypatch.setattr(probe, "native_runtime", lambda: {"host_test_fixture": True})
    monkeypatch.setattr(probe, "numba_case", lambda: (_ for _ in ()).throw(RuntimeError("actual failure")))
    monkeypatch.setattr(probe, "mapped_libraries", lambda: [{"path": "/fixture"}])
    assert probe.run_case("numba", lock, tmp_path, tmp_path) == 1
    result = json.loads((tmp_path / "native-numba.json").read_bytes())
    assert result["status"] == "failed" and result["error"]["message"] == "actual failure"


def test_compiler_timeout_stops_its_process_group_and_stays_failed(tmp_path, monkeypatch):
    waits, kills = [], []
    class Process:
        pid = 54321
        def wait(self, timeout):
            waits.append(timeout)
            if len(waits) < 3:
                raise subprocess.TimeoutExpired(["compiler"], timeout)
            return -9
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(probe.os, "killpg", lambda pid, sig: kills.append((pid, sig)), raising=False)
    monkeypatch.setattr(probe.signal, "SIGKILL", 9, raising=False)
    with pytest.raises(probe.ProbeError, match="124"):
        probe.bounded_command(["compiler"], tmp_path, "compiler-fixture", 1)
    assert [pid for pid, _ in kills] == [54321, 54321]
    assert len(waits) == 3
    assert (tmp_path / "compiler-fixture.stderr.log").exists()


@pytest.mark.parametrize("inherited_platform", [
    None, "android-24-arm64_v8a", "android-aarch64", "linux-x86_64",
])
def test_native_build_uses_actual_android_platform(tmp_path, lock, monkeypatch, inherited_platform):
    """Exercise CPython's real parser using the environment passed to pip.

    This is a host-side build-command control, not a Bionic compilation. Clone
    the stdlib function with only its OS/configuration inputs replaced so the
    actual Android platform parser is exercised without mutating host globals.
    """
    if inherited_platform is None:
        monkeypatch.delenv("_PYTHON_HOST_PLATFORM", raising=False)
    else:
        monkeypatch.setenv("_PYTHON_HOST_PLATFORM", inherited_platform)
    inputs, out, work = (tmp_path / name for name in ("inputs", "out", "work"))
    (inputs / "sources").mkdir(parents=True)
    out.mkdir()
    work.mkdir()
    observed = []

    class BuildReached(Exception):
        pass

    def command(argv, output, label, timeout, env=None, cwd=None):
        if label not in ("native-build-python-inputs", "native-build-numba"):
            return {}
        namespace = dict(sysconfig.get_platform.__globals__)
        namespace.update({
            "os": SimpleNamespace(name="posix", environ=env,
                                  uname=lambda: ("Linux", "owned-fixture", "6.1", "", "aarch64")),
            "sys": SimpleNamespace(platform="android"),
            "get_config_var": lambda name: 24 if name == "ANDROID_API_LEVEL" else None,
        })
        platform_name = FunctionType(sysconfig.get_platform.__code__, namespace)()
        assert platform_name.replace("-", "_") == lock["target"]["wheel_platform"]
        # scikit-build-core reads this variable directly instead of expanding
        # CPython's OS/machine pair, so neither form is valid across both backends.
        assert "_PYTHON_HOST_PLATFORM" not in env
        observed.append(label)
        if label == "native-build-numba":
            raise BuildReached
        return {}

    monkeypatch.setattr(probe, "bounded_command", command)
    with pytest.raises(BuildReached):
        probe.build_packages(lock, inputs, out, work)
    assert observed == ["native-build-python-inputs", "native-build-numba"]


@pytest.mark.parametrize("load_mode,valid", [(-1, True), (99, False)])
def test_llama_probe_uses_current_load_mode_and_releases_backend(tmp_path, monkeypatch, load_mode, valid):
    """Current wrapper contract without loading host-incompatible native code."""
    import ctypes
    import sys
    from types import ModuleType

    class ModelParams(ctypes.Structure):
        _fields_ = [("load_mode", ctypes.c_int)]

    params = ModelParams(load_mode)
    assert not hasattr(params, "use_mmap")
    prefix = tmp_path / "venv"
    package_dir = prefix / "lib" / "python3.14" / "site-packages" / "llama_cpp"
    library = package_dir / "lib" / "libllama.so"
    events = []
    api = SimpleNamespace(
        _lib=SimpleNamespace(_name=str(library)),
        LLAMA_LOAD_MODE_AUTO=-1,
        llama_backend_init=lambda: events.append("init"),
        llama_backend_free=lambda: events.append("free"),
        llama_print_system_info=lambda: b"CPU : NEON = 1",
        llama_model_default_params=lambda: params,
        llama_context_default_params=lambda: SimpleNamespace(n_ctx=512, n_batch=2048, n_threads=4),
        llama_supports_gpu_offload=lambda: False,
        llama_supports_rpc=lambda: False,
        llama_supports_mmap=lambda: True,
        llama_supports_mlock=lambda: True,
    )
    package = ModuleType("llama_cpp")
    package.__file__ = str(package_dir / "__init__.py")
    package.__version__ = "0.3.36"
    package.llama_cpp = api
    monkeypatch.setitem(sys.modules, "llama_cpp", package)
    monkeypatch.setattr(probe.sys, "prefix", str(prefix))
    monkeypatch.setattr(probe, "elf", lambda path, dynamic: {"path": str(path)})
    monkeypatch.setattr(probe, "mapped_libraries", lambda: [
        {"path": str(library)}, {"path": str(library.parent / "libggml-base.so")}
    ])
    if valid:
        result = probe.llama_case()
        assert result["default_model_load_mode"] == -1
        assert "default_model_use_mmap" not in result
        assert result["backend_initialized"] and result["backend_freed"]
        assert result["model_loaded"] is False and result["inference_tested"] is False
        assert result["supports_mmap"] is True
    else:
        with pytest.raises(probe.ProbeError, match="default model load mode"):
            probe.llama_case()
    assert events == ["init", "free"]
