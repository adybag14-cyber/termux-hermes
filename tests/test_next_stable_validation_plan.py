from pathlib import Path
import subprocess

import pytest

from scripts.plan_next_stable_validation import GROUPS, changed_paths, select_checks


@pytest.mark.parametrize("changed,groups", [
    (["scripts/compatibility_probe_browser.sh"], ["browser"]),
    (["scripts/compatibility_probe_desktop.sh", "scripts/compatibility_probe_gateway.sh"], ["desktop", "gateway"]),
    (["docs/compatibility-0.22.2-1.md", "audit/native-probes/example.json"], []),
    (["patches/next-stable/cua-driver.patch"], []),
    (["patches/next-stable/compatibility.patch"], list(GROUPS)),
    (["scripts/probe_native_compatibility.py"], list(GROUPS)),
    (["manifest/release.json"], list(GROUPS)),
    (["scripts/plan_next_stable_validation.py"], list(GROUPS)),
])
def test_select_only_affected_components(changed, groups):
    result = select_checks("components", changed)
    assert result == {"required": bool(groups), "groups": groups}


@pytest.mark.parametrize("path", [
    "manifest/release.json", "patches/upstream-v0.22.2-core.patch",
    "patches/next-stable/compatibility.patch", "scripts/check_next_stable_candidate.sh",
    "scripts/check_next_stable_lifecycle.py", ".github/workflows/next-stable-candidate.yml",
])
def test_candidate_rebuilds_for_each_build_or_lifecycle_input(path):
    assert select_checks("candidate", [path])["required"]


def test_candidate_does_not_repeat_for_independent_probes_or_evidence():
    assert not select_checks("candidate", [
        "scripts/compatibility_probe_browser.sh", "scripts/probe_native_compatibility.py",
        "docs/compatibility-0.22.2-1.md", "audit/evidence.json",
    ])["required"]


def test_unknown_history_and_explicit_dispatch_retain_validation():
    assert select_checks("components", None)["groups"] == list(GROUPS)
    assert select_checks("candidate", None)["required"]
    assert select_checks("components", [], requested="browser")["groups"] == ["browser"]
    with pytest.raises(ValueError):
        select_checks("components", [], requested="arbitrary")
    with pytest.raises(ValueError):
        select_checks("arbitrary", [])


def test_initial_or_malformed_events_do_not_skip_checks(tmp_path):
    assert changed_paths({}, event_name="pull_request", repo=tmp_path) is None
    assert changed_paths({"action": "synchronize", "before": "bad"}, event_name="pull_request", repo=tmp_path) is None
    assert changed_paths({}, event_name="workflow_dispatch", repo=tmp_path) is None


def test_real_git_comparison_and_force_push_fallback(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Validation fixture")
    git("config", "user.email", "fixture@example.invalid")
    path = tmp_path / "docs" / "note.md"
    path.parent.mkdir()
    path.write_text("first\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "first")
    before = git("rev-parse", "HEAD")
    path.write_text("second\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "second")
    after = git("rev-parse", "HEAD")
    event = {"action": "synchronize", "before": before, "pull_request": {"head": {"sha": after}}}
    assert changed_paths(event, event_name="pull_request", repo=tmp_path) == ["docs/note.md"]
    # Reversed ancestry represents replaced history, so all checks are retained.
    event["before"] = after
    event["pull_request"]["head"]["sha"] = before
    assert changed_paths(event, event_name="pull_request", repo=tmp_path) is None
    event["before"] = "0" * 40
    assert changed_paths(event, event_name="pull_request", repo=tmp_path) is None


def test_workflow_triggers_cover_shared_inputs_and_native_checkout_matches_plan():
    import fnmatch
    import re

    root = Path(__file__).resolve().parents[1]
    for name in ('compatibility-probes.yml', 'next-stable-candidate.yml'):
        content = (root / '.github' / 'workflows' / name).read_text(encoding='utf-8')
        trigger = content.split('permissions:', 1)[0]
        patterns = re.findall(r'''^\s+- ['"]([^'"]+)['"]$''', trigger, re.MULTILINE)
        for path in ('manifest/release.json', 'patches/upstream-v0.22.2-core.patch',
                     'scripts/plan_next_stable_validation.py'):
            assert any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), (name, path)
        # Both the planner and its native worker compare and test the PR head.
        assert content.count('ref: ${{ github.event.pull_request.head.sha || github.sha }}') == 2
