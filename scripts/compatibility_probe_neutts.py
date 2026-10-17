"""APT scientific behavior with an exact supplemental Python dependency set."""
import ctypes
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import math
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
import zipfile
import wave

CASES = ("torch", "torchaudio", "torchcodec", "scipy", "llvmlite", "soxr")
EXPECTED = {
    "torch": "2.14.1", "torchaudio": "2.11.0", "torchcodec": "0.17.0",
    "scipy": "1.18.1", "llvmlite": "0.49.0", "soxr": "1.1.0", "numpy": "2.5.4",
}

# Frozen versions/artifacts already present in Hermes v0.22.2's immutable lock.
# These complete the APT Torch metadata graph; they do not resolve NeuTTS itself.
SUPPLEMENTAL_LOCK_URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/d923a5eb487a17c0a68801bba9ef0f56c81040a8/uv.lock"
SUPPLEMENTAL_LOCK_SHA256 = "16300cf807347b7fcfa3c19963f5fe950913fdb3e41e3c649ea724bc7dc997da"
SUPPLEMENTAL_LOCK_BYTES = 1202425
SUPPLEMENTAL = [
    {
        "name": "filelock",
        "version": "3.32.4",
        "url": "https://files.pythonhosted.org/packages/01/a4/9b63d595d748e3aff8812b65eacc1a2c4bd90b7c2012e08e72373b4835eb/filelock-3.32.4-py3-none-any.whl",
        "sha256": "22e58ca3b1ae3b98993b762d7338367ae64fe50252bf78d59da3bfebcdf1cedd",
        "bytes": 99864,
        "kind": "wheel"
    },
    {
        "name": "fsspec",
        "version": "2026.7.0",
        "url": "https://files.pythonhosted.org/packages/fd/3c/6a2bf344106328fd04963664a60b9bb6496fc25df8e962fcdc1367285fb9/fsspec-2026.7.0-py3-none-any.whl",
        "sha256": "b57ddbafedfaef7018c1ecab32aa200a9d7ca26b77965f64e48b70061249d279",
        "bytes": 206583,
        "kind": "wheel"
    },
    {
        "name": "jinja2",
        "version": "3.1.6",
        "url": "https://files.pythonhosted.org/packages/62/a1/3d680cbfd5f4b8f15abc1d571870c5fc3e594bb582bc3b64ea099db13e56/jinja2-3.1.6-py3-none-any.whl",
        "sha256": "85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67",
        "bytes": 134899,
        "kind": "wheel"
    },
    {
        "name": "markupsafe",
        "version": "3.0.3",
        "url": "https://files.pythonhosted.org/packages/7e/99/7690b6d4034fffd95959cbe0c02de8deb3098cc577c67bb6a24fe5d7caa7/markupsafe-3.0.3.tar.gz",
        "sha256": "722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698",
        "bytes": 80313,
        "kind": "sdist"
    },
    {
        "name": "mpmath",
        "version": "1.3.0",
        "url": "https://files.pythonhosted.org/packages/43/e3/7d92a15f894aa0c9c4b49b8ee9ac9850d6e63b03c9c32c0367a13ae62209/mpmath-1.3.0-py3-none-any.whl",
        "sha256": "a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c",
        "bytes": 536198,
        "kind": "wheel"
    },
    {
        "name": "networkx",
        "version": "3.6.1",
        "url": "https://files.pythonhosted.org/packages/9e/c9/b2622292ea83fbb4ec318f5b9ab867d0a28ab43c5717bb85b0a5f6b3b0a4/networkx-3.6.1-py3-none-any.whl",
        "sha256": "d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762",
        "bytes": 2068504,
        "kind": "wheel"
    },
    {
        "name": "packaging",
        "version": "26.0",
        "url": "https://files.pythonhosted.org/packages/b7/b9/c538f279a4e237a006a2c98387d081e9eb060d203d8ed34467cc0f0b9b53/packaging-26.0-py3-none-any.whl",
        "sha256": "b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529",
        "bytes": 74366,
        "kind": "wheel"
    },
    {
        "name": "setuptools",
        "version": "83.0.0",
        "url": "https://files.pythonhosted.org/packages/5d/40/e1e72872c6354b306daef1703549e8e83b4d43cfea356311bf722a043752/setuptools-83.0.0-py3-none-any.whl",
        "sha256": "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3",
        "bytes": 1008090,
        "kind": "wheel"
    },
    {
        "name": "sympy",
        "version": "1.14.0",
        "url": "https://files.pythonhosted.org/packages/a2/09/77d55d46fd61b4a135c444fc97158ef34a095e5681d0a6c10b75bf356191/sympy-1.14.0-py3-none-any.whl",
        "sha256": "e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5",
        "bytes": 6299353,
        "kind": "wheel"
    },
    {
        "name": "typing-extensions",
        "version": "4.16.0",
        "url": "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl",
        "sha256": "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
        "bytes": 45571,
        "kind": "wheel"
    }
]
NATIVE_METADATA_SHA256 = {
    "torch": "afeda2aa1bfeb3657774e36875a5995895e951d65473ef831f2eef68a7b1d229",
    "torchaudio": "1ac77b6a77750febc5fe4921ac29d43b3cebf5b191d03c0e1413cab7e343ac31",
    "torchcodec": "260e2c0dc46d782d896f4995b81db75772a9d3d41fdfd891d2a3504b0ba5faf4",
}

