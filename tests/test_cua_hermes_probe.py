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
