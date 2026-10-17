#!/usr/bin/env python3
"""Recreate and verify the frozen Hermes audio experiment at its final native path."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib
import importlib.metadata as metadata
import io
import json
import math
import numbers
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import stat
import subprocess
import sys
import sysconfig
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prepare_audio_device_bundle as bundle
else:
    from . import prepare_audio_device_bundle as bundle

StagingError = bundle.StagingError
require = bundle.require
PREFIX = bundle.PREFIX
SITE = "lib/python3.14/site-packages"
MANIFEST = "staging/bundle-manifest.json"
RECEIPT = "staging/assembly-receipt.json"
ENVIRONMENT = "staging/environment-manifest.json"
VALIDATION = "staging/native-validation.json"
DIAGNOSTIC = "staging/audio-diagnostic.json"
LIB_DIRS = (
    "tools/python/data/data/com.termux/files/usr/lib",
    "tools/node/data/data/com.termux/files/usr/lib",
    "tools/ffmpeg/data/data/com.termux/files/usr/lib",
    "runtime-libs/lib",
)
SEALED_ROOTS = ("venv", "pm-runtime")
ADDITIONS = {"numpy": "2.4.3", "sounddevice": "0.5.5"}


def normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def runtime_environment(root: Path, inherited_env: dict[str, str]) -> dict[str, str]:
    """Keep the user's HOME; place all experiment state and native libraries here."""
    for key in inherited_env:
        require(key != "_PYTHON_HOST_PLATFORM" and not key.startswith("_PYTHON_SYSCONFIGDATA"),
                "inherited Python platform override is forbidden")
    root = Path(root)
    require(root.is_absolute(), "runtime root must be absolute")
    env = {
        key: value for key, value in inherited_env.items()
        if not key.startswith(("PYTHON", "LD_", "UV_", "PIP_", "HERMES_"))
        and key not in {"VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "BASH_ENV", "ENV"}
    }
    state = root / "state"
    env.update({
        "PREFIX": PREFIX,
        "HERMES_HOME": str(state / "profile"),
        "HERMES_RUNTIME_DIR": str(root / "tools"),
        "HERMES_PYTHON_SRC_ROOT": str(root / "app"),
        "HERMES_PYTHON": str(root / "venv/bin/python"),
        "HERMES_NODE": str(root / "tools/node/data/data/com.termux/files/usr/bin/node"),
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "XDG_CACHE_HOME": str(state / "cache"),
        "XDG_CONFIG_HOME": str(state / "config"),
        "XDG_DATA_HOME": str(state / "data"),
        "XDG_STATE_HOME": str(state / "local-state"),
        "TMPDIR": str(state / "tmp"), "TMP": str(state / "tmp"), "TEMP": str(state / "tmp"),
        "UV_CACHE_DIR": str(state / "cache/uv"), "UV_OFFLINE": "1", "PIP_NO_INDEX": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(state / "cache/pycache"),
        "LD_LIBRARY_PATH": os.pathsep.join(str(root / path) for path in LIB_DIRS),
    })
    binaries = [str(root / "tools" / name / "data/data/com.termux/files/usr/bin")
                for name in ("python", "uv", "node", "npm", "ffmpeg", "ripgrep")]
    env["PATH"] = os.pathsep.join(binaries + ["/system/bin", PREFIX + "/bin"])
    return env


def write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    require(not path.is_symlink() and path.parent.is_dir() and not path.parent.is_symlink(),
            "receipt destination is not a regular owned path")
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()
    with path.open("xb" if exclusive else "wb") as stream:
        stream.write(data)
    path.chmod(0o644)


def root_path(value: Path) -> Path:
    root = Path(value)
    require(root.is_absolute() and root.is_dir() and not root.is_symlink() and root.resolve() == root,
            "destination must be a real, canonical, absolute directory")
    installed = Path(PREFIX) / "lib/hermes-agent"
    require(not root.is_relative_to(installed) and not installed.is_relative_to(root),
            "destination overlaps the installed Hermes candidate")
    return root


def load_bundle(root: Path, *, verify: bool = True) -> dict:
    root_path(root)
    manifest = bundle.read_json(root / MANIFEST)
    lock = bundle.read_json(root / "staging/audio_device_bundle_lock.json")
    require(manifest.get("lock") == lock, "bundle lock snapshot differs")
    require(lock.get("schema_version") == 1, "unsupported frozen lock")
    if verify:
        bundle.verify_manifest_tree(root, manifest, allow_generated=True)
    for name, pin in lock["source_locks"].items():
        bundle.verify_file(root / name, pin, "frozen source lock")
    for change in lock["source_changes"]:
        bundle.verify_file(root / change["path"], change["after"], "exact audio source patch")
    return manifest


def assert_native(root: Path, lock: dict, *, application: bool = False) -> Path:
    runtime = lock["runtime"]
    python = root / runtime["python"]["file"]
    bundle.verify_file(python, runtime["python"], "bundled Python")
    require(sys.platform == runtime["sys_platform"], "native Android Python is required")
    require(platform.machine().lower() in runtime["machine"], "native ARM64 is required")
    require(list(sys.version_info[:3]) == runtime["python_version"], "bundled Python version differs")
    require(sysconfig.get_platform() == runtime["sysconfig_platform"], "native platform tag differs")
    require(Path(sys.executable).resolve() == python.resolve(), "unexpected executing interpreter")
    require(hasattr(os, "geteuid") and os.geteuid() != 0, "run as the ordinary Termux user")
    require(root.stat().st_uid == os.geteuid(), "destination is not owned by this user")
    if application:
        require(Path(sys.prefix).resolve() == root / "venv", "application must use its fresh venv")
        require(Path(sys.base_prefix).resolve().is_relative_to(root / "tools/python"),
                "application base interpreter escaped the payload")
    return python


def expected_versions(lock: dict) -> dict[str, str]:
    baseline = lock["candidate"]["baseline_versions"]
    require(len(baseline) == 100 and baseline.get("hermes-agent") == "0.0.0",
            "frozen candidate inventory differs")
    require("setuptools" not in baseline and not set(ADDITIONS).intersection(baseline),
            "unexpected baseline audio/build dependency")
    expected = dict(baseline)
    expected.update(ADDITIONS)
    return expected


def app_site(root: Path) -> Path:
    path = root / "venv" / SITE
    require(path.is_dir() and not path.is_symlink() and path.resolve() == path,
            "isolated application site-packages is missing")
    return path


def source_pth(root: Path) -> bytes:
    return (Path(os.path.relpath(root / "app", root / "venv" / SITE)).as_posix() + "\n").encode()


def add_source(root: Path) -> None:
    site = app_site(root)
    target = site / "hermes-agent.pth"
    require(not target.exists() and not target.is_symlink(), "source PTH already exists")
    infos = list((root / "app").glob("hermes_agent-*.dist-info/METADATA"))
    require(len(infos) == 1, "frozen source-layout Hermes metadata is missing or ambiguous")
    target.write_bytes(source_pth(root))
    target.chmod(0o644)


def audio_resolver_source(root: Path, pin: dict) -> bytes:
    """An owned locator adapter, not a replacement for PortAudio's native loading."""
    library = str(root / "runtime-libs/lib/libportaudio.so.2")
    code = (
        '"""Private Hermes audio experiment: locate only the frozen PortAudio library."""\n'
        'import ctypes.util as _hermes_ctypes_util\n'
        'import hashlib as _hermes_hashlib\n'
        'from pathlib import Path as _HermesPath\n'
        '_HERMES_AUDIO_ROOT = ' + repr(str(root)) + '\n'
        '_HERMES_AUDIO_LIBRARY = ' + repr(library) + '\n'
        '_HERMES_AUDIO_SHA256 = ' + repr(pin["sha256"]) + '\n'
        '_HERMES_AUDIO_SIZE = ' + repr(pin["size"]) + '\n'
        '_hermes_original_find_library = _hermes_ctypes_util.find_library\n'
        'def _hermes_audio_find_library(name):\n'
        '    if name != "portaudio":\n'
        '        return _hermes_original_find_library(name)\n'
        '    path = _HermesPath(_HERMES_AUDIO_LIBRARY)\n'
        '    if (not path.is_file() or path.is_symlink() or path.resolve() != path\n'
        '            or path.stat().st_size != _HERMES_AUDIO_SIZE\n'
        '            or _hermes_hashlib.sha256(path.read_bytes()).hexdigest() != _HERMES_AUDIO_SHA256):\n'
        '        raise OSError("Frozen isolated PortAudio library failed verification")\n'
        '    return str(path)\n'
        '_hermes_audio_find_library("portaudio")\n'
        '_hermes_ctypes_util.find_library = _hermes_audio_find_library\n'
    )
    return code.encode()


def add_audio_resolver(root: Path, lock: dict) -> None:
    path = app_site(root) / "sitecustomize.py"
    require(not path.exists() and not path.is_symlink(), "private audio resolver already exists")
    path.write_bytes(audio_resolver_source(root, lock["audio"]["portaudio"]))
    path.chmod(0o644)


def verify_audio_resolver(root: Path, lock: dict) -> dict:
    import ctypes.util
    path = app_site(root) / "sitecustomize.py"
    require(path.is_file() and not path.is_symlink()
            and path.read_bytes() == audio_resolver_source(root, lock["audio"]["portaudio"]),
            "owned audio resolver source differs")
    adapter = sys.modules.get("sitecustomize")
    require(adapter is not None and Path(adapter.__file__).resolve() == path
            and getattr(adapter, "_HERMES_AUDIO_ROOT", None) == str(root)
            and ctypes.util.find_library is getattr(adapter, "_hermes_audio_find_library", None),
            "private audio resolver was not activated from this environment")
    resolved = ctypes.util.find_library("portaudio")
    require(resolved == str(root / "runtime-libs/lib/libportaudio.so.2"), "PortAudio resolver escaped frozen library")
    return {"path": path.relative_to(root).as_posix(), "sha256": bundle.file_digest(path),
            "name": "portaudio", "resolved": resolved, "library_sha256": lock["audio"]["portaudio"]["sha256"],
            "other_names_delegated": True, "native_loading_replaced": False, "audio_imported_at_startup": False}


def inside(root: Path, path: Path, label: str) -> Path:
    require(path.resolve().is_relative_to(root), label + " escapes destination")
    return path


def inventory_entry(root: Path, path: Path) -> dict:
    name = path.relative_to(root).as_posix()
    bundle.safe_relative_path(name)
    require(path.parent.resolve().is_relative_to(root), "generated parent escapes destination")
    mode = path.lstat().st_mode
    row = {"path": name, "mode": stat.S_IMODE(mode)}
    if path.is_symlink():
        target = os.readlink(path)
        bundle.safe_link_target(name, target)
        require(path.exists() and path.resolve().is_relative_to(root), "generated symlink escapes destination")
        row.update(kind="symlink", target=target)
    elif stat.S_ISDIR(mode):
        row["kind"] = "directory"
    elif stat.S_ISREG(mode):
        row.update(kind="file", size=path.stat().st_size, sha256=bundle.file_digest(path))
    else:
        raise StagingError("unsupported generated filesystem member")
    return row


def environment_inventory(root: Path) -> dict:
    entries = []
    for relative in SEALED_ROOTS:
        top = root / relative
        require(top.is_dir() and not top.is_symlink(), "generated environment root must be a real directory")
        entries.append(inventory_entry(root, top))
        for parent, dirs, files in os.walk(top, followlinks=False):
            for name in dirs + files:
                entries.append(inventory_entry(root, Path(parent) / name))
    entries.append(inventory_entry(root, root / "tools/facts.json"))
    return {"schema_version": 1, "root": str(root), "entries": sorted(entries, key=lambda row: row["path"]),
            "sealed_roots": list(SEALED_ROOTS), "mutable_state": "state"}


def verify_generated_tree(root: Path, snapshot: dict) -> dict:
    require(snapshot.get("schema_version") == 1 and snapshot.get("root") == str(root),
            "environment receipt belongs to a different destination")
    require(snapshot.get("sealed_roots") == list(SEALED_ROOTS) and snapshot.get("mutable_state") == "state",
            "generated environment policy differs")
    actual = environment_inventory(root)
    require(actual == snapshot, "generated environment bytes, paths, or modes changed")
    state = root / "state"
    require(state.is_dir() and not state.is_symlink(), "mutable state root is not an owned directory")
    # State is mutable, but it can never redirect a future launch outside this destination.
    for parent, dirs, files in os.walk(state, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            require(path.parent.resolve().is_relative_to(state), "state parent escapes isolated state")
            mode = path.lstat().st_mode
            require(stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode),
                    "unsupported mutable state member")
            if path.is_symlink():
                require(path.exists() and path.resolve().is_relative_to(state), "state symlink escapes isolated state")
    return {"entries": len(snapshot["entries"]), "mutable_state_path_guards": "passed"}


def launcher_bytes(root: Path, manifest_sha: str, receipt_sha: str) -> bytes:
    python = root / "tools/python/data/data/com.termux/files/usr/bin/python3.14"
    helper = root / "staging/prepare_audio_device_environment.py"
    env_library = ":".join(str(root / name) for name in LIB_DIRS)
    command = " ".join(shlex.quote(str(value)) for value in (
        python, "-I", "-B", helper, "launch", "--root", root,
        "--manifest-sha256", manifest_sha, "--receipt-sha256", receipt_sha, "--"))
    text = ("#!" + PREFIX + "/bin/sh\n"
            "unset LD_PRELOAD LD_AUDIT LD_DEBUG PYTHONHOME PYTHONPATH VIRTUAL_ENV\n"
            "export LD_LIBRARY_PATH=" + shlex.quote(env_library) + "\n"
            "exec " + command + ' "$@"\n')
    return text.encode()


def verify_receipts(root: Path, *, manifest_sha: str | None = None,
                    receipt_sha: str | None = None) -> tuple[dict, dict]:
    manifest = load_bundle(root)
    actual_manifest_sha = bundle.file_digest(root / MANIFEST)
    actual_receipt_sha = bundle.file_digest(root / RECEIPT)
    if manifest_sha is not None:
        require(actual_manifest_sha == manifest_sha, "launcher bundle binding differs")
    if receipt_sha is not None:
        require(actual_receipt_sha == receipt_sha, "launcher assembly binding differs")
    receipt = bundle.read_json(root / RECEIPT)
    require(receipt.get("schema_version") == 1 and receipt.get("status") == "passed"
            and receipt.get("root") == str(root), "assembly receipt is incomplete or moved")
    require(receipt.get("bundle_manifest_sha256") == actual_manifest_sha,
            "assembly receipt bundle binding differs")
    require(receipt.get("versions") == expected_versions(manifest["lock"]),
            "assembly receipt inventory differs")
    for relative, key in ((ENVIRONMENT, "environment_manifest_sha256"), (VALIDATION, "native_validation_sha256")):
        require(bundle.file_digest(root / relative) == receipt.get(key), "assembly receipt evidence hash differs")
    require(receipt.get("claims") == claims(), "assembly receipt claims differ")
    snapshot = bundle.read_json(root / ENVIRONMENT)
    verify_generated_tree(root, snapshot)
    bindir = root / "bin"
    require(bindir.is_dir() and not bindir.is_symlink()
            and {path.name for path in bindir.iterdir()} == {"audio-python"}, "unexpected generated launcher")
    launcher = bindir / "audio-python"
    require(launcher.is_file() and not launcher.is_symlink()
            and launcher.read_bytes() == launcher_bytes(root, actual_manifest_sha, actual_receipt_sha),
            "launcher destination or receipt binding changed")
    if os.name != "nt":
        require(stat.S_IMODE(launcher.stat().st_mode) == 0o755, "launcher mode differs")
    return manifest, receipt


def claims() -> dict:
    return {"assembly_only": True, "device_readiness": False, "microphone_accessed": False,
            "recording_tested": False, "vad_tested": False, "candidate_published": False,
            "default_extras_changed": False, "ci_venv_copied": False}


def _clean_process(root: Path) -> dict[str, str]:
    env = runtime_environment(root, dict(os.environ))
    os.environ.clear()
    os.environ.update(env)
    return env


def helper_command(root: Path, phase: str, *, python: Path | None = None) -> list[str]:
    return [str(python or root / "venv/bin/python"), "-I", "-B",
            str(root / "staging/prepare_audio_device_environment.py"), phase, "--root", str(root)]


def run_child(root: Path, phase: str, *, python: Path | None = None, timeout: int = 180) -> dict:
    result = subprocess.run(helper_command(root, phase, python=python), env=runtime_environment(root, dict(os.environ)),
                            cwd=root / "state", capture_output=True, text=True, timeout=timeout, check=False)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    require(result.returncode == 0, f"{phase} failed with exit {result.returncode}: {result.stdout[-1200:]}")
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise StagingError("native child returned malformed JSON") from exc
    require(isinstance(value, dict), "native child must return one JSON object")
    return value


def _app_import_path(root: Path) -> None:
    sys.path.insert(0, str(root / "app"))


def assemble(root: Path) -> dict:
    manifest = load_bundle(root)
    lock = manifest["lock"]
    python = assert_native(root, lock)
    # Refuse every partial/prior assembly before claiming or modifying anything.
    for name in bundle.GENERATED_ROOTS:
        require(not (root / name).exists() and not (root / name).is_symlink(), "destination was already prepared")
    for name in bundle.GENERATED_FILES:
        if name == MANIFEST:
            continue
        require(not (root / name).exists() and not (root / name).is_symlink(), "destination has prior generated state")
    env = _clean_process(root)
    for relative in ("state", "state/profile", "state/cache", "state/cache/uv", "state/cache/pycache",
                     "state/config", "state/data", "state/local-state", "state/tmp"):
        (root / relative).mkdir()
    _app_import_path(root)
    from scripts.bundles.payload import record_tools, seal_pm_runtime, relativize_links
    from pm import stage_manager_runtime
    entries = {name: name for name in ("python", "uv", "node", "npm", "ffmpeg", "ripgrep")
               if (root / "tools" / name).is_dir()}
    require("python" in entries and "uv" in entries, "pinned manager tool inputs are missing")
    record_tools(root, root / "app/pm/lock.json", "linux-arm64-bionic", entries)
    manager = stage_manager_runtime(python=python, destination=root / "pm-runtime",
                                    project=root / "app/pm", wheelhouse=root / "wheelhouse",
                                    offline=True, cache=root / "state/cache/uv")
    # The application worker verifies generated links before it can import PM.
    # Seal interpreter link spelling now, even if UV left an absolute internal link.
    relativize_links(root)
    run_child(root, "_application", python=manager, timeout=600)
    add_source(root)
    add_audio_resolver(root, lock)
    seal_pm_runtime(root, python)
    # UV creates relocatable venv links; seal the remaining app links with the same audited helper.
    relativize_links(root)
    validation = run_child(root, "_validate", timeout=300)
    require(validation.get("status") == "passed", "native validation did not pass")
    write_json(root / VALIDATION, validation, exclusive=True)
    bundle.verify_manifest_tree(root, manifest, allow_generated=True)
    snapshot = environment_inventory(root)
    write_json(root / ENVIRONMENT, snapshot, exclusive=True)
    receipt = {
        "schema_version": 1, "status": "passed", "root": str(root),
        "bundle_manifest_sha256": bundle.file_digest(root / MANIFEST),
        "environment_manifest_sha256": bundle.file_digest(root / ENVIRONMENT),
        "native_validation_sha256": bundle.file_digest(root / VALIDATION),
        "candidate_run_id": lock["candidate"]["run_id"], "candidate_head_sha": lock["candidate"]["head_sha"],
        "versions": expected_versions(lock), "installed_distribution_count": 102,
        "wheelhouse_count": len(manifest["wheels"]), "manager_fresh": True,
        "owned_runtime_adapter": validation["audio_resolver"],
        "claims": claims(),
    }
    write_json(root / RECEIPT, receipt, exclusive=True)
    (root / "bin").mkdir()
    launcher = root / "bin/audio-python"
    launcher.write_bytes(launcher_bytes(root, receipt["bundle_manifest_sha256"], bundle.file_digest(root / RECEIPT)))
    launcher.chmod(0o755)
    verify_receipts(root)
    return receipt


def application(root: Path) -> dict:
    manifest = load_bundle(root)
    python = assert_native(root, manifest["lock"])
    _clean_process(root)
    _app_import_path(root)
    from pm import build_requirements_environment
    expected = expected_versions(manifest["lock"])
    requirements = [f"{name}=={version}" for name, version in sorted(expected.items()) if name != "hermes-agent"]
    build_requirements_environment(requirements, out=root / "venv", python=python,
                                   cache=root / "state/cache/uv", env=runtime_environment(root, dict(os.environ)),
                                   wheelhouse=root / "wheelhouse", offline=True, sealed=True, explicit=True)
    return {"status": "passed", "requirements_count": len(requirements)}


def verify_inventory(distributions: list, expected: dict[str, str], site: Path, app: Path | None = None) -> dict:
    found = {}
    for dist in distributions:
        name = normalized_name(dist.metadata["Name"])
        require(name not in found, "duplicate installed distribution identity: " + name)
        location = Path(dist.locate_file("")).resolve()
        expected_location = app if name == "hermes-agent" else site
        require(expected_location is not None and location == expected_location,
                "installed distribution resolved outside its declared root: " + name)
        found[name] = dist.version
    require(found == expected, "installed distribution inventory differs from frozen closure")
    return found


def dependency_graph(distributions: dict, expected: dict[str, str], extras: list[str]) -> list[dict]:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.version import Version
    from packaging.specifiers import SpecifierSet
    environment = default_environment()
    for name, dist in distributions.items():
        constraint = dist.metadata.get("Requires-Python")
        require(not constraint or Version(platform.python_version()) in SpecifierSet(constraint),
                "installed distribution Requires-Python conflict: " + name)
    active = {name: {""} for name in expected}
    if "hermes-agent" in active:
        active["hermes-agent"].update(extras)
    visited, edges = set(), {}
    while True:
        pending = sorted((name, extra) for name, values in active.items() for extra in values
                         if (name, extra) not in visited)
        if not pending:
            break
        for name, extra in pending:
            visited.add((name, extra))
            for text in distributions[name].requires or []:
                requirement = Requirement(text)
                if requirement.marker and not requirement.marker.evaluate({**environment, "extra": extra}):
                    continue
                dependency = normalized_name(requirement.name)
                require(requirement.url is None, "active direct-URL dependency is outside the frozen wheel closure")
                require(dependency in expected, "missing active dependency: " + dependency)
                require(Version(expected[dependency]) in requirement.specifier,
                        "frozen dependency version conflict: " + text)
                active[dependency].update(requirement.extras)
                edges[(name, text)] = {"parent": name, "requirement": text, "selected": expected[dependency]}
    return [edges[key] for key in sorted(edges)]


def installed_wheel(root: Path, wheel_row: dict, *, environment: str = "venv") -> dict:
    path = root / wheel_row["file"]
    bundle.verify_file(path, wheel_row, "frozen wheel")
    venv = root / environment
    site = venv / SITE
    checked = 0
    original_targets = set()
    with zipfile.ZipFile(path) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in infos]
        require(len(names) == len(set(names)), "duplicate wheel member")
        metadata_names = [name for name in names if name.count("/") == 1 and name.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "ambiguous wheel metadata")
        prefix = metadata_names[0].rsplit("/", 1)[0]
        record_name, wheel_name = prefix + "/RECORD", prefix + "/WHEEL"
        original_records = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
        require(all(len(row) == 3 for row in original_records)
                and len(original_records) == len(names) and {row[0] for row in original_records} == set(names),
                "wheel RECORD does not cover original members exactly")
        records = {row[0]: row[1:] for row in original_records}
        for item in infos:
            relative = bundle.safe_relative_path(item.filename)
            content = archive.read(item)
            encoded, size = records[item.filename]
            if item.filename == record_name:
                require(encoded == size == "", "invalid wheel RECORD self-entry")
                continue
            require(encoded == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
                    and size == str(len(content)), "wheel RECORD content hash differs")
            parts = relative.parts
            script = False
            if parts[0].endswith(".data"):
                require(len(parts) >= 3, "invalid wheel data scheme")
                scheme = parts[1]
                if scheme in ("purelib", "platlib"):
                    target = site.joinpath(*parts[2:])
                elif scheme == "scripts":
                    target, script = venv.joinpath("bin", *parts[2:]), True
                elif scheme == "data":
                    target = venv.joinpath(*parts[2:])
                else:
                    raise StagingError("unsupported wheel installation scheme: " + scheme)
            else:
                target = site.joinpath(*parts)
            inside(venv, target, "installed wheel member")
            require(target.is_file() and not target.is_symlink(), "installed wheel member missing: " + item.filename)
            require(target.resolve() not in original_targets, "wheel members collide after installation mapping")
            original_targets.add(target.resolve())
            installed = target.read_bytes()
            if installed != content:
                require(script and content.startswith((b"#!python\n", b"#!pythonw\n"))
                        and installed.startswith(b"#!") and installed.split(b"\n", 1)[1] == content.split(b"\n", 1)[1],
                        "installed wheel bytes differ: " + item.filename)
            checked += 1
        installed_record = inside(venv, site / record_name, "installed RECORD")
        require(installed_record.is_file() and not installed_record.is_symlink(), "installed RECORD must be a regular file")
        rows = list(csv.reader(io.StringIO(installed_record.read_text())))
        require(all(len(row) == 3 for row in rows) and len({row[0] for row in rows}) == len(rows),
                "installed RECORD is malformed or duplicated")
        installed_targets = set()
        for name, encoded, size in rows:
            require(name and not Path(name).is_absolute() and "\\" not in name and "\x00" not in name,
                    "unsafe installed RECORD path")
            target = inside(venv, site / name, "installed RECORD")
            require(target.is_file() and not target.is_symlink(), "installed RECORD member missing")
            require(target.resolve() not in installed_targets, "duplicate resolved installed RECORD target")
            installed_targets.add(target.resolve())
            if target.resolve() == installed_record.resolve():
                require(encoded == size == "", "installed RECORD self-entry must be unhashed")
                continue
            require(encoded.startswith("sha256=") and size == str(target.stat().st_size),
                    "installed RECORD digest or size absent")
            actual = base64.urlsafe_b64encode(bytes.fromhex(bundle.file_digest(target))).rstrip(b"=").decode()
            require(encoded == "sha256=" + actual, "installed RECORD content differs")
        require(original_targets | {installed_record.resolve()} <= installed_targets,
                "installed RECORD omits an original wheel member or its self-entry")
        # These original identity files are checked byte for byte above, not retagged after installation.
        return {"name": wheel_row["name"], "version": wheel_row["version"], "wheel_sha256": wheel_row["sha256"],
                "installed_member_count": checked, "installed_record_count": len(rows),
                "installed_record_sha256": bundle.file_digest(installed_record),
                "wheel_metadata_sha256": bundle.file_digest(site / wheel_name),
                "metadata_sha256": bundle.file_digest(site / metadata_names[0])}


