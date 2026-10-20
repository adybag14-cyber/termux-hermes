#!/usr/bin/env python3
"""One native, offline environment for all 116 original NeuTTS dependencies."""
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import importlib.metadata
import importlib.util
import io
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import traceback
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
PREFIX = Path("/data/data/com.termux/files/usr")
PREPARER_SHA256 = "a537ec2d19cfee4b2cfffcbf96b1eb7a3f1259199b471d10c0da5431b94fc8ed"
PERTH_SHA256 = "7780965f1a336afa8244136e7c40b44d9483d91e17e662f6d07c2cbb78fcd7a2"
NONRUST_SHA256 = "11d0dc5ed34dd45c855bffbba51c02eecf74ce8c5a5dd38cb1483e57f1d14e4b"
FALSE_FLAGS = ("neutts_engine_installed", "default_speech_model_downloaded",
               "production_admission_changed", "release_output")
_KEEPALIVE = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path, limit=16 * 1024 * 1024):
    require(Path(path).is_file() and not Path(path).is_symlink()
            and Path(path).stat().st_size <= limit, "Missing, linked or oversized evidence")
    return json.loads(Path(path).read_bytes())


def save_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def module_at(name, path, expected):
    require(isinstance(expected, str) and sha_file(path) == expected, "Executing support source changed")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def support():
    prep = module_at("_complete_preparation", SCRIPT_DIR / "prepare_neutts_complete_runtime.py",
                     PREPARER_SHA256)
    perth = module_at("_complete_perth_runtime", SCRIPT_DIR / "compatibility_probe_neutts_perth.py",
                      PERTH_SHA256)
    nr = module_at("_complete_isolated_runtime", SCRIPT_DIR / "compatibility_probe_neutts_nonrust.py",
                   NONRUST_SHA256)
    _, common, apt = nr.support()
    return prep, perth, nr, common, apt


def source_module(lock, filename):
    path = "scripts/" + filename
    pin = next(p for p in lock["source_files"] if p["path"] == path)
    return module_at("_complete_operation_" + Path(filename).stem, ROOT / path, pin["sha256"])


def all_apt_pins(lock, prep):
    foundation, _, compiler = prep.apt_helper().load_pins(ROOT, False)
    require(compiler is None and len(foundation) == 122, "Original foundation scope changed")
    pins = {p["name"]: p for p in foundation}
    for p in prep.extra_apt_pins(lock):
        require(p["name"] not in pins, "An extension overwrote an original foundation package")
        pins[p["name"]] = p
    require(len(pins) == 142, "Complete native archive count changed")
    return pins


def validate_install_plan(text, pins):
    expected = {p["name"]: p["version"] for p in pins}
    require(len(expected) == len(pins) == 19, "Unexpected complete-runtime APT install request")
    seen = {}
    for line in text.splitlines():
        require(not line.startswith("Remv "), "APT proposed a removal")
        if line.startswith("Inst "):
            match = re.match(r"^Inst ([a-z0-9+.-]+)(?::[a-z0-9-]+)? (?:\[[^\]]+\] )?\((\S+)", line)
            require(match is not None, "Malformed APT install proposal")
            name, version = match.groups()
            require(name in expected and name not in seen and expected[name] == version,
                    "APT proposed an extra, duplicate or different package")
            seen[name] = version
    require(seen == expected, "APT omitted an original required package")
    return {"status": "exact-original-19-package-plan", "packages": seen, "removals": False}


def source_image(args, lock):
    inputs = read_json(args.image_receipt, 4 * 1024 * 1024)
    require(inputs.get("schema_version") == 1
            and inputs.get("native_image") == lock["platform_runtime"]["native_image"]
            and inputs.get("production_admission_changed") is False
            and inputs.get("release_output") is False, "Host source boundary differs")
    for name in ("compatibility_probe_neutts_complete_runtime.py", "compatibility_probe_neutts_complete_runtime.sh",
                 "prepare_neutts_complete_runtime.py", "neutts_complete_runtime_lock.json"):
        require(inputs.get("inputs", {}).get("scripts/" + name) == sha_file(SCRIPT_DIR / name),
                "Executing complete source differs from host input receipt")
    for pin in lock["source_files"]:
        require(inputs.get("inputs", {}).get(pin["path"]) == pin["sha256"],
                "Reviewed support source is missing from the host receipt")
    path = args.out / "COMPLETE-SOURCE-IMAGE.json"
    rows = read_json(path, 2 * 1024 * 1024)
    require(isinstance(rows, list) and len(rows) == 1, "Ambiguous source image inspection")
    image = rows[0]
    require(image.get("Architecture") == "arm64" and image.get("Os") == "linux"
            and inputs["native_image"] in image.get("RepoDigests", [])
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("Id", "")), "Wrong immutable native image")
    return {"status": "verified-pinned-image", "native_image": inputs["native_image"],
            "docker_image_id": image["Id"], "input_receipt_sha256": sha_file(args.image_receipt),
            "inspection_sha256": sha_file(path)}


