"""Exact input and simulated loader-selection regression tests; no native audio claims."""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit/neutts-soundfile-discovery-fix-20261020"

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

prep = module("_soundfile_test_preparer", ROOT / "scripts/prepare_neutts_soundfile.py")
perth = module("_soundfile_test_perth", ROOT / "scripts/prepare_neutts_perth_runtime.py")


class ExactDerivativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = prep.load_lock()
        cls.upstream = AUDIT / "original" / cls.lock["upstream_package"]["artifact"]["filename"]
        cls.patch = (ROOT / cls.lock["patch"]["path"]).read_bytes()
        cls.derived = prep.derived_bytes(cls.upstream, cls.patch, cls.lock)

    def test_exact_original_and_reproducible_eight_member_derivative(self):
        original = prep.verify_wheel(self.upstream, self.lock, upstream=True)
        self.assertEqual(original["members_verified"], 8)
        self.assertEqual(self.derived, prep.derived_bytes(self.upstream, self.patch, self.lock))
        self.assertEqual(len(self.derived), 90959)
        self.assertEqual(hashlib.sha256(self.derived).hexdigest(),
                         "ad4f764ecc142ab5a9e05a0d61fda83ddf190fb7d59ca3c0da094be6229ee992")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / self.upstream.name
            path.write_bytes(self.derived)
            self.assertEqual(prep.verify_wheel(path, self.lock, upstream=False)["members_verified"], 8)

    def test_only_source_and_truthful_record_change(self):
        with zipfile.ZipFile(self.upstream) as original, zipfile.ZipFile(io.BytesIO(self.derived)) as derived:
            before = {i.filename: original.read(i) for i in original.infolist()}
            after = {i.filename: derived.read(i) for i in derived.infolist()}
        changed = sorted(n for n in before if before[n] != after[n])
        self.assertEqual(changed, sorted(self.lock["patch"]["changed_members"]))
        self.assertEqual(len(before) - len(changed), 6)
        for name in before:
            if name not in changed:
                with self.subTest(member=name):
                    self.assertEqual(before[name], after[name])
        old = b"        elif _sys.platform == 'linux':\n            _explicit_libname = 'libsndfile.so'\n"
        new = b"        elif _sys.platform in ('linux', 'android'):\n            _explicit_libname = 'libsndfile.so'\n"
        self.assertEqual(before["soundfile.py"].count(old), 1)
        self.assertEqual(after["soundfile.py"], before["soundfile.py"].replace(old, new))
        self.assertEqual(before["soundfile.py"].split(b"except (OSError, ImportError, TypeError):", 1)[0],
                         after["soundfile.py"].split(b"except (OSError, ImportError, TypeError):", 1)[0])

    def test_corrupt_original_patch_or_derivative_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / self.upstream.name
            raw = bytearray(self.upstream.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
            with self.assertRaises(prep.PreparationError):
                prep.verify_wheel(path, self.lock, upstream=True)
            with self.assertRaises(prep.PreparationError):
                prep.derived_bytes(self.upstream, self.patch + b"\n", self.lock)
            value = bytearray(self.derived); value[100] ^= 1; path.write_bytes(value)
            with self.assertRaises(prep.PreparationError):
                prep.verify_wheel(path, self.lock, upstream=False)

    def test_record_truthfulness_is_independent_of_whole_archive_hash(self):
        changed = copy.deepcopy(self.lock)
        with zipfile.ZipFile(io.BytesIO(self.derived)) as archive:
            infos = archive.infolist()
            content = {i.filename: archive.read(i) for i in infos}
        target = "soundfile-0.13.1.dist-info/LICENSE"
        content[target] += b"explicitly synthetic integrity test\n"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for info in infos:
                archive.writestr(info, content[info.filename])
        raw = output.getvalue()
        changed["derived_artifact"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        next(row for row in changed["derived_members"] if row["path"] == target).update(
            bytes=len(content[target]), sha256=hashlib.sha256(content[target]).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / self.upstream.name; path.write_bytes(raw)
            with self.assertRaisesRegex(prep.PreparationError, "Untruthful RECORD"):
                prep.verify_wheel(path, changed, upstream=False)

    def test_complete_preparation_receipt_and_layout_are_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "inputs"
            receipt = prep.prepare(out, self.upstream)
            self.assertEqual(receipt, prep.verify_inputs(out))
            self.assertEqual(receipt["unchanged_original_members"], 6)
            self.assertFalse(receipt["native_runtime_admitted"])
            self.assertFalse(receipt["audio_io_executed"])
            self.assertFalse(receipt["release_output"])
            path = out / prep.RECEIPT
            value = json.loads(path.read_bytes()); value["native_runtime_admitted"] = True
            path.write_bytes(prep.encoded(value))
            with self.assertRaisesRegex(prep.PreparationError, "receipt"):
                prep.verify_inputs(out)

    def test_prepared_extra_file_or_changed_metadata_cannot_be_admitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "inputs"; prep.prepare(out, self.upstream)
            (out / "unreviewed.txt").write_bytes(b"extra")
            with self.assertRaisesRegex(prep.PreparationError, "inventory"):
                prep.verify_inputs(out)

    def test_original_foundation_library_has_exact_native_soname(self):
        pin = self.lock["required_original_apt_library"]
        self.assertEqual((pin["name"], pin["version"], pin["architecture"]),
                         ("libsndfile", "1.2.2-3", "aarch64"))
        archive = AUDIT / "original" / perth.apt_helper().archive_name(pin)
        raw = perth.verified_bytes(archive, pin)
        perth.apt_helper().verify_snapshot(ROOT / "audit/neutts-runtime-index-20261017", [pin])
        parts = dict(perth.wheel_helper().ar_parts(raw))
        data = next(v for name, v in parts.items() if name.startswith("data.tar."))
        selected = []
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|*") as tar:
            for item in tar:
                if item.name.removeprefix("./") == "data/data/com.termux/files/usr/lib/libsndfile.so":
                    self.assertTrue(item.isfile())
                    selected.append(tar.extractfile(item).read())
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(selected[0]), 439352)
        self.assertEqual(hashlib.sha256(selected[0]).hexdigest(),
                         "079263392fddcdd975f2d452f6fd654e26f199fda1c85e08d67fedfbb4b55825")
        elf = module("_soundfile_test_elf", ROOT / "scripts/neutts_runtime_elf.py")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "libsndfile.so"; path.write_bytes(selected[0])
            facts = elf.elf(path, dynamic=True)
            self.assertEqual(facts["soname"], ["libsndfile.so"])
            self.assertEqual((facts["class"], facts["machine"]), (64, 183))

    def test_retained_native_failure_has_passed_closure_but_no_public_api_pass(self):
        review = json.loads((AUDIT / "NATIVE-FAILURE-REVIEW.json").read_bytes())
        for row in review["selected_crc_verified_members"]:
            with self.subTest(member=row["member"]):
                raw = (AUDIT / "native-failure" / row["member"]).read_bytes()
                self.assertEqual(len(raw), row["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["sha256"])
        core = json.loads((AUDIT / "native-failure/NEUTTS-CORE-RESULT.json").read_bytes())
        child = json.loads((AUDIT / "native-failure/PERTH-RUNTIME-RESULT.json").read_bytes())
        installed = json.loads((AUDIT / "native-failure/PERTH-APT-AFTER.json").read_bytes())
        self.assertEqual(core["status"], "passed")
        self.assertEqual(len(core["cases"]), 7)
        self.assertTrue(all(p["status"] == "passed" for p in core["cases"]))
        self.assertEqual((child["closure"]["node_count"], child["closure"]["active_edge_count"]), (43, 50))
        self.assertEqual(child["auxiliary"]["status"], "passed")
        self.assertEqual(child["status"], "failed")
        self.assertIn("sndfile library not found", child["error"]["message"])
        self.assertEqual(installed["libsndfile"],
                         {"version": "1.2.2-3", "architecture": "aarch64", "status": "installed"})
        self.assertFalse(review["public_watermark_passed"])
        self.assertFalse(review["native_fix_tested"])

    def test_perth_retains_complete_graph_and_uses_verified_derivative(self):
        lock, _ = perth.load_lock()
        package = next(p for p in lock["packages"] if p["name"] == "soundfile")
        self.assertEqual(package["artifact"], self.lock["derived_artifact"])
        self.assertEqual(package["origin"]["kind"], "soundfile-android-derivative")
        original = self.lock["upstream_package"]
        self.assertEqual(package["requires_dist"], original["requires_dist"])
        self.assertEqual(package["requires_python"], original["requires_python"] or "")
        self.assertEqual((lock["node_count"], lock["edge_count"]), (43, 50))
        self.assertEqual(perth.SOUNDFILE_HELPER_SHA256,
                         hashlib.sha256((ROOT / "scripts/prepare_neutts_soundfile.py").read_bytes()).hexdigest())


class LoaderSelectionTests(unittest.TestCase):
    """Execute the real source's loader branch with explicit simulated OS/FFI results.

    These tests prove source dispatch and error propagation only. Actual libsndfile
    loading, WAV I/O and watermark operations remain required native workflow gates.
    """
    @classmethod
    def setUpClass(cls):
        lock = prep.load_lock()
        upstream = AUDIT / "original" / lock["upstream_package"]["artifact"]["filename"]
        with zipfile.ZipFile(upstream) as archive:
            cls.original = archive.read("soundfile.py")
        cls.patched = prep.apply_patch(cls.original, (ROOT / lock["patch"]["path"]).read_bytes(), lock)

    def execute(self, source, platform, lookup, accepted):
        tree = ast.parse(source)
        nodes = [n for n in tree.body if isinstance(n, ast.Try)
                 and any(isinstance(v, ast.Name) and v.id == "_packaged_libname" for v in ast.walk(n))]
        self.assertEqual(len(nodes), 1)
        block = ast.Module(body=nodes, type_ignores=[])
        attempts = []
        def dlopen(name):
            attempts.append(name)
            if name not in accepted:
                raise OSError("simulated normal missing DLL: " + name)
            return ("simulated-loaded", name)
        namespace = {"_sys": types.SimpleNamespace(platform=platform), "_os": os,
                     "_find_library": mock.Mock(return_value=lookup),
                     "_ffi": types.SimpleNamespace(dlopen=dlopen)}
        data = types.SimpleNamespace(__file__="/reviewed/_soundfile_data/__init__.py")
        with mock.patch.dict(sys.modules, {"_soundfile_data": data}), mock.patch("platform.machine", return_value="aarch64"):
            exec(compile(block, "<real-soundfile-loader-source>", "exec"), namespace)
        return namespace, attempts

    def test_original_android_missing_lookup_reproduces_failure(self):
        with self.assertRaisesRegex(OSError, "sndfile library not found"):
            self.execute(self.original, "android", None, {"libsndfile.so"})

    def test_patched_android_tries_real_system_filename(self):
        values, attempts = self.execute(self.patched, "android", None, {"libsndfile.so"})
        self.assertEqual(attempts, ["libsndfile.so"])
        self.assertEqual(values["_explicit_libname"], "libsndfile.so")
        self.assertIsNone(values["_libname"])
        self.assertEqual(values["_snd"], ("simulated-loaded", "libsndfile.so"))

    def test_successful_ctypes_lookup_still_takes_precedence(self):
        for source in (self.original, self.patched):
            with self.subTest(source_sha256=hashlib.sha256(source).hexdigest()):
                values, attempts = self.execute(source, "android", "/reviewed/libsndfile.so",
                                                 {"/reviewed/libsndfile.so"})
                self.assertEqual(attempts, ["/reviewed/libsndfile.so"])
                self.assertNotIn("_explicit_libname", values)

    def test_normal_missing_native_library_is_not_masked(self):
        with self.assertRaisesRegex(OSError, "simulated normal missing DLL: libsndfile.so"):
            self.execute(self.patched, "android", None, set())

    def test_existing_linux_packaged_library_branch_is_unchanged(self):
        expected = os.path.join("/reviewed/_soundfile_data", "libsndfile_arm64.so")
        for source in (self.original, self.patched):
            with self.subTest(source_sha256=hashlib.sha256(source).hexdigest()):
                values, attempts = self.execute(source, "linux", None, {expected})
                self.assertEqual(attempts, [expected])
                self.assertNotIn("_explicit_libname", values)

    def test_unreviewed_platform_is_not_given_android_fallback(self):
        with self.assertRaisesRegex(OSError, "sndfile library not found"):
            self.execute(self.patched, "unreviewed-platform", None, {"libsndfile.so"})


if __name__ == "__main__":
    unittest.main()
