#!/usr/bin/env python3
"""Prepare the frozen, isolated audio-validation payload; never install a package."""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib

PREFIX = "/data/data/com.termux/files/usr"
PAYLOAD_PREFIX = "data/data/com.termux/files/usr/lib/hermes-agent/"
GENERATED_ROOTS = ("venv", "pm-runtime", "state", "bin")
GENERATED_FILES = ("staging/bundle-manifest.json", "staging/assembly-receipt.json",
                   "staging/environment-manifest.json", "staging/native-validation.json",
                   "staging/audio-diagnostic.json", "tools/facts.json")
CHUNK = 1024 * 1024


class StagingError(ValueError):
    """A failed, bounded verification; no successful assembly is claimed."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise StagingError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def read_json(path: Path) -> dict:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, "duplicate JSON key")
            out[key] = value
        return out
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StagingError("unreadable JSON document") from exc
    require(isinstance(value, dict), "JSON document must be an object")
    return value


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(name: str) -> PurePosixPath:
    require(isinstance(name, str) and bool(name), "empty relative path")
    require(not any(char in name for char in ("\0", "\\", ":", "\n", "\r")),
            "unsafe relative path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in name.split("/")),
            "unsafe relative path")
    return path


validate_member_path = safe_relative_path


def safe_link_target(name: str, target: str) -> str:
    safe_relative_path(name)
    require(isinstance(target, str) and target and not any(c in target for c in ("\0", "\\", ":", "\n", "\r")),
            "unsafe symlink target")
    require(not PurePosixPath(target).is_absolute(), "absolute symlink target")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    require(resolved not in ("", ".", "..") and not resolved.startswith("../"),
            "symlink target escapes payload")
    safe_relative_path(resolved)
    return resolved


def validate_destination(destination: Path, *, forbidden_roots: tuple[Path, ...] = ()) -> Path:
    destination = Path(destination)
    require(destination.is_absolute(), "destination must be absolute")
    require(destination != Path(destination.anchor), "filesystem root is not a destination")
    require(not destination.exists() and not destination.is_symlink(), "destination already exists")
    require(destination.parent.is_dir(), "destination parent must exist")
    require(destination.resolve() == destination, "destination has symlink or noncanonical parents")
    for forbidden in forbidden_roots:
        forbidden = Path(forbidden).resolve()
        require(not destination.is_relative_to(forbidden) and not forbidden.is_relative_to(destination),
                "destination overlaps protected input")
    return destination


def verify_file(path: Path, expected: dict, label: str = "file") -> None:
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f"{label}: regular file required")
    size = expected.get("size", expected.get("bytes"))
    require(type(size) is int and size >= 0, f"{label}: invalid frozen size")
    require(path.stat().st_size == size, f"{label}: size mismatch")
    require(file_digest(path) == expected.get("sha256"), f"{label}: SHA-256 mismatch")


def select_audio_wheels(candidate_rows: list[dict], audio_rows: list[dict], policy: dict) -> list[dict]:
    """Keep every candidate wheel byte and explicitly admit only the frozen additions."""
    def index(rows):
        by_name, filenames = {}, set()
        for original in rows:
            row = copy.deepcopy(original)
            name, filename = row.get("name"), row.get("file")
            require(isinstance(name, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name),
                    "noncanonical wheel distribution name")
            safe_relative_path(filename)
            require(filename.endswith(".whl"), "wheel filename required")
            require(name not in by_name and filename not in filenames, "duplicate wheel identity")
            require(isinstance(row.get("version"), str) and row["version"], "wheel version missing")
            require(type(row.get("size")) is int and row["size"] > 0, "wheel size missing")
            require(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "wheel digest missing")
            by_name[name] = row
            filenames.add(filename)
        return by_name
    candidate, audio = index(candidate_rows), index(audio_rows)
    additions = policy.get("additions")
    require(isinstance(additions, list) and len(additions) == len(set(additions)),
            "invalid audio additions policy")
    require(set(additions).isdisjoint(candidate), "audio additions replace a candidate distribution")
    selected = copy.deepcopy(candidate)
    used_collisions = set()
    for name, row in audio.items():
        if name in candidate:
            original = candidate[name]
            require((original["file"], original["version"]) == (row["file"], row["version"]),
                    "audio changes a baseline wheel identity")
            if (original["sha256"], original["size"]) != (row["sha256"], row["size"]):
                pin = policy.get("candidate_wins", {}).get(name)
                require(isinstance(pin, dict) and
                        pin.get("candidate_sha256") == original["sha256"] and
                        pin.get("audio_sha256") == row["sha256"],
                        "unreviewed same-name wheel collision")
                used_collisions.add(name)
        else:
            require(name in additions, "undeclared audio wheel addition")
            selected[name] = row
    require(set(additions).issubset(selected) and set(additions).issubset(audio),
            "required audio additions are missing")
    require(used_collisions == set(policy.get("candidate_wins", {})),
            "frozen candidate collision policy was not exercised")
    return [selected[name] for name in sorted(selected)]


def verify_manifest_tree(root: Path, manifest: dict, *, allow_generated: bool = False) -> dict:
    root = Path(root)
    require(root.is_absolute() and root.is_dir() and not root.is_symlink() and root.resolve() == root,
            "payload root must be a real absolute directory")
    require(manifest.get("schema_version") == 1 and isinstance(manifest.get("entries"), list),
            "invalid payload manifest")
    preserved_dangling = {row["path"]: row["target"] for row in
                          manifest.get("lock", {}).get("preserved_dangling_symlinks", [])}
    expected, counts = {}, {"files": 0, "symlinks": 0, "directories": 0, "bytes": 0}
    for row in manifest["entries"]:
        require(isinstance(row, dict), "invalid payload entry")
        name = row.get("path")
        safe_relative_path(name)
        require(name not in expected, "duplicate payload path")
        expected[name] = row
        path = root.joinpath(*PurePosixPath(name).parts)
        require(path.parent.resolve().is_relative_to(root), "payload parent escapes root")
        require(path.exists() or path.is_symlink(), "payload member missing: " + name)
        kind = row.get("kind")
        if kind == "file":
            verify_file(path, row, name)
            counts["files"] += 1
            counts["bytes"] += row["size"]
        elif kind == "symlink":
            require(path.is_symlink() and os.readlink(path) == row.get("target"), "symlink mismatch: " + name)
            safe_link_target(name, row["target"])
            require(path.resolve().is_relative_to(root), "symlink resolves outside payload")
            require(path.exists() or preserved_dangling.get(name) == row["target"],
                    "unreviewed dangling payload symlink")
            counts["symlinks"] += 1
        elif kind == "directory":
            require(path.is_dir() and not path.is_symlink(), "directory mismatch: " + name)
            counts["directories"] += 1
        else:
            raise StagingError("unknown payload entry kind")
        if kind != "symlink" and "mode" in row and os.name != "nt":
            require(stat.S_IMODE(path.stat().st_mode) == row["mode"], "payload mode mismatch: " + name)
    actual = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            actual.add((Path(parent) / name).relative_to(root).as_posix())
    def generated(name):
        return (name in GENERATED_FILES or
                any(name == prefix or name.startswith(prefix + "/") for prefix in GENERATED_ROOTS))
    unexpected = actual - set(expected)
    if allow_generated:
        require(all(generated(name) for name in unexpected), "unexpected payload member")
        for name in unexpected:
            path = root.joinpath(*PurePosixPath(name).parts)
            require(path.parent.resolve().is_relative_to(root), "generated parent escapes payload")
            if path.is_symlink():
                safe_link_target(name, os.readlink(path))
                require(path.resolve().is_relative_to(root), "generated symlink escapes payload")
            if name in GENERATED_FILES:
                require(path.is_file() and not path.is_symlink(), "generated receipt must be a regular file")
    else:
        require(not unexpected, "unexpected payload member")
    return counts


def verify_archive(path: Path, pin: dict) -> None:
    verify_file(path, pin["archive"], "input archive")
    rows = pin["members"]
    expected = {row["name"]: row for row in rows}
    require(len(expected) == len(rows), "duplicate frozen archive member")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            require(len(infos) == len(expected) and {i.filename for i in infos} == set(expected),
                    "archive member set differs from frozen input")
            for info in infos:
                safe_relative_path(info.filename)
                require(not info.is_dir() and not info.flag_bits & 1 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "unsupported archive entry")
                require(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG),
                        "nonregular archive entry")
                row = expected[info.filename]
                require(info.file_size == row.get("size", row.get("bytes")), "archive member size mismatch")
                crc = row["crc32"]
                require(info.CRC == (int(crc, 16) if isinstance(crc, str) else crc), "archive member CRC mismatch")
                h = hashlib.sha256()
                with archive.open(info) as stream:
                    while block := stream.read(CHUNK):
                        h.update(block)
                require(h.hexdigest() == row["sha256"], "archive member SHA-256 mismatch")
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise StagingError("invalid input ZIP") from exc


def deb_data(path: Path) -> bytes:
    with path.open("rb") as source:
        require(source.read(8) == b"!<arch>\n", "invalid Debian ar archive")
        names, result = set(), None
        while header := source.read(60):
            require(len(header) == 60 and header[58:] == b"\x60\n", "invalid ar header")
            name = header[:16].decode("ascii").strip().rstrip("/")
            require(name not in names, "duplicate ar member")
            names.add(name)
            size = int(header[48:58])
            require(0 <= size <= path.stat().st_size, "invalid ar member size")
            data = source.read(size)
            require(len(data) == size, "truncated ar member")
            if size % 2:
                require(len(source.read(1)) == 1, "missing ar padding")
            if name == "debian-binary":
                require(data == b"2.0\n", "unsupported Debian archive version")
            elif name.startswith("data.tar"):
                require(result is None, "duplicate Debian data archive")
                result = data
    require(result is not None, "Debian payload missing")
    return result


def verified_openssl_additions(archive_path: Path, pin: dict) -> dict[str, bytes]:
    """Bind the missing provider/config to the candidate's exact OpenSSL libraries."""
    verify_file(archive_path, pin["archive"], "official OpenSSL archive")
    require(set(pin["libraries"]) == {"libcrypto", "libssl"}, "OpenSSL library binding changed")
    rows = [pin["provider"], pin["config"], *pin["libraries"].values()]
    expected = {row["member"]: row for row in rows}
    require(len(expected) == 4 and len({row["file"] for row in rows}) == 4,
            "duplicate OpenSSL member or destination")
    for row in rows:
        safe_relative_path(row["member"].removeprefix("./"))
        safe_relative_path(row["file"])
    seen, additions = set(), {}
    with tarfile.open(fileobj=io.BytesIO(deb_data(archive_path)), mode="r:*") as archive:
        for member in archive:
            if member.name not in expected:
                continue
            row = expected[member.name]
            require(member.name not in seen and member.isfile(), "OpenSSL member missing or ambiguous")
            require(member.size == row["size"], "OpenSSL member size differs")
            data = archive.extractfile(member).read()
            require((len(data), digest_bytes(data)) == (row["size"], row["sha256"]),
                    "OpenSSL member bytes differ")
            seen.add(member.name)
            if row in (pin["provider"], pin["config"]):
                additions[row["file"]] = data
    require(seen == set(expected) and len(additions) == 2, "OpenSSL frozen member set incomplete")
    return additions


