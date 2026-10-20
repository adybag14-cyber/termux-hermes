"""The Android ABI3 forwarding stub must survive only HF Xet's link step."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("_hf_python_linkage", ROOT / "scripts/compatibility_probe_neutts_rust.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
LOCK = json.loads((ROOT / "scripts/neutts_rust_sources_lock.json").read_bytes())

def test_hf_only_scoped_linker_arguments_preserve_ambient_state():
    before = {"RUSTFLAGS": LOCK["build"]["rustflags"], "CARGO_NET_OFFLINE": "true",
              "PYO3_PYTHON": "/pinned/python", "OTHER": "unchanged"}
    copy = dict(before)
    scoped = native.source_build_environment(LOCK, before, "hf-xet")
    assert before == copy
    assert scoped["RUSTFLAGS"] == before["RUSTFLAGS"] + (
        " -C link-arg=-Wl,--push-state,--no-as-needed"
        " -C link-arg=-lpython3 -C link-arg=-Wl,--pop-state")
    assert {k: v for k, v in scoped.items() if k != "RUSTFLAGS"} == {
        k: v for k, v in before.items() if k != "RUSTFLAGS"}
    assert "LD_PRELOAD" not in scoped

@pytest.mark.parametrize("name", ["maturin", "safetensors", "tokenizers"])
def test_other_original_component_flags_are_unchanged(name):
    before = {"RUSTFLAGS": LOCK["build"]["rustflags"], "CARGO_NET_OFFLINE": "true"}
    scoped = native.source_build_environment(LOCK, before, name)
    assert scoped == before and scoped is not before

@pytest.mark.parametrize("flags", ["", "-C target-cpu=native", LOCK["build"]["rustflags"] + " -l python3"])
def test_reject_unreviewed_base_rustflags(flags):
    with pytest.raises(native.ProbeError, match="Original Rust flags"):
        native.source_build_environment(LOCK, {"RUSTFLAGS": flags}, "hf-xet")

def test_reject_an_unknown_component_scope():
    with pytest.raises(native.ProbeError, match="Unknown component"):
        native.source_build_environment(LOCK, {"RUSTFLAGS": LOCK["build"]["rustflags"]}, "another-library")

def test_require_original_hf_abi3_library_and_forwarding_dependency():
    native.validate_hf_python_linkage([{"wheel_member": "hf_xet/hf_xet.abi3.so",
                                       "needed": ["libssl.so", "libpython3.so", "libc.so"]}])

@pytest.mark.parametrize("rows", [
    [],
    [{"wheel_member": "hf_xet/hf_xet.abi3.so", "needed": ["libc.so"]}],
    [{"wheel_member": "hf_xet/hf_xet.cpython-314.so", "needed": ["libpython3.so"]}],
    [{"wheel_member": "hf_xet/hf_xet.abi3.so", "needed": ["libpython3.14.so"]}],
    [{"wheel_member": "hf_xet/hf_xet.abi3.so", "needed": ["libpython3.so"]}] * 2,
])
def test_reject_dropped_stub_and_retagged_or_ambiguous_extension(rows):
    with pytest.raises(native.ProbeError):
        native.validate_hf_python_linkage(rows)

def test_exact_python_archive_and_project_metadata_stay_frozen():
    python = next(p for p in LOCK["build_apt"]["packages"] if p["name"] == "python")
    assert python["version"] == "3.14.6-1"
    assert python["sha256"] == "3166e56c2b6c03fff41191fbb9d736302978e7c484702814d9f6dc99dd6006bd"
    source = next(p for p in LOCK["sources"] if p["name"] == "hf-xet")
    assert source["version"] == "1.6.0"
    assert source["expected_tag"] == "cp38-abi3-android_24_arm64_v8a"
    assert hashlib.sha256((ROOT / "scripts/neutts_rust_sources_lock.json").read_bytes()).hexdigest() == native.helpers()[0].LOCK_SHA256
