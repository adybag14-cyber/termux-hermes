"""Host controls for retained original APT inputs; no native signature/runtime claim."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_neutts_apt_preparation", ROOT / "scripts/prepare_neutts_apt_snapshot.py")
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


def bash_path():
    if os.name == "nt":
        git = shutil.which("git")
        candidate = Path(git).parent.parent / "bin/bash.exe" if git else Path("missing-bash")
        if candidate.is_file():
            return str(candidate)
    candidate = shutil.which("bash")
    if not candidate:
        raise RuntimeError("Bash is required for the native bootstrap host controls")
    return candidate


class Response:
    status = 200

    def __init__(self, raw, length=None, url="https://packages.termux.dev/fixture.deb"):
        self.stream = io.BytesIO(raw)
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, count):
        return self.stream.read(count)

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, *args, **kwargs):
        self.calls += 1
        return self.response


class FrozenAptPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins, cls.foundation, cls.compiler = PREP.load_pins(ROOT, True)
        cls.foundation_pins = PREP.parse_tsv(cls.foundation)
        cls.python_pin = next(p for p in cls.pins if p["name"] == "python")
        cls.snapshot = ROOT / "audit/neutts-runtime-index-20261017"
        cls.packages = gzip.decompress((cls.snapshot / "Packages.gz").read_bytes())
        cls.python_archive = ROOT / "vendor/termux-preparation/apt-archives" / PREP.archive_name(cls.python_pin)

    def test_original_pins_and_both_profiles_match_real_signed_records(self):
        for compiler, count, total in [(False, 122, 173952336), (True, 141, 240783372)]:
            with self.subTest(compiler=compiler):
                pins, foundation, extra = PREP.load_pins(ROOT, compiler)
                self.assertEqual((len(pins), sum(p["bytes"] for p in pins)), (count, total))
                self.assertEqual(hashlib.sha256(foundation).hexdigest(), PREP.FOUNDATION_SHA256)
                self.assertEqual(PREP.verify_selected_index(self.packages, pins), count)
                self.assertEqual(set(PREP.verify_snapshot(self.snapshot, pins)), {"InRelease", "Packages.gz"})
                self.assertEqual(extra is not None, compiler)

    def test_epoch_names_preserve_original_identity(self):
        pin = next(p for p in self.pins if p["name"] == "fmt")
        before = copy.deepcopy(pin)
        self.assertEqual(PREP.archive_name(pin), "fmt_1%3A11.2.0-1_aarch64.deb")
        self.assertEqual(PREP.archive_name(pin, native=True), "fmt_1%3a11.2.0-1_aarch64.deb")
        self.assertEqual(pin, before)

    def test_tsv_rejects_duplicate_package_and_malformed_fields(self):
        first = self.foundation.splitlines(keepends=True)[0]
        for raw in [self.foundation + first, self.foundation[:-1], self.foundation.replace(b"\t", b" ", 1),
                    self.foundation.replace(b"\n", b"\r\n", 1)]:
            with self.subTest(prefix=raw[:40]), self.assertRaises(PREP.PrepareError):
                PREP.parse_tsv(raw)

    def test_archive_identity_rejects_path_aliases_and_invalid_epoch(self):
        for field, bad in [("filename", "../python.deb"), ("filename", "pool/main/p/../python/python_3.14.6-1_aarch64.deb"),
                           ("filename", "pool/main/p/python/python_3.14.6-1_aarch64.deb%00"),
                           ("version", "1:2:3"), ("architecture", "x86_64"), ("bytes", 0)]:
            pin = {**self.python_pin, field: bad}
            with self.subTest(field=field, bad=bad), self.assertRaises(PREP.PrepareError):
                PREP.archive_name(pin)

    def python_record(self):
        return next(p for p in self.packages.split(b"\n\n")
                    if p.startswith(b"Package: python\n") and b"\nVersion: 3.14.6-1\n" in p)

    def test_multi_version_package_name_remains_selectable(self):
        extra = self.python_record().replace(b"Version: 3.14.6-1\n", b"Version: 3.14.7-1\n")
        self.assertEqual(PREP.verify_selected_index(self.packages + b"\n\n" + extra + b"\n\n",
                                                   [self.python_pin]), 1)

    def test_duplicate_signed_identity_is_rejected(self):
        with self.assertRaisesRegex(PREP.PrepareError, "Duplicate package identity"):
            PREP.verify_selected_index(self.packages + b"\n\n" + self.python_record() + b"\n\n", [self.python_pin])

    def test_duplicate_signed_fields_and_orphan_continuation_are_rejected(self):
        record = self.python_record()
        for altered in [record + b"\nSHA256: " + b"0" * 64, record + b"\nsha256: " + b"0" * 64,
                        b" continuation\n" + record]:
            with self.subTest(raw=altered[-80:]), self.assertRaises(PREP.PrepareError):
                PREP.verify_selected_index(altered + b"\n\n", [self.python_pin])

    def test_selected_signed_size_hash_filename_and_architecture_are_bound(self):
        record = self.python_record()
        for old, new in [
            (b"Size: 4816756", b"Size: 4816757"),
            (self.python_pin["sha256"].encode(), b"0" * 64),
            (self.python_pin["filename"].encode(), b"pool/main/p/python/other.deb"),
            (b"Architecture: aarch64", b"Architecture: all"),
        ]:
            with self.subTest(old=old), self.assertRaises(PREP.PrepareError):
                PREP.verify_selected_index(record.replace(old, new) + b"\n\n", [self.python_pin])

    def test_changed_original_snapshot_bytes_are_rejected(self):
        for name in ("InRelease", "Packages.gz"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                for source in ("InRelease", "Packages.gz"):
                    shutil.copyfile(self.snapshot / source, directory / source)
                path = directory / name
                raw = path.read_bytes()
                path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
                with self.assertRaisesRegex(PREP.PrepareError, "snapshot bytes"):
                    PREP.verify_snapshot(directory, self.foundation_pins)

    def test_inrelease_must_bind_compressed_index_even_if_release_hash_is_reviewed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            raw = (self.snapshot / "InRelease").read_bytes()
            changed = raw.replace(PREP.SNAPSHOT["Packages.gz"]["sha256"].encode(), b"0" * 64)
            self.assertNotEqual(raw, changed)
            (directory / "InRelease").write_bytes(changed)
            shutil.copyfile(self.snapshot / "Packages.gz", directory / "Packages.gz")
            revised = copy.deepcopy(PREP.SNAPSHOT)
            revised["InRelease"]["sha256"] = hashlib.sha256(changed).hexdigest()
            with patch.object(PREP, "SNAPSHOT", revised), self.assertRaisesRegex(PREP.PrepareError, "does not bind"):
                PREP.verify_snapshot(directory, self.foundation_pins)

    def test_real_retained_python_is_copied_without_network(self):
        PREP.verify_file(self.python_archive, self.python_pin)
        with tempfile.TemporaryDirectory() as temp, patch.object(PREP, "build_opener", side_effect=AssertionError("network")):
            destination = Path(temp) / self.python_archive.name
            result = PREP.acquire_archive(self.python_pin, destination, [self.python_archive.parent])
            self.assertEqual(result["method"], "verified-retained-cache")
            self.assertEqual(PREP.verify_file(destination, self.python_pin), self.python_pin["sha256"])

    def test_corrupt_retained_python_fails_without_network_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            cache = directory / "cache"
            cache.mkdir()
            raw = self.python_archive.read_bytes()
            (cache / self.python_archive.name).write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            with patch.object(PREP, "build_opener", side_effect=AssertionError("network")):
                with self.assertRaisesRegex(PREP.PrepareError, "SHA256 differs"):
                    PREP.acquire_archive(self.python_pin, directory / self.python_archive.name, [cache])
            self.assertFalse((directory / self.python_archive.name).exists())

    def test_truncated_or_nonregular_cache_fails_without_network(self):
        for kind in ("short", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                cache = directory / "cache"
                cache.mkdir()
                candidate = cache / self.python_archive.name
                if kind == "short":
                    candidate.write_bytes(b"not the original archive")
                else:
                    candidate.mkdir()
                with patch.object(PREP, "build_opener", side_effect=AssertionError("network")):
                    with self.assertRaises(PREP.PrepareError):
                        PREP.acquire_archive(self.python_pin, directory / self.python_archive.name, [cache])

    def test_linked_cache_candidate_is_rejected(self):
        # lstat mode is the boundary; this also runs on Windows without needing
        # administrator permission to create a filesystem symlink.
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "archive.deb"
            candidate.write_bytes(b"test")
            info = candidate.lstat()
            altered = os.stat_result((0o120777, *tuple(info)[1:]))
            with patch.object(Path, "lstat", return_value=altered), self.assertRaises(PREP.PrepareError):
                PREP.verify_file(candidate, {"bytes": 4, "sha256": hashlib.sha256(b"test").hexdigest()})

    def test_https_download_checks_status_size_hash_and_effective_scheme(self):
        raw = b"explicit unit fixture, not a package"
        pin = {**self.python_pin, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for label, response, passes in [
            ("exact", Response(raw, len(raw)), True),
            ("short", Response(raw[:-1]), False),
            ("long", Response(raw + b"x"), False),
            ("hash", Response(raw[:-1] + b"x", len(raw)), False),
            ("length", Response(raw, len(raw) + 1), False),
            ("http", Response(raw, len(raw), "http://example.invalid/archive.deb"), False),
        ]:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                opener = Opener(response)
                target = Path(temp) / PREP.archive_name(pin)
                if passes:
                    result = PREP.acquire_archive(pin, target, [], opener=opener)
                    self.assertEqual(result["method"], "original-https-archive")
                else:
                    with self.assertRaises(PREP.PrepareError):
                        PREP.acquire_archive(pin, target, [], opener=opener)
                self.assertEqual(opener.calls, 1)

    def test_changed_prepared_receipt_and_unreviewed_layout_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "APT-PREPARED-INPUTS.json").write_text('{"status":"passed"}')
            with self.assertRaisesRegex(PREP.PrepareError, "preparation receipt"):
                PREP.verify_inputs(directory)

    def valid_receipt(self):
        return {
            "schema": "neutts-frozen-apt-preparation/v1", "status": "verified-original-inputs",
            "foundation_packages": 122, "compiler_packages": 44,
            "archive_count": len(self.pins), "archive_bytes": sum(p["bytes"] for p in self.pins),
            "foundation_tsv_sha256": PREP.FOUNDATION_SHA256, "compiler_tsv_sha256": PREP.COMPILER_TSV_SHA256,
            "snapshot": copy.deepcopy(PREP.SNAPSHOT), "packages_uncompressed_sha256": PREP.PACKAGES_SHA256,
            "selected_signed_index_records_verified": len(self.pins),
            "downloads": [{"filename": PREP.archive_name(p), "bytes": p["bytes"], "sha256": p["sha256"],
                           "origin_url": PREP.ORIGIN + p["filename"], "method": "original-https-archive",
                           "effective_url": PREP.ORIGIN + p["filename"]} for p in self.pins],
            "host_openpgp_verified": False, "native_apt_authentication_required": True,
            "package_install_performed": False, "pin_changes": False, "release_output": False,
        }

    def test_receipt_requires_original_identity_cardinality_and_honest_boundaries(self):
        valid = self.valid_receipt()
        PREP.verify_receipt(valid, self.pins, True)
        mutations = [
            lambda r: r["downloads"].pop(),
            lambda r: r["downloads"].append(copy.deepcopy(r["downloads"][0])),
            lambda r: r["downloads"].__setitem__(1, copy.deepcopy(r["downloads"][0])),
            lambda r: r["downloads"][0].update(filename="unreviewed.deb"),
            lambda r: r["downloads"][0].update(bytes=1),
            lambda r: r["downloads"][0].update(sha256="0" * 64),
            lambda r: r["downloads"][0].update(origin_url="https://example.invalid/changed.deb"),
            lambda r: r["downloads"][0].update(effective_url="http://example.invalid/archive.deb"),
            lambda r: r["downloads"][0].update(effective_url="https://user:password@example.invalid/archive.deb"),
            lambda r: r["downloads"][0].update(method="unverified"),
            lambda r: r["downloads"][0].update(signature_verified=True),
        ]
        for field in ["host_openpgp_verified", "package_install_performed", "pin_changes", "release_output"]:
            mutations.append(lambda r, field=field: r.update({field: True}))
        mutations.append(lambda r: r.update(native_apt_authentication_required=False))
        mutations.append(lambda r: r.update(native_runtime_verified=True))
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                altered = copy.deepcopy(valid)
                mutate(altered)
                with self.assertRaises(PREP.PrepareError):
                    PREP.verify_receipt(altered, self.pins, True)

    def test_receipt_cache_path_is_descriptive_but_bounded_and_method_specific(self):
        valid = self.valid_receipt()
        row = valid["downloads"][0]
        row.pop("effective_url")
        row.update(method="verified-retained-cache", cache_path=r"C:\retained\archive.deb")
        PREP.verify_receipt(valid, self.pins, True)
        for path in ["", "path\ninjection", "x" * 4097]:
            altered = copy.deepcopy(valid)
            altered["downloads"][0]["cache_path"] = path
            with self.subTest(path=path[:30]), self.assertRaises(PREP.PrepareError):
                PREP.verify_receipt(altered, self.pins, True)

    def test_native_plan_controls_execute_real_shell_against_original_pins(self):
        # Simulated plan text tests the rejection oracle; it is not native APT
        # solver evidence. The native workflow must still simulate and install.
        lines = [f"Inst {p['name']} ({p['version']} Termux:stable [{p['architecture']}])"
                 for p in self.foundation_pins]
        cases = {
            "exact": (lines, True),
            "architecture-qualified-name": ([lines[0].replace("Inst abseil-cpp ", "Inst abseil-cpp:aarch64 "), *lines[1:]], True),
            "removal": ([*lines, "Remv unrelated [1.0]"], False),
            "extra": ([*lines, "Inst unrelated (1.0 Termux:stable [all])"], False),
            "duplicate": ([*lines, lines[0]], False),
            "omission": (lines[1:], False),
            "wrong-version": ([lines[0].replace("20260526.0", "20260527.0"), *lines[1:]], False),
            "no-version": (["Inst abseil-cpp", *lines[1:]], False),
        }
        with tempfile.TemporaryDirectory(prefix="neutts-plan-") as temp:
            for name, (plan, passes) in cases.items():
                with self.subTest(name=name):
                    path = Path(temp) / (name + ".log")
                    path.write_text("\n".join(plan) + "\n", encoding="ascii", newline="\n")
                    result = subprocess.run(
                        [bash_path(), "--noprofile", "--norc", "-c",
                         'set -Eeuo pipefail; source "$1"; neutts_apt_validate_plan "$2" "$3"',
                         "host-plan-control", (ROOT / "scripts/neutts_apt_snapshot.sh").as_posix(),
                         path.as_posix(), (ROOT / PREP.FOUNDATION_PATH).as_posix()],
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(result.returncode == 0, passes, result.stdout + result.stderr)

    def test_native_pin_guard_rejects_changed_tsv_before_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            altered = directory / "pins.tsv"
            altered.write_bytes(self.foundation.replace(b"20260526.0", b"20260527.0"))
            plan = directory / "plan"
            plan.write_text("")
            result = subprocess.run(
                [bash_path(), "--noprofile", "--norc", "-c",
                 'set -Eeuo pipefail; source "$1"; neutts_apt_validate_plan "$2" "$3"',
                 "host-pin-control", (ROOT / "scripts/neutts_apt_snapshot.sh").as_posix(),
                 plan.as_posix(), altered.as_posix()],
                capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pin set changed", result.stderr)

    def test_all_foundation_callers_parse_after_shared_bootstrap_wiring(self):
        names = ["neutts_apt_snapshot", "compatibility_probe_neutts",
                 "compatibility_probe_neutts_engine_wheel", "compatibility_probe_neutts_rust",
                 "compatibility_probe_neutts_nonrust", "compatibility_probe_neutts_torchao",
                 "compatibility_probe_neutts_espeak", "compatibility_probe_neutts_apt_extensions"]
        for name in names:
            with self.subTest(name=name):
                result = subprocess.run([bash_path(), "--noprofile", "--norc", "-n",
                                         str(ROOT / "scripts" / (name + ".sh"))],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