def module_origin(root: Path, module) -> dict:
    value = getattr(module, "__file__", None)
    require(isinstance(value, str), "imported module has no attributable file")
    path = Path(value).resolve()
    require(path.is_file() and (path.is_relative_to(root / "venv")
                               or path.is_relative_to(root / "app")), "module came from ambient installation")
    return {"module": module.__name__, "path": path.relative_to(root).as_posix(),
            "sha256": bundle.file_digest(path)}


def mapped_libraries(root: Path, lock: dict) -> dict:
    maps = Path("/proc/self/maps")
    require(maps.is_file(), "native mapped-library evidence is unavailable")
    paths = sorted({line.split(maxsplit=5)[5].strip() for line in maps.read_text().splitlines()
                    if len(line.split(maxsplit=5)) == 6 and line.split(maxsplit=5)[5].startswith("/")
                    and ".so" in line.split(maxsplit=5)[5]})
    origins = []
    for spelling in paths:
        require(not spelling.endswith(" (deleted)"), "deleted native library mapping")
        path = Path(spelling).resolve()
        if path.is_relative_to(root):
            require(path.is_file(), "mapped payload library missing")
            origins.append({"scope": "payload", "path": path.relative_to(root).as_posix(),
                            "sha256": bundle.file_digest(path)})
        else:
            allowed = (lock["external_runtime_policy"]["allowed_system_roots"]
                       + lock["external_runtime_policy"]["container_bionic_roots"])
            require(any(path.is_relative_to(Path(prefix).resolve()) for prefix in allowed),
                    "native library resolved from an undeclared ambient directory: " + str(path))
            origins.append({"scope": "platform", "path": str(path), "sha256": bundle.file_digest(path)})
    require(any(row["scope"] == "payload" for row in origins), "no payload native library mapping recorded")
    return {"origins": origins, "ambient_termux_library_directory_used": False}


