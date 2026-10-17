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
