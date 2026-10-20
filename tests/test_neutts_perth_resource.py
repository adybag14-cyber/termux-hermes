"""Resource-lookup regression and exact original Perth-wheel preservation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("perth_resource_prepare", ROOT / "scripts/prepare_neutts_perth_resource.py")
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)
FIXTURE = ROOT / "tests/fixtures/neutts-perth-resource/original-init.py"


class ResourceLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = PREP.load_lock()
        cls.before = FIXTURE.read_bytes()
        cls.patch = (ROOT / cls.lock["patch"]["path"]).read_bytes()
        cls.after = PREP.apply_patch(cls.before, cls.patch, cls.lock)

    def execute_resource_module(self, source, root):
        package = root / "perth/perth_net"
        checkpoint = package / "pretrained/implicit"
        checkpoint.mkdir(parents=True)
        model = checkpoint / "perth_net_250000.pth.tar"
        model.write_bytes(b"local resource existence fixture; no model loading")
        module_path = package / "__init__.py"
        module_path.write_bytes(source)
        sentinel = type("PreservedWatermarkerImport", (), {})
        names = ["perth", "perth.perth_net.perth_net_implicit",
                 "perth.perth_net.perth_net_implicit.perth_watermarker"]
        imports = {name: types.ModuleType(name) for name in names}
        for obj in imports.values():
            obj.__path__ = []
        imports[names[-1]].PerthImplicitWatermarker = sentinel
        imports["pkg_resources"] = None
        spec = importlib.util.spec_from_file_location("perth.perth_net", module_path,
                                                     submodule_search_locations=[str(package)])
        module = importlib.util.module_from_spec(spec)
        imports["perth.perth_net"] = module
        with mock.patch.dict(sys.modules, imports):
            spec.loader.exec_module(module)
        return module, checkpoint.parent, model, sentinel

    def test_original_fails_when_pkg_resources_is_absent(self):
        self.assertEqual(len(self.before), 187)
        self.assertEqual(hashlib.sha256(self.before).hexdigest(), self.lock["patch"]["before_sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ModuleNotFoundError) as caught:
                self.execute_resource_module(self.before, Path(temporary))
            self.assertEqual(caught.exception.name, "pkg_resources")

    def test_patched_lookup_resolves_its_installed_resources_without_pkg_resources(self):
        with tempfile.TemporaryDirectory(prefix="perth resource path ") as temporary:
            module, expected, model, sentinel = self.execute_resource_module(self.after, Path(temporary))
            self.assertIsInstance(module.PREPACKAGED_MODELS_DIR, str)
            self.assertEqual(Path(module.PREPACKAGED_MODELS_DIR), expected.resolve())
            self.assertTrue((Path(module.PREPACKAGED_MODELS_DIR) / "implicit" / model.name).is_file())
            self.assertIs(module.PerthImplicitWatermarker, sentinel)

    def test_resource_lookup_is_independent_of_current_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unrelated = root / "unrelated"
            unrelated.mkdir()
            previous = Path.cwd()
            try:
                os.chdir(unrelated)
                module, expected, _, _ = self.execute_resource_module(self.after, root / "installed")
            finally:
                os.chdir(previous)
            self.assertEqual(Path(module.PREPACKAGED_MODELS_DIR), expected.resolve())

    def test_changed_original_resource_module_is_rejected(self):
        for changed in (self.before + b"\n", self.before.replace(b"pretrained", b"elsewhere")):
            with self.subTest(changed=changed[-25:]):
                with self.assertRaises(PREP.PreparationError):
                    PREP.apply_patch(changed, self.patch, self.lock)

    def test_changed_patch_is_rejected(self):
        with self.assertRaises(PREP.PreparationError):
            PREP.apply_patch(self.before, self.patch.replace(b"pretrained", b"elsewhere"), self.lock)

    def test_source_pin_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / PREP.LOCK_NAME
            raw = (ROOT / "scripts" / PREP.LOCK_NAME).read_bytes()
            path.write_bytes(raw + b"\n")
            with self.assertRaises(PREP.PreparationError):
                PREP.load_lock(path)

    def test_changed_version_or_metadata_artifact_fails_before_archive_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / self.lock["upstream_package"]["artifact"]["filename"]
            path.write_bytes(b"not the pinned original wheel")
            with self.assertRaises(PREP.PreparationError):
                PREP.verify_wheel(path, self.lock, upstream=True)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "existing"
            target.mkdir()
            marker = target / "owner-file"
            marker.write_bytes(b"preserve")
            with self.assertRaises(PREP.PreparationError):
                PREP.prepare(target, Path(temporary) / "missing.whl")
            self.assertEqual(marker.read_bytes(), b"preserve")


@unittest.skipUnless(os.environ.get("NEUTTS_PERTH_WHEEL"), "Set NEUTTS_PERTH_WHEEL to exact original public archive")
class OriginalWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wheel = Path(os.environ["NEUTTS_PERTH_WHEEL"])
        cls.lock = PREP.load_lock()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.prepared = Path(cls.temporary.name) / "prepared"
        cls.receipt = PREP.prepare(cls.prepared, cls.wheel)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_actual_derivative_preserves_all_other_members_and_checkpoint(self):
        name = self.lock["derived_artifact"]["filename"]
        with zipfile.ZipFile(self.wheel) as original, zipfile.ZipFile(self.prepared / name) as derived:
            self.assertEqual(original.namelist(), derived.namelist())
            changed = [n for n in original.namelist() if original.read(n) != derived.read(n)]
            self.assertEqual(sorted(changed), sorted(self.lock["patch"]["changed_members"]))
            checkpoint = self.lock["upstream_package"]["embedded_checkpoint_members"][0]
            self.assertEqual(hashlib.sha256(derived.read(checkpoint["path"])).hexdigest(), checkpoint["sha256"])
        self.assertEqual(self.receipt["unchanged_original_members"], 26)
        self.assertFalse(self.receipt["native_runtime_admitted"])
        self.assertFalse(self.receipt["model_execution"])
        self.assertFalse(self.receipt["release_output"])

    def test_derived_archive_reproduces_exact_reviewed_bytes(self):
        patch = (ROOT / self.lock["patch"]["path"]).read_bytes()
        output = PREP.derived_bytes(self.wheel, patch, self.lock)
        self.assertEqual(hashlib.sha256(output).hexdigest(), self.lock["derived_artifact"]["sha256"])
        self.assertEqual(len(output), self.lock["derived_artifact"]["bytes"])

    def test_false_native_admission_or_changed_receipt_is_rejected(self):
        path = self.prepared / PREP.RECEIPT
        before = path.read_bytes()
        changed = json.loads(before)
        changed["native_runtime_admitted"] = True
        try:
            path.write_bytes(PREP.encoded(changed))
            with self.assertRaises(PREP.PreparationError):
                PREP.verify_inputs(self.prepared)
        finally:
            path.write_bytes(before)

    def test_unexpected_prepared_payload_is_rejected(self):
        extra = self.prepared / "unreviewed.py"
        try:
            extra.write_bytes(b"raise RuntimeError\n")
            with self.assertRaises(PREP.PreparationError):
                PREP.verify_inputs(self.prepared)
        finally:
            extra.unlink()


if __name__ == "__main__":
    unittest.main()