def verify_signed_context(args):
    evidence = args.out / "complete-signed-snapshot"
    result = read_json(evidence / "RESULT.json")
    require(result.get("status") == "passed" and result.get("authority") == "native APT configured trust store"
            and result.get("insecure_repository_exceptions") is False
            and result.get("acquired_index_bytes_equal") is True and result.get("archive_count") == 122
            and result.get("inrelease_sha256") == "249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901"
            and result.get("packages_gz_sha256") == "dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6",
            "Unchanged native signed APT snapshot did not pass")
    config = Path(os.environ.get("APT_CONFIG", ""))
    require(config.is_file() and not config.is_symlink()
            and config.read_bytes() == (evidence / "frozen.conf").read_bytes(),
            "Active APT configuration differs from authenticated snapshot")
    lines = config.read_text().splitlines()
    for line in ('Acquire::AllowInsecureRepositories "false";',
                 'Acquire::AllowDowngradeToInsecureRepositories "false";',
                 'Acquire::AllowWeakRepositories "false";',
                 'APT::Get::AllowUnauthenticated "false";', 'Dir::Etc::sourceparts "-";'):
        require(lines.count(line) == 1, "Native APT authentication was relaxed")
    return {"status": "authenticated-original-index", "receipt_sha256": sha_file(evidence / "RESULT.json"),
            "active_config_sha256": sha_file(config)}


def runtime_environment(work, perth):
    env = perth.runtime_environment(work)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
                 "HF_ENDPOINT", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "NUMBA_THREADING_LAYER",
                 "PHONEMIZER_ESPEAK_LIBRARY", "ESPEAK_DATA_PATH", "TRANSFORMERS_CACHE"):
        env.pop(name, None)
    env.update({"HF_HOME": str(work / "hf-home"), "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "NUMBA_THREADING_LAYER": "workqueue",
                "RAYON_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"})
    (work / "hf-home").mkdir(exist_ok=True)
    return env


def validate_network(args, image_id, lock, perth):
    path = args.out / "COMPLETE-NETWORK-OFFLINE.json"
    value = read_json(path, 3 * 1024 * 1024)
    require(value.get("lock_sha256") == sha_file(args.inputs / "neutts_complete_runtime_lock.json")
            and value.get("remaining_networks") == {}, "Offline receipt belongs to different inputs")
    perth.validate_network_inspection(value, image_id, socket.gethostname())
    interfaces = socket.if_nameindex()
    require({name for _, name in interfaces} == {"lo"}, "Non-loopback network interface remains")
    route = Path("/proc/net/route").read_bytes()
    require(len(route.splitlines()) == 1, "A runtime network route remains")
    return {"status": "verified-disconnected", "host_receipt_sha256": sha_file(path),
            "interfaces": interfaces, "route_sha256": hashlib.sha256(route).hexdigest(),
            "network_connections_available": False}


