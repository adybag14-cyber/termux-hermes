from __future__ import annotations

from dataclasses import replace
from email.message import Message
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from urllib.error import HTTPError, URLError
from urllib.request import Request
import warnings
import zipfile
import zlib

import pytest

from scripts import fetch_compatibility_candidate as fetch


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_bytes(contents: dict[str, bytes], *, extra=None, symlink: str | None = None) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in contents.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            if name == symlink:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, data)
        if extra:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(*extra)
    return stream.getvalue()


def metadata(pin):
    repository = {"full_name": pin.repository, "id": pin.repository_id}
    run = {
        "id": pin.run_id, "head_sha": pin.head_sha,
        "status": "completed", "conclusion": "success",
        "path": ".github/workflows/next-stable-candidate.yml",
        "repository": dict(repository), "head_repository": dict(repository),
    }
    artifact = {
        "id": pin.artifact_id, "name": pin.artifact_name,
        "size_in_bytes": pin.archive_size, "digest": "sha256:" + pin.archive_sha256,
        "expired": False, "expires_at": "2099-01-01T00:00:00Z",
        "workflow_run": {
            "id": pin.run_id, "head_sha": pin.head_sha,
            "repository_id": pin.repository_id, "head_repository_id": pin.repository_id,
        },
    }
    return run, artifact


class FixtureClient:
    def __init__(self, pin, archive: bytes, output: Path):
        self.pin = pin
        self.archive = archive
        self.output = output
        self.run, self.artifact = metadata(pin)
        self.download_started = False

    def metadata(self, endpoint):
        assert not self.output.exists()
        if endpoint.endswith("/runs/" + str(self.pin.run_id)):
            return self.run
        assert endpoint.endswith("/artifacts/" + str(self.pin.artifact_id))
        return self.artifact

    def artifact_stream(self, endpoint):
        assert not self.output.exists()
        assert endpoint.endswith("/artifacts/" + str(self.pin.artifact_id) + "/zip")
        self.download_started = True
        return io.BytesIO(self.archive)


@pytest.fixture
def candidate(tmp_path):
    contents = {
        entry.member: ("bounded fixture: " + entry.member).encode()
        for entry in fetch.PIN.entries
    }
    deb = next(entry for entry in fetch.PIN.entries if entry.output == fetch.IDENTITY["package"])
    contents[deb.member] = b"!<arch>\nbounded synthetic package fixture\n"
    identity = dict(fetch.IDENTITY, package_sha256=sha(contents[deb.member]))
    identity_entry = next(e for e in fetch.PIN.entries if e.output == "CANDIDATE-IDENTITY.json")
    selection_entry = next(e for e in fetch.PIN.entries if e.output == "venv-selection.json")
    contents[identity_entry.member] = (json.dumps(identity) + "\n").encode()
    contents[selection_entry.member] = (json.dumps(fetch.SELECTION) + "\n").encode()
    entries = tuple(
        replace(entry, size=len(contents[entry.member]), sha256=sha(contents[entry.member]),
                crc32=zlib.crc32(contents[entry.member]))
        for entry in fetch.PIN.entries
    )
    archive = zip_bytes(contents)
    pin = replace(fetch.PIN, entries=entries, archive_size=len(archive),
                  archive_sha256=sha(archive), identity_json=json.dumps(identity))
    output = tmp_path / "verified"
    return pin, contents, FixtureClient(pin, archive, output), output


def rebind_archive(pin, client, archive):
    pin = replace(pin, archive_size=len(archive), archive_sha256=sha(archive))
    client.pin = pin
    client.archive = archive
    client.run, client.artifact = metadata(pin)
    return pin


def assert_unpublished(output):
    assert not output.exists()
    assert not list(output.parent.glob(".candidate-fetch-*"))


def test_exact_archive_is_verified_before_only_named_outputs_appear(candidate):
    pin, contents, client, output = candidate
    receipt = fetch.fetch_candidate(output, pin=pin, client=client)
    assert set(p.name for p in output.iterdir()) == {
        fetch.IDENTITY["package"], "CANDIDATE-IDENTITY.json",
        "venv-selection.json", "candidate-receipt.json",
    }
    for entry in pin.entries:
        if entry.output:
            assert (output / entry.output).read_bytes() == contents[entry.member]
    assert receipt == json.loads((output / "candidate-receipt.json").read_text())
    assert receipt["status"] == "verified"
    assert receipt["artifact"]["sha256"] == pin.archive_sha256
    assert receipt["package"]["sha256"] == sha(
        (output / fetch.IDENTITY["package"]).read_bytes()
    )
    assert receipt["native_selection"]["bundled_wheels"] == fetch.SELECTION["bundled_wheels"]
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o755
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o644 for p in output.iterdir())
    assert not list(output.parent.glob(".candidate-fetch-*"))


