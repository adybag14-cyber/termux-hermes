from __future__ import annotations

from pathlib import Path

import pytest

from scripts.termux_requirements import (
    expand_termux_requirements,
    filter_universal_requirements,
    lock_constraints,
)


def test_expands_termux_profile_and_removes_unsupported_optional_accelerators(
    tmp_path: Path,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "hermes-agent"
dependencies = [
  "uvicorn[standard]>=0.24,<1",
  "basepkg==1",
  "windows-only==1; sys_platform == 'win32'",
]
[project.optional-dependencies]
termux = ["python-telegram-bot[webhooks]==22.8", "hermes-agent[mcp]"]
mcp = ["mcp==2.0.0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    requirements = expand_termux_requirements(pyproject, python_version="3.13.15")
    assert "uvicorn<1,>=0.24" in requirements
    assert "python-telegram-bot==22.8" in requirements
    assert "mcp==2.0.0" in requirements
    assert all("standard" not in value for value in requirements)
    assert all("webhooks" not in value for value in requirements)
    assert all("windows-only" not in value for value in requirements)


def test_missing_profile_or_self_extra_fails_closed(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\nname='hermes-agent'\ndependencies=[]\n"
        "[project.optional-dependencies]\ntermux=['hermes-agent[missing]']\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="self-extra is missing"):
        expand_termux_requirements(pyproject)
    with pytest.raises(ValueError, match="profile is missing"):
        expand_termux_requirements(pyproject, profile="absent")


def test_lock_constraints_skip_platform_forks(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text(
        """
version = 1
[[package]]
name = "single"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }
[[package]]
name = "forked"
version = "1.0"
source = { registry = "https://pypi.org/simple" }
[[package]]
name = "forked"
version = "2.0"
source = { registry = "https://pypi.org/simple" }
[[package]]
name = "local"
version = "0.1"
source = { editable = "." }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    assert lock_constraints(lock) == ["single==1.2.3"]


def test_universal_lock_filters_non_android_markers_and_requires_exact_pins() -> None:
    requirements = filter_universal_requirements(
        """
base==1.0
windows-only==2.0 ; sys_platform == 'win32'
android-only==3.0 ; sys_platform == 'android'
""",
        python_version="3.13.15",
    )
    assert requirements == ["base==1.0", "android-only==3.0"]
    with pytest.raises(ValueError, match="not exactly pinned"):
        filter_universal_requirements("demo>=1\n", python_version="3.13.15")