# Exact WHEEL bytes retained by the seven reviewed APT archives.
APT_WHEEL_SHA256 = {
    "llvmlite": "05d94d41cb53e5b01ecf10839cd3590e7f740654a0237676c6e73a955e7d9501",
    "numpy": "a20faf9d5aaa10c4de3ffaef30aaf997af4aa80cce1e8d234f1e60f8f6da53d0",
    "scipy": "a20faf9d5aaa10c4de3ffaef30aaf997af4aa80cce1e8d234f1e60f8f6da53d0",
    "soxr": "e07b9b81cf17f8809c2b11d3901b3d6dc621fbcf8104f87d0bc5b8fd282dd540",
    "torch": "ffdbc8fb24da49c70951e582e00ac5885ef338aa509f182f31d9ea4f75abbffa",
    "torchaudio": "05d94d41cb53e5b01ecf10839cd3590e7f740654a0237676c6e73a955e7d9501",
    "torchcodec": "ffdbc8fb24da49c70951e582e00ac5885ef338aa509f182f31d9ea4f75abbffa"
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pinned_url(url, size, digest):
    parts = urllib.parse.urlsplit(url)
    require(parts.scheme == "https" and parts.hostname in ("raw.githubusercontent.com", "files.pythonhosted.org"),
            "unexpected Python input source")
    with urllib.request.urlopen(url, timeout=45) as response:
        raw = response.read(size + 1)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
            "Python input bytes/hash differ: " + url)
    return raw


def inspect_wheel(path, expected, *, universal):
    with zipfile.ZipFile(path) as wheel:
        require(wheel.testzip() is None, "wheel CRC differs")
        names = wheel.namelist()
        require(all(not n.startswith("/") and ".." not in n.split("/") for n in names), "unsafe wheel path")
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA") and n.count("/") == 1]
        require(len(metadata_names) == 1, "wheel must have exactly one root distribution")
        metadata_raw = wheel.read(metadata_names[0])
        metadata = BytesParser().parsebytes(metadata_raw)
        require(canonical(metadata["Name"]) == expected["name"] and metadata["Version"] == expected["version"],
                "wheel name/version differs")
        wheel_metadata = BytesParser().parsebytes(wheel.read(metadata_names[0].removesuffix("METADATA") + "WHEEL"))
        tags = wheel_metadata.get_all("Tag", [])
        native = [n for n in names if n.endswith((".so", ".pyd", ".dll", ".dylib"))]
        if universal:
            require(wheel_metadata["Root-Is-Purelib"] == "true" and tags == ["py3-none-any"] and not native,
                    "supplemental registry wheel is not universal pure Python")
        else:
            from packaging.tags import sys_tags
            from packaging.utils import parse_wheel_filename
            require(bool(parse_wheel_filename(path.name)[3] & set(sys_tags())), "built wheel tags differ from target")
            for name in native:
                raw = wheel.read(name)
                require(raw[:6] == b"\x7fELF\x02\x01" and len(raw) >= 20
                        and struct.unpack_from("<H", raw, 18)[0] == 183,
                        "built extension is not Android's AArch64 ELF")
        return {"name": canonical(metadata["Name"]), "version": metadata["Version"],
                "filename": path.name, "sha256": sha(path), "bytes": path.stat().st_size,
                "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
                "requires_python": metadata.get("Requires-Python"),
                "requires_dist": metadata.get_all("Requires-Dist", []),
                "tags": tags, "native_members": native}


