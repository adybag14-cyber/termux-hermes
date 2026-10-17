from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts import verify_release_candidate as promote

REPO = "adybag14-cyber/termux-hermes"
RUN_ID = "123456789"
COMMIT = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
HEAD = "9a82cb98862edee817da4f9648a3d16d12fe5e7b"
TAG = "hermes-agent-termux-0.22.2-20261016.1"
VERSION = "0.22.2-1"
FILENAME = f"hermes-agent_{VERSION}_aarch64.deb"
PINS = {
    "schema_version": 1, "source_repository": "NousResearch/hermes-agent",
    "source_tag": "v0.22.2", "source_commit": COMMIT, "package_version": VERSION,
    "feature_profile": "termux", "python_abi": "cp314",
    "platform_tag": "android_24_arm64_v8a",
    "termux_image": "termux/termux-docker@sha256:" + "c" * 64,
}


def build_run() -> dict:
    return {
        "id": int(RUN_ID), "path": ".github/workflows/build-hermes-package.yml",
        "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
        "head_sha": HEAD, "repository": {"full_name": REPO},
        "head_repository": {"full_name": REPO},
    }


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checksums(candidate: Path) -> None:
    names = [FILENAME, "BUILD-METADATA.json", "WHEELHOUSE-MANIFEST.json",
             "RESOLVED.txt", "RELEASE-PINS.json"]
    (candidate / "SHA256SUMS").write_text(
        "".join(f"{checksum(candidate / name)}  {name}\n" for name in names),
        encoding="ascii",
    )


def candidate_files(tmp_path: Path, package_bytes: bytes = b"native deb fixture") -> tuple[Path, Path]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    deb = candidate / FILENAME
    deb.write_bytes(package_bytes)
    stamp = {
        "schemaVersion": 2, "commit": COMMIT, "tag": "v0.22.2",
        "baseVersion": "0.22.2", "displayVersion": "0.22.2", "distance": 0,
        "payload": "runtime", "source": "bundle", "distribution": "apt-termux",
        "updateMechanism": "external", "dirty": True,
    }
    metadata = {
        "schema_version": 1,
        "package": {"name": "hermes-agent", "version": VERSION, "architecture": "aarch64",
                    "file": FILENAME, "sha256": checksum(deb), "size": len(package_bytes)},
        "upstream": {"repository": "NousResearch/hermes-agent", "tag": "v0.22.2",
                     "commit": COMMIT, "install_stamp": stamp},
        "packaging": {"repository": REPO, "commit": HEAD, "builder_image": PINS["termux_image"]},
        "runtime": {"feature_profile": "termux",
                    "enabled_features": ["acp", "cron", "mcp", "telegram", "termux"]},
        "inspection": {"package_contract": "passed"},
    }
    (candidate / "BUILD-METADATA.json").write_text(json.dumps(metadata), encoding="utf-8")
    (candidate / "WHEELHOUSE-MANIFEST.json").write_text("{}", encoding="utf-8")
    (candidate / "RESOLVED.txt").write_text("locked graph fixture", encoding="utf-8")
    (candidate / "RELEASE-PINS.json").write_text(json.dumps(PINS), encoding="utf-8")
    write_checksums(candidate)
    installer = tmp_path / "install.sh"
    installer.write_text(
        f"PACKAGE_VERSION='{VERSION}'\n"
        'PACKAGE_FILENAME="hermes-agent_${PACKAGE_VERSION}_aarch64.deb"\n'
        f"PACKAGE_SHA256='{checksum(deb)}'\n"
        f'PACKAGE_RELEASE_URL="https://github.com/{REPO}/releases/download/{TAG}/{FILENAME}"\n',
        encoding="utf-8",
    )
    return candidate, installer


def fake_control(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promote.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"Package: hermes-agent\nVersion: {VERSION}\nArchitecture: aarch64\n",
            returncode=0,
        ),
    )


def test_candidate_is_bound_to_build_bytes_reviewed_pins_and_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, installer = candidate_files(tmp_path)
    fake_control(monkeypatch)
    verified = promote.verify_candidate(candidate, build_run(), REPO, RUN_ID, TAG, PINS, installer)
    assert verified["package_sha256"] == checksum(candidate / FILENAME)
    assert verified["build_head_sha"] == HEAD
    assert verified["installer"]["sha256"] == checksum(installer)


@pytest.mark.parametrize("changed", [
    {"conclusion": "failure"},
    {"status": "in_progress"},
    {"path": ".github/workflows/ci.yml"},
    {"head_repository": {"full_name": "someone/termux-hermes"}},
    {"repository": {"full_name": "someone/termux-hermes"}},
    {"id": int(RUN_ID) + 1},
])
def test_a_different_or_unsuccessful_run_cannot_be_promoted(changed: dict) -> None:
    with pytest.raises(ValueError, match="build run"):
        promote.validate_run({**build_run(), **changed}, REPO, RUN_ID)