def native_validation(root: Path) -> dict:
    manifest = load_bundle(root)
    lock = manifest["lock"]
    assert_native(root, lock, application=True)
    _clean_process(root)
    site = app_site(root)
    require((site / "hermes-agent.pth").read_bytes() == source_pth(root), "source-layout PTH differs")
    resolver = verify_audio_resolver(root, lock)
    expected = expected_versions(lock)
    distributions = list(metadata.distributions())
    versions = verify_inventory(distributions, expected, site, root / "app")
    selected = {normalized_name(dist.metadata["Name"]): dist for dist in distributions}
    rows = manifest["wheels"]
    require(len(rows) == 102 and len({row["name"] for row in rows}) == 102, "combined wheel catalog differs")
    by_name = {row["name"]: row for row in rows}
    require(set(by_name) == (set(expected) - {"hermes-agent"}) | {"setuptools"},
            "wheel catalog has a missing or unexpected dependency")
    wheels = [installed_wheel(root, by_name[name]) for name in sorted(expected) if name != "hermes-agent"]
    graph = dependency_graph(selected, expected, lock["candidate"]["extras"] + ["audio-io"])
    import pm
    import cffi
    import _cffi_backend
    import numpy as np
    import numpy._core._multiarray_umath as numpy_native
    import pydantic_core
    import cryptography.hazmat.bindings._rust as crypto_native
    import uvloop
    import psutil
    ffi = cffi.FFI()
    integers = ffi.new("int[]", [3, 5, 8])
    require(sum(integers) == 16, "real CFFI allocation/operation failed")
    values = np.arange(12, dtype=np.float64).reshape(3, 4)
    result = (values @ values.T).tolist()
    require(result == [[14.0, 38.0, 62.0], [38.0, 126.0, 214.0], [62.0, 214.0, 366.0]],
            "real NumPy numerical operation failed")
    require(bool(np.isfinite(np.linalg.svd(values, compute_uv=False)).all()), "NumPy linalg returned nonfinite values")
    require(pm.available("audio-io"), "prepared audio metadata/import anchors are unavailable")
    source_origins = []
    for name in ("pm", "tools.voice_mode", "tools.voice_mode_capture", "tools.transcription_tools"):
        spec = importlib.util.find_spec(name)
        require(spec is not None and isinstance(spec.origin, str), "pinned application module is missing")
        origin = Path(spec.origin).resolve()
        require(origin.is_file() and origin.is_relative_to(root / "app"),
                "application module resolved outside patched source: " + name)
        source_origins.append({"module": name, "path": origin.relative_to(root).as_posix(),
                               "sha256": bundle.file_digest(origin)})
    modules = [module_origin(root, module) for module in
               (pm, cffi, _cffi_backend, np, numpy_native, pydantic_core, crypto_native, uvloop, psutil)]
    from pm.runtime import runtime_command, runtime_environment as manager_environment
    command = runtime_command(root / "staging/prepare_audio_device_environment.py",
                              ["_manager", "--root", str(root)], bootstrap=False)
    manager_result = subprocess.run(command, env=manager_environment(), cwd=root / "state",
                                    capture_output=True, text=True, timeout=120, check=False)
    require(manager_result.returncode == 0, "fresh sealed PM runtime validation failed: " + manager_result.stderr[-1200:])
    manager = json.loads(manager_result.stdout)
    require(manager.get("status") == "passed", "fresh PM result is not successful")
    bundle.verify_manifest_tree(root, manifest, allow_generated=True)
    return {"schema_version": 1, "status": "passed", "root": str(root),
            "bundle_manifest_sha256": bundle.file_digest(root / MANIFEST),
            "versions": versions, "installed_distribution_count": len(versions), "installed_wheels": wheels,
            "source_layout": {"path": "app", "metadata": "hermes-agent==0.0.0", "pth": source_pth(root).decode()},
            "active_extras": lock["candidate"]["extras"] + ["audio-io"],
            "active_dependency_edges": graph, "module_origins": modules,
            "application_source_origins": source_origins, "manager": manager,
            "native_operations": {"cffi_sum": 16, "numpy_matrix_product": result, "numpy_linalg_finite": True},
            "audio_available_metadata_only": True, "audio_resolver": resolver,
            "native_libraries": mapped_libraries(root, lock), "claims": claims()}


