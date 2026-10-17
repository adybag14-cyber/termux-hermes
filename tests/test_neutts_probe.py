"""Probe receipts must keep concrete failures and cannot certify NeuTTS synthesis."""
import json
from pathlib import Path
import subprocess

import pytest

from scripts import compatibility_probe_neutts as probe


def passed_receipt(component="torch", **updates):
    return {
        "schema_version": 1, "component": component, "status": "passed",
        "behavior": {"independent_numeric_oracle": "fixture"},
        "mapped_libraries": [{"path": "/fixture/libnative.so", "machine": 183}],
        **updates,
    }


def child_result(monkeypatch, out, receipt, *, code=0, stdout=b"", stderr=b"", error=None):
    def run(args, **kwargs):
        assert args[-3:] == ["--case", "torch", str(out)]
        assert kwargs == {"capture_output": True, "timeout": 90}
        if receipt is not None:
            raw = receipt if isinstance(receipt, str) else json.dumps(receipt)
            (out / "neutts-torch.json").write_text(raw, encoding="utf-8")
        if error:
            raise error
        return subprocess.CompletedProcess(args, code, stdout, stderr)
    monkeypatch.setattr(probe.subprocess, "run", run)


def test_valid_child_requires_both_successful_exit_and_native_evidence(tmp_path, monkeypatch):
    child_result(monkeypatch, tmp_path, passed_receipt(), stdout=b"numerical result\n")
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["receipt_sha256"] == probe.sha(tmp_path / "neutts-torch.json")
    assert (tmp_path / "neutts-torch.stdout.log").read_bytes() == b"numerical result\n"


@pytest.mark.parametrize("receipt", [
    "not json",
    "[]",
    passed_receipt(component="scipy"),
    passed_receipt(schema_version=2),
    passed_receipt(status="unknown"),
    passed_receipt(behavior=None),
    passed_receipt(mapped_libraries=[]),
])
def test_malformed_child_evidence_is_failure_not_an_aborted_collector(tmp_path, monkeypatch, receipt):
    child_result(monkeypatch, tmp_path, receipt)
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "failed"
    assert result["receipt_error"]["message"]
    assert (tmp_path / "neutts-torch.stderr.log").exists()


def test_native_import_failure_is_reported_without_hiding_the_missing_dependency(tmp_path, monkeypatch):
    failure = {"schema_version": 1, "component": "torch", "status": "failed",
               "error": {"type": "ModuleNotFoundError", "message": "No module named 'fixture'"},
               "mapped_libraries": []}
    child_result(monkeypatch, tmp_path, failure, code=1)
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "failed"
    assert result["error"] == failure["error"]


def test_native_crash_retains_signal_and_logs_without_a_receipt(tmp_path, monkeypatch):
    child_result(monkeypatch, tmp_path, None, code=-11, stderr=b"native diagnostic")
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "failed"
    assert result["termination_signal"] == 11
    assert result["receipt"] is None
    assert result["receipt_error"]["type"] == "FileNotFoundError"
    assert (tmp_path / "neutts-torch.stderr.log").read_bytes() == b"native diagnostic"


def test_nonzero_exit_cannot_pass_with_a_successful_receipt(tmp_path, monkeypatch):
    child_result(monkeypatch, tmp_path, passed_receipt(), code=9)
    assert probe.execute_case("torch", tmp_path)["status"] == "failed"


def test_timeout_cannot_pass_with_a_successful_receipt(tmp_path, monkeypatch):
    error = subprocess.TimeoutExpired("native fixture", 90, output=b"partial stdout", stderr=b"partial stderr")
    child_result(monkeypatch, tmp_path, passed_receipt(), error=error)
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "failed" and result["timed_out"] is True
    assert result["exit_code"] == 124
    assert (tmp_path / "neutts-torch.stdout.log").read_bytes() == b"partial stdout"
    assert (tmp_path / "neutts-torch.stderr.log").read_bytes() == b"partial stderr"


def test_launch_failure_is_a_retained_result(tmp_path, monkeypatch):
    child_result(monkeypatch, tmp_path, None, error=FileNotFoundError("missing interpreter fixture"))
    result = probe.execute_case("torch", tmp_path)
    assert result["status"] == "failed" and result["exit_code"] == 127
    assert result["launch_error"]["type"] == "FileNotFoundError"


def test_bounded_log_tails_disclose_truncation(tmp_path, monkeypatch):
    child_result(monkeypatch, tmp_path, passed_receipt(), stdout=b"discard" + b"x" * 100000)
    result = probe.execute_case("torch", tmp_path)
    assert result["stdout_bytes"] == 100007
    assert result["stdout_saved_bytes"] == 100000
    assert result["stdout_truncated"] is True
    assert (tmp_path / "neutts-torch.stdout.log").read_bytes() == b"x" * 100000


