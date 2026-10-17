"""Host integrity tests; no native runtime, package install, or workflow is run."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_cua_candidate", ROOT / "scripts/prepare_cua_hermes_candidate.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def put(root, name, data=b"original"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_frozen_patch_has_the_reviewed_paths_and_no_dependencies_or_build_source_edits():
    path = ROOT / "patches/next-stable/cua-hermes-integration.patch"
    prepare.pinned_file(path, digest=prepare.PATCH_SHA256, size=prepare.PATCH_BYTES)
    names = prepare.patch_paths(path.read_bytes())
    assert names == set(prepare.PATCH_FILES)
    assert len(names) == 19
    assert not names & {"uv.lock", "pyproject.toml", "pm/uv.lock", "pm/lock.json", "pm/pyproject.toml"}
    assert not any(name.startswith("scripts/") for name in names)
    assert all(name in prepare.NEW_FILES for name in names if name.startswith("tests/"))


@pytest.mark.parametrize("raw", [
    b"diff --git a/good.py b/other.py\n",
    b"diff --git a/../outside b/../outside\n",
    b"diff --git a/a.py b/a.py\nnew file mode 120000\n",
    b"diff --git a/a.py b/a.py\nnew file mode 100755\n",
    b"diff --git a/a.py b/a.py\nGIT binary patch\n",
    b"diff --git a/a.py b/a.py\ndiff --git a/a.py b/a.py\n",
    b"diff --git a/a.py b/a.py\ndeleted file mode 100644\n",
])
def test_unreviewed_patch_operations_are_rejected(raw):
    with pytest.raises(prepare.PreparationError):
        prepare.patch_paths(raw)


def test_same_size_file_corruption_is_detected_even_when_mtime_is_preserved(tmp_path):
    root = tmp_path / "payload"
    file = put(root, "venv/native.so", b"first")
    original_stat = file.stat()
    before = prepare.payload_inventory(root)
    file.write_bytes(b"wrong")
    os.utime(file, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    after = prepare.payload_inventory(root)
    assert before["venv/native.so"]["bytes"] == after["venv/native.so"]["bytes"]
    assert before["venv/native.so"]["sha256"] != after["venv/native.so"]["sha256"]
    assert prepare.inventory_digest(before) != prepare.inventory_digest(after)
    assert "venv" in before and "" not in before and "." not in before


def test_directory_symlink_is_recorded_without_traversing_its_target(tmp_path):
    root = tmp_path / "payload"
    root.mkdir()
    outside = tmp_path / "outside"
    put(outside, "must-not-be-enumerated", b"outside")
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host does not permit creation of a directory symlink: {exc}")
    inventory = prepare.payload_inventory(root)
    assert set(inventory) == {"link"}
    assert inventory["link"] == {"kind": "symlink", "mode": stat.S_IMODE(link.lstat().st_mode),
                                 "target": os.readlink(link)}


def test_ordinary_hardlinks_do_not_invent_new_payload_bytes(tmp_path):
    root = tmp_path / "payload"
    original = put(root, "one", b"same bytes")
    os.link(original, root / "two")
    inventory = prepare.payload_inventory(root)
    assert inventory["one"] == inventory["two"]
    assert inventory["one"]["kind"] == "file"


def changed_payload(tmp_path, monkeypatch):
    root = tmp_path / "payload"
    for name in ("app/pm/install.py", "app/uv.lock", "app/pm/uv.lock", "app/pm/lock.json",
                 "venv/site/native.so", "pm-runtime/site/packaging.py", "wheelhouse/native-1.whl",
                 "runtime-libs/lib/libnative.so", "tools/python/python", "tools/facts.json",
                 "bundled-wheels.json", "manifest.json"):
        put(root, name)
    before = prepare.payload_inventory(root)
    modified = put(root, "app/pm/install.py", b"reviewed code")
    added = put(root, "app/pm/bundled_tools.py", b"reviewed new source")
    files = {
        "pm/install.py": {"bytes": modified.stat().st_size, "sha256": prepare.sha256(modified)},
        "pm/bundled_tools.py": {"bytes": added.stat().st_size, "sha256": prepare.sha256(added)},
    }
    monkeypatch.setattr(prepare, "PATCH_FILES", files)
    put(root, "manifest.json", b"new canonical manifest")
    put(root, "bundled-tools.json", b"reviewed descriptor")
    entry = "tools/cua-driver-0.21.0-linux-arm64-bionic"
    put(root, entry + "/cua-driver", b"native ELF fixture")
    put(root, entry + "/source-receipt.json", b"source pin fixture")
    row = {"entry": entry, "binary": "cua-driver", "source_receipt": "source-receipt.json"}
    return root, before, row


def test_reviewed_source_and_separate_driver_can_preserve_every_original_runtime_byte(tmp_path, monkeypatch):
    root, before, row = changed_payload(tmp_path, monkeypatch)
    after = prepare.payload_inventory(root)
    changes = prepare.verify_change_boundary(before, after, row)
    assert "app/pm/install.py" in changes
    assert "app/pm/bundled_tools.py" in changes
    assert row["entry"] + "/cua-driver" in changes
    assert not any(name.startswith(("venv/", "pm-runtime/", "wheelhouse/", "runtime-libs/")) for name in changes)


@pytest.mark.parametrize("name", [
    "venv/site/native.so", "pm-runtime/site/packaging.py", "wheelhouse/native-1.whl",
    "runtime-libs/lib/libnative.so", "tools/python/python", "tools/facts.json",
    "bundled-wheels.json", "app/uv.lock", "app/pm/uv.lock", "app/pm/lock.json",
    "app/unreviewed.py",
])
def test_dependency_lock_or_unreviewed_source_mutation_refuses_candidate(tmp_path, monkeypatch, name):
    root, before, row = changed_payload(tmp_path, monkeypatch)
    put(root, name, b"unreviewed mutation")
    with pytest.raises(prepare.PreparationError, match="unreviewed payload change"):
        prepare.verify_change_boundary(before, prepare.payload_inventory(root), row)


def test_removing_an_original_runtime_file_refuses_candidate(tmp_path, monkeypatch):
    root, before, row = changed_payload(tmp_path, monkeypatch)
    (root / "wheelhouse/native-1.whl").unlink()
    with pytest.raises(prepare.PreparationError, match="unreviewed payload change"):
        prepare.verify_change_boundary(before, prepare.payload_inventory(root), row)


def test_path_allowlist_does_not_accept_wrong_post_patch_source_bytes(tmp_path, monkeypatch):
    root, before, row = changed_payload(tmp_path, monkeypatch)
    put(root, "app/pm/install.py", b"not the reviewed code")
    with pytest.raises(prepare.PreparationError, match="patched source output mismatch"):
        prepare.verify_change_boundary(before, prepare.payload_inventory(root), row)


def test_existing_ancestor_permissions_are_part_of_preserved_identity(tmp_path, monkeypatch):
    root, before, row = changed_payload(tmp_path, monkeypatch)
    after = prepare.payload_inventory(root)
    after["tools"] = {**after["tools"], "mode": after["tools"]["mode"] ^ stat.S_IXUSR}
    with pytest.raises(prepare.PreparationError, match="existing ancestor changed"):
        prepare.verify_change_boundary(before, after, row)


CONTROL = b"""Package: hermes-agent
Version: 0.22.2-1
Architecture: aarch64
Maintainer: Hermes preparation
Description: Prepared bundle
 Retained second description line
