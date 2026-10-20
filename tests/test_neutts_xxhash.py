"""Host integrity negatives only; actual Android operations have a separate native gate."""
from __future__ import annotations

import ast
import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = module_at("_tested_xxhash_preparer", ROOT / "scripts/prepare_neutts_xxhash.py")
probe = module_at("_tested_xxhash_probe", ROOT / "scripts/compatibility_probe_neutts_xxhash.py")


def regenerate_record(site, record_name):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for path in sorted(p for p in site.rglob("*") if p.is_file()):
        name = path.relative_to(site).as_posix()
        if name == record_name:
            writer.writerow((name, "", ""))
        else:
            raw = path.read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
            writer.writerow((name, "sha256=" + digest, str(len(raw))))
    (site / record_name).write_text(buffer.getvalue(), encoding="utf-8", newline="\n")


class ExactInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xxhash-integrity-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.lock = prep.load_lock()
        self.wheel = prep.AUDIT_DIR / self.lock["package"]["artifact"]["filename"]

    def test_exact_original_wheel_replay_preserves_archive(self):
        out = self.work / "prepared"
        receipt = prep.prepare(out, self.wheel)
        lock, wheel, proof = prep.verify_inputs(out)
        self.assertEqual(wheel.read_bytes(), self.wheel.read_bytes())
        self.assertEqual(proof, receipt["wheel"])
        self.assertEqual(lock["original_package"]["requires_dist"], [])
        self.assertFalse(receipt["installed"])
        self.assertFalse(receipt["native_operations_proved"])

    def test_original_and_core_inventory_encodings_are_both_checked(self):
        with zipfile.ZipFile(self.wheel) as archive:
            names = "\n".join(sorted(archive.namelist()))
        self.assertEqual(hashlib.sha256(names.encode()).hexdigest(),
                         self.lock["original_package"]["wheel"]["members_sha256"])
        self.assertEqual(hashlib.sha256((names + "\n").encode()).hexdigest(),
                         self.lock["package"]["wheel"]["members_sha256"])
        changed = copy.deepcopy(self.lock)
        changed["original_package"]["wheel"]["members_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "Original public member inventory"):
            prep.verify_wheel(self.wheel, changed)

    def test_existing_output_is_never_overwritten(self):
        out = self.work / "existing"
        out.mkdir()
        sentinel = out / "sentinel"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(RuntimeError, "new input directory"):
            prep.prepare(out, self.wheel)
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_corrupt_archive_rejected_before_creating_output(self):
        raw = self.wheel.read_bytes()
        mutations = (raw[:-1], raw + b"x", raw[:100] + bytes([raw[100] ^ 1]) + raw[101:])
        for index, data in enumerate(mutations):
            with self.subTest(mutation=index):
                bad = self.work / ("bad-" + str(index) + ".whl")
                bad.write_bytes(data)
                out = self.work / ("out-" + str(index))
                with self.assertRaises(RuntimeError):
                    prep.prepare(out, bad)
                self.assertFalse(out.exists())

    def test_unowned_prepared_file_rejected(self):
        out = self.work / "prepared"
        prep.prepare(out, self.wheel)
        (out / "extra.pth").write_bytes(b"import unknown\n")
        with self.assertRaisesRegex(RuntimeError, "exactly"):
            prep.verify_inputs(out)

    def test_false_prepared_scope_claims_rejected(self):
        for field in ("native_operations_proved", "installed", "model_downloaded", "release_output"):
            with self.subTest(field=field):
                out = self.work / field
                prep.prepare(out, self.wheel)
                path = out / prep.RECEIPT_NAME
                receipt = json.loads(path.read_bytes())
                receipt[field] = True
                path.write_text(json.dumps(receipt), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "receipt differs"):
                    prep.verify_inputs(out)

    def test_changed_helper_is_rejected_before_import(self):
        lock = copy.deepcopy(self.lock)
        lock["foundation"]["helpers"]["prepare_neutts_core_python.py"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "helper changed"):
            prep.helper("prepare_neutts_core_python.py", lock)

    def test_fixed_vector_constants_match_original_upstream_tests(self):
        # Independent primary source literals, not an oracle produced by our gate
        # or by any host/native XXHash binary.
        for algorithm, (_, _, expected) in probe.FIXED_VECTORS.items():
            with self.subTest(algorithm=algorithm):
                tree = ast.parse((prep.AUDIT_DIR / "upstream" / ("test_" + algorithm + ".py")).read_bytes())
                function = next(n for n in ast.walk(tree)
                                if isinstance(n, ast.FunctionDef) and n.name == "test_" + algorithm)
                calls = [n.value for n in function.body if isinstance(n, ast.Expr)]
                values = tuple(ast.literal_eval(call.args[1]) for call in calls)
                self.assertEqual(values, (expected[0], *expected))
                for call in calls:
                    constructor = call.args[0].func.value
                    self.assertEqual(constructor.func.attr, algorithm)
                    self.assertEqual(ast.literal_eval(constructor.args[0]), b"a")


class InstalledFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xxhash-installed-")
        self.addCleanup(self.temporary.cleanup)
        self.site = Path(self.temporary.name) / "site"
        self.site.mkdir()
        self.lock = prep.load_lock()
        self.wheel = prep.AUDIT_DIR / self.lock["package"]["artifact"]["filename"]
        prep.verify_wheel(self.wheel, self.lock)
        # File-integrity fixture only; no Android extension is imported on the host.
        with zipfile.ZipFile(self.wheel) as archive:
            for item in archive.infolist():
                if not item.is_dir():
                    path = self.site / item.filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(item))
        self.info = self.site / "xxhash-4.0.1.dist-info"
        (self.info / "INSTALLER").write_bytes(b"pip\n")
        (self.info / "REQUESTED").write_bytes(b"")
        digest = self.lock["package"]["artifact"]["sha256"]
        (self.info / "direct_url.json").write_text(json.dumps({
            "url": self.wheel.resolve().as_uri(),
            "archive_info": {"hashes": {"sha256": digest}},
        }), encoding="utf-8")
        self.record = self.lock["package"]["wheel"]["record_member"]
        regenerate_record(self.site, self.record)

    def check(self):
        return probe.verify_installed(self.wheel, self.site, self.lock, prep)

    def test_complete_original_members_and_truthful_record_accepted(self):
        proof = self.check()
        self.assertEqual(proof["original_files_verified"], 9)
        self.assertEqual(proof["installed_file_count"], 13)
        self.assertTrue(proof["complete_installed_record_verified"])

    def test_changed_extension_rejected_even_with_rewritten_record(self):
        path = self.site / self.lock["original_package"]["native_elf_members"][0]["path"]
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        regenerate_record(self.site, self.record)
        with self.assertRaisesRegex(RuntimeError, "wheel bytes changed"):
            self.check()

    def test_changed_metadata_rejected_even_with_rewritten_record(self):
        path = self.info / "METADATA"
        path.write_bytes(path.read_bytes().replace(b"Version: 4.0.1", b"Version: 4.0.2"))
        regenerate_record(self.site, self.record)
        with self.assertRaisesRegex(RuntimeError, "wheel bytes changed"):
            self.check()

    def test_missing_source_rejected(self):
        (self.site / "xxhash/__init__.py").unlink()
        regenerate_record(self.site, self.record)
        with self.assertRaisesRegex(RuntimeError, "member missing"):
            self.check()

    def test_extra_import_hook_rejected(self):
        (self.site / "unowned.pth").write_bytes(b"import unexpected\n")
        regenerate_record(self.site, self.record)
        with self.assertRaisesRegex(RuntimeError, "unowned"):
            self.check()

    def test_wrong_wheel_origin_rejected(self):
        path = self.info / "direct_url.json"
        data = json.loads(path.read_bytes())
        data["url"] = "file:///different/original.whl"
        path.write_text(json.dumps(data), encoding="utf-8")
        regenerate_record(self.site, self.record)
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            self.check()

    def test_duplicate_record_rejected(self):
        path = self.site / self.record
        with path.open("a", encoding="utf-8") as stream:
            stream.write(self.record + ",,\n")
        with self.assertRaisesRegex(RuntimeError, "exactly once"):
            self.check()

    def test_untruthful_installed_record_rejected(self):
        path = self.site / self.record
        data = path.read_text()
        index = data.index("sha256=") + len("sha256=")
        path.write_text(data[:index] + ("A" if data[index] != "A" else "B") + data[index + 1:],
                        encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "RECORD hash differs"):
            self.check()


