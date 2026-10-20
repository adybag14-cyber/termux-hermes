#!/usr/bin/env python3
"""Prepare an unpublished CUA candidate from the exact proven Termux package.

Run with the original candidate's native Python (-I -B) while that candidate is
installed at its real Termux prefix. This script does not install packages,
download inputs, change a lock, rebuild dependencies, or publish a release.
Only a separate dpkg extraction is changed. Canonical AgentInputs/assemble runs
from four SHA-verified upstream build modules; the staged app's own PM then
records the reviewed native driver. Native default-selection and lifecycle
validation remain separate mandatory gates.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import types
from typing import Any

PREFIX = Path("/data/data/com.termux/files/usr")
INSTALLED = PREFIX / "lib/hermes-agent"
TARGET = "linux-arm64-bionic"
APT_DEPENDS = "libx11, libxi"
ELF_NEEDED = frozenset(("libX11.so", "libXi.so", "libdl.so", "libm.so", "libc.so"))
UPSTREAM = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
PATCH_SHA256 = "8bbfddbbacfd508db35de6158e4c1a2c06423b84cd5f4ed621d4955fcd529edd"
PATCH_BYTES = 67709
SOURCE_RECEIPT_SHA256 = "47c43e002a868f0387e02142a9c623e5790c2656076959688abc3e93a6ec6167"
OUTPUT_DEB = "hermes-agent_0.22.2-1_aarch64-cua-candidate.deb"
INVENTORY_NAME = "CUA-PREPARED-PAYLOAD.json"
RECEIPT_NAME = "prepared-cua-receipt.json"
CANDIDATE = {
    "repository": "adybag14-cyber/termux-hermes",
    "run_id": 39048514731,
    "head_sha": "e271e922a2e71fd18591c45e9b98b8c7f9fffe02",
    "artifact_id": 12107225801,
    "artifact_name": "hermes-termux-next-stable-candidate",
    "artifact_bytes": 222119336,
    "artifact_sha256": "c49f41590424520b99136800b7ba9fa41f3ab3926d418131cdf686da812d849b",
    "package_file": "hermes-agent_0.22.2-1_aarch64.deb",
    "package_bytes": 222089768,
    "package_sha256": "1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a",
}
RAW_PINS = {
    "identity": ("CANDIDATE-IDENTITY.json", "bd45eceb7ffecf4e892243f6e964fd28337f1be20abee39435d934cc768fb5a5"),
    "native_selection": ("venv-selection.json", "5d7eef31190f9152c3b8005f3c9cc8bb05a69fdb57b883c648edcfe4db2cf1ce"),
}
SELECTION = {
    "schema": 1,
    "target": TARGET,
    "extras": ["acp", "cron", "matrix", "mcp", "telegram", "termux", "uvloop"],
    "stamp": "3b2935496d2e947be1904f37052d1fcbae409418e892a52973d5a46fc1df4d7f",
    "bundled_wheels": {"path": "bundled-wheels.json", "sha256": "d2dc66575cf8aa5ef828e5e536b4d55b8801143101b7e608f6fb4878c2397904"},
    "uv_lock_sha256": "72abb87a634769baaf30830cd317892053c6e15f8e9519b085524fa0ed542829",
    "pm_lock_sha256": "49b79259220160f147255078a19af541a5f328d3871c8041cc1eb909d19eb549",
    "requirements_sha256": "f3e32ca1cae5bb50a30e0957ed136f992d546e4475fb8bc73350790e9e762698",
}
PATCH_FILES = {
    "hermes_cli/tools_config.py": {
        "bytes": 62528,
        "sha256": "0917e0ba72ebcec3f9ef25fc2912881d93e957c69d9d5c588bbbd043e400352a"
    },
    "hermes_cli/tools_config_cua.py": {
        "bytes": 13367,
        "sha256": "2b3a21ebe23a5cf73a760bb50674e450d9bbc29ed639494506cca265cce3c6a5"
    },
    "hermes_cli/tools_config_providers.py": {
        "bytes": 57967,
        "sha256": "ac8f72e9f4ba724e2d6f7d5815cbe949e106d05d0fc28470f384824dcccb29bc"
    },
    "plugins/computer_use/cua/__init__.py": {
        "bytes": 2184,
        "sha256": "8c641bf2d6a455c46c93d5d3b5c025a618810a0938f3039ef81a25153e7c3661"
    },
    "tests/hermes_cli/test_cua_termux_setup.py": {
        "bytes": 1313,
        "sha256": "727bfcef24f4c7d64b7a2819b4dee00ab0ffb999224e432d0a56c13fe5611fd6"
    },
    "tests/tools/test_computer_use_termux_override.py": {
        "bytes": 5306,
        "sha256": "78b012f260821bc13c072f1517402f7cde3a2a70e15f1cec8b23d11555a5e3f7"
    },
    "tests/tools/test_cua_scroll_schema.py": {
        "bytes": 2667,
        "sha256": "fa40a2af52bd3e5e3a7946af91b0082dd1fd52f8dcf10234b69af1a6867008a5"
    },
    "tools/computer_use/cua_backend.py": {
        "bytes": 28820,
        "sha256": "f45d94d5d844e87d857b72a854f29eb6edabf13777e01cf922835f976ac9bd35"
    },
    "tools/computer_use/cua_backend_driver.py": {
        "bytes": 10146,
        "sha256": "c24c0cc00914e7450dcd7dcb2dc8d9cba1811894b64f1a248e62cbbc153932b8"
    },
    "tools/computer_use/cua_backend_input.py": {
        "bytes": 11650,
        "sha256": "e9bab44b82580a11015d631727a272d044711b2a096d74898725dcf5f172aab2"
    },
    "tools/computer_use/cua_backend_platform.py": {
        "bytes": 3453,
        "sha256": "05be45b88ec4378d3c87d5549bf85990bb193c233fb6724777ed5d6fe3d2ca2f"
    },
    "tools/computer_use/permissions.py": {
        "bytes": 8792,
        "sha256": "4c13f04af424f04e34448a9485564c9c5070862f7e54fbe752de937dbb72c995"
    },
    "pm/bundled_tools.py": {
        "bytes": 10485,
        "sha256": "ffa6a1e2c608d22034e7242e056936a7f306f400dd9ebd0e4a527b6ae4c8eabe"
    },
    "pm/install.py": {
        "bytes": 44976,
        "sha256": "8976fae19e0fb96f78b6a30629b34b12eb4a3281aa5349ddfd0f2fac7fa5d4d1"
    },
    "pm/packages.py": {
        "bytes": 59135,
        "sha256": "afd5805ee887176b7abd187a5ebf7ef82dcb88e766551214a440b27657026311"
    },
    "tests/pm/test_bundled_tools.py": {
        "bytes": 10409,
        "sha256": "55e8b51da40511748c911b24dbe166135aa03b22b81620c13da8aaa8b8bc1afa"
    },
    "tools/computer_use/tool.py": {
        "bytes": 65590,
        "sha256": "c6a9123bdc171f5e106d85dc30440cebdfe061476939987607c272eeaf2b5a36"
    },
    "tools/computer_use/schema.py": {
        "bytes": 8769,
        "sha256": "97b6171c49506bfd15883e9f438b4ffa73c8fb28f3864b7085ecd9f708ce5fba"
    },
    "tests/tools/test_cua_termux_delivery.py": {
        "bytes": 9580,
        "sha256": "fce4feb09e70d8fd7870127159d979e487310ec6e72fced729b0852c71793021"
    }
}
NEW_FILES = frozenset(["pm/bundled_tools.py","tests/hermes_cli/test_cua_termux_setup.py","tests/pm/test_bundled_tools.py","tests/tools/test_computer_use_termux_override.py","tests/tools/test_cua_scroll_schema.py","tests/tools/test_cua_termux_delivery.py","tools/computer_use/cua_backend_platform.py"])
ASSEMBLY_FILES = {
    "scripts/build/agent.py": {
        "bytes": 8754,
        "sha256": "f59ed0dc39a37814a43f2465e1391311a3ce8203e42a69257e58db6f3cda3652"
    },
    "scripts/build/inputs.py": {
        "bytes": 5846,
        "sha256": "36fb218726fce97505d7dfd50002046bb9c19b25c0b7cc546bae0b9c586083d9"
    },
    "scripts/build/launchers.py": {
        "bytes": 4861,
        "sha256": "cf5c225ded65193042a330f69b217a5ffcd5201032cca9e288cebea681cb37b3"
    },
    "scripts/build/launcher_wrapper.py": {
        "bytes": 6327,
        "sha256": "bfab043b63b8faa588ea1fa6f9143ff33b319df71ef6a7e3855f8574c2b07155"
    }
}
SHA256 = re.compile(r"[a-f0-9]{64}")
SHA1 = re.compile(r"[a-f0-9]{40}")


class PreparationError(ValueError):
    pass


def require(value: Any, message: str) -> None:
    if not value:
        raise PreparationError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def regular(path: Path) -> bool:
    return stat.S_ISREG(path.lstat().st_mode) if path.exists() or path.is_symlink() else False


def json_object(raw: bytes, label: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreparationError(f"invalid {label} JSON") from exc
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def write_json(path: Path, value: dict) -> dict:
    body = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(body)
    path.chmod(0o644)
    return {"file": path.name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def pinned_file(path: Path, *, digest: str, size: int | None = None) -> dict:
    require(SHA256.fullmatch(digest) is not None, "invalid expected SHA-256")
    require(regular(path), f"input is not a regular file: {path}")
    length = path.stat().st_size
    require(size is None or length == size, f"input size mismatch: {path.name}")
    actual = sha256(path)
    require(actual == digest, f"input SHA-256 mismatch: {path.name}")
    return {"file": path.name, "bytes": length, "sha256": actual}


def elf_linkage(path: Path) -> dict:
    """Read the actual ELF64 dynamic contract without executing the driver."""
    require(regular(path), "ELF input must be a regular file")
    length = path.stat().st_size
    with path.open("rb") as stream:
        def read(offset: int, size: int) -> bytes:
            require(type(offset) is int and type(size) is int and 0 <= offset <= length
                    and 0 <= size <= length - offset, "ELF table escapes the input")
            stream.seek(offset)
            data = stream.read(size)
            require(len(data) == size, "ELF input was truncated")
            return data

        header = struct.unpack("<16sHHIQQQIHHHHHH", read(0, 64))
        require(header[0][:7] == b"\x7fELF\x02\x01\x01" and header[1] == 3 and header[2] == 183
                and header[3] == 1 and header[8] == 64 and header[9] == 56
                and 1 <= header[10] <= 64, "expected an AArch64 ELF64 little-endian PIE")
        segments = [struct.unpack("<IIQQQQQQ", read(header[5] + i * 56, 56)) for i in range(header[10])]
        dynamic = [p for p in segments if p[0] == 2]
        interpreters = [p for p in segments if p[0] == 3]
        require(len(dynamic) == len(interpreters) == 1, "ELF must declare one dynamic table and interpreter")
        interp = interpreters[0]
        require(1 < interp[5] <= 256, "invalid ELF interpreter size")
        interpreter = read(interp[2], interp[5])
        require(interpreter == b"/system/bin/linker64\0", "ELF does not use the Android linker")
        table = dynamic[0]
        require(0 < table[5] <= 65536 and table[5] % 16 == 0, "invalid ELF dynamic table size")
        entries = [struct.unpack("<QQ", read(table[2] + i, 16)) for i in range(0, table[5], 16)]
        terminator = next((i for i, (tag, _) in enumerate(entries) if tag == 0), None)
        require(terminator is not None, "unterminated ELF dynamic table")
        entries = entries[:terminator]
        strings = [v for t, v in entries if t == 5]
        sizes = [v for t, v in entries if t == 10]
        require(len(strings) == len(sizes) == 1 and 0 < sizes[0] <= 1024 * 1024,
                "ELF dynamic strings are missing or ambiguous")
        mappings = [p for p in segments if p[0] == 1 and p[3] <= strings[0]
                    and strings[0] - p[3] + sizes[0] <= p[5]]
        require(len(mappings) == 1, "ELF dynamic strings do not map to one file segment")
        mapped = mappings[0]
        raw = read(mapped[2] + strings[0] - mapped[3], sizes[0])

        def string(offset: int) -> str:
            require(0 <= offset < len(raw), "ELF dynamic string offset is invalid")
            end = raw.find(b"\0", offset)
            require(end >= 0, "unterminated ELF dynamic string")
            try:
                return raw[offset:end].decode("ascii")
            except UnicodeError as exc:
                raise PreparationError("ELF dynamic string is not ASCII") from exc

        needed = [string(value) for tag, value in entries if tag == 1]
        require(len(needed) == len(set(needed)) and set(needed) == ELF_NEEDED,
                f"unreviewed ELF shared-library closure: {needed}")
        search = [string(value) for tag, value in entries if tag in (15, 29)]
        require(len(search) == 1 and posixpath.normpath(search[0]) == (PREFIX / "lib").as_posix(),
                f"ELF library search path differs from the declared Termux APT prefix: {search}")
        return {"interpreter": "/system/bin/linker64", "needed": needed, "search_path": search,
                "apt_depends": APT_DEPENDS,
                "platform_libraries": ["libc.so", "libdl.so", "libm.so"],
                "method": "Read actual ELF PT_DYNAMIC/DT_NEEDED/PT_INTERP; no driver execution."}


def payload_inventory(root: Path) -> dict[str, dict]:
    """Inventory all descendants, including directory modes, without following links.

    The root itself is excluded. Timestamps and UID/GID are excluded because dpkg
    assigns ownership on installation; bytes, link destinations and modes bind
    the actual executable payload. Special files are not a valid package input.
    """
    require(root.is_dir() and not root.is_symlink(), "payload root is not a real directory")
    rows = {}

    def visit(directory: Path):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                rows[relative] = {"kind": "symlink", "mode": mode, "target": os.readlink(path)}
            elif stat.S_ISDIR(info.st_mode):
                rows[relative] = {"kind": "directory", "mode": mode}
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                rows[relative] = {"kind": "file", "mode": mode, "bytes": info.st_size, "sha256": sha256(path)}
            else:
                raise PreparationError(f"payload contains a special file: {relative}")

    visit(root)
    return rows


def inventory_digest(rows: dict) -> str:
    data = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(data).hexdigest()


def subtree(rows: dict, prefix: str) -> dict:
    return {name[len(prefix) + 1:]: row for name, row in rows.items() if name.startswith(prefix + "/")}


def relative_path(root: Path, value: str, label: str) -> Path:
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
            f"invalid {label} path")
    parts = PurePosixPath(value)
    require(not parts.is_absolute() and all(p not in ("", ".", "..") for p in value.split("/")),
            f"invalid {label} path")
    path = root / value
    require(path.resolve().is_relative_to(root.resolve()), f"{label} escapes the payload")
    return path


def verify_candidate(directory: Path) -> tuple[dict, dict]:
    receipt_path = directory / "candidate-receipt.json"
    require(regular(receipt_path), "candidate fetch receipt is missing")
    require(receipt_path.stat().st_size <= 65536, "candidate fetch receipt is too large")
    receipt = json_object(receipt_path.read_bytes(), "candidate receipt")
    require(type(receipt.get("schema_version")) is int and receipt["schema_version"] == 1
            and receipt.get("status") == "verified", "candidate fetch is not verified schema 1")
    for key in ("repository", "run_id", "head_sha"):
        require(type(receipt.get(key)) is type(CANDIDATE[key]) and receipt[key] == CANDIDATE[key],
                f"candidate {key} mismatch")
    artifact = receipt.get("artifact", {})
    for key, source in (("id", "artifact_id"), ("name", "artifact_name"), ("bytes", "artifact_bytes"), ("sha256", "artifact_sha256")):
        require(type(artifact.get(key)) is type(CANDIDATE[source]) and artifact[key] == CANDIDATE[source],
                f"candidate artifact {key} mismatch")
    package = receipt.get("package", {})
    for key, source in (("file", "package_file"), ("bytes", "package_bytes"), ("sha256", "package_sha256")):
        require(type(package.get(key)) is type(CANDIDATE[source]) and package[key] == CANDIDATE[source],
                f"candidate package {key} mismatch")
    for key, (filename, digest) in RAW_PINS.items():
        raw = directory / filename
        pinned_file(raw, digest=digest)
        document = json_object(raw.read_bytes(), filename)
        wrapped = receipt.get(key, {})
        require(wrapped.get("file") == filename and wrapped.get("sha256") == digest,
                f"candidate {key} raw identity mismatch")
        require({k: v for k, v in wrapped.items() if k not in ("file", "sha256", "zip_member")} == document,
                f"candidate {key} receipt differs from raw bytes")
        if key == "native_selection":
            require(document == SELECTION, "candidate native selection differs")
    pinned_file(directory / CANDIDATE["package_file"], digest=CANDIDATE["package_sha256"], size=CANDIDATE["package_bytes"])
    return receipt, {"file": receipt_path.name, "bytes": receipt_path.stat().st_size, "sha256": sha256(receipt_path)}


def patch_paths(raw: bytes) -> set[str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise PreparationError("patch is not UTF-8 text") from exc
    names = []
    for line in lines:
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/([A-Za-z0-9_./-]+) b/([A-Za-z0-9_./-]+)", line)
            require(match is not None and match[1] == match[2], "patch renames or unsafe paths are not allowed")
            name = match[1]
            require(all(p not in ("", ".", "..") for p in name.split("/")), "patch path traversal")
            names.append(name)
        elif line.startswith(("GIT binary patch", "Binary files ", "rename ", "copy ", "deleted file mode", "old mode", "new mode")):
            raise PreparationError("patch may only modify or add regular text files")
        elif line.startswith("new file mode "):
            require(line == "new file mode 100644", "patch adds a non-regular or executable file")
    require(names and len(names) == len(set(names)), "patch contains no paths or repeats a path")
    return set(names)


def verify_patch(patch: Path, app: Path) -> dict:
    identity = pinned_file(patch, digest=PATCH_SHA256, size=PATCH_BYTES)
    require(patch_paths(patch.read_bytes()) == set(PATCH_FILES), "patch paths differ from reviewed source export")
    for name in PATCH_FILES:
        path = app / name
        require(not any(part.is_symlink() for part in [path, *list(path.parents)[:len(PurePosixPath(name).parts) - 1]]),
                f"patch path traverses a symlink: {name}")
        if name in NEW_FILES:
            require(not path.exists(), f"new patch path already exists: {name}")
        else:
            require(regular(path), f"existing patch path is missing or not regular: {name}")
    return identity


def verify_patched_files(app: Path) -> dict:
    for name, identity in PATCH_FILES.items():
        pinned_file(app / name, digest=identity["sha256"], size=identity["bytes"])
    return {name: dict(identity) for name, identity in sorted(PATCH_FILES.items())}


def parse_control(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise PreparationError("invalid Debian control encoding") from exc
    while lines and not lines[-1]:
        lines.pop()
    fields = {}
    current = None
    for line in lines:
        require(line != "", "multiple or empty Debian control paragraphs")
        if line.startswith((" ", "\t")):
            require(current is not None, "control continuation without a field")
            fields[current] += "\n" + line
            continue
        key, separator, value = line.partition(":")
        require(separator and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key), "invalid Debian control field")
        require(key not in fields, f"duplicate Debian control field: {key}")
        current = key
        fields[key] = value.strip()
    return fields


def check_package_fields(fields: dict, *, augmented: bool = False) -> None:
    for key, expected in (("Package", "hermes-agent"), ("Version", "0.22.2-1"), ("Architecture", "aarch64")):
        require(fields.get(key) == expected, f"Debian {key} differs from candidate")
    require(fields.get("Depends", "") == (APT_DEPENDS if augmented else ""),
            "Debian Depends differs from the exact candidate runtime contract")
    require(fields.get("Pre-Depends", "") == "", "unexpected Debian Pre-Depends")


def prepare_control(control: Path, size_kib: int) -> dict:
    require(type(size_kib) is int and size_kib > 0, "invalid installed size")
    before = parse_control(control.read_bytes())
    check_package_fields(before)
    lines = control.read_text(encoding="utf-8").splitlines()
    for key, value in (("Installed-Size", str(size_kib)), ("Depends", APT_DEPENDS)):
        positions = [i for i, line in enumerate(lines) if line.startswith(key + ":")]
        require(len(positions) <= 1, f"duplicate {key}")
        if positions:
            lines[positions[0]] = f"{key}: {value}"
        else:
            lines.append(f"{key}: {value}")
    control.write_text("\n".join(lines) + "\n", encoding="utf-8")
    after = parse_control(control.read_bytes())
    allowed = {"Installed-Size", "Depends"}
    require({k: v for k, v in before.items() if k not in allowed} ==
            {k: v for k, v in after.items() if k not in allowed},
            "control update changed an undeclared package field")
    check_package_fields(after, augmented=True)
    return {"original_fields": before, "prepared_fields": after,
            "installed_size_kib": {"before": before.get("Installed-Size"), "after": str(size_kib)},
            "declared_runtime_libraries": {"libX11.so": "libx11", "libXi.so": "libxi"}}


def system_environment() -> dict:
    env = dict(os.environ)
    for name in list(env):
        if name.startswith("GIT_") or name in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME"):
            env.pop(name)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 120,
        env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, cwd=cwd, env=system_environment() if env is None else env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        raise PreparationError(f"{Path(argv[0]).name} exited {result.returncode}: "
                               + result.stderr.decode("utf-8", "replace")[-8000:])
    return result


def verify_native_invocation() -> dict:
    require(sys.flags.isolated and sys.dont_write_bytecode, "invoke the candidate interpreter with -I -B")
    require(sys.implementation.name == "cpython" and sys.version_info[:3] == (3, 14, 6),
            "exact native candidate CPython 3.14.6 is required")
    require(os.name == "posix" and sys.platform in ("linux", "android")
            and platform.machine().lower() in ("aarch64", "arm64"), "native AArch64 Termux is required")
    require(INSTALLED.resolve() == INSTALLED and INSTALLED.is_dir(), "the original candidate is not at its real prefix")
    require(Path(sys.executable).resolve().is_relative_to(INSTALLED / "tools/python"),
            "the executing interpreter is not the installed candidate's bundled Python")
    require(Path(sys.base_prefix).resolve().is_relative_to(INSTALLED / "tools/python"),
            "the interpreter base prefix does not belong to the candidate")
    require(os.environ.get("PREFIX") == str(PREFIX), "unexpected Termux PREFIX")
    return {"executable": sys.executable, "base_prefix": sys.base_prefix, "version": sys.version,
            "machine": platform.machine(), "sys_platform": sys.platform, "sha256": sha256(Path(sys.executable).resolve())}


def canonical_modules(root: Path):
    for name, identity in ASSEMBLY_FILES.items():
        pinned_file(root / name, digest=identity["sha256"], size=identity["bytes"])
    # The original package intentionally omits scripts. Load only the reviewed
    # build modules; a reference source tree must never select its PM or app.
    for name, path in (("scripts", root / "scripts"), ("scripts.build", root / "scripts/build")):
        require(name not in sys.modules, f"unexpected preloaded build namespace: {name}")
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    loaded = {}
    for name in ("inputs", "launchers", "agent"):
        qualified = "scripts.build." + name
        path = root / "scripts/build" / (name + ".py")
        spec = importlib.util.spec_from_file_location(qualified, path)
        require(spec is not None and spec.loader is not None, "cannot load canonical build module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded["inputs"], loaded["agent"]


def verify_native_selection(payload: Path, manifest: dict) -> dict:
    require(manifest.get("schema") == 1 and manifest.get("target") == TARGET
            and manifest.get("repo") == "app" and manifest.get("venv") == "venv"
            and manifest.get("store") == "tools", "candidate payload layout differs")
    require(manifest.get("bundled_wheels") == SELECTION["bundled_wheels"],
            "candidate bundled wheel descriptor differs")
    pinned_file(payload / "bundled-wheels.json", digest=SELECTION["bundled_wheels"]["sha256"])
    pinned_file(payload / "app/uv.lock", digest=SELECTION["uv_lock_sha256"])
    pinned_file(payload / "app/pm/lock.json", digest=SELECTION["pm_lock_sha256"])
    features = json_object((payload / "enabled-features.json").read_bytes(), "enabled features")
    require(features == {"schema": 1, "extras": SELECTION["extras"]}, "candidate extra selection differs")
    facts = json_object((payload / "tools/facts.json").read_bytes(), "payload facts")
    require(facts.get("packages", {}).get("venv") ==
            {"stamp": SELECTION["stamp"], "extras": SELECTION["extras"]}, "candidate native venv fact differs")
    return facts


def assemble_worker(request_file: Path) -> None:
    request = json_object(request_file.read_bytes(), "assembly request")
    payload, assembly = Path(request["payload"]), Path(request["assembly_source"])
    app = payload / "app"
    require("pm" not in sys.modules, "assembly worker must start without another PM import")
    verify_patched_files(app)
    sys.path.insert(0, str(app))
    from pm.bundled_wheels import write_catalog
    from pm.bundled_tools import selected_tool, stage_source_built_tool
    from pm.filesystem import durable_write_bytes
    from pm.packages import Venv
    from pm.paths import repo_root
    from pm.runtime import _inputs
    from pm.store import current_target

    require(repo_root().resolve() == app.resolve(), "assembly worker imported another app's PM")
    require(current_target() == TARGET, "selection identity must be checked on actual Bionic")
    old_manifest = json_object((payload / "manifest.json").read_bytes(), "original manifest")
    verify_native_selection(payload, old_manifest)
    old_facts_sha = sha256(payload / "tools/facts.json")
    runtime = old_manifest["runtime"]
    python = relative_path(payload, runtime["storePython"], "store Python")
    site = relative_path(payload, runtime["sitePackages"], "application site")
    pm_site = json_object((payload / "pm-runtime/pm-runtime.json").read_bytes(), "PM marker")
    require((payload / "pm-runtime" / pm_site["sitePackages"]).resolve().is_relative_to(payload / "pm-runtime"),
            "PM site escapes its runtime")
    require((payload / "pm-runtime" / pm_site["python"]).resolve().is_relative_to(payload),
            "PM interpreter escapes its payload")
    recomputed = Venv(app).expected_stamp(SELECTION["extras"], plugin_dirs=[],
                                         bundled_wheels_sha256=SELECTION["bundled_wheels"]["sha256"])
    require(recomputed == SELECTION["stamp"], "patched PM changes native dependency selection; rebuild is required")
    final_python = INSTALLED / runtime["storePython"]
    manager_before = _inputs(INSTALLED / "app/pm", final_python)
    manager_after = _inputs(app / "pm", final_python)
    require(manager_before == manager_after, "PM dependency runtime inputs changed; rebuild is required")
    inputs_module, agent_module = canonical_modules(assembly)
    inputs = inputs_module.AgentInputs(
        project=app / "pyproject.toml", code=app, repo="app", placement="fixed", target=TARGET,
        python=python, site_packages=site, environment=payload / "venv", pm_runtime=payload / "pm-runtime",
        tools=payload / "tools", resources={name: app / name for name in inputs_module.RESOURCE_ENV},
        stamp=app / "install-stamp.json", features=payload / "enabled-features.json",
    )
    # Built frontend products already reside in this exact app snapshot and are
    # preserved by the full-file oracle; no frontend source graph is re-entered.
    manifest = agent_module.assemble(inputs, payload)
    descriptor = write_catalog(payload, wheelhouse=payload / "wheelhouse",
                               lock_paths=(app / "uv.lock", app / "pm/uv.lock"))
    require(descriptor == SELECTION["bundled_wheels"], "canonical catalog no longer matches native selection")
    manifest["bundled_wheels"] = descriptor
    durable_write_bytes(payload / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    (payload / "manifest.json").chmod(0o644)
    require(sha256(payload / "tools/facts.json") == old_facts_sha, "source-only assembly changed dependency facts")
    staged = stage_source_built_tool(
        payload, name="cua-driver", target=TARGET, binary=Path(request["driver"]),
        binary_sha256=request["driver_sha256"], source_receipt=Path(request["source_receipt"]),
    )
    tool = selected_tool("cua-driver", target=TARGET)
    require(tool is not None and tool.binary.resolve() ==
            (payload / staged["tool"]["entry"] / staged["tool"]["binary"]).resolve(),
            "staged PM does not passively select its own resident driver")
    require(sha256(tool.binary) == request["driver_sha256"], "resident selection changed driver bytes")
    require(not any(os.environ.get(name) for name in
                    ("HERMES_CUA_DRIVER_CMD", "HERMES_RUNTIME_DIR", "HERMES_INSTALL_ROOT")),
            "assembly worker used a runtime authority override")
    write_json(Path(request["result"]), {
        "bundled_tools": staged,
        "dependency_identity": {
            "venv_stamp_original": SELECTION["stamp"], "venv_stamp_recomputed": recomputed,
            "pm_runtime_inputs_original": manager_before, "pm_runtime_inputs_recomputed": manager_after,
            "method": "Native PM recomputation; unchanged exact graph/catalog and final interpreter path.",
            "environment_rebuilt": False, "facts_sha256": old_facts_sha,
        },
        "pm_source": "app/pm", "target": current_target(),
        "passive_resident_selection": "passed", "runtime_authority_overrides": [],
    })


def run_worker(payload: Path, assembly_source: Path, driver: Path, driver_sha256: str,
               source_receipt: Path, workspace: Path) -> dict:
    request = workspace / "assembly-request.json"
    result = workspace / "assembly-result.json"
    write_json(request, {"payload": str(payload), "assembly_source": str(assembly_source),
                         "driver": str(driver), "driver_sha256": driver_sha256,
                         "source_receipt": str(source_receipt), "result": str(result)})
    # Canonical PM launch uses the original installed independent runtime. The
    # fresh child selects only staged app/pm; it never imports this parent's PM.
    sys.path.insert(0, str(INSTALLED / "app"))
    from pm.paths import repo_root
    from pm.runtime import runtime_command, runtime_environment

    require(repo_root().resolve() == INSTALLED / "app", "bootstrap PM is not the installed candidate's PM")
    command = runtime_command(Path(__file__).resolve(), ["--assembly-worker", str(request)], bootstrap=False)
    env = runtime_environment()
    for name in ("HERMES_CUA_DRIVER_CMD", "HERMES_RUNTIME_DIR", "HERMES_INSTALL_ROOT", "HERMES_PYTHON_SRC_ROOT"):
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run(command, timeout=600, env=env)
    require(regular(result), "canonical assembly worker produced no result")
    return json_object(result.read_bytes(), "assembly result")


def verify_change_boundary(before: dict, after: dict, tool_row: dict) -> dict:
    source_paths = {"app/" + name for name in PATCH_FILES}
    entry = tool_row["entry"]
    new_paths = {"bundled-tools.json", entry, entry + "/" + tool_row["binary"],
                 entry + "/" + tool_row["source_receipt"]}
    allowed = source_paths | new_paths | {"manifest.json"}
    for name in list(allowed):
        allowed.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    changes = {}
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        require(name in allowed and new is not None, f"unreviewed payload change: {name}")
        if name not in source_paths | new_paths | {"manifest.json"}:
            require(old is None and new["kind"] == "directory", f"existing ancestor changed: {name}")
        changes[name] = {"before": old, "after": new}
    for name, pin in PATCH_FILES.items():
        row = after.get("app/" + name)
        require(row is not None and row["kind"] == "file" and row["bytes"] == pin["bytes"]
                and row["sha256"] == pin["sha256"], f"patched source output mismatch: {name}")
    for prefix in ("venv", "pm-runtime", "wheelhouse", "runtime-libs"):
        require(subtree(before, prefix) == subtree(after, prefix), f"original {prefix} files changed")
    require(before["bundled-wheels.json"] == after["bundled-wheels.json"], "original wheel catalog changed")
    require(before["tools/facts.json"] == after["tools/facts.json"], "original PM facts changed")
    return changes


def ensure_separate_output(out: Path, inputs: tuple[Path, ...]) -> None:
    require(not out.exists() and not out.is_symlink(), "output directory already exists")
    resolved = out.resolve()
    for source in inputs:
        source = source.resolve()
        require(not resolved.is_relative_to(source) and not source.is_relative_to(resolved),
                "output must be separate from every input and installed payload")


def prepare(options) -> Path:
    interpreter = verify_native_invocation()
    candidate_dir, patch = options.candidate_dir.resolve(), options.patch.resolve()
    assembly, driver = options.assembly_source.resolve(), options.driver.absolute()
    source_receipt, out = options.source_receipt.absolute(), options.out.absolute()
    require(SHA1.fullmatch(options.packaging_commit) is not None, "packaging commit must be a full Git SHA")
    ensure_separate_output(out, (candidate_dir, assembly, driver, source_receipt, INSTALLED, patch))
    receipt, receipt_identity = verify_candidate(candidate_dir)
    original_deb = candidate_dir / CANDIDATE["package_file"]
    patch_identity = pinned_file(patch, digest=PATCH_SHA256, size=PATCH_BYTES)
    driver_identity = pinned_file(driver, digest=options.driver_sha256)
    source_identity = pinned_file(source_receipt, digest=SOURCE_RECEIPT_SHA256)
    linkage = elf_linkage(driver)
    for name, pin in ASSEMBLY_FILES.items():
        pinned_file(assembly / name, digest=pin["sha256"], size=pin["bytes"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".prepare-cua-", dir=out.parent) as temporary:
        workspace = Path(temporary)
        stage, result_dir = workspace / "package-root", workspace / "result"
        result_dir.mkdir(mode=0o755)
        print("Verifying the separate original package extraction...", flush=True)
        run(["dpkg-deb", "--raw-extract", str(original_deb), str(stage)], timeout=300)
        payload = stage / INSTALLED.relative_to("/")
        require(payload.is_dir(), "extracted package has no fixed-prefix Hermes payload")
        control_dir = stage / "DEBIAN"
        controls_before = payload_inventory(control_dir)
        require(set(controls_before) == {"control", "postinst", "prerm"},
                "unreviewed Debian control members require an explicit regeneration contract")
        check_package_fields(parse_control((control_dir / "control").read_bytes()))
        before = payload_inventory(payload)
        installed_before = payload_inventory(INSTALLED)
        require(installed_before == before, "installed candidate differs from the exact original package")
        verify_native_selection(payload, json_object((payload / "manifest.json").read_bytes(), "manifest"))
        verify_patch(patch, payload / "app")
        git_env = system_environment()
        git_env["GIT_CEILING_DIRECTORIES"] = str((payload / "app").parent)
        run(["git", "-c", "core.autocrlf=false", "apply", "--check", "--whitespace=error-all", str(patch)],
            cwd=payload / "app", env=git_env)
        run(["git", "-c", "core.autocrlf=false", "apply", "--whitespace=error-all", str(patch)],
            cwd=payload / "app", env=git_env)
        source_files = verify_patched_files(payload / "app")
        print("Reassembling with canonical build modules and staged native PM...", flush=True)
        worker = run_worker(payload, assembly, driver, options.driver_sha256, source_receipt, workspace)
        after = payload_inventory(payload)
        changes = verify_change_boundary(before, after, worker["bundled_tools"]["tool"])
        # All original tools, including their linker libraries and package facts,
        # were protected by the same exact change-boundary oracle above.
        controls_middle = payload_inventory(control_dir)
        require(controls_middle == controls_before, "assembly changed maintainer/control files")
        size_text = run(["du", "-sk", str(stage)]).stdout.decode("ascii").split()[0]
        require(size_text.isdigit(), "du returned no valid installed size")
        control_change = prepare_control(control_dir / "control", int(size_text))
        controls_after = payload_inventory(control_dir)
        require({k: v for k, v in controls_before.items() if k != "control"} ==
                {k: v for k, v in controls_after.items() if k != "control"},
                "maintainer scripts changed")
        package = result_dir / OUTPUT_DEB
        print("Building the distinct unpublished same-version candidate...", flush=True)
        run(["dpkg-deb", "--build", "-Zxz", "--root-owner-group", str(stage), str(package)], timeout=900)
        package.chmod(0o644)
        check_package_fields(parse_control(run(["dpkg-deb", "--field", str(package)]).stdout), augmented=True)
        # Verify final container serialization instead of assuming dpkg copied the
        # tree correctly. No executable from the augmented payload runs here.
        roundtrip = workspace / "roundtrip"
        run(["dpkg-deb", "--raw-extract", str(package), str(roundtrip)], timeout=300)
        require(payload_inventory(roundtrip / INSTALLED.relative_to("/")) == after,
                "new Debian payload differs from prepared bytes")
        require(payload_inventory(roundtrip / "DEBIAN") == controls_after,
                "new Debian control archive differs from prepared bytes")
        require(payload_inventory(INSTALLED) == installed_before, "original installed payload was mutated")
        verify_candidate(candidate_dir)
        pinned_file(patch, digest=PATCH_SHA256, size=PATCH_BYTES)
        pinned_file(driver, digest=options.driver_sha256)
        pinned_file(source_receipt, digest=SOURCE_RECEIPT_SHA256)
        inventory = write_json(result_dir / INVENTORY_NAME, {"schema_version": 1, "files": after})
        catalog = json_object((payload / "bundled-wheels.json").read_bytes(), "bundled wheels")
        source = {
            "full_source_reference_only": {"baseline_tree": "f49c77b666cef7fd5235cdd786556908527b532e",
                                           "replay_tree": "dfac85279351daafa64350b6bfc7fcb3ac3ce02b"},
            "method": "Exact candidate trimmed app plus the pinned experimental patch; not the full reference Git tree.",
            "original_app_inventory_sha256": inventory_digest(subtree(before, "app")),
            "prepared_app_inventory_sha256": inventory_digest(subtree(after, "app")),
            "changed_files": source_files,
        }
        output = {
            "schema_version": 1, "status": "prepared-candidate", "published": False, "version_bumped": False,
            "purpose": "Unpublished native default-CUA and package-lifecycle validation only.",
            "packaging_commit": options.packaging_commit,
            "input_candidate": {
                "run_id": CANDIDATE["run_id"], "head_sha": CANDIDATE["head_sha"],
                "artifact_id": CANDIDATE["artifact_id"], "package_sha256": CANDIDATE["package_sha256"],
                "candidate_receipt_sha256": receipt_identity["sha256"],
            },
            "package": {"file": OUTPUT_DEB, "bytes": package.stat().st_size, "sha256": sha256(package),
                        "name": "hermes-agent", "version": "0.22.2-1", "architecture": "aarch64",
                        "depends": APT_DEPENDS, "pre_depends": ""},
            "patch": {"file": "cua-hermes-integration.patch", "bytes": PATCH_BYTES, "sha256": PATCH_SHA256},
            "assembly_source": {"upstream_commit": UPSTREAM, "files": ASSEMBLY_FILES},
            "source": source, "native_selection": SELECTION,
            "bundled_tools": worker["bundled_tools"],
            "driver_input": driver_identity, "source_receipt": source_identity, "driver_linkage": linkage,
            "payload": {"root": str(INSTALLED), "manifest_sha256": sha256(payload / "manifest.json"),
                        "inventory": inventory, "inventory_sha256": inventory_digest(after)},
            "dependency_identity": {
                **worker["dependency_identity"],
                "original_wheel_count": len(catalog["wheels"]),
                "original_wheels_preserved": True,
                "original_venv_inventory_sha256": inventory_digest(subtree(before, "venv")),
                "original_pm_runtime_inventory_sha256": inventory_digest(subtree(before, "pm-runtime")),
                "locks_and_catalog_preserved": True,
            },
            "interpreter": interpreter, "payload_changes": changes,
            "control": {"original": controls_before, "prepared": controls_after, **control_change},
            "checks": {
                "original_input_and_installed_payload_preserved": "passed",
                "exact_patch_paths_and_output_hashes": "passed",
                "canonical_agent_assembly": "passed", "native_dependency_identity": "passed",
                "unchanged_dependency_bytes": "passed", "passive_resident_selection": "passed",
                "deb_roundtrip_identity": "passed",
                "native_default_cua_integration": "required-pending",
                "installed_package_reinstall_and_optional_pm_lifecycle": "required-pending",
            },
        }
        require(output["package"]["sha256"] != CANDIDATE["package_sha256"], "augmentation did not create a new identity")
        write_json(result_dir / RECEIPT_NAME, output)
        require(not out.exists() and not out.is_symlink(), "output appeared during preparation")
        result_dir.rename(out)
    print(str(out / RECEIPT_NAME), flush=True)
    return out / RECEIPT_NAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--assembly-source", type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--driver-sha256")
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--packaging-commit")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--assembly-worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.assembly_worker is not None:
            assemble_worker(args.assembly_worker)
        else:
            for key in ("candidate_dir", "patch", "assembly_source", "driver", "driver_sha256",
                        "source_receipt", "packaging_commit", "out"):
                require(getattr(args, key) is not None, "--" + key.replace("_", "-") + " is required")
            prepare(args)
    except (PreparationError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        print(f"CUA candidate preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