def setup(args, lock, prep, perth, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "inputs",
              **{flag: False for flag in FALSE_FLAGS}}
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["foundation"] = common.validate_foundation(args.out / "NEUTTS-CORE-RESULT.json", lock)
        prep.verify_inputs(args.inputs, args.foundation_inputs)
        report["signed_snapshot"] = verify_signed_context(args)
        pins = all_apt_pins(lock, prep)
        require(not args.apt_archives.exists(), "Use a new exact native APT cache")
        (args.apt_archives / "partial").mkdir(parents=True)
        extra = {p["name"] for p in prep.extra_apt_pins(lock)}
        for pin in pins.values():
            root = args.inputs / "apt-extra-archives" if pin["name"] in extra else args.foundation_inputs / "apt-archives"
            source = prep.archive_path(root, pin)
            target = args.apt_archives / prep.apt_helper().archive_name(pin, native=True)
            prep.verified_bytes(source, pin)
            shutil.copyfile(source, target)
            prep.verified_bytes(target, pin)
            for field, key in (("Package", "name"), ("Version", "version"), ("Architecture", "architecture")):
                actual = subprocess.check_output([str(PREFIX / "bin/dpkg-deb"), "-f", str(target), field],
                                                 text=True, timeout=15).strip()
                require(actual == pin[key], "Staged APT control differs")
        report["inherited_gmp"] = perth.verify_gmp(args, lock, common, apt)
        report["stage"] = "original-19-extra-packages"
        before = perth.installed_packages()
        save_json(args.out / "COMPLETE-APT-BEFORE.json", before)
        requests = [p["name"] + "=" + p["version"] for p in lock["apt_install"]]
        options = ["-o", "Dir::Cache::archives=" + str(args.apt_archives),
                   "-o", "APT::Get::AllowUnauthenticated=false"]
        env = runtime_environment(args.work, perth)
        simulation = common.bounded_command([str(PREFIX / "bin/apt-get"), *options, "--simulate",
            "--reinstall", "--no-install-recommends", "install", *requests],
            args.out, "complete-extra-apt-plan", 90, env)
        raw = (args.out / "complete-extra-apt-plan.stdout.log").read_text()
        report["plan"] = {**validate_install_plan(raw, lock["apt_install"]), "process": simulation}
        report["install"] = common.bounded_command([str(PREFIX / "bin/apt-get"), *options,
            "--yes", "--no-download", "--reinstall", "--no-install-recommends", "install", *requests],
            args.out, "complete-extra-apt-install", 300, env)
        after = perth.installed_packages()
        save_json(args.out / "COMPLETE-APT-AFTER.json", after)
        expected_after = dict(before)
        for pin in lock["apt_install"]:
            expected_after[pin["name"]] = {"version": pin["version"], "architecture": pin["architecture"],
                                           "status": "installed"}
        require(after == expected_after, "APT changed an unreviewed package")
        base = sorted([{"name": prep.canonical_name(d.metadata["Name"]), "version": d.version}
                       for d in importlib.metadata.distributions()], key=lambda row: row["name"])
        expected_names = prep.APT_NAMES | {p["name"] for p in lock["packages"]
                                          if p["origin"]["kind"] == "foundation-core-wheel"} | {"pip", "torchcodec"}
        require(len(base) == len(expected_names) and {p["name"] for p in base} == expected_names,
                "Global foundation acquired an unreviewed Python distribution")
        report.update({"base_python_distributions": base, "verified_archive_count": 142,
                       "only_installed_or_reinstalled": [p["name"] for p in lock["apt_install"]],
                       "compiler_installed": False, "stage": "complete", "status": "passed"})
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "COMPLETE-APT-SETUP.json", report)
    return 0 if report["status"] == "passed" else 1


def image_platform(paths, lock, common, apt, perth):
    platform = lock["platform_runtime"]
    pins = {Path(p["path"]): p for p in platform["files"]}
    require(len(pins) == len(platform["files"]) == 6 and set(paths) <= set(pins),
            "Reviewed original five image files plus PyArrow ICU member changed")
    package = platform["package"]
    require(common.package_snapshot([package["name"]]) == {
        package["name"]: {k: package[k] for k in ("version", "architecture", "status")}},
        "Image owner package changed")
    owners = apt.collect_owners({p.as_posix() for p in paths})
    rows = []
    for path in sorted(paths):
        pin = pins[path]
        require(path.absolute() == path.resolve() and stat.S_ISREG(path.lstat().st_mode)
                and path.stat().st_size == pin["bytes"] and sha_file(path) == pin["sha256"]
                and owners.get(path.as_posix()) == [package["name"]], "Image file bytes, identity or owner differs")
        elf = perth.native_elf(path, dynamic=True)
        require(elf["class"] == pin["elf_class"] == 64 and elf["machine"] == pin["machine"] == 183
                and elf["endianness"] == pin["endianness"] == "little", "Foreign image native ABI")
        rows.append({"package": package["name"], "package_version": package["version"], **elf})
    return {"status": "verified-image-members", "members": rows, "native_image": platform["native_image"]}


def classify_asset_mappings(rows, work, assets, prep):
    """Only actual byte-identical copies created by the real Phonemizer API qualify."""
    library = assets / "libespeak-ng.so"
    pin = {"bytes": library.stat().st_size, "sha256": sha_file(library)}
    copies = []
    for row in rows:
        path = Path(row["resolved_path"])
        if row["classification"] == "rejected-foreign" and not row["deleted"]:
            candidate = path == library.resolve() or path.is_relative_to(work / "tmp")
            if candidate and path.name.startswith("libespeak-ng.so"):
                require(path.absolute() == path.resolve() and stat.S_ISREG(path.lstat().st_mode),
                        "Native eSpeak asset copy is not a regular owned path")
                prep.verified_bytes(path, pin)
                row["classification"] = "espeak-asset-copy"
                copies.append(str(path))
        require(not row["classification"].startswith("rejected-"), "Unreviewed mapped native path: " + str(path))
        require(not path.is_relative_to(PREFIX / "lib/python3.14/site-packages"),
                "Native operation loaded a global Python payload")
    require(copies, "Real Phonemizer did not map its reviewed eSpeak asset")
    return sorted(set(copies))