def prepare_python_inputs(out):
    """Fetch only reviewed immutable artifacts; do not install anything on the host."""
    import tarfile
    import tomllib
    require(not out.exists(), "use a new Python input directory")
    out.mkdir()
    lock_raw = read_pinned_url(SUPPLEMENTAL_LOCK_URL, SUPPLEMENTAL_LOCK_BYTES, SUPPLEMENTAL_LOCK_SHA256)
    lock = tomllib.loads(lock_raw.decode("utf-8"))
    rows = []
    for expected in SUPPLEMENTAL:
        matches = [p for p in lock["package"] if p["name"] == expected["name"] and p["version"] == expected["version"]]
        require(len(matches) == 1, "ambiguous or missing frozen Python input")
        package = matches[0]
        candidates = package.get("wheels", []) if expected["kind"] == "wheel" else [package["sdist"]]
        require(any(a["url"] == expected["url"] and a["hash"] == "sha256:" + expected["sha256"]
                    and a["size"] == expected["bytes"] for a in candidates), "Python input differs from frozen lock")
        name = Path(urllib.parse.urlsplit(expected["url"]).path).name
        path = out / name
        path.write_bytes(read_pinned_url(expected["url"], expected["bytes"], expected["sha256"]))
        row = dict(expected, filename=name)
        if expected["kind"] == "wheel":
            row["wheel"] = inspect_wheel(path, expected, universal=True)
        else:
            require(expected["name"] == "markupsafe", "unreviewed source build")
            with tarfile.open(path, "r:gz") as archive:
                metadata = BytesParser().parsebytes(archive.extractfile("markupsafe-3.0.3/PKG-INFO").read())
                require(canonical(metadata["Name"]) == expected["name"] and metadata["Version"] == expected["version"],
                        "sdist metadata differs")
        rows.append(row)
    receipt = {"schema_version": 1, "status": "prepared", "source_lock_url": SUPPLEMENTAL_LOCK_URL,
               "source_lock_sha256": SUPPLEMENTAL_LOCK_SHA256, "source_lock_bytes": SUPPLEMENTAL_LOCK_BYTES,
               "inputs": rows, "engine_dependency_lock": False, "engine_installed": False}
    (out / "inputs.json").write_text(json.dumps(receipt, indent=2) + "\n")
    requirements = [p["name"] + "==" + p["version"] + " --hash=sha256:" + p["sha256"]
                    for p in SUPPLEMENTAL if p["kind"] == "wheel"]
    (out / "registry-wheels.txt").write_text("\n".join(requirements) + "\n")
    print(json.dumps({"status": "prepared", "inputs": len(rows),
                      "source_lock_sha256": SUPPLEMENTAL_LOCK_SHA256}), flush=True)
    return 0


def validate_metadata_closure(distributions, environment):
    """Reject any missing, incompatible, or unpinned active runtime edge."""
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    checked = []
    for name, distribution in sorted(distributions.items()):
        requirement = distribution.get("requires_python")
        require(not requirement or environment["python_full_version"] in SpecifierSet(requirement),
                "distribution excludes this interpreter: " + name)
        for raw in distribution.get("requires_dist", []):
            edge = Requirement(raw)
            active = not edge.marker or edge.marker.evaluate(environment | {"extra": ""})
            row = {"from": name, "requirement": raw, "active": active}
            if active:
                target = canonical(edge.name)
                require(not edge.url, "runtime direct URL dependency requires review: " + raw)
                require(not edge.extras, "runtime dependency extras require review: " + raw)
                require(target in distributions, "missing pinned runtime dependency: " + name + " -> " + raw)
                require(distributions[target]["version"] in edge.specifier,
                        "incompatible pinned runtime dependency: " + name + " -> " + raw)
                row["selected_version"] = distributions[target]["version"]
            checked.append(row)
    return checked


