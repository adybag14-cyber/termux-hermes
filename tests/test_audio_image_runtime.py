"""Container-only audio platform provenance controls; no native library is loaded."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prep = load("audio_image_preparation_test", "prepare_audio_hermes_environment.py")
probe = load("audio_image_probe_test", "compatibility_probe_audio_hermes.py")


@pytest.fixture
def image_case(tmp_path, monkeypatch):
    prefix = tmp_path / "prefix"
    library = prefix / "opt/aosp/lib64"
    library.mkdir(parents=True)
    pins, paths = {}, []
    for name in probe.IMAGE_PLATFORM_FILES:
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (183).to_bytes(2, "little")
        raw = bytes(header) + name.encode()
        path = library / name
        path.write_bytes(raw)
        pins[name] = (len(raw), hashlib.sha256(raw).hexdigest())
        paths.append(path)
    monkeypatch.setattr(prep, "PREFIX", prefix)
    monkeypatch.setattr(probe, "IMAGE_PLATFORM_FILES", pins)
    image = [{"Architecture": "arm64", "Os": "linux",
              "RepoDigests": [prep.IMAGE], "Id": "sha256:" + "1" * 64}]
    inspection = tmp_path / "image.json"
    inspection.write_bytes((json.dumps(image) + "\n").encode())
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    state = {
        "snapshot": b"aosp-libs\t9.0.0-r76-4\taarch64\tinstalled\n",
        "owners": "".join("aosp-libs: " + str(path) + "\n" for path in sorted(paths)).encode(),
        "calls": [],
    }

    def query(argv, out, name, *, timeout):
        state["calls"].append((argv, out, name, timeout))
        assert argv[0] == str(prefix / "bin/dpkg-query")
        assert out == evidence and timeout == 20
        return subprocess.CompletedProcess(argv, 0,
                    state["snapshot"] if argv[1] == "-W" else state["owners"], b"")

    monkeypatch.setattr(prep, "run_logged", query)
    return {"paths": paths, "pins": pins, "prefix": prefix, "image": image,
            "inspection": inspection, "evidence": evidence, "state": state}


def verify(case):
    return probe.verify_image_platform_members(
        case["paths"], case["inspection"], case["evidence"], prep)


def test_five_image_files_require_and_preserve_actual_observation_and_ownership(image_case):
    case = image_case
    raw = case["inspection"].read_bytes()
    result = verify(case)
    assert result["status"] == "verified-image-members"
    assert result["native_image"] == prep.IMAGE
    assert result["inspection_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (case["evidence"] / "audio-source-image.json").read_bytes() == raw
    assert len(result["members"]) == 5
    assert {row["path"]: (row["bytes"], row["sha256"]) for row in result["members"]} == {
        str(path): case["pins"][path.name] for path in case["paths"]}
    assert {row["machine"] for row in result["members"]} == {183}
    calls = case["state"]["calls"]
    assert len(calls) == 2
    assert calls[0][0][1] == "-W" and calls[0][0][-1] == "aosp-libs"
    assert calls[1][0][1:] == ["-S", *map(str, sorted(case["paths"]))]


def test_device_without_image_paths_requires_no_docker_or_package_query(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("device path must not run an image-only query")
    monkeypatch.setattr(prep, "run_logged", unexpected)
    result = probe.verify_image_platform_members([], None, tmp_path, prep)
    assert result["status"] == "not-used" and result["members"] == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutation", ["missing-inspection", "unknown-aosp", "ordinary-prefix", "directory"])
def test_image_gate_rejects_unreviewed_paths_before_dependency_query(image_case, mutation):
    case = image_case
    if mutation == "missing-inspection":
        case["inspection"] = None
    elif mutation == "unknown-aosp":
        case["paths"].append(case["prefix"] / "opt/aosp/lib64/libicuuc.so")
    elif mutation == "ordinary-prefix":
        case["paths"] = [case["prefix"] / "lib/libc++.so"]
    else:
        case["inspection"] = case["evidence"]
    with pytest.raises(prep.PreparationError):
        verify(case)
    assert case["state"]["calls"] == []


@pytest.mark.parametrize("mutation", ["digest", "architecture", "os", "id", "multiple"])
def test_image_identity_drift_is_rejected_before_package_query(image_case, mutation):
    case = image_case
    image = copy.deepcopy(case["image"])
    if mutation == "digest":
        image[0]["RepoDigests"] = ["termux/termux-docker@sha256:" + "2" * 64]
    elif mutation == "architecture":
        image[0]["Architecture"] = "amd64"
    elif mutation == "os":
        image[0]["Os"] = "windows"
    elif mutation == "id":
        image[0]["Id"] = "sha256:" + "g" * 64
    else:
        image.append(copy.deepcopy(image[0]))
    case["inspection"].write_text(json.dumps(image))
    with pytest.raises(prep.PreparationError):
        verify(case)
    assert case["state"]["calls"] == []


@pytest.mark.parametrize("mutation", ["version", "architecture", "status", "package"])
def test_platform_package_identity_drift_is_rejected(image_case, mutation):
    case = image_case
    replacements = {"version": (b"9.0.0-r76-4", b"9.0.0-r76-5"),
                    "architecture": (b"aarch64", b"x86_64"),
                    "status": (b"installed", b"config-files"),
                    "package": (b"aosp-libs", b"unreviewed-libs")}
    case["state"]["snapshot"] = case["state"]["snapshot"].replace(*replacements[mutation])
    with pytest.raises(prep.PreparationError, match="owner version differs"):
        verify(case)
    assert len(case["state"]["calls"]) == 1


@pytest.mark.parametrize("mutation", ["wrong-owner", "duplicate", "missing", "extra"])
def test_every_mapped_image_path_needs_unambiguous_exact_ownership(image_case, mutation):
    case = image_case
    rows = case["state"]["owners"].decode().splitlines()
    if mutation == "wrong-owner":
        rows[0] = rows[0].replace("aosp-libs:", "other-libs:", 1)
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "missing":
        rows.pop()
    else:
        rows.append("aosp-libs: " + str(case["prefix"] / "opt/aosp/lib64/libextra.so"))
    case["state"]["owners"] = ("\n".join(rows) + "\n").encode()
    with pytest.raises(prep.PreparationError):
        verify(case)


def test_one_changed_native_byte_fails_the_original_pin(image_case):
    case = image_case
    path = case["paths"][0]
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(prep.PreparationError):
        verify(case)


@pytest.mark.parametrize("mutation", ["ELF32", "big-endian", "machine"])
def test_hash_match_alone_cannot_admit_a_wrong_native_abi(image_case, mutation):
    case = image_case
    path = case["paths"][0]
    raw = bytearray(path.read_bytes())
    if mutation == "ELF32":
        raw[4] = 1
    elif mutation == "big-endian":
        raw[5] = 2
    else:
        raw[18:20] = (62).to_bytes(2, "little")
    path.write_bytes(raw)
    # Deliberately allow the synthetic bytes to reach the independent ELF gate.
    case["pins"][path.name] = (len(raw), hashlib.sha256(raw).hexdigest())
    with pytest.raises(prep.PreparationError, match="ABI differs"):
        verify(case)


def test_platform_alias_is_rejected_even_when_the_resolved_body_matches(image_case, monkeypatch):
    case = image_case
    path = case["paths"][0]
    original = Path.resolve

    def resolve(p, *args, **kwargs):
        return original(case["paths"][1]) if p == path else original(p, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(prep.PreparationError, match="exact regular path"):
        verify(case)


def test_production_five_file_pins_equal_original_reviewed_image_set():
    original_probe = load("audio_image_original_pin_test", "compatibility_probe_audio_hermes.py")
    lock = json.loads((ROOT / "scripts/neutts_nonrust_runtime_lock.json").read_bytes())
    original = lock["platform_runtime"]
    assert original["native_image"] == prep.IMAGE
    assert original_probe.IMAGE_PLATFORM_FILES == {
        Path(row["path"]).name: (row["bytes"], row["sha256"])
        for row in original["files"]
    }
    assert len(original_probe.IMAGE_PLATFORM_FILES) == 5


def test_mixed_maps_exclude_image_linker_but_keep_unreviewed_shared_library(image_case):
    case = image_case
    known = case["paths"][0]
    unknown = case["prefix"] / "opt/aosp/lib64/libunreviewed.so"
    linker = case["prefix"] / "opt/aosp/bin/linker64"
    ordinary = case["prefix"] / "lib/libffi.so"
    mapped = probe.image_shared_objects([known, unknown, linker, ordinary], case["prefix"])
    assert mapped == {known, unknown}
    with pytest.raises(prep.PreparationError, match="unreviewed container image platform"):
        probe.verify_image_platform_members(
            mapped, case["inspection"], case["evidence"], prep)
    assert case["state"]["calls"] == []