def manager_validation(root: Path) -> dict:
    manifest = load_bundle(root)
    assert_native(root, manifest["lock"])
    _clean_process(root)
    _app_import_path(root)
    site = root / "pm-runtime" / SITE
    require(str(site) in sys.path and sys.flags.no_site == 1, "manager did not use its sealed site directory")
    import packaging
    import tomli_w
    import truststore
    import ruamel.yaml
    import pm
    require(Path(pm.__file__).resolve().is_relative_to(root / "app/pm"), "manager PM source is not pinned app source")
    for module in (packaging, tomli_w, truststore, ruamel.yaml):
        require(Path(module.__file__).resolve().is_relative_to(site), "manager dependency import escaped private site")
    distributions = list(metadata.distributions(path=[str(site)]))
    by_name = {row["name"]: row for row in manifest["wheels"]}
    expected = {normalized_name(dist.metadata["Name"]): by_name[normalized_name(dist.metadata["Name"])]["version"]
                for dist in distributions}
    verify_inventory(distributions, expected, site)
    require(set(expected) == {"packaging", "tomli-w", "truststore", "ruamel-yaml"},
            "private PM dependency closure differs")
    wheels = [installed_wheel(root, by_name[name], environment="pm-runtime") for name in sorted(expected)]
    graph = dependency_graph({normalized_name(dist.metadata["Name"]): dist for dist in distributions}, expected, [])
    return {"status": "passed", "site": "pm-runtime/" + SITE, "versions": expected,
            "source": "app/pm", "installed_wheels": wheels, "active_dependency_edges": graph}