def verify_python_closure():
    from packaging.markers import default_environment
    expected_versions = EXPECTED | {p["name"]: p["version"] for p in SUPPLEMENTAL}
    distributions = {}
    for name, version in expected_versions.items():
        distribution = importlib.metadata.distribution(name)
        require(distribution.version.split("+", 1)[0] == version, "installed dependency version differs: " + name)
        raw = distribution.read_text("METADATA")
        require(raw is not None, "installed dependency has no metadata: " + name)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if name in NATIVE_METADATA_SHA256:
            require(digest == NATIVE_METADATA_SHA256[name], "APT scientific metadata changed: " + name)
        distributions[canonical(name)] = {
            "version": distribution.version, "requires_python": distribution.metadata.get("Requires-Python"),
            "requires_dist": distribution.requires or [], "metadata_sha256": digest,
        }
    environment = default_environment()
    edges = validate_metadata_closure(distributions, environment)
    import jinja2
    import markupsafe
    escaped = str(markupsafe.escape("<tag>&\"'"))
    require(escaped == "&lt;tag&gt;&amp;&#34;&#39;", "MarkupSafe escaping differs")
    rendered = jinja2.Environment(autoescape=True).from_string("{{ value }}").render(value="<owned>&")
    require(rendered == "&lt;owned&gt;&amp;", "Jinja2 escaping differs")
    return {"environment": environment, "distributions": distributions, "runtime_edges": edges,
            "markupsafe_backend": markupsafe._escape_inner.__module__, "escape_result": escaped,
            "jinja2_result": rendered}


def installed_apt_wheel_evidence():
    from packaging.tags import parse_tag, sys_tags
    supported = set(sys_tags())
    evidence = {}
    for name, digest in APT_WHEEL_SHA256.items():
        distribution = importlib.metadata.distribution(name)
        require(distribution.version == EXPECTED[name], "APT distribution version changed: " + name)
        text = distribution.read_text("WHEEL")
        require(text is not None, "APT distribution has no WHEEL metadata: " + name)
        actual_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        require(actual_digest == digest, "APT WHEEL metadata changed: " + name)
        metadata = BytesParser().parsebytes(text.encode("utf-8"))
        tags = metadata.get_all("Tag", [])
        require(tags, "APT distribution has no recorded wheel tags: " + name)
        parsed = {tag for value in tags for tag in parse_tag(value)}
        evidence[name] = {"version": distribution.version, "wheel_metadata": text,
                          "wheel_metadata_sha256": actual_digest, "tags": tags,
                          "matches_current_supported_tags": bool(parsed & supported)}
    return evidence


def classify_pip_check(code, stdout, stderr):
    """Allow measured diagnostics only for the exact original APT tag mismatch."""
    if code == 0:
        require(not stderr and stdout.strip() == "No broken requirements found.",
                "unexpected successful pip-check output")
        return {"status": "passed", "pip_check_passed": True, "wheel_tag_compatibility": "passed"}
    expected = {f"{name} {EXPECTED[name]} is not supported on this platform" for name in APT_WHEEL_SHA256}
    lines = stdout.splitlines()
    require(code == 1 and not stderr and len(lines) == len(expected) and set(lines) == expected,
            "pip check has errors beyond the reviewed APT wheel-tag diagnostic")
    evidence = installed_apt_wheel_evidence()
    require(set(evidence) == set(APT_WHEEL_SHA256), "APT wheel evidence set differs")
    for name, row in evidence.items():
        require(row["version"] == EXPECTED[name] and row["wheel_metadata_sha256"] == APT_WHEEL_SHA256[name]
                and row["matches_current_supported_tags"] is False,
                "unverified APT wheel-tag diagnostic: " + name)
    return {"status": "failed", "pip_check_passed": False, "wheel_tag_compatibility": "unresolved",
            "diagnostic_continuation": "only measured native scientific behavior",
            "apt_wheel_evidence": evidence}


