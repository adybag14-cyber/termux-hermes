"""Freeze exact successful run 39073138135, with independent artifact/source/wheel rechecks."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
import base64, csv, hashlib, io, json, posixpath, re, stat, struct, tarfile, zipfile, zlib
import packaging
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

BASE = Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace")
EVIDENCE = BASE / "espeak-termux-native-evidence-20261017/39073138135"
REPO = BASE / "termux-hermes-next-stable-20261017"
AUDIT = REPO / "audit/neutts-espeak-native-20261017"
RAW = AUDIT / "run-39073138135"
SUMMARY = AUDIT / "run-39073138135.json"
HEAD = "f9116a739ab802fccb16b6d081e8626bd1ec8521"
ARTIFACT_SHA = "0b1f2dd9ecb3c6bc92006d0e89b867e6676cbeae4c68be66bf8a51fc37801038"

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def raw_json(path):
    return json.loads(path.read_bytes())

def save_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw

def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def safe_name(name):
    p = PurePosixPath(name)
    assert name and not p.is_absolute() and "\\" not in name and "\0" not in name
    assert all(x not in ("", ".", "..") for x in p.parts)
    return p

def verify_bytes(raw, identity):
    assert len(raw) == identity["bytes"] and digest(raw) == identity["sha256"]

def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def git_tree(rows):
    root = {}
    for row in rows:
        parts = safe_name(row["path"]).parts
        at = root
        for part in parts[:-1]:
            at = at.setdefault(part, {})
        assert parts[-1] not in at
        at[parts[-1]] = row
    def walk(tree):
        entries = []
        for name, value in tree.items():
            directory = "path" not in value
            mode, sha = ("40000", walk(value)) if directory else (value["mode"], value["git_blob_sha1"])
            entries.append((name.encode() + (b"/" if directory else b""), mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(sha)))
        body = b"".join(data for _, data in sorted(entries))
        return hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()
    return walk(root)

def source_archive(raw, root, expected, sole_symlink=None):
    expected = {row["path"]: row for row in expected}
    found, blobs = {}, {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            safe_name(name)
            assert name == root or name.startswith(root + "/")
            if member.isdir():
                continue
            relative = name[len(root) + 1:]
            assert relative in expected and relative not in found
            row = expected[relative]
            if member.issym():
                assert sole_symlink is not None
                assert relative == sole_symlink["path"] and member.linkname == sole_symlink["target"]
                target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), member.linkname))
                assert target in expected and not target.startswith("../")
                data, mode = member.linkname.encode(), "120000"
            else:
                assert member.isfile()
                data = archive.extractfile(member).read()
                mode = "100755" if member.mode & 0o111 else "100644"
            size_key = "size" if "size" in row else "bytes"
            assert len(data) == row[size_key] and digest(data) == row["sha256"] and mode == row["mode"]
            if "git_blob_sha1" in row:
                assert blob_sha(data) == row["git_blob_sha1"]
            found[relative], blobs[relative] = row, data
    assert set(found) == set(expected)
    return blobs

def elf(raw):
    assert raw[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", raw, 18)[0] == 183
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", raw, 0)
    phoff, phentsize, phnum = header[5], header[9], header[10]
    assert phentsize == 56
    ph = [struct.unpack_from("<IIQQQQQQ", raw, phoff + i * phentsize) for i in range(phnum)]
    dyn = next((p for p in ph if p[0] == 2), None)
    needed, runpath = [], []
    if dyn:
        entries = []
        for offset in range(dyn[2], dyn[2] + dyn[5], 16):
            tag, value = struct.unpack_from("<qQ", raw, offset)
            if tag == 0:
                break
            entries.append((tag, value))
        string_addr = next(v for k, v in entries if k == 5)
        segment = next(p for p in ph if p[0] == 1 and p[3] <= string_addr < p[3] + p[5])
        start = segment[2] + string_addr - segment[3]
        def string(offset):
            end = raw.index(b"\0", start + offset)
            return raw[start + offset:end].decode()
        needed = [string(v) for k, v in entries if k == 1]
        runpath = [string(v) for k, v in entries if k in (15, 29)]
    return {"class": 64, "endianness": "little", "machine": 183, "needed": needed, "runpath": runpath}

def verify_elf_receipt(raw, receipt):
    verify_bytes(raw, receipt)
    actual = elf(raw)
    for k, v in actual.items():
        if k in receipt:
            assert receipt[k] == v, (k, receipt[k], v)
    return actual

def verify_wheel(raw, package):
    verify_bytes(raw, package["artifact"])
    pin = package["wheel"]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        assert len(infos) == pin["entry_count"] and len({x.filename for x in infos}) == len(infos)
        assert archive.testzip() is None
        members = {}
        for item in infos:
            safe_name(item.filename.rstrip("/"))
            mode = item.external_attr >> 16
            assert not stat.S_ISLNK(mode)
            if item.is_dir():
                continue
            assert stat.S_IFMT(mode) in (0, stat.S_IFREG)
            members[item.filename] = archive.read(item)
        assert len(members) == pin["file_count"]
        assert sum(map(len, members.values())) == pin["uncompressed_bytes"]
        assert max(map(len, members.values())) == pin["max_member_bytes"]
        for kind in ("metadata", "wheel", "record"):
            assert digest(members[pin[kind + "_member"]]) == pin[kind + "_sha256"]
        rows = list(csv.reader(io.StringIO(members[pin["record_member"]].decode("utf-8"))))
        assert all(len(row) == 3 for row in rows)
        assert len(rows) == len(members) and {row[0] for row in rows} == set(members)
        for name, hashed, size in rows:
            if name == pin["record_member"]:
                assert hashed == size == ""
            else:
                assert hashed.startswith("sha256=") and size == str(len(members[name]))
                value = base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest()).decode().rstrip("=")
                assert hashed == "sha256=" + value
        metadata = BytesParser(policy=compat32).parsebytes(members[pin["metadata_member"]])
        assert canonicalize_name(metadata["Name"]) == package["name"] and metadata["Version"] == package["version"]
        assert metadata.get_all("Requires-Dist", []) == package["requires_dist"]
        assert metadata.get("Requires-Python", "") == package["requires_python"]
        assert SpecifierSet(package["requires_python"]).contains("3.14.6", prereleases=True)
        wheel_metadata = BytesParser(policy=compat32).parsebytes(members[pin["wheel_member"]])
        assert wheel_metadata.get_all("Tag", []) == pin["tags"]
        assert (wheel_metadata["Root-Is-Purelib"].lower() == "true") == pin["root_is_purelib"]
        native = []
        for name, data in members.items():
            if data.startswith(b"\x7fELF"):
                assert elf(data)["machine"] == 183
                native.append({"member": name, "bytes": len(data), "sha256": digest(data)})
        assert native == package["native_members"]
        member_rows = [{"path": name, "bytes": len(data), "sha256": digest(data)} for name, data in sorted(members.items())]
        return members, {"name": package["name"], "version": package["version"],
                         "artifact": package["artifact"], "entry_count": len(infos), "regular_files": len(members),
                         "all_member_crc_record_metadata_native_pins_verified": True,
                         "inner_member_ledger_sha256": digest(encode(member_rows))}

def command_recheck(directory, stem, record):
    assert record["exit_code"] == 0
    for channel in ("stdout", "stderr"):
        path = directory / (stem + "." + channel + ".log")
        assert digest(path.read_bytes()) == record[channel + "_sha256"]

def main():
    assert not RAW.exists() and not SUMMARY.exists()
    ledger = raw_json(EVIDENCE / "verified-artifact.json")
    assert ledger["run_id"] == 39073138135 and ledger["head_sha"] == HEAD
    assert ledger["job_id"] == 117514736579 and ledger["conclusion"] == "success"
    assert ledger["artifact_id"] == 12116350977 and ledger["artifact_bytes"] == 55254989
    assert ledger["artifact_sha256"] == ARTIFACT_SHA
    archive_path = EVIDENCE / "artifact.zip"
    assert archive_path.stat().st_size == 55254989 and digest(archive_path.read_bytes()) == ARTIFACT_SHA
    entries = {row["name"]: row for row in ledger["members"]}
    assert len(entries) == len(ledger["members"]) == 654
    retained = {name: row for name, row in entries.items() if row["extracted"]}
    assert len(retained) == 145
    extracted = EVIDENCE / "extracted"
    assert {p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file()} == set(retained)
    for name, row in retained.items():
        safe_name(name)
        path = extracted / name
        assert path.is_file() and not path.is_symlink()
        verify_bytes(path.read_bytes(), row)
    log = (EVIDENCE / "native-job.log").read_bytes()
    assert len(log) == 205600 and digest(log) == "2c9e34b8a0f832a6b05d3d80b9a58b440d59c7f3f832660df9acc011f959dd77"
    inputs = raw_json(extracted / "ESPEAK-PROBE-INPUTS.json")
    assert inputs["head_sha"] == inputs["workflow_ref_commit"] == HEAD and inputs["run_id"] == "39073138135"
    assert len(inputs["inputs"]) == 23
    source_files = {}
    for name, sha in inputs["inputs"].items():
        safe_name(name)
        raw = (REPO / name).read_bytes()
        assert digest(raw) == sha, "Current reviewed source does not match run input: " + name
        source_files[name] = raw
    assert digest(source_files["scripts/compatibility_probe_phonemizer.py"]) == "6387ecead23b7777e879588d7e76bd4c8d462de5574de1d77092053efc596211"

    core = raw_json(extracted / "NEUTTS-CORE-RESULT.json")
    assert core["status"] == "passed" and len(core["cases"]) == 7
    assert {row["component"] for row in core["cases"]} == {"python_dependencies", "torch", "torchaudio", "torchcodec", "scipy", "llvmlite", "soxr"}
    for row in core["cases"]:
        assert row["status"] == "passed" and row["exit_code"] == 0 and row["timed_out"] is False
        assert digest((extracted / row["receipt"]).read_bytes()) == row["receipt_sha256"]
        child = raw_json(extracted / row["receipt"])
        assert child["status"] == "passed" and child["component"] == row["component"]
    validation = core["apt_python_validation"]
    assert validation["status"] == "requirements-and-provenance-passed" and validation["exit_code"] == 0
    assert digest((extracted / validation["receipt"]).read_bytes()) == validation["sha256"]
    assert core["pip_check"]["exit_code"] == 1
    assert digest((extracted / core["pip_check"]["log"]).read_bytes()) == core["pip_check"]["log_sha256"]
    assert raw_json(extracted / "ESPEAK-EXIT.json")["exit_code"] == 0

    component = extracted / "espeak-component"
    espeak = raw_json(component / "ESPEAK-COMPONENT-RESULT.json")
    assert espeak["status"] == "passed" and len(espeak["cases"]) == 14
    assert espeak["source_commit"] == "69bfd1efde0236654ccc117a28d04aef27673a30"
    assert espeak["source_manifest"] == {"bytes": 63434219, "file_count": 2606,
        "sha256": "69e5228b663815a4fa4b20bfca13242826d132128f1ee5a43f03091ce608ff50"}
    assert espeak["lock_sha256"] == "02e4469a3b7b3e6594d7b1bc9c6816c72adf1ea9eb917256cefefc9c12763baa"
    assert espeak["real_python_wrapper_proved"] is False
    for stage in ("configure", "build", "install"):
        command_recheck(component, "espeak-" + stage, espeak[stage])
    toolchain = espeak["toolchain"]
    assert len(toolchain["archives"]) == 44 and toolchain["additional_count"] == 19 and toolchain["apt"]["exit_code"] == 0
    cases = []
    for row in espeak["cases"]:
        assert row["status"] == "passed"
        for channel in ("stdout", "stderr"):
            assert digest((component / (row["case"] + "." + channel + ".log")).read_bytes()) == row[channel + "_sha256"]
        if row["case"] == "espeak-missing-data":
            assert row["exit_code"] == 1 and row["expected_initialization_failure"] is True
            assert b"phontab" in (component / (row["case"] + ".stderr.log")).read_bytes()
            cases.append({"case": row["case"], "status": "passed", "exit_code": 1,
                          "meaning": "Expected native initialization rejection with missing data"})
        else:
            assert row["exit_code"] == 0
            assert digest((component / row["receipt"]).read_bytes()) == row["receipt_sha256"]
            child = raw_json(component / row["receipt"])
            assert child["status"] == "passed" and child["synthesis_called"] is False
            if "phonemes" in child:
                assert child["cursor_completed"] is True and child["phonemes"]
            cases.append({k: row[k] for k in ("case", "status", "exit_code", "receipt", "receipt_sha256")})
    assert len({row["case"] for row in cases}) == 14
    for n in range(5):
        original, relocated = [raw_json(component / f"espeak-{mode}-{n}.json") for mode in ("ascii", "relocated")]
        assert original["phonemes"] == relocated["phonemes"]
        assert original["upstream_ascii_oracle_checked"] and relocated["upstream_ascii_oracle_checked"]
        assert original["data_path"] != relocated["data_path"]
    assert [raw_json(component / f"espeak-ipa-repeat-{n}.json")["phonemes"] for n in range(2)] == ["həlˈəʊ", "həlˈəʊ"]
    data_tree = raw_json(component / "ESPEAK-DATA-MANIFEST.json")
    assert len(data_tree) == espeak["data_tree"]["file_count"] == 371
    assert sum(row["size"] for row in data_tree) == espeak["data_tree"]["bytes"] == 18632313
    assert len([r for r in data_tree if r["path"].endswith("_dict")]) == 117
    assert digest((component / "ESPEAK-DATA-MANIFEST.json").read_bytes()) == espeak["data_tree"]["manifest_sha256"]

    union = raw_json(extracted / "PHONEMIZER-APT-ARCHIVE-UNION.json")
    assert union["status"] == "verified-45-archive-union" and union["archive_count"] == 45
    assert len(union["archives"]) == 45 and union["compiler_archive_count"] == 44
    assert union["pip_control_verified"] is True and union["pip_selected_source_files_verified"] == 456
    assert union["apt_install_performed"] is False and union["compiler_gate_changed"] is False
    assert union["espeak_receipt_sha256"] == digest((component / "ESPEAK-COMPONENT-RESULT.json").read_bytes())

    phdir = extracted / "phonemizer-component"
    ph = raw_json(phdir / "PHONEMIZER-COMPONENT-RESULT.json")
    assert ph["status"] == "passed" and ph["stage"] == "complete"
    assert ph["lock_sha256"] == "48d43784778817bd4a907b63f11738ff910cafc6aac2eed6bc27349b6d5d8c82"
    runtime_path = phdir / ph["runtime_receipt"]["path"]
    assert digest(runtime_path.read_bytes()) == ph["runtime_receipt"]["sha256"]
    runtime = raw_json(runtime_path)
    assert runtime["status"] == "passed"
    for report in (ph, runtime):
        assert report["model_downloaded"] is False and report["synthesis_tested"] is False
        assert report["production_admission_changed"] is False
        identity = report["runtime"]
        assert identity["api_level"] == 24 and identity["machine"] == "aarch64" and identity["sys_platform"] == "android"
        assert identity["uid"] == 1000 and identity["python"].startswith("3.14.6 ")
        assert identity["executable"]["sha256"] == "4f8d78ede7fc26e96e99342dd83ce42d32c9b4d0806bc9a99ff7151396269b25"
        assert report["espeak_input"]["status"] == "verified-separate-c-abi-result"
        assert report["espeak_input"]["receipt_sha256"] == digest((component / "ESPEAK-COMPONENT-RESULT.json").read_bytes())
        assert report["espeak_input"]["data_manifest_sha256"] == espeak["data_tree"]["manifest_sha256"]
        assert report["espeak_input"]["library"] == espeak["library"]
    assert ph["release_output"] is False
    assert ph["foundation"]["sha256"] == digest((extracted / "NEUTTS-CORE-RESULT.json").read_bytes())
    assert ph["foundation"]["case_count"] == 7 and ph["foundation"]["raw_pip_exit_code"] == 1
    assert ph["foundation"]["apt_validation_sha256"] == validation["sha256"]
    assert ph["apt_runtime_provenance"]["status"] == "passed"
    assert len(ph["apt_runtime_provenance"]["archives"]) == 2 and len(ph["apt_runtime_provenance"]["installed_files"]) == 460
    command_recheck(phdir, "phonemizer-pip-check", ph["raw_pip_check"])
    assert (phdir / "phonemizer-pip-check.stdout.log").read_bytes().strip() == b"No broken requirements found."
    command_recheck(phdir, "phonemizer-runtime", ph["runtime_process"])
    built = raw_json(phdir / "PHONEMIZER-BUILT-WHEELS.json")
    assert len(built["packages"]) == len(ph["built_wheels"]) == len(ph["source_builds"]) == 2
    assert built["source_builds"] == ph["source_builds"]
    for record in built["source_builds"]:
        command_recheck(phdir, "phonemizer-build-" + record["name"], record["result"])
        assert all(record["transfer"][key] is True for key in ("copied_bytes_verified", "exclusive_destination", "source_preserved"))
        package = next(p for p in built["packages"] if p["name"] == record["name"])
        assert record["transfer"]["bytes"] == package["artifact"]["bytes"]
        assert record["transfer"]["sha256"] == package["artifact"]["sha256"]
    regex_log = (phdir / "phonemizer-build-regex.stdout.log").read_bytes() + (phdir / "phonemizer-build-regex.stderr.log").read_bytes()
    assert b"--target=aarch64-linux-android24" in regex_log and b"-march=native" not in regex_log

    lock = raw_json(extracted / "phonemizer-inputs/phonemizer-runtime-lock.json")
    assert digest((extracted / "phonemizer-inputs/phonemizer-runtime-lock.json").read_bytes()) == ph["lock_sha256"]
    complete = {p["name"]: p for p in lock["packages"] + built["packages"]}
    assert len(complete) == 23 and set(complete) == set(lock["names"])
    installed = runtime["installed"]
    assert installed["status"] == "passed" and installed["distribution_count"] == 23
    assert installed["active_edge_count"] == 26 and installed["build_distributions_visible"] is False
    assert set(installed["distributions"]) == set(complete)
    assert len(installed["installed_wheels"]) == 23
    installed_wheels = {row["name"]: row for row in installed["installed_wheels"]}
    assert set(installed_wheels) == set(complete)
    wheel_checks, installed_files, source_checks, native_checks = [], 0, [], []
    eslock = raw_json(extracted / "espeak-inputs/espeak-source-lock.json")

    with zipfile.ZipFile(archive_path) as archive:
        assert len(archive.infolist()) == 654 and set(archive.namelist()) == set(entries)
        for info in archive.infolist():
            row = entries[info.filename]
            data = archive.read(info)
            verify_bytes(data, row)
            assert info.CRC == row["crc"] == zlib.crc32(data) & 0xffffffff
        assert archive.testzip() is None
        for row in data_tree:
            data = archive.read("espeak-component/bundle/share/espeak-ng-data/" + row["path"])
            assert len(data) == row["size"] and digest(data) == row["sha256"] and blob_sha(data) == row["git_blob_sha1"]
        for kind in ("library", "cli"):
            data = archive.read(espeak[kind]["path"].removeprefix("/out/"))
            native_checks.append({"kind": "espeak_" + kind, **verify_elf_receipt(data, espeak[kind])})
        original_manifest = raw_json(extracted / "espeak-inputs/original-source-manifest.json")
        patched_manifest = raw_json(extracted / "espeak-inputs/patched-source-manifest.json")
        assert len(original_manifest) == len(patched_manifest) == 2606
        es_archive = archive.read("espeak-inputs/" + eslock["source"]["artifact"]["filename"])
        verify_bytes(es_archive, eslock["source"]["artifact"])
        es_files = source_archive(es_archive, eslock["source"]["root"], original_manifest, eslock["source"]["exact_symlink"])
        assert sum(map(len, es_files.values())) == 63434177
        assert git_tree(original_manifest) == eslock["source"]["tree"] == "c8d05b9f7d8a1fe9c38ca909e152ee4cec20dd97"
        assert {r["path"] for r in original_manifest} == {r["path"] for r in patched_manifest}
        before_by_name = {r["path"]: r for r in original_manifest}
        differences = [r["path"] for r in patched_manifest if r != before_by_name[r["path"]]]
        assert differences == [eslock["patch"]["source_path"]]
        before = es_files[eslock["patch"]["source_path"]]
        old = b"else()\n  FetchContent_Declare(sonic-git"
        new = b"elseif(NOT DEFINED USE_LIBSONIC OR USE_LIBSONIC)\n  FetchContent_Declare(sonic-git"
        assert before.count(old) == 1 and digest(before) == eslock["patch"]["before_sha256"]
        after = before.replace(old, new, 1)
        changed = next(r for r in patched_manifest if r["path"] == eslock["patch"]["source_path"])
        assert digest(after) == eslock["patch"]["after_sha256"] == changed["sha256"]
        assert len(after) == changed["size"] and blob_sha(after) == changed["git_blob_sha1"]
        assert sum(r["size"] for r in patched_manifest) == 63434219
        source_checks.append({"name": "espeak-ng", "original_files": 2606, "patched_files": 2606,
                              "all_original_archive_blobs_and_single_patch_recomputed": True,
                              "actual_git_tree": eslock["source"]["tree"], "sole_symlink_verified": True})
        prepared = raw_json(extracted / "phonemizer-inputs/PHONEMIZER-PREPARED-INPUTS.json")
        assert prepared["status"] == "verified-inputs" and prepared["installed"] is False and prepared["native_build_performed"] is False
        for source in lock["sources"]:
            source_raw = archive.read("phonemizer-inputs/archives/" + source["artifact"]["filename"])
            verify_bytes(source_raw, source["artifact"])
            originals = source_archive(source_raw, source["archive_root"], source["files"])
            tree = prepared["source_trees"][source["name"]]
            root = "phonemizer-inputs/sources/" + source["archive_root"] + "/"
            names = {name[len(root):] for name in entries if name.startswith(root)}
            assert names == {r["path"] for r in tree}
            for row in tree:
                data = archive.read(root + row["path"])
                verify_bytes(data, row)
                if "patch" in source and row["path"] == source["patch"]["production_path"]:
                    assert digest(originals[row["path"]]) == source["patch"]["before_sha256"]
                    assert digest(data) == source["patch"]["after_sha256"]
                elif "patch" in source and row["path"] == source["patch"]["added_test_path"]:
                    assert row["path"] not in originals
                    assert len(data) == source["patch"]["added_test_bytes"] and digest(data) == source["patch"]["added_test_sha256"]
                else:
                    assert data == originals[row["path"]]
            assert len(tree) == len(originals) + (1 if "patch" in source else 0)
            source_checks.append({"name": source["name"], "original_files": len(originals), "prepared_files": len(tree),
                                  "all_archive_and_prepared_source_bytes_recomputed": True})

        wheel_contents = {}
        for name, package in sorted(complete.items()):
            prefix = "phonemizer-component/wheels/" if name in ("phonemizer", "regex") else "phonemizer-inputs/wheels/"
            content, check = verify_wheel(archive.read(prefix + package["artifact"]["filename"]), package)
            wheel_contents[name] = content
            record = installed_wheels[name]
            assert record["wheel_sha256"] == package["artifact"]["sha256"]
            expected_files = {n: digest(b) for n, b in content.items() if n != package["wheel"]["record_member"]}
            assert len(record["files"]) == record["verified_file_count"] == len(expected_files)
            assert len({r["path"] for r in record["files"]}) == len(expected_files)
            assert {r["path"]: r["sha256"] for r in record["files"]} == expected_files
            assert record["documented_rewrites"] == [{"path": package["wheel"]["record_member"], "reason": "pip installation RECORD"}]
            dist = installed["distributions"][name]
            assert dist["version"] == package["version"] and dist["metadata_sha256"] == package["wheel"]["metadata_sha256"]
            assert dist["requires_dist"] == package["requires_dist"] and dist["requires_python"] == package["requires_python"]
            assert dist["metadata_path"] == runtime["runtime"]["prefix"] + "/lib/python3.14/site-packages/" + package["wheel"]["metadata_member"]
            check["native_reported_original_installed_files_recomputed"] = len(expected_files)
            installed_files += len(expected_files)
            wheel_checks.append(check)
        for package in lock["build_packages"]:
            _, check = verify_wheel(archive.read("phonemizer-inputs/wheels/" + package["artifact"]["filename"]), package)
            check["scope"] = "separate build-only distribution; absent from 23-node runtime"
            wheel_checks.append(check)
        ops = runtime["operations"]
        assert ops["status"] == "passed" and ops["model_downloaded"] is False and ops["speech_synthesis_tested"] is False
        assert ops["regex"]["graphemes"] == ["a\u0301", "🇦🇷", "👩‍💻"] and ops["regex"]["fuzzy_counts"] == [0, 0, 1]
        assert ops["rpds"]["original"] == {"first": 1} and ops["rpds"]["updated"] == {"first": 1, "second": 2}
        for name, operation in (("regex", "regex"), ("rpds-py", "rpds")):
            native = complete[name]["native_members"]
            assert len(native) == 1
            receipt = ops[operation]["native_module"]
            native_checks.append({"kind": name, **verify_elf_receipt(wheel_contents[name][native[0]["member"]], receipt)})
        public = ops["phonemizer"]
        assert public["public_api"] == "phonemizer.phonemize" and public["real_wrapper_proved"] is True
        assert public["dlinfo_imported"] is False and public["njobs"] == 1 and public["version"] == [1, 52, 0, 1]
        api = "phonemizer/backend/espeak/api.py"
        assert public["api_sha256"] == digest(wheel_contents["phonemizer"][api]) == lock["sources"][0]["patch"]["after_sha256"]
        assert public["api_path"] == runtime["runtime"]["prefix"] + "/lib/python3.14/site-packages/" + api
        assert public["library"] == espeak["library"]
        libraw = archive.read(espeak["library"]["path"].removeprefix("/out/"))
        verify_elf_receipt(libraw, public["actual_wrapper_copy"])
        assert public["actual_wrapper_copy"]["path"] != public["library"]["path"]
        assert public["data_path"] == espeak["data_tree"]["path"]
        assert public["public_output"] == public["raw_wrapper_phonemes"].replace("_", "").strip() == "həlˈoʊ"
        assert public["without_stress"] == public["public_output"].replace("ˈ", "").replace("ˌ", "") == "həloʊ"
        assert public["batch_output"] == ["həlˈoʊ, wˈɜːld!", "ɐ sˈɪmpəl tˈɛst."]

    queue, reached, edges = ["phonemizer"], set(), []
    while queue:
        name = queue.pop(0)
        if name in reached:
            continue
        reached.add(name)
        for text in complete[name]["requires_dist"]:
            req = Requirement(text)
            if req.marker and not req.marker.evaluate(lock["environment"]):
                continue
            assert not req.url and not req.extras
            target = canonicalize_name(req.name)
            assert target in complete and req.specifier.contains(complete[target]["version"], prereleases=True)
            edges.append({"from": name, "to": target, "requirement": str(req), "selected_extras": []})
            queue.append(target)
    def edge_key(row):
        return (row["from"], row["to"], str(Requirement(row["requirement"])), tuple(row["selected_extras"]))
    assert len(reached) == 23 and reached == set(lock["names"])
    assert len(edges) == 26
    assert sorted(map(edge_key, edges)) == sorted(map(edge_key, lock["edges"])) == sorted(map(edge_key, installed["graph_edges"]))
    mapped = runtime["mapped_apt_libraries"]
    assert mapped["status"] == "passed" and len(mapped["mapped_apt_libraries"]) == 42
    assert all(r["machine"] == 183 and r["class"] == 64 for r in mapped["mapped_apt_libraries"])
    assert len({r["path"] for r in mapped["mapped_apt_libraries"]}) == 42

    recheck = {
        "schema_version": 1, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_full_sha256_and_all_654_member_crc_sha256_recomputed": True,
        "retained_145_files_match_exact_member_ledger": True,
        "run_input_source_files_exactly_rechecked_and_saved": 23,
        "source_archives_and_prepared_trees": source_checks,
        "foundation": {"cases_passed": 7, "all_child_receipt_sha256_verified": True,
                       "raw_pip_check_exit_code": 1, "separate_requirements_and_provenance_passed": True},
        "espeak_c_abi": {"cases_passed": 14, "positive_child_exits_zero": 13,
                        "expected_missing_data_exit_one": True, "cases": cases,
                        "all_receipt_stdout_stderr_hashes_verified": True,
                        "all_371_data_files_match_zip_bytes_sha256_git_blob_sha1": True,
                        "data_bytes": 18632313, "dictionaries": 117, "separate_real_wrapper_claim": False},
        "compiler_archives_verified_by_native_gate": 44, "selected_toolchain_installs": 19,
        "post_c_abi_provenance_archive_union": 45,
        "phonemizer": {
            "status": "passed", "runtime_distribution_count": 23, "recomputed_reachable_node_count": len(reached),
            "recomputed_active_requirement_edges": edges, "edge_count": 26,
            "graph_recheck_packaging_version": packaging.__version__,
            "runtime_wheels_original_record_crc_metadata_native_hashes_rechecked": 23,
            "separate_build_wheels_rechecked": 2,
            "native_reported_unchanged_installed_files_recomputed": installed_files,
            "installed_record_scope": "Original wheel RECORDs fully rechecked; 23 installed pip RECORDs are documented rewrites. The temporary runtime files themselves are not retained or re-executed by this host recheck.",
            "wheel_checks": wheel_checks, "source_builds": ph["source_builds"],
            "both_built_wheel_transfer_hashes_and_preserved_zip_bytes_verified": True,
            "raw_pip_check_exit_code": 0, "real_runtime_child_exit_code": 0,
            "all_build_pip_runtime_stdout_stderr_hashes_verified": True,
            "mapped_apt_library_count_verified_by_reviewed_native_probe": 42,
            "mapped_apt_scope": "The native probe verified mapped files against pinned APT archives. This host recheck preserves and checks receipt structure, without claiming a second native execution or retaining those 42 library bytes.",
            "real_public_api": public, "regex": ops["regex"], "rpds": ops["rpds"],
            "build_distributions_visible": False},
        "independent_elf_header_and_dynamic_library_rechecks": native_checks,
        "full_engine_proved": False, "model_downloaded": False, "audio_io_performed": False,
        "synthesis_tested": False, "physical_device_proved": False, "release_output": False}
    for name in retained:
        save_new(RAW / name, (extracted / name).read_bytes())
    for path in EVIDENCE.iterdir():
        if path.is_file() and (path.name.endswith("-api.json") or "-api-" in path.name or path.name in ("native-job.log", "verified-artifact.json")):
            raw = path.read_bytes()
            assert b"&sig=" not in raw and b"?sv=" not in raw
            save_new(RAW / path.name, raw)
    for name, raw in source_files.items():
        save_new(RAW / "run-source" / name, raw)
    save_new(RAW / "capture_espeak_component_run_20261017.py", (BASE / "capture_espeak_component_run_20261017.py").read_bytes())
    save_new(RAW / "freeze-run-evidence.py", Path(__file__).read_bytes())
    save_new(RAW / ".gitattributes", b"* -text\n")
    save_new(RAW / "VERIFIED-RESULT-RECHECK.json", encode(recheck))
    rows = [{"path": p.relative_to(RAW).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
            for p in sorted(RAW.rglob("*")) if p.is_file()]
    save_new(RAW / "SAVED-FILES.json", encode({"schema_version": 1, "scope": "All raw files except this ledger",
                                              "files": rows, "file_count": len(rows), "total_bytes": sum(r["bytes"] for r in rows)}))
    for row in rows:
        verify_bytes((RAW / row["path"]).read_bytes(), row)
    all_raw = [p for p in RAW.rglob("*") if p.is_file()]
    summary = {
        "schema_version": 1, "captured_utc": recheck["checked_utc"],
        "repository": "adybag14-cyber/termux-hermes", "run_id": 39073138135,
        "url": "https://github.com/adybag14-cyber/termux-hermes/actions/runs/39073138135",
        "head_sha": HEAD, "job_id": ledger["job_id"], "workflow_conclusion": "success",
        "proved": {
            "scientific_foundation_cases": 7, "espeak_c_abi_checks": 14,
            "source_commit": espeak["source_commit"], "source_actual_git_tree": eslock["source"]["tree"],
            "source_manifest": espeak["source_manifest"], "native_library": espeak["library"], "data_tree": espeak["data_tree"],
            "compiler_archive_identities": 44, "selected_toolchain_installs": 19, "post_c_abi_archive_union": 45,
            "phonemizer_runtime_distributions": 23, "active_requirement_edges": 26,
            "separate_build_distributions": 2, "built_wheels": ph["built_wheels"],
            "native_reported_original_installed_files_recomputed": installed_files,
            "real_public_api": "phonemizer.phonemize", "public_output": public["public_output"],
            "without_stress": public["without_stress"], "batch_output": public["batch_output"],
            "explicit_library_and_actual_wrapper_copy_hash_match": True, "dlinfo_imported": False,
            "native_regex_unicode_grapheme_property_fuzzy_operations": "passed",
            "native_rpds_persistent_map_operation": "passed",
            "phonemizer_runtime_raw_pip_check_exit_code": 0,
            "mapped_apt_libraries_verified_in_native_runtime": 42},
        "evidence_boundaries": {
            "c_abi_and_real_public_wrapper_have_separate_receipts": True,
            "unchanged_foundation_raw_pip_check_exit_code": 1,
            "unchanged_foundation_separate_requirements_and_provenance_gate": "passed",
            "installed_record_scope": recheck["phonemizer"]["installed_record_scope"],
            "mapped_apt_scope": recheck["phonemizer"]["mapped_apt_scope"]},
        "not_proved": ["Complete NeuTTS engine", "Model inference or speech synthesis", "Audio I/O",
                       "Physical device behavior", "Production feature admission", "Release readiness"],
        "source_inputs_receipt": {"path": "run-39073138135/ESPEAK-PROBE-INPUTS.json",
                                  "sha256": digest((RAW / "ESPEAK-PROBE-INPUTS.json").read_bytes()),
                                  "all_23_exact_run_source_files_saved": True},
        "artifact": {"id": ledger["artifact_id"], "bytes": ledger["artifact_bytes"], "sha256": ARTIFACT_SHA,
                     "zip_members": 654, "retained_members": 145, "all_member_crc_and_sha256_verified": True,
                     "full_zip_saved_outside_git": str(archive_path),
                     "full_member_ledger_sha256": digest((RAW / "verified-artifact.json").read_bytes())},
        "native_job_log": ledger["native_job_log"],
        "raw_evidence": {"directory": RAW.relative_to(REPO).as_posix(), "file_count": len(all_raw),
                         "total_bytes": sum(p.stat().st_size for p in all_raw),
                         "saved_files_sha256": digest((RAW / "SAVED-FILES.json").read_bytes()),
                         "result_recheck_sha256": digest((RAW / "VERIFIED-RESULT-RECHECK.json").read_bytes()),
                         "preserved_exact_bytes": True, "binary_wheels_sources_and_data_tree_excluded_from_git": True},
        "earlier_failures_preserved": ["audit/neutts-espeak-native-20261017/run-39068675792.json",
                                      "audit/neutts-espeak-native-20261017/run-39071928457.json"],
        "release_output": False}
    save_new(SUMMARY, encode(summary))
    print(json.dumps({"summary": str(SUMMARY), "summary_bytes": SUMMARY.stat().st_size,
                      "summary_sha256": digest(SUMMARY.read_bytes()), "raw_file_count": len(all_raw),
                      "raw_bytes": sum(p.stat().st_size for p in all_raw),
                      "saved_files_sha256": summary["raw_evidence"]["saved_files_sha256"],
                      "result_recheck_sha256": summary["raw_evidence"]["result_recheck_sha256"],
                      "total_file_count": len(all_raw) + 1,
                      "total_bytes": sum(p.stat().st_size for p in all_raw) + SUMMARY.stat().st_size,
                      "runtime_original_file_hashes_recomputed": installed_files}, indent=2))

if __name__ == "__main__":
    main()
