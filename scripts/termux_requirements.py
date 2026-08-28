#!/usr/bin/env python3
"""Generate an Android-safe dependency profile from an exact Hermes source tree."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import tomllib
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SELF_NAME = "hermes-agent"
DROP_EXTRAS = {
    # The pure-Python Uvicorn/H11 path is reliable on Android. Its standard
    # accelerators do not publish PEP 738 wheels and are not required.
    "uvicorn": {"standard"},
    # Polling works without Tornado and avoids another unsupported extension.
    "python-telegram-bot": {"webhooks"},
}


def _android_environment(python_version: str | None = None) -> dict[str, str]:
    env = default_environment()
    env.update(
        {
            "sys_platform": "android",
            "platform_system": "Android",
            "platform_machine": "aarch64",
            "platform_release": "android",
            "os_name": "posix",
        }
    )
    if python_version:
        parts = python_version.split(".")
        env["python_version"] = ".".join(parts[:2])
        env["python_full_version"] = python_version
    return env


def _render_requirement(requirement: Requirement, extras: set[str]) -> str:
    rendered = requirement.name
    if extras:
        rendered += "[" + ",".join(sorted(extras)) + "]"
    if requirement.url:
        rendered += f" @ {requirement.url}"
    else:
        rendered += str(requirement.specifier)
    if requirement.marker:
        rendered += f"; {requirement.marker}"
    return rendered


def expand_termux_requirements(
    pyproject: Path, *, profile: str = "termux", python_version: str | None = None
) -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data["project"]
    extras_table = project.get("optional-dependencies", {})
    if profile not in extras_table:
        raise ValueError(f"Hermes optional dependency profile is missing: {profile}")
    pending = list(project.get("dependencies", []))
    pending.extend(extras_table[profile])
    expanded_extras: set[str] = {profile}
    output: list[str] = []
    seen: set[str] = set()
    marker_env = _android_environment(python_version)

    while pending:
        req = Requirement(pending.pop(0))
        name = canonicalize_name(req.name)
        if name == SELF_NAME:
            for extra in sorted(req.extras):
                if extra in expanded_extras:
                    continue
                if extra not in extras_table:
                    raise ValueError(f"Hermes self-extra is missing: {extra}")
                expanded_extras.add(extra)
                pending.extend(extras_table[extra])
            continue
        if req.marker and not req.marker.evaluate(marker_env):
            continue
        kept_extras = set(req.extras) - DROP_EXTRAS.get(name, set())
        rendered = _render_requirement(req, kept_extras)
        if rendered not in seen:
            seen.add(rendered)
            output.append(rendered)

    return sorted(output, key=lambda value: canonicalize_name(Requirement(value).name))


def lock_constraints(lockfile: Path) -> list[str]:
    data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    versions: dict[str, set[str]] = {}
    for package in data.get("package", []):
        name = package.get("name")
        version = package.get("version")
        source = package.get("source") or {}
        if not name or not version or "registry" not in source:
            continue
        versions.setdefault(canonicalize_name(name), set()).add(str(version))
    return [
        f"{name}=={next(iter(found))}"
        for name, found in sorted(versions.items())
        if len(found) == 1
    ]


def filter_universal_requirements(text: str, *, python_version: str) -> list[str]:
    marker_env = _android_environment(python_version)
    output: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "--")):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate(marker_env):
            continue
        versions = [item.version for item in req.specifier if item.operator == "=="]
        if len(versions) != 1:
            raise ValueError(f"resolved requirement is not exactly pinned: {line}")
        output.append(f"{req.name}=={versions[0]}")
    return output


def resolve_android_requirements(
    requirements: Path,
    constraints: Path,
    *,
    uv: str,
    python_version: str,
) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="termux-hermes-lock-") as temp:
        universal = Path(temp) / "universal.txt"
        subprocess.run(
            [
                uv,
                "pip",
                "compile",
                str(requirements),
                "--constraint",
                str(constraints),
                "--universal",
                "--python-version",
                python_version,
                "--no-annotate",
                "--no-header",
                "--output-file",
                str(universal),
            ],
            check=True,
        )
        return filter_universal_requirements(
            universal.read_text(encoding="utf-8"), python_version=python_version
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--constraints", type=Path, required=True)
    parser.add_argument("--resolved", type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--profile", default="termux")
    parser.add_argument("--python-version", default="3.13.15")
    args = parser.parse_args(argv)
    requirements = expand_termux_requirements(
        args.pyproject, profile=args.profile, python_version=args.python_version
    )
    constraints = lock_constraints(args.lock)
    args.requirements.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    args.constraints.write_text("\n".join(constraints) + "\n", encoding="utf-8")
    resolved: list[str] | None = None
    if args.resolved:
        resolved = resolve_android_requirements(
            args.requirements,
            args.constraints,
            uv=args.uv,
            python_version=args.python_version,
        )
        args.resolved.write_text("\n".join(resolved) + "\n", encoding="utf-8")
    print(
        f"Generated {len(requirements)} direct Android requirements and "
        f"{len(constraints)} lock constraints"
        + (f"; resolved {len(resolved)} packages" if resolved is not None else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
