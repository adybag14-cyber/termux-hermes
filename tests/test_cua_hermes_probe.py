"""Regression checks for false-positive native CUA integration evidence."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest

from scripts import compatibility_probe_cua_hermes as probe


@pytest.fixture
def candidate_receipt(tmp_path):
    saved = Path(__file__).resolve().parents[1] / "audit/candidate-lifecycle-e271e92-20261017"
    data = {
        "schema_version": 1, "status": "verified",
        **{key: probe.CANDIDATE[key] for key in ("repository", "run_id", "head_sha")},
        "artifact": {"id": 12107225801, "name": "hermes-termux-next-stable-candidate",
                     "sha256": probe.CANDIDATE["artifact_sha256"]},
        "package": {"file": "hermes-agent_0.22.2-1_aarch64.deb", "bytes": 222089768,
                    "sha256": probe.CANDIDATE["package_sha256"]},
    }
    for key, (name, expected_sha) in probe.CANDIDATE_RAW_FILES.items():
        original = (saved / name).read_bytes()
        (tmp_path / name).write_bytes(original)
        data[key] = {**json.loads(original), "file": name, "sha256": expected_sha, "zip_member": "fixture/" + name}
    path = tmp_path / "candidate-receipt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_saved_proven_candidate_is_accepted_and_another_run_is_rejected(candidate_receipt):
    verified = probe.read_candidate_receipt(candidate_receipt)
    assert verified["identity"]["published"] is False
    assert verified["native_selection"]["target"] == "linux-arm64-bionic"
    verified["run_id"] += 1
    candidate_receipt.write_text(json.dumps(verified), encoding="utf-8")
    with pytest.raises(probe.ProbeFailure, match="run_id"):
        probe.read_candidate_receipt(candidate_receipt)


def test_verified_label_cannot_hide_changed_native_selection_bytes(candidate_receipt):
    raw_path = candidate_receipt.parent / "venv-selection.json"
    raw = json.loads(raw_path.read_text())
    raw["extras"].remove("matrix")
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(probe.ProbeFailure, match="raw bytes"):
        probe.read_candidate_receipt(candidate_receipt)


def test_receipt_fields_must_match_the_pinned_original(candidate_receipt):
    data = json.loads(candidate_receipt.read_text())
    data["native_selection"]["stamp"] = "0" * 64
    candidate_receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(probe.ProbeFailure, match="fields differ"):
        probe.read_candidate_receipt(candidate_receipt)


@pytest.mark.parametrize("changed", ["catalog", "lock", "features"])
def test_actual_payload_must_match_selection_not_just_receipt_label(changed):
    selection = {"target": "linux-arm64-bionic", "extras": ["mcp", "termux"],
                 "bundled_wheels": {"path": "bundled-wheels.json", "sha256": "a" * 64},
                 "uv_lock_sha256": "b" * 64, "pm_lock_sha256": "c" * 64}
    hashes = {"bundled-wheels.json": "a" * 64, "app/uv.lock": "b" * 64, "app/pm/lock.json": "c" * 64}
    source = {"uv.lock": "b" * 64, "pm/lock.json": "c" * 64}
    manifest = {"bundled_wheels": selection["bundled_wheels"]}
    features = {"schema": 1, "extras": ["mcp", "termux"]}
    probe.verify_native_selection(selection, hashes, source, manifest, features)
    if changed == "catalog":
        hashes["bundled-wheels.json"] = "d" * 64
    elif changed == "lock":
        source["uv.lock"] = "d" * 64
    else:
        features["extras"].append("computer-use")
    with pytest.raises(probe.ProbeFailure):
        probe.verify_native_selection(selection, hashes, source, manifest, features)


@pytest.mark.parametrize("wrong", ["position", "duplicate", "other_input"])
def test_button_success_requires_exact_fixture_coordinates_and_count(wrong):
    event = {"event": "button", "button": 1, "x": 80, "y": 60}
    probe.require_button_events([event], button=1, count=1, x=80, y=60)
    if wrong == "position":
        observed = [{**event, "x": 160}]
    elif wrong == "duplicate":
        observed = [event, event]
    else:
        observed = [event, {"event": "key", "hex": "61"}]
    with pytest.raises(probe.ProbeFailure, match="exact button oracle"):
        probe.require_button_events(observed, button=1, count=1, x=80, y=60)


def test_text_oracle_uses_delivered_bytes_not_transport_ok():
    observed = [{"event": "key", "hex": "6865726d6573"}, {"event": "key", "hex": ""}]
    probe.require_text_events(observed, "hermes")
    with pytest.raises(probe.ProbeFailure, match="differs"):
        probe.require_text_events(observed, "hermes-native-input")
    with pytest.raises(probe.ProbeFailure, match="unexpected button"):
        probe.require_text_events([*observed, {"event": "button", "button": 1, "x": 80, "y": 60}], "hermes")


def test_image_oracle_rejects_plausible_wrong_window(tmp_path):
    from PIL import Image

    def result(right_color):
        image = Image.new("RGB", (320, 240), probe.LEFT_RGB)
        image.paste(right_color, (160, 0, 320, 240))
        raw = io.BytesIO()
        image.save(raw, format="PNG")
        return {"_multimodal": True, "meta": {"width": 320, "height": 240},
                "content": [{"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(raw.getvalue()).decode("ascii")}}]}

    proof = probe.capture_evidence(result(probe.RIGHT_RGB), tmp_path)
    assert proof["dimensions"] == [320, 240]
    with pytest.raises(probe.ProbeFailure, match="right fixture color"):
        probe.capture_evidence(result(probe.LEFT_RGB), tmp_path)


def test_completed_bad_jsonl_is_not_treated_as_missing_evidence(tmp_path):
    path = tmp_path / "fixture.jsonl"
    path.write_text('{"event":"ready","pid":42,"window_id":43}\n{"event":"paint"', encoding="utf-8")
    assert probe.read_events(path) == [{"event": "ready", "pid": 42, "window_id": 43}]
    path.write_text('{"event":"ready","pid":42,"window_id":43}\nnot-json\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        probe.read_events(path)


class LivingFixture:
    pid = 42

    def poll(self):
        return None


def test_fixture_approval_is_one_exact_prompt_not_a_reusable_grant():
    records = []
    callback = probe.FixtureApproval(LivingFixture(), records)
    callback.arm("click", "click at (80, 60)")
    command = "computer_use: click at (80, 60)" + probe.FOREGROUND_NOTICE
    assert callback(command, "Allow computer_use to perform `click`?") == "once"
    assert records[0]["fixture_pid"] == 42
    with pytest.raises(probe.ProbeFailure, match="unexpected or repeated"):
        callback(command, "Allow computer_use to perform `click`?")
    callback.arm("click", "click at (80, 60)")
    with pytest.raises(probe.ProbeFailure, match="unexpected approval target"):
        callback("computer_use: click at (5, 5)" + probe.FOREGROUND_NOTICE, "Allow computer_use to perform `click`?")
    assert len(records) == 1



@pytest.fixture
def prepared_candidate(tmp_path, candidate_receipt, monkeypatch):
    """Small byte fixture; source receipt is reconstructed and SHA-verified from saved native evidence."""
    import hashlib
    from types import SimpleNamespace

    monkeypatch.delenv("CUA_PROBE_HEAD_SHA", raising=False)
    candidate = probe.read_candidate_receipt(candidate_receipt)
    payload = tmp_path / "payload"
    source = payload / "app"
    source.mkdir(parents=True)
    (source / "example.py").write_bytes(b"owned source fixture\n")
    driver = payload / probe.PACKAGED_TOOL_ENTRY / "cua-driver"
    driver.parent.mkdir(parents=True)
    driver.write_bytes(b"owned binary bytes for metadata-validator tests\n")
    driver_sha = probe.digest(driver)
    saved = Path(__file__).resolve().parents[1] / "audit/cua-native-20261017/run-39056267366.json"
    raw_source = json.loads(saved.read_text(encoding="utf-8"))["raw_artifact_subdocuments"]["CUA-SOURCE-RECEIPT.json"]
    source_bytes = (json.dumps(raw_source, indent=2) + "\n").encode("utf-8")
    assert hashlib.sha256(source_bytes).hexdigest() == probe.SOURCE_RECEIPT_SHA256
    (driver.parent / "source-receipt.json").write_bytes(source_bytes)
    tool = {
        "name": "cua-driver", "version": "0.21.0", "target": "linux-arm64-bionic",
        "entry": probe.PACKAGED_TOOL_ENTRY, "binary": "cua-driver", "binary_sha256": driver_sha,
        "source_receipt": "source-receipt.json", "source_receipt_sha256": probe.SOURCE_RECEIPT_SHA256,
        "tree_sha256": "a" * 64,
    }
    catalog_path = payload / "bundled-tools.json"
    catalog_path.write_text(json.dumps({"schema_version": 1, "tools": [tool]}), encoding="utf-8")
    descriptor = {"path": "bundled-tools.json", "sha256": probe.digest(catalog_path)}
    manifest = payload / "manifest.json"
    manifest.write_text(json.dumps({"bundled_tools": descriptor}), encoding="utf-8")
    inventory_path = tmp_path / "CUA-PREPARED-PAYLOAD.json"
    inventory_path.write_text(json.dumps({"schema_version": 1, "files": probe.payload_inventory(payload)}), encoding="utf-8")
    package = tmp_path / "hermes-agent_0.22.2-1_aarch64-cua-candidate.deb"
    package.write_bytes(b"candidate archive identity fixture\n")
    data = {
        "schema_version": 1, "status": "prepared-candidate", "published": False, "version_bumped": False,
        "packaging_commit": "b" * 40,
        "input_candidate": {
            **{key: probe.CANDIDATE[key] for key in ("run_id", "head_sha", "artifact_id", "package_sha256")},
            "candidate_receipt_sha256": probe.digest(candidate_receipt),
        },
        "package": {
            "file": package.name, "bytes": package.stat().st_size, "sha256": probe.digest(package),
            "name": "hermes-agent", "version": "0.22.2-1", "architecture": "aarch64",
            "depends": "libx11, libxi", "pre_depends": "",
        },
        "patch": dict(probe.PREPARED_PATCH),
        "native_selection": {key: value for key, value in candidate["native_selection"].items()
                             if key not in {"file", "sha256", "zip_member"}},
        "bundled_tools": {"descriptor": descriptor, "tool": tool},
        "payload": {
            "root": str(payload), "manifest_sha256": probe.digest(manifest),
            "inventory": {"file": inventory_path.name, "bytes": inventory_path.stat().st_size,
                          "sha256": probe.digest(inventory_path)},
        },
    }
    data = json.loads(json.dumps(data))  # Receipt bytes and independently verified inputs share no mutable values.
    path = tmp_path / "prepared-cua-receipt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    state = SimpleNamespace(path=path, data=data, payload=payload, source=source,
                            driver=driver, driver_sha=driver_sha, package=package, inventory=inventory_path)
    state.read = lambda: probe.read_prepared_receipt(
        path, payload=payload, source=source, driver=driver, driver_sha256=driver_sha,
        candidate_path=candidate_receipt, candidate=candidate,
    )
    return state


def test_prepared_candidate_binds_exact_installed_inventory(prepared_candidate):
    state = prepared_candidate
    receipt, inventory = state.read()
    assert receipt["input_candidate"]["package_sha256"] == probe.CANDIDATE["package_sha256"]
    assert inventory == probe.payload_inventory(state.payload)
    assert inventory["app"]["kind"] == "directory"
    assert "mode" in inventory["app"]
    assert inventory["app/example.py"]["kind"] == "file"


@pytest.mark.parametrize("change", [
    "published", "version", "input", "patch", "package-bytes", "source-receipt",
    "driver", "catalog", "manifest", "selection", "inventory", "installed-extra-file",
])
def test_prepared_label_cannot_hide_changed_bytes_or_identity(prepared_candidate, change):
    state = prepared_candidate
    if change == "published":
        state.data["published"] = True
    elif change == "version":
        state.data["package"]["version"] = "0.22.2-2"
    elif change == "input":
        state.data["input_candidate"]["run_id"] += 1
    elif change == "patch":
        state.data["patch"]["sha256"] = "c" * 64
    elif change == "package-bytes":
        state.package.write_bytes(b"changed archive")
    elif change == "source-receipt":
        (state.driver.parent / "source-receipt.json").write_bytes(b"changed source")
    elif change == "driver":
        state.driver.write_bytes(b"changed driver")
    elif change == "catalog":
        (state.payload / "bundled-tools.json").write_bytes(b"{}")
    elif change == "manifest":
        (state.payload / "manifest.json").write_bytes(b"{}")
    elif change == "selection":
        state.data["native_selection"]["extras"].append("computer-use")
    elif change == "inventory":
        state.inventory.write_bytes(b"{}")
    elif change == "installed-extra-file":
        (state.source / "extra.py").write_bytes(b"unsealed")
    state.path.write_text(json.dumps(state.data), encoding="utf-8")
    with pytest.raises(probe.ProbeFailure):
        state.read()


def test_inventory_records_directory_links_without_traversing(tmp_path):
    import os

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "not-owned").write_bytes(b"must not be traversed")
    root = tmp_path / "payload"
    root.mkdir()
    try:
        os.symlink(outside, root / "linked", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create this directory symlink: {exc}")
    rows = probe.payload_inventory(root)
    assert set(rows) == {"linked"}
    assert rows["linked"]["kind"] == "symlink"
    assert rows["linked"]["target"] == os.readlink(root / "linked")
    assert "mode" in rows["linked"]


@pytest.mark.parametrize("packaged", [False, True])
def test_environment_exercises_defaults_only_on_packaged_route(tmp_path, packaged):
    import os
    import sys
    from unittest.mock import patch

    work, payload = tmp_path / "work", tmp_path / "payload"
    work.mkdir()
    before_bytecode = sys.dont_write_bytecode
    try:
        with patch.dict(os.environ, {
            "HERMES_CUA_DRIVER_CMD": "untrusted-driver",
            "HERMES_RUNTIME_DIR": "untrusted-tools",
            "HERMES_INSTALL_ROOT": "untrusted-root",
        }):
            home = probe.configure_environment(work, payload, packaged_default=packaged)
            config = (home / "config.yaml").read_text(encoding="utf-8")
            assert ("no_overlay: true" in config) is (not packaged)
            assert "permission_mode: standard" in config
            assert "mode: manual" in config
            if packaged:
                assert all(key not in os.environ for key in probe.AUTHORITY_OVERRIDES)
            else:
                assert "HERMES_CUA_DRIVER_CMD" not in os.environ
                assert os.environ["HERMES_RUNTIME_DIR"] == str(payload / "tools")
    finally:
        sys.dont_write_bytecode = before_bytecode


def test_argument_observer_rejects_nested_caller_mutation():
    from types import SimpleNamespace

    arguments = {"action": "click", "coordinate": [80, 60]}

    def mutate(name, args, **kwargs):
        args["coordinate"][0] = 160
        return '{"ok":true}'

    with pytest.raises(probe.ProbeFailure, match="mutated the original"):
        probe.dispatch_unchanged(SimpleNamespace(dispatch=mutate), arguments, session_id="fixture")


def test_argument_observer_preserves_result_and_original_request():
    from types import SimpleNamespace

    arguments = {"action": "click", "coordinate": [80, 60]}

    def dispatch(name, args, **kwargs):
        assert name == "computer_use" and kwargs == {"session_id": "fixture"}
        assert "delivery_mode" not in args
        return '{"ok":true}'

    assert probe.dispatch_unchanged(SimpleNamespace(dispatch=dispatch), arguments, session_id="fixture") == '{"ok":true}'
    assert arguments == {"action": "click", "coordinate": [80, 60]}


@pytest.mark.parametrize("changed", ["override", "pm-source", "selected-path", "version", "bytes"])
def test_packaged_selection_cannot_be_faked_by_a_matching_label(tmp_path, monkeypatch, changed):
    from types import SimpleNamespace

    for key in probe.AUTHORITY_OVERRIDES:
        monkeypatch.delenv(key, raising=False)
    payload = tmp_path / "payload"
    entry = payload / probe.PACKAGED_TOOL_ENTRY
    entry.mkdir(parents=True)
    driver = entry / "cua-driver"
    driver.write_bytes(b"resident-driver-fixture")
    expected = probe.digest(driver)
    selected = SimpleNamespace(path=entry, binary=driver, version="0.21.0")
    pm_module = SimpleNamespace(
        __file__=str(payload / "app" / "pm" / "__init__.py"),
        installed_package=lambda name: selected if name == "cua-driver" else None,
    )
    assert probe.verify_packaged_driver(pm_module, payload, driver, expected)["sha256"] == expected
    if changed == "override":
        monkeypatch.setenv("HERMES_INSTALL_ROOT", "untrusted")
    elif changed == "pm-source":
        pm_module.__file__ = str(tmp_path / "other" / "pm" / "__init__.py")
    elif changed == "selected-path":
        selected.path = tmp_path
    elif changed == "version":
        selected.version = "0.20.0"
    elif changed == "bytes":
        driver.write_bytes(b"changed")
    with pytest.raises(probe.ProbeFailure):
        probe.verify_packaged_driver(pm_module, payload, driver, expected)


@pytest.mark.parametrize("extra", [
    ["--packaged-default"],
    ["--prepared-receipt", "receipt.json"],
])
def test_packaged_route_requires_both_cli_options(tmp_path, extra):
    base = ["--source", "source", "--driver", "driver", "--driver-sha256", "a" * 64,
            "--fixture", "fixture", "--out", str(tmp_path / "out"), "--candidate-receipt", "candidate.json"]
    with pytest.raises(SystemExit) as exc:
        probe.main([*base, *extra])
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()



@pytest.mark.parametrize("wrong", ["depends", "pre_depends", "version", "extra-field"])
def test_installed_control_must_match_the_augmented_runtime_contract(wrong):
    package = {"name": "hermes-agent", "version": "0.22.2-1", "architecture": "aarch64",
               "depends": "libx11, libxi", "pre_depends": ""}
    rows = ["hermes-agent", "0.22.2-1", "aarch64", "libx11, libxi", ""]
    assert probe.verify_installed_control_output("\n".join(rows) + "\n", package)["Depends"] == "libx11, libxi"
    if wrong == "depends":
        rows[3] = ""
    elif wrong == "pre_depends":
        rows[4] = "unexpected"
    elif wrong == "version":
        rows[1] = "0.22.2-2"
    else:
        rows.append("unparsed")
    with pytest.raises(probe.ProbeFailure):
        probe.verify_installed_control_output("\n".join(rows) + "\n", package)



def test_prepared_candidate_must_match_the_workflow_head(prepared_candidate, monkeypatch):
    state = prepared_candidate
    monkeypatch.setenv("CUA_PROBE_HEAD_SHA", state.data["packaging_commit"])
    state.read()
    monkeypatch.setenv("CUA_PROBE_HEAD_SHA", "c" * 40)
    with pytest.raises(probe.ProbeFailure, match="actual workflow head"):
        state.read()
