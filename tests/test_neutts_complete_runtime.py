"""Targeted host checks for the original complete dependency environment."""
from __future__ import annotations

import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import sys
import unittest
import weakref

ROOT = Path(__file__).resolve().parents[1]


def load(filename):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location("_test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = load("prepare_neutts_complete_runtime.py")
runtime = load("compatibility_probe_neutts_complete_runtime.py")


class OriginalGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nodes, edges, environment, engine = prep.original_graph()
        cls.lock = {"names": sorted(n["name"] for n in nodes), "nodes": nodes, "edges": edges,
                    "environment": environment}
        cls.metadata = {n["name"]: {k: n[k] for k in ("version", "requires_dist", "requires_python")}
                        for n in nodes}

    def check(self, lock=None, metadata=None):
        return prep.validate_closure(lock or self.lock, metadata or self.metadata, self.lock["environment"])

    def test_original_116_nodes_183_links_pass(self):
        result = self.check()
        self.assertEqual((result["node_count"], result["active_edge_count"]), (116, 183))
        self.assertEqual(result["selected_extras"], {"fsspec": ["http"]})
        self.assertNotIn("neutts", self.metadata)
        self.assertEqual(set(self.metadata) & prep.APT_NAMES, prep.APT_NAMES)

    def test_nine_absent_python_bounds_are_preserved(self):
        absent = {name for name, row in self.metadata.items() if not row["requires_python"]}
        self.assertEqual(absent, {"local-attention", "mpmath", "rfc3986", "soundfile",
                                 "standard-aifc", "standard-chunk", "standard-sunau", "torchao", "torchaudio"})
        original = copy.deepcopy(self.metadata)
        self.check()
        self.assertEqual(self.metadata, original)
        equivalent = copy.deepcopy(self.metadata)
        for name in absent:
            equivalent[name]["requires_python"] = ""
        self.check(metadata=equivalent)
        self.assertEqual(self.metadata, original)

    def test_missing_and_extra_distribution_rejected(self):
        for name in ("torchtune", "neucodec", "aiohttp", "pyarrow", "soundfile"):
            with self.subTest(name=name):
                bad = copy.deepcopy(self.metadata)
                del bad[name]
                with self.assertRaisesRegex(ValueError, "Incomplete or extra"):
                    self.check(metadata=bad)
        bad = copy.deepcopy(self.metadata)
        bad["neutts"] = {"version": "1.4.1", "requires_dist": [], "requires_python": ">=3.10,<3.14"}
        with self.assertRaisesRegex(ValueError, "Incomplete or extra"):
            self.check(metadata=bad)

    def test_original_versions_and_python_bounds_cannot_be_relaxed(self):
        mutations = [
            ("tokenizers", "version", "0.23.0"),
            ("transformers", "version", "5.2.0"),
            ("soundfile", "requires_python", ">=3.10"),
            ("huggingface-hub", "requires_python", ""),
            ("numba", "requires_python", ">=3.15"),
        ]
        for name, field, value in mutations:
            with self.subTest(name=name, field=field):
                bad = copy.deepcopy(self.metadata)
                bad[name][field] = value
                with self.assertRaises(ValueError):
                    self.check(metadata=bad)

    def test_dropping_even_an_inactive_requirement_is_rejected(self):
        bad = copy.deepcopy(self.metadata)
        old = bad["fsspec"]["requires_dist"]
        self.assertTrue(any("extra ==" in row for row in old))
        bad["fsspec"]["requires_dist"] = old[:-1]
        with self.assertRaisesRegex(ValueError, "Original metadata"):
            self.check(metadata=bad)

    def test_fsspec_http_extra_cannot_be_omitted(self):
        bad = copy.deepcopy(self.lock)
        next(n for n in bad["nodes"] if n["name"] == "fsspec")["active_extras"] = []
        with self.assertRaises(ValueError):
            self.check(lock=bad)

    def test_original_edge_cannot_be_omitted_or_duplicated(self):
        for change in ("drop", "duplicate", "redirect"):
            with self.subTest(change=change):
                bad = copy.deepcopy(self.lock)
                if change == "drop":
                    bad["edges"].pop()
                elif change == "duplicate":
                    bad["edges"].append(copy.deepcopy(bad["edges"][0]))
                else:
                    bad["edges"][0]["to"] = "packaging"
                with self.assertRaisesRegex(ValueError, "183 active"):
                    self.check(lock=bad)

    def test_actual_platform_cannot_be_impersonated(self):
        for field, value in (("sys_platform", "linux"), ("python_full_version", "3.13.9"),
                             ("platform_machine", "x86_64"), ("platform_system", "Linux")):
            with self.subTest(field=field):
                environment = {**self.lock["environment"], field: value}
                with self.assertRaisesRegex(ValueError, "Actual marker environment"):
                    prep.validate_closure(self.lock, self.metadata, environment)

    def test_requirement_whitespace_is_semantic_without_rewriting(self):
        first = "setuptools > 77.0.3"
        second = "setuptools>77.0.3"
        self.assertEqual(prep.requirement_key(first), prep.requirement_key(second))
        self.assertNotEqual(first, second)


class ExactAptPlanTests(unittest.TestCase):
    def setUp(self):
        original = json.loads((ROOT / "scripts/neutts_apt_extensions_lock.json").read_bytes())
        self.pins = [{"name": r["package"], "version": r["version"]}
                     for r in original["apt"]["provenance_packages"]
                     if r["package"] in original["apt"]["additional_names"]]
        self.pins.append({"name": "libyaml", "version": "0.2.5-5"})
        self.plan = "\n".join("Inst " + p["name"] + " (" + p["version"] + " original [aarch64])"
                              for p in self.pins)

    def test_exact_original_19_packages(self):
        result = runtime.validate_install_plan(self.plan, self.pins)
        self.assertEqual(len(result["packages"]), 19)

    def test_added_removed_duplicate_and_changed_packages_fail(self):
        invalid = [
            self.plan + "\nInst clang (99 original [aarch64])",
            self.plan + "\nRemv python [3.14.6]",
            self.plan + "\n" + self.plan.splitlines()[0],
            "\n".join(self.plan.splitlines()[1:]),
            self.plan.replace("libyaml (0.2.5-5", "libyaml (0.2.5-6"),
            self.plan + "\nInst malformed",
        ]
        for plan in invalid:
            with self.subTest(plan=plan[-70:]):
                with self.assertRaises(ValueError):
                    runtime.validate_install_plan(plan, self.pins)


class AssetProvenanceTests(unittest.TestCase):
    def test_exact_real_wrapper_copy_and_bad_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, work = root / "assets", root / "work"
            assets.mkdir()
            (work / "tmp").mkdir(parents=True)
            original = b"owned fixture bytes for identity validation"
            (assets / "libespeak-ng.so").write_bytes(original)
            copy_path = work / "tmp/libespeak-ng.so"
            copy_path.write_bytes(original)
            row = {"classification": "rejected-foreign", "resolved_path": str(copy_path.resolve()), "deleted": False}
            rows = [row]
            copies = runtime.classify_asset_mappings(rows, work, assets, prep)
            self.assertEqual(copies, [str(copy_path.resolve())])
            self.assertEqual(rows[0]["classification"], "espeak-asset-copy")
            copy_path.write_bytes(original + b"tamper")
            with self.assertRaises((ValueError, prep.helper().PrepareError)):
                runtime.classify_asset_mappings([{**row, "classification": "rejected-foreign"}],
                                               work, assets, prep)

    def test_deleted_or_foreign_native_mapping_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            (assets / "libespeak-ng.so").write_bytes(b"fixture")
            for classification, deleted in (("rejected-deleted", True), ("rejected-foreign", False)):
                with self.subTest(classification=classification):
                    row = {"classification": classification, "resolved_path": str(root / "foreign.so"),
                           "deleted": deleted}
                    with self.assertRaises(ValueError):
                        runtime.classify_asset_mappings([row], root / "work", assets, prep)


class EspeakLifetimeTests(unittest.TestCase):
    def fixture_api(self, finalized):
        class FixtureAPI:
            def __init__(self, label, fail=False):
                self._library = None
                weakref.finalize(self, finalized.append, label)
                if fail:
                    raise RuntimeError("native initialization fixture failed")
                self._library = object()
                self._library_path = Path("literal-original-library")
        return FixtureAPI

    def test_real_instances_survive_until_retention_is_released(self):
        finalized = []
        api = self.fixture_api(finalized)
        previous = sys.getprofile()
        with runtime.retain_espeak_instances(api) as retained:
            api("first")
            api("second")
            gc.collect()
            self.assertEqual(finalized, [])
        self.assertIs(sys.getprofile(), previous)
        self.assertEqual(retained["constructor_calls"], 2)
        self.assertEqual(len(retained["instances"]), 2)
        self.assertTrue(all(type(instance) is api for instance in retained["instances"]))
        gc.collect()
        self.assertEqual(finalized, [])
        retained["instances"].clear()
        gc.collect()
        self.assertCountEqual(finalized, ["first", "second"])

    def test_other_constructor_and_failed_instance_are_not_retained(self):
        finalized = []
        api = self.fixture_api(finalized)
        other = self.fixture_api(finalized)
        with runtime.retain_espeak_instances(api) as retained:
            other("other")
            with self.assertRaisesRegex(RuntimeError, "native initialization"):
                api("failed", fail=True)
            api("actual")
        self.assertEqual(retained["constructor_calls"], 2)
        self.assertEqual(len(retained["instances"]), 1)
        gc.collect()
        self.assertCountEqual(finalized, ["other", "failed"])
        retained["instances"].clear()

    def test_constructor_cap_fails_and_previous_profile_is_restored(self):
        finalized = []
        api = self.fixture_api(finalized)
        previous = sys.getprofile()
        def existing_profile(frame, event, value):
            return None
        try:
            sys.setprofile(existing_profile)
            with self.assertRaisesRegex(ValueError, "retention cap exceeded"):
                with runtime.retain_espeak_instances(api, maximum=1) as retained:
                    api("one")
                    api("two")
            self.assertIs(sys.getprofile(), existing_profile)
            self.assertEqual(len(retained["instances"]), 1)
            self.assertTrue(retained["prior_profile_present"])
        finally:
            sys.setprofile(previous)

    def test_exception_restores_previous_profile_without_retaining_frames(self):
        finalized = []
        api = self.fixture_api(finalized)
        previous = sys.getprofile()
        try:
            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                with runtime.retain_espeak_instances(api) as retained:
                    api("actual")
                    raise RuntimeError("operation failed")
            self.assertIs(sys.getprofile(), previous)
            self.assertEqual(set(retained), {"instances", "constructor_calls",
                                            "maximum_instances", "prior_profile_present"})
            self.assertTrue(all(type(instance) is api for instance in retained["instances"]))
            for maximum in (0, 33, True):
                with self.subTest(maximum=maximum), self.assertRaisesRegex(ValueError, "retention bound"):
                    with runtime.retain_espeak_instances(api, maximum=maximum):
                        pass
            self.assertIs(sys.getprofile(), previous)
        finally:
            sys.setprofile(previous)


class WorkflowContractTests(unittest.TestCase):
    def test_embedded_python_parses(self):
        wrapper = (ROOT / "scripts/compatibility_probe_neutts_complete_runtime.sh").read_text(encoding="utf-8")
        blocks = re.findall(r"<<'(PY_[A-Z]+)'\n(.*?)\n\1", wrapper, re.S)
        self.assertEqual({label for label, _ in blocks}, {"PY_INPUTS", "PY_NETWORK", "PY_RESULT", "PY_READY"})
        for label, source in blocks:
            with self.subTest(label=label):
                compile(source, label, "exec")

    def test_host_verifier_rejects_connected_stopped_and_wrong_input_container(self):
        wrapper = (ROOT / "scripts/compatibility_probe_neutts_complete_runtime.sh").read_text(encoding="utf-8")
        source = dict(re.findall(r"<<'(PY_[A-Z]+)'\n(.*?)\n\1", wrapper, re.S))["PY_NETWORK"]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / "complete-inputs").mkdir()
            lock = b'{"test":"identity fixture"}'
            (out / "complete-inputs/neutts_complete_runtime_lock.json").write_bytes(lock)
            lock_sha = hashlib.sha256(lock).hexdigest()
            (out / "COMPLETE-CONTAINER-ID.txt").write_text("a" * 64)
            ready = {"schema_version": 1, "status": "ready-for-network-disconnect", "lock_sha256": lock_sha}
            inspection = {"Id": "a" * 64, "State": {"Running": True}, "NetworkSettings": {"Networks": {}}}
            import unittest.mock
            for kind in ("connected", "stopped", "wrong-container", "wrong-lock", "valid"):
                with self.subTest(kind=kind):
                    actual, current = copy.deepcopy(inspection), copy.deepcopy(ready)
                    if kind == "connected":
                        actual["NetworkSettings"]["Networks"] = {"bridge": {}}
                    elif kind == "stopped":
                        actual["State"]["Running"] = False
                    elif kind == "wrong-container":
                        actual["Id"] = "b" * 64
                    elif kind == "wrong-lock":
                        current["lock_sha256"] = "c" * 64
                    (out / "COMPLETE-DISCONNECTED-CONTAINER.json").write_text(json.dumps([actual]))
                    (out / "COMPLETE-NETWORK-READY.json").write_text(json.dumps(current))
                    with unittest.mock.patch("sys.argv", ["host-validator", str(out)]):
                        if kind == "valid":
                            exec(compile(source, "PY_NETWORK", "exec"), {})
                            value = json.loads((out / "COMPLETE-NETWORK-OFFLINE.json").read_bytes())
                            self.assertEqual(value["container"], inspection)
                            self.assertEqual(value["lock_sha256"], lock_sha)
                        else:
                            with self.assertRaises(SystemExit):
                                exec(compile(source, "PY_NETWORK", "exec"), {})


if __name__ == "__main__":
    unittest.main()
