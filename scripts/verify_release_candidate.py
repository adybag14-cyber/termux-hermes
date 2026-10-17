"""Verify and promote an existing native build artifact without rebuilding it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bundle_metadata import file_record, validate_control, validate_identity, validate_stamp

BUILD_WORKFLOW = ".github/workflows/build-hermes-package.yml"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RELEASE_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
EVIDENCE = ("BUILD-METADATA.json", "WHEELHOUSE-MANIFEST.json", "RESOLVED.txt", "RELEASE-PINS.json")


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def validate_run(run: dict, repository: str, run_id: str) -> str:
    if not REPOSITORY.fullmatch(repository) or not re.fullmatch(r"[1-9]\d*", run_id):
        raise ValueError("repository and positive build run ID are required")
    expected = {"id": int(run_id), "path": BUILD_WORKFLOW,
                "status": "completed", "conclusion": "success", "event": "workflow_dispatch"}
    for field, value in expected.items():
        if run.get(field) != value:
            raise ValueError(f"build run {field} must be {value!r}")
    for field in ("repository", "head_repository"):
        if not isinstance(run.get(field), dict) or run[field].get("full_name") != repository:
            raise ValueError(f"build run {field} must be the publishing repository")
    commit = run.get("head_sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("build run head_sha must be a full commit SHA")
    return commit


def validate_tag(tag: str) -> None:
    if not RELEASE_TAG.fullmatch(tag) or tag.endswith(".") or ".." in tag:
        raise ValueError("release tag must be a simple immutable Git tag name")


def verify_checksums(candidate: Path, package_filename: str) -> dict[str, dict]:
    expected = {package_filename, *EVIDENCE}
    actual = {path.name for path in candidate.iterdir()}
    if actual != expected | {"SHA256SUMS"}:
        raise ValueError("candidate artifact must contain exactly the package and required evidence")
    if any(path.is_symlink() or not path.is_file() for path in candidate.iterdir()):
        raise ValueError("candidate artifacts must be regular files")
    checksums: dict[str, str] = {}
    for line in (candidate / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *]([A-Za-z0-9][A-Za-z0-9._+-]*)", line)
        if match is None:
            raise ValueError("SHA256SUMS contains an invalid digest or unsafe filename")
        digest, name = match.groups()
        if name in checksums:
            raise ValueError(f"SHA256SUMS repeats {name}")
        checksums[name] = digest
    if set(checksums) != expected:
        raise ValueError("SHA256SUMS must cover every candidate package and evidence file")
    records = {}
    for name, expected_hash in checksums.items():
        record = file_record(candidate / name)
        if record["sha256"] != expected_hash:
            raise ValueError(f"candidate checksum mismatch: {name}")
        records[name] = record
    records["SHA256SUMS"] = file_record(candidate / "SHA256SUMS")
    return records


def installer_assignment(text: str, name: str) -> str:
    lines = [line[len(name) + 1:] for line in text.splitlines() if line.startswith(name + "=")]
    if len(lines) != 1:
        raise ValueError(f"installer must contain one reviewed {name} assignment")
    value = lines[0]
    if len(value) < 2 or value[0] not in ("'", '"') or value[-1] != value[0]:
        raise ValueError(f"installer {name} must use a quoted, single-line value")
    value = value[1:-1]
    if any(character in value for character in ("\r", "\n", "\\", "`")):
        raise ValueError(f"installer {name} cannot contain shell expressions")
    return value


def verify_installer(installer: Path, repository: str, release_tag: str,
                     version: str, package_filename: str, digest: str) -> dict:
    text = installer.read_text(encoding="utf-8")
    expected = {
        "PACKAGE_VERSION": version,
        "PACKAGE_SHA256": digest,
        "PACKAGE_RELEASE_URL": (
            f"https://github.com/{repository}/releases/download/{release_tag}/"
            + quote(package_filename, safe="")
        ),
    }
    for name, value in expected.items():
        if installer_assignment(text, name) != value:
            raise ValueError(f"installer {name} does not match the exact release candidate")
    filename = installer_assignment(text, "PACKAGE_FILENAME")
    if filename not in (package_filename, "hermes-agent_${PACKAGE_VERSION}_aarch64.deb"):
        raise ValueError("installer PACKAGE_FILENAME does not match the exact release candidate")
    return file_record(installer)


def verify_candidate(candidate: Path, run: dict, repository: str, run_id: str,
                     release_tag: str, pins: dict, installer: Path) -> dict:
    head = validate_run(run, repository, run_id)
    validate_tag(release_tag)
    required_pins = ("source_repository", "source_tag", "source_commit", "package_version",
                     "feature_profile", "termux_image")
    if any(not isinstance(pins.get(field), str) for field in required_pins):
        raise ValueError("reviewed release pins are incomplete")
    validate_identity(pins["source_tag"], pins["source_commit"], pins["package_version"],
                      head, pins["termux_image"])
    if pins["feature_profile"] != "termux":
        raise ValueError("reviewed feature profile must remain termux")
    filename = f"hermes-agent_{pins['package_version']}_aarch64.deb"
    records = verify_checksums(candidate, filename)
    if read_json(candidate / "RELEASE-PINS.json") != pins:
        raise ValueError("candidate release pins differ from the reviewed checkout")
    metadata = read_json(candidate / "BUILD-METADATA.json")
    package = metadata.get("package", {})
    expected_package = {"name": "hermes-agent", "architecture": "aarch64",
                        "version": pins["package_version"], **records[filename]}
    if package != expected_package:
        raise ValueError("candidate package metadata does not describe its actual bytes")
    upstream = metadata.get("upstream", {})
    for key, pin in (("repository", "source_repository"), ("tag", "source_tag"),
                     ("commit", "source_commit")):
        if upstream.get(key) != pins[pin]:
            raise ValueError(f"candidate upstream {key} differs from the reviewed release")
    validate_stamp(upstream.get("install_stamp"), pins["source_tag"], pins["source_commit"])
    packaging = metadata.get("packaging", {})
    if packaging.get("repository") != repository or packaging.get("commit") != head:
        raise ValueError("candidate packaging commit does not match the successful build run")
    if packaging.get("builder_image") != pins["termux_image"]:
        raise ValueError("candidate builder image differs from the reviewed release")
    runtime = metadata.get("runtime", {})
    if runtime.get("feature_profile") != "termux" or runtime.get("enabled_features") != [
        "acp", "cron", "mcp", "telegram", "termux"
    ]:
        raise ValueError("candidate must retain the complete declared Termux feature profile")
    if metadata.get("inspection", {}).get("package_contract") != "passed":
        raise ValueError("candidate package inspection did not pass")
    control = subprocess.run(
        ["dpkg-deb", "--field", str(candidate / filename)], check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    validate_control(control, pins["package_version"])
    installer_record = verify_installer(
        installer, repository, release_tag, pins["package_version"],
        filename, records[filename]["sha256"],
    )
    return {
        "schema_version": 1, "build_run_id": int(run_id), "build_head_sha": head,
        "build_run_url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "repository": repository, "release_tag": release_tag,
        "package_filename": filename, "package_version": pins["package_version"],
        "package_sha256": records[filename]["sha256"], "source_tag": pins["source_tag"],
        "source_commit": pins["source_commit"], "termux_image": pins["termux_image"],
        "installer": installer_record, "files": records,
    }


def validate_draft(release: dict, tag: str, target_commit: str) -> int:
    validate_tag(tag)
    if not re.fullmatch(r"[a-f0-9]{40}", target_commit) or target_commit == "0" * 40:
        raise ValueError("draft target must be a full publishing commit SHA")
    release_id = release.get("id")
    if type(release_id) is not int or release_id <= 0:
        raise ValueError("draft must have a positive numeric release ID")
    if (release.get("tag_name") != tag or release.get("draft") is not True
            or release.get("prerelease") is not False
            or release.get("published_at") is not None
            or release.get("target_commitish") != target_commit):
        raise ValueError("release must be the unpublished draft for this tag and publishing commit")
    return release_id


def verify_release_assets(candidate: Path, release: dict, tag: str,
                          release_id: int, target_commit: str) -> None:
    actual_id = validate_draft(release, tag, target_commit)
    if type(release_id) is not int or actual_id != release_id:
        raise ValueError("GitHub response does not match the selected numeric release ID")
    metadata = read_json(candidate / "BUILD-METADATA.json")
    package_filename = metadata.get("package", {}).get("file", "")
    if not re.fullmatch(r"hermes-agent_[0-9][A-Za-z0-9.+~-]*_aarch64\.deb", package_filename):
        raise ValueError("invalid candidate package filename")
    records = verify_checksums(candidate, package_filename)
    assets = release.get("assets")
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("GitHub release assets are missing")
    names = [asset.get("name") for asset in assets]
    if len(names) != len(set(names)) or set(names) != set(records):
        raise ValueError("GitHub release asset set differs from the exact candidate")
    for asset in assets:
        expected = records[asset["name"]]
        if (asset.get("state") != "uploaded" or asset.get("size") != expected["size"]
                or asset.get("digest") != f"sha256:{expected['sha256']}"):
            raise ValueError(f"GitHub asset digest/size/state mismatch: {asset['name']}")


def releases_for_tag(repository: str, tag: str) -> list[dict]:
    """The authenticated list includes unpublished drafts absent from /tags/."""
    if not REPOSITORY.fullmatch(repository):
        raise ValueError("invalid repository name")
    validate_tag(tag)
    response = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if response.returncode != 0:
        raise ValueError("could not establish release absence: " + response.stderr.strip())
    try:
        pages = json.loads(response.stdout)
    except ValueError as error:
        raise ValueError("invalid GitHub release list JSON") from error
    if (not isinstance(pages, list) or not pages
            or any(not isinstance(page, list) for page in pages)
            or any(not isinstance(release, dict)
                   or not isinstance(release.get("tag_name"), str)
                   for page in pages for release in page)):
        raise ValueError("invalid paginated GitHub release list")
    return [release for page in pages for release in page if release["tag_name"] == tag]


def draft_release_id(repository: str, tag: str, target_commit: str) -> int:
    matches = releases_for_tag(repository, tag)
    if len(matches) != 1:
        raise ValueError("expected exactly one matching draft release")
    return validate_draft(matches[0], tag, target_commit)


def ensure_new_release(repository: str, tag: str) -> None:
    if releases_for_tag(repository, tag):
        raise ValueError(f"immutable release or draft already exists: {tag}")
    response = subprocess.run(
        ["gh", "api", "--include", f"repos/{repository}/git/ref/tags/{tag}"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    status = re.search(r"^HTTP/\S+ (\d{3})\b", response.stdout, flags=re.MULTILINE)
    if response.returncode == 0:
        raise ValueError(f"immutable Git tag already exists: {tag}")
    if status is None or status[1] != "404":
        raise ValueError("could not establish tag absence: " + response.stderr.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    candidate_parser = commands.add_parser("candidate")
    for command in (run_parser, candidate_parser):
        command.add_argument("--run-json", type=Path, required=True)
        command.add_argument("--repository", required=True)
        command.add_argument("--run-id", required=True)
    candidate_parser.add_argument("--candidate", type=Path, required=True)
    candidate_parser.add_argument("--pins", type=Path, required=True)
    candidate_parser.add_argument("--installer", type=Path, required=True)
    candidate_parser.add_argument("--release-tag", required=True)
    candidate_parser.add_argument("--github-output", type=Path)
    assets_parser = commands.add_parser("assets")
    assets_parser.add_argument("--candidate", type=Path, required=True)
    assets_parser.add_argument("--release-json", type=Path, required=True)
    assets_parser.add_argument("--release-tag", required=True)
    assets_parser.add_argument("--release-id", type=int, required=True)
    assets_parser.add_argument("--target-commit", required=True)
    draft_parser = commands.add_parser("draft-id")
    draft_parser.add_argument("--repository", required=True)
    draft_parser.add_argument("--release-tag", required=True)
    draft_parser.add_argument("--target-commit", required=True)
    new_parser = commands.add_parser("new-release")
    new_parser.add_argument("--repository", required=True)
    new_parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            commit = validate_run(read_json(args.run_json), args.repository, args.run_id)
            print(f"Successful native build {args.run_id} at {commit}")
        elif args.command == "candidate":
            result = verify_candidate(
                args.candidate, read_json(args.run_json), args.repository, args.run_id,
                args.release_tag, read_json(args.pins), args.installer,
            )
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as stream:
                    for key in ("package_filename", "package_version", "package_sha256",
                                "source_tag", "source_commit", "termux_image", "build_head_sha"):
                        value = result[key]
                        if any(character in value for character in "\r\n\0"):
                            raise ValueError("invalid GitHub output value")
                        stream.write(f"{key}={value}\n")
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "assets":
            verify_release_assets(args.candidate, read_json(args.release_json), args.release_tag,
                                  args.release_id, args.target_commit)
            print("GitHub draft assets match every verified candidate digest and size")
        elif args.command == "draft-id":
            print(draft_release_id(args.repository, args.release_tag, args.target_commit))
        else:
            ensure_new_release(args.repository, args.release_tag)
            print(f"Release and Git tag are available: {args.release_tag}")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"verify_release_candidate: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
