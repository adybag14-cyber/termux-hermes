from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import package_hermes_agent


def test_runtime_python_contract_accepts_only_compatible_313() -> None:
    assert "python3.13 (>= 3.13.15) | python (>= 3.13)" in package_hermes_agent.RUNTIME_DEPS
    assert "python3.13 (>= 3.13.15) | python (<< 3.14)" in package_hermes_agent.RUNTIME_DEPS
    assert "python3.13 (>= 3.13.15)" not in package_hermes_agent.RUNTIME_DEPS


@pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb is required")
def test_built_control_contains_both_python_alternatives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "app"
    hermes = app / "venv" / "bin" / "hermes"
    hermes.parent.mkdir(parents=True)
    hermes.write_text("#!/bin/sh\n", encoding="utf-8")
    hermes.chmod(0o755)
    (app / ".install_method").write_text("apt\n", encoding="utf-8")
    launcher = tmp_path / "launcher"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    output = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "package_hermes_agent.py",
            "--app",
            str(app),
            "--launcher",
            str(launcher),
            "--version",
            "0.20.6+termux2",
            "--hermes-version",
            "0.20.6",
            "--source-commit",
            "a" * 40,
            "--source-repository",
            "NousResearch/hermes-agent",
            "--wheelhouse-repository",
            "adybag14-cyber/termux-hermes",
            "--wheelhouse-tag",
            "test-wheelhouse",
            "--wheelhouse-sha256sums",
            "b" * 64,
            "--output-dir",
            str(output),
        ],
    )
    assert package_hermes_agent.main() == 0
    deb = output / "hermes-agent_0.20.6+termux2_aarch64.deb"
    depends = subprocess.check_output(["dpkg-deb", "-f", deb, "Depends"], text=True)
    assert "python3.13 (>= 3.13.15) | python (>= 3.13)" in depends
    assert "python3.13 (>= 3.13.15) | python (<< 3.14)" in depends
