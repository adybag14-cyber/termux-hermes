"""Regression for verified wheel transfer across native build/output mounts."""
from __future__ import annotations
import errno
import hashlib
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("_phonemizer_transfer_test", ROOT / "scripts/compatibility_probe_phonemizer.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def wheel_transfer(tmp_path):
    source = tmp_path / "build" / "verified.whl"
    source.parent.mkdir()
    raw = b"already verified wheel bytes\0\xff\n"
    source.write_bytes(raw)
    destination = tmp_path / "output" / source.name
    destination.parent.mkdir()
    pin = {"filename": source.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return source, destination, raw, pin


def test_verified_copy_survives_a_rename_cross_device_failure(wheel_transfer, monkeypatch):
    source, destination, raw, pin = wheel_transfer
    def unavailable_rename(*args, **kwargs):
        raise OSError(errno.EXDEV, "Cross-device link")
    monkeypatch.setattr(Path, "rename", unavailable_rename)
    with pytest.raises(OSError) as error:
        source.rename(destination)
    assert error.value.errno == errno.EXDEV
    result = probe.copy_built_wheel(source, destination, pin)
    assert source.read_bytes() == destination.read_bytes() == raw
    assert result["copied_bytes_verified"] and result["exclusive_destination"]
    assert result["source_preserved"] and result["sha256"] == pin["sha256"]


@pytest.mark.parametrize("change", ["filename", "size", "hash", "oversized"])
def test_changed_transfer_input_is_rejected_before_output_creation(wheel_transfer, change):
    source, destination, raw, pin = wheel_transfer
    if change == "filename":
        pin["filename"] = "different.whl"
    elif change == "size":
        pin["bytes"] += 1
    elif change == "hash":
        pin["sha256"] = "0" * 64
    else:
        pin["bytes"] = 16_000_001
    with pytest.raises(probe.ProbeError):
        probe.copy_built_wheel(source, destination, pin)
    assert source.read_bytes() == raw and not destination.exists()


def test_existing_output_is_preserved(wheel_transfer):
    source, destination, raw, pin = wheel_transfer
    destination.write_bytes(b"existing evidence")
    with pytest.raises(probe.ProbeError, match="destination already exists"):
        probe.copy_built_wheel(source, destination, pin)
    assert destination.read_bytes() == b"existing evidence" and source.read_bytes() == raw


@pytest.mark.parametrize("which", ["source", "destination"])
def test_transfer_rejects_symlinks_without_changing_targets(wheel_transfer, which):
    source, destination, raw, pin = wheel_transfer
    target = source.parent / "target.whl"
    target.write_bytes(raw)
    link = source if which == "source" else destination
    if link.exists():
        link.unlink()
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Host cannot create the transfer symlink fixture: {exc}")
    with pytest.raises(probe.ProbeError):
        probe.copy_built_wheel(source, destination, pin)
    assert link.is_symlink() and target.read_bytes() == raw


def test_corrupted_copy_is_not_admitted(wheel_transfer, monkeypatch):
    source, destination, raw, pin = wheel_transfer
    def corrupted_copy(input_stream, output_stream, **kwargs):
        output_stream.write(b"corrupt output")
    monkeypatch.setattr(probe.shutil, "copyfileobj", corrupted_copy)
    with pytest.raises(probe.ProbeError, match="transfer changed bytes"):
        probe.copy_built_wheel(source, destination, pin)
    assert source.read_bytes() == raw
