"""Freeze exact completed run 39071928457 and independently recheck its recorded gates."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib, json, zipfile

BASE = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
EVIDENCE = BASE / "espeak-termux-native-evidence-20261017/39071928457"
REPO = BASE / "termux-hermes-next-stable-20261017"
AUDIT = REPO / "audit/neutts-espeak-native-20261017"
RAW = AUDIT / "run-39071928457"
SUMMARY = AUDIT / "run-39071928457.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_json(path):
    return json.loads(path.read_bytes())


def save_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def main():
    assert not RAW.exists() and not SUMMARY.exists()
    ledger = raw_json(EVIDENCE / "verified-artifact.json")
    assert ledger["run_id"] == 39071928457
    assert ledger["head_sha"] == "555752c8e080b38715bff234001283a03298c743"
    assert ledger["job_id"] == 117511147583 and ledger["conclusion"] == "failure"
    assert ledger["artifact_id"] == 12115681939 and ledger["artifact_bytes"] == 54767182
    assert ledger["artifact_sha256"] == "0198a6225fc09c0ab9f77a036901332ca712e9aad087630b4e9fd00a5d75b7b1"
    archive = EVIDENCE / "artifact.zip"
    assert archive.stat().st_size == ledger["artifact_bytes"]
    assert digest(archive.read_bytes()) == ledger["artifact_sha256"]
    entries = {row["name"]: row for row in ledger["members"]}
    assert len(entries) == len(ledger["members"]) == 641
    retained = {name: row for name, row in entries.items() if row["extracted"]}
    assert len(retained) == 134
    extracted = EVIDENCE / "extracted"
    assert {p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file()} == set(retained)
    for name, row in retained.items():
        path = extracted / name
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == row["bytes"] and digest(path.read_bytes()) == row["sha256"]
    log = (EVIDENCE / "native-job.log").read_bytes()
    assert len(log) == 207730 and digest(log) == "d6e8a3cd448fb45df905003bfc9be6dc9308ea4188781b6ff7280fd889836fe2"

    core = raw_json(extracted / "NEUTTS-CORE-RESULT.json")
    assert core["status"] == "passed" and len(core["cases"]) == 7
    for row in core["cases"]:
        assert row["status"] == "passed" and row["exit_code"] == 0 and row["timed_out"] is False
        assert digest((extracted / row["receipt"]).read_bytes()) == row["receipt_sha256"]
        child = raw_json(extracted / row["receipt"])
        assert child["status"] == "passed" and child["component"] == row["component"]
    validation = core["apt_python_validation"]
    assert validation["status"] == "requirements-and-provenance-passed" and validation["exit_code"] == 0
    assert digest((extracted / validation["receipt"]).read_bytes()) == validation["sha256"]
    assert core["pip_check"]["exit_code"] == 1
    assert digest((extracted / core["pip_check"]["log"]).read_bytes()) == core["pip_check"]["log_sha256"]

    component = extracted / "espeak-component"
    espeak = raw_json(component / "ESPEAK-COMPONENT-RESULT.json")
    assert espeak["status"] == "passed" and len(espeak["cases"]) == 14
    assert espeak["source_commit"] == "69bfd1efde0236654ccc117a28d04aef27673a30"
    assert espeak["source_manifest"] == {"bytes": 63434219, "file_count": 2606,
        "sha256": "69e5228b663815a4fa4b20bfca13242826d132128f1ee5a43f03091ce608ff50"}
    assert espeak["lock_sha256"] == "02e4469a3b7b3e6594d7b1bc9c6816c72adf1ea9eb917256cefefc9c12763baa"
    assert espeak["real_python_wrapper_proved"] is False
    for stage in ("configure", "build", "install"):
        assert espeak[stage]["exit_code"] == 0
        for channel in ("stdout", "stderr"):
            assert digest((component / ("espeak-" + stage + "." + channel + ".log")).read_bytes()) == espeak[stage][channel + "_sha256"]
    toolchain = espeak["toolchain"]
    assert len(toolchain["archives"]) == 44 and toolchain["additional_count"] == 19
    assert toolchain["apt"]["exit_code"] == 0
    source_lock = raw_json(extracted / "espeak-inputs/espeak-source-lock.json")
    cases = []
    for row in espeak["cases"]:
        assert row["status"] == "passed"
        for channel in ("stdout", "stderr"):
            assert digest((component / (row["case"] + "." + channel + ".log")).read_bytes()) == row[channel + "_sha256"]
        if row["case"] == "espeak-missing-data":
            assert row["exit_code"] == 1 and row["expected_initialization_failure"] is True
            assert b"phontab" in (component / (row["case"] + ".stderr.log")).read_bytes()
            cases.append({"case": row["case"], "status": "passed", "exit_code": 1,
                          "meaning": "Expected native initialization rejection with missing data"})
        else:
            assert row["exit_code"] == 0
            path = component / row["receipt"]
            assert digest(path.read_bytes()) == row["receipt_sha256"]
            child = raw_json(path)
            assert child["status"] == "passed" and child["synthesis_called"] is False
            if "phonemes" in child:
                assert child["cursor_completed"] is True and child["phonemes"]
            cases.append({k: row[k] for k in ("case", "status", "exit_code", "receipt", "receipt_sha256")})
    assert len({row["case"] for row in cases}) == 14
    for fixture in range(5):
        original = raw_json(component / f"espeak-ascii-{fixture}.json")
        relocated = raw_json(component / f"espeak-relocated-{fixture}.json")
        assert original["phonemes"] == relocated["phonemes"]
        assert original["upstream_ascii_oracle_checked"] and relocated["upstream_ascii_oracle_checked"]
        assert original["data_path"] != relocated["data_path"]
    ipa = [raw_json(component / f"espeak-ipa-repeat-{n}.json")["phonemes"] for n in range(2)]
    assert ipa == ["h\u0259l\u02c8\u0259\u028a", "h\u0259l\u02c8\u0259\u028a"]
    tree = raw_json(component / "ESPEAK-DATA-MANIFEST.json")
    assert len(tree) == espeak["data_tree"]["file_count"] == 371
    assert sum(row["size"] for row in tree) == espeak["data_tree"]["bytes"] == 18632313
    assert len([r for r in tree if r["path"].endswith("_dict")]) == 117
    assert digest((component / "ESPEAK-DATA-MANIFEST.json").read_bytes()) == espeak["data_tree"]["manifest_sha256"]
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == set(entries)
        for row in tree:
            name = "espeak-component/bundle/share/espeak-ng-data/" + row["path"]
            data = z.read(name)
            assert len(data) == row["size"] and digest(data) == row["sha256"]
            blob = b"blob " + str(len(data)).encode() + b"\x00" + data
            assert hashlib.sha1(blob).hexdigest() == row["git_blob_sha1"]
        for kind in ("library", "cli"):
            identity = espeak[kind]
            name = identity["path"].removeprefix("/out/")
            data = z.read(name)
            assert len(data) == identity["bytes"] and digest(data) == identity["sha256"]
            assert data[:6] == b"\x7fELF\x02\x01" and int.from_bytes(data[18:20], "little") == 183

    union = raw_json(extracted / "PHONEMIZER-APT-ARCHIVE-UNION.json")
    assert union["status"] == "verified-45-archive-union" and union["archive_count"] == 45
    assert len(union["archives"]) == 45 and union["compiler_archive_count"] == 44
    assert union["pip_control_verified"] is True and union["pip_selected_source_files_verified"] == 456
    assert union["apt_install_performed"] is False and union["compiler_gate_changed"] is False
    assert union["espeak_receipt_sha256"] == digest((component / "ESPEAK-COMPONENT-RESULT.json").read_bytes())
    phonemizer = raw_json(extracted / "phonemizer-component/PHONEMIZER-COMPONENT-RESULT.json")
    assert phonemizer["status"] == "failed" and phonemizer["stage"] == "native-build"
    assert phonemizer["error"]["type"] == "OSError" and "[Errno 18] Cross-device link" in phonemizer["error"]["message"]
    assert not (extracted / "phonemizer-component/PHONEMIZER-RUNTIME-RESULT.json").exists()
    assert "source_builds" not in phonemizer and "built_wheels" not in phonemizer
    assert not any("wheel-phonemizer" in n and n.endswith(".whl") for n in entries)
    build_stdout = (extracted / "phonemizer-component/phonemizer-build-phonemizer.stdout.log").read_text()
    assert '"source": "phonemizer"' in build_stdout and '"wheel": "phonemizer-3.3.0-py3-none-any.whl"' in build_stdout

    for name in retained:
        save_new(RAW / name, (extracted / name).read_bytes())
    supplementary = [p for p in EVIDENCE.iterdir() if p.is_file() and
                     (p.name.endswith("-api.json") or "-api-" in p.name or
                      p.name in ("native-job.log", "verified-artifact.json"))]
    for path in supplementary:
        raw = path.read_bytes()
        assert b"&sig=" not in raw and b"?sv=" not in raw
        save_new(RAW / path.name, raw)
    save_new(RAW / "capture_espeak_component_run_20261017.py",
             (BASE / "capture_espeak_component_run_20261017.py").read_bytes())
    save_new(RAW / "freeze-run-evidence.py", Path(__file__).read_bytes())
    save_new(RAW / ".gitattributes", b"* -text\n")
    recheck = {"schema_version": 1, "checked_utc": datetime.now(timezone.utc).isoformat(),
               "artifact_full_digest_and_all_641_member_crcs_rechecked": True,
               "retained_134_files_match_exact_member_ledger": True,
               "foundation": {"cases_passed": 7, "all_child_receipt_sha256_verified": True,
                              "raw_pip_check_exit_code": 1, "provenance_passed": True},
               "espeak": {"cases_passed": 14, "positive_child_exits_zero": 13,
                          "expected_missing_data_exit_one": True, "cases": cases,
                          "all_child_receipt_and_stdout_stderr_hashes_verified": True,
                          "all_371_data_files_independently_match_zip_bytes_sha256_git_blob_sha1": True,
                          "data_bytes": 18632313, "dictionaries": 117,
                          "library_and_cli_independent_elf_aarch64_and_sha256": True,
                          "library": espeak["library"], "data_tree": espeak["data_tree"],
                          "source_manifest": espeak["source_manifest"]},
               "compiler_archives_verified": 44, "selected_toolchain_installs": 19,
               "phonemizer_provenance_archive_union_verified": 45,
               "phonemizer_build_log_completed": True,
               "phonemizer_built_wheel_bytes_retained": False,
               "regex_build_reached": False, "real_phonemizer_api_proved": False,
               "full_engine_proved": False, "model_downloaded": False,
               "audio_io_performed": False, "synthesis_tested": False, "release_output": False}
    save_new(RAW / "VERIFIED-RESULT-RECHECK.json", encode(recheck))
    rows = [{"path": p.relative_to(RAW).as_posix(), "bytes": p.stat().st_size,
             "sha256": digest(p.read_bytes())} for p in sorted(RAW.rglob("*")) if p.is_file()]
    save_new(RAW / "SAVED-FILES.json", encode({"schema_version": 1, "scope": "All raw files except this ledger",
                                             "files": rows, "file_count": len(rows),
                                             "total_bytes": sum(r["bytes"] for r in rows)}))
    for row in rows:
        p = RAW / row["path"]
        assert p.stat().st_size == row["bytes"] and digest(p.read_bytes()) == row["sha256"]
    all_raw = [p for p in RAW.rglob("*") if p.is_file()]
    summary = {"schema_version": 1, "captured_utc": recheck["checked_utc"],
               "repository": "adybag14-cyber/termux-hermes", "run_id": 39071928457,
               "url": "https://github.com/adybag14-cyber/termux-hermes/actions/runs/39071928457",
               "head_sha": ledger["head_sha"], "job_id": ledger["job_id"], "workflow_conclusion": "failure",
               "failure": {"stage": "Phonemizer built-wheel retention, before Regex and installed public API",
                           "error": phonemizer["error"],
                           "source": "scripts/compatibility_probe_phonemizer.py:804",
                           "cause": "Path.rename cannot move a wheel from PREFIX/tmp to the separate /out bind mount.",
                           "bounded_followup": "Copy to an exclusively created destination and verify exact source/destination bytes before later wheel and runtime gates."},
               "proved": {"scientific_foundation_cases": 7, "espeak_c_abi_checks": 14,
                          "espeak_source_commit": espeak["source_commit"], "espeak_source_manifest": espeak["source_manifest"],
                          "native_library": espeak["library"], "data_tree": espeak["data_tree"],
                          "compiler_archive_identities": 44, "selected_toolchain_installs": 19,
                          "post_c_abi_provenance_archive_union": 45,
                          "pure_phonemizer_wheel_build_completion": "Logged; output wheel was lost during temporary-directory cleanup after the cross-filesystem rename failed."},
               "not_proved": ["Retained and independently verified built Phonemizer wheel",
                              "Regex native build", "23-distribution installed Phonemizer public API",
                              "Complete NeuTTS engine", "Model inference or synthesis", "Audio I/O",
                              "Physical device behavior", "Release readiness"],
               "source_inputs_receipt": {"path": "run-39071928457/ESPEAK-PROBE-INPUTS.json",
                                         "sha256": digest((RAW / "ESPEAK-PROBE-INPUTS.json").read_bytes())},
               "artifact": {"id": ledger["artifact_id"], "bytes": ledger["artifact_bytes"],
                            "sha256": ledger["artifact_sha256"], "zip_members": 641,
                            "retained_members": 134, "all_member_crc_and_sha256_verified": True,
                            "full_zip_saved_outside_git": str(archive),
                            "full_member_ledger_sha256": digest((RAW / "verified-artifact.json").read_bytes())},
               "native_job_log": ledger["native_job_log"],
               "raw_evidence": {"directory": RAW.relative_to(REPO).as_posix(),
                                "file_count": len(all_raw), "total_bytes": sum(p.stat().st_size for p in all_raw),
                                "saved_files_sha256": digest((RAW / "SAVED-FILES.json").read_bytes()),
                                "result_recheck_sha256": digest((RAW / "VERIFIED-RESULT-RECHECK.json").read_bytes()),
                                "preserved_exact_bytes": True, "binary_wheels_sources_and_data_tree_excluded_from_git": True},
               "earlier_failure_preserved": "audit/neutts-espeak-native-20261017/run-39068675792.json",
               "release_output": False}
    save_new(SUMMARY, encode(summary))
    print(json.dumps({"summary": str(SUMMARY), "summary_bytes": SUMMARY.stat().st_size,
                      "summary_sha256": digest(SUMMARY.read_bytes()),
                      "raw_file_count": len(all_raw), "raw_bytes": sum(p.stat().st_size for p in all_raw),
                      "saved_files_sha256": summary["raw_evidence"]["saved_files_sha256"],
                      "total_file_count": len(all_raw) + 1,
                      "total_bytes": sum(p.stat().st_size for p in all_raw) + SUMMARY.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
