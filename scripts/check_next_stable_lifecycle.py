"""Check the installed native PM lifecycle in a disposable Termux container."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from packaging.utils import canonicalize_name


def inventory(python: Path) -> dict[str, str]:
    program = (
        "import importlib.metadata,json; "
        "from packaging.utils import canonicalize_name; "
        "print(json.dumps({canonicalize_name(d.metadata['Name']):d.version "
        "for d in importlib.metadata.distributions() if d.metadata['Name']}))"
    )
    return json.loads(subprocess.check_output([str(python), "-I", "-c", program], text=True))


def main() -> None:
    root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    project = root / "app"
    baseline_python = root / "venv/bin/python"
    from pm.environments import selected_venv
    from pm.packages import Venv
    from pm.features import read_features
    from pm.lock import Facts
    from pm.paths import facts_path
    from scripts.termux.feature_profile import BUNDLED_EXTRAS

    expected = list(BUNDLED_EXTRAS)
    assert read_features() == expected, read_features()
    fact = Facts(facts_path()).get("venv")
    assert fact is not None and fact["extras"] == expected, fact
    assert fact["stamp"] == Venv(project).expected_stamp(expected, plugin_dirs=[])
    assert selected_venv(project).resolve() == baseline_python.parent.parent.resolve()
    for name in ("clang", "clang++", "rustc", "cargo", "cmake", "make"):
        assert shutil.which(name) is None, f"native build tool could mask a cache defect: {name}"
    before = inventory(baseline_python)
    assert "anthropic" not in before
    for name in ("uvloop", "python-olm", "mautrix", "nemo-relay"):
        assert name in before, f"prepared compatibility dependency missing: {name}"
    app_lock_before = hashlib.sha256((project / "uv.lock").read_bytes()).hexdigest()
    wheel_digests = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "wheelhouse").glob("*.whl")
    }
    assert wheel_digests
    launcher = Path(os.environ["PREFIX"]) / "bin/hermes"
    start = time.monotonic()
    result = subprocess.run(
        [str(launcher), "pm", "install", "--extra", "anthropic"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900, check=False,
    )
    (out / "cold-cache-install.log").write_text(result.stdout, encoding="utf-8")
    print(result.stdout, flush=True)
    result.check_returncode()
    selected = selected_venv(project).resolve()
    assert selected != baseline_python.parent.parent.resolve(), "optional feature did not publish a generation"
    after = inventory(selected / "bin/python")
    missing = {name: version for name, version in before.items() if after.get(name) != version}
    assert not missing, f"core dependencies were removed or changed: {missing}"
    import tomllib
    lock = tomllib.loads((project / "uv.lock").read_text())
    anthropic = next(p for p in lock["package"] if p["name"] == "anthropic")
    assert after.get("anthropic") == anthropic["version"]
    assert hashlib.sha256((project / "uv.lock").read_bytes()).hexdigest() == app_lock_before
    assert wheel_digests == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "wheelhouse").glob("*.whl")
    }
    subprocess.run([str(launcher), "--version"], check=True, timeout=90)
    subprocess.run([str(launcher), "chat", "--help"], check=True, timeout=90)
    subprocess.run([str(selected / "bin/python"), "-I", "-c",
                    "import anthropic, uvloop, olm, asyncpg, nemo_relay, psutil; "
                    "assert psutil.Process().pid > 0; print('COLD_CACHE_NATIVE_IMPORTS_OK')"],
                   check=True, timeout=90)
    # A repeat request must reuse the completed generation.
    subprocess.run([str(launcher), "pm", "install", "--extra", "anthropic"],
                   check=True, timeout=180)
    assert selected_venv(project).resolve() == selected
    report = {
        "status": "passed", "purpose": "candidate-only; no release",
        "baseline_extras": expected, "new_extra": "anthropic",
        "baseline_distributions": before, "selected_distributions": after,
        "preserved_baseline_count": len(before), "changed_baseline_distributions": missing,
        "wheel_count": len(wheel_digests), "wheel_sha256": wheel_digests,
        "lock_sha256": app_lock_before, "elapsed_seconds": round(time.monotonic() - start, 3),
        "native_build_toolchain_present": False, "repeat_generation_reused": True,
    }
    (out / "COLD-CACHE-LIFECYCLE.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("NEXT_STABLE_COLD_CACHE_LIFECYCLE_OK", flush=True)


if __name__ == "__main__":
    main()