def native_mappings(args, lock, manifest, prep, perth, nr, common, apt):
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    native = {}
    for p in manifest["wheels"]:
        for row in p["native_members"]:
            native[(site / row["member"]).resolve()] = {"package": p["name"], **row}
    for p in manifest["apt_python"]:
        for row in p["files"]:
            if row["path"].endswith(".so") or ".so." in row["path"]:
                native[(site / row["path"]).resolve()] = {"package": p["name"], **row}
    platform = {Path(p["path"]) for p in lock["platform_runtime"]["files"]}
    raw = nr.read_native_maps()
    (args.out / "COMPLETE-NATIVE-MAPPINGS.raw.txt").write_bytes(raw)
    rows = nr.native_mapping_rows(raw, site, native, platform)
    copies = classify_asset_mappings(rows, args.work, args.inputs / "espeak-assets", prep)
    retained_copies = {str(Path(instance._library._name).resolve()) for instance in _KEEPALIVE}
    require(retained_copies and retained_copies <= set(copies),
            "A retained original eSpeak API library is absent from actual native maps")
    save_json(args.out / "COMPLETE-NATIVE-MAPPINGS.json", {"schema_version": 1, "mappings": rows,
              "raw_sha256": hashlib.sha256(raw).hexdigest()})
    loaded = {Path(r["resolved_path"]) for r in rows if r["classification"] == "source-extension"}
    image_loaded = {Path(r["resolved_path"]) for r in rows if r["classification"] == "image-platform"}
    records = []
    for path in sorted(loaded):
        pin = native[path]
        prep.verified_bytes(path, pin)
        details = perth.native_elf(path, dynamic=True)
        require(details["class"] == 64 and details["machine"] == 183 and details["endianness"] == "little"
                and not any(n in {"libc.so.6", "libstdc++.so.6", "libpython3.14.so.1.0"}
                            for n in details.get("needed", [])), "Foreign extension ABI")
        records.append({"package": pin["package"], **details})
    required = {p["name"] for p in manifest["wheels"] if p["native_members"]} | prep.APT_NAMES
    require(required <= {p["package"] for p in records}, "A selected native dependency was never loaded")
    apt_records = perth.mapped_apt_libraries(rows, args.apt_archives, all_apt_pins(lock, prep), common, apt)
    require(any(p["package"] == "libsndfile" for p in apt_records["mapped_apt_libraries"]),
            "SoundFile did not map original APT libsndfile")
    return {"status": "passed", "actually_mapped_extensions": records, "apt": apt_records,
            "image_platform": image_platform(image_loaded, lock, common, apt, perth),
            "espeak_asset_copies": [perth.native_elf(Path(p), dynamic=True) for p in copies],
            "raw_mapping_sha256": hashlib.sha256(raw).hexdigest()}


@contextlib.contextmanager
def retain_espeak_instances(api_class, maximum=32):
    """Keep only real completed API instances alive until native provenance."""
    require(type(maximum) is int and 1 <= maximum <= 32, "Invalid eSpeak retention bound")
    constructor_code = api_class.__init__.__code__
    state = {"instances": [], "constructor_calls": 0, "maximum_instances": maximum,
             "prior_profile_present": sys.getprofile() is not None}
    previous_profile = sys.getprofile()

    def retain_return(frame, event, value):
        if frame.f_code is not constructor_code:
            return
        instance = frame.f_locals.get("self")
        if type(instance) is not api_class:
            return
        if event == "call":
            state["constructor_calls"] += 1
            require(state["constructor_calls"] <= maximum, "eSpeak constructor retention cap exceeded")
        elif event == "return":
            # The exact original constructor writes _library_path only after
            # successful native initialization. Exceptional returns do not qualify.
            if (instance.__dict__.get("_library") is not None
                    and instance.__dict__.get("_library_path") is not None):
                require(value is None, "Original eSpeak constructor return changed")
                require(not any(old is instance for old in state["instances"]),
                        "Original eSpeak constructor returned the same instance twice")
                state["instances"].append(instance)

    try:
        sys.setprofile(retain_return)
        yield state
    finally:
        sys.setprofile(previous_profile)


