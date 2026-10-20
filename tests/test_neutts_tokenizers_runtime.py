"""Host checks for original input selection and the owned native network barrier.

These tests inspect original metadata/archive bytes and exercise rejection paths.
They do not execute native Android extensions or certify the native runtime.
"""
from __future__ import annotations
import ast
import copy
from email.parser import BytesParser
from email.policy import compat32
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit/neutts-tokenizers-runtime-preparation-20261020"
ENVIRONMENT = {
    "extra": "", "implementation_name": "cpython", "implementation_version": "3.14.6",
    "os_name": "posix", "platform_machine": "aarch64",
    "platform_python_implementation": "CPython", "platform_system": "Android",
    "python_full_version": "3.14.6", "python_version": "3.14", "sys_platform": "android",
}

def load(filename):
    spec = importlib.util.spec_from_file_location("_tokenizers_tests_" + filename[:-3], ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

prep = load("prepare_neutts_tokenizers_runtime.py")
probe = load("compatibility_probe_neutts_tokenizers_runtime.py")

def original_selection():
    raw = (AUDIT / "original-rust-subset-handoff.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != "42d47b3fe4f8858d94d69a5216db1253e75d05437c9ffad42651369130252768":
        raise AssertionError("Original handoff changed")
    value = json.loads(raw)
    return {
        "schema_version": 1, "status": "reviewed-native-handoffs",
        "node_count": value["node_count"], "edge_count": value["edge_count"],
        "packages": copy.deepcopy(value["nodes"]), "edges": copy.deepcopy(value["edges"]),
        "names": sorted(row["name"] for row in value["nodes"]),
        "roots": ["fsspec", "safetensors", "tokenizers"], "environment": dict(ENVIRONMENT),
        "handoff": {"sha256": prep.HANDOFF_SHA256}, "frozen_graph": {"sha256": prep.GRAPH_SHA256},
        "apt_archives": [{"name": "libyaml"}, {"name": "libgmp"}], "apt_install_names": ["libyaml"],
    }

def shell_python_blocks():
    text = (ROOT / "scripts/compatibility_probe_neutts_tokenizers_runtime.sh").read_text()
    return {tag: body for tag, body in re.findall(r"<<'(PY_[A-Z]+)'\n(.*?)\n\1(?:\n|$)", text, re.S)}

def original_archive_pins():
    raw = gzip.decompress((ROOT / "audit/neutts-runtime-index-20261017/Packages.gz").read_bytes())
    wanted = {}
    for block in raw.split(b"\n\n"):
        if not block.strip():
            continue
        value = BytesParser(policy=compat32).parsebytes(block)
        if value.get("Package") not in {"libyaml", "libgmp"}:
            continue
        pin = {"name": value["Package"], "version": value["Version"],
               "architecture": value["Architecture"], "bytes": int(value["Size"]),
               "sha256": value["SHA256"], "filename": value["Filename"],
               "depends": value.get("Depends", ""), "pre_depends": value.get("Pre-Depends", "")}
        wanted[pin["name"]] = pin
    if set(wanted) != {"libyaml", "libgmp"}:
        raise AssertionError("Original signed index selection differs")
    return wanted

class OriginalClosureTests(unittest.TestCase):
    def check(self, lock, environment=None):
        with patch("packaging.markers.default_environment", return_value=environment or dict(ENVIRONMENT)):
            return probe.closure(lock)

    def test_original_25_node_29_edge_metadata_reaches_every_selected_distribution(self):
        result = self.check(original_selection())
        self.assertEqual((result["node_count"], result["edge_count"]), (25, 29))
        self.assertFalse(result["original_metadata_modified"])

    def test_reject_actual_non_android_or_wrong_interpreter_environment(self):
        for key, value in (("sys_platform", "linux"), ("platform_machine", "x86_64"),
                           ("python_full_version", "3.13.9"), ("python_version", "3.13"),
                           ("platform_system", "Linux")):
            with self.subTest(key=key):
                actual = {**ENVIRONMENT, key: value}
                with self.assertRaisesRegex(RuntimeError, "marker environment"):
                    self.check(original_selection(), actual)

    def test_reject_missing_dependencies_version_conflicts_or_original_python_bound(self):
        for kind in ("missing", "version", "python"):
            lock = original_selection()
            if kind == "missing":
                lock["packages"] = [row for row in lock["packages"] if row["name"] != "httpcore"]
            else:
                target = next(row for row in lock["packages"] if row["name"] == "httpcore")
                target["version" if kind == "version" else "requires_python"] = "0.0.0" if kind == "version" else "<3.14"
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.check(lock)

    def test_reject_removed_extra_or_rewritten_edges(self):
        for kind in ("extra", "edge", "url", "duplicate"):
            lock = original_selection()
            if kind == "extra":
                next(row for row in lock["packages"] if row["name"] == "fsspec")["active_extras"] = []
            elif kind == "edge":
                lock["edges"].pop()
            elif kind == "url":
                next(row for row in lock["packages"] if row["name"] == "tokenizers")["requires_dist"].append(
                    "unreviewed @ https://example.invalid/package.whl")
            else:
                lock["edges"].append(copy.deepcopy(lock["edges"][0]))
            with self.subTest(kind=kind):
                if kind == "duplicate":
                    # Structural lock validation must reject duplicate source edge entries.
                    self.validate_lock(lock, rejected=True)
                else:
                    with self.assertRaises(RuntimeError):
                        self.check(lock)

    def validate_lock(self, lock, rejected=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            raw = (json.dumps(lock, sort_keys=True) + "\n").encode()
            path.write_bytes(raw)
            # This scoped fixture hash exercises structural validation only.
            # It does not alter the production lock or admit a native input.
            with patch.object(prep, "LOCK_SHA256", hashlib.sha256(raw).hexdigest()):
                if rejected:
                    with self.assertRaises(prep.PrepareError):
                        prep.load_lock(path)
                else:
                    parsed, actual = prep.load_lock(path)
                    self.assertEqual(actual, raw)
                    self.assertEqual(parsed["names"], lock["names"])

    def test_structural_lock_and_rejected_scope_expansion(self):
        self.validate_lock(original_selection())
        for kind in ("duplicate-node", "missing-node", "unreviewed-status", "roots", "apt-install", "handoff"):
            lock = original_selection()
            if kind == "duplicate-node":
                lock["packages"].append(copy.deepcopy(lock["packages"][0]))
            elif kind == "missing-node":
                lock["packages"].pop()
            elif kind == "unreviewed-status":
                lock["status"] = "pending-native-handoffs"
            elif kind == "roots":
                lock["roots"].append("neutts")
            elif kind == "apt-install":
                lock["apt_install_names"].append("clang")
            else:
                lock["handoff"]["sha256"] = "0" * 64
            with self.subTest(kind=kind):
                self.validate_lock(lock, rejected=True)

    def test_unreviewed_lock_bytes_are_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text('{"schema_version":1}')
            with self.assertRaisesRegex(prep.PrepareError, "lock changed"):
                prep.load_lock(path)

class OriginalInputTests(unittest.TestCase):
    def test_original_libyaml_and_gmp_control_and_hashes(self):
        for name, pin in original_archive_pins().items():
            path = AUDIT / "apt-archives" / (name + "_" + pin["version"] + "_" + pin["architecture"] + ".deb")
            with self.subTest(name=name):
                result = prep.verify_apt_archive(path, pin)
                self.assertEqual(result["sha256"], pin["sha256"])
                self.assertEqual(result["bytes"], pin["bytes"])
                self.assertRegex(result["control_sha256"], r"^[0-9a-f]{64}$")

    def test_reject_changed_archive_or_declared_control_identity(self):
        pin = original_archive_pins()["libyaml"]
        path = AUDIT / "apt-archives/libyaml_0.2.5-5_aarch64.deb"
        for field, value in (("sha256", "0" * 64), ("version", "0.0.0"),
                             ("architecture", "x86_64"), ("depends", "unreviewed")):
            altered = {**pin, field: value}
            with self.subTest(field=field), self.assertRaises((prep.PrepareError, RuntimeError)):
                prep.verify_apt_archive(path, altered)

    def test_input_paths_cannot_escape_audit_ownership(self):
        for value in ("../outside.whl", "audit/../outside.whl", "/audit/file.whl",
                      "scripts/file.whl", r"audit\file.whl"):
            with self.subTest(value=value), self.assertRaises(Exception):
                prep.repo_input(ROOT, value)
        self.assertEqual(prep.repo_input(ROOT, "audit/neutts-tokenizers-runtime-preparation-20261020/original-rust-subset-handoff.json"),
                         AUDIT / "original-rust-subset-handoff.json")

    def test_original_native_pyyaml_is_verified_without_loading_it(self):
        helper = prep.helper()
        path = AUDIT / "wheels/pyyaml-6.0.3-cp314-cp314-android_24_arm64_v8a.whl"
        facts = helper.wheel_facts(path)
        self.assertEqual(facts["artifact"]["sha256"],
                         "61eb9363ea29cdf0f49ecb3d965e54d59345dd0fb8c3d2aa6d22b07f9e71b851")
        self.assertEqual((facts["name"], facts["version"]), ("pyyaml", "6.0.3"))
        self.assertTrue(facts["native_members"])
        altered = copy.deepcopy(facts)
        altered["requires_python"] = ">=3.99"
        with self.assertRaises(RuntimeError):
            helper.verify_wheel(path, altered)

class NativeBarrierTests(unittest.TestCase):
    def test_embedded_python_compiles(self):
        blocks = shell_python_blocks()
        self.assertEqual(set(blocks), {"PY_INPUTS", "PY_NETWORK", "PY_RESULT"})
        for name, text in blocks.items():
            with self.subTest(name=name):
                ast.parse(text, filename=name)

    def test_owned_offline_signal_accepts_only_exact_disconnected_running_container(self):
        block = shell_python_blocks()["PY_NETWORK"]
        for bad in (None, "network", "stopped", "wrong-id", "lock", "duplicate"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                container_id = "a" * 64
                (out / "TOKENIZERS-CONTAINER-ID.txt").write_text(container_id + "\n")
                (out / "tokenizers-inputs").mkdir()
                raw_lock = b'{"fixture":"host-only-unit-test"}\n'
                (out / "tokenizers-inputs/neutts_tokenizers_runtime_lock.json").write_bytes(raw_lock)
                ready = {"schema_version": 1, "status": "ready-for-network-disconnect",
                         "lock_sha256": hashlib.sha256(raw_lock).hexdigest()}
                values = [{"Id": container_id, "State": {"Running": True}, "NetworkSettings": {"Networks": {}}}]
                if bad == "network":
                    values[0]["NetworkSettings"]["Networks"] = {"bridge": {}}
                elif bad == "stopped":
                    values[0]["State"]["Running"] = False
                elif bad == "wrong-id":
                    values[0]["Id"] = "b" * 64
                elif bad == "lock":
                    ready["lock_sha256"] = "0" * 64
                elif bad == "duplicate":
                    values.append(copy.deepcopy(values[0]))
                (out / "TOKENIZERS-NETWORK-READY.json").write_text(json.dumps(ready))
                (out / "TOKENIZERS-DISCONNECTED-CONTAINER.json").write_text(json.dumps(values))
                result = subprocess.run([sys.executable, "-I", "-B", "-c", block, str(out)],
                                        capture_output=True, timeout=10)
                signal = out / "TOKENIZERS-NETWORK-OFFLINE.json"
                if bad is None:
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    value = json.loads(signal.read_bytes())
                    self.assertEqual(value["remaining_networks"], {})
                    self.assertEqual(value["lock_sha256"], ready["lock_sha256"])
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(signal.exists())

    def test_actual_child_rejects_other_container_image_user_or_network(self):
        container_id, image_id, hostname = "a" * 64, "sha256:" + "b" * 64, "a" * 12
        original = {
            "Id": container_id, "Image": image_id, "State": {"Running": True},
            "NetworkSettings": {"Networks": {}},
            "Config": {"Hostname": hostname, "User": "1000:1000"},
            "HostConfig": {"NanoCpus": 2_000_000_000, "Memory": 6_442_450_944, "PidsLimit": 512},
        }
        self.assertEqual(probe.validate_disconnected_container(
            original, container_id, image_id, hostname), original)
        changes = [
            ("Id", None, "c" * 64), ("Image", None, "sha256:" + "c" * 64),
            ("State", "Running", False), ("NetworkSettings", "Networks", {"bridge": {}}),
            ("Config", "Hostname", "other"), ("Config", "User", "0:0"),
            ("HostConfig", "NanoCpus", 1_000_000_000), ("HostConfig", "Memory", 0),
            ("HostConfig", "PidsLimit", -1),
        ]
        for group, field, value in changes:
            changed = copy.deepcopy(original)
            if field is None:
                changed[group] = value
            else:
                changed[group][field] = value
            with self.subTest(group=group, field=field), self.assertRaises(RuntimeError):
                probe.validate_disconnected_container(changed, container_id, image_id, hostname)

    def test_workflow_is_read_only_finite_and_preparation_branch_only(self):
        import yaml
        value = yaml.load((ROOT / ".github/workflows/neutts-tokenizers-runtime.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(value["permissions"], {"contents": "read"})
        self.assertEqual(value["on"]["push"]["branches"], ["prepare/termux-compatibility-next-stable"])
        job = value["jobs"]["native-tokenizers-runtime"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04-arm")
        self.assertEqual(int(job["timeout-minutes"]), 45)
        self.assertEqual(len(job["steps"]), 3)
        for step in job["steps"]:
            if "uses" in step:
                self.assertRegex(step["uses"], r"^actions/(checkout|upload-artifact)@[0-9a-f]{40}$")
        self.assertEqual(job["steps"][0]["with"]["persist-credentials"], "false")

if __name__ == "__main__":
    unittest.main()