def install_python_inputs(inputs, out):
    """Complete the disposable APT interpreter graph without changing native pins."""
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.getuid() == 1000,
            "native Bionic UID1000 interpreter required")
    require(Path(sys.prefix).resolve() == Path(os.environ["PREFIX"]).resolve(), "managed interpreter is not allowed")
    declared = json.loads((inputs / "inputs.json").read_text())
    require(declared.get("source_lock_sha256") == SUPPLEMENTAL_LOCK_SHA256, "Python input lock differs")
    require(len(declared["inputs"]) == len(SUPPLEMENTAL), "Python input count differs")
    for expected, actual in zip(SUPPLEMENTAL, declared["inputs"], strict=True):
        require(all(actual.get(k) == v for k, v in expected.items()), "Python input manifest differs")
        name = Path(urllib.parse.urlsplit(expected["url"]).path).name
        require(actual["filename"] == name, "Python input filename differs")
        path = inputs / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == expected["bytes"]
                and sha(path) == expected["sha256"], "Python input archive differs")
    work = Path(__file__).parent
    receipt = {"schema_version": 1, "status": "running", "source_lock_sha256": SUPPLEMENTAL_LOCK_SHA256,
               "inputs_sha256": sha(inputs / "inputs.json"), "engine_installed": False,
               "synthesis_tested": False, "native_package_versions_changed": False, "commands": []}
    receipt_path = out / "NEUTTS-PYTHON-RESULT.json"

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    def run_logged(label, args, *, enforce_success=True):
        save()
        try:
            result = subprocess.run(args, capture_output=True, timeout=180)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        (out / (label + ".stdout.log")).write_bytes(stdout[-200000:])
        (out / (label + ".stderr.log")).write_bytes(stderr[-200000:])
        receipt["commands"].append({"label": label, "exit_code": code, "argv": args,
                                    "stdout_bytes": len(stdout), "stderr_bytes": len(stderr)})
        save()
        if enforce_success:
            require(code == 0, "pinned Python dependency command failed: " + label)
        return code, stdout, stderr

    try:
        requirements = work / "registry-wheels.txt"
        requirements.write_text("\n".join(p["name"] + "==" + p["version"] + " --hash=sha256:" + p["sha256"]
                                          for p in SUPPLEMENTAL if p["kind"] == "wheel") + "\n")
        pip = [sys.executable, "-I", "-B", "-m", "pip"]
        run_logged("neutts-python-install", pip + [
            "install", "--no-index", "--no-deps", "--no-compile", "--require-hashes", "--only-binary=:all:",
            "--find-links", str(inputs), "-r", str(requirements),
        ])
        source = next(p for p in SUPPLEMENTAL if p["name"] == "markupsafe")
        wheel_out = work / "markupsafe-wheel"
        wheel_out.mkdir()
        # Unmodified upstream setup.py tries the C extension and supports a
        # plain-Python fallback if this APT-only environment has no compiler.
        # Preserve the real build log and the actual backend; do not fake a compiler.
        run_logged("neutts-markupsafe-build", pip + [
            "wheel", "--no-index", "--no-deps", "--no-build-isolation", "--no-cache-dir",
            "--wheel-dir", str(wheel_out), str(inputs / Path(urllib.parse.urlsplit(source["url"]).path).name),
        ])
        wheels = list(wheel_out.glob("*.whl"))
        require(len(wheels) == 1, "unexpected MarkupSafe build output count")
        receipt["built_markupsafe"] = inspect_wheel(wheels[0], source, universal=False)
        built_requirements = work / "built-markupsafe.txt"
        built_requirements.write_text("markupsafe==" + source["version"] + " --hash=sha256:" + sha(wheels[0]) + "\n")
        run_logged("neutts-markupsafe-install", pip + [
            "install", "--no-index", "--no-deps", "--no-compile", "--require-hashes", "--only-binary=:all:",
            "--find-links", str(wheel_out), "-r", str(built_requirements),
        ])
        receipt["closure"] = verify_python_closure()
        receipt["dependency_closure_passed"] = True
        code, stdout, stderr = run_logged("neutts-python-check", pip + ["check"], enforce_success=False)
        receipt["pip_check_passed"] = False
        receipt["pip_check"] = classify_pip_check(code, stdout.decode("utf-8"), stderr.decode("utf-8"))
        receipt["pip_check_passed"] = receipt["pip_check"]["pip_check_passed"]
        receipt["pip_wheel_tag_compatibility"] = receipt["pip_check"]["wheel_tag_compatibility"]
        receipt["status"] = "passed" if receipt["pip_check_passed"] else "ready-for-native-diagnostics"
        save()
        return 0
    except Exception as exc:
        receipt.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        save()
        raise


