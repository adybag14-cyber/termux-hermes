#!/usr/bin/env python3
"""Package a validated native Hermes checkout + venv as a Termux .deb."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TERMUX_PREFIX = Path("data/data/com.termux/files/usr")
RUNTIME_DEPS = [
    "bash",
    "ca-certificates",
    "coreutils",
    "curl",
    "dpkg",
    "gdbm",
    "git",
    "libandroid-posix-semaphore",
    "libandroid-support",
    "libbz2",
    "libcrypt",
    "libexpat",
    "libffi",
    "libjpeg-turbo",
    "liblzma",
    "libpng",
    "libsqlite",
    "libtiff",
    "libwebp",
    "libyaml",
    "littlecms",
    "ncurses",
    "ncurses-ui-libs",
    "openjpeg",
    "openssl",
    "python3.13 (>= 3.13.15)",
    "readline",
    "ripgrep",
    "zlib",
]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--hermes-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--wheelhouse-repository", required=True)
    parser.add_argument("--wheelhouse-tag", required=True)
    parser.add_argument("--wheelhouse-sha256sums", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    app = args.app.resolve(strict=True)
    launcher = args.launcher.resolve(strict=True)
    if not (app / "venv" / "bin" / "hermes").is_file():
        raise RuntimeError("validated Hermes venv entrypoint is missing")
    if (app / ".git").exists():
        raise RuntimeError("package source must have .git removed before packaging")
    stamp = (app / ".install_method").read_text(encoding="utf-8").strip()
    if stamp != "apt":
        raise RuntimeError(f"Hermes package must be stamped apt, got {stamp!r}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"hermes-agent_{args.version}_aarch64.deb"

    with tempfile.TemporaryDirectory(prefix="hermes-agent-termux-deb-") as td:
        root = Path(td)
        prefix = root / TERMUX_PREFIX
        packaged_app = prefix / "lib" / "hermes-agent" / "app"
        packaged_app.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app, packaged_app, symlinks=True)

        bin_dir = prefix / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(launcher, bin_dir / "hermes")
        (bin_dir / "hermes").chmod(0o755)

        docs = prefix / "share" / "doc" / "hermes-agent"
        docs.mkdir(parents=True, exist_ok=True)
        metadata = {
            "package": "hermes-agent",
            "package_version": args.version,
            "hermes_version": args.hermes_version,
            "source_repository": args.source_repository,
            "source_commit": args.source_commit,
            "wheelhouse_repository": args.wheelhouse_repository,
            "wheelhouse_tag": args.wheelhouse_tag,
            "wheelhouse_sha256sums_sha256": args.wheelhouse_sha256sums,
            "target": "aarch64-linux-android/Termux",
            "python": "3.13",
        }
        (docs / "BUILD-METADATA.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        debian = root / "DEBIAN"
        debian.mkdir()
        depends = ", ".join(RUNTIME_DEPS)
        (debian / "control").write_text(
            f"""Package: hermes-agent
Version: {args.version}
Architecture: aarch64
Maintainer: adybag14-cyber <adybag14-cyber@users.noreply.github.com>
Depends: {depends}
Suggests: ffmpeg, nodejs (>= 22), uv, wrangler
Section: utils
Priority: optional
Homepage: https://github.com/NousResearch/hermes-agent
Description: Hermes Agent packaged natively for Termux aarch64
 Full Hermes runtime/source asset tree and a prevalidated CPython 3.13 virtual
 environment built in native Android/Bionic Termux. User configuration and
 credentials remain under the user's HERMES_HOME and are never packaged.
""",
            encoding="utf-8",
        )
        postinst = debian / "postinst"
        postinst.write_text(
            "#!/data/data/com.termux/files/usr/bin/sh\n"
            "set -eu\n"
            "echo 'Hermes Agent installed. Run: hermes setup'\n"
            "exit 0\n",
            encoding="utf-8",
        )
        postinst.chmod(0o755)

        run("dpkg-deb", "--build", "--root-owner-group", str(root), str(output))

    run("dpkg-deb", "--info", str(output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())