def apply_pinned_patch(original: bytes, patch: bytes, relative: str) -> bytes:
    """Apply only the exact production-file hunk; test hunks remain review evidence."""
    lines = patch.decode("utf-8").splitlines(keepends=True)
    original_lines = original.decode("utf-8").splitlines(keepends=True)
    begin = next((i for i, line in enumerate(lines)
                  if line.rstrip("\r\n") == f"diff --git a/{relative} b/{relative}"), None)
    require(begin is not None, "production path absent from audio patch")
    end = next((i for i in range(begin + 1, len(lines)) if lines[i].startswith("diff --git ")), len(lines))
    segment, result, cursor, i = lines[begin:end], [], 0, 0
    while i < len(segment):
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", segment[i])
        if not match:
            i += 1
            continue
        start, old_len, _, new_len = (int(match.group(1)), int(match.group(2) or 1),
                                     int(match.group(3)), int(match.group(4) or 1))
        require(start - 1 >= cursor, "overlapping audio patch hunks")
        result.extend(original_lines[cursor:start - 1])
        cursor = start - 1
        consumed = produced = 0
        i += 1
        while i < len(segment) and not segment[i].startswith("@@ "):
            line = segment[i]
            if not line or line[0] not in " +-":
                break
            marker, text = line[0], line[1:]
            if marker in " -":
                require(cursor < len(original_lines) and original_lines[cursor] == text,
                        "audio patch source context mismatch")
                cursor += 1
                consumed += 1
            if marker in " +":
                result.append(text)
                produced += 1
            i += 1
        require((consumed, produced) == (old_len, new_len), "audio patch hunk length mismatch")
    result.extend(original_lines[cursor:])
    return "".join(result).encode("utf-8")



