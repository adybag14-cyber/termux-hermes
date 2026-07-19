from __future__ import annotations

import csv
import importlib.util
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_wheels", ROOT / "scripts" / "build_wheels.py")
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

CHECKSUM_SPEC = importlib.util.spec_from_file_location(
    "checksum_artifact", ROOT / "scripts" / "checksum_artifact.py"
)
assert CHECKSUM_SPEC and CHECKSUM_SPEC.loader
checksum = importlib.util.module_from_spec(CHECKSUM_SPEC)
CHECKSUM_SPEC.loader.exec_module(checksum)

def test_manifest_is_complete_and_unique() -> None:
    manifest = json.loads((ROOT / "manifest" / "wheels.json").read_text("utf-8"))
    builder.validate_manifest(manifest)
    names = [builder.canonicalize_name(p["name"]) for p in manifest["packages"]]
    assert names == [
        "cffi",
        "markupsafe",
        "pillow",
        "psutil",
        "pyyaml",
        "ruamel-yaml-clib",
        "cryptography",
        "jiter",
        "pydantic-core",
        "rpds-py",
    ]
    assert len(names) == len(set(names)) == 10
    assert manifest["target"]["wheel_platform"] == "android_24_arm64_v8a"


def test_safe_extract_rejects_tar_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        root = tarfile.TarInfo("demo-1")
        root.type = tarfile.DIRTYPE
        tf.addfile(root)
        link = tarfile.TarInfo("demo-1/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        tf.addfile(link)
    with pytest.raises(builder.BuildError, match="rejected"):
        builder.safe_extract(archive, tmp_path / "out")


def test_setup_cfg_tag_preserves_existing_sections(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    cfg = root / "setup.cfg"
    cfg.write_text("[metadata]\nname = demo\n\n[bdist_wheel]\nuniversal = 0\n", "utf-8")
    builder.configure_setuptools_tag(root, "android_24_arm64_v8a")
    text = cfg.read_text("utf-8")
    assert "[metadata]\nname = demo" in text
    assert "plat_name = android_24_arm64_v8a" in text
    assert "universal = 0" in text


def test_psutil_patch_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "src"
    common = root / "psutil" / "_common.py"
    common.parent.mkdir(parents=True)
    common.write_text(builder.PSUTIL_MARKER + "\n", "utf-8")
    builder.patch_psutil(root)
    builder.patch_psutil(root)
    assert common.read_text("utf-8").count(builder.PSUTIL_REPLACEMENT) == 1


def _synthetic_wheel(path: Path) -> None:
    dist = "demo-1.0.dist-info"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("demo/native.so", b"ELF-placeholder")
        wheel.writestr(
            f"{dist}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\nTag: cp313-cp313-linux_x86_64\n",
        )
        wheel.writestr(f"{dist}/METADATA", "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n")
        wheel.writestr(f"{dist}/RECORD", "")


def test_retag_rewrites_filename_metadata_and_record(tmp_path: Path) -> None:
    wheel = tmp_path / "demo-1.0-cp313-cp313-linux_x86_64.whl"
    _synthetic_wheel(wheel)
    tagged = builder.retag_wheel(wheel, "android_24_arm64_v8a")
    assert tagged.name == "demo-1.0-cp313-cp313-android_24_arm64_v8a.whl"
    assert not wheel.exists()
    with zipfile.ZipFile(tagged) as archive:
        wheel_text = archive.read("demo-1.0.dist-info/WHEEL").decode()
        assert "Tag: cp313-cp313-android_24_arm64_v8a" in wheel_text
        rows = list(csv.reader(archive.read("demo-1.0.dist-info/RECORD").decode().splitlines()))
        assert rows[-1] == ["demo-1.0.dist-info/RECORD", "", ""]
        assert all(row[1].startswith("sha256=") for row in rows[:-1])
        assert archive.testzip() is None


def test_expected_platform_mappings() -> None:
    assert builder.expected_platform(24, "aarch64") == "android_24_arm64_v8a"
    assert builder.expected_platform(24, "x86_64") == "android_24_x86_64"
    with pytest.raises(builder.BuildError):
        builder.expected_platform(20, "aarch64")


def test_sidecar_checksum_is_relocatable_after_directory_copy(tmp_path: Path) -> None:

    wheelhouse = tmp_path / "build" / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    sums = wheelhouse / "SHA256SUMS"
    sums.write_text("", "utf-8")
    sidecar = wheelhouse / "system-packages.txt"
    sidecar.write_text("python=3.13.14\n", "utf-8")

    entry = checksum.append_relative_checksum(sums, sidecar)
    assert entry.endswith("  system-packages.txt")
    assert str(wheelhouse) not in sums.read_text("utf-8")

    relocated = tmp_path / "release"
    relocated.mkdir()
    for source in wheelhouse.iterdir():
        (relocated / source.name).write_bytes(source.read_bytes())
    expected, filename = (relocated / "SHA256SUMS").read_text("utf-8").split()
    assert checksum.sha256_file(relocated / filename) == expected


def test_sidecar_checksum_rejects_non_sibling_artifact(tmp_path: Path) -> None:

    sums = tmp_path / "wheelhouse" / "SHA256SUMS"
    sums.parent.mkdir()
    sums.write_text("", "utf-8")
    artifact = tmp_path / "elsewhere" / "system-packages.txt"
    artifact.parent.mkdir()
    artifact.write_text("python=3.13.14\n", "utf-8")
    with pytest.raises(checksum.ChecksumError, match="beside"):
        checksum.append_relative_checksum(sums, artifact)
