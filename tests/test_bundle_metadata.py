from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

import pytest

from scripts import bundle_metadata as bundle

TAG = "v0.22.2"
COMMIT = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
VERSION = "0.22.2-1"
PACKAGING_COMMIT = "9a82cb98862edee817da4f9648a3d16d12fe5e7b"
IMAGE = "termux/termux-docker@sha256:" + "c" * 64
CONTROL = f"Package: hermes-agent\nVersion: {VERSION}\nArchitecture: aarch64\n"


def release_stamp() -> dict:
    return {
        "schemaVersion": 2, "commit": COMMIT, "tag": TAG,
        "baseVersion": "0.22.2", "displayVersion": "0.22.2", "distance": 0,
        "payload": "runtime", "source": "bundle", "distribution": "apt-termux",
        "updateMechanism": "external", "dirty": False,
    }


def package_files() -> dict[str, tuple[bytes, int]]:
    """A minimal package fixture retaining the source/runtime boundary."""
    files = {
        "app/.install_method": (b"apt\n", 0o644),
        "app/install-stamp.json": (json.dumps(release_stamp()).encode(), 0o644),
        "app/pm/lock.json": (b'{"schema": 1, "packages": {}}\n', 0o644),
        "app/hermes_cli/tui_dist/entry.js": (b"// built TUI\n", 0o644),
        "app/hermes_cli/tui_dist/package.json": (b"{}\n", 0o644),
        "tools/facts.json": (b"{}\n", 0o644),
        "native-wheels.json": (b'["psutil"]\n', 0o644),
        "enabled-features.json": (json.dumps({
            "schema": 1, "extras": ["acp", "cron", "mcp", "telegram", "termux"],
        }).encode(), 0o644),
        "manifest.json": (json.dumps({
            "schema": 1, "target": "linux-arm64-bionic", "repo": "app", "venv": "venv",
            "store": "tools", "launchers": ["hermes", "hermes-agent", "hermes-acp"],
            "runtime": {
                "repoDir": "app", "toolsDir": "tools",
                "storePython": f"tools/python/{bundle.PREFIX}/bin/python3.14",
                "sitePackages": "venv/lib/python3.14/site-packages",
                "commands": {name: f"bin/{name}" for name in
                             ["hermes", "hermes-agent", "hermes-acp"]},
            },
        }).encode(), 0o644),
        "pm-runtime/pm-runtime.json": (json.dumps({
            "python": f"../tools/python/{bundle.PREFIX}/bin/python3.14",
            "sitePackages": "lib/python3.14/site-packages",
        }).encode(), 0o644),
    }
    for path in [
        f"tools/python/{bundle.PREFIX}/bin/python3.14",
        f"tools/node/{bundle.PREFIX}/bin/node", f"tools/uv/{bundle.PREFIX}/bin/uv",
        f"tools/ffmpeg/{bundle.PREFIX}/bin/ffmpeg", "tools/npm/bin/npm", "tools/ripgrep/rg",
        "bin/hermes", "bin/hermes-agent", "bin/hermes-acp",
    ]:
        files[path] = (b"#!/bin/sh\nexit 0\n", 0o755)
    for module in ["packaging", "tomli_w", "truststore", "ruamel/yaml"]:
        files[f"pm-runtime/lib/python3.14/site-packages/{module}/__init__.py"] = (b"", 0o644)
    for distribution in ["python_telegram_bot-22.8", "mcp-2.0.0", "croniter-6.0.0",
                         "agent_client_protocol-0.9.0"]:
        files[f"venv/lib/python3.14/site-packages/{distribution}.dist-info/METADATA"] = (
            b"Metadata-Version: 2.3\n", 0o644,
        )
    return files


def data_archive(files: dict[str, tuple[bytes, int]] | None = None,
                 python_link: str | None = None) -> io.BytesIO:
    files = package_files() if files is None else files
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        dirs = {f"{bundle.ROOT}/runtime-libs/lib", f"{bundle.ROOT}/venv/bin"}
        for path in files:
            dirs.update(str(parent) for parent in
                        PurePosixPath(f"{bundle.ROOT}/{path}").parents if str(parent) != ".")
        for directory in sorted(dirs):
            member = tarfile.TarInfo(directory)
            member.type, member.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(member)
        for path, (content, mode) in sorted(files.items()):
            member = tarfile.TarInfo(f"{bundle.ROOT}/{path}")
            member.size, member.mode = len(content), mode
            archive.addfile(member, io.BytesIO(content))
        member = tarfile.TarInfo(f"{bundle.ROOT}/venv/bin/python")
        member.type, member.mode = tarfile.SYMTYPE, 0o777
        member.linkname = python_link or f"../../tools/python/{bundle.PREFIX}/bin/python3.14"
        archive.addfile(member)
    stream.seek(0)
    return stream


def test_canonical_bundle_and_its_own_interpreter_are_accepted() -> None:
    inspected = bundle.validate_archive(bundle.scan_tar(data_archive()), TAG, COMMIT)
    assert inspected["install_stamp"]["updateMechanism"] == "external"
    assert inspected["native_distributions"] == ["psutil"]
    assert inspected["enabled_features"] == ["acp", "cron", "mcp", "telegram", "termux"]


@pytest.mark.parametrize("change", [
    {"commit": "a" * 40},
    {"tag": "v0.22.1"},
    {"updateMechanism": "self"},
    {"payload": "bundled"},
    {"source": "commit-build"},
    {"displayVersion": "0.0.0"},
    {"schemaVersion": True},
])
def test_a_release_cannot_claim_wrong_identity_or_update_owner(change: dict) -> None:
    files = package_files()
    files["app/install-stamp.json"] = (
        json.dumps({**release_stamp(), **change}).encode(), 0o644,
    )
    with pytest.raises(ValueError, match="install stamp"):
        bundle.validate_archive(bundle.scan_tar(data_archive(files)), TAG, COMMIT)