def elf(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        header = stream.read(64)
    require(header[:6] == b"\x7fELF\x02\x01", "expected little-endian ELF64")
    machine = struct.unpack_from("<H", header, 18)[0]
    require(machine == 183, "expected actual AArch64 ELF")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path),
            "elf_class": 64, "endianness": "little", "machine": machine}


def libraries():
    prefix = Path(os.environ["PREFIX"])
    owners = {}
    for listing in (prefix / "var/lib/dpkg/info").glob("*.list"):
        for line in listing.read_text(errors="replace").splitlines():
            owners.setdefault(line, []).append(listing.name.removesuffix(".list"))
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/") and ".so" in parts[5]:
            paths.add(parts[5])
    result = []
    for raw in sorted(paths):
        path = Path(raw)
        if path.is_file():
            identity = elf(path)
            identity["mapped_path"] = raw
            identity["dpkg_owners"] = sorted(set(owners.get(raw, []) + owners.get(str(path.resolve()), [])))
            result.append(identity)
    return result


def module_identity(module):
    name = module.__name__.split(".")[0]
    version = importlib.metadata.version(name)
    require(version.split("+", 1)[0] == EXPECTED[name], f"{name} distribution version differs")
    return {"distribution": name, "version": version, "module_file": module.__file__,
            "module_sha256": sha(module.__file__)}


def torch_case():
    import torch
    torch.set_num_threads(2)
    x = torch.arange(8, dtype=torch.float32).reshape(1, 1, 8)
    conv = torch.nn.Conv1d(1, 1, 3, bias=False)
    with torch.no_grad():
        conv.weight.copy_(torch.tensor([[[1.0, 2.0, 1.0]]]))
        result = conv(x).flatten().tolist()
    require(result == [4.0, 8.0, 12.0, 16.0, 20.0, 24.0], "Conv1d differs from exact stencil oracle")
    a = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    b = torch.tensor([[2.0, 0.0], [1.0, 2.0]])
    product = (a @ b).tolist()
    require(product == [[4.0, 4.0], [10.0, 8.0]], "tensor multiplication differs")
    return {"modules": [module_identity(torch)], "conv1d": result, "matmul": product, "device": str(x.device)}


