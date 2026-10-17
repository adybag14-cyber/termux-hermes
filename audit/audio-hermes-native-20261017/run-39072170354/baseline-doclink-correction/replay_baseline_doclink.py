from pathlib import Path, PurePosixPath
import ast
import copy
import hashlib
import importlib.util
import json
import os
import posixpath
import sys

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def read_pin(path, size, sha):
    raw = path.read_bytes()
    assert len(raw) == size and digest(raw) == sha, str(path)
    return raw

old_path = OUT / "before/scripts/prepare_audio_hermes_environment.py"
new_path = ROOT / "scripts/prepare_audio_hermes_environment.py"
old_raw = read_pin(old_path, 72206, "2f45fc5e4ede6dfa895ef56d51c05888ac04ed8fedcf2cd612fe7e1f6f7087ad")
new_raw = read_pin(new_path, 75630, "9c0186ac96cb897fee764a51995b0834586b7c953439092e6b184097753dad88")
old = load("audio_doclink_original_preparer", old_path)
new = load("audio_doclink_corrected_preparer", new_path)
before_raw = read_pin(OUT / "original-payload-inventory.json", 6786488,
                      "0232971ac994a0961954eb7574517492ee02bfc1bce3ce29b9dc37a4924de16b")
after_raw = read_pin(OUT / "post-build-payload-inventory.json", 8341213,
                     "14177cc2987a8c410f533daa910b4ada33ebb0e887c3431d8c8179ad33c45b98")
before = new.json_object(before_raw)["files"]
after = new.json_object(after_raw)["files"]
pin = copy.deepcopy(new.BASELINE_MISSING_DOCUMENTATION_LINK)
assert new.inventory_sha(before) == pin["original_inventory_sha256"]
assert new.inventory_sha(after) == "1095ad2b5508bd3f31bdb166e1e5a712d4627315c6fae27b206785a81ae65fea"
assert before[pin["path"]] == after[pin["path"]] == {
    "kind": "symlink", "mode": 511, "target": pin["target"],
}
assert pin["missing_destination"] not in before and pin["missing_destination"] not in after
assert before[pin["preserved_license"]["path"]] == after[pin["preserved_license"]["path"]] == {
    "kind": "file", "mode": 420, "bytes": pin["preserved_license"]["bytes"],
    "sha256": pin["preserved_license"]["sha256"],
}
license_raw = read_pin(OUT / "GPL-3.0.txt", pin["preserved_license"]["bytes"],
                       pin["preserved_license"]["sha256"])

def resolve_metadata(rows, name, allow_original_installed_prefix=False):
    path = name
    original_absolute_chain = False
    for _ in range(512):
        assert path and not path.startswith("/") and ":" not in path and "\\" not in path
        path = posixpath.normpath(path)
        assert path not in (".", "..") and not path.startswith("../")
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            row = rows.get(prefix)
            if row is not None and row["kind"] == "symlink":
                target = row["target"]
                assert ":" not in target and "\\" not in target
                if target.startswith("/"):
                    installed_prefix = "/data/data/com.termux/files/usr/lib/hermes-agent/"
                    assert allow_original_installed_prefix and target.startswith(installed_prefix)
                    # Metadata lookup only: the original package's installed path.
                    # The corrected checker never permits absolute prepared links.
                    path = posixpath.join(target[len(installed_prefix):], *parts[i:])
                    original_absolute_chain = True
                else:
                    path = posixpath.join(posixpath.dirname(prefix), target, *parts[i:])
                break
        else:
            return path, rows.get(path), original_absolute_chain
    raise AssertionError("metadata symlink cycle")

native_tables = {}
for label, rows in [("original", before), ("post_build", after)]:
    links = {}
    for name, row in rows.items():
        if row["kind"] != "symlink":
            continue
        target, final_row, absolute_chain = resolve_metadata(
            rows, name, allow_original_installed_prefix=label == "original",
        )
        links[name] = {
            "target": row["target"], "resolved_relative_destination": target,
            "destination_present_in_inventory": final_row is not None,
            "destination_kind": None if final_row is None else final_row["kind"],
            "original_installed_absolute_chain_rebased_for_metadata_lookup": absolute_chain,
        }
    absent = {name: row for name, row in links.items() if not row["destination_present_in_inventory"]}
    assert len(links) == 77 and set(absent) == {pin["path"]}
    assert absent[pin["path"]]["resolved_relative_destination"] == pin["missing_destination"]
    native_tables[label] = {
        "entries": len(rows), "inventory_sha256": new.inventory_sha(rows),
        "symlinks": len(links), "present_destinations": len(links) - len(absent),
        "missing_documentation": absent, "all_links": links,
        "direct_absolute_links": {n: r["target"] for n, r in rows.items()
                                  if r["kind"] == "symlink" and r["target"].startswith("/")},
    }
