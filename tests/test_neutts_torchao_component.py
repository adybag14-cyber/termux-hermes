"""Input-integrity and independent-oracle checks; native TorchAO is a separate CI gate."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = module_at("_tested_torchao_prep", ROOT / "scripts/prepare_neutts_torchao.py")
probe = module_at("_tested_torchao_probe", ROOT / "scripts/compatibility_probe_neutts_torchao.py")


def fixture_inputs():
    value = os.environ.get("TORCHAO_COMPONENT_INPUTS")
    if not value:
        raise unittest.SkipTest("Set TORCHAO_COMPONENT_INPUTS to the exact prepared one-wheel fixture")
    inputs = Path(value)
    lock, wheel, _ = prep.verify_inputs(inputs)
    return inputs, lock, wheel


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
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.lock, cls.wheel = fixture_inputs()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="torchao-input-check-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def copy_inputs(self):
        target = self.work / "inputs"
        shutil.copytree(self.inputs, target)
        return target

    def test_real_wheel_preparation_and_replay(self):
        out = self.work / "prepared"
        receipt = prep.prepare(out, self.wheel)
        lock, wheel, proof = prep.verify_inputs(out)
        self.assertEqual(wheel.read_bytes(), self.wheel.read_bytes())
        self.assertEqual(proof, receipt["wheel"])
        self.assertEqual(lock, self.lock)
        self.assertFalse(receipt["installed"])

    def test_existing_output_cannot_be_reused(self):
        out = self.work / "existing"
        out.mkdir()
        sentinel = out / "owned-by-another-step.txt"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(prep.PrepareError, "new input directory"):
            prep.prepare(out, self.wheel)
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_corrupt_cached_wheel_rejected_before_output_creation(self):
        bad = self.work / self.wheel.name
        raw = bytearray(self.wheel.read_bytes())
        raw[len(raw) // 2] ^= 1
        bad.write_bytes(raw)
        with self.assertRaises(RuntimeError):
            prep.prepare(self.work / "uncreated", bad)
        self.assertFalse((self.work / "uncreated").exists())

    def test_changed_lock_bytes_rejected(self):
        inputs = self.copy_inputs()
        with (inputs / prep.LOCK_NAME).open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(prep.PrepareError, "lock changed"):
            prep.verify_inputs(inputs)

    def test_unowned_import_hook_rejected(self):
        inputs = self.copy_inputs()
        (inputs / "extra.pth").write_bytes(b"import unexpected_module\n")
        with self.assertRaisesRegex(prep.PrepareError, "exactly"):
            prep.verify_inputs(inputs)

    def test_false_installation_claim_rejected(self):
        inputs = self.copy_inputs()
        path = inputs / prep.RECEIPT_NAME
        receipt = json.loads(path.read_bytes())
        receipt["installed"] = True
        path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(prep.PrepareError, "receipt differs"):
            prep.verify_inputs(inputs)

    def test_incomplete_receipt_rejected(self):
        inputs = self.copy_inputs()
        path = inputs / prep.RECEIPT_NAME
        receipt = json.loads(path.read_bytes())
        receipt["source_members"].pop()
        path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(prep.PrepareError, "receipt differs"):
            prep.verify_inputs(inputs)


class InstalledFileBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.lock, cls.wheel = fixture_inputs()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="torchao-site-check-")
        self.addCleanup(self.temporary.cleanup)
        self.site = Path(self.temporary.name) / "site"
        self.site.mkdir()
        # This is a file-integrity fixture, not a package import or native-operation proof.
        prep.verify_wheel(self.wheel, self.lock)
        with zipfile.ZipFile(self.wheel) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                path = self.site / item.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(item))
        self.info = self.site / "torchao-0.12.0.dist-info"
        (self.info / "INSTALLER").write_bytes(b"pip\n")
        (self.info / "REQUESTED").write_bytes(b"")
        digest = self.lock["package"]["artifact"]["sha256"]
        (self.info / "direct_url.json").write_text(json.dumps({
            "url": self.wheel.resolve().as_uri(),
            "archive_info": {"hash": "sha256=" + digest, "hashes": {"sha256": digest}},
        }), encoding="utf-8")
        self.record_name = self.lock["package"]["wheel"]["record_member"]
        regenerate_record(self.site, self.record_name)

    def check(self):
        return probe.verify_installed(self.wheel, self.site, self.lock, prep)

    def test_complete_original_wheel_and_generated_record_accepted(self):
        report = self.check()
        self.assertEqual(report["original_files_verified"], 347)
        self.assertEqual(report["installed_file_count"], 351)
        self.assertTrue(report["complete_installed_record_verified"])

    def test_changed_source_is_rejected_even_with_rewritten_record(self):
        source = self.site / "torchao/__init__.py"
        with source.open("ab") as stream:
            stream.write(b"\n# modified\n")
        regenerate_record(self.site, self.record_name)
        with self.assertRaisesRegex(RuntimeError, "wheel bytes changed"):
            self.check()

    def test_missing_original_file_rejected(self):
        (self.site / "torchao/dtypes/nf4tensor.py").unlink()
        regenerate_record(self.site, self.record_name)
        with self.assertRaisesRegex(RuntimeError, "member missing"):
            self.check()

    def test_foreign_python_file_rejected(self):
        (self.site / "unowned.py").write_bytes(b"raise RuntimeError('not an input')\n")
        regenerate_record(self.site, self.record_name)
        with self.assertRaisesRegex(RuntimeError, "unowned"):
            self.check()

    def test_false_wheel_origin_rejected(self):
        path = self.info / "direct_url.json"
        value = json.loads(path.read_bytes())
        value["archive_info"]["hashes"]["sha256"] = "0" * 64
        path.write_text(json.dumps(value), encoding="utf-8")
        regenerate_record(self.site, self.record_name)
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            self.check()

    def test_duplicate_record_member_rejected(self):
        path = self.site / self.record_name
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(self.record_name + ",,\n")
        with self.assertRaisesRegex(RuntimeError, "exactly once"):
            self.check()

    def test_bad_record_digest_rejected(self):
        path = self.site / self.record_name
        text = path.read_text()
        index = text.index("sha256=") + len("sha256=")
        text = text[:index] + ("A" if text[index] != "A" else "B") + text[index + 1:]
        path.write_text(text, encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RuntimeError, "RECORD hash differs"):
            self.check()


class IndependentOracleTests(unittest.TestCase):
    def test_exact_codebook_pack_order(self):
        values = list(map(probe.f32, probe.CODEBOOK)) * 1024
        self.assertEqual(probe.reference_packed(values),
                         [0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF] * 1024)

    def test_scalar_unpack_scale_and_nibble_order(self):
        values = probe.reference_dequantized([0x07, 0x8F] * 4096, [0] * 256, [2.0], 2.0)
        self.assertEqual(len(values), 16384)
        self.assertEqual(values[:4], [-2.0, 0.0, probe.f32(probe.f32(0.0796) * 2.0), 2.0])
        self.assertEqual(values[-4:], values[:4])

    def test_invalid_factor_or_shape_rejected(self):
        for packed, factors in (([0] * 8191, [1.0]), ([0] * 8192, [0.0]),
                                ([0] * 8192, [float("nan")])):
            with self.subTest(length=len(packed), factor=factors[0]):
                with self.assertRaises(RuntimeError):
                    probe.reference_dequantized(packed, [0] * 256, factors, 1.0)

    def test_actual_fixture_has_varied_blocks_and_quantization_error_margin(self):
        values = probe.weight_values()
        self.assertEqual(len(values), 16384)
        scales = [max(map(abs, values[i:i + 64])) for i in range(0, len(values), 64)]
        self.assertEqual(len(set(scales)), 256)
        packed = probe.reference_packed(values)
        codes = [code for byte in packed for code in (byte >> 4, byte & 15)]
        self.assertEqual(set(codes), set(range(16)))
        ideal = [probe.f32(probe.f32(probe.CODEBOOK[code]) * scales[i // 64])
                 for i, code in enumerate(codes)]
        relative = math.sqrt(sum((a - b) ** 2 for a, b in zip(ideal, values))
                             / sum(value * value for value in values))
        self.assertGreater(relative, 0.02)
        self.assertLess(relative, 0.12)  # Margin below the native double-quantized bound, 0.16.


class ProcessEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="torchao-process-check-")
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name)

    def test_real_child_failure_preserves_complete_logs(self):
        command = [sys.executable, "-I", "-B", "-c",
                   "import sys; print('fixture stdout'); print('fixture stderr', file=sys.stderr); sys.exit(7)"]
        row = probe.bounded(command, self.out, "failed-child", 10, dict(os.environ), self.out)
        self.assertEqual(row["exit_code"], 7)
        self.assertFalse(row["timed_out"])
        for channel in ("stdout", "stderr"):
            data = (self.out / row["logs"][channel]["path"]).read_bytes()
            self.assertEqual(row["logs"][channel]["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(row["logs"][channel]["bytes"], len(data))
            self.assertFalse(row["logs"][channel]["truncated"])
            self.assertIn(("fixture " + channel).encode(), data)

    def test_real_child_timeout_cannot_be_reported_as_pass(self):
        command = [sys.executable, "-I", "-B", "-c",
                   "import time; print('started', flush=True); time.sleep(8)"]
        row = probe.bounded(command, self.out, "timeout-child", 1, dict(os.environ), self.out)
        self.assertEqual(row["exit_code"], 124)
        self.assertTrue(row["timed_out"])


if __name__ == "__main__":
    unittest.main()