def torchaudio_case():
    import torch
    import torchaudio
    torch.set_num_threads(2)
    signal = torch.tensor([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)])
    actual = torchaudio.functional.resample(signal, 24000, 16000)
    require(tuple(actual.shape) == (1600,) and bool(torch.isfinite(actual).all()), "resampled shape or values differ")
    expected = torch.tensor([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(torch.mean(torch.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "resampling differs from independent sinusoid oracle")
    return {"modules": [module_identity(torch), module_identity(torchaudio)],
            "input_rate": 24000, "output_rate": 16000, "output_samples": 1600, "mean_absolute_error": error}


def torchcodec_case(work):
    import torch
    import torchcodec
    from torchcodec.decoders import AudioDecoder
    pcm = [round(10000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(1600)]
    fixture = work / "owned-pcm.wav"
    with wave.open(str(fixture), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(struct.pack("<" + "h" * len(pcm), *pcm))
    decoded = AudioDecoder(str(fixture)).get_all_samples()
    require(decoded.sample_rate == 16000 and tuple(decoded.data.shape) == (1, 1600), "PCM decode shape/rate differs")
    expected = torch.tensor(pcm, dtype=torch.float32).reshape(1, -1) / 32768
    error = float(torch.max(torch.abs(decoded.data - expected)))
    require(bool(torch.isfinite(decoded.data).all()) and error < 0.000002, "decoded PCM differs from source samples")
    return {"modules": [module_identity(torch), module_identity(torchcodec)],
            "fixture_sha256": sha(fixture), "samples": 1600, "sample_rate": 16000, "maximum_absolute_error": error}


def scipy_case():
    import numpy as np
    import scipy
    from scipy import fft, linalg
    solved = linalg.solve(np.array([[3.0, 1.0], [1.0, 2.0]]), np.array([9.0, 8.0]))
    require(bool(np.allclose(solved, [2.0, 3.0], rtol=0, atol=1e-12)), "LAPACK solution differs")
    transformed = fft.fft(np.array([1.0, 2.0, 3.0, 4.0]))
    require(bool(np.allclose(transformed, [10.0, -2+2j, -2.0, -2-2j], rtol=0, atol=1e-12)), "FFT differs")
    return {"modules": [module_identity(np), module_identity(scipy)], "solution": solved.tolist(),
            "fft": [[float(x.real), float(x.imag)] for x in transformed]}


def llvmlite_case():
    import llvmlite
    from llvmlite import binding as llvm
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    triple = llvm.get_default_triple()
    target = llvm.Target.from_default_triple().create_target_machine()
    module = llvm.parse_assembly("""
define double @owned_mul_add(double %a, double %b) {
entry:
  %product = fmul double %a, %b
  %result = fadd double %product, 2.0
  ret double %result
}
""")
    module.triple = triple
    module.verify()
    with llvm.create_mcjit_compiler(module, target) as engine:
        engine.finalize_object()
        address = engine.get_function_address("owned_mul_add")
        require(address != 0, "JIT returned a null function")
        result = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double, ctypes.c_double)(address)(3.0, 7.0)
        require(result == 23.0, "native JIT function differs from independent arithmetic oracle")
    return {"modules": [module_identity(llvmlite)], "llvm_version": list(llvm.llvm_version_info),
            "target_triple": triple, "native_jit_result": result}


def soxr_case():
    import numpy as np
    import soxr
    signal = np.array([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)], dtype=np.float32)
    actual = soxr.resample(signal, 24000, 16000)
    require(actual.shape == (1600,) and bool(np.isfinite(actual).all()), "soxr shape/values differ")
    expected = np.array([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(np.mean(np.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "soxr differs from independent sinusoid oracle")
    return {"modules": [module_identity(np), module_identity(soxr)], "output_samples": 1600,
            "mean_absolute_error": error}


def run_case(name, out):
    receipt = {"schema_version": 1, "component": name, "status": "failed"}
    start = time.monotonic()
    try:
        result = torchcodec_case(Path(__file__).parent) if name == "torchcodec" else globals()[name + "_case"]()
        receipt.update(status="passed", behavior=result)
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        try:
            receipt["mapped_libraries"] = libraries()
        except Exception as exc:
            receipt.update(status="failed", library_evidence_error=str(exc))
        receipt["elapsed_seconds"] = round(time.monotonic() - start, 3)
        (out / f"neutts-{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if receipt["status"] == "passed" else 1


def execute_case(name, out):
    """Retain every child outcome; failed or malformed evidence cannot pass."""
    require(name in CASES, "unknown native component")
    path = out / f"neutts-{name}.json"
    require(not path.exists(), "refusing a stale component receipt: " + path.name)
    timed_out = False
    launch_error = None
    try:
        child = subprocess.run([sys.executable, "-I", "-B", __file__, "--case", name, str(out)],
                               capture_output=True, timeout=90)
        code, stdout, stderr = child.returncode, child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        timed_out = True
    except OSError as exc:
        code, stdout, stderr = 127, b"", str(exc).encode("utf-8")
        launch_error = {"type": type(exc).__name__, "message": str(exc)}
    row = {"component": name, "exit_code": code, "status": "failed", "timed_out": timed_out,
           "receipt": path.name if path.is_file() else None,
           "receipt_sha256": sha(path) if path.is_file() else None}
    for channel, payload in (("stdout", stdout), ("stderr", stderr)):
        saved = payload[-100000:]
        (out / f"neutts-{name}.{channel}.log").write_bytes(saved)
        row[channel + "_bytes"] = len(payload)
        row[channel + "_saved_bytes"] = len(saved)
        row[channel + "_truncated"] = len(saved) != len(payload)
    if code < 0:
        row["termination_signal"] = -code
    if launch_error:
        row["launch_error"] = launch_error
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(result, dict), "component receipt is not an object")
        require(result.get("schema_version") == 1, "component receipt schema differs")
        require(result.get("component") == name, "component receipt identity differs")
        require(result.get("status") in ("passed", "failed"), "component receipt status differs")
        if code == 0 and not timed_out and result["status"] == "passed":
            require(isinstance(result.get("behavior"), dict), "passed receipt has no behavior")
            require(isinstance(result.get("mapped_libraries"), list) and result["mapped_libraries"],
                    "passed receipt has no native library evidence")
            row["status"] = "passed"
        if "error" in result:
            row["error"] = result["error"]
        if "library_evidence_error" in result:
            row["library_evidence_error"] = result["library_evidence_error"]
    except (OSError, ValueError, RuntimeError) as exc:
        row["receipt_error"] = {"type": type(exc).__name__, "message": str(exc)}
    return row


def main(out):
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.getuid() == 1000,
            "native Bionic UID1000 interpreter required")
    require(sys.version_info[:3] == (3, 14, 6), "actual APT Python version differs")
    require(Path(sys.prefix).resolve() == Path(os.environ["PREFIX"]).resolve(), "probe entered a managed environment")
    packages = {}
    for line in (out / "NEUTTS-INSTALLED-PACKAGES.tsv").read_text().splitlines():
        name, version, architecture = line.split("\t")
        packages[name] = {"version": version, "architecture": architecture}
    pins = []
    for line in (out / "NEUTTS-PINNED-APT.tsv").read_text().splitlines():
        name, version, architecture, digest, size, filename = line.split("\t")
        require(packages.get(name) == {"version": version, "architecture": architecture}, "installed APT pin differs: " + name)
        pins.append({"package": name, "version": version, "architecture": architecture,
                     "sha256": digest, "bytes": int(size), "repository_path": filename})
    python_result_path = out / "NEUTTS-PYTHON-RESULT.json"
    python_result = json.loads(python_result_path.read_text())
    require(python_result.get("status") in ("passed", "ready-for-native-diagnostics")
            and python_result.get("dependency_closure_passed") is True,
            "supplemental Python dependency gate did not pass")
    receipt = {
        "schema_version": 1, "status": "running", "scope": "APT native scientific ABI/behavior with exact Python dependencies",
        "python_dependencies_receipt": python_result_path.name,
        "python_dependencies_receipt_sha256": sha(python_result_path),
        "dependency_closure_passed": True,
        "pip_check_passed": python_result["pip_check_passed"],
        "pip_wheel_tag_compatibility": python_result["pip_wheel_tag_compatibility"],
        "python": {"version": sys.version, "platform": sys.platform, "prefix": sys.prefix,
                   "executable": elf("/proc/self/exe")}, "uid": os.getuid(),
        "apt_archives": pins, "apt_archive_hashes_checked_before_install": True,
        "signed_apt": {p.name: sha(p) for p in (out / "signed-apt").iterdir()},
        "engine_installed": False, "synthesis_tested": False, "model_downloaded": False,
        "physical_audio_tested": False, "candidate_modified": False, "pm_admission_changed": False,
        "cases": [],
    }
    result_path = out / "NEUTTS-CORE-RESULT.json"
    result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name in CASES:
        receipt["cases"].append(execute_case(name, out))
        result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt["scientific_behavior_passed"] = all(row["exit_code"] == 0 and row["status"] == "passed"
                                               for row in receipt["cases"])
    receipt["status"] = "passed" if receipt["scientific_behavior_passed"] else "failed"
    result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "scientific_behavior_passed": receipt["scientific_behavior_passed"],
                      "pip_check_passed": receipt["pip_check_passed"],
                      "pip_wheel_tag_compatibility": receipt["pip_wheel_tag_compatibility"],
                      "cases": receipt["cases"]}), flush=True)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: compatibility_probe_neutts.py --prepare-python OUT | --install-python INPUTS OUT | --case NAME OUT | OUT")
    if sys.argv[1] == "--prepare-python":
        raise SystemExit(prepare_python_inputs(Path(sys.argv[2])))
    if sys.argv[1] == "--install-python":
        raise SystemExit(install_python_inputs(Path(sys.argv[2]), Path(sys.argv[3])))
    if sys.argv[1] == "--case":
        raise SystemExit(run_case(sys.argv[2], Path(sys.argv[3])))
    raise SystemExit(main(Path(sys.argv[1])))
