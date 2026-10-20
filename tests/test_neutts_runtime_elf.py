"""Bounded ELF parsing and original AArch64 wheel regression tests."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_elf", ROOT / "scripts/neutts_runtime_elf.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

def fixture(needed=("libc.so", "libpython3.so"), soname="fixture.so", runpath="$ORIGIN"):
    strings = bytearray(b"\0")
    def add(value):
        offset = len(strings)
        strings.extend(value.encode("ascii") + b"\0")
        return offset
    entries = [(1, add(value)) for value in needed]
    entries += [(14, add(soname)), (29, add(runpath))]
    dynamic = 256
    string_offset = 512
    entries += [(5, 0x10000 + string_offset), (10, len(strings)), (0, 0)]
    raw = bytearray(string_offset + len(strings))
    header = (b"\x7fELF\x02\x01\x01" + b"\0" * 9, 3, 183, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    raw[:64] = struct.pack("<16sHHIQQQIHHHHHH", *header)
    raw[64:120] = struct.pack("<IIQQQQQQ", 1, 4, 0, 0x10000, 0x10000, len(raw), len(raw), 4096)
    raw[120:176] = struct.pack("<IIQQQQQQ", 2, 4, dynamic, 0x10100, 0x10100, len(entries) * 16, len(entries) * 16, 8)
    for i, entry in enumerate(entries):
        struct.pack_into("<QQ", raw, dynamic + i * 16, *entry)
    raw[string_offset:] = strings
    return raw

class RuntimeElfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.so"

    def inspect(self, raw, dynamic=True):
        self.path.write_bytes(raw)
        return reader.elf(self.path, dynamic=dynamic)

    def test_literal_dynamic_table_without_external_program(self):
        raw = fixture()
        result = self.inspect(raw)
        self.assertEqual(result["needed"], ["libc.so", "libpython3.so"])
        self.assertEqual(result["soname"], ["fixture.so"])
        self.assertEqual(result["runpath"], ["$ORIGIN"])
        self.assertEqual((result["class"], result["machine"], result["endianness"]), (64, 183, "little"))
        self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIn("no readelf", result["inspection"])

    def test_original_native_xxhash_wheel(self):
        wheel = ROOT / "audit/neutts-xxhash-preparation-20261020/xxhash-4.0.1-cp314-cp314-android_24_arm64_v8a.whl"
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(),
                         "af05a3f650220a6c59fa0ad2410249f2d2470a05225807c378fb67458693f8df")
        with zipfile.ZipFile(wheel) as archive:
            names = [name for name in archive.namelist() if name.endswith(".so")]
            self.assertEqual(len(names), 1)
            raw = archive.read(names[0])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "73252f83ab6ed584103a380a5b4015f0620b8d7d6e1b51d100c851ed879ebde2")
        result = self.inspect(raw)
        self.assertIn("libc.so", result["needed"])
        self.assertEqual(result["bytes"], 92528)
        self.assertNotIn("libc.so.6", result["needed"])

    def test_reject_foreign_or_wrong_abi(self):
        for offset, value in ((0, b"NOT!"), (4, b"\1"), (5, b"\2"), (18, struct.pack("<H", 62)),
                              (16, struct.pack("<H", 1)), (52, struct.pack("<H", 63))):
            with self.subTest(offset=offset):
                raw = fixture()
                raw[offset:offset + len(value)] = value
                with self.assertRaises(ValueError):
                    self.inspect(raw)

    def test_reject_truncated_and_out_of_bounds_tables(self):
        samples = [fixture()[:63], fixture()[:175]]
        for offset, value in ((32, 2**63), (96, 2**63), (152, 65552), (152, 17), (128, 2**63)):
            raw = fixture()
            struct.pack_into("<Q", raw, offset, value)
            samples.append(raw)
        for number, raw in enumerate(samples):
            with self.subTest(number=number), self.assertRaises(ValueError):
                self.inspect(raw)

    def test_reject_missing_or_ambiguous_dynamic_metadata(self):
        samples = []
        raw = fixture()
        struct.pack_into("<I", raw, 120, 1)
        samples.append(raw)
        raw = fixture()
        struct.pack_into("<Q", raw, 256 + 6 * 16, 21)
        samples.append(raw)
        raw = fixture()
        struct.pack_into("<Q", raw, 256 + 4 * 16, 10)
        samples.append(raw)
        raw = fixture()
        struct.pack_into("<Q", raw, 256 + 5 * 16 + 8, 4 * 1024 * 1024 + 1)
        samples.append(raw)
        raw = fixture()
        struct.pack_into("<Q", raw, 256 + 4 * 16 + 8, 0x10000 + len(raw) + 10)
        samples.append(raw)
        for number, raw in enumerate(samples):
            with self.subTest(number=number), self.assertRaises(ValueError):
                self.inspect(raw)

    def test_reject_bad_dynamic_names(self):
        for names in (("libc.so", "libc.so"), ("",), ("/usr/lib/libc.so",),
                      ("libc.so.6",), ("libstdc++.so.6",), ("libc.musl-aarch64.so.1",)):
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.inspect(fixture(needed=names))
        raw = fixture()
        struct.pack_into("<Q", raw, 264, 2**63)
        with self.assertRaises(ValueError):
            self.inspect(raw)
        raw = fixture()
        raw[-1] = ord("X")
        with self.assertRaises(ValueError):
            self.inspect(raw)

    def test_header_only_inspection_and_size_limit(self):
        raw = fixture()
        result = self.inspect(raw, dynamic=False)
        self.assertNotIn("needed", result)
        with self.path.open("wb") as stream:
            stream.truncate(256 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "size bound"):
            reader.elf(self.path)

    def test_reject_non_regular_file(self):
        self.path.mkdir()
        with self.assertRaises(ValueError):
            reader.elf(self.path)

if __name__ == "__main__":
    unittest.main()