@pytest.mark.parametrize("section,key,value", [
    ("run", "id", True),
    ("run", "head_sha", "0" * 40),
    ("run", "conclusion", "failure"),
    ("run", "status", "in_progress"),
    ("run", "path", ".github/workflows/ci.yml"),
    ("run", "head_repository", {"full_name": "other/repo", "id": 1}),
    ("artifact", "id", 12107225802),
    ("artifact", "name", "unrelated artifact"),
    ("artifact", "digest", None),
    ("artifact", "size_in_bytes", 0),
    ("artifact", "expired", True),
    ("artifact", "expires_at", "2000-01-01T00:00:00Z"),
    ("artifact", "expires_at", "2099-01-01T00:00:00"),
    ("artifact", "workflow_run", {"id": 1}),
])
def test_wrong_or_expired_metadata_fails_before_download(candidate, section, key, value):
    pin, _, client, output = candidate
    getattr(client, section)[key] = value
    with pytest.raises(fetch.VerificationError):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert not client.download_started
    assert_unpublished(output)


@pytest.mark.parametrize("mode", ["changed", "truncated", "oversized"])
def test_streamed_zip_bytes_must_match_the_frozen_size_and_sha(candidate, mode):
    pin, _, client, output = candidate
    data = client.archive
    client.archive = (
        data[:-1] + bytes([data[-1] ^ 1]) if mode == "changed"
        else data[:-1] if mode == "truncated"
        else data + b"unexpected extra bytes"
    )
    with pytest.raises(fetch.VerificationError, match="ZIP"):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert_unpublished(output)


@pytest.mark.parametrize("mode", ["traversal", "absolute", "backslash", "extra", "duplicate", "symlink"])
def test_unsafe_or_unexpected_zip_entries_are_never_extracted(candidate, mode):
    pin, contents, client, output = candidate
    first = next(iter(contents))
    extras = {
        "traversal": ("../escaped", b"unsafe"),
        "absolute": ("/escaped", b"unsafe"),
        "backslash": ("..\\escaped", b"unsafe"),
        "extra": ("unlisted-file.txt", b"not in the pinned artifact"),
        "duplicate": (first, contents[first]),
    }
    archive = zip_bytes(contents, extra=extras.get(mode),
                        symlink=first if mode == "symlink" else None)
    pin = rebind_archive(pin, client, archive)
    with pytest.raises(fetch.VerificationError, match="ZIP member"):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert_unpublished(output)
    assert not (output.parent / "escaped").exists()


def test_corrupt_member_crc_is_rejected_even_with_a_matching_archive_digest(candidate):
    pin, _, client, output = candidate
    data = bytearray(client.archive)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.infolist()[0]
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    data[offset] ^= 1
    pin = rebind_archive(pin, client, bytes(data))
    with pytest.raises(fetch.VerificationError, match="integrity|CRC|SHA-256"):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert_unpublished(output)


@pytest.mark.parametrize("changed", ["source", "patch", "published", "selection"])
def test_rewritten_claims_fail_even_if_the_zip_and_entry_checksums_are_rebound(candidate, changed):
    pin, contents, client, output = candidate
    output_name = "venv-selection.json" if changed == "selection" else "CANDIDATE-IDENTITY.json"
    entry = next(e for e in pin.entries if e.output == output_name)
    value = json.loads(contents[entry.member])
    if changed == "source":
        value["upstream_commit"] = "0" * 40
    elif changed == "patch":
        value["patches"]["patches/next-stable/compatibility.patch"] = "0" * 64
    elif changed == "published":
        value["published"] = 0  # Equality with False must not bypass the boolean boundary.
    else:
        value["extras"] = ["termux"]
    contents[entry.member] = (json.dumps(value) + "\n").encode()
    data = contents[entry.member]
    pin = replace(pin, entries=tuple(
        replace(e, size=len(data), crc32=zlib.crc32(data), sha256=sha(data))
        if e.member == entry.member else e for e in pin.entries
    ))
    pin = rebind_archive(pin, client, zip_bytes(contents))
    with pytest.raises(fetch.VerificationError, match="identity|publication|selection"):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert_unpublished(output)


