"""Focused input/provenance regressions for the standalone five-APT native gate.

Set NEUTTS_APT_EXTENSIONS_INPUTS to an actual prepared cache for the archive
regressions. No host test claims execution of Android extension code.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREP = load("test_apt_extensions_prepare", "prepare_neutts_apt_extensions.py")
PROBE = load("test_apt_extensions_probe", "compatibility_probe_neutts_apt_extensions.py")


class FrozenContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock, cls.lock_raw = PREP.load_lock()
        cls.original = PREP.apt_helper().load_manifest(ROOT / "scripts/neutts_apt_python_metadata.json")

    def mutated(self):
        return copy.deepcopy(self.lock)

    def test_original_seven_loader_and_new_twelve_binding_are_separate(self):
        self.assertEqual(len(self.original["apt_distributions"]), 7)
        self.assertEqual(len(self.lock["metadata"]["apt_distributions"]), 12)
        original = {r["name"]: r for r in self.original["apt_distributions"]}
        new = {r["name"]: r for r in self.lock["metadata"]["apt_distributions"]}
        self.assertEqual({name: new[name] for name in original}, original)
        self.assertEqual(hashlib.sha256(self.lock_raw).hexdigest(), PREP.LOCK_SHA256)

    def test_additions_derive_only_from_original_122_foundation(self):
        foundation = {p["package"] for p in self.lock["foundation"]["packages"]}
        additions = set(self.lock["apt"]["closure_names"]) - foundation
        self.assertEqual((len(foundation), len(additions)), (122, 18))
        self.assertEqual(additions, set(self.lock["apt"]["additional_names"]))
        self.assertNotIn("clang", additions)
        pins = [p for p in self.lock["apt"]["provenance_packages"] if p["package"] in additions]
        self.assertEqual(sum(p["bytes"] for p in pins), 14_043_104)
        self.assertTrue(all(":" not in p["version"] for p in pins))

    def test_missing_twelve_metadata_row_rejected(self):
        lock = self.mutated()
        lock["metadata"]["apt_distributions"].pop()
        with self.assertRaises(PREP.PreparationError):
            PREP.validate_manifest(lock, self.original)

    def test_original_seven_metadata_change_rejected(self):
        lock = self.mutated()
        next(r for r in lock["metadata"]["apt_distributions"] if r["name"] == "numpy")["version"] = "0"
        with self.assertRaises(PREP.PreparationError):
            PREP.validate_manifest(lock, self.original)

    def test_extra_compiler_addition_rejected(self):
        lock = self.mutated()
        lock["apt"]["additional_names"].append("clang")
        with self.assertRaises(PREP.PreparationError):
            PREP.validate_manifest(lock, self.original)

    def test_image_mapping_boundary_cannot_be_broadened(self):
        lock = self.mutated()
        lock["image_runtime"]["files"][0]["path"] = "/data/data/com.termux/files/usr/opt/aosp/lib64/arbitrary.so"
        with self.assertRaises(PREP.PreparationError):
            PREP.validate_manifest(lock, self.original)

    def test_whole_lock_byte_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / PREP.LOCK_FILENAME
            path.write_bytes(self.lock_raw + b"\n")
            with self.assertRaisesRegex(PREP.PreparationError, "lock differs"):
                PREP.load_lock(path)

    def test_raw_pip_retains_exact_twelve_failures(self):
        apt = PREP.apt_helper()
        lines = [r["name"] + " " + r["version"] + " is not supported on this platform"
                 for r in self.lock["metadata"]["apt_distributions"]]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pip.txt"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            record = apt.raw_pip_record(path, 1, self.lock["metadata"])
            self.assertFalse(record["passed"])
            self.assertEqual(record["exit_code"], 1)
            with self.assertRaises(apt.ValidationError):
                apt.raw_pip_record(path, 0, self.lock["metadata"])
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            with self.assertRaises(apt.ValidationError):
                apt.raw_pip_record(path, 1, self.lock["metadata"])


class InstallAndMappingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock, _ = PREP.load_lock()
        cls.additions = [p for p in cls.lock["apt"]["provenance_packages"]
                         if p["package"] in cls.lock["apt"]["additional_names"]]
        cls.before = {p["package"]: PROBE.installed_identity(p) for p in cls.lock["foundation"]["packages"]}

    def plan(self):
        return "\n".join("Inst " + p["package"] + " (" + p["version"] + " exact-source [aarch64])"
                         for p in self.additions) + "\n"

    def test_exact_names_and_versions_are_required(self):
        selected = PROBE.validate_plan(self.plan(), self.additions)
        self.assertEqual(selected, {p["package"]: p["version"] for p in self.additions})

    def test_extra_package_plan_rejected(self):
        with self.assertRaisesRegex(PROBE.ProbeError, "extra"):
            PROBE.validate_plan(self.plan() + "Inst clang (99.0 exact-source [aarch64])\n", self.additions)

    def test_different_selected_version_rejected(self):
        first = self.additions[0]
        changed = self.plan().replace("(" + first["version"] + " ", "(99.0 ", 1)
        with self.assertRaisesRegex(PROBE.ProbeError, "version"):
            PROBE.validate_plan(changed, self.additions)

    def test_existing_upgrade_in_plan_rejected(self):
        first = self.additions[0]["package"]
        changed = self.plan().replace("Inst " + first + " (", "Inst " + first + " [0.0] (", 1)
        with self.assertRaisesRegex(PROBE.ProbeError, "upgrade/downgrade"):
            PROBE.validate_plan(changed, self.additions)

    def test_removal_plan_rejected(self):
        with self.assertRaisesRegex(PROBE.ProbeError, "removal"):
            PROBE.validate_plan(self.plan() + "Remv python [3.14.6-1]\n", self.additions)

    def test_omitted_install_rejected(self):
        with self.assertRaisesRegex(PROBE.ProbeError, "omission"):
            PROBE.validate_plan("\n".join(self.plan().splitlines()[1:]), self.additions)

    def test_duplicate_install_rejected(self):
        with self.assertRaisesRegex(PROBE.ProbeError, "duplicate"):
            PROBE.validate_plan(self.plan() + self.plan().splitlines()[0] + "\n", self.additions)

    def test_preexisting_exact_package_is_distinguished_from_new(self):
        before = copy.deepcopy(self.before)
        first = self.additions[0]
        before[first["package"]] = PROBE.installed_identity(first)
        additions = PROBE.validate_before(before, self.lock)
        after = {**before, **{p["package"]: PROBE.installed_identity(p) for p in additions}}
        changes = PROBE.validate_after(before, after, additions)
        self.assertEqual(len(changes["new_packages"]), 17)
        self.assertEqual(changes["reinstalled_exact_packages"], [first["package"]])

    def test_preexisting_wrong_selected_version_rejected(self):
        before = copy.deepcopy(self.before)
        first = self.additions[0]
        before[first["package"]] = {**PROBE.installed_identity(first), "version": "0"}
        with self.assertRaisesRegex(PROBE.ProbeError, "pre-existing"):
            PROBE.validate_before(before, self.lock)

    def test_whole_dpkg_state_change_outside_selection_rejected(self):
        after = {**self.before, **{p["package"]: PROBE.installed_identity(p) for p in self.additions}}
        after["python"] = {**after["python"], "version": "3.15.0"}
        with self.assertRaisesRegex(PROBE.ProbeError, "outside"):
            PROBE.validate_after(self.before, after, self.additions)

    def test_duplicate_dpkg_records_rejected(self):
        line = "python\t3.14.6-1\taarch64\tinstalled\n"
        with self.assertRaisesRegex(PROBE.ProbeError, "duplicate"):
            PROBE.parse_package_snapshot(line + line)

    def test_exact_image_paths_have_separate_authority(self):
        for row in self.lock["image_runtime"]["files"]:
            self.assertEqual(PROBE.classify_mapping(row["path"], self.lock), "pinned-image-aosp")
        self.assertEqual(PROBE.classify_mapping(PREP.PREFIX_TEXT + "/lib/libarrow.so", self.lock), "apt")

    def test_unknown_mapping_reports_actual_offender(self):
        path = PREP.PREFIX_TEXT + "/opt/aosp/lib64/unreviewed.so"
        with self.assertRaisesRegex(PROBE.ProbeError, re.escape(path)):
            PROBE.classify_mapping(path, self.lock)

    def test_mapping_traversal_rejected(self):
        with self.assertRaisesRegex(PROBE.ProbeError, "Non-canonical"):
            PROBE.classify_mapping(PREP.PREFIX_TEXT + "/lib/../../foreign.so", self.lock)

    def test_real_child_failure_preserves_exit_and_raw_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            argv = [sys.executable, "-I", "-B", "-c",
                    "import sys; sys.stderr.write('native fixture diagnostic\\n'); raise SystemExit(7)"]
            with self.assertRaisesRegex(PROBE.ProbeError, "exit=7"):
                PROBE.command(argv, out, "fixture", 15)
            record = json.loads((out / "fixture.command.json").read_bytes())
            raw = (out / "fixture.stderr.log").read_bytes()
            self.assertEqual(record["exit_code"], 7)
            self.assertEqual(record["status"], "failed")
            self.assertIn(b"native fixture diagnostic", raw)
            self.assertEqual(record["stderr"]["sha256"], hashlib.sha256(raw).hexdigest())


class ActualArchiveFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get("NEUTTS_APT_EXTENSIONS_INPUTS")
        if not value:
            raise unittest.SkipTest("Set NEUTTS_APT_EXTENSIONS_INPUTS to the verified original five-archive fixture")
        cls.inputs = Path(value)
        cls.lock, cls.receipt = PREP.verify_inputs(cls.inputs)
        cls.pins = {p["package"]: p for p in cls.lock["apt"]["provenance_packages"]}

    def test_actual_five_archives_full_inventory_and_elf_counts(self):
        roots = self.receipt["roots"]
        self.assertEqual(len(roots), 5)
        self.assertEqual(sum(p["regular_files"] for p in roots), 893)
        self.assertEqual(sum(p["symlinks"] for p in roots), 1)
        self.assertEqual(sum(p["native_files"] for p in roots), 34)
        self.assertFalse(self.receipt["native_execution"])

    def test_real_multiversion_index_selects_exact_identities(self):
        raw = PREP.snapshot_metadata(self.inputs / "snapshot", self.lock)
        names = re.findall(rb"^Package: (.+)$", raw, re.MULTILINE)
        self.assertEqual(len(names), 3011)
        self.assertEqual(len(set(names)), 3008)

    def test_exact_selected_index_version_drift_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["foundation"]["packages"][0]["version"] += ".unreviewed"
        with self.assertRaisesRegex(PREP.PreparationError, "index package"):
            PREP.snapshot_metadata(self.inputs / "snapshot", lock)

    def test_cached_fresh_preparation_preserves_bytes_and_rejects_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "prepared"
            receipt = PREP.prepare(out, self.inputs / "archives")
            self.assertEqual(receipt, self.receipt)
            for name in PREP.ROOTS:
                pin = self.pins[name]
                self.assertEqual((out / "archives" / pin["filename"]).read_bytes(),
                                 (self.inputs / "archives" / pin["filename"]).read_bytes())
            with self.assertRaises(PREP.PreparationError):
                PREP.prepare(out, self.inputs / "archives")

    def test_extra_prepared_snapshot_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "fixture"
            shutil.copytree(self.inputs, target)
            (target / "snapshot/unreviewed.txt").write_text("extra")
            PREP.snapshot_metadata(target / "snapshot", self.lock)
            with self.assertRaisesRegex(PREP.PreparationError, "snapshot file set"):
                PREP.verify_inputs(target)

    def test_original_archive_byte_mutation_rejected(self):
        pin = self.pins["python-msgpack"]
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / pin["filename"]
            raw = bytearray((self.inputs / "archives" / pin["filename"]).read_bytes())
            raw[-1] ^= 1
            target.write_bytes(raw)
            with self.assertRaisesRegex(PREP.PreparationError, "identity"):
                PREP.inspect_deb(target, pin, wanted=set())

    def test_original_control_identity_rejected_when_expected_version_changes(self):
        pin = copy.deepcopy(self.pins["python-msgpack"])
        pin["control"]["Version"] = "0"
        with self.assertRaisesRegex(PREP.PreparationError, "control"):
            PREP.inspect_deb(self.inputs / "archives" / pin["filename"], pin, wanted=set())

    def test_omitting_original_package_file_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["original_root_files"]["python-msgpack"].pop()
        pin = self.pins["python-msgpack"]
        with self.assertRaisesRegex(PREP.PreparationError, "file bytes/modes/links"):
            PREP.verify_root(self.inputs / "archives" / pin["filename"], pin, lock)

    def test_original_five_wheel_tags_are_unchanged_archive_bytes(self):
        rows = [r for r in self.lock["metadata"]["apt_distributions"] if r["name"] in PREP.NAMES]
        for row in rows:
            pin = self.pins[row["apt"]["package"]]
            files = PREP.inspect_deb(self.inputs / "archives" / pin["filename"], pin,
                                     wanted={row["wheel"]["path"], row["metadata"]["path"]})["selected"]
            for field in ("metadata", "wheel"):
                self.assertEqual(PREP.sha(files[row[field]["path"]]), row[field]["sha256"])
            self.assertIn(b"android_aarch64", files[row["wheel"]["path"]])
            self.assertNotIn(b"android_24_arm64_v8a", files[row["wheel"]["path"]])

    def test_native_msgpack_payload_requires_actual_aarch64_header(self):
        row = self.lock["root_native_files"]["python-msgpack"][0]
        pin = self.pins["python-msgpack"]
        raw = PREP.inspect_deb(self.inputs / "archives" / pin["filename"], pin,
                               wanted={row["path"]})["selected"][row["path"]]
        self.assertEqual(PREP.elf_identity(raw)["machine"], 183)
        changed = bytearray(raw)
        changed[18:20] = (62).to_bytes(2, "little")
        with self.assertRaisesRegex(PREP.PreparationError, "AArch64"):
            PREP.elf_identity(changed)


if __name__ == "__main__":
    unittest.main()