def test_stale_receipt_cannot_be_reused(tmp_path, monkeypatch):
    receipt = tmp_path / "neutts-torch.json"
    receipt.write_text(json.dumps(passed_receipt()), encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("a child must not launch against stale evidence")

    monkeypatch.setattr(probe.subprocess, "run", unexpected)
    with pytest.raises(RuntimeError, match="stale component receipt"):
        probe.execute_case("torch", tmp_path)


def test_child_preserves_behavior_error_even_if_library_inspection_fails(tmp_path, monkeypatch):
    def failed_behavior():
        raise ImportError("actual import failure fixture")

    def failed_libraries():
        raise OSError("actual maps failure fixture")

    monkeypatch.setattr(probe, "torch_case", failed_behavior)
    monkeypatch.setattr(probe, "libraries", failed_libraries)
    assert probe.run_case("torch", tmp_path) == 1
    result = json.loads((tmp_path / "neutts-torch.json").read_text())
    assert result["status"] == "failed"
    assert result["error"]["message"] == "actual import failure fixture"
    assert result["library_evidence_error"] == "actual maps failure fixture"


def test_container_gate_refuses_host_python_before_any_package_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="native Bionic"):
        probe.main(tmp_path)


def test_elf_evidence_rejects_wrong_machine(tmp_path):
    header = bytearray(64)
    header[:6] = b"\x7fELF\x02\x01"
    header[18:20] = (62).to_bytes(2, "little")
    fixture = tmp_path / "wrong-machine.so"
    fixture.write_bytes(header)
    with pytest.raises(RuntimeError, match="actual AArch64"):
        probe.elf(fixture)


def test_exact_engine_source_provenance_block_compiles():
    script = (Path(__file__).resolve().parents[1] / "scripts/compatibility_probe_neutts.sh").read_text(encoding="utf-8")
    block = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    compile(block, "neutts-host-provenance", "exec")


ANDROID_MARKERS = {
    "python_full_version": "3.14.6", "python_version": "3.14",
    "sys_platform": "android", "platform_machine": "aarch64", "platform_system": "Android",
}


def test_missing_transitive_python_dependency_is_rejected():
    graph = {
        "torch": {"version": "2.14.1", "requires_dist": ["jinja2"]},
        "jinja2": {"version": "3.1.6", "requires_dist": ["MarkupSafe>=2.0"]},
    }
    with pytest.raises(RuntimeError, match="missing pinned runtime dependency: jinja2"):
        probe.validate_metadata_closure(graph, ANDROID_MARKERS)


def test_complete_closure_checks_active_markers_without_unrequested_extras():
    graph = {
        "torch": {"version": "2.14.1", "requires_python": ">=3.10",
                  "requires_dist": ["typing_extensions>=4.10.0", "optree; extra == 'optree'",
                                    "cuda; sys_platform == 'linux'"]},
        "typing-extensions": {"version": "4.16.0", "requires_dist": []},
    }
    edges = probe.validate_metadata_closure(graph, ANDROID_MARKERS)
    assert [edge["active"] for edge in edges] == [True, False, False]
    assert edges[0]["selected_version"] == "4.16.0"


def test_incompatible_pinned_dependency_is_rejected():
    graph = {"torch": {"version": "2.14.1", "requires_dist": ["sympy>=1.13.3"]},
             "sympy": {"version": "1.12.0", "requires_dist": []}}
    with pytest.raises(RuntimeError, match="incompatible pinned runtime dependency"):
        probe.validate_metadata_closure(graph, ANDROID_MARKERS)


def test_engine_python_boundary_cannot_be_erased_by_a_complete_dependency_list():
    with pytest.raises(RuntimeError, match="excludes this interpreter"):
        probe.validate_metadata_closure({"neutts": {"version": "1.4.1", "requires_python": ">=3.10,<3.14",
                                                    "requires_dist": []}}, ANDROID_MARKERS)


@pytest.mark.parametrize("requirement", [
    "child @ https://example.invalid/child.whl", "child[unreviewed]",
])
def test_unreviewed_runtime_dependency_arrangements_fail(requirement):
    graph = {"parent": {"version": "1.0", "requires_dist": [requirement]},
             "child": {"version": "1.0", "requires_dist": []}}
    with pytest.raises(RuntimeError, match="requires? review"):
        probe.validate_metadata_closure(graph, ANDROID_MARKERS)


