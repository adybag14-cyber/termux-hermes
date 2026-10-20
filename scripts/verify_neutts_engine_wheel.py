#!/usr/bin/env python3
"""Strict source, nested compiler and built-wheel checks for the isolated NeuTTS experiment."""
from __future__ import annotations

import base64
import csv
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import struct
import zipfile


class EngineWheelError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise EngineWheelError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def one(message, field):
    values = message.get_all(field, [])
    require(len(values) == 1, "Missing or duplicate metadata field: " + field)
    return values[0]


def packaging_api():
    # The native parent verifies this exact APT pip distribution and its files
    # before checking the built wheel; the three-wheel build child uses its own
    # byte-verified packaging wheel through prepare.build_graph instead.
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    from pip._vendor.packaging.version import Version
    return Requirement, SpecifierSet, canonicalize_name, parse_wheel_filename, Version


def expected_requirements(project):
    requirement, *_ = packaging_api()
    values = [str(requirement(text)) for text in project["dependencies"]]
    for extra, requirements in project["optional-dependencies"].items():
        for text in requirements:
            values.append(str(requirement(text + '; extra == "' + extra + '"')))
    return sorted(values)


def verify_metadata(raw, project, readme):
    Requirement, SpecifierSet, normalize, _, Version = packaging_api()
    metadata = BytesParser(policy=compat32).parsebytes(raw)
    require(normalize(one(metadata, "Name")) == project["name"]
            and one(metadata, "Version") == project["version"], "NeuTTS metadata identity changed")
    actual_python = one(metadata, "Requires-Python")
    require(SpecifierSet(actual_python) == SpecifierSet(project["requires-python"]),
            "Original NeuTTS Python bound changed")
    require(Version("3.14.6") not in SpecifierSet(actual_python),
            "A build-only wheel must still exclude Python 3.14 under the original bound")
    actual = sorted(str(Requirement(text)) for text in metadata.get_all("Requires-Dist", []))
    require(actual == expected_requirements(project), "NeuTTS base or optional dependency metadata changed")
    require(sorted(metadata.get_all("Provides-Extra", [])) == sorted(project["optional-dependencies"]),
            "NeuTTS optional dependency groups changed")
    require(one(metadata, "Summary") == project["description"], "NeuTTS description changed")
    require(one(metadata, "Author-Email") == "neuphonic <general@neuphonic.com>",
            "Original author metadata changed")
    require(one(metadata, "Description-Content-Type") == "text/markdown",
            "Original README content type changed")
    _, separator, body = raw.replace(b"\r\n", b"\n").partition(b"\n\n")
    require(separator and body == readme.replace(b"\r\n", b"\n"),
            "Original README metadata payload changed")
    return {"name": project["name"], "version": project["version"], "metadata_sha256": digest(raw),
            "requires_python": actual_python, "requires_python_excludes_current_314": True,
            "all_declared_requirements": metadata.get_all("Requires-Dist", []),
            "all_extras": metadata.get_all("Provides-Extra", []),
            "engine_install_admitted": False}


def cache_values(raw):
    values = {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith(("//", "#")):
            continue
        match = re.fullmatch(r"([^:=]+):[^=]+=(.*)", line)
        require(match is not None, "Unrecognized CMake cache row")
        name, value = match.groups()
        require(name not in values, "Duplicate CMake cache key")
        values[name] = value
    return values


def check_portable_flags(argv, *, require_source_flags=False, include_path=None):
    require("--target=aarch64-linux-android24" in argv and "-march=armv8-a" in argv,
            "A compile command lost the Android API24/ARMv8 target")
    targets = [t for t in argv if t.startswith(("--target", "-target"))]
    arches = [t for t in argv if t.startswith(("-march", "-mcpu"))]
    require(targets == ["--target=aarch64-linux-android24"] and arches == ["-march=armv8-a"],
            "Conflicting or unreviewed target/CPU flags")
    require(not any(t.startswith("@") for t in argv), "Unreviewed compiler response file")
    require("-fPIC" in argv, "A native command lost position-independent code")
    if require_source_flags:
        require("-D_FILE_OFFSET_BITS=64" in argv and "-I" + str(include_path) in argv,
                "The original nested eSpeak flags were lost")


def verify_compile_commands(commands, source, build, compilers):
    require(isinstance(commands, list) and commands, "No actual nested compile commands")
    rows, seen = [], set()
    source, build = Path(source).resolve(), Path(build).resolve()
    expected = {Path(p).resolve() for p in compilers}
    include = source / "src/ucd-tools/src/include"
    for row in commands:
        require(isinstance(row, dict) and set(row) <= {"directory", "file", "command", "arguments", "output"},
                "Malformed compile-command row")
        require("directory" in row and "file" in row and (("command" in row) != ("arguments" in row)),
                "Compile command must contain one explicit argument representation")
        directory = Path(row["directory"]).resolve()
        require(directory.is_relative_to(build), "Compiler working directory escaped the nested build")
        file = Path(row["file"])
        file = (file if file.is_absolute() else directory / file).resolve()
        require(file.is_relative_to(source) or file.is_relative_to(build),
                "Compiler source is outside the exact source/build")
        argv = row["arguments"] if "arguments" in row else shlex.split(row["command"], posix=True)
        require(isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv),
                "Invalid compiler argument vector")
        compiler = Path(argv[0])
        require(compiler.is_absolute() and compiler.resolve() in expected,
                "Actual nested compiler differs from the pinned parent compiler")
        check_portable_flags(argv, require_source_flags=True, include_path=include)
        identity = (str(directory), str(file), row.get("output", ""), tuple(argv))
        require(identity not in seen, "Duplicate nested compile-command entry")
        seen.add(identity)
        rows.append({"file": str(file), "compiler": str(compiler),
                     "target": "aarch64-linux-android24", "architecture": "armv8-a",
                     "argv_sha256": digest(canonical(argv))})
    require(any(Path(r["file"]) == source / "src/libespeak-ng/speech.c" for r in rows),
            "The actual eSpeak speech library compilation is missing")
    return {"status": "passed", "compile_commands": len(rows),
            "every_command_api24_armv8_checked": True, "commands": rows}


