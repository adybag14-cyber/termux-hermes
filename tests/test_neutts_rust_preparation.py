"""Integrity regressions for unpublished native Rust preparation.

All fixtures are local and small. These tests execute no Cargo, source backend,
native Termux component, microphone, model, or release action.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import ssl
import subprocess
import sys
import tarfile
import threading
import time
import tomllib
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


prep = module("_test_rust_prep", "prepare_neutts_rust_sources.py")
native = module("_test_rust_native", "compatibility_probe_neutts_rust.py")
ops = module("_test_rust_ops", "neutts_rust_operations.py")


def archive(members, root="example-1.0.0"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as stream:
        for name, raw, kind in members:
            item = tarfile.TarInfo(root + "/" + name)
            if kind in ("symlink", "hardlink"):
                item.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                item.linkname = "../../outside"
                stream.addfile(item)
            elif kind == "fifo":
                item.type = tarfile.FIFOTYPE
                stream.addfile(item)
            else:
                item.size = len(raw)
                item.mode = 0o755 if kind == "exec" else 0o644
                stream.addfile(item, io.BytesIO(raw))
    return buf.getvalue()


def fixture_crate(tmp_path):
    raw = archive([("Cargo.toml", b'[package]\nname="example"\nversion="1.0.0"\n', "file"),
                   ("src/lib.rs", b"pub fn value() -> u8 { 3 }\n", "file"),
                   ("scripts/check.sh", b"#!/bin/sh\nexit 0\n", "exec")])
    pin = {"name": "example", "version": "1.0.0", "filename": "example-1.0.0.crate",
           "sha256": prep.sha(raw), "bytes": len(raw),
           "url": "https://static.crates.io/crates/example/example-1.0.0.crate"}
    path = tmp_path / pin["filename"]
    path.write_bytes(raw)
    return path, pin


def fixture_wheel(path, *, payload=b"VALUE=3\n", extra=None):
    files = {
        "example/__init__.py": payload,
        "example-1.0.0.dist-info/METADATA":
            b"Metadata-Version: 2.4\nName: example\nVersion: 1.0.0\nRequires-Python: >=3.9\n"
            b"Requires-Dist: packaging>=24; extra == 'build'\n\n",
        "example-1.0.0.dist-info/WHEEL":
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n",
    }
    if extra:
        files.update(extra)
    rn = "example-1.0.0.dist-info/RECORD"
    rows = [[name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(value).digest()).decode().rstrip("="),
             str(len(value))] for name, value in files.items()]
    rows.append([rn, "", ""])
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(rows)
    files[rn] = buf.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, value in files.items():
            out.writestr(name, value)
    return path


def rewrite_wheel(path, name, value):
    with zipfile.ZipFile(path) as source:
        files = {i.filename: source.read(i) for i in source.infolist()}
    files[name] = value
    with zipfile.ZipFile(path, "w") as out:
        for member, raw in files.items():
            out.writestr(member, raw)


def test_frozen_source_closure_and_distinct_capture_stage():
    lock, raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    assert len(raw) == 552620
    assert len(lock["registry"]) == 804
    assert {p["source"] for p in lock["registry"]} == {prep.REGISTRY}
    assert {s["name"] for s in lock["sources"] if s["cargo_lock"]} == set(prep.LOCKED_NAMES)
    assert next(s for s in lock["sources"] if s["name"] == "tiktoken")["cargo_lock"] is None
    assert len(lock["build_apt"]["packages"]) == 47
    assert set(lock["build_apt"]["additional_to_foundation"]) == {
        p["name"] for p in lock["build_apt"]["packages"] if not p["in_foundation"]}
    assert len(lock["build_apt"]["additional_to_foundation"]) == 20
    assert lock["build_apt"]["apt_maturin_cli_installed"] is False
    assert lock["boundaries"]["four_component_runtime_complete"] is False


def test_helper_pins_resolve_actual_reviewed_sources():
    loaded, apt = native.helpers()
    assert loaded.LOCK_SHA256 == prep.LOCK_SHA256
    assert apt.__file__.endswith("validate_neutts_apt_python.py")
    assert native.sha_file(ROOT / "scripts/neutts_rust_operations.py") == native.OPERATIONS_SHA256


@pytest.mark.parametrize("source_name,expected", [
    ("maturin", "55cd5302953baf66ef08c5552c2294944dfe65251bfa51370be83370848c6f56"),
    ("hf-xet", "042146dd9c975cf623bd50a5cdb319d132ec715f6dd770342942992895d59f6f"),
    ("safetensors", "f7d484a57bc394042b3424d57dab0a17d6a343f5e57e30870b9dd72dfb90f6b7"),
    ("tokenizers", "a3ff2022b3790e2f5863fe59732ab76da81dd75bc3a94905127206e87125170d"),
])
def test_embedded_cargo_lock_identities_stay_original(source_name, expected):
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    assert next(s for s in lock["sources"] if s["name"] == source_name)["cargo_lock"]["sha256"] == expected


def test_maturin_bootstrap_retains_original_authored_metadata():
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    source = next(s for s in lock["sources"] if s["name"] == "maturin")
    assert source["expected_tag"] == "cp314-cp314-android_24_arm64_v8a"
    assert source["requires_python"] == ">=3.7"
    assert source["expected_bootstrap_requires_dist"] == [
        "tomli>=1.1.0 ; python_version<'3.11'",
        'ziglang>=0.10.0; extra == "zig"', 'patchelf; extra == "patchelf"']
    assert source["requires_dist"][0] == "tomli>=1.1.0 ; python_full_version < '3.11'"
    assert source["expected_bootstrap_metadata_basis"]["sha256"] == source["pyproject_sha256"]


@pytest.mark.parametrize("value", ["../outside", "/absolute", "a/../b", "a//b",
                                   r"a\b", "C:drive", "a/./b", "a\nb", "", "a/"])
def test_relative_paths_reject_escape_and_aliases(value):
    with pytest.raises(prep.PrepareError):
        prep.safe_relative(value)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_source_archive_rejects_links_and_special_members(kind, tmp_path):
    raw = archive([("Cargo.toml", b"", kind)])
    with pytest.raises(prep.PrepareError):
        prep.archive_files(raw, "example-1.0.0", output=tmp_path / "tree")


@pytest.mark.parametrize("members", [
    [("../outside", b"x", "file")],
    [("a", b"x", "file"), ("a", b"x", "file")],
    [("A", b"x", "file"), ("a", b"x", "file")],
])
def test_source_archive_rejects_traversal_duplicates_and_case_aliases(members, tmp_path):
    with pytest.raises(prep.PrepareError):
        prep.archive_files(archive(members), "example-1.0.0", output=tmp_path / "tree")


def test_original_source_export_is_complete_and_byte_exact(tmp_path):
    path, pin = fixture_crate(tmp_path)
    destination = tmp_path / "source"
    rows = prep.archive_files(path.read_bytes(), "example-1.0.0", output=destination)
    assert len(rows) == 3 and next(r for r in rows if r["path"] == "scripts/check.sh")["executable"]
    source = {"files": rows}
    assert prep.verify_source(destination, source)["files"] == 3
    (destination / "src/lib.rs").write_bytes(b"altered")
    with pytest.raises(prep.PrepareError):
        prep.verify_source(destination, source)


def test_crate_checksum_cannot_authorize_changed_source(tmp_path):
    path, pin = fixture_crate(tmp_path)
    out = tmp_path / "vendor/example-1.0.0"
    prep.export_crate(path, pin, out)
    assert prep.verify_crate(path, pin, out) == 3
    changed = b"pub fn value() -> u8 { 4 }\n"
    (out / "src/lib.rs").write_bytes(changed)
    checksum = json.loads((out / ".cargo-checksum.json").read_bytes())
    checksum["files"]["src/lib.rs"] = prep.sha(changed)
    (out / ".cargo-checksum.json").write_text(json.dumps(checksum))
    with pytest.raises(prep.PrepareError, match="checksum file differs"):
        prep.verify_crate(path, pin, out)


def test_crate_modified_payload_with_original_checksum_is_rejected(tmp_path):
    path, pin = fixture_crate(tmp_path)
    out = tmp_path / "vendor"
    prep.export_crate(path, pin, out)
    (out / "src/lib.rs").write_bytes(b"tampered")
    with pytest.raises(prep.PrepareError, match="inventory differs"):
        prep.verify_crate(path, pin, out)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_crate_inventory_rejects_added_or_missing_files(tmp_path, change):
    path, pin = fixture_crate(tmp_path)
    out = tmp_path / "vendor"
    prep.export_crate(path, pin, out)
    if change == "extra":
        (out / "unexpected").write_bytes(b"unowned")
    else:
        (out / "src/lib.rs").unlink()
    with pytest.raises(prep.PrepareError):
        prep.verify_crate(path, pin, out)


def test_published_crate_cannot_supply_its_own_checksum_metadata(tmp_path):
    raw = archive([("Cargo.toml", b'[package]\nname="example"\nversion="1.0.0"\n', "file"),
                   (".cargo-checksum.json", b"{}", "file")])
    path = tmp_path / "x.crate"
    path.write_bytes(raw)
    pin = {"name": "example", "version": "1.0.0", "sha256": prep.sha(raw), "bytes": len(raw)}
    with pytest.raises(prep.PrepareError, match="unexpectedly supplied"):
        prep.export_crate(path, pin, tmp_path / "vendor")


def test_registry_manifest_identity_must_match_original_lock(tmp_path):
    path, pin = fixture_crate(tmp_path)
    bad = {**pin, "version": "2.0.0"}
    with pytest.raises(prep.PrepareError):
        prep.export_crate(path, bad, tmp_path / "vendor")


def test_cached_download_verifies_bytes_before_copy(tmp_path, monkeypatch):
    cache, output = tmp_path / "cache", tmp_path / "output"
    cache.mkdir()
    output.mkdir()
    raw = b"exact cached input"
    source = cache / "original.crate"
    source.write_bytes(raw)
    pin = {"filename": source.name, "bytes": len(raw), "sha256": prep.sha(raw),
           "url": "https://static.crates.io/crates/original/original.crate"}
    monkeypatch.setattr(prep, "build_opener", lambda *a: pytest.fail("Cache must not use network"))
    result = prep.download(pin, output / source.name, [cache], time.monotonic() + 5)
    assert result["sha256"] == pin["sha256"] and (output / source.name).read_bytes() == raw
    source.write_bytes(b"tampered")
    with pytest.raises(prep.PrepareError):
        prep.download(pin, output / "other.crate", [cache], time.monotonic() + 5)


@pytest.mark.parametrize("case", ["unknown-stage", "existing-output", "overlapping-output"])
def test_fresh_preparation_rejects_before_any_download(tmp_path, monkeypatch, case):
    monkeypatch.setattr(prep, "download", lambda *a: pytest.fail("Rejected preparation cannot download"))
    lock = ROOT / "scripts" / prep.LOCK_FILENAME
    snapshot = ROOT / "audit/neutts-runtime-index-20261017"
    out, stage = tmp_path / "out", "locked-build"
    if case == "unknown-stage":
        stage = "silently-resolve-everything"
    elif case == "existing-output":
        out.mkdir()
    else:
        out = snapshot / "unreviewed-output"
    with pytest.raises(prep.PrepareError):
        prep.prepare(lock, snapshot, out, stage)
    if case == "overlapping-output":
        assert not out.exists()


def test_frozen_lock_mutation_is_rejected(tmp_path):
    path = tmp_path / prep.LOCK_FILENAME
    path.write_bytes((ROOT / "scripts" / prep.LOCK_FILENAME).read_bytes() + b" ")
    with pytest.raises(prep.PrepareError, match="lock changed"):
        prep.load_lock(path)


def test_native_build_cannot_admit_missing_tiktoken_lock(monkeypatch):
    monkeypatch.setattr(native, "native_runtime", lambda: {})
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    with pytest.raises(native.ProbeError, match="Tiktoken lock cannot be built"):
        native.build_one(SimpleNamespace(source_name="tiktoken"), lock, prep)


def test_snapshot_binding_checks_both_exact_bytes_and_signed_index_hash(tmp_path):
    packages = gzip.compress(b"Package: example\nVersion: 1\nArchitecture: aarch64\n\n", mtime=0)
    release = ("SHA256:\n " + prep.sha(packages) + " " + str(len(packages))
               + " main/binary-aarch64/Packages.gz\nSHA512:\n").encode()
    (tmp_path / "InRelease").write_bytes(release)
    (tmp_path / "Packages.gz").write_bytes(packages)
    pins = [{"filename": n, "sha256": prep.sha(v), "bytes": len(v)}
            for n, v in (("InRelease", release), ("Packages.gz", packages))]
    result = prep.snapshot_binding(tmp_path, pins)
    assert result["compressed_hash_binding_verified"] and not result["openpgp_verified_by_this_host_step"]
    (tmp_path / "extra").write_bytes(b"unreviewed")
    with pytest.raises(prep.PrepareError, match="Snapshot directory changed"):
        prep.snapshot_binding(tmp_path, pins)


def test_wheel_crc_record_and_original_metadata_are_checked(tmp_path):
    path = fixture_wheel(tmp_path / "example-1.0.0-py3-none-any.whl")
    facts = prep.wheel_facts(path)
    assert facts["name"] == "example" and facts["version"] == "1.0.0"
    assert facts["requires_dist"] == ["packaging>=24; extra == 'build'"]
    assert prep.verify_wheel(path, facts) == facts
    rewrite_wheel(path, "example/__init__.py", b"changed bytes\n")
    with pytest.raises(prep.PrepareError, match="RECORD hash/size mismatch"):
        prep.wheel_facts(path)


def test_wheel_declared_metadata_cannot_change_even_with_valid_new_record(tmp_path):
    path = fixture_wheel(tmp_path / "example-1.0.0-py3-none-any.whl")
    facts = prep.wheel_facts(path)
    fixture_wheel(path, extra={"example-1.0.0.dist-info/METADATA":
                              b"Metadata-Version: 2.4\nName: example\nVersion: 1.0.0\nRequires-Python: >=3.9\n\n"})
    with pytest.raises(prep.PrepareError, match="artifact identity differs"):
        prep.verify_wheel(path, facts)


def test_clean_environment_removes_platform_tls_and_cargo_overrides(tmp_path, monkeypatch):
    for name in ("PYTHONHOME", "PYTHONPATH", "_PYTHON_HOST_PLATFORM", "PYO3_USE_ABI3_FORWARD_COMPATIBILITY",
                 "RUSTC_WRAPPER", "CARGO_UNSTABLE_ALLOW_FEATURES", "SSL_CERT_FILE", "HTTPS_PROXY",
                 "CARGO_HTTP_SSL_VERIFY", "MATURIN_SETUP_ARGS", "OPENSSL_NO_VERIFY"):
        monkeypatch.setenv(name, "unreviewed")
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    env = native.clean_environment(lock, tmp_path)
    assert env["CARGO_NET_OFFLINE"] == "true"
    assert env["OPENSSL_STATIC"] == "0" and env["OPENSSL_NO_VENDOR"] == "1"
    assert env["MATURIN_NO_INSTALL_RUST"] == "1" and "ANDROID_API_LEVEL" not in env
    assert env["CARGO_BUILD_TARGET"] == "aarch64-linux-android"
    assert not any(k in env for k in ("PYTHONHOME", "PYTHONPATH", "_PYTHON_HOST_PLATFORM",
                                     "PYO3_USE_ABI3_FORWARD_COMPATIBILITY", "RUSTC_WRAPPER",
                                     "SSL_CERT_FILE", "HTTPS_PROXY", "CARGO_HTTP_SSL_VERIFY",
                                     "MATURIN_SETUP_ARGS", "OPENSSL_NO_VERIFY"))
    online = native.clean_environment(lock, tmp_path, online_lock_capture=True)
    assert "CARGO_NET_OFFLINE" not in online


def test_cargo_directory_source_is_explicit_fresh_and_path_safe(tmp_path):
    vendor = tmp_path / "verified-vendor"
    vendor.mkdir()
    home = tmp_path / "fresh-home"
    record = native.cargo_source_config(home, vendor)
    config = tomllib.loads((home / "config.toml").read_text())
    assert config["source"]["crates-io"]["replace-with"] == "reviewed-directory"
    assert Path(config["source"]["reviewed-directory"]["directory"]) == vendor.resolve()
    assert record["sha256"] == native.sha_file(home / "config.toml")
    with pytest.raises(native.ProbeError, match="fresh Cargo home"):
        native.cargo_source_config(home, vendor)


def tls_child(case, accepted):
    return {"stage": "hf-xet-token-refresh", "expected_case": case, "accepted": accepted,
            "exception_type": None if accepted else "RuntimeError"}


def tls_server(valid):
    return {"requests": [{"method": "GET", "path": "/token"}] if valid else [],
            "handshakes": 1 if valid else 0,
            "tls_failures": [] if valid else [{"reason": "TLSV1_ALERT_UNKNOWN_CA"}]}


@pytest.mark.parametrize("case", ["trusted", "untrusted", "wrong-hostname"])
def test_tls_gate_accepts_only_observed_expected_transport_result(case):
    assert ops.verify_tls_outcome(case, tls_child(case, case == "trusted"), tls_server(case == "trusted"))


@pytest.mark.parametrize("case,result,server", [
    ("trusted", tls_child("trusted", True), {"requests": [], "handshakes": 0, "tls_failures": []}),
    ("untrusted", tls_child("untrusted", True), tls_server(True)),
    ("wrong-hostname", tls_child("wrong-hostname", False),
     {"requests": [], "handshakes": 0, "tls_failures": [{"reason": "UNEXPECTED_EOF_WHILE_READING"}]}),
    ("untrusted", {"stage": "import", "expected_case": "untrusted", "accepted": False}, tls_server(False)),
    ("untrusted", tls_child("untrusted", False),
     {"requests": [{"method": "GET", "path": "/token"}], "handshakes": 1,
      "tls_failures": [{"reason": "TLSV1_ALERT_UNKNOWN_CA"}]}),
])
def test_tls_gate_refuses_false_positive_rejections(case, result, server):
    with pytest.raises(RuntimeError):
        ops.verify_tls_outcome(case, result, server)


def test_real_local_certificate_fixture_validates_chain_and_hostname(tmp_path, monkeypatch):
    openssl = os.environ.get("HERMES_RUST_TLS_OPENSSL") or shutil.which("openssl")
    assert openssl, "Host integrity gate requires OpenSSL for its real local certificate fixture"
    executable = Path(openssl)
    monkeypatch.setattr(ops, "PREFIX", executable.parent.parent)
    def run(command, label, timeout, env=None):
        # Only this selected host fixture command is substituted for the native APT
        # OpenSSL path. No Termux, source backend, or Cargo command is executed.
        command = [str(executable), *command[1:]]
        completed = subprocess.run(command, capture_output=True, timeout=timeout, env=env)
        assert completed.returncode == 0, completed.stderr.decode(errors="replace")
        return {"exit_code": completed.returncode}
    certs = tmp_path / "certificates"
    records = ops.issue_certificates(certs, tmp_path / "public-certificates", run)
    assert len(records) == 3 and not list((tmp_path / "public-certificates").glob("*.key"))
    controls = []
    for case in ("trusted", "untrusted", "wrong-hostname"):
        server = ops.TokenServer(certs / (case + ".pem"), certs / (case + ".key"), tmp_path / "cas")
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        worker.start()
        try:
            url = "https://127.0.0.1:" + str(server.server_address[1]) + "/token"
            value = ops.python_tls_control(url, certs / "trusted-ca.pem", case == "trusted")
            controls.append((case, value))
            if case != "trusted":
                assert server.requests == [] and value["verify_code"] != 0
        finally:
            server.shutdown()
            server.server_close()
            worker.join(3)
            assert not worker.is_alive()
    assert controls[0][1]["accepted"] is True
    assert controls[1][1]["accepted"] is controls[2][1]["accepted"] is False
    assert controls[1][1]["verify_code"] != controls[2][1]["verify_code"]


def test_failed_subprocess_retains_full_raw_logs(tmp_path):
    code = "import sys;print('before failure',flush=True);print('actual cause',file=sys.stderr,flush=True);raise SystemExit(7)"
    with pytest.raises(native.ProbeError, match="exit code 7"):
        native.bounded_command([sys.executable, "-I", "-B", "-c", code], tmp_path, "failure", 10)
    assert b"before failure" in (tmp_path / "failure.stdout.log").read_bytes()
    assert b"actual cause" in (tmp_path / "failure.stderr.log").read_bytes()


def test_timeout_retains_logs_and_stops_owned_child(tmp_path, monkeypatch):
    if os.name == "nt":
        monkeypatch.setattr(native.os, "killpg", lambda pid, sig: os.kill(pid, signal.SIGTERM), raising=False)
    code = "import sys,time;print('timeout stdout',flush=True);print('timeout stderr',file=sys.stderr,flush=True);time.sleep(15)"
    with pytest.raises(native.ProbeError, match="exit code 124"):
        native.bounded_command([sys.executable, "-I", "-B", "-c", code], tmp_path, "timeout", 0.5)
    assert b"timeout stdout" in (tmp_path / "timeout.stdout.log").read_bytes()
    assert b"timeout stderr" in (tmp_path / "timeout.stderr.log").read_bytes()


def test_workflow_preserves_preparation_and_two_independent_stages():
    import yaml
    value = yaml.load((ROOT / ".github/workflows/neutts-rust-components.yml").read_text(), Loader=yaml.BaseLoader)
    assert value["permissions"] == {"contents": "read"}
    assert value["on"]["push"]["branches"] == ["prepare/termux-compatibility-next-stable"]
    assert value["on"]["workflow_dispatch"]["inputs"]["stage"]["options"] == ["all", "locked-build", "tiktoken-lock"]
    job = value["jobs"]["native-rust"]
    assert job["runs-on"] == "ubuntu-24.04-arm" and job["strategy"]["fail-fast"] == "false"
    assert job["steps"][0]["with"]["persist-credentials"] == "false"
    assert job["steps"][-1]["if"] == "always()"
    assert "release" not in json.dumps(value["permissions"])


def test_tree_inventory_uses_canonical_posix_string_order(tmp_path):
    names = ["Cargo.toml", "README.md", "deny.toml", "docs.md", "docs/README.md", "src/lib.rs"]
    raw = archive([(name, name.encode(), "file") for name in names])
    root = tmp_path / "canonical-source"
    expected = prep.archive_files(raw, "example-1.0.0", output=root)
    actual = prep.tree_files(root)
    assert [r["path"] for r in actual] == sorted(names)
    prep.same_files(actual, expected)


def test_tls_control_alert_cannot_be_misattributed_to_client(tmp_path, monkeypatch):
    """A delayed control alert must not turn an unrelated client error into a pass."""
    openssl = os.environ.get("HERMES_RUST_TLS_OPENSSL") or shutil.which("openssl")
    assert openssl
    servers, state = [], {}
    original_server = ops.TokenServer
    original_control = ops.python_tls_control
    def server_factory(*args):
        value = original_server(*args)
        servers.append(value)
        return value
    def control(url, certificate, expected_valid):
        state["control_server"] = next(s for s in servers
                                       if ":" + str(s.server_address[1]) + "/" in url)
        return original_control(url, certificate, expected_valid)
    monkeypatch.setattr(ops, "TokenServer", server_factory)
    monkeypatch.setattr(ops, "python_tls_control", control)
    def run(command, label, timeout, env=None):
        if "--tls-client" not in command:
            completed = subprocess.run([openssl, *command[1:]], capture_output=True, timeout=timeout)
            assert completed.returncode == 0, completed.stderr.decode(errors="replace")
            return {"exit_code": 0}
        case = command[command.index("--case") + 1]
        output = Path(command[command.index("--out") + 1])
        if case == "trusted":
            url = command[command.index("--url") + 1]
            assert original_control(url, Path(env["SSL_CERT_FILE"]), True)["accepted"]
            result = tls_child(case, True)
        else:
            assert case == "untrusted"
            # Model an alert arriving from the already exercised control connection.
            # The tested client deliberately makes no TLS connection at all.
            state["control_server"].tls_failures.append({"reason": "TLSV1_ALERT_UNKNOWN_CA"})
            result = {**tls_child(case, False), "error": "unrelated client failure"}
        output.write_text(json.dumps(result))
        return {"exit_code": 0}
    work, evidence = tmp_path / "work", tmp_path / "evidence"
    work.mkdir()
    evidence.mkdir()
    with pytest.raises(RuntimeError, match="actual certificate-related handshake alert"):
        ops.tls_operation(work, evidence, {}, run)


def test_real_ar_archive_member_and_control_contract(tmp_path):
    """Exercise the real ar + compressed tar parser, including identity rejection."""
    def tar_bytes(name, value, compression):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:" + compression) as stream:
            member = tarfile.TarInfo(name)
            member.size = len(value)
            stream.addfile(member, io.BytesIO(value))
        return buffer.getvalue()
    control = b"Package: parser-fixture\nVersion: 1.0-1\nArchitecture: aarch64\n"
    member = "/data/data/com.termux/files/usr/lib/libfixture.so"
    contents = b"exact selected payload"
    entries = [("debian-binary", b"2.0\n"),
               ("control.tar.gz", tar_bytes("./control", control, "gz")),
               ("data.tar.xz", tar_bytes("." + member, contents, "xz"))]
    raw = b"!<arch>\n"
    for name, value in entries:
        header = (f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(value):<10}" + "`\n").encode()
        assert len(header) == 60
        raw += header + value + (b"\n" if len(value) % 2 else b"")
    path = tmp_path / "parser-fixture_1.0-1_aarch64.deb"
    path.write_bytes(raw)
    pin = {"name": "parser-fixture", "version": "1.0-1", "architecture": "aarch64",
           "bytes": len(raw), "sha256": prep.sha(raw)}
    assert native.ar_data_members(path, pin, {member}) == {member: contents}
    with pytest.raises(native.ProbeError, match="control identity differs"):
        native.ar_data_members(path, {**pin, "version": "2.0-1"}, {member})
    with pytest.raises(native.ProbeError, match="Incomplete APT member inventory"):
        native.ar_data_members(path, pin, {member, member + ".missing"})


def test_actual_installed_inventory_executes_wheel_adapter(tmp_path, monkeypatch):
    wheel = fixture_wheel(tmp_path / "example-1.0.0-py3-none-any.whl")
    package = {**prep.wheel_facts(wheel), "wheel_path": str(wheel)}
    environment, apt_prefix = tmp_path / "venv", tmp_path / "apt-prefix"
    site = environment / "lib/python3.14/site-packages"
    site.mkdir(parents=True)
    apt_prefix.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            path = site / item.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(item))
    actual_distributions = list(native.importlib.metadata.distributions(path=[str(site)]))
    assert len(actual_distributions) == 1
    monkeypatch.setattr(native, "PREFIX", apt_prefix.resolve())
    monkeypatch.setattr(native.sys, "prefix", str(environment))
    monkeypatch.setattr(native.sys, "base_prefix", str(apt_prefix))
    monkeypatch.setattr(native.importlib.metadata, "distributions", lambda: iter(actual_distributions))
    manifest = {"names": ["example"], "wheels": [package]}
    result = native.installed_inventory(manifest, prep)
    assert result["status"] == "passed" and result["actual_visible_distribution_count"] == 1
    assert result["verified_site_files"] == 4 and result["declared_metadata_modified"] is False
    (site / "example/__init__.py").write_bytes(b"changed installed source\n")
    with pytest.raises(native.ProbeError, match="Installed wheel file changed"):
        native.installed_inventory(manifest, prep)


def test_frozen_apt_epoch_names_are_portable_bijective_and_metadata_exact():
    lock, raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    pins = lock["build_apt"]["packages"]
    before = deepcopy(pins)
    names = prep.apt_archive_names(pins)
    assert len(names) == len(set(names.values())) == 47
    changed = {p["name"]: names[p["filename"]] for p in pins
               if names[p["filename"]] != Path(p["filename"]).name}
    assert changed == {
        "ca-certificates": "ca-certificates_1%3A2026.09.25_all.deb",
        "openssl": "openssl_1%3A3.6.5_aarch64.deb",
        "openssl-tool": "openssl-tool_1%3A3.6.5_aarch64.deb",
    }
    for p in pins:
        assert names[p["filename"]].replace("%3A", ":") == Path(p["filename"]).name
        prep.safe_relative(names[p["filename"]])
    assert pins == before
    assert prep.sha(raw) == prep.LOCK_SHA256
    with pytest.raises(prep.PrepareError):
        prep.safe_relative("openssl_1:3.6.5_aarch64.deb")


def epoch_archive_fixture():
    filename = "pool/main/f/fixture/fixture_1:1.0_all.deb"
    raw = b"owned epoch archive copy fixture\n"
    return raw, {"name": "fixture", "version": "1:1.0", "architecture": "all",
                 "filename": filename,
                 "url": "https://packages.termux.dev/apt/termux-main/" + filename,
                 "bytes": len(raw), "sha256": prep.sha(raw)}


@pytest.mark.parametrize("field,value", [
    ("filename", "pool/main/f/fixture/../fixture_1:1.0_all.deb"),
    ("filename", "pool/main/f/fixture/fixture_1%3A1.0_all.deb"),
    ("filename", "pool/main/f/fixture/fixture_1:1.0_all.deb:stream"),
    ("url", "https://unreviewed.example/fixture_1:1.0_all.deb"),
    ("version", "1:"),
])
def test_apt_cache_mapping_rejects_escape_alias_and_false_identity(field, value):
    _, pin = epoch_archive_fixture()
    with pytest.raises(prep.PrepareError):
        prep.apt_archive_filename({**pin, field: value})


def test_apt_cache_mapping_rejects_duplicate_and_case_aliases():
    _, pin = epoch_archive_fixture()
    with pytest.raises(prep.PrepareError, match="Duplicate or aliased"):
        prep.apt_archive_names([pin, pin])
    pins = []
    for version in ("1:1a", "1:1A"):
        filename = "pool/main/f/fixture/fixture_" + version + "_all.deb"
        pins.append({**pin, "version": version, "filename": filename,
                     "url": "https://packages.termux.dev/apt/termux-main/" + filename})
    with pytest.raises(prep.PrepareError, match="Duplicate or aliased"):
        prep.apt_archive_names(pins)


@pytest.mark.parametrize("route", ["verified-cache", "original-url"])
def test_epoch_download_preserves_bytes_and_original_request_identity(tmp_path, monkeypatch, route):
    raw, original = epoch_archive_fixture()
    before = deepcopy(original)
    local = prep.apt_archive_filename(original)
    pin = {**original, "filename": local}
    cache, output = tmp_path / "cache", tmp_path / "output"
    cache.mkdir()
    output.mkdir()
    requests = []
    if route == "verified-cache":
        (cache / local).write_bytes(raw)
        monkeypatch.setattr(prep, "build_opener", lambda *a: pytest.fail("Verified cache must not access network"))
    else:
        class Response(io.BytesIO):
            status = 200
        def opened(request, timeout):
            requests.append((request.full_url, timeout))
            return Response(raw)
        monkeypatch.setattr(prep, "build_opener", lambda *a: SimpleNamespace(open=opened))
    result = prep.download(pin, output / local, [cache], time.monotonic() + 5)
    assert (output / local).read_bytes() == raw and result["sha256"] == original["sha256"]
    assert result["filename"] == local and original == before
    assert requests == ([] if route == "verified-cache" else [(original["url"], 30)])


@pytest.mark.parametrize("stage", ["locked-build", "tiktoken-lock"])
def test_both_real_stage_download_plans_preserve_all_original_apt_pins(tmp_path, monkeypatch, stage):
    """Run actual preparation through all download planning; stop before export."""
    lock, raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    before = deepcopy(lock)
    recorded = []
    verified = prep.verified_bytes
    class DownloadsPlanned(Exception):
        pass
    def acquire(pin, destination, caches, deadline):
        recorded.append((deepcopy(pin), destination))
        return {"filename": destination.name, "bytes": pin.get("bytes"),
                "sha256": pin["sha256"]}
    def retained(path, pin):
        if pin["filename"] in ("InRelease", "Packages.gz"):
            return verified(path, pin)
        raise DownloadsPlanned()
    monkeypatch.setattr(prep, "download", acquire)
    monkeypatch.setattr(prep, "verified_bytes", retained)
    snapshot = ROOT / "audit/neutts-runtime-index-20261017"
    apt_names = prep.apt_archive_names(lock["build_apt"]["packages"])
    expected_apt = {apt_names[p["filename"]]: {**p, "filename": apt_names[p["filename"]]}
                    for p in lock["build_apt"]["packages"]}
    expected_sources = {s["artifact"]["filename"] for s in lock["sources"]
                        if (s["name"] == "tiktoken") == (stage == "tiktoken-lock")}
    first_plan = None
    for iteration in (1, 2):
        recorded.clear()
        output = tmp_path / ("fresh-" + str(iteration))
        with pytest.raises(DownloadsPlanned):
            prep.prepare(ROOT / "scripts" / prep.LOCK_FILENAME, snapshot, output, stage)
        apt = {path.name: pin for pin, path in recorded if path.parent.name == "apt-archives"}
        assert apt == expected_apt and len(apt) == 47
        assert {path.name for pin, path in recorded if path.parent.name == "archives"} == expected_sources
        assert len([path for pin, path in recorded if path.parent.name == "crates"]) == (804 if stage == "locked-build" else 0)
        assert len([path for pin, path in recorded if path.parent.name == "wheels"]) == (5 if stage == "locked-build" else 0)
        plan = sorted((path.relative_to(output).as_posix(), json.dumps(pin, sort_keys=True))
                      for pin, path in recorded)
        assert first_plan is None or plan == first_plan
        first_plan = plan
        assert not (output / "RUST-PREPARED-INPUTS.json").exists()
        count = len(recorded)
        with pytest.raises(prep.PrepareError, match="fresh preparation"):
            prep.prepare(ROOT / "scripts" / prep.LOCK_FILENAME, snapshot, output, stage)
        assert len(recorded) == count
    assert lock == before and prep.sha(raw) == prep.LOCK_SHA256


def test_native_writable_apt_copy_restores_index_basename_and_preserves_input(tmp_path, monkeypatch):
    raw, pin = epoch_archive_fixture()
    source_dir, work = tmp_path / "inputs", tmp_path / "native-work"
    source_dir.mkdir()
    work.mkdir()
    source = source_dir / prep.apt_archive_filename(pin)
    source.write_bytes(raw)
    requested, stored = [], {}
    copy, digest = shutil.copyfile, native.sha_file
    def copy_to_native_name(origin, target):
        requested.append(target.name)
        # Windows cannot represent an epoch colon in a normal filename. Preserve
        # the requested native name and adapt only this fixture's physical path.
        actual = target.with_name(target.name.replace(":", "%3A")) if os.name == "nt" else target
        stored[str(target)] = actual
        return copy(origin, actual)
    monkeypatch.setattr(native.shutil, "copyfile", copy_to_native_name)
    monkeypatch.setattr(native, "sha_file", lambda path: digest(stored.get(str(path), path)))
    result = native.stage_install_archives(SimpleNamespace(apt_archives=source_dir), [pin], work)
    assert requested == ["fixture_1:1.0_all.deb"]
    assert (result / "partial").is_dir()
    assert source.read_bytes() == raw
    assert list(stored.values())[0].read_bytes() == raw
    assert digest(list(stored.values())[0]) == pin["sha256"]


def apt_index_row(pin, **changed):
    fields = {"Package": pin["name"], "Version": pin["version"],
              "Architecture": pin["architecture"], "Filename": pin["filename"],
              "Size": str(pin["bytes"]), "SHA256": pin["sha256"]}
    fields.update(changed)
    return "".join(key + ": " + value + "\n" for key, value in fields.items()).encode()


def selected_index_fixture():
    raw, pin = epoch_archive_fixture()
    selected = apt_index_row(pin)
    other_version = apt_index_row(pin, Version="1:0.9",
                                  Filename="pool/main/f/fixture/fixture_1:0.9_all.deb",
                                  SHA256="7" * 64, Size="72")
    unrelated = apt_index_row(pin, Package="unrelated", Version="2.0",
                              Filename="pool/main/u/unrelated/unrelated_2.0_aarch64.deb",
                              Architecture="aarch64")
    unrelated_old = apt_index_row(pin, Package="unrelated", Version="1.0",
                                  Filename="pool/main/u/unrelated/unrelated_1.0_aarch64.deb",
                                  Architecture="aarch64")
    return pin, selected, b"\n".join((other_version, unrelated, unrelated_old))


def test_actual_frozen_index_preserves_all_rows_and_matches_all_47_selections():
    lock, lock_raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    snapshot = ROOT / "audit/neutts-runtime-index-20261017/Packages.gz"
    compressed = snapshot.read_bytes()
    index_pin = next(p for p in lock["build_apt"]["snapshot"] if p["filename"] == "Packages.gz")
    assert len(compressed) == index_pin["bytes"] and prep.sha(compressed) == index_pin["sha256"]
    raw, pins = gzip.decompress(compressed), deepcopy(lock["build_apt"]["packages"])
    before = bytes(raw), deepcopy(pins)
    assert native.verify_selected_apt_index(raw, pins) == {
        "target_record_count": 3011, "target_package_name_count": 3008,
        "selected_record_count": 47}
    assert (raw, pins) == before
    assert snapshot.read_bytes() == compressed and prep.sha(lock_raw) == prep.LOCK_SHA256


def test_selected_apt_index_accepts_other_versions_without_rewriting_index_or_pins():
    pin, selected, others = selected_index_fixture()
    raw, pins = selected + b"\n" + others, [pin]
    before = bytes(raw), deepcopy(pins)
    assert native.verify_selected_apt_index(raw, pins) == {
        "target_record_count": 4, "target_package_name_count": 2, "selected_record_count": 1}
    assert (raw, pins) == before


@pytest.mark.parametrize("case", ["missing", "exact-duplicate", "conflicting-selected-row"])
def test_selected_apt_index_rejects_missing_duplicate_or_conflicting_selected_identity(case):
    pin, selected, others = selected_index_fixture()
    if case == "missing":
        raw = others
    elif case == "exact-duplicate":
        raw = selected + b"\n" + others + b"\n" + selected
    else:
        raw = selected + b"\n" + others + b"\n" + apt_index_row(pin, SHA256="0" * 64)
    with pytest.raises(native.ProbeError, match="selected identity is missing or duplicated"):
        native.verify_selected_apt_index(raw, [pin])


@pytest.mark.parametrize("field,value", [
    ("Filename", "pool/main/f/fixture/changed_1:1.0_all.deb"),
    ("Size", "123456789"),
    ("SHA256", "0" * 64),
])
def test_selected_apt_index_rejects_changed_single_selected_archive(field, value):
    pin, selected, others = selected_index_fixture()
    with pytest.raises(native.ProbeError, match="source index pin differs"):
        native.verify_selected_apt_index(apt_index_row(pin, **{field: value}) + b"\n" + others, [pin])


@pytest.mark.parametrize("field", ["Package", "Version", "Architecture", "Filename", "Size", "SHA256"])
def test_selected_apt_index_rejects_repeated_selected_fields(field):
    pin, selected, others = selected_index_fixture()
    # Even an identical repeated header is ambiguous input, not a second valid identity.
    repeated = next(line for line in selected.splitlines(keepends=True)
                    if line.startswith((field + ":").encode()))
    with pytest.raises(native.ProbeError, match="source index pin differs or has repeated fields"):
        native.verify_selected_apt_index(selected + repeated + b"\n" + others, [pin])


def test_selected_apt_index_rejects_duplicate_frozen_selection():
    pin, selected, others = selected_index_fixture()
    with pytest.raises(native.ProbeError, match="Duplicate frozen APT selected identity"):
        native.verify_selected_apt_index(selected + b"\n" + others, [pin, deepcopy(pin)])


@pytest.mark.parametrize("acquired", ["exact", "changed-packages", "changed-inrelease"])
def test_real_signed_snapshot_preserves_authentication_and_acquired_byte_oracles(tmp_path, monkeypatch, acquired):
    """Run production parsing and retained-byte gates; only native APT is a fixture."""
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    inputs, work, output = tmp_path / "inputs", tmp_path / "work", tmp_path / "out"
    snapshot = inputs / "snapshot"
    snapshot.mkdir(parents=True)
    work.mkdir()
    output.mkdir()
    original = ROOT / "audit/neutts-runtime-index-20261017"
    for filename in ("InRelease", "Packages.gz"):
        shutil.copyfile(original / filename, snapshot / filename)
    raw = gzip.decompress((snapshot / "Packages.gz").read_bytes())
    calls = []
    def update(command, out, label, timeout):
        assert command[0] == str(native.PREFIX / "bin/apt-get") and command[-1] == "update"
        assert (out, label, timeout) == (output, "rust-frozen-signed-index", 90)
        for setting in (
            "Acquire::AllowInsecureRepositories=false",
            "Acquire::AllowDowngradeToInsecureRepositories=false",
            "Acquire::AllowWeakRepositories=false",
            "APT::Get::AllowUnauthenticated=false",
            "APT::Update::Error-Mode=any",
        ):
            assert command[command.index(setting) - 1] == "-o"
        repository = work / "signed-repository/dists/stable"
        assert (repository / "InRelease").read_bytes() == (snapshot / "InRelease").read_bytes()
        assert (repository / "main/binary-aarch64/Packages.gz").read_bytes() == (snapshot / "Packages.gz").read_bytes()
        lists = work / "apt-lists"
        retained = (snapshot / "InRelease").read_bytes()
        (lists / "fixture_InRelease").write_bytes(retained + (b"\nchanged" if acquired == "changed-inrelease" else b""))
        (lists / "fixture_Packages").write_bytes(raw)
        calls.append("update-fixture")
        return {"exit_code": 0, "fixture_only": True}
    def acquired_bytes(command, **kwargs):
        assert command == [str(native.PREFIX / "lib/apt/apt-helper"), "cat-file",
                           str(work / "apt-lists/fixture_Packages")]
        assert kwargs == {"capture_output": True, "timeout": 30, "check": False}
        calls.append("acquired-byte-fixture")
        return SimpleNamespace(returncode=0, stdout=raw + (b"\nchanged" if acquired == "changed-packages" else b""),
                               stderr=b"")
    monkeypatch.setattr(native, "bounded_command", update)
    monkeypatch.setattr(native.subprocess, "run", acquired_bytes)
    args = SimpleNamespace(inputs=inputs, out=output)
    if acquired == "exact":
        options, result = native.signed_snapshot(args, lock, work)
        assert result["matched_archives"] == 47 and result["insecure_repository_exceptions"] is False
        assert result["selected_index"] == {"target_record_count": 3011,
                                             "target_package_name_count": 3008, "selected_record_count": 47}
        assert result["packages_uncompressed_sha256"] == prep.sha(raw)
        assert calls == ["update-fixture", "acquired-byte-fixture"]
    else:
        message = "APT-acquired package index differs" if acquired == "changed-packages" else "APT did not retain the exact authenticated InRelease"
        with pytest.raises(native.ProbeError, match=message):
            native.signed_snapshot(args, lock, work)
        assert calls == (["update-fixture", "acquired-byte-fixture"] if acquired == "changed-packages" else ["update-fixture"])
    assert all((snapshot / filename).read_bytes() == (original / filename).read_bytes()
               for filename in ("InRelease", "Packages.gz"))


def test_openssl_tool_is_the_only_frozen_input_closure_change():
    lock, raw = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    original = deepcopy(lock)
    tool = next(p for p in lock["build_apt"]["packages"] if p["name"] == "openssl-tool")
    library = next(p for p in lock["build_apt"]["packages"] if p["name"] == "openssl")
    assert tool["version"] == library["version"] == "1:3.6.5"
    assert tool["depends"] == "openssl (= 1:3.6.5)"
    assert tool["bytes"] == 278628
    assert tool["sha256"] == "91b6fd0e86f2585447a44c42a496e8c4da364ff3d7b13bec236a7e65be108109"
    assert tool["in_foundation"] is False and tool["pre_depends"] == ""
    assert original["build_apt"]["roots"].pop("openssl-tool") == tool["version"]
    original["build_apt"]["additional_to_foundation"].remove("openssl-tool")
    original["build_apt"]["packages"].remove(tool)
    # Removing exactly the reviewed addition reproduces every original lock byte,
    # including all 46 archive records, source files, Cargo locks and runtime pins.
    original_raw = (json.dumps(original, sort_keys=True, indent=2) + "\n").encode()
    assert prep.sha(original_raw) == "c72d8bfa5f9ae86205443b2c7c19892be77a2879ec7604ccd77aeda2a94775af"
    assert prep.sha(raw) == prep.LOCK_SHA256


def compiler_archive_fixture(directory, member, contents, *, linked=False):
    """Build a real ar/control/data fixture for the production archive reader."""
    directory.mkdir(parents=True, exist_ok=True)
    name = "compiler-input-fixture"
    control = f"Package: {name}\nVersion: 1.0-1\nArchitecture: aarch64\n".encode()
    values = []
    for archive_name, member_name, payload in (
            ("control.tar.gz", "./control", control),
            ("data.tar.gz", "." + member, contents)):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as stream:
            item = tarfile.TarInfo(member_name)
            if archive_name.startswith("data.") and linked:
                item.type, item.linkname = tarfile.SYMTYPE, "unreviewed-target"
                stream.addfile(item)
            else:
                item.size = len(payload)
                stream.addfile(item, io.BytesIO(payload))
        values.append((archive_name, buffer.getvalue()))
    raw = b"!<arch>\n"
    for entry, value in [("debian-binary", b"2.0\n"), *values]:
        header = (f"{entry + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(value):<10}" + "\x60\n").encode()
        assert len(header) == 60
        raw += header + value + (b"\n" if len(value) % 2 else b"")
    path = directory / (name + "_1.0-1_aarch64.deb")
    path.write_bytes(raw)
    pin = {"name": name, "version": "1.0-1", "architecture": "aarch64",
           "bytes": len(raw), "sha256": prep.sha(raw)}
    return path, pin


@pytest.mark.parametrize("fault", [
    "valid", "wrong-archive", "wrong-path", "short-bound", "long-bound", "wrong-body-hash", "symlink",
])
def test_exact_large_member_bounds_execute_real_archive_control_and_payload(tmp_path, monkeypatch, fault):
    member = "/data/data/com.termux/files/usr/lib/compiler-fixture.rmeta"
    contents = b"reviewed larger compiler fixture"
    path, pin = compiler_archive_fixture(tmp_path, member, contents, linked=fault == "symlink")
    identity = (pin["sha256"], member)
    exact = {"bytes": len(contents), "sha256": prep.sha(contents)}
    if fault == "wrong-archive":
        identity = ("0" * 64, member)
    elif fault == "wrong-path":
        identity = (pin["sha256"], member + ".other")
    elif fault == "short-bound":
        exact["bytes"] -= 1
    elif fault == "long-bound":
        exact["bytes"] += 1
    elif fault == "wrong-body-hash":
        exact["sha256"] = "0" * 64
    assert native.APT_MEMBER_MAX_BYTES == 64_000_000
    # Scale only the resource bound and reviewed fixture identity. The production
    # ar/control parser, exact length check and actual payload hashing still run.
    monkeypatch.setattr(native, "APT_MEMBER_MAX_BYTES", 16)
    monkeypatch.setattr(native, "APT_EXACT_LARGE_MEMBERS", {identity: exact})
    if fault == "valid":
        assert native.ar_data_members(path, pin, {member}) == {member: contents}
        with pytest.raises(native.ProbeError, match="control identity differs"):
            native.ar_data_members(path, {**pin, "version": "2.0-1"}, {member})
    else:
        with pytest.raises(native.ProbeError):
            native.ar_data_members(path, pin, {member})


def test_unlisted_large_member_still_fails_and_small_member_still_verifies(tmp_path, monkeypatch):
    member = "/data/data/com.termux/files/usr/lib/compiler-fixture.rmeta"
    monkeypatch.setattr(native, "APT_MEMBER_MAX_BYTES", 16)
    path, pin = compiler_archive_fixture(tmp_path / "large", member, b"unlisted" * 8)
    with pytest.raises(native.ProbeError, match="Invalid selected APT native member"):
        native.ar_data_members(path, pin, {member})
    path, pin = compiler_archive_fixture(tmp_path / "small", member, b"small")
    assert native.ar_data_members(path, pin, {member}) == {member: b"small"}


@pytest.mark.parametrize("kind,status,message", [
    ("missing", "missing-file", "input is missing"),
    ("directory", "not-regular-file", "not a regular file"),
    ("escaped-link", "escaped-prefix", "escaped prefix"),
    ("dangling-link", "missing-file", "input is missing"),
    ("outside-file", "escaped-prefix", "escaped prefix"),
])
def test_compiler_path_diagnostics_retain_original_and_resolved_before_rejection(tmp_path, monkeypatch, kind, status, message):
    prefix = (tmp_path / "prefix").resolve()
    prefix.mkdir()
    good = prefix / "good"
    good.write_bytes(b"owned fixture")
    candidate = prefix / "candidate"
    if kind == "directory":
        candidate.mkdir()
    elif kind == "escaped-link":
        target = tmp_path / "outside"
        target.write_bytes(b"outside fixture")
        candidate.symlink_to(target)
    elif kind == "dangling-link":
        candidate.symlink_to(prefix / "absent")
    elif kind == "outside-file":
        candidate = tmp_path / "outside"
        candidate.write_bytes(b"outside fixture")
    monkeypatch.setattr(native, "PREFIX", prefix)
    diagnostic = tmp_path / "paths.json"
    apt = SimpleNamespace(collect_owners=lambda paths: pytest.fail("Invalid paths must fail before owner admission"))
    with pytest.raises(native.ProbeError, match=message) as error:
        native.verify_apt_files([good, candidate], tmp_path, {}, apt, diagnostic_path=diagnostic)
    report = json.loads(diagnostic.read_bytes())
    assert report["status"] == "failed" and len(report["requested_paths"]) == 2
    row = next(r for r in report["requested_paths"] if r["original_path"] == candidate.as_posix())
    assert row["resolved_path"] == candidate.resolve().as_posix()
    assert row["status"] == status
    assert repr(row["original_path"]) in str(error.value)
    assert repr(row["resolved_path"]) in str(error.value)
    assert next(r for r in report["requested_paths"] if r["original_path"] == good.as_posix())["status"] == "regular-file-within-prefix"


def test_compiler_aliases_verify_original_archive_bytes_and_reject_changed_install(tmp_path, monkeypatch):
    prefix = (tmp_path / "prefix").resolve()
    prefix.mkdir()
    real = prefix / "compiler-real"
    real.write_bytes(b"exact compiler payload")
    alias = prefix / "compiler-alias"
    alias.symlink_to(real)
    member = "/data/data/com.termux/files/usr/bin/compiler-real"
    archive, pin = compiler_archive_fixture(tmp_path / "archives", member, real.read_bytes())
    monkeypatch.setattr(native, "PREFIX", prefix)
    actual_reader = native.ar_data_members
    physical = real.resolve().as_posix()
    calls = []
    def archive_adapter(path, selected_pin, wanted):
        # Only map the host temporary location to the fixture's original POSIX
        # archive path; the real archive/control/hash reader is left intact.
        assert wanted == {physical}
        calls.append((path, deepcopy(selected_pin)))
        raw = actual_reader(path, selected_pin, {member})
        return {physical: raw[member]}
    monkeypatch.setattr(native, "ar_data_members", archive_adapter)
    apt = SimpleNamespace(collect_owners=lambda paths: {physical: [pin["name"]]})
    report = tmp_path / "paths.json"
    result = native.verify_apt_files([real, alias], archive.parent, {pin["name"]: pin}, apt, diagnostic_path=report)
    assert result == [{"path": physical, "package": pin["name"], "bytes": real.stat().st_size,
                       "sha256": prep.sha(real.read_bytes())}]
    rows = json.loads(report.read_bytes())["requested_paths"]
    assert len(rows) == 2 and {r["resolved_path"] for r in rows} == {physical}
    assert len(calls) == 1 and calls[0][0] == archive
    real.write_bytes(b"changed compiler payload")
    with pytest.raises(native.ProbeError, match="differs from its archive"):
        native.verify_apt_files([real, alias], archive.parent, {pin["name"]: pin}, apt, diagnostic_path=report)


@pytest.mark.parametrize("owners", [[], ["unreviewed-package"], ["first", "second"]])
def test_compiler_path_presence_does_not_admit_unowned_or_ambiguous_file(tmp_path, monkeypatch, owners):
    prefix = tmp_path.resolve()
    member = prefix / "compiler"
    member.write_bytes(b"present is insufficient")
    monkeypatch.setattr(native, "PREFIX", prefix)
    apt = SimpleNamespace(collect_owners=lambda paths: {member.as_posix(): owners})
    with pytest.raises(native.ProbeError, match="Unowned/unpinned"):
        native.verify_apt_files([member], tmp_path, {}, apt)


@pytest.mark.parametrize("plan_case", ["valid", "missing-tool", "unexpected-package", "removal", "duplicate"])
def test_native_toolchain_plan_keeps_exact_20_additions_and_27_foundation(tmp_path, monkeypatch, plan_case):
    lock, _ = prep.load_lock(ROOT / "scripts" / prep.LOCK_FILENAME)
    original = deepcopy(lock)
    pins = lock["build_apt"]["packages"]
    additions = [p for p in pins if not p["in_foundation"]]
    foundation = [p for p in pins if p["in_foundation"]]
    by_name = {p["name"]: p for p in pins}
    calls, snapshots, copied = [], [], []
    def snapshot(names):
        snapshots.append(list(names))
        return {name: {"version": by_name[name]["version"], "architecture": by_name[name]["architecture"],
                       "status": "installed"} for name in names}
    def stage_archives(args, selected, work):
        assert selected == pins and len(selected) == 47
        copied.append(deepcopy(selected))
        result = work / "install-archives"
        result.mkdir()
        return result
    def command(argv, out, label, timeout, *args):
        calls.append((argv, label))
        assert "--no-download" in argv and "--no-remove" in argv and "--reinstall" in argv
        requested = argv[argv.index("install") + 1:]
        assert requested == [p["name"] + "=" + p["version"] for p in additions]
        assert requested.count("openssl-tool=1:3.6.5") == 1
        if label == "rust-apt-plan":
            proposed = [p["name"] for p in additions]
            if plan_case == "missing-tool":
                proposed.remove("openssl-tool")
            elif plan_case == "unexpected-package":
                proposed.append("unreviewed")
            elif plan_case == "duplicate":
                proposed.append("openssl-tool")
            text = "".join("Inst " + name + " (fixture)\n" for name in proposed)
            if plan_case == "removal":
                text += "Remv pinned-foundation (fixture)\n"
            (out / "rust-apt-plan.stdout.log").write_text(text)
        return {"exit_code": 0, "controlled_native_command_fixture": True}
    monkeypatch.setattr(native, "package_snapshot", snapshot)
    monkeypatch.setattr(native, "stage_install_archives", stage_archives)
    monkeypatch.setattr(native, "bounded_command", command)
    args = SimpleNamespace(out=tmp_path, apt_archives=tmp_path / "verified-inputs")
    if plan_case == "valid":
        result = native.install_toolchain(args, lock, ["-o", "APT::Get::AllowUnauthenticated=false"], tmp_path)
        assert result["status"] == "passed" and result["additional_count"] == 20
        assert len(result["installed_packages"]) == 47
        assert len(snapshots) == 2 and len(snapshots[0]) == 27 and len(snapshots[1]) == 47
        assert [label for argv, label in calls] == ["rust-apt-plan", "rust-apt-install"]
    else:
        with pytest.raises(native.ProbeError):
            native.install_toolchain(args, lock, [], tmp_path)
        assert [label for argv, label in calls] == ["rust-apt-plan"]
        assert len(snapshots) == 1
    assert len(foundation) == 27 and len(additions) == 20 and len(copied) == 1
    assert lock == original