changed_link_rows = {
    n: {"original": r, "post_build": after.get(n)}
    for n, r in before.items() if r["kind"] == "symlink" and r != after.get(n)
}
assert set(changed_link_rows) == {"venv/bin/python"}
assert changed_link_rows["venv/bin/python"]["original"]["target"] == (
    "/data/data/com.termux/files/usr/lib/hermes-agent/tools/python/data/data/com.termux/files/usr/bin/python3.14"
)
assert changed_link_rows["venv/bin/python"]["post_build"]["target"] == (
    "../../tools/python/data/data/com.termux/files/usr/bin/python3.14"
)
assert not native_tables["post_build"]["direct_absolute_links"]

def named_function(raw, name):
    tree = ast.parse(raw)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.dump(node, include_attributes=False)

assert named_function(old_raw, "allowed_changes") == named_function(new_raw, "allowed_changes")
old_changes = old.allowed_changes(before, after)
new_changes = new.allowed_changes(before, after)
assert old_changes == new_changes

# This is a small host filesystem regression, not a reconstructed native payload.
# Only its source-inventory pin is adapted to Windows metadata. The exact native
# source hash, link row, missing destination and license bytes were checked above.
fixture = OUT / "host-regression-payload"
fixture.mkdir(exist_ok=False)
doclink = fixture / pin["path"]
doclink.parent.mkdir(parents=True)
doclink.symlink_to(pin["target"])
license_path = fixture / pin["preserved_license"]["path"]
license_path.parent.mkdir(parents=True)
license_path.write_bytes(license_raw)
for directory, filename, linkname in [
    ("bin", "program", "runner"),
    ("runtime-libs/lib", "libdemo.so.1", "libdemo.so"),
]:
    target = fixture / directory / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"unexecuted filesystem fixture\n")
    (target.parent / linkname).symlink_to(filename)
fixture_before = new.inventory(fixture)
try:
    old.verify_links(fixture)
except old.PreparationError as exc:
    baseline_failure = str(exc)
else:
    raise AssertionError("Original checker must reproduce the documentation failure")
assert baseline_failure == "payload link is not contained: " + pin["path"]
native_pin = copy.deepcopy(new.BASELINE_MISSING_DOCUMENTATION_LINK)
try:
    new.BASELINE_MISSING_DOCUMENTATION_LINK["original_inventory_sha256"] = new.inventory_sha(fixture_before)
    report = new.verify_links(fixture, fixture_before)
finally:
    new.BASELINE_MISSING_DOCUMENTATION_LINK = native_pin
assert len(report["contained_links"]) == 2
assert set(report["baseline_missing_documentation_links"]) == {pin["path"]}
assert report["baseline_missing_documentation_links"][pin["path"]]["working"] is False
assert fixture_before == new.inventory(fixture)
assert not doclink.exists() and doclink.is_symlink()
assert license_path.read_bytes() == license_raw

result = {
    "schema_version": 1, "status": "passed",
    "native_input_replay": native_tables,
    "symlink_rows_already_changed_by_existing_canonical_rebuild": changed_link_rows,
    "original_payload_oracle_unchanged": True,
    "original_payload_oracle_replayed": "passed",
    "reviewed_preparation_changes": len(new_changes),
    "host_filesystem_regression": {
        "original_checker": {"status": "failed-as-expected", "failure": baseline_failure},
        "corrected_checker": {"status": "passed", **report},
        "payload_unchanged": True, "real_pinned_license_bytes": len(license_raw),
        "fixture_inventory_pin_adapted_to_host_metadata": True,
        "native_source_inventory_pin_independently_verified": True,
    },
    "limits": {
        "native_link_check_after_fix": "not-run",
        "native_audio_initialization": "not-run",
        "microphone_accessed": False,
        "physical_vad": "not-tested",
        "package_changed": False,
        "baseline_documentation_link_repaired": False,
        "full_native_engine_synthesis": "not-tested",
    },
    "source_files": {
        "before": {"bytes": len(old_raw), "sha256": digest(old_raw)},
        "after": {"bytes": len(new_raw), "sha256": digest(new_raw)},
    },
}
target = OUT / "baseline-doclink-replay.json"
with target.open("xb") as stream:
    stream.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({
    "status": result["status"], "native_metadata_links": 77,
    "present_destinations": 76, "missing_documentation_links": 1,
    "original_payload_oracle_replayed": "passed",
    "reviewed_preparation_changes": len(new_changes),
    "old_checker_failed": True, "corrected_host_checker_passed": True,
    "native_link_check_after_fix": "not-run",
    "output": str(target), "bytes": target.stat().st_size,
    "sha256": digest(target.read_bytes()),
}))
