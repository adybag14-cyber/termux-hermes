"""Host integrity review of the standalone gate; no native result is simulated."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit/neutts-tiktoken-preparation-20261020"
CAPTURE = ROOT / "audit/neutts-rust-native-20261017/run-39084939992"
METADATA = CAPTURE / "raw-termux-neutts-rust-tiktoken-lock/rust-components/tiktoken-offline-metadata-replay.stdout.log"


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


own = module("_tested_tiktoken_preparer", "prepare_neutts_tiktoken.py")
probe = module("_tested_tiktoken_probe", "compatibility_probe_neutts_tiktoken.py")
prep = own.helper()


class TiktokenIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tiktoken-integrity-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.lock, self.parent, _ = own.load_lock()

    def source(self, name="tiktoken"):
        source = own.source_record(self.lock, name)
        root = self.work / source["archive_root"]
        prep.archive_files(prep.verified_bytes(AUDIT / source["artifact"]["filename"], source["artifact"]),
                           source["archive_root"], output=root)
        if name == "tiktoken":
            pin = self.lock["references"]["cargo_lock"]
            (root / "Cargo.lock").write_bytes(prep.verified_bytes(ROOT / pin["path"], pin))
        return root

    def manifest(self):
        packages = deepcopy(self.lock["runtime_wheels"])
        packages += [{key: value[key] for key in ("name", "version", "requires_python", "requires_dist")}
                     for value in (self.lock["source"], self.lock["regex_source"])]
        return {"names": sorted(p["name"] for p in packages), "wheels": packages}

    def graph(self):
        raw = METADATA.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "950fced17a37700a12d7dfea731d48e57eab195d1925538b4bfaeabf732d5a4b")
        data = json.loads(raw)
        root = self.source()
        vendor = self.work / "vendor"
        for package in data["packages"]:
            path = (root / "Cargo.toml") if package["source"] is None else (
                vendor / (package["name"] + "-" + package["version"]) / "Cargo.toml")
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                # A filesystem-path fixture only. Original crate bytes are
                # independently checked by the immutable archive preparer.
                path.write_text("# Cargo metadata path fixture\n", encoding="utf-8")
            package["manifest_path"] = str(path)
        return data, root, vendor

    def test_approved_capture_is_separate_from_unchanged_original_source_record(self):
        self.assertIsNone(self.lock["source"]["cargo_lock"])
        self.assertEqual(self.lock["source"], next(p for p in self.parent["sources"] if p["name"] == "tiktoken"))
        self.assertNotIn("tiktoken", prep.LOCKED_NAMES)
        self.assertEqual(len(self.lock["registry"]), 27)
        self.assertEqual(sum(p["bytes"] for p in self.lock["registry"]), 5589389)
        self.assertEqual(self.lock["source"]["build_backend"], "setuptools.build_meta")
        self.assertEqual(self.lock["source"]["file_count"], 36)
        self.assertEqual(len(self.lock["regex_source"]["files"]), 22)

    def test_changed_standalone_lock_is_rejected_before_use(self):
        path = self.work / own.LOCK_FILENAME
        path.write_bytes((ROOT / "scripts" / own.LOCK_FILENAME).read_bytes() + b"\n")
        with self.assertRaisesRegex(RuntimeError, "standalone lock changed"):
            own.load_lock(path)

    def test_both_actual_original_source_archives_and_captured_lock_verify(self):
        for name, count in (("tiktoken", 36), ("regex", 22)):
            with self.subTest(source=name):
                result = own.verify_source_tree(self.source(name), name, self.lock, prep)
                self.assertEqual(result["files"], count)

    def test_original_setup_source_must_not_be_patched_for_locked_build(self):
        root = self.source()
        path = root / "setup.py"
        path.write_bytes(path.read_bytes().replace(b'debug=False', b'debug=True'))
        with self.assertRaises(RuntimeError):
            own.verify_source_tree(root, "tiktoken", self.lock, prep)

    def test_extra_source_file_is_not_hidden_by_captured_lock_exception(self):
        root = self.source()
        (root / "unreviewed.py").write_bytes(b"raise RuntimeError('unreviewed')\n")
        with self.assertRaises(RuntimeError):
            own.verify_source_tree(root, "tiktoken", self.lock, prep)

    def test_missing_captured_lock_is_rejected(self):
        root = self.source()
        (root / "Cargo.lock").unlink()
        with self.assertRaises((OSError, RuntimeError)):
            own.verify_source_tree(root, "tiktoken", self.lock, prep)

    def test_changed_captured_lock_is_rejected(self):
        root = self.source()
        path = root / "Cargo.lock"
        path.write_bytes(path.read_bytes().replace(b'0.29.3', b'0.29.4'))
        with self.assertRaises(RuntimeError):
            own.verify_source_tree(root, "tiktoken", self.lock, prep)

    def test_regex_cannot_gain_a_cargo_lock_or_extra_backend_path(self):
        root = self.source("regex")
        (root / "Cargo.lock").write_text("unreviewed", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            own.verify_source_tree(root, "regex", self.lock, prep)

    def test_captured_lock_has_exact_original_registry_checksums(self):
        root = self.source()
        result = probe.verify_cargo_lock(root / "Cargo.lock", self.lock, prep)
        self.assertEqual(result["full_lock_packages"], 28)
        self.assertEqual(result["original_registry_archives"], 27)
        bad = deepcopy(self.lock)
        bad["registry"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            probe.verify_cargo_lock(root / "Cargo.lock", bad, prep)

    def test_actual_runtime_wheels_keep_record_metadata_and_native_bytes(self):
        for package in self.lock["runtime_wheels"]:
            with self.subTest(package=package["name"]):
                facts = prep.verify_wheel(AUDIT / package["artifact"]["filename"], package)
                self.assertEqual(facts, package)
        native = next(p for p in self.lock["runtime_wheels"] if p["name"] == "charset-normalizer")
        self.assertEqual(len(native["native_members"]), 2)
        self.assertEqual(native["wheel"]["tags"], ["cp314-cp314-android_24_arm64_v8a"])

    def test_archives_cannot_be_replaced_by_newer_identically_named_input(self):
        package = self.lock["runtime_wheels"][0]
        path = self.work / package["artifact"]["filename"]
        raw = (AUDIT / path.name).read_bytes()
        path.write_bytes(raw + b"unreviewed")
        with self.assertRaises(RuntimeError):
            prep.verify_wheel(path, package)

    def test_original_native_metadata_replays_exact_target_graph(self):
        data, root, vendor = self.graph()
        result = probe.validate_cargo_graph(data, self.lock, root, vendor)
        self.assertEqual((result["target_packages"], result["target_edges"]), (25, 41))

    def test_cargo_registry_url_version_and_path_substitution_fail(self):
        original, root, vendor = self.graph()
        for field, value in (("source", "git+https://example.invalid/replacement"),
                             ("version", "99.0.0"), ("manifest_path", str(root / "Cargo.toml"))):
            with self.subTest(field=field):
                bad = deepcopy(original)
                package = next(p for p in bad["packages"] if p["source"] is not None)
                package[field] = value
                with self.assertRaises(RuntimeError):
                    probe.validate_cargo_graph(bad, self.lock, root, vendor)

    def test_cargo_local_root_outside_source_is_rejected(self):
        data, root, vendor = self.graph()
        foreign = self.work / "foreign/Cargo.toml"
        foreign.parent.mkdir()
        foreign.write_text("unreviewed", encoding="utf-8")
        next(p for p in data["packages"] if p["source"] is None)["manifest_path"] = str(foreign)
        with self.assertRaisesRegex(RuntimeError, "foreign local"):
            probe.validate_cargo_graph(data, self.lock, root, vendor)

    def test_cargo_feature_edge_and_target_node_changes_fail(self):
        original, root, vendor = self.graph()
        for mode in ("feature", "edge", "duplicate", "missing"):
            with self.subTest(change=mode):
                bad = deepcopy(original)
                rows = bad["resolve"]["nodes"]
                if mode == "feature":
                    rows[0]["features"].append("unreviewed-feature")
                elif mode == "edge":
                    next(p for p in rows if p["deps"])["deps"].pop()
                elif mode == "duplicate":
                    rows[-1] = deepcopy(rows[0])
                else:
                    rows.pop()
                with self.assertRaises(RuntimeError):
                    probe.validate_cargo_graph(bad, self.lock, root, vendor)

    def test_complete_original_runtime_has_exact_seven_nodes_six_edges(self):
        result = probe.validate_runtime_closure(self.lock, self.manifest(), self.lock["environment"])
        self.assertEqual((result["distribution_count"], result["active_edge_count"]), (7, 6))
        self.assertEqual(result["selected_extras"], [])

    def test_missing_extra_or_duplicate_runtime_distributions_fail(self):
        for mode in ("missing", "extra", "duplicate", "name-only"):
            with self.subTest(change=mode):
                manifest = self.manifest()
                if mode == "missing":
                    manifest["wheels"].pop()
                elif mode == "extra":
                    manifest["wheels"].append({"name": "unexpected"})
                elif mode == "duplicate":
                    manifest["wheels"][-1] = deepcopy(manifest["wheels"][0])
                else:
                    manifest["names"][-1] = "unexpected"
                with self.assertRaises(RuntimeError):
                    probe.validate_runtime_closure(self.lock, manifest, self.lock["environment"])

    def test_original_full_metadata_including_inactive_extras_cannot_be_stripped(self):
        for name in ("tiktoken", "requests", "idna", "urllib3"):
            with self.subTest(distribution=name):
                manifest = self.manifest()
                package = next(p for p in manifest["wheels"] if p["name"] == name)
                package["requires_dist"] = [r for r in package["requires_dist"] if ";" not in r]
                with self.assertRaisesRegex(RuntimeError, "full runtime metadata"):
                    probe.validate_runtime_closure(self.lock, manifest, self.lock["environment"])

    def test_runtime_version_python_bound_or_active_requirement_changes_fail(self):
        for key, value in (("version", "0.14.1"), ("requires_python", ">=3.10,<3.14"),
                           ("requires_dist", ["regex", "requests[socks]"]),
                           ("requires_dist", ["regex", "requests; python_version < '3.14'"])):
            with self.subTest(field=key, value=value):
                manifest = self.manifest()
                next(p for p in manifest["wheels"] if p["name"] == "tiktoken")[key] = value
                with self.assertRaises(RuntimeError):
                    probe.validate_runtime_closure(self.lock, manifest, self.lock["environment"])

    def test_runtime_actual_android_python_markers_are_enforced(self):
        for key, value in (("python_full_version", "3.13.0"), ("sys_platform", "linux"),
                           ("platform_machine", "x86_64"), ("platform_system", "Linux")):
            with self.subTest(marker=key):
                environment = {**self.lock["environment"], key: value}
                with self.assertRaisesRegex(RuntimeError, "marker environment"):
                    probe.validate_runtime_closure(self.lock, self.manifest(), environment)

    def test_abi3_stub_or_unlinked_cp314_extension_is_not_accepted(self):
        for needed in ([], ["libpython3.so", "libc.so"], ["libpython3.14.so", "libc.so.6"]):
            with self.subTest(needed=needed):
                with self.assertRaises(RuntimeError):
                    probe.require_python_linkage([{"needed": needed}])
        probe.require_python_linkage([{"needed": ["libpython3.14.so", "libc.so", "libm.so", "libdl.so"]}])

    def test_unreviewed_component_name_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Unreviewed source"):
            own.source_record(self.lock, "tokenizers")

    def test_existing_output_is_preserved(self):
        out = self.work / "existing"
        out.mkdir()
        sentinel = out / "sentinel"
        sentinel.write_bytes(b"owned-existing-data")
        with self.assertRaisesRegex(RuntimeError, "fresh input"):
            own.prepare(out, ROOT / "audit/neutts-runtime-index-20261017")
        self.assertEqual(sentinel.read_bytes(), b"owned-existing-data")

    def test_output_cannot_overlap_read_only_input_cache(self):
        cache = self.work / "cache"
        cache.mkdir()
        with self.assertRaisesRegex(RuntimeError, "overlaps"):
            own.prepare(cache / "new-output", ROOT / "audit/neutts-runtime-index-20261017", [cache])
        self.assertFalse((cache / "new-output").exists())

    def test_changed_shared_helper_is_rejected_before_import(self):
        path = self.work / "helper.py"
        path.write_bytes(b"raise AssertionError('must never execute')\n")
        with self.assertRaisesRegex(RuntimeError, "Shared helper bytes changed"):
            probe.module_at("_unreviewed_helper", path, "0" * 64)

    def test_selected_shared_helpers_are_bound_to_actual_bytes(self):
        _, rust, selected, apt = probe.helpers()
        self.assertEqual(selected.LOCK_SHA256, self.lock["references"]["rust_lock"]["sha256"])
        self.assertEqual(rust.PREFIX, Path("/data/data/com.termux/files/usr"))


    def test_only_measured_generated_manifest_body_is_allowed_after_build(self):
        for name, original_count in (("tiktoken", 36), ("regex", 22)):
            with self.subTest(source=name):
                root = self.source(name)
                before = own.verify_build_tree(root, name, self.lock, prep)
                self.assertEqual(before["original_files_byte_identical"], original_count)
                pin = self.lock["allowed_generated_source_manifests"][name]
                (root / pin["path"]).write_bytes((ROOT / pin["replay_evidence"]).read_bytes())
                after = own.verify_build_tree(root, name, self.lock, prep)
                self.assertEqual(after["original_files_byte_identical"], original_count - 1)
                self.assertEqual(len(after["allowed_generated_source_manifests"]), 1)
                with self.assertRaises(RuntimeError):
                    own.verify_source_tree(root, name, self.lock, prep)

    def test_generated_manifest_exception_cannot_hide_an_extra_path(self):
        for name in ("tiktoken", "regex"):
            with self.subTest(source=name):
                root = self.source(name)
                pin = self.lock["allowed_generated_source_manifests"][name]
                (root / pin["path"]).write_bytes((ROOT / pin["replay_evidence"]).read_bytes() + b"foreign.py\n")
                with self.assertRaisesRegex(RuntimeError, "Unreviewed change"):
                    own.verify_build_tree(root, name, self.lock, prep)

    def test_native_build_metadata_must_remain_byte_identical_even_when_host_uses_crlf(self):
        for name in ("tiktoken", "regex"):
            with self.subTest(source=name):
                root = self.source(name)
                path = root / (name + ".egg-info/PKG-INFO")
                path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
                with self.assertRaises(RuntimeError):
                    own.verify_build_tree(root, name, self.lock, prep)

    def test_generated_manifest_permission_does_not_allow_source_code_change(self):
        root = self.source()
        pin = self.lock["allowed_generated_source_manifests"]["tiktoken"]
        (root / pin["path"]).write_bytes((ROOT / pin["replay_evidence"]).read_bytes())
        path = root / "src/lib.rs"
        path.write_bytes(path.read_bytes() + b"\n// changed after verification\n")
        with self.assertRaises(RuntimeError):
            own.verify_build_tree(root, "tiktoken", self.lock, prep)

    def test_build_tree_requires_the_same_approved_cargo_lock(self):
        root = self.source()
        path = root / "Cargo.lock"
        path.write_bytes(path.read_bytes() + b"\n# new resolution\n")
        with self.assertRaises(RuntimeError):
            own.verify_build_tree(root, "tiktoken", self.lock, prep)


if __name__ == "__main__":
    unittest.main()