def verify_cmake(parent_raw, nested_raw, parent_system, nested_system, commands, lock, engine_source, espeak_source, build):
    parent, nested = cache_values(parent_raw), cache_values(nested_raw)
    prefix = Path("/data/data/com.termux/files/usr")
    compilers = [prefix / "bin/clang", prefix / "bin/clang++"]
    for key, path in zip(("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER"), compilers):
        for cache in (parent, nested):
            require(Path(cache.get(key, "")).is_absolute()
                    and Path(cache[key]).resolve() == path.resolve(), "Nested compiler identity changed: " + key)
    flags = lock["build"]["cflags"]
    nested_flags = flags + " -D_FILE_OFFSET_BITS=64 -I" + str(Path(espeak_source) / "src/ucd-tools/src/include")
    for key in ("CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS"):
        require(parent.get(key) == flags and nested.get(key) == nested_flags,
                "The original common/target flags were not propagated: " + key)
    for key in ("CMAKE_EXE_LINKER_FLAGS", "CMAKE_SHARED_LINKER_FLAGS", "CMAKE_MODULE_LINKER_FLAGS"):
        require(parent.get(key) == lock["build"]["ldflags"] and nested.get(key) == parent[key],
                "Nested linker settings differ from parent: " + key)
    # The pinned native CMake Android initializer selects RelWithDebInfo.
    # NeuTTS does not pass a nested build-type override; do not impose one.
    require(parent.get("CMAKE_BUILD_TYPE") == lock["build"]["parent_cmake_build_type"]
            and nested.get("CMAKE_BUILD_TYPE") == lock["build"]["nested_cmake_build_type"],
            "The original parent or pinned native nested build-type default changed")
    require(parent.get("CMAKE_EXPORT_COMPILE_COMMANDS") == nested.get("CMAKE_EXPORT_COMPILE_COMMANDS") == "ON",
            "Actual nested compile-command export was disabled")
    require(Path(parent.get("CMAKE_HOME_DIRECTORY", "")).resolve() == Path(engine_source).resolve()
            and Path(nested.get("CMAKE_HOME_DIRECTORY", "")).resolve() == Path(espeak_source).resolve(),
            "CMake configured an unexpected source tree")
    for system in (parent_system, nested_system):
        require(b'set(CMAKE_CROSSCOMPILING "FALSE")' in system,
                "Both levels must use actual native CMake builds for language-data generation")
    for name, value in {"BUILD_SHARED_LIBS": "ON", "CMAKE_POSITION_INDEPENDENT_CODE": "ON",
                        "USE_ASYNC": "OFF", "USE_MBROLA": "OFF", "USE_LIBSONIC": "OFF",
                        "USE_LIBPCAUDIO": "OFF", "USE_KLATT": "OFF", "USE_SPEECHPLAYER": "OFF",
                        "EXTRA_cmn": "ON", "EXTRA_ru": "ON", "COMPILE_INTONATIONS": "ON"}.items():
        require(nested.get(name) == value, "Original NeuTTS eSpeak option changed: " + name)
    result = verify_compile_commands(commands, espeak_source, build, compilers)
    result.update(parent_cache_sha256=digest(parent_raw), nested_cache_sha256=digest(nested_raw),
                  parent_system_sha256=digest(parent_system), nested_system_sha256=digest(nested_system),
                  parent_build_type=parent["CMAKE_BUILD_TYPE"], nested_build_type=nested.get("CMAKE_BUILD_TYPE", ""),
                  nested_common_flags=nested_flags, recorded_compile_commands_verified=True)
    return result