class FailureBoundaryTests(unittest.TestCase):
    def test_wrong_digest_representation_is_never_a_pass(self):
        for bad in ("integer", "bytes", "hex"):
            with self.subTest(field=bad):
                value = SimpleNamespace(
                    intdigest=lambda: 43 if bad == "integer" else 42,
                    digest=lambda: b"\x00\x00\x00+" if bad == "bytes" else b"\x00\x00\x00*",
                    hexdigest=lambda: "0000002b" if bad == "hex" else "0000002a")
                with self.assertRaisesRegex(RuntimeError, "Fixed vector"):
                    probe.check_digests(value, 42, 4, "deliberately wrong host unit fixture")

    def test_library_origin_changes_are_rejected(self):
        lock = prep.load_lock()
        member = lock["original_package"]["native_elf_members"][0]
        extension = PurePosixPath("/owned/site") / member["path"]
        own = {"path": str(extension), "bytes": member["bytes"], "sha256": member["sha256"]}
        foundation = [{"path": "/owned/lib/" + name, "bytes": 123,
                       "sha256": str(index) * 64, "dpkg_owners": ["fixture-owner"]}
                      for index, name in enumerate(member["elf"]["needed"])]
        libraries = [own, *copy.deepcopy(foundation)]
        # These are policy-unit records only, never a fabricated native receipt.
        probe.library_provenance(libraries, foundation, extension, lock)
        for mutation in ("wrong-extension", "wrong-dependency", "missing", "duplicate", "unowned"):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(libraries)
                if mutation == "wrong-extension":
                    rows[0]["sha256"] = "f" * 64
                elif mutation == "wrong-dependency":
                    rows[1]["sha256"] = "f" * 64
                elif mutation == "missing":
                    rows.pop()
                elif mutation == "duplicate":
                    rows.append(copy.deepcopy(rows[-1]))
                else:
                    rows[1]["dpkg_owners"] = []
                with self.assertRaises(RuntimeError):
                    probe.library_provenance(rows, foundation, extension, lock)

    def test_host_cannot_claim_native_success(self):
        lock = prep.load_lock()
        native = prep.helper("compatibility_probe_neutts_native.py", lock)
        with tempfile.TemporaryDirectory(prefix="xxhash-host-rejection-") as tmp:
            out = Path(tmp) / "result"
            args = SimpleNamespace(out=out, foundation_receipt=Path(tmp) / "absent",
                                   inputs=Path(tmp) / "not-used")
            code = probe.run(args, lock, Path(tmp) / "not-used.whl", prep, native, None)
            receipt = json.loads((out / "XXHASH-COMPONENT-RESULT.json").read_bytes())
            self.assertEqual(code, 1)
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["stage"], "preflight")
            self.assertEqual(receipt["commands"], [])
            self.assertIn("Real native Bionic", receipt["error"]["message"])
            self.assertNotIn("runtime_receipt", receipt)

    def test_real_child_failure_preserves_logs(self):
        with tempfile.TemporaryDirectory(prefix="xxhash-child-") as tmp:
            out = Path(tmp)
            result = probe.bounded([sys.executable, "-I", "-B", "-c",
                                    "import sys; print('actual child failure'); sys.exit(7)"],
                                   out, "failure", 10, dict(os.environ), out)
            self.assertEqual(result["exit_code"], 7)
            self.assertFalse(result["timed_out"])
            self.assertIn(b"actual child failure", (out / "failure.stdout.log").read_bytes())

    def test_real_child_timeout_is_failure(self):
        with tempfile.TemporaryDirectory(prefix="xxhash-timeout-") as tmp:
            out = Path(tmp)
            result = probe.bounded([sys.executable, "-I", "-B", "-c",
                                    "import time; time.sleep(10)"],
                                   out, "timeout", 0.2, dict(os.environ), out)
            self.assertEqual(result["exit_code"], 124)
            self.assertTrue(result["timed_out"])


if __name__ == "__main__":
    unittest.main()
