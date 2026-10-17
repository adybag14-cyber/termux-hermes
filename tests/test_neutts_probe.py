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


def validation_receipt(out):
    (out / "NEUTTS-PYTHON-CHECK.log").write_bytes(b"exact platform-tag diagnostics\n")
    return {
        "schema_version": 1, "status": "requirements-and-provenance-passed",
        "overall_compatibility_passed": False,
        "native_behavior": {"status": "required-pending"},
        "metadata_modified": False, "supported_tags_modified": False,
        "engine_synthesis_tested": False, "pm_admission_changed": False,
        "metadata_ledger": {"sha256": "a" * 64},
        "apt_provenance": {"status": "passed"},
        "apt_dependencies": {"status": "passed"},
        "requirements": {"status": "passed"},
        "raw_pip_check": {
            "exit_code": 1, "passed": False,
            "sha256": probe.sha(out / "NEUTTS-PYTHON-CHECK.log"),
        },
    }


def save_validation(out, result):
    (out / "NEUTTS-APT-PYTHON-VALIDATION.json").write_text(
        json.dumps(result), encoding="utf-8"
    )


def test_provenance_admission_keeps_raw_pip_failure_and_requires_native_behavior(tmp_path):
    result = validation_receipt(tmp_path)
    save_validation(tmp_path, result)
    admitted = probe.apt_python_validation(tmp_path, 1, 0, "a" * 64)
    assert admitted["status"] == "requirements-and-provenance-passed"
    assert admitted["raw_pip_check_preserved"] is True
    assert result["raw_pip_check"]["passed"] is False
    assert result["overall_compatibility_passed"] is False
    assert admitted["sha256"] == probe.sha(tmp_path / "NEUTTS-APT-PYTHON-VALIDATION.json")


@pytest.mark.parametrize("change", [
    {"schema_version": 2},
    {"status": "failed"},
    {"overall_compatibility_passed": True},
    {"native_behavior": {"status": "passed"}},
    {"metadata_modified": True},
    {"supported_tags_modified": True},
    {"engine_synthesis_tested": True},
    {"pm_admission_changed": True},
    {"metadata_ledger": {"sha256": "b" * 64}},
    {"apt_provenance": {"status": "failed"}},
    {"apt_dependencies": {"status": "failed"}},
    {"requirements": {"status": "failed"}},
    {"raw_pip_check": {"exit_code": 0, "passed": True, "sha256": "c" * 64}},
])
def test_incomplete_or_mismatched_provenance_cannot_admit_native_dependencies(tmp_path, change):
    result = validation_receipt(tmp_path)
    result.update(change)
    save_validation(tmp_path, result)
    with pytest.raises(RuntimeError):
        probe.apt_python_validation(tmp_path, 1, 0, "a" * 64)


def test_failed_validator_exit_cannot_pass_with_a_success_receipt(tmp_path):
    save_validation(tmp_path, validation_receipt(tmp_path))
    with pytest.raises(RuntimeError, match="validation failed"):
        probe.apt_python_validation(tmp_path, 1, 1, "a" * 64)


def test_replaced_pip_log_cannot_reuse_a_previous_validation_receipt(tmp_path):
    save_validation(tmp_path, validation_receipt(tmp_path))
    (tmp_path / "NEUTTS-PYTHON-CHECK.log").write_bytes(b"different requirements failure\n")
    with pytest.raises(RuntimeError, match="this invocation"):
        probe.apt_python_validation(tmp_path, 1, 0, "a" * 64)


def complete_core_fixture():
    cases = [
        {"component": name, "status": "passed", "exit_code": 0, "timed_out": False}
        for name in probe.CASES
    ]
    provenance = {"status": "requirements-and-provenance-passed", "exit_code": 0}
    metadata = {"unsupported_distribution_names": list(probe.EXPECTED)}
    return cases, provenance, metadata


def test_successful_scientific_core_does_not_claim_pip_or_engine_compatibility():
    cases, provenance, metadata = complete_core_fixture()
    result = probe.summarize_core_results(cases, provenance, metadata, 1)
    assert result["status"] == "passed"
    assert result["scientific_behavior_passed"] is True
    assert result["python_installed_files_passed"] is True
    assert result["dependency_closure_passed"] is True
    assert result["pip_check_passed"] is False
    assert result["pip_wheel_tag_compatibility"] == "unresolved"
    assert result["overall_compatibility_passed"] is False


def test_six_scientific_passes_cannot_hide_failed_installed_wheel_evidence():
    cases, provenance, metadata = complete_core_fixture()
    cases[0].update(status="failed", exit_code=1)
    result = probe.summarize_core_results(cases, provenance, metadata, 1)
    assert result["status"] == "failed"
    assert result["scientific_behavior_passed"] is True
    assert result["python_installed_files_passed"] is False


@pytest.mark.parametrize("provenance", [
    {"status": "failed", "exit_code": 1},
    {"status": "requirements-and-provenance-passed", "exit_code": 1},
    {"status": "requirements-and-provenance-passed", "exit_code": 0, "error": {}},
    {},
])
def test_seven_native_passes_cannot_replace_strict_dependency_provenance(provenance):
    cases, _, metadata = complete_core_fixture()
    result = probe.summarize_core_results(cases, provenance, metadata, 1)
    assert result["status"] == "failed"
    assert result["scientific_behavior_passed"] is True
    assert result["dependency_closure_passed"] is False


@pytest.mark.parametrize("metadata", [
    {"error": {"message": "unreadable original WHEEL"}},
    {"unsupported_distribution_names": ["unreviewed"]},
    {},
])
def test_summary_requires_the_exact_original_apt_tag_evidence(metadata):
    cases, provenance, _ = complete_core_fixture()
    assert probe.summarize_core_results(cases, provenance, metadata, 1)["status"] == "failed"


@pytest.mark.parametrize("kind", ["omitted", "duplicated", "unreviewed"])
def test_partial_or_ambiguous_case_collection_cannot_certify_the_scientific_core(kind):
    cases, provenance, metadata = complete_core_fixture()
    if kind == "omitted":
        cases.pop()
    elif kind == "duplicated":
        cases.append(dict(cases[-1]))
    else:
        cases.append({"component": "unreviewed", "status": "passed", "exit_code": 0, "timed_out": False})
    result = probe.summarize_core_results(cases, provenance, metadata, 1)
    assert result["status"] == "failed"
    assert result["native_case_set_complete"] is False


@pytest.mark.parametrize("updates", [{"exit_code": 9}, {"timed_out": True}])
def test_success_receipt_cannot_hide_a_failed_or_timed_out_scientific_child(updates):
    cases, provenance, metadata = complete_core_fixture()
    cases[-1].update(updates)
    result = probe.summarize_core_results(cases, provenance, metadata, 1)
    assert result["status"] == "failed"
    assert result["scientific_behavior_passed"] is False


def test_changed_pip_exit_is_outside_the_frozen_provenance_convention():
    cases, provenance, metadata = complete_core_fixture()
    result = probe.summarize_core_results(cases, provenance, metadata, 0)
    assert result["status"] == "failed"
    assert result["pip_check_passed"] is True
    assert result["overall_compatibility_passed"] is False
