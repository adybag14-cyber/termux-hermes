"""Exact original NeuCodec wheel/patch tests; no model imports or downloads."""
from __future__ import annotations
import ast
import base64
import copy
import csv
from email.parser import BytesParser
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "_neucodec_wheel_test_support", ROOT / "scripts/prepare_neucodec_wheel.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class FrozenFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = HELPER.load_lock()
        cls.original = ROOT / cls.lock["original_wheel_path"]
        cls.sdist = ROOT / cls.lock["source_archive"]["path"]
        cls.patch = (ROOT / cls.lock["patch"]["path"]).read_bytes()
        cls.sources = HELPER.source_contents(cls.sdist, cls.lock)
        cls.patched = HELPER.patched_sources(cls.sources, cls.patch, cls.lock)

    def test_original_official_artifact_and_source_share_every_package_member(self):
        proof = HELPER.verify_wheel(self.original, self.lock, upstream=True)
        self.assertEqual(proof["members_verified"], 20)
        content = HELPER.bind_original_source(self.original, self.sources, self.lock)
        self.assertEqual(len([n for n in content if n.startswith("neucodec/")]), 16)
        self.assertEqual(len(self.sources), 20)
        self.assertEqual(content["neucodec-0.0.4.dist-info/METADATA"], self.sources["PKG-INFO"])
        self.assertEqual(content["neucodec-0.0.4.dist-info/licenses/LICENSE"], self.sources["LICENSE"])
        meta = BytesParser().parsebytes(content["neucodec-0.0.4.dist-info/METADATA"])
        self.assertEqual(meta["Name"], "neucodec")
        self.assertEqual(meta["Version"], "0.0.4")
        self.assertEqual(meta["Requires-Python"], ">=3.10,<4.0")
        self.assertEqual(len(meta.get_all("Requires-Dist")), 8)
        self.assertIn("vector-quantize-pytorch (==1.17.8)", meta.get_all("Requires-Dist"))

    def test_exact_derivative_has_only_model_and_record_changes(self):
        raw = HELPER.derived_bytes(self.original, self.patched, self.lock)
        self.assertEqual(len(raw), 87563)
        self.assertEqual(HELPER.digest(raw),
                         "73fa4fd88856aaec3eba2b701a32916939acb54099279a8478732daaf16f7b96")
        with zipfile.ZipFile(self.original) as before, zipfile.ZipFile(io.BytesIO(raw)) as after:
            self.assertEqual(before.namelist(), after.namelist())
            changes = [n for n in before.namelist() if before.read(n) != after.read(n)]
            self.assertEqual(set(changes), {HELPER.MODEL, HELPER.RECORD})
            self.assertFalse(any(n.startswith("tests/") for n in after.namelist()))
            self.assertEqual(after.read(HELPER.MODEL), self.patched[HELPER.MODEL])
            self.assertEqual(after.read("neucodec-0.0.4.dist-info/WHEEL"),
                             b"Wheel-Version: 1.0\nGenerator: poetry-core 2.2.1\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
            self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in after.infolist()))
        self.assertEqual(raw, HELPER.derived_bytes(self.original, self.patched, self.lock))

    def test_complete_original_patch_including_tests_is_applied(self):
        self.assertEqual(len(self.patched), 21)
        changed = [n for n in self.sources if self.patched[n] != self.sources[n]]
        self.assertEqual(changed, [HELPER.MODEL])
        self.assertEqual(self.patched["pyproject.toml"], self.sources["pyproject.toml"])
        self.assertEqual(self.patched["PKG-INFO"], self.sources["PKG-INFO"])
        self.assertEqual(len(self.patched[HELPER.PATCH_TEST]), 11180)
        tree = ast.parse(self.patched[HELPER.MODEL])
        names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertTrue({"_hub_download_parameters", "_download_from_hub", "_HubDownloadCompat"} <= names)

    def test_source_patch_cannot_change_context_offsets_or_target(self):
        for before, after in [
            (b"--- a/neucodec/model.py", b"--- a/other/model.py"),
            (b"@@ -1,4 +1,5 @@", b"@@ -2,4 +1,5 @@"),
            (b"@@ -15,8 +16,39 @@", b"@@ -15,8 +17,39 @@"),
            (b" from pathlib import Path", b" from pathlib import OTHER"),
            (b"+import inspect\n", b"+import os\n"),
            (b"new file mode 100644", b"new file mode 100755"),
        ]:
            with self.subTest(change=before.decode()):
                patch = self.patch.replace(before, after, 1)
                self.assertNotEqual(patch, self.patch)
                lock = copy.deepcopy(self.lock)
                lock["patch"]["bytes"], lock["patch"]["sha256"] = len(patch), HELPER.digest(patch)
                with self.assertRaises(HELPER.PreparationError):
                    HELPER.patched_sources(self.sources, patch, lock)
        altered = dict(self.sources); altered[HELPER.MODEL] += b"\n"
        with self.assertRaises(HELPER.PreparationError):
            HELPER.patched_sources(altered, self.patch, self.lock)

    def test_corrupt_or_unreviewed_original_inputs_fail_before_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad"
            for data, kind in [(self.original.read_bytes(), "wheel"),
                               (self.sdist.read_bytes(), "source")]:
                with self.subTest(kind=kind):
                    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
                    with self.assertRaises(HELPER.PreparationError):
                        if kind == "wheel":
                            HELPER.verify_wheel(path, self.lock, upstream=True)
                        else:
                            HELPER.source_contents(path, self.lock)
            for patch in (self.patch + b"\n", self.patch[:-1], self.patch.replace(b"import inspect", b"import socket")):
                with self.subTest(length=len(patch)), self.assertRaises(HELPER.PreparationError):
                    HELPER.patched_sources(self.sources, patch, self.lock)

    def test_original_source_and_wheel_identity_must_agree(self):
        for name in (HELPER.MODEL, "PKG-INFO", "LICENSE"):
            with self.subTest(name=name):
                changed = dict(self.sources); changed[name] += b"\n"
                with self.assertRaises(HELPER.PreparationError):
                    HELPER.bind_original_source(self.original, changed, self.lock)

    def test_official_metadata_pin_and_scope_are_not_editable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "lock.json"
            for change in ("scope", "metadata", "wheel"):
                lock = copy.deepcopy(self.lock)
                if change == "scope": lock["scope"]["native_runtime_admitted"] = True
                elif change == "metadata": lock["upstream_package"]["requires_python"] = ">=3.10"
                else: lock["upstream_package"]["artifact"]["sha256"] = "0" * 64
                p.write_bytes(HELPER.encoded(lock))
                with self.subTest(change=change), self.assertRaises(HELPER.PreparationError):
                    HELPER.load_lock(p)

    def test_exact_preparation_works_without_network_and_verifies_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
                "socket.socket", side_effect=AssertionError("Preparation may not use network")):
            out = Path(tmp) / "prepared"
            receipt = HELPER.prepare(out)
            self.assertEqual(receipt, HELPER.verify_inputs(out))
            self.assertEqual(receipt["unchanged_original_wheel_members"], 18)
            for name in ("backend_build_performed", "installed", "native_runtime_admitted",
                         "model_download", "model_execution", "release_output"):
                self.assertIs(receipt[name], False)
            with self.assertRaises(HELPER.PreparationError):
                HELPER.prepare(out)

    def test_prepared_receipt_files_and_source_tampering_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "prepared"
            HELPER.prepare(out)
            receipt_path = out / HELPER.RECEIPT
            before = receipt_path.read_bytes()
            for key in ("native_runtime_admitted", "model_download", "backend_build_performed"):
                receipt = json.loads(before); receipt[key] = True
                receipt_path.write_bytes(HELPER.encoded(receipt))
                with self.subTest(key=key), self.assertRaises(HELPER.PreparationError):
                    HELPER.verify_inputs(out)
            receipt_path.write_bytes(before)
            extra = out / "surprise.py"; extra.write_bytes(b"")
            with self.assertRaises(HELPER.PreparationError): HELPER.verify_inputs(out)
            extra.unlink()
            extra.mkdir()
            with self.assertRaises(HELPER.PreparationError): HELPER.verify_inputs(out)
            extra.rmdir()
            source = out / "source/pyproject.toml"; source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaises(HELPER.PreparationError): HELPER.verify_inputs(out)

    def test_real_reviewed_downloader_regressions_and_original_failure(self):
        """The 34 reviewed tests use explicit recording fixtures, not native models."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "prepared"
            HELPER.prepare(out)
            test = out / "source" / HELPER.PATCH_TEST
            result = subprocess.run(
                [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test)],
                cwd=base, text=True, capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("34 passed", result.stdout)
            HELPER.verify_inputs(out)
            original_root = base / "original"
            (original_root / "neucodec").mkdir(parents=True)
            (original_root / HELPER.MODEL).write_bytes(self.sources[HELPER.MODEL])
            namespace = {"__file__": str(original_root / HELPER.PATCH_TEST), "__name__": "_original_neucodec_contract"}
            exec(compile(self.patched[HELPER.PATCH_TEST], str(test), "exec"), namespace)
            with self.assertRaisesRegex(TypeError, "proxies"):
                namespace["call_route"](("NeuCodec", "neuphonic/neucodec", "pytorch_model.bin"), "modern")

    def _write_wheel(self, directory, change):
        path = directory / "candidate.whl"
        with zipfile.ZipFile(self.original) as source, zipfile.ZipFile(path, "w") as dest:
            infos = source.infolist()
            for index, old in enumerate(infos):
                info = copy.copy(old); body = source.read(old)
                if index == 0:
                    if change == "alias": info.filename = "../" + info.filename
                    elif change == "symlink": info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    elif change == "compression": info.compress_type = zipfile.ZIP_BZIP2
                    elif change == "record": body += b"# altered source\n"
                dest.writestr(info, body)
            if change == "duplicate":
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    dest.writestr(infos[0], source.read(infos[0]))
        if change == "encrypted":
            raw = bytearray(path.read_bytes())
            offset = raw.index(b"PK\x01\x02")
            flags = struct.unpack_from("<H", raw, offset + 8)[0]
            struct.pack_into("<H", raw, offset + 8, flags | 1)
            path.write_bytes(raw)
        lock = copy.deepcopy(self.lock)
        data = path.read_bytes()
        lock["upstream_package"]["artifact"].update(bytes=len(data), sha256=HELPER.digest(data))
        if change == "record":
            with zipfile.ZipFile(path) as z:
                changed = {i.filename:z.read(i) for i in z.infolist()}
            lock["original_members"] = HELPER.content_manifest(changed)
        return path, lock

    def test_real_zip_headers_paths_duplicates_and_record_are_independently_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            for change in ("alias", "symlink", "compression", "duplicate", "encrypted", "record"):
                with self.subTest(change=change):
                    path, lock = self._write_wheel(Path(tmp), change)
                    with self.assertRaises(HELPER.PreparationError):
                        HELPER.verify_wheel(path, lock, upstream=True)

    def test_member_bounds_are_finite_even_with_changed_whole_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = copy.deepcopy(self.lock)
            lock["original_members"][0]["bytes"] = HELPER.MAX_MEMBER + 1
            with self.assertRaises(HELPER.PreparationError):
                HELPER.verify_wheel(self.original, lock, upstream=True)
            lock = copy.deepcopy(self.lock)
            for row in lock["original_members"]: row["bytes"] = HELPER.MAX_MEMBER
            with self.assertRaises(HELPER.PreparationError):
                HELPER.verify_wheel(self.original, lock, upstream=True)

    def test_tar_header_identity_type_and_size_checked_before_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            for change in ("path", "symlink", "duplicate", "size", "mode"):
                with self.subTest(change=change):
                    output = Path(tmp) / "bad.tar.gz"
                    with tarfile.open(output, "w:gz") as archive:
                        for index, (name, body) in enumerate(sorted(self.sources.items())):
                            item = tarfile.TarInfo("neucodec-0.0.4/" + name); item.mode = 0o644
                            if index == 0:
                                if change == "path": item.name = "neucodec-0.0.4/../escaped"
                                elif change == "symlink": item.type = tarfile.SYMTYPE; item.linkname = "elsewhere"; body = b""
                                elif change == "size": body = b"x" * (HELPER.MAX_MEMBER + 1)
                                elif change == "mode": item.mode = 0o755
                            item.size = len(body)
                            archive.addfile(item, io.BytesIO(body))
                            if index == 0 and change == "duplicate": archive.addfile(item, io.BytesIO(body))
                    lock = copy.deepcopy(self.lock); raw = output.read_bytes()
                    lock["source_archive"].update(bytes=len(raw), sha256=HELPER.digest(raw))
                    with self.assertRaises(HELPER.PreparationError):
                        HELPER.source_contents(output, lock)

    def test_unnormalized_archive_names_are_rejected(self):
        for name in ("../x", "/x", "a/../x", "./x", "a//b", "a\\b", "C:/x", "x\0y", ""):
            with self.subTest(name=name), self.assertRaises(HELPER.PreparationError):
                HELPER.safe_relative(name)


if __name__ == "__main__":
    unittest.main()