def validate_entry_relationships(entries: dict[str, dict], allowed_dangling: dict[str, str] | None = None) -> None:
    """Reject archive traversal through symlink parents before a tar can be unpacked."""
    allowed_dangling = allowed_dangling or {}
    used_allowances = set()
    for name, row in entries.items():
        parts = PurePosixPath(name).parts
        for stop in range(1, len(parts)):
            parent = "/".join(parts[:stop])
            require(parent in entries and entries[parent]["kind"] == "directory",
                    "archive member has missing or symlink parent")
        if row["kind"] != "symlink":
            continue
        current = safe_link_target(name, row["target"])
        visited = set()
        while True:
            require(current not in visited, "cyclic archive symlink")
            visited.add(current)
            bits = PurePosixPath(current).parts
            redirect = None
            for stop in range(1, len(bits) + 1):
                prefix = "/".join(bits[:stop])
                if entries.get(prefix, {}).get("kind") == "symlink":
                    redirect = (prefix, stop)
                    break
            if redirect is None:
                if current not in entries:
                    require(allowed_dangling.get(name) == row["target"], "symlink target was not retained")
                    used_allowances.add(name)
                break
            link, stop = redirect
            current = posixpath.normpath(posixpath.join(safe_link_target(link, entries[link]["target"]), *bits[stop:]))
            safe_relative_path(current)
    require(used_allowances == set(allowed_dangling), "unused dangling-link preservation policy")