def test_registry_wheel_rejects_native_payload_even_with_universal_tag(tmp_path):
    import zipfile
    path = tmp_path / "fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("fixture-1.0.dist-info/METADATA", "Name: fixture\nVersion: 1.0\n")
        wheel.writestr("fixture-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        wheel.writestr("fixture/native.so", b"unreviewed native code fixture")
    with pytest.raises(RuntimeError, match="universal pure Python"):
        probe.inspect_wheel(path, {"name": "fixture", "version": "1.0"}, universal=True)


def test_exact_artifact_download_rejects_changed_bytes(monkeypatch):
    import io
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"changed"))
    with pytest.raises(RuntimeError, match="bytes/hash differ"):
        probe.read_pinned_url("https://files.pythonhosted.org/fixture.whl", 7, "0" * 64)


def test_native_dependency_installer_refuses_host_python_before_reading_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="native Bionic"):
        probe.install_python_inputs(tmp_path / "missing", tmp_path)


def apt_platform_output():
    return "\n".join(f"{name} {probe.EXPECTED[name]} is not supported on this platform"
                     for name in probe.APT_WHEEL_SHA256) + "\n"


def apt_wheel_fixture():
    return {name: {"version": probe.EXPECTED[name], "wheel_metadata_sha256": digest,
                   "matches_current_supported_tags": False}
            for name, digest in probe.APT_WHEEL_SHA256.items()}


def test_exact_apt_tag_diagnostic_retains_failed_pip_compatibility(monkeypatch):
    evidence = apt_wheel_fixture()
    monkeypatch.setattr(probe, "installed_apt_wheel_evidence", lambda: evidence)
    result = probe.classify_pip_check(1, apt_platform_output(), "")
    assert result["status"] == "failed"
    assert result["pip_check_passed"] is False
    assert result["wheel_tag_compatibility"] == "unresolved"
    assert result["apt_wheel_evidence"] == evidence
    assert result["diagnostic_continuation"] == "only measured native scientific behavior"


@pytest.mark.parametrize("line", [
    "torch 2.14.1 requires filelock, which is not installed.",
    "torch 2.14.1 has requirement sympy>=1.13.3, but you have sympy 1.12.0.",
    "unknown 1.0 is not supported on this platform",
])
def test_missing_conflicting_or_unknown_pip_error_cannot_continue(line):
    with pytest.raises(RuntimeError, match="beyond the reviewed"):
        probe.classify_pip_check(1, apt_platform_output() + line + "\n", "")


@pytest.mark.parametrize("code,stderr", [(2, ""), (1, "unexpected stderr")])
def test_other_pip_status_or_stderr_cannot_continue(code, stderr):
    with pytest.raises(RuntimeError, match="beyond the reviewed"):
        probe.classify_pip_check(code, apt_platform_output(), stderr)


def test_partial_apt_unsupported_set_cannot_continue():
    with pytest.raises(RuntimeError, match="beyond the reviewed"):
        probe.classify_pip_check(1, "\n".join(apt_platform_output().splitlines()[:-1]), "")


@pytest.mark.parametrize("change", ["hash", "version", "compatible"])
def test_apt_diagnostic_requires_exact_original_wheel_evidence(monkeypatch, change):
    evidence = apt_wheel_fixture()
    row = evidence["torch"]
    if change == "hash":
        row["wheel_metadata_sha256"] = "0" * 64
    elif change == "version":
        row["version"] = "0.0"
    else:
        row["matches_current_supported_tags"] = True
    monkeypatch.setattr(probe, "installed_apt_wheel_evidence", lambda: evidence)
    with pytest.raises(RuntimeError, match="unverified APT"):
        probe.classify_pip_check(1, apt_platform_output(), "")


def test_genuine_successful_pip_check_is_reported_as_passed():
    result = probe.classify_pip_check(0, "No broken requirements found.\n", "")
    assert result == {"status": "passed", "pip_check_passed": True, "wheel_tag_compatibility": "passed"}


def test_installed_apt_wheel_evidence_rejects_changed_bytes(monkeypatch):
    class Distribution:
        version = probe.EXPECTED[next(iter(probe.APT_WHEEL_SHA256))]

        def read_text(self, name):
            assert name == "WHEEL"
            return "Wheel-Version: 1.0\nTag: invented\n"

    monkeypatch.setattr(probe.importlib.metadata, "distribution", lambda name: Distribution())
    with pytest.raises(RuntimeError, match="APT WHEEL metadata changed"):
        probe.installed_apt_wheel_evidence()