def verify_original_source_files(root, rows):
    """Check all original files after building; report generated additions separately."""
    root = Path(root)
    wanted = {r["path"] for r in rows}
    require(len(wanted) == len(rows), "Duplicate original source manifest entry")
    for row in rows:
        path = root / row["path"]
        if row["mode"] == "120000":
            require(path.is_symlink(), "Original source symlink changed")
            raw = path.readlink().as_posix().encode()
        else:
            require(path.is_file() and not path.is_symlink(), "Original source file disappeared")
            raw = path.read_bytes()
        require(len(raw) == row["size"] and digest(raw) == row["sha256"],
                "An original source file changed during the build: " + row["path"])
    generated = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        if name in wanted:
            continue
        require(path.is_file() and not path.is_symlink(), "Generated source-tree special file")
        raw = path.read_bytes()
        generated.append({"path": name, "bytes": len(raw), "sha256": digest(raw)})
    return {"original_files": len(rows), "original_bytes_preserved": True,
            "generated_source_tree_files": generated}


def verify_data_tree(data, source):
    data, source = Path(data), Path(source)
    text = (source / "cmake/data.cmake").read_text("utf-8")
    found = re.findall(r"list\(APPEND _dict_compile_list\s+(.*?)\)", text, re.S)
    require(len(found) == 1, "Ambiguous original eSpeak dictionary list")
    dictionaries = found[0].split()
    require(dictionaries and len(dictionaries) == len(set(dictionaries)), "Invalid original dictionary list")
    for name in [*(language + "_dict" for language in dictionaries), "intonations", "phondata", "phonindex", "phontab"]:
        path = data / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
                "Missing generated eSpeak data: " + name)
    for subtree in ("lang", "voices/!v"):
        originals = list((source / "espeak-ng-data" / subtree).rglob("*"))
        require(originals, "Original voice/language source tree is absent")
        for path in originals:
            if path.is_file():
                target = data / path.relative_to(source / "espeak-ng-data")
                require(target.is_file() and not target.is_symlink() and target.read_bytes() == path.read_bytes(),
                        "Original eSpeak voice/language bytes changed")
    rows = []
    for path in sorted(data.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        require(stat.S_ISREG(path.lstat().st_mode), "Nonregular generated language-data member")
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(data).as_posix(), "bytes": len(raw), "sha256": digest(raw)})
    return {"file_count": len(rows), "bytes": sum(r["bytes"] for r in rows),
            "dictionary_count": len(dictionaries), "manifest_sha256": digest(canonical(rows)), "files": rows}