def audio_input_inventory(sd) -> dict:
    """Inspect device descriptions and format support without opening a stream."""
    devices = sd.query_devices()
    require(isinstance(devices, (list, tuple)), "audio device inventory is not a sequence")
    rows = []
    for index, device in enumerate(devices):
        require(isinstance(device, dict), "audio device row is invalid")
        channels = device.get("max_input_channels")
        rate = device.get("default_samplerate")
        require(isinstance(channels, numbers.Integral) and not isinstance(channels, bool) and channels >= 0,
                "audio input channel count is invalid")
        require(isinstance(rate, numbers.Real) and not isinstance(rate, bool) and math.isfinite(rate) and rate > 0,
                "audio default sample rate is invalid or nonfinite")
        name = device.get("name")
        require(isinstance(name, str), "audio device name is invalid")
        rows.append({"index": index, "name": name, "max_input_channels": int(channels),
                     "default_samplerate": float(rate)})
    default = sd.default.device
    require(len(default) == 2 and isinstance(default[0], numbers.Integral)
            and not isinstance(default[0], bool) and -1 <= default[0] < len(rows),
            "default input device index is invalid")
    index = int(default[0])
    report = {"devices": rows, "default_input_device": index, "supported_input_formats": [],
              "input_device_status": "unavailable"}
    if index < 0 or rows[index]["max_input_channels"] < 1:
        return report
    supported = []
    for rate in sorted({16000.0, rows[index]["default_samplerate"]}):
        try:
            sd.check_input_settings(device=index, channels=1, dtype="int16", samplerate=rate)
        except Exception as exc:
            codes = [arg for arg in exc.args if type(arg) is int and arg in {-9998, -9997, -9994}]
            require(type(exc).__name__ == "PortAudioError" and len(codes) == 1,
                    "unexpected input-format inventory failure")
            supported.append({"samplerate": rate, "channels": 1, "dtype": "int16",
                              "status": "unsupported", "portaudio_code": codes[0]})
        else:
            supported.append({"samplerate": rate, "channels": 1, "dtype": "int16", "status": "supported"})
    report["supported_input_formats"] = supported
    report["input_device_status"] = "available" if any(row["status"] == "supported" for row in supported) else "unsupported"
    return report


