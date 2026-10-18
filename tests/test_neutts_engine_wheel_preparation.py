"""Focused host checks for the build-only NeuTTS wheel experiment.

Synthetic wheel/ELF fixtures test validation branches only. Real compiler execution,
Android ABI, installed build inventory and bundled eSpeak behavior require the
separate native workflow. These tests never install or import the NeuTTS engine.
"""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/neutts_engine_wheel"


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


CHECK = module("_test_engine_wheel_verify", "verify_neutts_engine_wheel.py")
PREP = module("_test_engine_wheel_prep", "prepare_neutts_engine_wheel.py")
PROBE = module("_test_engine_wheel_probe", "compatibility_probe_neutts_engine_wheel.py")
CORE = module("_test_engine_wheel_core", "prepare_neutts_core_python.py")
LOCK = json.loads((ROOT / "scripts/neutts_engine_wheel_lock.json").read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(project=None, readme=b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n"):
    project = LOCK["engine_source"]["project"] if project is None else project
    rows = [
        "Metadata-Version: 2.4", "Name: " + project["name"], "Version: " + project["version"],
        "Summary: " + project["description"], "Author-Email: neuphonic <general@neuphonic.com>",
        "Requires-Python: " + project["requires-python"], "Description-Content-Type: text/markdown",
        *("Requires-Dist: " + text for text in CHECK.expected_requirements(project)),
        *("Provides-Extra: " + text for text in sorted(project["optional-dependencies"])),
    ]
    return ("\n".join(rows) + "\n\n").encode() + readme


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engine-wheel-host-test-")
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()


class TestExactInputs(TemporaryTest):
    def test_lock_reuses_exact_original_three_wheel_records(self):
        lock, raw = PREP.load_lock()
        original = json.loads((ROOT / "scripts/neutts_native_sources_lock.json").read_bytes())
        selected = [p for p in original["additional_python_wheels"]
                    if p["name"] in {"scikit-build-core", "packaging", "pathspec"}]
        self.assertEqual(lock["build"]["python_wheels"], selected)
        self.assertEqual(sha(raw), PREP.LOCK_SHA256)
        self.assertEqual(sum(p["artifact"]["bytes"] for p in selected), 425144)
        self.assertEqual(lock["target"], original["target"])
        self.assertEqual(lock["build"]["cflags"], original["build"]["cflags"])

    def test_complete_marker_graph_preserves_declared_extra_requirements(self):
        rows = LOCK["build"]["python_wheels"]
        before = copy.deepcopy(rows)
        edges = PREP.build_graph(rows, LOCK["build"]["marker_environment"])
        self.assertEqual({(e["parent"], e["name"]) for e in edges},
                         {("scikit-build-core", "packaging"), ("scikit-build-core", "pathspec")})
        self.assertEqual(rows, before)
        self.assertEqual(len(rows[0]["declared_requires_dist"]), 13)
        self.assertEqual(len(rows[2]["declared_requires_dist"]), 3)

    def test_missing_active_distribution_rejected(self):
        for missing in ("packaging", "pathspec"):
            with self.subTest(missing=missing), self.assertRaisesRegex(RuntimeError, "Unresolved active"):
                PREP.build_graph([r for r in LOCK["build"]["python_wheels"] if r["name"] != missing],
                                 LOCK["build"]["marker_environment"])

    def test_wrong_active_version_rejected(self):
        rows = copy.deepcopy(LOCK["build"]["python_wheels"])
        next(p for p in rows if p["name"] == "pathspec")["version"] = "0.1"
        with self.assertRaisesRegex(RuntimeError, "Unresolved active"):
            PREP.build_graph(rows, LOCK["build"]["marker_environment"])

    def test_unsupported_python_and_unprepared_extras_rejected(self):
        for field, value in (("python_full_version", "3.7.0"), ("extra", "wheels"),
                             ("extra", "hatchling"), ("extra", "hyperscan")):
            env = dict(LOCK["build"]["marker_environment"], **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                PREP.build_graph(LOCK["build"]["python_wheels"], env)

    def test_duplicate_and_direct_url_build_requirement_rejected(self):
        rows = copy.deepcopy(LOCK["build"]["python_wheels"])
        with self.assertRaisesRegex(RuntimeError, "Duplicate build"):
            PREP.build_graph(rows + [rows[-1]], LOCK["build"]["marker_environment"])
        rows[0]["declared_requires_dist"].append("unreviewed @ https://example.invalid/a.whl")
        with self.assertRaisesRegex(RuntimeError, "Unresolved URL"):
            PREP.build_graph(rows, LOCK["build"]["marker_environment"])

    def test_original_pyproject_and_python_bound_unchanged(self):
        result = PREP.verify_project(FIXTURE / "pyproject.toml", LOCK)
        self.assertEqual(result["requires_python"], ">=3.10, <3.14")
        self.assertEqual(len(result["base_requires_dist"]), 9)
        self.assertEqual(set(result["optional_dependencies"]), {"llama", "onnx", "all"})
        self.assertFalse(result["engine_install_attempted"])

    def test_pyproject_bound_or_dependency_edit_rejected(self):
        original = (FIXTURE / "pyproject.toml").read_bytes()
        for before, after in ((b"<3.14", b"<3.15"), (b"torch>=2.8.0", b"torch>=2.7.0")):
            raw = original.replace(before, after)
            self.assertNotEqual(raw, original)
            p = self.base / "pyproject.toml"
            p.write_bytes(raw)
            with self.subTest(before=before), self.assertRaisesRegex(RuntimeError, "pyproject changed"):
                PREP.verify_project(p, LOCK)

    def test_all_fifty_six_source_pins_retained(self):
        rows = json.loads((FIXTURE / "wheel-source-manifest.json").read_bytes())
        self.assertEqual(len(rows), 56)
        self.assertEqual(sha(CHECK.canonical(rows)), LOCK["engine_source"]["wheel_source_manifest"]["sha256"])
        self.assertEqual(sum(r["size"] for r in rows), LOCK["engine_source"]["wheel_source_manifest"]["bytes"])
        original = copy.deepcopy(rows)
        target = next(r for r in original if r["path"] == "CMakeLists.txt")
        raw = (FIXTURE / "CMakeLists.root-offline.txt").read_bytes()
        target.update(size=len(raw), sha256=sha(raw),
                      git_blob_sha1=hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())
        self.assertEqual(sha(CHECK.canonical(original)), LOCK["engine_source"]["root_patched_manifest"]["sha256"])
        self.assertEqual(LOCK["engine_source"]["source_date_epoch"], 1784730951)

    def test_real_git_patch_retains_original_source_options(self):
        p = self.base / "CMakeLists.txt"
        p.write_bytes((FIXTURE / "CMakeLists.root-offline.txt").read_bytes())
        patch = ROOT / LOCK["patch"]["path"]
        result = subprocess.run(["git", "-C", str(self.base), "apply", "--check", str(patch)],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["git", "-C", str(self.base), "apply", str(patch)],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sha(p.read_bytes()), LOCK["patch"]["changes"][0]["after_sha256"])
        text = p.read_text("utf-8")
        self.assertIn("GIT_TAG 69bfd1efde0236654ccc117a28d04aef27673a30", text)
        self.assertNotIn("CMAKE_BUILD_TYPE", text)
        self.assertIn('"-DCMAKE_C_COMPILER:FILEPATH=${CMAKE_C_COMPILER}"', text)
        self.assertEqual({f.name for f in self.base.iterdir()}, {"CMakeLists.txt"})


class TestMetadata(TemporaryTest):
    def test_original_metadata_retains_all_fifteen_requirements_and_bound(self):
        result = CHECK.verify_metadata(metadata(), LOCK["engine_source"]["project"],
                                       b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n")
        self.assertEqual(len(result["all_declared_requirements"]), 15)
        self.assertEqual(set(result["all_extras"]), {"llama", "onnx", "all"})
        self.assertTrue(result["requires_python_excludes_current_314"])
        self.assertFalse(result["engine_install_admitted"])

    def test_utf8_readme_and_crlf_preserved(self):
        raw = metadata().replace(b"\n", b"\r\n")
        CHECK.verify_metadata(raw, LOCK["engine_source"]["project"],
                              b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n")

    def test_base_and_optional_dependency_omissions_rejected(self):
        for name in ("librosa", "torch", "onnxruntime", "llama-cpp-python"):
            raw = b"\n".join(line for line in metadata().split(b"\n")
                             if not line.startswith(("Requires-Dist: " + name).encode()))
            with self.subTest(name=name), self.assertRaisesRegex(CHECK.EngineWheelError, "dependency metadata"):
                CHECK.verify_metadata(raw, LOCK["engine_source"]["project"],
                                      b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n")

    def test_changed_bound_version_author_or_extra_rejected(self):
        changes = ((b"<3.14", b"<3.15"), (b"Version: 1.4.1", b"Version: 1.4.2"),
                   (b"general@neuphonic.com", b"other@example.invalid"),
                   (b"Provides-Extra: onnx\n", b""))
        for before, after in changes:
            with self.subTest(before=before), self.assertRaises(CHECK.EngineWheelError):
                CHECK.verify_metadata(metadata().replace(before, after), LOCK["engine_source"]["project"],
                                      b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n")

    def test_duplicate_identity_or_changed_readme_rejected(self):
        for raw in (b"Name: neutts\n" + metadata(), metadata() + b"\nchanged"):
            with self.subTest(raw=sha(raw)), self.assertRaises(CHECK.EngineWheelError):
                CHECK.verify_metadata(raw, LOCK["engine_source"]["project"],
                                      b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n")


class TestCompilerRecords(TemporaryTest):
    def setUp(self):
        super().setUp()
        self.source = self.base / "source"
        self.build = self.base / "build"
        self.compiler = self.base / "toolchain/clang"
        self.cxx = self.base / "toolchain/clang++"
        self.build.mkdir()
        (self.source / "src/libespeak-ng").mkdir(parents=True)
        self.flags = LOCK["build"]["cflags"].split() + [
            "-D_FILE_OFFSET_BITS=64", "-I" + str(self.source / "src/ucd-tools/src/include")]
        self.row = {"directory": str(self.build), "file": str(self.source / "src/libespeak-ng/speech.c"),
                    "arguments": [str(self.compiler), *self.flags, "-c",
                                  str(self.source / "src/libespeak-ng/speech.c")]}

    def check(self, rows):
        return CHECK.verify_compile_commands(rows, self.source, self.build, [self.compiler, self.cxx])

    def test_complete_recorded_command_checked_without_execution_claim(self):
        result = self.check([self.row])
        self.assertEqual(result["compile_commands"], 1)
        self.assertTrue(result["every_command_api24_armv8_checked"])
        self.assertNotIn("native_compiler_execution_claimed", result)

    def test_each_required_target_pic_or_original_source_flag_rejected_if_lost(self):
        for flag in self.flags:
            if flag == "-O2":
                continue
            row = copy.deepcopy(self.row)
            row["arguments"].remove(flag)
            with self.subTest(flag=flag), self.assertRaises(CHECK.EngineWheelError):
                self.check([row])

    def test_conflicting_target_cpu_and_response_file_rejected(self):
        for flag in ("--target=aarch64-linux-android35", "-target", "-mcpu=native",
                     "-march=armv8.2-a", "@hidden.rsp"):
            row = copy.deepcopy(self.row)
            row["arguments"].append(flag)
            with self.subTest(flag=flag), self.assertRaises(CHECK.EngineWheelError):
                self.check([row])

    def test_foreign_compiler_and_source_or_build_escape_rejected(self):
        for key in ("compiler", "file", "directory"):
            row = copy.deepcopy(self.row)
            if key == "compiler":
                row["arguments"][0] = str(self.base / "unreviewed/clang")
            else:
                row[key] = str(self.base / "outside")
            with self.subTest(key=key), self.assertRaises(CHECK.EngineWheelError):
                self.check([row])

    def test_empty_duplicate_and_missing_speech_records_rejected(self):
        wrong = copy.deepcopy(self.row)
        wrong["file"] = str(self.source / "src/libespeak-ng/other.c")
        for rows in ([], [self.row, self.row], [wrong]):
            with self.subTest(count=len(rows)), self.assertRaises(CHECK.EngineWheelError):
                self.check(rows)

    def test_ambiguous_argument_or_unknown_field_rejected(self):
        for patch in ({"command": "unreviewed"}, {"other": "value"}, {"arguments": "string"}):
            row = dict(self.row, **patch)
            with self.subTest(patch=patch), self.assertRaises(CHECK.EngineWheelError):
                self.check([row])

    def test_cache_parser_preserves_values_and_rejects_duplicates(self):
        self.assertEqual(CHECK.cache_values(b"// comment\nX:STRING=a=b\n# line\nY:BOOL=ON\n"),
                         {"X": "a=b", "Y": "ON"})
        for raw in (b"X:BOOL=ON\nX:BOOL=OFF\n", b"not a cache row\n"):
            with self.subTest(raw=raw), self.assertRaises(CHECK.EngineWheelError):
                CHECK.cache_values(raw)

    def test_build_settings_preserve_upstream_nested_default(self):
        settings = PROBE.build_settings(LOCK, self.source, self.build)
        self.assertEqual(settings["build.tool-args"], ["-j2"])
        self.assertEqual(settings["cmake.define.CMAKE_C_FLAGS"], LOCK["build"]["cflags"])
        self.assertEqual(settings["cmake.define.CMAKE_CXX_FLAGS"], LOCK["build"]["cflags"])
        self.assertNotIn("cmake.define.CMAKE_BUILD_TYPE", settings)
        self.assertFalse(any("wheel." in k or "python" in k.lower() for k in settings))

    def test_hostile_environment_overrides_removed(self):
        bad = {"SKBUILD_WHEEL_TAGS": "foreign", "_PYTHON_HOST_PLATFORM": "manylinux",
               "CMAKE_TOOLCHAIN_FILE": "/foreign", "CC": "/foreign", "CXXFLAGS": "-march=native",
               "LD_PRELOAD": "/foreign", "PYTHONPATH": "/foreign", "KEEP_TEST_CONTROL": "kept"}
        with mock.patch.dict(os.environ, bad, clear=True):
            env = PROBE.clean_environment(LOCK)
        for name in ("SKBUILD_WHEEL_TAGS", "_PYTHON_HOST_PLATFORM", "CMAKE_TOOLCHAIN_FILE",
                     "LD_PRELOAD", "PYTHONPATH"):
            self.assertNotIn(name, env)
        self.assertEqual(env["CC"], str(PROBE.PREFIX / "bin/clang"))
        self.assertEqual(env["CXXFLAGS"], LOCK["build"]["cflags"])
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "1784730951")
        self.assertEqual(env["KEEP_TEST_CONTROL"], "kept")


class TestSourceAndData(TemporaryTest):
    def test_original_bytes_preserved_and_generated_addition_reported(self):
        (self.base / "original").write_bytes(b"source")
        rows = [{"path": "original", "mode": "100644", "size": 6, "sha256": sha(b"source")}]
        (self.base / "generated").write_bytes(b"generated")
        result = CHECK.verify_original_source_files(self.base, rows)
        self.assertEqual(result["original_files"], 1)
        self.assertEqual(result["generated_source_tree_files"][0]["path"], "generated")

    def test_original_byte_change_or_disappearance_rejected(self):
        rows = [{"path": "original", "mode": "100644", "size": 6, "sha256": sha(b"source")}]
        for raw in (b"changed", None):
            p = self.base / "original"
            if raw is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(CHECK.EngineWheelError):
                CHECK.verify_original_source_files(self.base, rows)

    def test_complete_language_data_and_source_voices_required(self):
        source = self.base / "source"
        data = self.base / "data"
        (source / "cmake").mkdir(parents=True)
        (source / "cmake/data.cmake").write_text("list(APPEND _dict_compile_list\n en fr)\n")
        for subtree in ("lang", "voices/!v"):
            (source / "espeak-ng-data" / subtree).mkdir(parents=True)
            (source / "espeak-ng-data" / subtree / "original").write_bytes(b"voice")
            (data / subtree).mkdir(parents=True)
            (data / subtree / "original").write_bytes(b"voice")
        for name in ("en_dict", "fr_dict", "intonations", "phondata", "phonindex", "phontab"):
            (data / name).write_bytes(b"compiled")
        result = CHECK.verify_data_tree(data, source)
        self.assertEqual(result["dictionary_count"], 2)
        self.assertEqual(result["file_count"], 8)
        for name in ("en_dict", "phondata", "lang/original"):
            p = data / name
            old = p.read_bytes()
            p.unlink()
            with self.subTest(missing=name), self.assertRaises(CHECK.EngineWheelError):
                CHECK.verify_data_tree(data, source)
            p.write_bytes(old)
        (data / "voices/!v/original").write_bytes(b"changed")
        with self.assertRaisesRegex(CHECK.EngineWheelError, "voice/language bytes"):
            CHECK.verify_data_tree(data, source)


class TestWheelStructure(TemporaryTest):
    """Synthetic headers exercise validators only; they are not native ABI evidence."""

    def setUp(self):
        super().setUp()
        self.lock = copy.deepcopy(LOCK)
        self.source = self.base / "source"
        self.source.mkdir()
        self.readme = b"# NeuTTS\nA UTF-8 reference: \xe2\x98\x85\n"
        (self.source / "README.md").write_bytes(self.readme)
        (self.source / "LICENSE").write_bytes(b"original license fixture\n")
        self.install = self.base / "install"
        (self.install / "lib").mkdir(parents=True)
        self.members = {}
        selected = []
        for row in LOCK["engine_source"]["required_wheel_source_members"]:
            raw = ("fixture " + row["source_path"] + "\n").encode()
            selected.append({**row, "bytes": len(raw), "sha256": sha(raw)})
            self.members[row["wheel_path"]] = raw
        self.lock["engine_source"]["required_wheel_source_members"] = selected
        self.elf = bytearray(64)
        self.elf[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", self.elf, 18, 183)
        for name in self.lock["espeak"]["library_names"]:
            (self.install / "lib" / name).write_bytes(self.elf)
            self.members["neutts/" + name] = bytes(self.elf)
        self.data = {"files": [{"path": "phondata", "bytes": 4, "sha256": sha(b"data")}],
                     "manifest_sha256": sha(b"data-manifest-fixture")}
        self.members["neutts/espeak-ng-data/phondata"] = b"data"
        self.prefix = "neutts-1.4.1.dist-info/"
        self.members[self.prefix + "METADATA"] = metadata(readme=self.readme)
        self.members[self.prefix + "WHEEL"] = (
            "Wheel-Version: 1.0\nGenerator: scikit-build-core 1.1.1\nRoot-Is-Purelib: false\nTag: "
            + self.lock["build"]["expected_built_tag"] + "\n\n").encode()
        self.members[self.prefix + "licenses/LICENSE"] = (self.source / "LICENSE").read_bytes()
        self.path = self.base / "neutts-1.4.1-cp314-cp314-android_24_arm64_v8a.whl"

    def write_wheel(self, mutate_record=None, extra_info=None):
        members = dict(self.members)
        record = self.prefix + "RECORD"
        rows = [[name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("="),
                 str(len(raw))] for name, raw in sorted(members.items())]
        rows.append([record, "", ""])
        if mutate_record:
            mutate_record(rows)
        stream = io.StringIO(newline="")
        csv.writer(stream, lineterminator="\n").writerows(rows)
        members[record] = stream.getvalue().encode()
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, raw in members.items():
                z.writestr(name, raw)
            if extra_info:
                z.writestr(*extra_info)

    def verify(self, destination=None):
        return CHECK.verify_built_wheel(self.path, self.lock, self.source, self.install, self.data,
                                        CORE.safe_member, {self.lock["build"]["expected_built_tag"]}, destination)

    def test_complete_structure_copies_exact_members_without_admission(self):
        self.write_wheel()
        destination = self.base / "inspected"
        result = self.verify(destination)
        self.assertEqual(result["source_members_preserved"], 14)
        self.assertEqual(len(result["native_members"]), 3)
        self.assertFalse(result["wheel_installed"])
        self.assertFalse(result["engine_imported"])
        self.assertFalse(result["python314_admission"])
        self.assertEqual((destination / "neutts/libespeak-ng.so").read_bytes(), bytes(self.elf))
        self.assertEqual(result["source_licenses"][0]["source"], "LICENSE")

    def test_missing_python_reference_data_or_license_rejected(self):
        names = ("neutts/__init__.py", "neutts/samples/emily.pt", "neutts/samples/emily.txt",
                 "neutts/espeak-ng-data/phondata", self.prefix + "licenses/LICENSE")
        for name in names:
            original = self.members.pop(name)
            self.write_wheel()
            with self.subTest(name=name), self.assertRaises(CHECK.EngineWheelError):
                self.verify()
            self.members[name] = original

    def test_changed_original_member_or_unexpected_payload_rejected(self):
        original = self.members["neutts/neutts.py"]
        self.members["neutts/neutts.py"] = b"changed"
        self.write_wheel()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "differs"):
            self.verify()
        self.members["neutts/neutts.py"] = original
        self.members["neutts/unreviewed.py"] = b"unreviewed"
        self.write_wheel()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "Unexpected wheel payload"):
            self.verify()

    def test_wrong_filename_or_internal_tag_and_generator_rejected(self):
        self.write_wheel()
        original = self.path
        self.path = self.base / "neutts-1.4.1-cp314-cp314-manylinux_2_17_aarch64.whl"
        shutil.copyfile(original, self.path)
        with self.assertRaisesRegex(CHECK.EngineWheelError, "native Android tag"):
            self.verify()
        self.path = original
        for before, after in ((b"android_24_arm64_v8a", b"android_35_arm64_v8a"),
                              (b"scikit-build-core 1.1.1", b"scikit-build-core 0.9.0"),
                              (b"Root-Is-Purelib: false", b"Root-Is-Purelib: true")):
            wheel = self.members[self.prefix + "WHEEL"]
            self.members[self.prefix + "WHEEL"] = wheel.replace(before, after)
            self.write_wheel()
            with self.subTest(before=before), self.assertRaises(CHECK.EngineWheelError):
                self.verify()
            self.members[self.prefix + "WHEEL"] = wheel

    def test_foreign_elf_header_rejected_even_with_matching_install_hashes(self):
        foreign = bytearray(self.elf)
        struct.pack_into("<H", foreign, 18, 62)
        for name in self.lock["espeak"]["library_names"]:
            (self.install / "lib" / name).write_bytes(foreign)
            self.members["neutts/" + name] = bytes(foreign)
        self.write_wheel()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "Foreign or unexpected"):
            self.verify()

    def test_installed_library_aliases_must_match(self):
        (self.install / "lib/libespeak-ng.so.1").write_bytes(bytes(self.elf) + b"changed")
        self.write_wheel()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "aliases differ"):
            self.verify()

    def test_unsafe_paths_and_symlink_entries_rejected(self):
        for name, mode in (("../escaped", stat.S_IFREG | 0o644),
                           ("neutts/link", stat.S_IFLNK | 0o777)):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            self.write_wheel(extra_info=(info, b"target"))
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                self.verify()

    def test_record_hash_omission_and_self_hash_rejected(self):
        mutations = [
            lambda rows: rows[0].__setitem__(1, "sha256=invalid"),
            lambda rows: rows.pop(0),
            lambda rows: rows[-1].__setitem__(2, "1"),
        ]
        for index, mutate in enumerate(mutations):
            self.write_wheel(mutate_record=mutate)
            with self.subTest(index=index), self.assertRaises(CHECK.EngineWheelError):
                self.verify()

    def test_wrong_license_asset_rejected(self):
        self.members[self.prefix + "licenses/LICENSE"] = b"replacement"
        self.write_wheel()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "license is not"):
            self.verify()

    def test_existing_inspection_output_rejected(self):
        self.write_wheel()
        destination = self.base / "inspection"
        destination.mkdir()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "Fresh wheel inspection"):
            self.verify(destination)


class TestSourceImageReceipt(TemporaryTest):
    def setUp(self):
        super().setUp()
        names = set(LOCK["helpers"]) | {
            "scripts/compatibility_probe_neutts_engine_wheel.py",
            "scripts/compatibility_probe_neutts_engine_wheel.sh",
            "scripts/prepare_neutts_engine_wheel.py", "scripts/neutts_engine_wheel_lock.json",
            "scripts/verify_neutts_engine_wheel.py", "scripts/check_neutts_engine_wheel_cmake.py",
            "patches/next-stable/neutts-propagate-espeak-toolchain.patch",
            ".github/workflows/neutts-engine-wheel.yml",
        }
        self.receipt = {"schema_version": 1, "head_sha": "a" * 40,
                        "native_image": LOCK["native_image"],
                        "inputs": {name: sha((ROOT / name).read_bytes()) for name in sorted(names)}}
        self.image = {"Id": "sha256:" + "b" * 64, "Architecture": "arm64", "Os": "linux",
                      "RepoDigests": [LOCK["native_image"]]}
        self.path = self.base / "ENGINE-WHEEL-PROBE-INPUTS.json"

    def write(self):
        self.path.write_bytes(CHECK.canonical(self.receipt))
        (self.base / "NATIVE-IMAGE-IDENTITY.json").write_bytes(CHECK.canonical(self.image))

    def test_bound_source_ledger_and_image_record_structure(self):
        self.write()
        result = PROBE.source_identity(self.path, LOCK, CHECK)
        self.assertEqual(result["native_image"], LOCK["native_image"])
        self.assertEqual(result["verified_source_files"], len(self.receipt["inputs"]))
        self.assertEqual(result["actual_image_receipt"]["sha256"],
                         sha((self.base / "NATIVE-IMAGE-IDENTITY.json").read_bytes()))

    def test_wrong_image_arch_os_or_digest_rejected(self):
        for field, value in (("Architecture", "amd64"), ("Os", "windows"),
                             ("RepoDigests", ["other@sha256:" + "b" * 64]),
                             ("Id", "not-a-digest")):
            original = self.image[field]
            self.image[field] = value
            self.write()
            with self.subTest(field=field), self.assertRaisesRegex(CHECK.EngineWheelError, "image architecture"):
                PROBE.source_identity(self.path, LOCK, CHECK)
            self.image[field] = original

    def test_missing_actual_image_receipt_rejected(self):
        self.write()
        (self.base / "NATIVE-IMAGE-IDENTITY.json").unlink()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "actual image receipt"):
            PROBE.source_identity(self.path, LOCK, CHECK)

    def test_missing_or_changed_source_pin_rejected(self):
        name = "scripts/verify_neutts_engine_wheel.py"
        original = self.receipt["inputs"].pop(name)
        self.write()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "omitted"):
            PROBE.source_identity(self.path, LOCK, CHECK)
        self.receipt["inputs"][name] = "0" * 64
        self.write()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "differs from host"):
            PROBE.source_identity(self.path, LOCK, CHECK)
        self.receipt["inputs"][name] = original

    def test_source_ledger_path_escape_rejected(self):
        self.receipt["inputs"]["../escape"] = "0" * 64
        self.write()
        with self.assertRaisesRegex(CHECK.EngineWheelError, "Unsafe source ledger"):
            PROBE.source_identity(self.path, LOCK, CHECK)


if __name__ == "__main__":
    unittest.main()