def verify_built_wheel(path, lock, source, nested_install, data_manifest, safe_member, supported_tags, destination=None):
    _, _, normalize, parse_filename, _ = packaging_api()
    path, source, nested_install = Path(path), Path(source), Path(nested_install)
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size < lock["build"]["wheel_size_limit_bytes"], "Invalid or oversized built wheel")
    name, version, build, tags = parse_filename(path.name)
    tag = lock["build"]["expected_built_tag"]
    require(normalize(name) == "neutts" and str(version) == lock["engine_source"]["project"]["version"]
            and not build and {str(t) for t in tags} == {tag} and tag in supported_tags,
            "Built wheel does not carry the genuine supported native Android tag")
    expected = {r["wheel_path"]: {"bytes": r["bytes"], "sha256": r["sha256"], "origin": r["source_path"]}
                for r in lock["engine_source"]["required_wheel_source_members"]}
    libraries = {}
    for name in lock["espeak"]["library_names"]:
        library = nested_install / "lib" / name
        resolved = library.resolve(strict=True)
        require(resolved.is_relative_to(nested_install.resolve()) and resolved.is_file(),
                "Nested installed eSpeak library link escaped or is missing")
        raw = resolved.read_bytes()
        libraries["neutts/" + name] = {"bytes": len(raw), "sha256": digest(raw)}
    require(len({r["sha256"] for r in libraries.values()}) == 1,
            "Nested installed eSpeak library aliases differ")
    expected.update({name: {**pin, "origin": "actual-nested-eSpeak-install"} for name, pin in libraries.items()})
    expected.update({"neutts/espeak-ng-data/" + row["path"]:
                    {"bytes": row["bytes"], "sha256": row["sha256"], "origin": "actual-nested-language-data"}
                    for row in data_manifest["files"]})
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        require(len(names) == len(set(names)) and len(entries) < 10000
                and sum(i.file_size for i in entries) < lock["build"]["wheel_uncompressed_limit_bytes"],
                "Duplicate or oversized built-wheel inventory")
        for item in entries:
            safe_member(item)
        meta_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        require(len(meta_names) == 1 and meta_names[0] == "neutts-1.4.1.dist-info/METADATA",
                "Ambiguous or wrong wheel distribution")
        metadata_name = meta_names[0]
        prefix = metadata_name.rsplit("/", 1)[0]
        wheel_name, record_name = prefix + "/WHEEL", prefix + "/RECORD"
        metadata = verify_metadata(archive.read(metadata_name), lock["engine_source"]["project"],
                                   (source / "README.md").read_bytes())
        wheel = BytesParser(policy=compat32).parsebytes(archive.read(wheel_name))
        require(one(wheel, "Wheel-Version") == "1.0" and one(wheel, "Root-Is-Purelib") == "false"
                and wheel.get_all("Tag", []) == [tag], "Built WHEEL metadata changed native platform identity")
        generator = one(wheel, "Generator")
        require(generator == "scikit-build-core 1.1.1", "Unreviewed wheel backend generator")
        hashes, sizes, native = {}, {}, {}
        license_rows = []
        for item in entries:
            if item.is_dir():
                continue
            raw = archive.read(item)
            hashes[item.filename], sizes[item.filename] = digest(raw), len(raw)
            if item.filename in expected:
                pin = expected[item.filename]
                require(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"],
                        "Wheel source/install member differs: " + item.filename)
            elif item.filename in {metadata_name, wheel_name, record_name}:
                pass
            elif item.filename.startswith(prefix + "/licenses/"):
                relative = item.filename.removeprefix(prefix + "/licenses/")
                original = source.joinpath(*PurePosixPath(relative).parts)
                require(original.is_file() and not original.is_symlink()
                        and original.resolve().is_relative_to(source.resolve())
                        and original.read_bytes() == raw, "Wheel license is not an exact original source asset")
                license_rows.append({"path": item.filename, "source": relative, "sha256": digest(raw)})
            else:
                raise EngineWheelError("Unexpected wheel payload member: " + item.filename)
            if item.filename.endswith((".so", ".pyd", ".dll", ".dylib")) or ".so." in item.filename:
                require(item.filename in libraries and len(raw) >= 64 and raw[:6] == b"\x7fELF\x02\x01"
                        and struct.unpack_from("<H", raw, 18)[0] == 183,
                        "Foreign or unexpected native library in wheel")
                native[item.filename] = {"bytes": len(raw), "sha256": digest(raw), "class": 64, "machine": 183}
        require(set(expected) <= set(hashes) and set(native) == set(libraries),
                "The built wheel omits original sources/references or actual eSpeak install output")
        expected_licenses = {
            p.relative_to(source).as_posix()
            for pattern in ("LICEN[CS]E*", "COPYING*", "NOTICE*", "AUTHORS*")
            for p in source.glob(pattern) if p.is_file() and not p.is_symlink()
        }
        require("LICENSE" in expected_licenses
                and {r["source"] for r in license_rows} == expected_licenses,
                "The built wheel omits an original backend-selected license asset")
        records = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
        require(all(len(row) == 3 for row in records) and len(records) == len(hashes)
                and len({row[0] for row in records}) == len(records)
                and {row[0] for row in records} == set(hashes), "RECORD does not cover every wheel file exactly once")
        for name, encoded, size in records:
            if name == record_name:
                require(encoded == size == "", "Invalid RECORD self-entry")
            else:
                require(encoded == "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(hashes[name])).decode().rstrip("=")
                        and size == str(sizes[name]), "Built wheel RECORD member hash differs")
        if destination is not None:
            destination = Path(destination)
            require(not destination.exists() and not destination.is_symlink(), "Fresh wheel inspection directory required")
            destination.mkdir(parents=True)
            for item in entries:
                if item.is_dir():
                    continue
                target = destination.joinpath(*PurePosixPath(item.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(archive.read(item))
                target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)
                require(target.stat().st_size == sizes[item.filename]
                        and digest(target.read_bytes()) == hashes[item.filename], "Inspected wheel copy changed")
    return {"status": "passed", "filename": path.name, "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()), "tag": tag, "metadata": metadata,
            "wheel_metadata_sha256": hashes[wheel_name], "record_sha256": hashes[record_name],
            "all_member_crc_record_hashes_checked": True, "file_count": len(hashes),
            "source_members_preserved": len(lock["engine_source"]["required_wheel_source_members"]),
            "native_members": native, "data_manifest_sha256": data_manifest["manifest_sha256"],
            "source_licenses": license_rows,
            "members": [{"path": n, "bytes": sizes[n], "sha256": hashes[n]} for n in sorted(hashes)],
            "wheel_installed": False, "engine_imported": False, "python314_admission": False}