def diagnose_native(root: Path) -> dict:
    manifest = load_bundle(root)
    assert_native(root, manifest["lock"], application=True)
    _clean_process(root)
    report = {"schema_version": 1, "root": str(root), "status": "failed", "protocol_valid": False,
              "bundle_manifest_sha256": bundle.file_digest(root / MANIFEST),
              "assembly_receipt_sha256": bundle.file_digest(root / RECEIPT),
              "readiness": False, "device_readiness": False, "microphone_accessed": False,
              "recording_tested": False, "vad_tested": False, "device_stream_opened": False}
    try:
        report["audio_resolver"] = verify_audio_resolver(root, manifest["lock"])
        from tools.voice_mode_capture import AudioInitializationError, import_audio_modules
        try:
            sd, np = import_audio_modules()
        except AudioInitializationError as exc:
            cause = exc.__cause__
            require(cause is not None and type(cause).__name__ == "PortAudioError"
                    and any(type(arg) is int and arg == -9999 for arg in cause.args)
                    and "PortAudio" in str(cause), "unexpected audio initialization failure")
            report.update(status="audio-unavailable", protocol_valid=True,
                          expected_portaudio_failure=True, input_device_status="initialization-unavailable",
                          error={"type": type(exc).__name__, "message": str(exc),
                                 "cause_type": type(cause).__name__, "cause_message": str(cause),
                                 "portaudio_code": -9999})
        else:
            report.update(status="audio-initialized", protocol_valid=True, expected_portaudio_failure=False,
                          audio_modules=[module_origin(root, sd), module_origin(root, np)])
            report.update(audio_input_inventory(sd))
        report["native_libraries"] = mapped_libraries(root, manifest["lock"])
        libraries = report["native_libraries"]["origins"]
        require(any(row["scope"] == "payload" and "libportaudio.so" in row["path"]
                    and row["sha256"] == manifest["lock"]["audio"]["portaudio"]["sha256"]
                    for row in libraries), "initialized PortAudio did not map the pinned payload library")
        system_framework = [row for row in libraries
                            if row["scope"] == "platform" and Path(row["path"]).name == "libOpenSLES.so"]
        report["framework_input"] = {"provides_real_android_framework": False,
                                     "role": "forwarder to the real Android framework",
                                     "package": manifest["lock"]["opensles"]["package"],
                                     "sha256": manifest["lock"]["opensles"]["sha256"],
                                     "real_android_framework_mapped": bool(system_framework),
                                     "system_framework_libraries": system_framework}
    except Exception as exc:
        report.update(status="failed", protocol_valid=False,
                      error={"type": type(exc).__name__, "message": str(exc)})
    return report


