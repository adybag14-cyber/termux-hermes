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
from types import SimpleNamespace
import unittest
from unittest import mock

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


    def case_matrix_fixture(self, temporary, mode):
        out = Path(temporary)
        fixture = out / "case-fixture.py"
        fixture.write_text(
            "import json,pathlib,sys\n"
            "name,target,mode=sys.argv[1:]\n"
            "out=pathlib.Path(target); out.mkdir()\n"
            "record={'component': name, 'status': 'passed'}\n"
            "code=0\n"
            "if mode=='fail' and name=='pyarrow': record['status']='failed'; code=7\n"
            "if mode=='fail' and name=='lxml': record['component']='wrong-component'\n"
            "if not (mode=='fail' and name=='msgpack'):\n"
            " (out/'CASE-RESULT.json').write_text(json.dumps(record))\n"
            "sys.stderr.write('exact child diagnostic: '+name+'\\n')\n"
            "raise SystemExit(code)\n", encoding="utf-8")
        original_command = PROBE.command
        calls = []
        def real_child(argv, output, label, timeout, **kwargs):
            self.assertFalse(kwargs["check"])
            name = argv[-1]
            target = argv[argv.index("--out") + 1]
            calls.append(name)
            return original_command([sys.executable, "-I", "-B", str(fixture), name, target, mode],
                                    output, label, min(timeout, 15), **kwargs)
        args = SimpleNamespace(out=out, inputs=out / "inputs", apt_archives=out / "archives",
                               foundation_receipt=out / "foundation.json")
        return args, calls, real_child

    def test_all_five_real_children_run_before_aggregate_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, calls, child = self.case_matrix_fixture(temporary, "fail")
            report = {}
            with mock.patch.object(PROBE, "command", side_effect=child):
                with self.assertRaisesRegex(PROBE.ProbeError, "pyarrow, lxml, msgpack"):
                    PROBE.run_cases(args, self.lock, report)
            self.assertEqual(calls, list(PROBE.CASES))
            self.assertEqual([r["status"] for r in report["cases"]],
                             ["failed", "failed", "failed", "passed", "passed"])
            self.assertEqual(report["cases"][0]["command"]["exit_code"], 7)
            self.assertIn("receipt_error", report["cases"][1])
            self.assertIn("receipt_error", report["cases"][2])
            for row in report["cases"]:
                raw = (args.out / row["command"]["stderr"]["file"]).read_bytes()
                self.assertIn(("exact child diagnostic: " + row["component"]).encode(), raw)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["command"]["stderr"]["sha256"])

    def test_case_matrix_requires_five_matching_successful_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, calls, child = self.case_matrix_fixture(temporary, "pass")
            report = {}
            with mock.patch.object(PROBE, "command", side_effect=child):
                PROBE.run_cases(args, self.lock, report)
            self.assertEqual(calls, list(PROBE.CASES))
            self.assertEqual(len(report["cases"]), 5)
            self.assertTrue(all(row["status"] == row["child_status"] == "passed"
                                and row["command"]["exit_code"] == 0 for row in report["cases"]))

    def test_behavior_and_mapping_failures_are_retained_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(out=Path(temporary), case="pyarrow", foundation_receipt=Path("unused"))
            apt = SimpleNamespace(native_runtime=lambda contract: None)
            common = SimpleNamespace(validate_foundation=lambda path, lock: None)
            with mock.patch.object(PROBE.os, "getuid", return_value=1000, create=True), \
                    mock.patch.object(PROBE, "pyarrow_case", side_effect=ValueError("behavior fixture")), \
                    mock.patch.object(PROBE, "verify_mappings", side_effect=PROBE.ProbeError("mapping fixture")):
                with self.assertRaisesRegex(PROBE.ProbeError, "Actual native case failed"):
                    PROBE.case_run(args, self.lock, PREP, common, apt)
            result = json.loads((args.out / "CASE-RESULT.json").read_bytes())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["stage"], "behavior")
            self.assertEqual(result["error"]["message"], "behavior fixture")
            self.assertEqual(result["mapping_error"]["stage"], "native-mapping-provenance")
            self.assertEqual(result["mapping_error"]["message"], "mapping fixture")
            self.assertNotIn("mappings", result)


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


    def observations_fixture(self, temporary, corrupt_second=False):
        out = Path(temporary)
        elf = self.lock["root_native_files"]["python-msgpack"][0]
        pin = self.pins["python-msgpack"]
        raw = PREP.inspect_deb(self.inputs / "archives" / pin["filename"], pin,
                              wanted={elf["path"]})["selected"][elf["path"]]
        paths, aliases = [], {}
        for index in range(2):
            path = out / ("unreviewed-" + str(index) + ".so")
            data = raw if not (index == 1 and corrupt_second) else b"not-an-ELF"
            path.write_bytes(data)
            name = path.as_posix()
            paths.append(name)
            aliases[name] = {PREP.PREFIX_TEXT + "/opt/aosp/lib64/unreviewed-" + str(index) + ".so"}
        owners = {path: ["aosp-libs"] for path in paths}
        state = {"aosp-libs": {"version": "fixture-exact", "architecture": "aarch64", "status": "installed"}}
        apt = SimpleNamespace(collect_owners=lambda wanted: owners)
        with mock.patch.object(PROBE, "package_snapshot", return_value=state):
            found, observations = PROBE.mapping_observations(
                SimpleNamespace(out=out), self.lock, apt, PREP, paths, aliases, [])
        return paths, found, observations

    def test_all_real_elf_observations_are_saved_without_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, owners, result = self.observations_fixture(temporary)
            saved = json.loads((Path(temporary) / "MAPPED-LIBRARY-OBSERVATIONS.json").read_bytes())
            self.assertEqual(saved, result)
            self.assertTrue(result["complete"])
            self.assertFalse(result["admitted"])
            self.assertEqual(len(result["files"]), 2)
            for row in result["files"]:
                path = Path(row["resolved_path"])
                self.assertIn(row["resolved_path"], paths)
                self.assertEqual(row["bytes"], path.stat().st_size)
                self.assertEqual(row["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(row["elf"]["machine"], 183)
                self.assertEqual(row["owners"], ["aosp-libs"])
                self.assertEqual(row["owner_states"]["aosp-libs"]["version"], "fixture-exact")
                self.assertFalse(row["admitted"])
                for alias in row["mapped_paths"]:
                    with self.assertRaisesRegex(PROBE.ProbeError, "Unreviewed native mapping"):
                        PROBE.classify_mapping(alias, self.lock)

    def test_bad_elf_observation_keeps_both_files_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, owners, result = self.observations_fixture(temporary, corrupt_second=True)
            self.assertFalse(result["complete"])
            self.assertFalse(result["admitted"])
            self.assertEqual(len(result["files"]), 2)
            bad = next(row for row in result["files"] if row["resolved_path"] == paths[1])
            self.assertEqual(bad["sha256"], hashlib.sha256(b"not-an-ELF").hexdigest())
            self.assertIn("AArch64", bad["observation_error"]["message"])
            self.assertTrue((Path(temporary) / "MAPPED-LIBRARY-OBSERVATIONS.json").is_file())


if __name__ == "__main__":
    unittest.main()