def phonemizer_operation(args, lock, prep):
    from phonemizer import phonemize
    from phonemizer.backend.espeak.api import EspeakAPI
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    import rpds
    import xxhash
    assets = args.inputs / "espeak-assets"
    prep.verify_assets(assets, lock)
    os.environ["ESPEAK_DATA_PATH"] = str(assets / "espeak-ng-data")
    EspeakWrapper.set_library(str(assets / "libespeak-ng.so"))
    package = next(p for p in lock["packages"] if p["name"] == "phonemizer")
    wheel_path = args.inputs / "wheels" / package["artifact"]["filename"]
    prep.verified_bytes(wheel_path, package["artifact"])
    source_member = "phonemizer/backend/espeak/api.py"
    source_path = Path(EspeakAPI.__init__.__code__.co_filename)
    expected_source = Path(sys.prefix) / "lib/python3.14/site-packages" / source_member
    with zipfile.ZipFile(wheel_path) as archive:
        original_source = archive.read(source_member)
    require(source_path.resolve() == expected_source.resolve()
            and source_path.read_bytes() == original_source
            and EspeakAPI.__init__.__module__ == "phonemizer.backend.espeak.api"
            and EspeakAPI.__init__.__qualname__ == "EspeakAPI.__init__",
            "eSpeak constructor is not the original installed wheel source")
    constructor_source = inspect.getsource(EspeakAPI.__init__).encode("utf-8")
    with retain_espeak_instances(EspeakAPI) as retained:
        wrapper = EspeakWrapper()
        require(wrapper.library_path.resolve() == (assets / "libespeak-ng.so").resolve()
                and wrapper.data_path.resolve() == (assets / "espeak-ng-data").resolve(),
                "Phonemizer selected a foreign library or data path")
        wrapper.set_voice("en-us")
        raw = wrapper.text_to_phonemes("hello")
        actual = phonemize("hello", language="en-us", backend="espeak", strip=True,
                           preserve_punctuation=True, with_stress=True, njobs=1)
        require(actual == "h\u0259l\u02c8o\u028a" and actual == raw.replace("_", "").strip(),
                "Real Phonemizer/eSpeak public output differs from literal original oracle")
        no_stress = phonemize("hello", language="en-us", backend="espeak", strip=True,
                             with_stress=False, njobs=1)
        require(no_stress == "h\u0259lo\u028a" and "dlinfo" not in sys.modules,
                "Stress option or explicit native loading changed")
    require(retained["instances"] and len(retained["instances"]) == retained["constructor_calls"],
            "An original eSpeak constructor did not complete successfully")
    _KEEPALIVE.extend(retained["instances"])
    copies = []
    for instance in retained["instances"]:
        copied = Path(instance._library._name)
        require(copied.is_absolute() and copied.absolute() == copied.resolve()
                and copied.is_relative_to(args.work / "tmp")
                and stat.S_ISREG(copied.lstat().st_mode),
                "Original eSpeak API copied its library outside owned temporary work")
        prep.verified_bytes(copied, lock["assets"]["library"])
        require(instance._library_path.resolve() == (assets / "libespeak-ng.so").resolve(),
                "An original eSpeak API selected a foreign source library")
        copies.append({"path": str(copied), "bytes": copied.stat().st_size,
                       "sha256": sha_file(copied)})
    require(len({p["path"] for p in copies}) == len(copies), "Repeated eSpeak library copy path")
    original = rpds.HashTrieMap({"first": 1})
    require(dict(original.insert("second", 2)) == {"first": 1, "second": 2}
            and dict(original) == {"first": 1}, "Native persistent map failed")
    require(xxhash.xxh64_hexdigest(b"abc") == "44bc2cf5ad770999", "Native XXHash known answer failed")
    return {"status": "passed", "public_output": actual, "without_stress": no_stress,
            "library_copies": copies, "data_files": 371, "rpds": "passed", "xxhash": "passed",
            "gate_only_lifetime_instrumentation": {
                "kind": "bounded-original-constructor-profile-return-retention",
                "package_source_changed": False, "public_api_replaced": False,
                "retained_until": "complete-native-mapping-verification",
                "constructor_calls": retained["constructor_calls"],
                "retained_instances": len(retained["instances"]),
                "maximum_instances": retained["maximum_instances"],
                "prior_profile_present": retained["prior_profile_present"],
                "prior_profile_restored": True,
                "original_source": {"wheel_sha256": package["artifact"]["sha256"],
                    "member": source_member, "path": str(source_path),
                    "bytes": len(original_source),
                    "sha256": hashlib.sha256(original_source).hexdigest(),
                    "constructor_qualname": EspeakAPI.__init__.__qualname__,
                    "constructor_first_line": EspeakAPI.__init__.__code__.co_firstlineno,
                    "constructor_source_sha256": hashlib.sha256(constructor_source).hexdigest()}},
            "engine_installed": False, "model_downloaded": False}


