"""Exercise the exact helper shipped in the upstream patch without fetching upstream."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "upstream-v0.22.2-source-integrity.patch"
SDIST_HASH = "a" * 64
WHEEL_HASH = "b" * 64
SDIST_URL = "https://files.pythonhosted.org/packages/example_pkg-1.0.tar.gz"
WHEEL_URL = "https://files.pythonhosted.org/packages/example_pkg-1.0-py3-none-any.whl"


@pytest.fixture(scope="module")
def sources():
    # A new-file patch contains the helper in full. Execute those exact bytes,
    # so CI tests the deliverable rather than a separately maintained copy.
    section = PATCH.read_text(encoding="utf-8").split(
        "+++ b/scripts/termux/locked_sources.py\n", 1,
    )[1].split("\ndiff --git ", 1)[0]
    lines = section.splitlines()
    assert lines[0].startswith("@@ -0,0 ")
    assert all(line.startswith("+") for line in lines[1:])
    source = "\n".join(line[1:] for line in lines[1:]) + "\n"
    module = types.ModuleType("upstream_locked_sources")
    module.__file__ = str(ROOT / "upstream-fixture/scripts/termux/locked_sources.py")
    exec(compile(source, str(PATCH), "exec"), module.__dict__)
    return module


def package(name="example-pkg", version="1.0"):
    return {
        "name": name,
        "version": version,
        "source": {"registry": "https://pypi.org/simple"},
        "sdist": {"url": SDIST_URL, "hash": f"sha256:{SDIST_HASH}"},
        "wheels": [{"url": WHEEL_URL, "hash": f"sha256:{WHEEL_HASH}"}],
    }


def write_lock(path, rows):
    # JSON strings and simple inline tables are valid TOML for these fixtures.
    def toml(value):
        if isinstance(value, dict):
            return "{ " + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + " }"
        if isinstance(value, list):
            return "[" + ", ".join(toml(item) for item in value) + "]"
        return json.dumps(value)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join("[[package]]\n" + "\n".join(
            f"{key} = {toml(value)}" for key, value in row.items()
        ) for row in rows) + "\n" if rows else "package = []\n",
        encoding="utf-8-sig",
    )
    return path


def test_native_sdist_uses_locked_url_and_sha256(sources, tmp_path):
    lock = write_lock(tmp_path / "uv.lock", [package()])
    assert sources.native_requirement("Example_Pkg", "==1.0", lock_paths=(lock,)) == (
        f"example-pkg @ {SDIST_URL}#sha256={SDIST_HASH}"
    )


@pytest.mark.parametrize("spec", ["", ">=1.0", "==1.*", "~=1.0", "==1.0,!=1.0.1", "==2.0"])
def test_registry_inputs_reject_floating_or_missing_versions(sources, tmp_path, spec):
    lock = write_lock(tmp_path / "uv.lock", [package()])
    for resolver in (sources.native_requirement, sources.wheel_requirement):
        with pytest.raises(ValueError, match="exact version|No locked"):
            resolver("example-pkg", spec, lock_paths=(lock,))


@pytest.mark.parametrize("kind", ["sdist", "wheel"])
@pytest.mark.parametrize("bad_hash", [None, "", "sha256:" + "c" * 63, "sha512:" + "c" * 64])
def test_missing_or_invalid_hashes_fail_closed(sources, tmp_path, kind, bad_hash):
    row = package()
    artifact = row["sdist"] if kind == "sdist" else row["wheels"][0]
    if bad_hash is None:
        del artifact["hash"]
    else:
        artifact["hash"] = bad_hash
    lock = write_lock(tmp_path / "uv.lock", [row])
    resolver = sources.native_requirement if kind == "sdist" else sources.wheel_requirement
    with pytest.raises(ValueError, match="locked SHA-256"):
        resolver("example-pkg", "==1.0", lock_paths=(lock,))


@pytest.mark.parametrize("field", ["sdist", "wheels"])
def test_missing_artifact_fails_closed(sources, tmp_path, field):
    row = package()
    del row[field]
    lock = write_lock(tmp_path / "uv.lock", [row])
    resolver = sources.native_requirement if field == "sdist" else sources.wheel_requirement
    with pytest.raises(ValueError, match="artifact"):
        resolver("example-pkg", "==1.0", lock_paths=(lock,))


@pytest.mark.parametrize("url", ["", "http://example.invalid/pkg.tar.gz", SDIST_URL + "#untrusted"])
def test_invalid_locked_url_fails_closed(sources, tmp_path, url):
    row = package()
    row["sdist"]["url"] = url
    lock = write_lock(tmp_path / "uv.lock", [row])
    with pytest.raises(ValueError, match="artifact URL"):
        sources.native_requirement("example-pkg", "==1.0", lock_paths=(lock,))


@pytest.mark.parametrize("source", [{}, {"git": "https://example.invalid/repo.git#abcdef"}])
def test_non_registry_source_cannot_fall_back_to_pypi(sources, tmp_path, source):
    row = package()
    row["source"] = source
    lock = write_lock(tmp_path / "uv.lock", [row])
    with pytest.raises(ValueError, match="locked registry source"):
        sources.native_requirement("example-pkg", "==1.0", lock_paths=(lock,))


def test_ambiguous_locked_rows_are_rejected(sources, tmp_path):
    lock = write_lock(tmp_path / "uv.lock", [package(), package()])
    with pytest.raises(ValueError, match="one locked registry"):
        sources.wheel_requirement("example-pkg", "==1.0", lock_paths=(lock,))


def test_pm_fallback_and_primary_lock_precedence(sources, tmp_path):
    primary = write_lock(tmp_path / "uv.lock", [package("other")])
    pm = write_lock(tmp_path / "pm/uv.lock", [package()])
    assert SDIST_HASH in sources.native_requirement(
        "example-pkg", "==1.0", lock_paths=(primary, pm),
    )
    broken = package()
    del broken["sdist"]["hash"]
    write_lock(primary, [broken])
    with pytest.raises(ValueError, match="locked SHA-256"):
        sources.native_requirement("example-pkg", "==1.0", lock_paths=(primary, pm))


def test_setuptools_is_exact_and_hashed(sources, tmp_path):
    row = package("setuptools", "83.0.0")
    row["wheels"][0] = {
        "url": "https://files.pythonhosted.org/packages/5d/40/"
        "e1e72872c6354b306daef1703549e8e83b4d43cfea356311bf722a043752/"
        "setuptools-83.0.0-py3-none-any.whl",
        "hash": "sha256:29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3",
    }
    primary = write_lock(tmp_path / "uv.lock", [row])
    pm = write_lock(tmp_path / "pm/uv.lock", [])
    assert sources.wheel_requirement("setuptools", "==83.0.0", lock_paths=(primary, pm)) == (
        "setuptools==83.0.0 "
        "--hash=sha256:29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"
    )


def test_git_commit_is_preserved_and_moving_refs_are_rejected(sources):
    commit = "380bd2b59c67b0e1b04bbf3a90b11744f4f96644"
    repository = "git+https://github.com/giampaolo/psutil.git"
    # normalize_reqs already verifies this source against uv.lock.
    spec = f" @ {repository}@{commit}"
    assert sources.native_requirement("psutil", spec) == f"psutil{spec}"
    for revision in ("main", "v8.0.0", commit[:12]):
        with pytest.raises(ValueError, match="exact Git commit"):
            sources.native_requirement("psutil", f" @ {repository}@{revision}")


def test_pure_wheels_allow_only_locked_hashes(sources, tmp_path):
    row = package()
    second = "c" * 64
    row["wheels"].append({"url": WHEEL_URL, "hash": f"sha256:{second}"})
    lock = write_lock(tmp_path / "uv.lock", [row])
    assert sources.wheel_requirement("example-pkg", "==1.0", lock_paths=(lock,)) == (
        f"example-pkg==1.0 --hash=sha256:{WHEEL_HASH} --hash=sha256:{second}"
    )


def test_pip_accepts_locked_wheel_and_rejects_changed_bytes(sources, tmp_path):
    wheelhouse = tmp_path / "inputs"
    wheelhouse.mkdir()
    wheel = wheelhouse / "example_pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("example_pkg.py", "VALUE = 1\n")
        archive.writestr(
            "example_pkg-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: example-pkg\nVersion: 1.0\n",
        )
        archive.writestr(
            "example_pkg-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\n"
            "Tag: py3-none-any\n",
        )
        archive.writestr("example_pkg-1.0.dist-info/RECORD", "")
    row = package()
    row["wheels"][0]["hash"] = "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
    lock = write_lock(tmp_path / "uv.lock", [row])
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        sources.wheel_requirement("example-pkg", "==1.0", lock_paths=(lock,)) + "\n",
        encoding="utf-8",
    )

    def download(destination):
        return subprocess.run(
            [
                sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
                "--no-cache-dir", "download", "--no-index", "--no-deps", "--only-binary",
                ":all:", "--require-hashes", "--find-links", str(wheelhouse),
                "-r", str(requirements), "-d", str(destination),
            ],
            capture_output=True, text=True, timeout=30,
        )

    good = download(tmp_path / "good")
    assert good.returncode == 0, good.stdout + good.stderr
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("changed.txt", "bytes outside the locked artifact\n")
    bad = download(tmp_path / "bad")
    assert bad.returncode != 0
    assert "HASHES" in (bad.stdout + bad.stderr).upper()