@pytest.mark.parametrize("control", [
    CONTROL.replace("aarch64", "arm64"),
    CONTROL.replace(VERSION, "0.20.6+termux2"),
    CONTROL.replace("hermes-agent", "python"),
    CONTROL + "Version: 0.20.6+termux2\n",
])
def test_wrong_or_ambiguous_debian_identity_is_rejected(control: str) -> None:
    with pytest.raises(ValueError, match="Debian"):
        bundle.validate_control(control, VERSION)


def test_stable_release_inputs_require_matching_version_and_immutable_sources() -> None:
    bundle.validate_identity(TAG, COMMIT, VERSION, PACKAGING_COMMIT, IMAGE)
    with pytest.raises(ValueError, match="package version"):
        bundle.validate_identity(TAG, COMMIT, "0.22.1-1", PACKAGING_COMMIT, IMAGE)
    with pytest.raises(ValueError, match="immutable"):
        bundle.validate_identity(TAG, COMMIT, VERSION, PACKAGING_COMMIT, "termux:latest")


def test_missing_pm_dependencies_are_not_mistaken_for_a_complete_environment() -> None:
    files = package_files()
    del files["pm-runtime/lib/python3.14/site-packages/packaging/__init__.py"]
    with pytest.raises(ValueError, match="required payload path missing"):
        bundle.validate_archive(bundle.scan_tar(data_archive(files)), TAG, COMMIT)


def test_optional_termux_features_must_reach_the_actual_package() -> None:
    files = package_files()
    del files["venv/lib/python3.14/site-packages/mcp-2.0.0.dist-info/METADATA"]
    with pytest.raises(ValueError, match="termux feature dependency missing.*mcp"):
        bundle.validate_archive(bundle.scan_tar(data_archive(files)), TAG, COMMIT)


@pytest.mark.parametrize("declaration", [
    None,
    {"schema": 1, "extras": ["acp", "cron", "mcp", "Telegram", "termux"]},
])
def test_bundle_must_record_the_exact_pm_feature_baseline(declaration: dict | None) -> None:
    files = package_files()
    if declaration is None:
        del files["enabled-features.json"]
    else:
        files["enabled-features.json"] = (json.dumps(declaration).encode(), 0o644)
    with pytest.raises(ValueError, match="enabled-features.json"):
        bundle.validate_archive(bundle.scan_tar(data_archive(files)), TAG, COMMIT)


def test_launcher_cannot_depend_on_a_host_python() -> None:
    archive = bundle.scan_tar(data_archive(python_link="/usr/bin/python3"))
    with pytest.raises(ValueError, match="escapes the bundle"):
        bundle.validate_archive(archive, TAG, COMMIT)


def test_git_metadata_is_rejected_before_any_extraction() -> None:
    files = package_files()
    files["app/.git/config"] = (b"[remote]", 0o644)
    with pytest.raises(ValueError, match="Git metadata"):
        bundle.scan_tar(data_archive(files))


@pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb is required")
def test_real_deb_provenance_matches_payload_and_rejects_stale_inputs(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    with tarfile.open(fileobj=data_archive(), mode="r:") as archive:
        archive.extractall(stage, filter="data")
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        CONTROL + "Maintainer: Test <test@example.invalid>\nDescription: contract fixture\n",
        encoding="utf-8",
    )
    deb = tmp_path / f"hermes-agent_{VERSION}_aarch64.deb"
    subprocess.run(
        ["dpkg-deb", "--build", "-Zxz", "--root-owner-group", str(stage), str(deb)],
        check=True, capture_output=True,
    )
    payload = tmp_path / "payload"
    (payload / ".work").mkdir(parents=True)
    (payload / "wheelhouse").mkdir()
    (payload / ".work/resolved.txt").write_text(
        "".join(f"{name}\t==1.0\t\t\n" for name in [
            "python-telegram-bot", "mcp", "croniter", "agent-client-protocol", "psutil",
        ]), encoding="utf-8",
    )
    (payload / ".work/build_set.txt").write_text("psutil\n", encoding="utf-8")
    wheel = payload / "wheelhouse/psutil-1.0-cp314-cp314-android_24_arm64_v8a.whl"
    wheel.write_bytes(b"wheel artifact fixture")
    lock = stage / bundle.ROOT / "app/pm/lock.json"
    patch = tmp_path / "termux-profile.patch"
    patch.write_bytes(b"- --extra acp\n+ --extra termux\n")
    args = argparse.Namespace(
        deb=deb, payload=payload, upstream_tag=TAG, upstream_commit=COMMIT,
        package_version=VERSION, packaging_commit=PACKAGING_COMMIT,
        builder_image=IMAGE, pm_lock=lock, build_patch=[patch],
    )
    result = bundle.build_metadata(args)
    assert result["package"]["sha256"] == hashlib.sha256(deb.read_bytes()).hexdigest()
    assert result["runtime"]["feature_profile"] == "termux"
    assert result["packaging"]["build_patches"][0]["sha256"] == (
        hashlib.sha256(patch.read_bytes()).hexdigest()
    )
    assert result["wheelhouse"]["wheels"][0]["size"] == wheel.stat().st_size
    lock.write_bytes(b'{"different": true}\n')
    with pytest.raises(ValueError, match="PM lock differs"):
        bundle.build_metadata(args)