def llama_operation():
    import llama_cpp
    from llama_cpp import llama_cpp as api
    require(llama_cpp.__version__ == "0.3.36", "Original llama Python version changed")
    library_root = Path(llama_cpp.__file__).resolve().parent / "lib"
    require(Path(api._lib._name).resolve().is_relative_to(library_root),
            "llama loaded a foreign native library")
    api.llama_backend_init()
    try:
        text = api.llama_print_system_info().decode()
        model = api.llama_model_default_params()
        context = api.llama_context_default_params()
        require(text and "CPU" in text and model.load_mode == api.LLAMA_LOAD_MODE_AUTO
                and context.n_ctx > 0 and context.n_batch > 0 and context.n_threads > 0
                and api.llama_supports_gpu_offload() is False and api.llama_supports_rpc() is False,
                "Real portable CPU llama backend failed")
        result = {"status": "passed", "system_info": text, "default_context": {
            "n_ctx": context.n_ctx, "n_batch": context.n_batch, "n_threads": context.n_threads},
            "model_loaded": False, "inference_tested": False}
    finally:
        api.llama_backend_free()
    return result


def torchao_compiler_api_operation():
    """Verify the derivative resolves to the exact real signed Torch helpers."""
    import hashlib
    import sympy
    from torch._inductor.kernel.flex import common
    from torchao.prototype.inductor import int8_sdpa_lowering as lowering

    expected = "d20df6180978954f79a576f20b32a021558318f0c53d2c7c3bb8164edfa1918d"
    source = Path(common.__file__).resolve()
    require(source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == expected,
            "Actual Torch compiler helper source changed")
    require(lowering.construct_strides is common.construct_strides
            and lowering.maybe_realize is common.maybe_realize
            and common.construct_strides.__module__ == "torch._inductor.kernel.flex.common"
            and common.maybe_realize.__module__ == "torch._inductor.kernel.flex.common",
            "TorchAO did not retain the real current Torch compiler functions")
    contiguous = lowering.construct_strides([2, 3, 4], [2, 1, 0])
    transposed = lowering.construct_strides([2, 3, 4], [0, 1, 2])
    require(contiguous == [12, 4, 1] and transposed == [1, 2, 6]
            and lowering.construct_strides([], []) == [],
            "Real Torch compiler stride construction changed")
    symbol = sympy.Symbol("complete_dependency_dimension", integer=True, positive=True)
    integer = sympy.Integer(7)
    realized = lowering.maybe_realize([None, symbol, integer])
    require(len(realized) == 3 and realized[0] is None
            and realized[1] is symbol and realized[2] is integer,
            "Real Torch compiler optional/symbolic input realization changed")
    return {"status": "passed", "provider": "torch._inductor.kernel.flex.common",
            "source_path": str(source), "source_sha256": expected,
            "exact_function_identity": True, "contiguous_strides": contiguous,
            "transposed_strides": transposed, "optional_symbolic_realization": "passed",
            "functions_replaced": False}