def validate(root: Path) -> dict:
    manifest, receipt = verify_receipts(root)
    assert_native(root, manifest["lock"])
    _clean_process(root)
    result = run_child(root, "_validate", timeout=300)
    encoded = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()
    require(hashlib.sha256(encoded).hexdigest() == receipt["native_validation_sha256"],
            "fresh native validation differs from the original verified environment")
    return result


def diagnose(root: Path) -> dict:
    manifest, _ = verify_receipts(root)
    assert_native(root, manifest["lock"])
    _clean_process(root)
    try:
        report = run_child(root, "_diagnose", timeout=60)
    except Exception as exc:
        report = {"schema_version": 1, "root": str(root), "status": "failed", "protocol_valid": False,
                  "bundle_manifest_sha256": bundle.file_digest(root / MANIFEST),
                  "assembly_receipt_sha256": bundle.file_digest(root / RECEIPT),
                  "readiness": False, "device_readiness": False, "microphone_accessed": False,
                  "recording_tested": False, "vad_tested": False, "device_stream_opened": False,
                  "error": {"type": type(exc).__name__, "message": str(exc)}}
    write_json(root / DIAGNOSTIC, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("assemble", "validate", "diagnose", "launch",
                                         "_application", "_validate", "_manager", "_diagnose"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--receipt-sha256")
    args, remainder = parser.parse_known_args(argv)
    root = root_path(args.root)
    if args.phase != "launch":
        require(not remainder and args.manifest_sha256 is None and args.receipt_sha256 is None,
                "unexpected helper arguments")
    if args.phase == "launch":
        require(args.manifest_sha256 and args.receipt_sha256 and remainder[:1] == ["--"],
                "launch requires its frozen launcher bindings")
        manifest, _ = verify_receipts(root, manifest_sha=args.manifest_sha256, receipt_sha=args.receipt_sha256)
        assert_native(root, manifest["lock"])
        env = runtime_environment(root, dict(os.environ))
        os.execve(root / "venv/bin/python",
                  [str(root / "venv/bin/python"), "-I", "-B", *remainder[1:]], env)
        raise AssertionError("execve returned")
    actions = {"assemble": assemble, "validate": validate, "diagnose": diagnose,
               "_application": application, "_validate": native_validation,
               "_manager": manager_validation, "_diagnose": diagnose_native}
    result = actions[args.phase](root)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0 if args.phase != "diagnose" or result.get("protocol_valid") is True else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StagingError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"schema_version": 1, "status": "failed",
                          "error": {"type": type(exc).__name__, "message": str(exc)}}), file=sys.stderr)
        raise SystemExit(2)
