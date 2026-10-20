#!/usr/bin/env python3
"""Build reviewed Tiktoken/Regex sources and execute the isolated original 7/6 runtime.

The approved additional Cargo.lock is immutable. The original Setuptools-Rust
backend runs offline without source patches or fabricated platform metadata.
No default encoding vocabulary, speech model, or engine is downloaded/admitted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib
import traceback

SCRIPT_DIR = Path(__file__).resolve().parent
PREPARER_SHA256 = "5cb1e90882272c84f95702de67ff34d36ea82064ecbd237adca19ea6b958bf6b"
# Filled from the peer-reviewed shared helper after its separate HF-only fix.
RUST_PROBE_SHA256 = "79d72b454438d0bdd95dbae17c1883ecc52c96bedbbe39f1fb64d35fd0925944"
PREFIX = Path("/data/data/com.termux/files/usr")
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def module_at(name, path, digest):
    require(path.is_file() and not path.is_symlink()
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            "Shared helper bytes changed; review explicitly: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def helpers():
    own = module_at("_tiktoken_preparer", SCRIPT_DIR / "prepare_neutts_tiktoken.py", PREPARER_SHA256)
    rust = module_at("_tiktoken_rust_probe", SCRIPT_DIR / "compatibility_probe_neutts_rust.py",
                     RUST_PROBE_SHA256)
    prep, apt = rust.helpers()
    return own, rust, prep, apt


def requirement_key(value):
    try:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
    except ImportError:
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.utils import canonicalize_name
    req = Requirement(value)
    return canonicalize_name(req.name), str(req.specifier), tuple(sorted(req.extras)), str(req.marker or ""), req.url


def validate_runtime_closure(lock, manifest, environment):
    """Validate the full original clauses, not just the dependencies we import."""
    try:
        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.utils import canonicalize_name
    except ImportError:
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.specifiers import SpecifierSet
        from pip._vendor.packaging.utils import canonicalize_name
    markers = {**environment, "extra": ""}
    require(all(markers.get(key) == value for key, value in lock["environment"].items()),
            "Actual native marker environment differs from the original design")
    packages = manifest["wheels"]
    require(len(packages) == 7 and len(manifest["names"]) == 7
            and len(set(manifest["names"])) == 7 and set(manifest["names"]) == set(lock["runtime_names"]),
            "Incomplete, duplicate or extra Tiktoken runtime distribution")
    selected = {p["name"]: p for p in packages}
    require(set(selected) == set(manifest["names"]) and len(selected) == len(packages),
            "Runtime manifest names and wheels disagree")
    original = {n["name"]: n for n in lock["runtime_metadata"]}
    edges = []
    for name, package in selected.items():
        basis = original[name]
        require(package["version"] == basis["version"]
                and SpecifierSet(package["requires_python"]) == SpecifierSet(basis["requires_python"])
                and sorted(map(requirement_key, package["requires_dist"]))
                == sorted(map(requirement_key, basis["requires_dist"])),
                "Original full runtime metadata changed: " + name)
        require(SpecifierSet(package["requires_python"]).contains(markers["python_full_version"]),
                "Original package rejects actual native Python: " + name)
        for value in package["requires_dist"]:
            req = Requirement(value)
            require(req.url is None, "Runtime metadata introduced an unreviewed URL")
            if req.marker is not None and not req.marker.evaluate(markers):
                continue
            target = canonicalize_name(req.name)
            require(not req.extras and target in selected
                    and req.specifier.contains(selected[target]["version"]),
                    "Missing, extra-selected or incompatible original runtime dependency")
            edges.append((name, target, requirement_key(value)))
    expected = [(e["from"], e["to"], requirement_key(e["requirement"])) for e in lock["runtime_edges"]]
    require(len(edges) == 6 and sorted(edges) == sorted(expected), "Original six runtime edges changed")
    reached = {"tiktoken"}
    while True:
        expanded = reached | {target for source, target, _ in edges if source in reached}
        if expanded == reached:
            break
        reached = expanded
    require(reached == set(selected), "Tiktoken does not reach the complete runtime")
    return {"status": "passed", "distribution_count": 7, "active_edge_count": 6,
            "selected_extras": [], "original_metadata_modified": False,
            "actual_marker_environment": markers}


def verify_cargo_lock(path, lock, prep):
    raw = prep.verified_bytes(path, lock["captured_cargo_lock"])
    parsed = tomllib.loads(raw.decode("utf-8"))
    packages = parsed["package"]
    registry = {(p["name"], p["version"]): p for p in lock["registry"]}
    identities = [(p["name"], p["version"]) for p in packages]
    require(len(packages) == 28 and len(set(identities)) == 28,
            "Approved full Cargo lock identity count changed")
    local = []
    for package in packages:
        key = package["name"], package["version"]
        if package.get("source") is None:
            require(key == ("tiktoken", "0.14.0"), "Unreviewed local Cargo package")
            local.append(key)
        else:
            require(package["source"] == REGISTRY and key in registry
                    and package.get("checksum") == registry[key]["sha256"],
                    "Cargo lock selected an unpinned source or checksum")
    require(local == [("tiktoken", "0.14.0")], "Original local Cargo root is absent")
    return {"sha256": prep.sha(raw), "full_lock_packages": 28, "original_registry_archives": 27}


def canonical_deps(rows):
    return sorted(({"name": row["name"], "pkg": row["pkg"],
                    "dep_kinds": sorted(row["dep_kinds"], key=lambda x: json.dumps(x, sort_keys=True))}
                   for row in rows), key=lambda x: (x["name"], x["pkg"]))


def validate_cargo_graph(value, lock, source_root, vendor):
    registry = {(p["name"], p["version"]): p for p in lock["registry"]}
    packages = {}
    local = []
    for package in value["packages"]:
        require(package["id"] not in packages, "Duplicate resolved Cargo package")
        packages[package["id"]] = package
        key = package["name"], package["version"]
        manifest = Path(package["manifest_path"])
        require(manifest.is_file() and not manifest.is_symlink(), "Cargo manifest is absent or linked")
        if package["source"] is None:
            require(key == ("tiktoken", "0.14.0")
                    and manifest.resolve() == (source_root / "Cargo.toml").resolve(),
                    "Cargo selected a foreign local manifest")
            local.append(package["id"])
        else:
            require(package["source"] == REGISTRY and key in registry
                    and manifest.resolve() == (vendor / (package["name"] + "-" + package["version"])
                                               / "Cargo.toml").resolve(),
                    "Cargo did not select an original reviewed directory-source crate")
    require(len(local) == 1 and value["resolve"]["root"] == local[0], "Cargo root changed")
    rows = value["resolve"]["nodes"]
    require(len(rows) == 25 and len({n["id"] for n in rows}) == 25
            and all(n["id"] in packages for n in rows), "Target-filtered Cargo inventory changed")
    normalized = []
    for row in rows:
        require(all(dep["pkg"] in packages for dep in row["deps"]),
                "Cargo edge references an unreviewed package")
        package = packages[row["id"]]
        normalized.append({"name": package["name"], "version": package["version"], "source": package["source"],
                           "features": sorted(row["features"]), "dependency_ids": canonical_deps(row["deps"])})
    expected = [{**p, "features": sorted(p["features"]),
                 "dependency_ids": canonical_deps(p["dependency_ids"])}
                for p in lock["target_filtered_packages"]]
    key = lambda p: (p["name"], p["version"])
    require(sorted(normalized, key=key) == sorted(expected, key=key),
            "Reviewed target Cargo packages, features or dependencies changed")
    edges = sum(len(n["dependency_ids"]) for n in normalized)
    require(edges == 41, "Original target Cargo edge census changed")
    return {"status": "passed", "target_packages": 25, "target_edges": 41,
            "target_registry_packages": 24, "full_original_registry_archives": 27,
            "packages": sorted(normalized, key=key)}


def capture_metadata(args, lock, source_root, env, rust, prep):
    verify_cargo_lock(source_root / "Cargo.lock", lock, prep)
    command = [str(PREFIX / "bin/cargo"), "metadata", "--format-version", "1", "--locked", "--offline",
               "--filter-platform", "aarch64-linux-android", "--features", "python",
               "--manifest-path", str(source_root / "Cargo.toml")]
    record = rust.bounded_command(command, args.out, "tiktoken-locked-cargo-metadata", 120, env, source_root)
    value = rust.read_json(args.out / "tiktoken-locked-cargo-metadata.stdout.log", 8_000_000)
    graph = validate_cargo_graph(value, lock, source_root, args.inputs / "vendor")
    graph["command"] = record
    rust.save_json(args.out / "TIKTOKEN-CARGO-GRAPH.json", graph)
    return {"status": "passed", "receipt_sha256": rust.sha_file(args.out / "TIKTOKEN-CARGO-GRAPH.json"),
            "target_packages": 25, "target_edges": 41, "locked_offline_metadata": True}


def validate_backend_declarations(project, source):
    """Compare parsed PEP 508 declarations after exact source-byte verification."""
    from packaging.requirements import Requirement

    declared = project["build-system"]
    actual = [str(Requirement(value)) for value in declared["requires"]]
    expected = [str(Requirement(value)) for value in source["build_requires"]]
    require(actual == expected
            and declared["build-backend"] == source["build_backend"]
            and declared.get("backend-path", []) == source.get("backend_path", []) == [],
            "Original Setuptools backend declarations changed")
    return {"declared_requires": list(declared["requires"]),
            "lock_requires": list(source["build_requires"]),
            "canonical_requires": actual, "backend": declared["build-backend"],
            "backend_path": [], "original_source_metadata_modified": False}


def build_one(args, lock, own, rust, prep):
    rust.native_runtime()
    source = own.source_record(lock, args.source_name)
    own.verify_source_tree(args.source_root, args.source_name, lock, prep)
    manifest = rust.read_json(args.environment_manifest, 8_000_000)
    require(len(manifest["wheels"]) == 5 and set(manifest["names"])
            == {p["name"] for p in lock["python_build_packages"]},
            "Original isolated five-wheel Setuptools backend is incomplete or changed")
    original = {p["name"]: p for p in lock["python_build_packages"]}
    for package in manifest["wheels"]:
        require({k: v for k, v in package.items() if k != "wheel_path"} == original[package["name"]],
                "Backend wheel differs from original selected input")
    inventory = rust.installed_inventory(manifest, prep)
    from packaging.markers import default_environment
    versions = {p["name"]: p["version"] for p in manifest["wheels"]}
    markers = default_environment()
    project = tomllib.loads((args.source_root / "pyproject.toml").read_text())
    declarations = validate_backend_declarations(project, source)
    requirement_report = rust.validate_build_requirements(source["build_requires"], versions, markers)
    for package in manifest["wheels"]:
        rust.validate_build_requirements(package["requires_dist"], versions, markers)
    require(os.environ.get("CARGO_NET_OFFLINE") == "true"
            and os.environ.get("PYO3_PYTHON") == sys.executable
            and os.environ.get("ANDROID_API_LEVEL") == "24",
            "Native offline backend controls changed")
    require(args.wheel_dir.is_dir() and not any(args.wheel_dir.iterdir()), "Use a fresh backend wheel directory")
    os.chdir(args.source_root)
    backend = importlib.import_module(source["build_backend"])
    backend_path = Path(backend.__file__).resolve()
    require(backend_path.is_relative_to(Path(sys.prefix).resolve()), "Backend selected outside isolated environment")
    # Setuptools-Rust1.13.0 has no documented --locked environment option.
    # Keep original setup.py/config_settings unchanged: exact offline vendor plus
    # --locked metadata before building and immutable Cargo.lock after building.
    settings = {}
    dynamic = backend.get_requires_for_build_wheel(config_settings=settings)
    require(isinstance(dynamic, list) and all(isinstance(x, str) for x in dynamic),
            "Invalid dynamic backend requirements")
    dynamic_report = rust.validate_build_requirements(dynamic, versions, markers)
    filename = backend.build_wheel(str(args.wheel_dir), config_settings=settings)
    require(isinstance(filename, str) and filename == Path(filename).name and filename.endswith(".whl")
            and {p.name for p in args.wheel_dir.iterdir()} == {filename}, "Backend emitted unexpected outputs")
    unchanged = own.verify_build_tree(args.source_root, args.source_name, lock, prep)
    cargo = verify_cargo_lock(args.source_root / "Cargo.lock", lock, prep) if args.source_name == "tiktoken" else None
    rust.save_json(args.out / "SOURCE-BACKEND-RESULT.json", {
        "schema_version": 1, "status": "passed", "component": args.source_name,
        "original_archive_sha256": source["artifact"]["sha256"], "backend_path": str(backend_path),
        "backend_sha256": rust.sha_file(backend_path), "build_system_declarations": declarations,
        "declared_build_requirements": requirement_report,
        "dynamic_build_requirements": dynamic_report, "build_environment": inventory,
        "source_after": unchanged, "approved_cargo_lock_after": cargo, "config_settings": settings,
        "original_backend_modified": False, "cargo_offline": True, "new_cargo_resolution": False,
        "platform_override_used": False, "wheel": filename})


def require_python_linkage(rows):
    require(rows and all("libpython3.14.so" in row["needed"] for row in rows),
            "A cp314 extension lacks direct pinned libpython3.14 linkage")
    require(all(not any(name.endswith((".so.6", ".so.0")) or "musl" in name for name in row["needed"])
                for row in rows), "A cp314 extension linked a foreign libc ABI")


def operations():
    """Literal local BPE/UTF-8 cases derived from the original public Encoding API."""
    import tiktoken
    from tiktoken import _tiktoken
    import regex
    import regex._regex
    import requests
    import certifi
    import idna
    import urllib3
    import charset_normalizer
    ranks = {bytes([value]): value for value in range(256)}
    ranks[b"ab"] = 256
    encoding = tiktoken.Encoding("hermes_local_reviewed", pat_str=r"(?s).+",
                                mergeable_ranks=ranks, special_tokens={"<|endoftext|>": 257},
                                explicit_n_vocab=258)
    require(isinstance(encoding._core_bpe, _tiktoken.CoreBPE), "Public Encoding did not construct the real native BPE")
    examples = [("", []), ("ab ab", [256, 32, 256]), ("cab", [99, 256]),
                ("abab", [256, 256]), ("\u00e9\U0001f642", [195, 169, 240, 159, 153, 130]),
                ("ab\nab", [256, 10, 256])]
    observed = []
    for text, expected in examples:
        actual = encoding.encode(text)
        require(actual == expected and encoding.encode_ordinary(text) == expected,
                "Native BPE or literal UTF-8 token expectation failed")
        require(encoding.decode(expected) == text, "Native decode disagrees with a literal known token sequence")
        observed.append({"text": text, "expected_tokens": expected, "actual_tokens": actual})
    require(encoding.encode_batch([text for text, _ in examples], num_threads=2)
            == [tokens for _, tokens in examples], "Native threaded batch encoding failed")
    require(encoding.decode_batch([tokens for _, tokens in examples], num_threads=2)
            == [text for text, _ in examples], "Native threaded batch decoding failed")
    require(encoding.encode_single_token(b"ab") == 256
            and encoding.decode_single_token_bytes(256) == b"ab"
            and encoding.decode_bytes([256, 0, 255]) == b"ab\x00\xff",
            "Native binary single-token API failed")
    try:
        encoding.encode("<|endoftext|>")
    except ValueError:
        special_rejected = True
    else:
        raise ProbeError("Special token was accepted without explicit authorization")
    require(encoding.encode("ab<|endoftext|>", allowed_special={"<|endoftext|>"}) == [256, 257]
            and encoding.decode([256, 257]) == "ab<|endoftext|>",
            "Public special-token allowlist semantics failed")
    require(regex.findall(r"\X", "e\u0301\U0001f642") == ["e\u0301", "\U0001f642"],
            "Original native Regex Unicode grapheme behavior failed")
    request = requests.Request("GET", "https://b\u00fccher.example/ab", params={"q": "a b"}).prepare()
    require(request.url == "https://xn--bcher-kva.example/ab?q=a+b" and request.method == "GET",
            "Original Requests/IDNA/urllib3 local request preparation failed")
    require(idna.encode("b\u00fccher.example") == b"xn--bcher-kva.example"
            and urllib3.util.parse_url(request.url).host == "xn--bcher-kva.example",
            "Original dependency local Unicode host parsing failed")
    match = charset_normalizer.from_bytes(b"plain ASCII payload\n").best()
    require(match is not None and str(match) == "plain ASCII payload\n", "CharsetNormalizer decoding failed")
    certificate = Path(certifi.where()).resolve()
    require(certificate.is_relative_to(Path(sys.prefix).resolve()) and certificate.is_file(),
            "Certifi selected a certificate outside the exact runtime")
    return {"status": "passed", "fixed_examples": observed, "vocabulary_entries": 258,
            "vocabulary_source": "All256 single bytes plus literal ab merge256 and explicit special token257",
            "native_core_type": type(encoding._core_bpe).__name__, "batch_threads": 2,
            "binary_single_token_apis": "passed", "default_special_token_rejected": special_rejected,
            "allowed_special_token": "passed", "regex_unicode_graphemes": "passed",
            "request_url": request.url, "local_dependency_operations": "passed",
            "certifi_file": str(certificate), "network_vocabulary_downloaded": False}


def runtime_one(args, lock, rust, prep, apt):
    rust.native_runtime()
    manifest = rust.read_json(args.environment_manifest, 8_000_000)
    require(len(manifest["wheels"]) == 7 and set(manifest["names"]) == set(lock["runtime_names"]),
            "Runtime must contain exactly the original seven distributions")
    before = rust.installed_inventory(manifest, prep)
    def forbid_network(event, values):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise ProbeError("This deterministic component operation must not access a network")
    sys.addaudithook(forbid_network)
    behavior = operations()
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    selected = {}
    for package in manifest["wheels"]:
        for member in package["native_members"]:
            path = (site / member["member"]).resolve()
            require(path.is_relative_to(site.resolve()), "Extension escaped isolated site")
            require(path.as_posix() not in selected, "Duplicate native extension ownership")
            selected[path.as_posix()] = member
    require(len(selected) == 4, "Expected Tiktoken, Regex and two CharsetNormalizer extensions")
    mapped = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith(str(site)) or ".so" not in fields[5]:
            continue
        value = fields[5]
        require(value in selected and rust.sha_file(Path(value)) == selected[value]["sha256"],
                "Unowned or changed native extension mapping")
        mapped.add(value)
    require(mapped == set(selected), "An original selected native extension was not actually loaded")
    native_elf = [rust.elf(Path(path), dynamic=True) for path in sorted(mapped)]
    require_python_linkage(native_elf)
    _, parent, _ = module_at("_tiktoken_runtime_preparer", SCRIPT_DIR / "prepare_neutts_tiktoken.py",
                            PREPARER_SHA256).load_lock()
    pins = {p["name"]: p for p in parent["build_apt"]["packages"]}
    provenance = rust.verify_mapped_apt_libraries(args.apt_archives, pins, apt)
    require(any(p["package"] == "python" and Path(p["path"]).name == "libpython3.14.so"
                for p in provenance["mapped_apt_libraries"]), "Pinned real libpython mapping was not verified")
    after = rust.installed_inventory(manifest, prep)
    require(before == after, "Operations changed the exact installed wheel contents")
    rust.save_json(args.out / "TIKTOKEN-RUNTIME-RESULT.json", {
        "schema_version": 1, "status": "passed", "complete_distribution_count": 7,
        "before": before, "operations": behavior, "mapped_extensions": native_elf,
        "apt_provenance": provenance, "after": after, "network_connect_and_dns_forbidden": True,
        "engine_installed": False, "model_downloaded": False, "complete_engine_admitted": False})


def run(args, lock, parent, own, rust, prep, apt):
    require(args.out.is_absolute() and not args.out.exists() and not args.out.is_symlink(),
            "Use a fresh absolute native evidence directory")
    args.out.mkdir(parents=True)
    result = {"schema_version": 1, "status": "started", "stage": "inputs",
              "scope": "Original Tiktoken standalone complete base runtime",
              "engine_installed": False, "model_downloaded": False, "release_output": False,
              "complete_engine_admitted": False}
    try:
        result["native_runtime"] = rust.native_runtime()
        result["foundation"] = rust.validate_foundation(args.foundation_receipt, parent)
        _, _, _, result["input_checks"] = own.verify_inputs(args.inputs)
        result["lock_sha256"] = own.LOCK_SHA256
        result["approved_cargo_lock_sha256"] = lock["captured_cargo_lock"]["sha256"]
        result["archives"] = rust.verify_archive_set(args, parent, prep)
        with tempfile.TemporaryDirectory(prefix="neutts-tiktoken-", dir=PREFIX / "tmp") as temporary:
            work = Path(temporary)
            (work / "tmp").mkdir()
            (work / "sources").mkdir()
            env = rust.clean_environment(parent, work)
            result["cargo_directory_source"] = rust.cargo_source_config(work / "cargo-home", args.inputs / "vendor")
            result["stage"] = "signed-compiler-inputs"
            options, result["signed_index"] = rust.signed_snapshot(args, parent, work)
            result["compiler_install"] = rust.install_toolchain(args, parent, options, work)
            result["compiler_controls"] = rust.native_controls(args, parent, work, env, apt)
            build_wheels = [{**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])}
                            for p in lock["python_build_packages"]]
            build_python, build_manifest = rust.create_environment(
                build_wheels, work / "build-venv", args.out, "tiktoken-build-tools", prep, env)
            build_env = rust.with_python(env, build_python)
            result["build_inventory"] = rust.run_inventory(
                build_python, build_manifest, args.out, "tiktoken-build-tools", build_env)
            (args.out / "wheels").mkdir()
            (args.out / "components").mkdir()
            built, completed = {}, []
            for name in ("tiktoken", "regex"):
                result["stage"] = "source-" + name
                source = own.source_record(lock, name)
                root = work / "sources" / source["archive_root"]
                shutil.copytree(args.inputs / "sources" / source["archive_root"], root)
                own.verify_source_tree(root, name, lock, prep)
                graph = capture_metadata(args, lock, root, build_env, rust, prep) if name == "tiktoken" else None
                wheel_dir = args.out / "wheels" / name
                component_out = args.out / "components" / name
                wheel_dir.mkdir()
                component_out.mkdir()
                command = [str(build_python), "-I", "-B", str(Path(__file__).resolve()),
                           "--mode", "build", "--source-name", name, "--source-root", str(root),
                           "--wheel-dir", str(wheel_dir), "--environment-manifest", str(build_manifest),
                           "--inputs", str(args.inputs), "--out", str(component_out)]
                build_record = rust.bounded_command(command, component_out, "native-build-" + name,
                                                    1200 if name == "tiktoken" else 900, build_env, root)
                outputs = list(wheel_dir.iterdir())
                require(len(outputs) == 1 and outputs[0].suffix == ".whl", "Unexpected native build output")
                facts = rust.built_wheel(outputs[0], source, prep)
                native = rust.inspect_wheel_elf(outputs[0], facts, component_out, prep)
                require_python_linkage(native)
                unchanged = own.verify_build_tree(root, name, lock, prep)
                if name == "tiktoken":
                    verify_cargo_lock(root / "Cargo.lock", lock, prep)
                report = {"status": "wheel-built-and-verified", "name": name, "wheel": facts,
                          "build": build_record, "native_elf": native, "source_after": unchanged,
                          "cargo_graph": graph}
                rust.save_json(component_out / "TIKTOKEN-SOURCE-WHEEL-RESULT.json", report)
                completed.append({"name": name, "wheel": facts["artifact"],
                                  "receipt_sha256": rust.sha_file(component_out / "TIKTOKEN-SOURCE-WHEEL-RESULT.json")})
                built[name] = facts
                rust.save_json(args.out / "TIKTOKEN-BUILD-CHECKPOINT.json", {"schema_version": 1, "completed": completed})
            result["built_wheels"] = completed
            runtime_wheels = [built["tiktoken"], built["regex"]] + [
                {**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])}
                for p in lock["runtime_wheels"]]
            manifest = {"names": sorted(p["name"] for p in runtime_wheels), "wheels": runtime_wheels}
            from pip._vendor.packaging.markers import default_environment
            result["runtime_closure"] = validate_runtime_closure(lock, manifest, default_environment())
            result["stage"] = "isolated-runtime"
            runtime_python, runtime_manifest = rust.create_environment(
                runtime_wheels, work / "runtime-venv", args.out, "tiktoken-runtime", prep, env)
            runtime_env = rust.with_python(env, runtime_python)
            result["runtime_inventory"] = rust.run_inventory(
                runtime_python, runtime_manifest, args.out, "tiktoken-runtime", runtime_env)
            runtime_out = args.out / "runtime-operations"
            runtime_out.mkdir()
            result["runtime_command"] = rust.bounded_command(
                [str(runtime_python), "-I", "-B", str(Path(__file__).resolve()), "--mode", "runtime",
                 "--environment-manifest", str(runtime_manifest), "--inputs", str(args.inputs),
                 "--apt-archives", str(args.apt_archives), "--out", str(runtime_out)],
                args.out, "tiktoken-runtime-operations", 180, runtime_env)
            receipt = rust.read_json(runtime_out / "TIKTOKEN-RUNTIME-RESULT.json", 8_000_000)
            require(receipt["status"] == "passed" and receipt["complete_distribution_count"] == 7,
                    "Native runtime receipt failed or incomplete")
            result["runtime_receipt_sha256"] = rust.sha_file(runtime_out / "TIKTOKEN-RUNTIME-RESULT.json")
            result["stage"] = "final-original-inputs"
            own.verify_inputs(args.inputs)
            expected = {p["name"]: {"version": p["version"], "architecture": p["architecture"],
                                    "status": "installed"} for p in parent["build_apt"]["packages"]}
            require(rust.package_snapshot(list(expected)) == expected, "Original APT versions changed")
            result.update(status="passed", stage="complete", original_inputs_unchanged=True)
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        traceback.print_exc()
        return 1
    finally:
        rust.save_json(args.out / "TIKTOKEN-COMPONENT-RESULT.json", result)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("run", "build", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path)
    parser.add_argument("--foundation-receipt", type=Path)
    parser.add_argument("--source-name", choices=("tiktoken", "regex"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--environment-manifest", type=Path)
    args = parser.parse_args()
    own, rust, prep, apt = helpers()
    lock, parent, _ = own.load_lock(args.inputs / own.LOCK_FILENAME)
    if args.mode == "build":
        require(all(x is not None for x in (args.source_name, args.source_root, args.wheel_dir,
                                           args.environment_manifest)), "Incomplete build child arguments")
        build_one(args, lock, own, rust, prep)
        return 0
    if args.mode == "runtime":
        require(args.environment_manifest is not None and args.apt_archives is not None,
                "Incomplete runtime child arguments")
        runtime_one(args, lock, rust, prep, apt)
        return 0
    require(args.apt_archives is not None and args.foundation_receipt is not None,
            "Complete signed foundation inputs are required")
    return run(args, lock, parent, own, rust, prep, apt)


if __name__ == "__main__":
    raise SystemExit(main())
