"""Prepare, install and exercise a distinct unpublished native CUA candidate."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import runpy
import stat
import subprocess
import sys


def run(packaging: pathlib.Path, out: pathlib.Path, work: pathlib.Path, candidate: pathlib.Path) -> int:
    helper = packaging / "scripts/compatibility_probe_cua_hermes.py"
    augmenter = packaging / "scripts/prepare_cua_hermes_candidate.py"
    api = runpy.run_path(str(helper))
    require, digest = api["require"], api["digest"]
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.getuid() == 1000,
            "native Termux UID1000 required")
    verified = api["read_candidate_receipt"](candidate / "candidate-receipt.json")
    package = candidate / verified["package"]["file"]
    require(package.stat().st_size == verified["package"]["bytes"]
            and digest(package) == verified["package"]["sha256"],
            "base candidate bytes differ before native installation")
    standalone = json.loads((out / "CUA-BEHAVIOR.json").read_text())
    require(standalone.get("status") == "passed" and not standalone.get("cleanup_errors"),
            "packaged Hermes requires completed standalone operations")
    driver = out / "bin/cua-driver"
    require(digest(driver) == standalone["binary_sha256"], "standalone driver changed")
    prefix = pathlib.Path(os.environ["PREFIX"])
    payload = prefix / "lib/hermes-agent"
    patch = packaging / "patches/next-stable/cua-hermes-integration.patch"
    head = json.loads((out / "CUA-PROBE-INPUTS.json").read_text())["head_sha"]
    result = {
        "schema_version": 1, "status": "started", "published": False,
        "candidate_receipt_sha256": digest(candidate / "candidate-receipt.json"),
        "candidate": verified,
        "baseline": "exact e271 candidate; a distinct same-version augmented package is prepared and installed",
        "upstream_commit": verified["identity"]["upstream_commit"],
        "baseline_patches": verified["identity"]["patches"],
        "additional_patch": {"path": patch.relative_to(packaging).as_posix(), "sha256": digest(patch)},
        "helper_sha256": digest(helper), "augmenter_sha256": digest(augmenter),
        "driver_sha256": digest(driver), "installed_payload": str(payload),
        "hermes_pm_cua_admission_changed": True, "packaged_default_requested": True,
        "original_candidate_artifact_modified": False,
    }

    def tree_files(root):
        entries = {}
        for current, directories, files in os.walk(root, followlinks=False):
            base = pathlib.Path(current)
            for name in sorted(directories + files):
                path = base / name
                info = path.lstat()
                relative = path.relative_to(root).as_posix()
                if stat.S_ISLNK(info.st_mode):
                    entries[relative] = {"kind": "symlink", "target": os.readlink(path)}
                elif stat.S_ISREG(info.st_mode):
                    entries[relative] = {"kind": "file", "bytes": info.st_size,
                                         "sha256": digest(path), "mode": stat.S_IMODE(info.st_mode)}
                else:
                    require(stat.S_ISDIR(info.st_mode), "unexpected installed payload type: " + relative)
        return entries

    def tree_receipt(entries):
        raw = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        return {"file_and_symlink_count": len(entries), "sha256": hashlib.sha256(raw).hexdigest(),
                "regular_file_bytes": sum(row.get("bytes", 0) for row in entries.values())}

    def install_package(path, log_name):
        with (out / log_name).open("wb") as log:
            subprocess.run(["dpkg", "--force-not-root", "--force-script-chrootless",
                            "--install", str(path)], check=True, stdout=log,
                           stderr=subprocess.STDOUT, timeout=180)
        version = subprocess.check_output(["dpkg-query", "-W", "-f=" + chr(36) + "{Version}", "hermes-agent"],
                                          text=True, timeout=10)
        require(version == "0.22.2-1", "installed candidate version differs")

    before_payload = None
    failure = None
    try:
        control = {
            field: subprocess.check_output(["dpkg-deb", "-f", str(package), field],
                                           text=True, timeout=15).strip()
            for field in ("Package", "Version", "Architecture", "Depends", "Pre-Depends")
        }
        require(control == {"Package": "hermes-agent", "Version": "0.22.2-1",
                            "Architecture": "aarch64", "Depends": "", "Pre-Depends": ""},
                "base candidate Debian identity/dependency contract differs")
        result["baseline_debian_control"] = control
        install_package(package, "hermes-base-candidate-install.log")
        baseline = tree_files(payload)
        result["base_payload"] = tree_receipt(baseline)
        env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "HERMES_RUNTIME_DIR",
                     "HERMES_INSTALL_ROOT", "HERMES_CUA_DRIVER_CMD"):
            env.pop(name, None)
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", CUA_PROBE_HEAD_SHA=head,
                   LD_LIBRARY_PATH=":".join([
                       str(payload / "tools/python") + str(prefix / "lib"),
                       str(payload / "tools/node") + str(prefix / "lib"),
                       str(payload / "tools/ffmpeg") + str(prefix / "lib"),
                       str(payload / "runtime-libs/lib"), str(prefix / "lib"),
                   ]))
        prepared_dir = out / "hermes-prepared"
        prepare_command = [
            str(payload / "venv/bin/python"), "-I", "-B", str(augmenter),
            "--candidate-dir", str(candidate), "--patch", str(patch),
            "--assembly-source", "/assembly-source",
            "--driver", str(driver), "--driver-sha256", standalone["binary_sha256"],
            "--source-receipt", str(out / "CUA-SOURCE-RECEIPT.json"),
            "--packaging-commit", head, "--out", str(prepared_dir),
        ]
        result["prepare_command"] = prepare_command
        with (out / "hermes-candidate-prepare.log").open("wb") as log:
            prepared_process = subprocess.run(prepare_command, env=env, stdout=log,
                                              stderr=subprocess.STDOUT, timeout=600)
        result["prepare_exit_code"] = prepared_process.returncode
        require(prepared_process.returncode == 0, "CUA candidate preparation failed; see hermes-candidate-prepare.log")
        require(tree_files(payload) == baseline, "preparing the new package changed the original installed payload")
        result["base_payload_unchanged_during_preparation"] = True
        prepared_receipt = prepared_dir / "prepared-cua-receipt.json"
        prepared = json.loads(prepared_receipt.read_text())
        require(prepared.get("status") == "prepared-candidate" and prepared.get("published") is False
                and prepared.get("version_bumped") is False and prepared.get("packaging_commit") == head,
                "new candidate receipt identity differs")
        result["prepared_candidate"] = {"receipt": prepared_receipt.relative_to(out).as_posix(),
                                        "sha256": digest(prepared_receipt), "package": prepared["package"]}
        prepared_package = prepared_dir / prepared["package"]["file"]
        require(prepared_package.is_file() and prepared_package.stat().st_size == prepared["package"]["bytes"]
                and digest(prepared_package) == prepared["package"]["sha256"],
                "prepared candidate package bytes differ")
        install_package(prepared_package, "hermes-prepared-candidate-install.log")
        before_payload = tree_files(payload)
        result["installed_payload_before"] = tree_receipt(before_payload)
        resident_driver = payload / prepared["bundled_tools"]["tool"]["entry"] / prepared["bundled_tools"]["tool"]["binary"]
        require(digest(resident_driver) == standalone["binary_sha256"], "installed resident driver differs")
        command = [str(payload / "venv/bin/python"), "-I", "-B", str(helper),
                   "--source", str(payload / "app"), "--driver", str(resident_driver),
                   "--driver-sha256", standalone["binary_sha256"],
                   "--fixture", str(work / "cua-fixture"), "--out", str(out / "hermes-integration"),
                   "--candidate-receipt", str(candidate / "candidate-receipt.json"),
                   "--packaged-default", "--prepared-receipt", str(prepared_receipt)]
        result["command"] = command
        result["loader_library_paths"] = env["LD_LIBRARY_PATH"].split(":")
        with (out / "hermes-integration.log").open("wb") as log:
            completed = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        result["helper_exit_code"] = completed.returncode
        require(completed.returncode == 0, "native packaged Hermes integration failed; see hermes-integration.log")
        helper_result = out / "hermes-integration/hermes-cua-result.json"
        require(json.loads(helper_result.read_text()).get("status") == "passed",
                "Hermes helper did not produce a passed result")
        result["helper_result"] = {"path": helper_result.relative_to(out).as_posix(), "sha256": digest(helper_result)}
        install_package(prepared_package, "hermes-prepared-candidate-reinstall.log")
        result["same_version_reinstall_passed"] = True
        result["status"] = "passed"
    except BaseException as exc:
        failure = exc
        result["status"], result["error"] = "failed", repr(exc)
    finally:
        preservation_errors = []
        if before_payload is not None:
            try:
                result["installed_payload_after"] = tree_receipt(tree_files(payload))
                result["installed_payload_unchanged"] = result["installed_payload_before"] == result["installed_payload_after"]
                if not result["installed_payload_unchanged"]:
                    preservation_errors.append("augmented candidate payload changed during execution or reinstall")
            except BaseException as exc:
                preservation_errors.append("payload preservation check: " + repr(exc))
        try:
            require(digest(package) == verified["package"]["sha256"], "base candidate artifact changed")
        except BaseException as exc:
            preservation_errors.append("base artifact preservation check: " + repr(exc))
        result["preservation_errors"] = preservation_errors
        if preservation_errors:
            result["status"] = "failed"
        (out / "CUA-HERMES-PREPARATION.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "receipt": "CUA-HERMES-PREPARATION.json",
                          "helper_exit_code": result.get("helper_exit_code")}), flush=True)
    if failure is not None:
        raise failure
    require(result["status"] == "passed", "candidate preservation check failed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_cua_packaged_probe.py PACKAGING OUT WORK VERIFIED_CANDIDATE")
    raise SystemExit(run(*(pathlib.Path(p) for p in sys.argv[1:])))
