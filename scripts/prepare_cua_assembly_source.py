"""Fetch the four unchanged canonical Hermes assembly files for a CUA candidate.

Only exact public-source bytes at the audited upstream commit are accepted.
No source code is executed by this host preparation step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import shutil
import tempfile
import urllib.request

COMMIT = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
BASE_URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/" + COMMIT + "/"
FILES = {
    "scripts/build/agent.py": (8754, "f59ed0dc39a37814a43f2465e1391311a3ce8203e42a69257e58db6f3cda3652"),
    "scripts/build/inputs.py": (5846, "36fb218726fce97505d7dfd50002046bb9c19b25c0b7cc546bae0b9c586083d9"),
    "scripts/build/launchers.py": (4861, "cf5c225ded65193042a330f69b217a5ffcd5201032cca9e288cebea681cb37b3"),
    "scripts/build/launcher_wrapper.py": (6327, "bfab043b63b8faa588ea1fa6f9143ff33b319df71ef6a7e3855f8574c2b07155"),
}


def download(url: str, size: int) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("unexpected canonical source response or redirect")
        raw = response.read(size + 1)
    return raw


def prepare(out: Path, fetch=download) -> dict:
    out = Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise FileExistsError("canonical assembly input directory must be new")
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".cua-assembly-", dir=out.parent))
    published = False
    try:
        records = {}
        for name, (size, expected) in FILES.items():
            url = BASE_URL + name
            raw = fetch(url, size)
            actual = hashlib.sha256(raw).hexdigest()
            if len(raw) != size or actual != expected:
                raise ValueError("canonical source identity differs: " + name)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o644)
            records[name] = {"bytes": size, "sha256": expected, "source_url": url}
        receipt = {
            "schema_version": 1, "status": "verified-canonical-assembly-source",
            "repository": "NousResearch/hermes-agent", "commit": COMMIT,
            "files": records, "source_executed": False,
            "published_release": False,
        }
        (stage / "SOURCE.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (stage / "SOURCE.json").chmod(0o644)
        for path in (stage, stage / "scripts", stage / "scripts/build"):
            path.chmod(0o755)
        os.rename(stage, out)
        published = True
        return receipt
    finally:
        if not published:
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = prepare(args.out)
    print(json.dumps({"status": result["status"], "out": str(args.out),
                      "files": len(result["files"]), "commit": COMMIT}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
