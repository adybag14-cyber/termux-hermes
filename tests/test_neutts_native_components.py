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


def test_native_build_commands_cannot_inherit_or_inject_a_platform_override(tmp_path, lock, monkeypatch):
    # Reproduce the observed build environment, without pretending this host is Android.
    monkeypatch.setenv("_PYTHON_HOST_PLATFORM", "android-24-arm64_v8a")
    inputs, out, work = (tmp_path / name for name in ("inputs", "out", "work"))
    (inputs / "sources").mkdir(parents=True)
    out.mkdir()
    work.mkdir()
    commands = []

    class ReachedCompilerBoundary(Exception):
        pass

    def capture(command, destination, label, timeout, env=None, cwd=None):
        commands.append((label, env))
        if label == "native-build-numba":
            assert env is not None
            assert "_PYTHON_HOST_PLATFORM" not in env
            raise ReachedCompilerBoundary
        return {"exit_code": 0}

    monkeypatch.setattr(probe, "bounded_command", capture)
    with pytest.raises(ReachedCompilerBoundary):
        probe.build_packages(lock, inputs, out, work)
    assert [label for label, _ in commands] == [
        "native-create-venv", "native-build-python-inputs", "native-build-numba",
    ]
    assert all(env is not None and "_PYTHON_HOST_PLATFORM" not in env for _, env in commands)
    assert probe.os.environ["_PYTHON_HOST_PLATFORM"] == "android-24-arm64_v8a"


def test_native_runtime_refuses_an_inherited_override_before_platform_queries(monkeypatch):
    monkeypatch.setenv("_PYTHON_HOST_PLATFORM", "android-24-arm64_v8a")

    def unexpected_platform_query():
        pytest.fail("an inherited override must be rejected before querying native tags")

    monkeypatch.setattr(probe.sysconfig, "get_platform", unexpected_platform_query)
    with pytest.raises(probe.ProbeError, match="actual platform without a host override"):
        probe.native_runtime()


@pytest.fixture
def pinned_llama_api(monkeypatch):
    """Model the pinned C/Python API surface; this does not execute native code."""
    from types import ModuleType, SimpleNamespace

    calls = []
    package = ModuleType("llama_cpp")
    package.__version__ = "0.3.36"
    package.__file__ = str(Path(probe.sys.prefix) / "llama-oracle-fixture" / "llama_cpp" / "__init__.py")
    library = Path(package.__file__).resolve().parent / "lib" / "libllama.so"
    model = SimpleNamespace(load_mode=-1, lazy_mode=1)
    api = SimpleNamespace(
        _lib=SimpleNamespace(_name=str(library)),
        LLAMA_LOAD_MODE_AUTO=-1,
        LLAMA_LAZY_MODE_AUTO=1,
        llama_backend_init=lambda: calls.append("init"),
        llama_backend_free=lambda: calls.append("free"),
        llama_print_system_info=lambda: b"CPU : host oracle fixture",
        llama_model_default_params=lambda: model,
        llama_context_default_params=lambda: SimpleNamespace(n_ctx=512, n_batch=2048, n_threads=4),
        llama_supports_gpu_offload=lambda: False,
        llama_supports_rpc=lambda: False,
        llama_supports_mmap=lambda: True,
        llama_supports_mlock=lambda: True,
    )
    package.llama_cpp = api
    monkeypatch.setitem(probe.sys.modules, "llama_cpp", package)
    monkeypatch.setattr(probe, "elf", lambda path, **kwargs: {"host_fixture_path": str(path)})
    monkeypatch.setattr(probe, "mapped_libraries", lambda: [{"path": str(library)}])
    return model, calls


def test_llama_oracle_reads_pinned_load_modes_without_obsolete_use_mmap(pinned_llama_api):
    _, calls = pinned_llama_api
    result = probe.llama_case()
    assert result["default_model"] == {"load_mode": -1, "lazy_mode": 1}
    assert "default_model_use_mmap" not in result
    assert result["supports_mmap"] is True
    assert result["backend_initialized"] is True and result["backend_freed"] is True
    assert result["model_loaded"] is False and result["inference_tested"] is False
    assert calls == ["init", "free"]


@pytest.mark.parametrize("field,value", [("load_mode", 0), ("lazy_mode", 2)])
def test_llama_oracle_rejects_changed_pinned_defaults_and_frees_backend(pinned_llama_api, field, value):
    model, calls = pinned_llama_api
    setattr(model, field, value)
    with pytest.raises(probe.ProbeError, match="Unexpected native default model load modes"):
        probe.llama_case()
    assert calls == ["init", "free"]