def complete_integration_operation(work):
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import psutil
    from lxml import etree
    from PIL import Image
    import datasets
    import transformers
    import torchtune
    import torchao
    compiler_api = torchao_compiler_api_operation()
    import neucodec
    from neucodec import NeuCodec
    import torch
    require(isinstance(NeuCodec, type) and NeuCodec.__module__.startswith("neucodec"),
            "Real NeuCodec class was not imported")
    frame = pd.DataFrame({"text": ["hello", "caf\u00e9"], "value": [3, 7]})
    dataset = datasets.Dataset.from_pandas(frame, preserve_index=False)
    require(dataset.to_pandas().to_dict(orient="list")
            == {"text": ["hello", "caf\u00e9"], "value": [3, 7]},
            "Datasets/Arrow/Pandas interchange changed the literal data")
    table = pa.Table.from_pydict({"x": [1, 2, 3]})
    parquet = io.BytesIO()
    pq.write_table(table, parquet)
    restored = pq.read_table(io.BytesIO(parquet.getvalue()))
    require(restored.to_pydict() == {"x": [1, 2, 3]}, "Original Arrow/Parquet native roundtrip failed")
    root = etree.fromstring(b"<root><v>3</v><v>7</v></root>")
    require(root.xpath("sum(v)") == 10.0, "Native lxml XPath failed")
    image = Image.new("RGB", (3, 2), (12, 34, 56))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    with Image.open(io.BytesIO(encoded.getvalue())) as decoded:
        require(decoded.size == (3, 2) and decoded.getpixel((1, 1)) == (12, 34, 56), "Pillow native PNG failed")
    process = psutil.Process()
    require(process.pid == os.getpid() and process.memory_info().rss > 0, "Native psutil process query failed")
    config = transformers.LlamaConfig(hidden_size=16, intermediate_size=32, num_hidden_layers=1,
                                      num_attention_heads=2, num_key_value_heads=2, vocab_size=32)
    require(config.hidden_size == 16 and config.vocab_size == 32, "Transformers local configuration failed")
    require(np.array_equal(torch.tensor([1, 2, 3]).numpy(), np.array([1, 2, 3])),
            "Torch/NumPy cross-package tensor interchange failed")
    require("neutts" not in sys.modules, "The excluded NeuTTS engine was imported")
    return {"status": "passed", "datasets_rows": len(dataset), "arrow_parquet": "passed",
            "lxml_xpath_sum": 10, "pillow_png": "passed", "psutil_pid": process.pid,
            "neucodec_class": NeuCodec.__module__ + "." + NeuCodec.__name__,
            "torchtune_origin": torchtune.__file__, "torchao_origin": torchao.__file__,
            "torchao_compiler_api": compiler_api,
            "transformers_config": {"hidden_size": config.hidden_size, "vocab_size": config.vocab_size},
            "torch_numpy": "passed", "gated_weights_requested": False}


def runtime_case(args, lock, prep, perth, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "inputs",
              **{flag: False for flag in FALSE_FLAGS}}
    path = args.out / "COMPLETE-RUNTIME-RESULT.json"
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["network"] = validate_network(args, report["source_image"]["docker_image_id"], lock, perth)
        require(os.environ.get("LD_LIBRARY_PATH") == perth.isolated_native_library_path(sys.prefix)
                and os.environ.get("NUMBA_DISABLE_JIT") in (None, "", "0")
                and os.environ.get("HF_HUB_OFFLINE") == os.environ.get("HF_DATASETS_OFFLINE") == "1",
                "Isolated native lookup, real JIT or offline settings changed")
        manifest = read_json(args.environment_manifest)
        perth.validate_manifest(manifest, args, lock)
        report["installed_before"] = nr.installed_inventory(manifest, prep, common)
        report["record_integrity_before"] = perth.installed_records(manifest, prep)
        report["record_integrity_before"]["wheel_count"] = len(manifest["wheels"])
        report["closure"] = prep.validate_closure(lock)
        import torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(2)
        operations = report["operations"] = {}
        nonrust = source_module(lock, "neutts_nonrust_operations.py")
        rust = source_module(lock, "neutts_rust_operations.py")
        tokens = source_module(lock, "neutts_tokenizers_operations.py")
        tiktoken = source_module(lock, "compatibility_probe_neutts_tiktoken.py")
        work = args.work / "actual-operations"
        work.mkdir()
        cases = [
            ("foundation_and_audio", lambda: perth.auxiliary_operations()),
            ("nonrust", lambda: nonrust.run_operations(["pycryptodomex", "pandas", "sentencepiece"], work)),
            ("hf_xet", lambda: rust.hash_operation(work)),
            ("safetensors", lambda: rust.safetensors_operation(work)),
            ("tokenizers", lambda: tokens.tokenizer_operations(work)),
            ("hub_http_yaml", lambda: tokens.dependency_operations(work)),
            ("tiktoken", lambda: tiktoken.operations()),
            ("phonemizer", lambda: phonemizer_operation(args, lock, prep)),
            ("llama_cpu", llama_operation),
            ("perth_public_watermark", lambda: perth.perth_operations(args, lock, prep)),
            ("complete_dependency_integration", lambda: complete_integration_operation(work)),
        ]
        for name, operation in cases:
            report["stage"] = name
            save_json(path, report)
            operations[name] = operation()
            save_json(path, report)
        report["stage"] = "native-provenance"
        report["native_mappings"] = native_mappings(args, lock, manifest, prep, perth, nr, common, apt)
        report["installed_after"] = nr.installed_inventory(manifest, prep, common)
        report["record_integrity_after"] = perth.installed_records(manifest, prep)
        report["record_integrity_after"]["wheel_count"] = len(manifest["wheels"])
        require(report["installed_before"] == report["installed_after"]
                and report["record_integrity_before"] == report["record_integrity_after"],
                "Actual native operations altered the isolated original inputs")
        report["network_after"] = validate_network(args, report["source_image"]["docker_image_id"], lock, perth)
        report.update({"stage": "complete", "status": "passed", "engine_python_bound_changed": False})
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(path, report)
    return 0 if report["status"] == "passed" else 1


