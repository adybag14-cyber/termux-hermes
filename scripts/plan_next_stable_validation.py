#!/usr/bin/env python3
"""Choose native checks affected by this PR update; uncertain history runs all.

A synchronize event is compared with its exact previous head, not the PR's
cumulative diff. Documentation/evidence updates do not rebuild identical inputs.
The selected jobs still perform the ordinary native build and behavior gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

GROUPS = ("uvloop", "matrix", "nemo", "browser", "desktop", "audio", "gateway")
PLANNER = "scripts/plan_next_stable_validation.py"
COMPONENT_INPUTS = {
    PLANNER, ".github/workflows/compatibility-probes.yml",
    "patches/next-stable/compatibility.patch",
    "scripts/probe_native_compatibility.py", "scripts/probe_native_compatibility.sh",
}
CANDIDATE_INPUTS = {
    PLANNER, ".github/workflows/next-stable-candidate.yml",
    "patches/next-stable/compatibility.patch",
    "scripts/check_next_stable_candidate.sh", "scripts/check_next_stable_lifecycle.py",
}
GROUP_INPUTS = {
    "scripts/compatibility_probe_browser.sh": "browser",
    "scripts/compatibility_probe_desktop.sh": "desktop",
    "scripts/compatibility_probe_gateway.sh": "gateway",
}


def shared_input(path: str) -> bool:
    return path.startswith("manifest/") or path.startswith("patches/upstream-")


def select_checks(kind: str, changed: list[str] | None, *, requested: str = "all") -> dict:
    if kind not in {"components", "candidate"}:
        raise ValueError("unknown validation kind")
    if requested not in ("all", *GROUPS):
        raise ValueError("unknown native probe group")
    if kind == "candidate":
        run = changed is None or any(shared_input(p) or p in CANDIDATE_INPUTS for p in changed)
        return {"required": run, "groups": []}
    if requested != "all":
        return {"required": True, "groups": [requested]}
    if changed is None or any(shared_input(p) or p in COMPONENT_INPUTS for p in changed):
        groups = list(GROUPS)
    else:
        affected = {GROUP_INPUTS[p] for p in changed if p in GROUP_INPUTS}
        groups = [g for g in GROUPS if g in affected]
    return {"required": bool(groups), "groups": groups}


def changed_paths(event: dict, *, event_name: str, repo: Path) -> list[str] | None:
    """Fail conservatively on initial events, force pushes or unavailable history."""
    if event_name != "pull_request" or event.get("action") != "synchronize":
        return None
    before = event.get("before", "")
    after = event.get("pull_request", {}).get("head", {}).get("sha", "")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
               for value in (before, after)) or before == after:
        return None

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, timeout=45)

    try:
        # A force-push comparison is deliberately treated as unknown rather than
        # dropping a check because its previous input no longer has ancestry.
        for commit in (before, after):
            git("cat-file", "-e", commit + "^{commit}")
        git("merge-base", "--is-ancestor", before, after)
        raw = git("diff", "--no-renames", "--name-only", "-z", before, after, "--").stdout
        return [p.decode("utf-8") for p in raw.split(b"\0") if p]
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("components", "candidate"), required=True)
    parser.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "event.json")))
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--requested", default=os.environ.get("REQUESTED_GROUP", "all") or "all")
    args = parser.parse_args()
    event = json.loads(args.event.read_text(encoding="utf-8"))
    changed = changed_paths(event, event_name=args.event_name, repo=args.repo)
    requested = args.requested if args.event_name == "workflow_dispatch" else "all"
    result = select_checks(args.kind, changed, requested=requested)
    result["change_basis"] = "exact previous PR head" if changed is not None else "full validation (no reliable previous head)"
    result["changed_paths"] = changed
    print(json.dumps(result, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("required=" + str(result["required"]).lower() + "\n")
            stream.write("groups=" + json.dumps(result["groups"], separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
