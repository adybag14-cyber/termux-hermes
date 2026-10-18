#!/usr/bin/env python3
"""Prepare exact original APT inputs for five model-free native extension gates."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import posixpath
import re
import stat
import struct
import sys
import tarfile
import urllib.parse
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_FILENAME = "neutts_apt_extensions_lock.json"
LOCK_SHA256 = "52db5e627cf575312d8011b6c000feb0f6075f7266981a1ed5bda68319f42ac3"
APT_HELPER_SHA256 = "7c051b0143675594aadd52f9a0b66ec71e6950e9953feef3f773acceafcb0a29"
FOUNDATION_METADATA_SHA256 = "2031c8a6915915ffffb980b268ad5107d42a186682cb2ca7009d803fe2abe200"
ROOTS = frozenset(("python-pyarrow", "python-lxml", "python-msgpack", "python-pillow", "python-psutil"))
NAMES = frozenset(("pyarrow", "lxml", "msgpack", "pillow", "psutil"))
ALL_NAMES = NAMES | frozenset(("llvmlite", "numpy", "scipy", "soxr", "torch", "torchaudio", "torchcodec"))
PREFIX_TEXT = "/data/data/com.termux/files/usr"
RECEIPT = "APT-EXTENSIONS-PREPARED.json"
MAX_ARCHIVE = 64_000_000
MAX_MEMBER = 64_000_000


class PreparationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise PreparationError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
            "Input is not a bounded non-symlink regular file: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == info.st_size, "Input size changed during read")
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def apt_helper():
    path = SCRIPT_DIR / "validate_neutts_apt_python.py"
    require(sha(read_regular(path, 100_000)) == APT_HELPER_SHA256,
            "Original APT validator differs")
    spec = importlib.util.spec_from_file_location("_apt_extensions_original_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_manifest(lock, original):
    require(lock.get("schema_version") == 1 and set(lock["roots"]) == ROOTS
            and set(lock["distribution_names"]) == NAMES,
            "Exact five-root binding differs")
    rows = lock["metadata"]["apt_distributions"]
    require(len(rows) == 12 and {row["name"] for row in rows} == ALL_NAMES,
            "Exact twelve-distribution binding differs")
    preserved = [row for row in rows if row["name"] not in NAMES]
    require(sorted(preserved, key=lambda row: row["name"]) ==
            sorted(original["apt_distributions"], key=lambda row: row["name"]),
            "Original seven APT metadata rows changed")
    for key in ("runtime", "tag_convention"):
        require(lock["metadata"][key] == original[key], "Original runtime/tag contract changed")
    require(lock["foundation"]["apt_metadata_ledger_sha256"] == FOUNDATION_METADATA_SHA256,
            "Original metadata identity changed")
    foundation = lock["foundation"]["packages"]
    require(len(foundation) == 122 and len({p["package"] for p in foundation}) == 122,
            "Exact 122-package foundation differs")
    pins = lock["apt"]["provenance_packages"]
    require(len(pins) == 84 and len({p["package"] for p in pins}) == 84,
            "Exact provenance archive union differs")
    names = set(lock["apt"]["closure_names"])
    require(len(names) == len(lock["apt"]["closure_names"]) == 78
            and len(lock["apt"]["closure_edges"]) == 151, "APT closure dimensions differ")
    additions = names - {p["package"] for p in foundation}
    require(additions == set(lock["apt"]["additional_names"]) and len(additions) == 18,
            "Additions must be derived from the foundation alone")
    require(sum(p["bytes"] for p in pins if p["package"] in additions) == 14_043_104,
            "Addition archive byte count differs")
    expected_union = names | {p["package"] for p in original["runtime"]["archives"]} | {
        row["apt"]["package"] for row in original["apt_distributions"]}
    by_name = {p["package"]: p for p in pins}
    require(set(by_name) == expected_union, "APT provenance closure has missing/extra packages")
    for row in rows:
        require(row["apt"] == by_name[row["apt"]["package"]], "Metadata/archive binding differs")
    for pin in foundation:
        if pin["package"] in by_name:
            require(pin == by_name[pin["package"]], "Foundation archive identity changed")
    require(set(lock["original_root_files"]) == ROOTS and set(lock["root_native_files"]) == ROOTS,
            "Full root file inventory is incomplete")
    all_files = [row for rows in lock["original_root_files"].values() for row in rows]
    require(sum(r["kind"] == "file" for r in all_files) == 893
            and sum(r["kind"] == "symlink" for r in all_files) == 1
            and len({r["path"] for r in all_files}) == len(all_files),
            "Original five-package file set differs")
    require(sum(len(v) for v in lock["root_native_files"].values()) == 34,
            "Original five-package ELF set differs")
    require(lock["operation_cases"] == ["pyarrow", "lxml", "msgpack", "pillow", "psutil"],
            "Native operation gate set differs")
    require(not any(lock["admission"].values()), "Unexpected production or metadata change")
    image_rows = lock["image_runtime"]["files"]
    image_prefix = PREFIX_TEXT + "/opt/aosp/lib64/"
    require(lock["image_runtime"]["image"] == "termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303"
            and len(image_rows) == 5 and {row["path"] for row in image_rows} ==
            {image_prefix + name for name in ("libc++.so", "libc.so", "libdl.so", "liblog.so", "libm.so")}
            and all(row["dpkg_owners"] == ["aosp-libs"] and row["machine"] == 183
                    and row["elf_class"] == 64 for row in image_rows),
            "Exact pinned-image AOSP runtime binding differs")
    validate_extension_image_evidence(lock)
    return lock


def validate_extension_image_evidence(lock):
    extension = lock["extension_image_runtime"]
    pin = extension["source_evidence"]
    require(extension["image"] == lock["image_runtime"]["image"]
            and pin["path"] == "audit/neutts-apt-extensions-native-20261018/run-39082604000.json",
            "Exact extension-image source binding differs")
    raw = read_regular(SCRIPT_DIR.parent / pin["path"], pin["bytes"])
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"],
            "Frozen extension-image observation evidence differs")
    evidence = json.loads(raw, object_pairs_hook=unique_object)
    observed = evidence["observed_unknown_image_member"]
    require(evidence["run"]["id"] == 39082604000
            and evidence["run"]["head_sha"] == "2bf6e32b4009ca5233686d80a1dd2dcbf53cb7d2"
            and evidence["run"]["conclusion"] == "failure"
            and evidence["image_binding"]["image"] == extension["image"]
            and evidence["image_binding"]["owner_package_selected_for_install"] is False
            and observed["resolved_path"] == PREFIX_TEXT + "/opt/aosp/lib64/libicuuc.so"
            and observed["owners"] == ["aosp-libs"] and observed["admitted"] is False,
            "Exact native ICU observation binding differs")
    expected = {key: observed[key] for key in ("bytes", "sha256", "elf", "owners", "mode", "uid", "gid")}
    expected["path"] = observed["resolved_path"]
    expected["owner_state"] = observed["owner_states"]["aosp-libs"]
    require(evidence["image_binding"]["owner_state_before"] ==
            evidence["image_binding"]["owner_state_after"] == expected["owner_state"]
            and extension["files"] == [expected],
            "Only the exact observed ICU member and unchanged owner state may be admitted")


def load_lock(path=None):
    raw = read_regular(path or SCRIPT_DIR / LOCK_FILENAME, 1_000_000)
    require(sha(raw) == LOCK_SHA256, "Frozen extension lock differs")
    lock = json.loads(raw, object_pairs_hook=unique_object)
    for name, pin in lock["source_pins"].items():
        value = read_regular(SCRIPT_DIR.parent / name, pin["bytes"])
        require(len(value) == pin["bytes"] and sha(value) == pin["sha256"],
                "Reviewed foundation/helper source changed: " + name)
    apt = apt_helper()
    original = apt.load_manifest(SCRIPT_DIR / "neutts_apt_python_metadata.json")
    return validate_manifest(lock, original), raw


def pin_bytes(raw, pin):
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "APT archive identity differs")
    return raw


def elf_identity(raw):
    require(len(raw) >= 64 and raw[:6] == b"\x7fELF\x02\x01"
            and struct.unpack_from("<H", raw, 18)[0] == 183,
            "Expected original little-endian AArch64 ELF")
    return {"class": 64, "machine": 183, "endianness": "little"}


def inspect_deb(path, pin, wanted=None):
    """Bind controls and data to original archive bytes; never extract or execute."""
    apt = apt_helper()
    raw = pin_bytes(read_regular(path, min(pin["bytes"], MAX_ARCHIVE)), pin)
    controls, rows, selected, natives = [], [], {}, []
    data_count, control_count, expanded = 0, 0, 0
    for name, payload in apt.archive_members(raw):
        if not name.startswith(("control.tar", "data.tar")):
            continue
        is_data = name.startswith("data.tar")
        data_count += int(is_data)
        control_count += int(not is_data)
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r|*") as archive:
            for member in archive:
                normalized = apt.tar_name(member.name)
                require(normalized not in seen, "Duplicate APT tar path")
                seen.add(normalized)
                expanded += member.size
                require(expanded <= 512_000_000, "Expanded APT archive exceeds bound")
                if not is_data and normalized == "/control":
                    require(member.isfile() and member.size < 100_000, "Invalid APT control member")
                    controls.append(apt.control_record(archive.extractfile(member).read()))
                if not is_data or member.isdir() or wanted is not None and normalized not in wanted:
                    continue
                require(normalized.startswith(PREFIX_TEXT + "/"), "Root package file escapes PREFIX")
                row = {"path": normalized, "package": pin["package"], "mode": member.mode & 0o7777}
                if member.isfile():
                    require(member.size <= MAX_MEMBER, "Selected APT member exceeds bound")
                    value = archive.extractfile(member).read()
                    require(len(value) == member.size, "Truncated APT member")
                    row.update(kind="file", bytes=len(value), sha256=sha(value))
                    if value.startswith(b"\x7fELF"):
                        natives.append({"path": normalized, "bytes": len(value), "sha256": sha(value),
                                        **elf_identity(value)})
                    if wanted is not None:
                        selected[normalized] = value
                elif member.issym() and wanted is None:
                    target = member.linkname
                    require(not target.startswith("/") and "\\" not in target and "\0" not in target,
                            "Unexpected root package symlink target")
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(normalized), target))
                    require(resolved.startswith(PREFIX_TEXT + "/"), "Root symlink escapes PREFIX")
                    row.update(kind="symlink", target=target)
                else:
                    raise PreparationError("Unexpected selected APT member type: " + normalized)
                rows.append(row)
    require(data_count == control_count == 1 and controls == [pin["control"]],
            "APT archive control or tar identity differs")
    if wanted is not None:
        require(set(selected) == set(wanted), "Missing selected APT member")
    return {"control": controls[0], "files": sorted(rows, key=lambda r: r["path"]),
            "native": sorted(natives, key=lambda r: r["path"]), "selected": selected}


def verify_root(path, pin, lock):
    result = inspect_deb(path, pin)
    name = pin["package"]
    require(result["files"] == lock["original_root_files"][name], "Original root file bytes/modes/links differ")
    require(result["native"] == lock["root_native_files"][name], "Original native root files differ")
    return {"package": name, "bytes": pin["bytes"], "sha256": pin["sha256"],
            "regular_files": sum(row["kind"] == "file" for row in result["files"]),
            "symlinks": sum(row["kind"] == "symlink" for row in result["files"]),
            "native_files": len(result["native"]), "control": result["control"]}


def snapshot_metadata(snapshot, lock):
    frozen = lock["repository"]["snapshot"]
    for name, pin in frozen.items():
        value = read_regular(snapshot / name, pin["bytes"])
        require(len(value) == pin["bytes"] and sha(value) == pin["sha256"], "Frozen signed index differs")
    active, bindings = False, []
    for line in (snapshot / "InRelease").read_text(encoding="utf-8").splitlines():
        if line == "SHA256:":
            active = True
            continue
        if active and line and not line[0].isspace():
            active = False
        if active:
            match = re.fullmatch(r"\s+([0-9a-f]{64})\s+([0-9]+)\s+(\S+)", line)
            if match and match[3] == "main/binary-aarch64/Packages.gz":
                bindings.append((match[1], int(match[2])))
    require(bindings == [(frozen["Packages.gz"]["sha256"], frozen["Packages.gz"]["bytes"])],
            "InRelease does not bind the exact compressed index")
    with gzip.GzipFile(fileobj=io.BytesIO((snapshot / "Packages.gz").read_bytes())) as stream:
        expanded = stream.read(32_000_001)
    pin = lock["repository"]["packages_uncompressed"]
    require(len(expanded) == pin["bytes"] and sha(expanded) == pin["sha256"],
            "Expanded signed index identity differs")
    records = {}
    for block in expanded.split(b"\n\n"):
        if not block.strip():
            continue
        fields = BytesParser(policy=compat32).parsebytes(block)
        if fields.get("Architecture") in ("aarch64", "all"):
            key = tuple(fields.get(name) for name in ("Package", "Version", "Architecture", "Filename"))
            require(key not in records, "Duplicate exact APT index identity")
            records[key] = fields
    apt = apt_helper()
    for package in lock["foundation"]["packages"] + lock["apt"]["provenance_packages"]:
        key = (package["package"], package["version"], package["architecture"], package["repository_path"])
        found = records.get(key)
        require(found is not None and found["SHA256"] == package["sha256"]
                and int(found["Size"]) == package["bytes"], "Frozen APT index package differs")
        require(apt.control_record(str(found).encode()) == package["control"],
                "Frozen APT control/dependency declaration differs")
    return expanded


def tsv(packages):
    return "".join("\t".join((p["package"], p["version"], p["architecture"], p["sha256"],
                              str(p["bytes"]), p["repository_path"])) + "\n" for p in packages).encode()


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        require(parsed.scheme == "https" and parsed.hostname in
                {"packages.termux.dev", "packages-cf.termux.dev"}
                and not parsed.username and not parsed.password, "Unreviewed artifact redirect")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def acquire(pin, cache, base_url):
    if cache is not None and (cache / pin["filename"]).exists():
        return pin_bytes(read_regular(cache / pin["filename"], pin["bytes"]), pin)
    url = base_url + pin["repository_path"]
    parsed = urllib.parse.urlparse(url)
    require(parsed.scheme == "https" and parsed.hostname == "packages.termux.dev"
            and not parsed.query and not parsed.fragment, "Unreviewed APT artifact origin")
    request = urllib.request.Request(url, headers={"User-Agent": "termux-hermes-apt-extension-preparation"})
    with urllib.request.build_opener(OfficialRedirects).open(request, timeout=30) as response:
        raw = response.read(pin["bytes"] + 1)
    return pin_bytes(raw, pin)


def verify_inputs(inputs):
    require(inputs.is_dir() and not inputs.is_symlink(), "Prepared inputs must be a real directory")
    lock, _ = load_lock(inputs / LOCK_FILENAME)
    expected = {LOCK_FILENAME, RECEIPT, "snapshot", "archives", "foundation-pins.tsv", "apt-provenance-pins.tsv"}
    require({p.name for p in inputs.iterdir()} == expected, "Missing/extra prepared input")
    require(not (inputs / "snapshot").is_symlink() and not (inputs / "archives").is_symlink(),
            "Prepared input directory is symlinked")
    require({p.name for p in (inputs / "snapshot").iterdir()} == set(lock["repository"]["snapshot"]),
            "Prepared snapshot file set differs")
    snapshot_metadata(inputs / "snapshot", lock)
    require(read_regular(inputs / "foundation-pins.tsv", 100_000) == tsv(lock["foundation"]["packages"]),
            "Foundation TSV differs")
    require(read_regular(inputs / "apt-provenance-pins.tsv", 100_000) == tsv(lock["apt"]["provenance_packages"]),
            "Provenance TSV differs")
    pins = [p for p in lock["apt"]["provenance_packages"] if p["package"] in ROOTS]
    require({p.name for p in (inputs / "archives").iterdir()} == {p["filename"] for p in pins},
            "Missing/extra root archive")
    rows = [verify_root(inputs / "archives" / pin["filename"], pin, lock) for pin in pins]
    receipt = json.loads(read_regular(inputs / RECEIPT, 100_000), object_pairs_hook=unique_object)
    require(receipt.get("status") == "verified-inputs" and receipt.get("lock_sha256") == LOCK_SHA256
            and receipt.get("roots") == rows and receipt.get("native_execution") is False
            and receipt.get("model_downloaded") is False, "Prepared input receipt differs")
    return lock, receipt


def prepare(out, cache=None, lock_path=None):
    lock, raw = load_lock(lock_path)
    out = out.absolute()
    require(out.resolve() == out and not out.exists() and not out.is_symlink(),
            "Use a fresh output without symlink ancestors")
    if cache is not None:
        cache = cache.resolve()
        require(not out.is_relative_to(cache) and not cache.is_relative_to(out),
                "Output overlaps the read-only cache")
    snapshot = SCRIPT_DIR.parent / "audit/neutts-runtime-index-20261017"
    snapshot_metadata(snapshot, lock)
    pins = [p for p in lock["apt"]["provenance_packages"] if p["package"] in ROOTS]
    bodies = {p["filename"]: acquire(p, cache, lock["repository"]["base_url"]) for p in pins}
    out.mkdir(parents=True)
    write_new(out / LOCK_FILENAME, raw)
    for name in lock["repository"]["snapshot"]:
        write_new(out / "snapshot" / name, (snapshot / name).read_bytes())
    write_new(out / "foundation-pins.tsv", tsv(lock["foundation"]["packages"]))
    write_new(out / "apt-provenance-pins.tsv", tsv(lock["apt"]["provenance_packages"]))
    for name, value in bodies.items():
        write_new(out / "archives" / name, value)
    roots = [verify_root(out / "archives" / pin["filename"], pin, lock) for pin in pins]
    receipt = {"schema_version": 1, "status": "verified-inputs", "lock_sha256": LOCK_SHA256,
               "roots": roots, "closure_packages": 78, "closure_edges": 151, "foundation_packages": 122,
               "additional_packages": 18, "additional_archive_bytes": 14_043_104,
               "provenance_archives_required_natively": 84, "native_execution": False,
               "signed_index_authentication": "required natively; host hash binding only",
               "metadata_modified": False, "compiler_installed": False, "model_downloaded": False,
               "engine_installed": False, "published": False}
    write_new(out / RECEIPT, encoded(receipt))
    verify_inputs(out)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args(argv)
    receipt = prepare(args.out, args.cache, args.lock)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