def run(args, lock, prep, perth, nr, common, apt):
    report = {"schema_version": 1, "status": "failed", "stage": "setup",
              **{flag: False for flag in FALSE_FLAGS}}
    try:
        report["runtime"] = nr.native_runtime(common)
        report["source_image"] = source_image(args, lock)
        report["foundation"] = common.validate_foundation(args.out / "NEUTTS-CORE-RESULT.json", lock)
        setup_receipt = read_json(args.out / "COMPLETE-APT-SETUP.json")
        require(setup_receipt.get("status") == "passed" and setup_receipt.get("stage") == "complete"
                and setup_receipt.get("verified_archive_count") == 142
                and setup_receipt.get("only_installed_or_reinstalled") == [p["name"] for p in lock["apt_install"]]
                and setup_receipt.get("compiler_installed") is False, "Exact original APT setup did not pass")
        report["apt_setup_sha256"] = sha_file(args.out / "COMPLETE-APT-SETUP.json")
        report["network"] = validate_network(args, report["source_image"]["docker_image_id"], lock, perth)
        prep.verify_inputs(args.inputs)
        for pin in all_apt_pins(lock, prep).values():
            common.archive_path(args.apt_archives, pin)
        env = runtime_environment(args.work, perth)
        wheels = [{**p, "wheel_path": str(args.inputs / "wheels" / p["artifact"]["filename"])} for p in lock["packages"]]
        destination = args.work / "complete-runtime"
        report["stage"] = "isolated-116-dependency-install"
        python, manifest_path, manifest = nr.create_environment(args, lock, wheels, prep.APT_NAMES,
            destination, args.out, "complete-runtime", prep, common, env)
        perth.validate_manifest(manifest, args, lock)
        report["raw_pip"] = nr.raw_pip_check(python, set(lock["names"]), lock, args.out, common, env)
        report["stage"] = "complete-native-runtime"
        command = [str(python), "-I", "-B", str(Path(__file__).resolve()), "--phase", "runtime",
                   "--inputs", str(args.inputs), "--foundation-inputs", str(args.foundation_inputs),
                   "--out", str(args.out), "--work", str(args.work), "--apt-archives", str(args.apt_archives),
                   "--image-receipt", str(args.image_receipt), "--environment-manifest", str(manifest_path)]
        child_env = dict(env)
        child_env["LD_LIBRARY_PATH"] = perth.isolated_native_library_path(destination)
        report["child"] = common.bounded_command(command, args.out, "complete-public-runtime", 1800, child_env)
        child_path = args.out / "COMPLETE-RUNTIME-RESULT.json"
        child = read_json(child_path)
        require(child.get("status") == "passed" and child.get("stage") == "complete"
                and child.get("closure", {}).get("node_count") == 116
                and child.get("closure", {}).get("active_edge_count") == 183
                and len(child.get("operations", {})) == 11
                and child.get("native_mappings", {}).get("status") == "passed"
                and all(child.get(flag) is False for flag in FALSE_FLAGS), "Complete dependency child did not pass")
        report.update({"runtime_receipt": child_path.name, "runtime_receipt_sha256": sha_file(child_path),
                       "actual_runtime_distribution_count": 116, "active_edge_count": 183,
                       "wheel_count": 105, "apt_python_payloads": 11,
                       "foundation_support_outside_graph": ["pip", "torchcodec"],
                       "stage": "complete", "status": "passed"})
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    save_json(args.out / "COMPLETE-COMPONENT-RESULT.json", report)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("setup", "run", "runtime"), default="run")
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--foundation-inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--apt-archives", type=Path, required=True)
    parser.add_argument("--image-receipt", type=Path, required=True)
    parser.add_argument("--environment-manifest", type=Path)
    args = parser.parse_args(argv)
    prep, perth, nr, common, apt = support()
    lock, _ = prep.load_lock(args.inputs / prep.LOCK_FILENAME)
    require(args.out.is_dir() and args.work.is_dir(), "Existing owned evidence and work directories required")
    if args.phase == "runtime":
        require(args.environment_manifest is not None, "Missing isolated environment manifest")
        return runtime_case(args, lock, prep, perth, nr, common, apt)
    if args.phase == "setup":
        return setup(args, lock, prep, perth, nr, common, apt)
    return run(args, lock, prep, perth, nr, common, apt)


if __name__ == "__main__":
    raise SystemExit(main())