def _load_lock() -> dict:
    return read_json(Path(__file__).with_name("audio_device_bundle_lock.json"))


def _tar_entry(name: str, data: bytes | None = None, *, target: str | None = None,
               mode: int = 0o644) -> tuple[tarfile.TarInfo, dict]:
    safe_relative_path(name)
    entry = tarfile.TarInfo(name)
    entry.uid = entry.gid = entry.mtime = 0
    entry.uname = entry.gname = ""
    entry.mode = mode & 0o777
    row = {"path": name, "mode": entry.mode}
    if target is not None:
        safe_link_target(name, target)
        entry.type, entry.linkname = tarfile.SYMTYPE, target
        row.update(kind="symlink", target=target)
    elif data is None:
        entry.type = tarfile.DIRTYPE
        row["kind"] = "directory"
    else:
        entry.size = len(data)
        row.update(kind="file", size=len(data), sha256=digest_bytes(data))
    return entry, row


def _bootstrap(manifest_sha: str, archive_sha: str, python_relative: str) -> bytes:
    # Both inputs are fixed by the transfer receipt. No arbitrary archive is accepted.
    script = r'''#!/data/data/com.termux/files/usr/bin/sh
set -eu
test "$#" = 1 || { echo 'usage: prepare.sh NEW_ABSOLUTE_DESTINATION' >&2; exit 2; }
case "${_PYTHON_HOST_PLATFORM+x}${_PYTHON_SYSCONFIGDATA_NAME+x}${_PYTHON_SYSCONFIGDATA_PATH+x}" in
  '') ;; *) echo 'Refusing inherited Python platform override' >&2; exit 2 ;;
esac
bundle="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
destination="$1"
case "$destination" in /*) ;; *) echo 'Destination must be absolute' >&2; exit 2 ;; esac
case "$destination" in /|*/../*|*/./*|*/..|*/.) echo 'Noncanonical destination' >&2; exit 2 ;; esac
case "$destination" in "$bundle"|"$bundle"/*|/data/data/com.termux/files/usr/lib/hermes-agent|/data/data/com.termux/files/usr/lib/hermes-agent/*)
  echo 'Destination overlaps a protected input or installed Hermes' >&2; exit 2 ;;
esac
test ! -e "$destination" && test ! -L "$destination" || { echo 'Destination already exists' >&2; exit 2; }
parent="$(dirname -- "$destination")"
test -d "$parent" && test "$(realpath -- "$parent")" = "$parent" ||
  { echo 'Destination parent must exist without symlinks' >&2; exit 2; }
cd "$bundle"
printf '%s  %s\n' '__MANIFEST_SHA__' manifest.json '__ARCHIVE_SHA__' payload.tar.gz | sha256sum -c -
umask 077
mkdir -- "$destination"
# SHA-pinned tar member names and links were exhaustively checked by the packer.
tar --extract --gzip --file "$bundle/payload.tar.gz" --directory "$destination" --no-same-owner --same-permissions
cp "$bundle/manifest.json" "$destination/staging/bundle-manifest.json"
chmod 700 "$destination"
PREFIX=/data/data/com.termux/files/usr
export PREFIX
unset PYTHONPATH PYTHONHOME PYTHONUSERBASE VIRTUAL_ENV LD_PRELOAD OPENSSL_ENGINES CRYPTOGRAPHY_OPENSSL_NO_LEGACY
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export OPENSSL_MODULES="$destination/runtime-libs/lib/ossl-modules"
export OPENSSL_CONF="$destination/runtime-libs/etc/ssl/openssl.cnf"
export OPENSSL_CONF_INCLUDE="$destination/runtime-libs/etc/ssl"
export LD_LIBRARY_PATH="$destination/tools/python$PREFIX/lib:$destination/tools/node$PREFIX/lib:$destination/tools/ffmpeg$PREFIX/lib:$destination/runtime-libs/lib"
exec "$destination/__PYTHON__" -I -B "$destination/staging/prepare_audio_device_environment.py" assemble --root "$destination"
'''
    return script.replace("__MANIFEST_SHA__", manifest_sha).replace("__ARCHIVE_SHA__", archive_sha).replace(
        "__PYTHON__", python_relative).encode("utf-8")