Installed-Size: 1234
"""


def test_control_adds_exact_runtime_apt_dependencies_and_retains_every_other_field(tmp_path):
    control = put(tmp_path, "control", CONTROL)
    record = prepare.prepare_control(control, 9876)
    after = prepare.parse_control(control.read_bytes())
    assert after["Depends"] == "libx11, libxi"
    assert after["Installed-Size"] == "9876"
    assert after.get("Pre-Depends", "") == ""
    assert record["original_fields"] == prepare.parse_control(CONTROL)
    assert record["prepared_fields"] == after
    assert {key: value for key, value in after.items() if key not in {"Depends", "Installed-Size"}} == {
        key: value for key, value in prepare.parse_control(CONTROL).items() if key != "Installed-Size"
    }
    assert record["declared_runtime_libraries"] == {"libX11.so": "libx11", "libXi.so": "libxi"}


@pytest.mark.parametrize("old,new", [
    (b"hermes-agent", b"foreign-package"),
    (b"0.22.2-1", b"0.22.2-2"),
    (b"aarch64", b"all"),
    (b"Installed-Size: 1234", b"Depends: foreign-library"),
    (b"Installed-Size: 1234", b"Pre-Depends: bootstrap"),
])
def test_unexpected_original_control_is_rejected_before_rewrite(tmp_path, old, new):
    raw = CONTROL.replace(old, new)
    control = put(tmp_path, "control", raw)
    with pytest.raises(prepare.PreparationError):
        prepare.prepare_control(control, 9876)
    assert control.read_bytes() == raw


def test_duplicate_control_fields_are_not_silently_overwritten():
    with pytest.raises(prepare.PreparationError, match="duplicate Debian control field"):
        prepare.parse_control(CONTROL + b"Version: 9.9\n")


def test_augmented_control_requires_declared_runtime_dependencies():
    fields = prepare.parse_control(CONTROL)
    with pytest.raises(prepare.PreparationError, match="Depends"):
        prepare.check_package_fields(fields, augmented=True)
    fields["Depends"] = "libx11, libxi"
    prepare.check_package_fields(fields, augmented=True)


def elf_fixture(path, *, needed=None, interpreter=b"/system/bin/linker64\0",
                runpath="/data/data/com.termux/files/usr/bin/../../usr/lib"):
    needed = needed or ["libX11.so", "libXi.so", "libdl.so", "libm.so", "libc.so"]
    strings = bytearray(b"\0")
    offsets = []
    for name in [*needed, runpath]:
        offsets.append(len(strings))
        strings += name.encode() + b"\0"
    dynamic = [(1, offset) for offset in offsets[:-1]]
    dynamic += [(29, offsets[-1]), (5, 0x400), (10, len(strings)), (0, 0)]
    dynamic_bytes = b"".join(struct.pack("<QQ", *item) for item in dynamic)
    data = bytearray(0x400 + len(strings))
    ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    data[:64] = struct.pack("<16sHHIQQQIHHHHHH", ident, 3, 183, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    segments = [
        (1, 5, 0, 0, 0, len(data), len(data), 0x1000),
        (3, 4, 0x200, 0x200, 0x200, len(interpreter), len(interpreter), 1),
        (2, 6, 0x280, 0x280, 0x280, len(dynamic_bytes), len(dynamic_bytes), 8),
    ]
    for index, segment in enumerate(segments):
        data[64 + index * 56:64 + (index + 1) * 56] = struct.pack("<IIQQQQQQ", *segment)
    data[0x200:0x200 + len(interpreter)] = interpreter
    data[0x280:0x280 + len(dynamic_bytes)] = dynamic_bytes
    data[0x400:] = strings
    path.write_bytes(data)
    return path


def test_actual_shaped_elf_requires_only_declared_apt_and_android_libraries(tmp_path):
    path = elf_fixture(tmp_path / "driver")
    record = prepare.elf_linkage(path)
    assert record["needed"] == ["libX11.so", "libXi.so", "libdl.so", "libm.so", "libc.so"]
    assert record["apt_depends"] == "libx11, libxi"
    assert record["interpreter"] == "/system/bin/linker64"


@pytest.mark.parametrize("kwargs,reason", [
    ({"needed": ["libX11.so", "libXi.so", "libdl.so", "libm.so", "libc.so", "libstdc++.so.6"]}, "unreviewed ELF shared-library"),
    ({"interpreter": b"/lib/ld-linux-aarch64.so.1\0"}, "Android linker"),
    ({"runpath": "/tmp/unowned:/data/data/com.termux/files/usr/lib"}, "library search path"),
])
def test_elf_cannot_hide_undeclared_libraries_or_another_loader(tmp_path, kwargs, reason):
    path = elf_fixture(tmp_path / "driver", **kwargs)
    with pytest.raises(prepare.PreparationError, match=reason):
        prepare.elf_linkage(path)


def test_truncated_elf_cannot_be_certified(tmp_path):
    path = put(tmp_path, "driver", b"\x7fELF\x02\x01")
    with pytest.raises(prepare.PreparationError, match="ELF table escapes"):
        prepare.elf_linkage(path)


def test_hash_bound_input_rejects_same_size_corruption(tmp_path):
    path = put(tmp_path, "input", b"reviewed")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(b"tampered")
    with pytest.raises(prepare.PreparationError, match="SHA-256 mismatch"):
        prepare.pinned_file(path, digest=expected, size=8)


def test_output_cannot_overwrite_or_contain_an_input(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    with pytest.raises(prepare.PreparationError, match="already exists"):
        prepare.ensure_separate_output(candidate, (candidate,))
    with pytest.raises(prepare.PreparationError, match="separate"):
        prepare.ensure_separate_output(candidate / "new-output", (candidate,))
    absent_parent = tmp_path / "absent"
    with pytest.raises(prepare.PreparationError, match="separate"):
        prepare.ensure_separate_output(absent_parent, (absent_parent / "candidate",))
    separate = tmp_path / "new-output"
    prepare.ensure_separate_output(separate, (candidate,))
    assert not separate.exists()


def test_duplicate_receipt_keys_cannot_mask_another_package():
    with pytest.raises(prepare.PreparationError, match="duplicate JSON key"):
        prepare.json_object(b'{"package":"old","package":"other"}', "candidate")


def test_no_partial_json_receipt_overwrite(tmp_path):
    path = tmp_path / "receipt.json"
    record = prepare.write_json(path, {"status": "first"})
    assert record["sha256"] == prepare.sha256(path)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        prepare.write_json(path, {"status": "replacement"})
    assert path.read_bytes() == original


def test_preparation_cli_refuses_host_pytest_before_creating_outputs(tmp_path, capsys):
    # This process is the actual ordinary host test interpreter, not a simulated
    # Android runtime. The native CLI must reject it before any stage mutation.
    out = tmp_path / "out"
    args = []
    for name in ("candidate-dir", "patch", "assembly-source", "driver", "source-receipt"):
        args += ["--" + name, str(tmp_path / name)]
    args += ["--driver-sha256", "a" * 64, "--packaging-commit", "b" * 40, "--out", str(out)]
    assert prepare.main(args) == 1
    assert "invoke the candidate interpreter with -I -B" in capsys.readouterr().err
    assert not out.exists()