def test_changed_binary_is_rejected_before_any_installation(tmp_path: Path) -> None:
    candidate, _ = candidate_files(tmp_path)
    (candidate / FILENAME).write_bytes(b"replacement binary")
    with pytest.raises(ValueError, match="checksum mismatch"):
        promote.verify_checksums(candidate, FILENAME)


def test_checksums_cannot_reference_files_outside_the_candidate(tmp_path: Path) -> None:
    candidate, _ = candidate_files(tmp_path)
    with (candidate / "SHA256SUMS").open("a") as stream:
        stream.write("0" * 64 + "  ../outside\n")
    with pytest.raises(ValueError, match="unsafe filename"):
        promote.verify_checksums(candidate, FILENAME)


@pytest.mark.parametrize("section,field,value", [
    ("packaging", "commit", "a" * 40),
    ("upstream", "commit", "a" * 40),
    ("runtime", "enabled_features", ["acp"]),
])
def test_rewritten_metadata_cannot_claim_other_sources_or_reduced_features(
    tmp_path: Path, section: str, field: str, value: object,
) -> None:
    candidate, installer = candidate_files(tmp_path)
    metadata = promote.read_json(candidate / "BUILD-METADATA.json")
    metadata[section][field] = value
    (candidate / "BUILD-METADATA.json").write_text(json.dumps(metadata), encoding="utf-8")
    write_checksums(candidate)
    with pytest.raises(ValueError):
        promote.verify_candidate(candidate, build_run(), REPO, RUN_ID, TAG, PINS, installer)


@pytest.mark.parametrize("old,new", [
    ("PACKAGE_SHA256=", "PACKAGE_SHA256='stale'\nIGNORED_SHA256="),
    (TAG, "hermes-agent-termux-0.22.2-other-tag"),
    (f"PACKAGE_VERSION='{VERSION}'", "PACKAGE_VERSION='0.20.6+termux2'"),
])
def test_stale_installer_pins_block_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str,
) -> None:
    candidate, installer = candidate_files(tmp_path)
    installer.write_text(installer.read_text().replace(old, new), encoding="utf-8")
    fake_control(monkeypatch)
    with pytest.raises(ValueError, match="installer PACKAGE_"):
        promote.verify_candidate(candidate, build_run(), REPO, RUN_ID, TAG, PINS, installer)


def release_assets(candidate: Path) -> dict:
    return {
        "tag_name": TAG, "draft": True,
        "assets": [
            {"name": path.name, "digest": f"sha256:{checksum(path)}",
             "size": path.stat().st_size, "state": "uploaded"}
            for path in candidate.iterdir()
        ],
    }


def test_every_uploaded_draft_asset_must_match_before_publication(tmp_path: Path) -> None:
    candidate, _ = candidate_files(tmp_path)
    release = release_assets(candidate)
    promote.verify_release_assets(candidate, release, TAG)
    package = next(asset for asset in release["assets"] if asset["name"] == FILENAME)
    package["digest"] = None
    with pytest.raises(ValueError, match="digest/size/state mismatch"):
        promote.verify_release_assets(candidate, release, TAG)


def test_tag_availability_errors_do_not_masquerade_as_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promote.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="HTTP/2.0 503 Service Unavailable\n", stderr="HTTP 503",
        ),
    )
    with pytest.raises(ValueError, match="could not establish"):
        promote.ensure_new_release(REPO, TAG)


@pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb is required")
@pytest.mark.parametrize("architecture", ["aarch64", "arm64"])
def test_actual_debian_control_is_checked_against_candidate_metadata(
    tmp_path: Path, architecture: str,
) -> None:
    stage = tmp_path / "stage"
    (stage / "DEBIAN").mkdir(parents=True)
    (stage / "DEBIAN/control").write_text(
        f"Package: hermes-agent\nVersion: {VERSION}\nArchitecture: {architecture}\n"
        "Maintainer: Test <test@example.invalid>\nDescription: promotion fixture\n",
        encoding="utf-8",
    )
    deb = tmp_path / FILENAME
    subprocess.run(
        ["dpkg-deb", "--build", "-Zxz", "--root-owner-group", str(stage), str(deb)],
        check=True, capture_output=True,
    )
    candidate, installer = candidate_files(tmp_path, deb.read_bytes())
    if architecture == "aarch64":
        verified = promote.verify_candidate(candidate, build_run(), REPO, RUN_ID, TAG, PINS, installer)
        assert verified["package_sha256"] == checksum(deb)
    else:
        with pytest.raises(ValueError, match="Debian Architecture"):
            promote.verify_candidate(candidate, build_run(), REPO, RUN_ID, TAG, PINS, installer)