def test_existing_output_is_not_overwritten(candidate):
    pin, _, client, output = candidate
    output.mkdir()
    sentinel = output / "owned-file"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(fetch.VerificationError, match="already exist"):
        fetch.fetch_candidate(output, pin=pin, client=client)
    assert sentinel.read_bytes() == b"preserve"
    assert not client.download_started


class Response(io.BytesIO):
    status = 200


class RedirectOpener:
    def __init__(self, destination):
        self.destination = destination
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append(request)
        headers = Message()
        headers["Location"] = self.destination
        raise HTTPError(request.full_url, 302, "Found", headers, None)


class DownloadOpener:
    def __init__(self, failure=None):
        self.requests = []
        self.failure = failure

    def open(self, request, *, timeout):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return Response(b"archive")


def test_authenticated_redirect_and_anonymous_download_never_share_credentials():
    secret = "test-token-do-not-forward"
    client = fetch.GitHubClient(secret)
    signed = "https://fixture.blob.core.windows.net/artifact?sig=private-signed-value"
    api = RedirectOpener(signed)
    download = DownloadOpener()
    client._api_opener, client._download_opener = api, download
    with client.artifact_stream("repos/frozen/repo/actions/artifacts/1/zip") as stream:
        assert stream.read() == b"archive"
    assert api.requests[0].full_url.startswith("https://api.github.com/")
    assert api.requests[0].get_header("Authorization") == "Bearer " + secret
    request = download.requests[0]
    assert request.full_url == signed
    assert request.get_header("Authorization") is None
    assert request.get_header("Cookie") is None
    assert request.get_header("X-github-api-version") is None
    assert fetch._NoRedirect().redirect_request(
        Request("https://api.github.com", headers={"Authorization": secret}),
        None, 302, "Found", {}, signed,
    ) is None


@pytest.mark.parametrize("destination", [
    "http://fixture.invalid/artifact",
    "https://user:password@fixture.invalid/artifact",
    "https://fixture.invalid:444/artifact",
    "https://fixture.invalid/artifact\nInjected: header",
])
def test_bad_redirect_destinations_are_rejected_before_anonymous_fetch(destination):
    client = fetch.GitHubClient("test-token")
    client._api_opener = RedirectOpener(destination)
    client._download_opener = download = DownloadOpener()
    with pytest.raises(fetch.VerificationError, match="invalid HTTPS"):
        client.artifact_stream("repos/frozen/repo/actions/artifacts/1/zip")
    assert not download.requests


def test_download_errors_do_not_disclose_credentials_or_the_signed_url():
    secret = "test-token-sensitive"
    signed = "https://fixture.invalid/artifact?sig=never-print-this"
    client = fetch.GitHubClient(secret)
    client._api_opener = RedirectOpener(signed)
    client._download_opener = DownloadOpener(URLError(secret + " " + signed))
    with pytest.raises(fetch.VerificationError) as error:
        client.artifact_stream("repos/frozen/repo/actions/artifacts/1/zip")
    assert secret not in str(error.value)
    assert signed not in str(error.value)
    assert "never-print-this" not in str(error.value)


def test_frozen_pins_match_the_checked_in_success_evidence():
    root = Path(__file__).resolve().parents[1] / "audit/candidate-lifecycle-e271e92-20261017"
    bindings = json.loads((root / "bindings.json").read_text())
    artifact = next(a for a in bindings["artifacts"] if a["id"] == fetch.PIN.artifact_id)
    assert bindings["run"]["id"] == fetch.PIN.run_id
    assert bindings["checkout"]["actual_tested_commit"] == fetch.PIN.head_sha
    assert artifact["digest"] == "sha256:" + fetch.PIN.archive_sha256
    assert artifact["size_in_bytes"] == fetch.PIN.archive_size
    members = {m["path"]: m for m in artifact["members"]}
    assert set(members) == {entry.member for entry in fetch.PIN.entries}
    for entry in fetch.PIN.entries:
        saved = members[entry.member]
        assert (entry.size, entry.sha256, entry.crc32) == (
            saved["bytes"], saved["sha256"], int(saved["crc32"], 16),
        )
    assert json.loads(fetch.PIN.identity_json) == json.loads(
        (root / "CANDIDATE-IDENTITY.json").read_text()
    )
    assert json.loads(fetch.PIN.selection_json) == json.loads(
        (root / "venv-selection.json").read_text()
    )