def build_bundle(candidate_archive: Path, audio_archive: Path, opensles_deb: Path,
                 out: Path, *, openssl_deb: Path, lock: dict | None = None) -> dict:
    lock = lock or _load_lock()
    out = validate_destination(Path(out).absolute(),
                               forbidden_roots=tuple(p.resolve() for p in (candidate_archive, audio_archive, opensles_deb, openssl_deb)))
    verify_archive(candidate_archive, lock["candidate"])
    verify_archive(audio_archive, lock["audio"])
    verify_file(opensles_deb, lock["opensles"]["archive"], "official OpenSL ES package")
    packaging = Path(__file__).resolve().parent.parent
    patch = packaging / lock["audio_patch"]["file"]
    verify_file(patch, lock["audio_patch"], "audio readiness patch")
    patch_bytes = patch.read_bytes()
    helper = Path(__file__).with_name("prepare_audio_device_environment.py")
    require(helper.is_file(), "destination preparation helper missing")
    additions = verified_openssl_additions(openssl_deb, lock["openssl"])
    with zipfile.ZipFile(audio_archive) as archive:
        for name in lock["wheel_policy"]["additions"]:
            row = next(row for row in lock["audio"]["wheels"] if row["name"] == name)
            additions[row["file"]] = archive.read(row["file"])
        for name in ("libportaudio.so", "libportaudio.so.2", "libportaudio.so.2.0.0"):
            data = archive.read("added-runtime-libs/" + name)
            require((len(data), digest_bytes(data)) == (lock["audio"]["portaudio"]["size"], lock["audio"]["portaudio"]["sha256"]),
                    "PortAudio native bytes differ")
            additions["runtime-libs/lib/" + name] = data
    with tarfile.open(fileobj=io.BytesIO(deb_data(opensles_deb)), mode="r:*") as archive:
        matches = [m for m in archive if m.name == lock["opensles"]["member"]]
        require(len(matches) == 1 and matches[0].isfile(), "official OpenSL ES member missing or ambiguous")
        data = archive.extractfile(matches[0]).read()
        require((len(data), digest_bytes(data)) == (lock["opensles"]["size"], lock["opensles"]["sha256"]),
                "official OpenSL ES bytes differ")
        additions[lock["opensles"]["file"]] = data
    source_changes = {row["path"]: row for row in lock["source_changes"]}
    candidate_rows, entries, originals, baseline_wheels = None, {}, {}, {}
    with tempfile.TemporaryDirectory(prefix=".audio-bundle-", dir=out.parent) as temporary:
        stage = Path(temporary)
        package = stage / "candidate.deb"
        with zipfile.ZipFile(candidate_archive) as archive:
            name = next(row["name"] for row in lock["candidate"]["members"] if row["name"].endswith(".deb"))
            with archive.open(name) as source, package.open("xb") as target:
                shutil.copyfileobj(source, target, CHUNK)
        verify_file(package, lock["candidate"]["package"], "candidate package")
        prepared = stage / "ready"
        prepared.mkdir()
        archive_path = prepared / "payload.tar.gz"
        with archive_path.open("xb") as raw_output, gzip.GzipFile(
                filename="", fileobj=raw_output, mode="wb", mtime=0, compresslevel=3) as compressed, \
                tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as target:
            def add(name, data=None, *, link=None, mode=0o644):
                require(name not in entries, "duplicate prepared payload member: " + name)
                info, row = _tar_entry(name, data, target=link, mode=mode)
                entries[name] = row
                target.addfile(info, io.BytesIO(data) if data is not None else None)
            with tarfile.open(fileobj=io.BytesIO(deb_data(package)), mode="r:*") as source:
                for member in source:
                    original = member.name.removeprefix("./")
                    if not original.startswith(PAYLOAD_PREFIX):
                        continue
                    name = original[len(PAYLOAD_PREFIX):].rstrip("/")
                    if not name:
                        continue
                    safe_relative_path(name)
                    top = name.split("/")[0]
                    if top not in ("app", "tools", "runtime-libs", "wheelhouse",
                                   "bundled-wheels.json", "enabled-features.json", "manifest.json", "native-wheels.json"):
                        continue
                    if name == "tools/facts.json":
                        originals["staging/candidate-tools-facts.json"] = source.extractfile(member).read()
                        continue
                    if member.isdir():
                        add(name, mode=member.mode)
                    elif member.issym():
                        add(name, link=member.linkname, mode=member.mode)
                    elif member.isfile() or member.islnk():
                        data = source.extractfile(member).read()
                        if name in source_changes:
                            pin = source_changes[name]
                            require((len(data), digest_bytes(data)) == (pin["before"]["size"], pin["before"]["sha256"]),
                                    "candidate trimmed source differs from audio baseline")
                            data = apply_pinned_patch(data, patch_bytes, name.removeprefix("app/"))
                            require((len(data), digest_bytes(data)) == (pin["after"]["size"], pin["after"]["sha256"]),
                                    "patched production source differs from reviewed output")
                        if name == "bundled-wheels.json":
                            require((len(data), digest_bytes(data)) == (lock["candidate"]["catalog"]["size"], lock["candidate"]["catalog"]["sha256"]),
                                    "candidate wheel catalog changed")
                            candidate_rows = json.loads(data)["wheels"]
                        if name == "enabled-features.json":
                            require((len(data), digest_bytes(data)) == (lock["candidate"]["enabled_features"]["size"], lock["candidate"]["enabled_features"]["sha256"]),
                                    "candidate default feature selection changed")
                        if name.startswith("wheelhouse/") and name.endswith(".whl"):
                            baseline_wheels[name] = (len(data), digest_bytes(data))
                        add(name, data, mode=member.mode)
                    else:
                        raise StagingError("special file in selected candidate payload")
            require(candidate_rows is not None, "candidate catalog missing")
            require(set(baseline_wheels) == {row["file"] for row in candidate_rows}, "candidate wheel catalog/file set mismatch")
            for row in candidate_rows:
                require(baseline_wheels[row["file"]] == (row["size"], row["sha256"]), "candidate catalog wheel digest mismatch")
            for pin in lock["openssl"]["libraries"].values():
                for name in (pin["file"], pin["file"].removesuffix(".3")):
                    row = entries.get(name, {})
                    require(row.get("kind") == "file" and
                            (row.get("size"), row.get("sha256")) == (pin["size"], pin["sha256"]),
                            "candidate OpenSSL libraries differ from the pinned provider source")
            selected = select_audio_wheels(candidate_rows, lock["audio"]["wheels"], lock["wheel_policy"])
            require(len(candidate_rows) == 100 and len(selected) == 102, "frozen wheel count changed")
            add("staging", mode=0o755)
            for row in (lock["openssl"]["provider"], lock["openssl"]["config"]):
                for parent in reversed(PurePosixPath(row["file"]).parents):
                    name = parent.as_posix()
                    if name == ".":
                        continue
                    if name in entries:
                        require(entries[name]["kind"] == "directory", "OpenSSL parent is not a directory")
                    else:
                        add(name, mode=0o755)
            for name, data in sorted(additions.items()):
                require(name not in entries, "audio addition collides with candidate payload")
                add(name, data)
            snapshots = {
                "staging/prepare_audio_device_bundle.py": Path(__file__).read_bytes(),
                "staging/prepare_audio_device_environment.py": helper.read_bytes(),
                "staging/audio_device_bundle_lock.json": canonical_json(lock),
                "staging/audio-readiness.patch": patch_bytes,
                **originals,
            }
            for name, data in sorted(snapshots.items()):
                add(name, data)
        require(set(source_changes).issubset(entries), "patched production files are missing")
        validate_entry_relationships(entries, {row["path"]: row["target"] for row in lock.get("preserved_dangling_symlinks", [])})
        for name, pin in lock["source_locks"].items():
            require(name in entries and (entries[name]["size"], entries[name]["sha256"]) == (pin["size"], pin["sha256"]),
                    "candidate frozen source lock changed")
        manifest = {
            "schema_version": 1,
            "purpose": lock["purpose"],
            "lock": lock,
            "candidate": lock["candidate"]["identity"],
            "source_changes": lock["source_changes"],
            "wheels": selected,
            "entries": [entries[name] for name in sorted(entries)],
            "generated_roots": list(GENERATED_ROOTS),
            "archive": {"file": "payload.tar.gz", "size": archive_path.stat().st_size, "sha256": file_digest(archive_path)},
            "claims": lock["claims"],
        }
        manifest_bytes = canonical_json(manifest)
        (prepared / "manifest.json").write_bytes(manifest_bytes)
        bootstrap = _bootstrap(digest_bytes(manifest_bytes), manifest["archive"]["sha256"], lock["runtime"]["python"]["file"])
        (prepared / "prepare.sh").write_bytes(bootstrap)
        (prepared / "prepare.sh").chmod(0o755)
        receipt = {
            "schema_version": 1, "status": "prepared-input-bundle",
            "candidate_package_sha256": lock["candidate"]["package"]["sha256"],
            "files": {p.name: {"size": p.stat().st_size, "sha256": file_digest(p)}
                      for p in sorted(prepared.iterdir())},
            "source_changes": lock["source_changes"],
            "wheel_count": len(selected), "baseline_distribution_count": len(lock["candidate"]["baseline_versions"]),
            "environment_included": False, "environment_recreated_at_destination": True,
            "assembly_validated_natively": False, "audio_readiness": False,
            "microphone_accessed": False, "recording_tested": False,
            "external_runtime_policy": lock["external_runtime_policy"],
        }
        (prepared / "BUNDLE-RECEIPT.json").write_bytes(canonical_json(receipt))
        require(not out.exists() and not out.is_symlink(), "output appeared during preparation")
        prepared.rename(out)
    return receipt


