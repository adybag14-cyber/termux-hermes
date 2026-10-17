#!/usr/bin/env python3
"""Fetch the exact proven compatibility candidate for an isolated native probe.

Run on the GitHub host with GH_TOKEN/actions:read. Credentials are used only
for api.github.com; signed artifact downloads use a separate anonymous opener.
The output directory appears only after every check succeeds. No installation,
Docker invocation, release operation, or arbitrary ZIP extraction is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile
import zlib


class VerificationError(ValueError):
    """A bounded, credential-free diagnostic suitable for CI output."""


@dataclass(frozen=True)
class EntryPin:
    member: str
    size: int
    sha256: str
    crc32: int
    output: str | None = None


IDENTITY = {
    "purpose": "next-stable compatibility candidate; do not publish",
    "published": False,
    "version_bumped": False,
    "package": "hermes-agent_0.22.2-1_aarch64.deb",
    "package_sha256": "1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a",
    "packaging_commit": "e271e922a2e71fd18591c45e9b98b8c7f9fffe02",
    "workflow_ref_commit": "6f2f8e28deab2729673b2efbbf4054c5dd715a65",
    "upstream_commit": "d923a5eb487a17c0a68801bba9ef0f56c81040a8",
    "upstream_tag": "v0.22.2",
    "patches": {
        "patches/upstream-v0.22.2-imports.patch":
            "f95683a50151c690b645ed83dc3dddc93354364b9e091fa54ed62deaeeb83729",
        "patches/upstream-v0.22.2-snapshot.patch":
            "b762b8ec3429064193d80cd8c9fe80571c83d085c1cb20409ab9cfc7fbc844aa",
        "patches/upstream-v0.22.2-source-integrity.patch":
            "ae8d1a7a6137c8ba5c6b642ad1d4b69f1877cfaeb2fb6de9720f1f18d35815f3",
        "patches/upstream-v0.22.2-termux.patch":
            "6fafa8a39ed0295e6788755206a4c7c946e9246bb99484b5a23eb186e54608d2",
        "patches/next-stable/compatibility.patch":
            "77ac41bc11a6facd928f4cef577642b9eeb042ce3da7d820478aa49e1d98fa1e",
    },
}
SELECTION = {
    "schema": 1,
    "target": "linux-arm64-bionic",
    "extras": ["acp", "cron", "matrix", "mcp", "telegram", "termux", "uvloop"],
    "stamp": "3b2935496d2e947be1904f37052d1fcbae409418e892a52973d5a46fc1df4d7f",
    "bundled_wheels": {
        "path": "bundled-wheels.json",
        "sha256": "d2dc66575cf8aa5ef828e5e536b4d55b8801143101b7e608f6fb4878c2397904",
    },
    "uv_lock_sha256": "72abb87a634769baaf30830cd317892053c6e15f8e9519b085524fa0ed542829",
    "pm_lock_sha256": "49b79259220160f147255078a19af541a5f328d3871c8041cc1eb909d19eb549",
    "requirements_sha256": "f3e32ca1cae5bb50a30e0957ed136f992d546e4475fb8bc73350790e9e762698",
}


@dataclass(frozen=True)
class CandidatePin:
    repository: str = "adybag14-cyber/termux-hermes"
    repository_id: int = 1305668154
    run_id: int = 39048514731
    head_sha: str = "e271e922a2e71fd18591c45e9b98b8c7f9fffe02"
    artifact_id: int = 12107225801
    artifact_name: str = "hermes-termux-next-stable-candidate"
    archive_size: int = 222119336
    archive_sha256: str = "c49f41590424520b99136800b7ba9fa41f3ab3926d418131cdf686da812d849b"
    identity_json: str = json.dumps(IDENTITY, sort_keys=True)
    selection_json: str = json.dumps(SELECTION, sort_keys=True)
    entries: tuple[EntryPin, ...] = (
        EntryPin(
            "hermes-source/termux-build/deb/hermes-agent_0.22.2-1_aarch64.deb",
            222089768,
            "1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a",
            0xA827D502,
            "hermes-agent_0.22.2-1_aarch64.deb",
        ),
        EntryPin(
            "next-stable-evidence/CANDIDATE-IDENTITY.json", 1086,
            "bd45eceb7ffecf4e892243f6e964fd28337f1be20abee39435d934cc768fb5a5",
            0x7E445162, "CANDIDATE-IDENTITY.json",
        ),
        EntryPin(
            "next-stable-evidence/COLD-CACHE-LIFECYCLE.json", 17390,
            "3c670908208101819648f32f779b35a62966e8a01e484281a1c7a0d1f6704048",
            0x67E81708,
        ),
        EntryPin(
            "next-stable-evidence/USER-STATE-BEFORE.sha256", 460,
            "333d3d72fd5eeeb600559f9b27bbb70fc4b2f772dac0c8d7f6a81e7905ac2d64",
            0xEEF93307,
        ),
        EntryPin(
            "next-stable-evidence/cold-cache-install.log", 166,
            "696310b071d5db4821130c5d517bdce729922739b6fb8a8a500d8372cdbc442b",
            0x9B70E533,
        ),
        EntryPin(
            "next-stable-evidence/lifecycle.log", 8475,
            "8c7e1509bba656c667ea8a6f824d87064787c4874658abef07bf41afdab80240",
            0x1230FA5F,
        ),
        EntryPin(
            "hermes-source/termux-build/payload/.work/venv-selection.json", 653,
            "5d7eef31190f9152c3b8005f3c9cc8bb05a69fdb57b883c648edcfe4db2cf1ce",
            0x095D5AE9, "venv-selection.json",
        ),
    )


PIN = CandidatePin()
CHUNK_SIZE = 1024 * 1024


def _require(actual: object, expected: object, label: str) -> None:
    if type(actual) is not type(expected) or actual != expected:
        raise VerificationError(f"{label} mismatch")


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise VerificationError(f"invalid {label} object")
    return value


def _json_object(raw: bytes, label: str) -> dict:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"duplicate key in {label}")
            result[key] = value
        return result

    try:
        return _object(json.loads(raw, object_pairs_hook=unique), label)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid {label} JSON") from None


def validate_metadata(run: dict, artifact: dict, pin: CandidatePin = PIN) -> None:
    for key, expected in (
        ("id", pin.run_id), ("head_sha", pin.head_sha),
        ("status", "completed"), ("conclusion", "success"),
        ("path", ".github/workflows/next-stable-candidate.yml"),
    ):
        _require(run.get(key), expected, f"candidate run {key}")
    for key in ("repository", "head_repository"):
        repo = _object(run.get(key), f"run {key}")
        _require(repo.get("full_name"), pin.repository, f"run {key} name")
        _require(repo.get("id"), pin.repository_id, f"run {key} ID")
    for key, expected in (
        ("id", pin.artifact_id), ("name", pin.artifact_name),
        ("size_in_bytes", pin.archive_size), ("digest", "sha256:" + pin.archive_sha256),
        ("expired", False),
    ):
        _require(artifact.get(key), expected, f"candidate artifact {key}")
    associated = _object(artifact.get("workflow_run"), "artifact workflow_run")
    for key, expected in (
        ("id", pin.run_id), ("head_sha", pin.head_sha),
        ("repository_id", pin.repository_id), ("head_repository_id", pin.repository_id),
    ):
        _require(associated.get(key), expected, f"artifact association {key}")
    try:
        expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise ValueError
    except (KeyError, AttributeError, TypeError, ValueError):
        raise VerificationError("candidate artifact expiry is invalid or elapsed") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_signed_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.port in (None, 443)
            and parsed.username is None and parsed.password is None
            and not parsed.fragment
            and not any(ord(char) <= 32 or ord(char) == 127 for char in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise VerificationError("GitHub returned an invalid HTTPS artifact destination")


class GitHubClient:
    """Only API requests carry a token; redirects never inherit request headers."""

    def __init__(self, token: str):
        if not token.strip():
            raise VerificationError("GH_TOKEN with actions:read is required")
        self._token = token
        self._api_opener = build_opener(_NoRedirect())
        self._download_opener = build_opener(_NoRedirect())

    def _api_request(self, endpoint: str) -> Request:
        return Request(
            "https://api.github.com/" + endpoint,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "termux-hermes-candidate-verifier",
            },
        )

    def metadata(self, endpoint: str) -> dict:
        try:
            with self._api_opener.open(self._api_request(endpoint), timeout=30) as response:
                if response.status != 200:
                    raise VerificationError("GitHub metadata request did not return HTTP 200")
                raw = response.read(2 * CHUNK_SIZE + 1)
                if len(raw) > 2 * CHUNK_SIZE:
                    raise VerificationError("GitHub metadata response exceeds its size limit")
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise VerificationError(f"GitHub metadata request failed (HTTP {status})") from None
        except (OSError, http.client.HTTPException):
            raise VerificationError("GitHub metadata request failed") from None
        return _json_object(raw, "GitHub metadata")

    def artifact_stream(self, endpoint: str):
        try:
            response = self._api_opener.open(self._api_request(endpoint), timeout=30)
        except HTTPError as exc:
            status = exc.code
            destination = exc.headers.get("Location", "")
            exc.close()
            if status not in (302, 307):
                raise VerificationError(
                    f"GitHub artifact redirect request failed (HTTP {status})"
                ) from None
        except (OSError, http.client.HTTPException):
            raise VerificationError("GitHub artifact redirect request failed") from None
        else:
            response.close()
            raise VerificationError("GitHub artifact request did not return a download redirect")
        _validate_signed_url(destination)
        # A new request on a separate opener: no Authorization, cookies or API headers.
        request = Request(destination, headers={
            "Accept-Encoding": "identity", "User-Agent": "termux-hermes-candidate-verifier",
        })
        try:
            response = self._download_opener.open(request, timeout=30)
            if response.status != 200:
                response.close()
                raise VerificationError("Artifact download did not return HTTP 200")
            return response
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise VerificationError(f"Artifact download failed (HTTP {status})") from None
        except (OSError, http.client.HTTPException):
            raise VerificationError("Artifact download failed") from None


def _save_archive(stream, destination: Path, pin: CandidatePin) -> None:
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + 600
    try:
        with destination.open("xb") as target:
            while chunk := stream.read(CHUNK_SIZE):
                total += len(chunk)
                if total > pin.archive_size:
                    raise VerificationError("candidate ZIP exceeds the frozen size")
                if time.monotonic() > deadline:
                    raise VerificationError("candidate ZIP download exceeded its time limit")
                digest.update(chunk)
                target.write(chunk)
    except (OSError, http.client.HTTPException):
        raise VerificationError("candidate ZIP transfer or staging failed") from None
    _require(total, pin.archive_size, "downloaded candidate ZIP size")
    _require(digest.hexdigest(), pin.archive_sha256, "downloaded candidate ZIP SHA-256")


def _safe_member(info: zipfile.ZipInfo) -> bool:
    name = info.filename
    mode = stat.S_IFMT(info.external_attr >> 16)
    return (
        bool(name) and "\\" not in name and "\x00" not in name and ":" not in name
        and not PurePosixPath(name).is_absolute()
        and all(part not in ("", ".", "..") for part in name.split("/"))
        and not info.is_dir() and mode in (0, stat.S_IFREG)
        and not info.flag_bits & 1
        and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
    )


def _verify_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo,
                  entry: EntryPin, output: Path) -> None:
    _require(info.file_size, entry.size, "candidate ZIP member size")
    _require(info.CRC, entry.crc32, "candidate ZIP member declared CRC")
    target = None
    total, crc = 0, 0
    digest = hashlib.sha256()
    try:
        if entry.output:
            if "/" in entry.output or "\\" in entry.output or entry.output in (".", ".."):
                raise VerificationError("invalid fixed output filename")
            target = (output / entry.output).open("xb")
        with archive.open(info) as source:
            while chunk := source.read(CHUNK_SIZE):
                total += len(chunk)
                if total > entry.size:
                    raise VerificationError("candidate ZIP member exceeds its frozen size")
                digest.update(chunk)
                crc = zlib.crc32(chunk, crc)
                if target:
                    target.write(chunk)
    finally:
        if target:
            target.close()
    _require(total, entry.size, "candidate ZIP member actual size")
    _require(crc, entry.crc32, "candidate ZIP member actual CRC")
    _require(digest.hexdigest(), entry.sha256, "candidate ZIP member SHA-256")


def _verify_entries(zip_path: Path, output: Path, pin: CandidatePin) -> tuple[dict, dict]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise VerificationError("duplicate candidate ZIP member")
            if not all(_safe_member(info) for info in infos):
                raise VerificationError("unsafe candidate ZIP member")
            if set(names) != {entry.member for entry in pin.entries}:
                raise VerificationError("candidate ZIP member set differs from the frozen artifact")
            for entry in pin.entries:
                _verify_entry(archive, archive.getinfo(entry.member), entry, output)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise VerificationError("candidate ZIP member integrity or format failure") from None
    identity = _json_object((output / "CANDIDATE-IDENTITY.json").read_bytes(), "candidate identity")
    selection = _json_object((output / "venv-selection.json").read_bytes(), "native selection")
    _require(identity, json.loads(pin.identity_json), "candidate identity source/patch fields")
    _require(identity.get("published"), False, "candidate publication boundary")
    _require(identity.get("version_bumped"), False, "candidate version boundary")
    _require(selection, json.loads(pin.selection_json), "candidate native selection fields")
    return identity, selection


def fetch_candidate(output: Path, *, pin: CandidatePin = PIN, client=None) -> dict:
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise VerificationError("output directory must not already exist")
    client = client or GitHubClient(os.environ.get("GH_TOKEN", ""))
    base = f"repos/{pin.repository}/actions"
    run = client.metadata(f"{base}/runs/{pin.run_id}")
    artifact = client.metadata(f"{base}/artifacts/{pin.artifact_id}")
    validate_metadata(run, artifact, pin)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".candidate-fetch-", dir=output.parent) as scratch:
        stage = Path(scratch)
        archive_path = stage / "candidate.zip"
        with client.artifact_stream(f"{base}/artifacts/{pin.artifact_id}/zip") as stream:
            _save_archive(stream, archive_path, pin)
        publish = stage / "verified"
        publish.mkdir()
        identity, selection = _verify_entries(archive_path, publish, pin)
        by_output = {entry.output: entry for entry in pin.entries if entry.output}
        deb = by_output[identity["package"]]
        identity_entry = by_output["CANDIDATE-IDENTITY.json"]
        selection_entry = by_output["venv-selection.json"]
        receipt = {
            "schema_version": 1, "status": "verified",
            "repository": pin.repository, "run_id": pin.run_id, "head_sha": pin.head_sha,
            "artifact": {"id": pin.artifact_id, "name": pin.artifact_name,
                         "bytes": pin.archive_size, "sha256": pin.archive_sha256},
            "package": {"file": deb.output, "bytes": deb.size, "sha256": deb.sha256,
                        "zip_member": deb.member},
            "identity": {**identity, "file": identity_entry.output,
                         "sha256": identity_entry.sha256, "zip_member": identity_entry.member},
            "native_selection": {**selection, "file": selection_entry.output,
                                 "sha256": selection_entry.sha256,
                                 "zip_member": selection_entry.member},
        }
        (publish / "candidate-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n",
        )
        for path in publish.iterdir():
            path.chmod(0o644)
        publish.chmod(0o755)
        if output.exists() or output.is_symlink():
            raise VerificationError("output directory appeared during verification")
        publish.rename(output)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="new directory for the fully verified candidate and receipt")
    args = parser.parse_args(argv)
    try:
        receipt = fetch_candidate(args.out)
    except (VerificationError, OSError):
        # Exceptions from network/file layers may contain a signed URL: never echo them.
        exc = sys.exception()
        message = str(exc) if isinstance(exc, VerificationError) else "local staging failed"
        print(f"candidate fetch failed: {message}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "verified", "output": str(args.out.absolute()),
                      "package_sha256": receipt["package"]["sha256"],
                      "receipt": "candidate-receipt.json"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
