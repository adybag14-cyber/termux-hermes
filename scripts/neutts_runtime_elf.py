#!/usr/bin/env python3
"""Bounded static ELF64 inspection for native preparation gates without a compiler."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def elf(path, dynamic=False):
    path = Path(path)
    require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode),
            "ELF inspection requires a regular non-symlink file")
    path = path.resolve()
    length = path.stat().st_size
    require(64 <= length <= 256 * 1024 * 1024, "ELF input exceeds the reviewed size bound")
    with path.open("rb") as stream:
        def read(offset, size):
            require(type(offset) is int and type(size) is int and 0 <= offset <= length
                    and 0 <= size <= length - offset, "ELF table escapes its original file")
            stream.seek(offset)
            raw = stream.read(size)
            require(len(raw) == size, "ELF input was truncated")
            return raw

        header = struct.unpack("<16sHHIQQQIHHHHHH", read(0, 64))
        require(header[0][:7] == b"\x7fELF\x02\x01\x01" and header[1] in (2, 3)
                and header[2] == 183 and header[3] == 1 and header[8] == 64,
                "Expected original little-endian AArch64 ELF64")
        row = {"path": str(path), "bytes": length, "class": 64, "machine": 183, "endianness": "little"}
        if dynamic:
            require(header[9] == 56 and 1 <= header[10] <= 128, "Invalid ELF program-header bounds")
            segments = [struct.unpack("<IIQQQQQQ", read(header[5] + i * 56, 56))
                        for i in range(header[10])]
            for segment in segments:
                require(segment[2] <= length and segment[5] <= length - segment[2],
                        "ELF segment escapes its original file")
            tables = [segment for segment in segments if segment[0] == 2]
            require(len(tables) == 1, "ELF requires one unambiguous dynamic table")
            table = tables[0]
            require(0 < table[5] <= 65536 and table[5] % 16 == 0, "Invalid dynamic table size")
            values = [struct.unpack("<QQ", read(table[2] + offset, 16))
                      for offset in range(0, table[5], 16)]
            end = next((i for i, (tag, _) in enumerate(values) if tag == 0), None)
            require(end is not None, "Unterminated ELF dynamic table")
            values = values[:end]
            strings = [value for tag, value in values if tag == 5]
            sizes = [value for tag, value in values if tag == 10]
            require(len(strings) == len(sizes) == 1 and 0 < sizes[0] <= 4 * 1024 * 1024,
                    "ELF dynamic strings are missing, ambiguous or oversized")
            mappings = [segment for segment in segments if segment[0] == 1
                        and segment[3] <= strings[0]
                        and strings[0] - segment[3] + sizes[0] <= segment[5]]
            require(len(mappings) == 1, "Dynamic strings must map to one original file segment")
            segment = mappings[0]
            raw_strings = read(segment[2] + strings[0] - segment[3], sizes[0])

            def string(offset):
                require(0 <= offset < len(raw_strings), "Invalid dynamic string offset")
                stop = raw_strings.find(b"\0", offset)
                require(stop >= 0 and stop - offset <= 16384, "Unterminated or oversized dynamic string")
                return raw_strings[offset:stop].decode("ascii", "strict")

            needed = [string(value) for tag, value in values if tag == 1]
            require(len(needed) <= 128 and len(needed) == len(set(needed))
                    and all(name and "/" not in name for name in needed),
                    "Invalid or duplicate ELF dynamic dependency")
            require(not any(name in {"libc.so.6", "libm.so.6", "libpthread.so.0",
                                     "libstdc++.so.6", "libpython3.14.so.1.0"}
                            or "musl" in name for name in needed),
                    "Foreign GNU/Linux dynamic dependency")
            row.update(needed=needed, runpath=[string(value) for tag, value in values if tag in (15, 29)],
                       soname=[string(value) for tag, value in values if tag == 14],
                       inspection="Bounded original ELF64 PT_DYNAMIC; no readelf or binary execution")
        stream.seek(0)
        row["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    return row