def fetch_inputs(out: Path, *, lock: dict | None = None) -> dict:
    """Fetch the four fixed inputs; the existing CUA candidate pin is untouched."""
    from urllib.request import urlopen
    from types import SimpleNamespace
    from fetch_compatibility_candidate import GitHubClient, _save_archive
    lock = lock or _load_lock()
    out = validate_destination(Path(out).absolute())
    client = GitHubClient(os.environ.get("GH_TOKEN", ""))
    base = "repos/" + lock["repository"] + "/actions"
    receipts = {}
    with tempfile.TemporaryDirectory(prefix=".audio-fetch-", dir=out.parent) as temporary:
        stage = Path(temporary)
        for label, filename in (("candidate", "candidate.zip"), ("audio", "audio.zip")):
            pin = lock[label]
            run = client.metadata(base + "/runs/" + str(pin["run_id"]))
            artifact = client.metadata(base + "/artifacts/" + str(pin["artifact_id"]))
            for key, value in (("id", pin["run_id"]), ("head_sha", pin["head_sha"]),
                               ("path", pin["workflow_path"]), ("status", "completed"), ("conclusion", pin["conclusion"])):
                require(run.get(key) == value, label + " run metadata mismatch: " + key)
            for key in ("repository", "head_repository"):
                require(run.get(key, {}).get("id") == lock["repository_id"] and
                        run.get(key, {}).get("full_name") == lock["repository"], label + " repository mismatch")
            for key, value in (("id", pin["artifact_id"]), ("name", pin["artifact_name"]),
                               ("size_in_bytes", pin["archive"]["bytes"]),
                               ("digest", "sha256:" + pin["archive"]["sha256"]), ("expired", False)):
                require(type(artifact.get(key)) is type(value) and artifact[key] == value,
                        label + " artifact metadata mismatch: " + key)
            association = artifact.get("workflow_run", {})
            for key, value in (("id", pin["run_id"]), ("head_sha", pin["head_sha"]),
                               ("repository_id", lock["repository_id"]), ("head_repository_id", lock["repository_id"])):
                require(association.get(key) == value, label + " artifact association mismatch")
            size_pin = SimpleNamespace(archive_size=pin["archive"]["bytes"], archive_sha256=pin["archive"]["sha256"])
            with client.artifact_stream(base + "/artifacts/" + str(pin["artifact_id"]) + "/zip") as stream:
                _save_archive(stream, stage / filename, size_pin)
            verify_archive(stage / filename, pin)
            receipts[label] = {"run": run, "artifact": artifact}
        for label in ("opensles", "openssl"):
            pin = lock[label]
            with urlopen(pin["url"], timeout=30) as source:
                data = source.read(pin["archive"]["size"] + 1)
            archive_path = stage / (label + ".deb")
            archive_path.write_bytes(data)
            verify_file(archive_path, pin["archive"], "official " + label + " archive")
            receipts[label] = {"url": pin["url"], "archive": pin["archive"]}
        (stage / "fetch-receipt.json").write_bytes(canonical_json(receipts))
        require(not out.exists() and not out.is_symlink(), "fetch output appeared")
        stage.rename(out)
    return {"status": "verified", "directory": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--out", required=True, type=Path)
    build = sub.add_parser("build")
    for name in ("candidate-archive", "audio-archive", "opensles-deb", "openssl-deb", "out"):
        build.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            result = fetch_inputs(args.out)
        else:
            result = build_bundle(args.candidate_archive, args.audio_archive, args.opensles_deb, args.out,
                                  openssl_deb=args.openssl_deb)
        print(json.dumps(result, indent=2))
        return 0
    except (StagingError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print("AUDIO_STAGING_FAILED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
