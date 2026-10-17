#!/usr/bin/env python3
"""Build and exercise one frozen feature closure in a disposable Android PM env.

The lock is checked through PM first. Graph traversal starts at the requested
feature's own edges, so a native probe does not rebuild the unrelated Hermes
core. Artifacts are still selected by the canonical SHA-locked wheel builder.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import tomllib

ANCHORS = {
    "uvloop": {"uvloop"},
    "matrix": {"aiohttp", "aiohttp-socks", "aiosqlite", "asyncpg", "mautrix",
               "python-olm", "pycryptodome"},
    "nemo": {"nemo-relay"},
}


def locked_closure(lock: dict, group: str, environment: dict[str, str]) -> dict[str, dict]:
    """Walk actual target-admitted package and extra edges, rejecting ambiguity."""
    from packaging.markers import Marker
    from packaging.utils import canonicalize_name

    by_name = defaultdict(list)
    for package in lock["package"]:
        by_name[canonicalize_name(package["name"])].append(package)
    roots = by_name["hermes-agent"]
    if len(roots) != 1:
        raise ValueError("Expected exactly one Hermes project in the frozen lock")
    root = roots[0]
    if group == "nemo":
        starts = [d for d in root.get("dependencies", []) if d["name"] == "nemo-relay"]
    else:
        starts = root.get("optional-dependencies", {}).get(group, [])
    selected, seen = {}, set()

    def admits(marker: str | None) -> bool:
        return not marker or Marker(marker).evaluate(environment)

    def visit(edge: dict) -> None:
        if not admits(edge.get("marker")):
            return
        name = canonicalize_name(edge["name"])
        matches = [
            p for p in by_name[name]
            if ("version" not in edge or p["version"] == edge["version"])
            and ("source" not in edge or p["source"] == edge["source"])
            and (not p.get("resolution-markers")
                 or any(admits(m) for m in p["resolution-markers"]))
        ]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous or missing locked target for {name}")
        package = matches[0]
        if name in selected and selected[name] != package:
            raise ValueError(f"Conflicting locked versions for {name}")
        selected[name] = package
        extras = tuple(sorted(edge.get("extra", [])))
        identity = (name, package["version"], extras)
        if identity in seen:
            return
        seen.add(identity)
        dependencies = list(package.get("dependencies", []))
        for extra in extras:
            if extra not in package.get("optional-dependencies", {}):
                raise ValueError(f"Missing locked extra: {name}[{extra}]")
            dependencies.extend(package["optional-dependencies"][extra])
        for dependency in dependencies:
            visit(dependency)

    for edge in starts:
        visit(edge)
    if missing := ANCHORS[group] - selected.keys():
        raise ValueError(f"{group} is still target-excluded or incomplete: {sorted(missing)}")
    if "hermes-agent" in selected:
        raise ValueError("A feature probe must not recursively include the Hermes core")
    return dict(sorted(selected.items()))


def source_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_native() -> None:
    if sys.platform != "android" or platform.machine() not in ("aarch64", "arm64"):
        raise RuntimeError(f"Native Android ARM64 required, got {sys.platform}/{platform.machine()}")
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError(f"The published bundle's Python 3.14 ABI is required: {sys.version}")


async def _tcp_roundtrip() -> None:
    async def echo(reader, writer):
        try:
            writer.write(await reader.readexactly(13))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"termux-native")
        await writer.drain()
        assert await reader.readexactly(13) == b"termux-native"
        writer.close()
        await writer.wait_closed()
        assert await asyncio.gather(*(asyncio.sleep(0, result=n) for n in range(8))) == list(range(8))
    finally:
        server.close()
        await server.wait_closed()


def exercise_uvloop() -> list[str]:
    import uvloop
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(asyncio.wait_for(_tcp_roundtrip(), 15))
    return ["uvloop native extension", "TCP roundtrip", "task scheduling", "loop shutdown"]


async def _matrix_http() -> None:
    from aiohttp import ClientSession, web
    import aiosqlite

    app = web.Application()
    async def handler(request):
        return web.Response(text=await request.text())
    app.router.add_post("/echo", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        port = site._server.sockets[0].getsockname()[1]
        async with ClientSession() as session:
            async with session.post(f"http://127.0.0.1:{port}/echo", data="matrix-native") as response:
                assert response.status == 200
                assert await response.text() == "matrix-native"
        async with aiosqlite.connect(":memory:") as db:
            await db.execute("create table state (value text)")
            await db.execute("insert into state values (?)", ("encrypted",))
            async with db.execute("select value from state") as cursor:
                assert await cursor.fetchone() == ("encrypted",)
    finally:
        await runner.cleanup()


def exercise_matrix() -> list[str]:
    import olm
    import mautrix.crypto
    import asyncpg.protocol.protocol
    from asyncpg.pgproto.pgproto import UUID
    from Crypto.Cipher import AES

    alice, bob = olm.Account(), olm.Account()
    bob.generate_one_time_keys(1)
    key = next(iter(bob.one_time_keys["curve25519"].values()))
    outgoing = olm.OutboundSession(alice, bob.identity_keys["curve25519"], key)
    message = outgoing.encrypt("olm-native")
    incoming = olm.InboundSession(bob, message)
    assert incoming.decrypt(message) == "olm-native"
    bob.remove_one_time_keys(incoming)
    assert outgoing.decrypt(incoming.encrypt("olm-reply")) == "olm-reply"
    group = olm.OutboundGroupSession()
    receiver = olm.InboundGroupSession(group.session_key)
    assert receiver.decrypt(group.encrypt("megolm-native"))[0] == "megolm-native"
    cipher = AES.new(b"0" * 16, AES.MODE_ECB)
    assert cipher.decrypt(cipher.encrypt(b"1" * 16)) == b"1" * 16
    assert str(UUID("12345678-1234-5678-1234-567812345678")) == "12345678-1234-5678-1234-567812345678"
    asyncio.run(asyncio.wait_for(_matrix_http(), 20))
    return ["Olm bidirectional ratchet", "Megolm roundtrip", "mautrix crypto import",
            "PyCryptodome AES", "asyncpg native UUID codec", "aiohttp loopback", "SQLite state"]


def exercise_nemo() -> list[str]:
    import nemo_relay

    report = nemo_relay.plugin.validate_exact({"version": 1, "components": []})
    assert report["config"]["diagnostics"] == []
    assert report["resolved_config"]["version"] == 1
    assert report["resolved_config"]["components"] == []
    with nemo_relay.use_scope_stack(nemo_relay.create_scope_stack()):
        parent = nemo_relay.scope.push("termux-native", nemo_relay.ScopeType.Custom)
        try:
            first = nemo_relay.capture_traceparent().split("-")
            assert len(first) == 4 and len(first[1]) == 32 and len(first[2]) == 16
            child = nemo_relay.scope.push("nested-native", nemo_relay.ScopeType.Function)
            try:
                nested = nemo_relay.capture_traceparent().split("-")
                assert nested[1] == first[1] and nested[2] != first[2]
            finally:
                nemo_relay.scope.pop(child, output={"ok": True})
            assert nemo_relay.capture_traceparent().split("-")[2] == first[2]
        finally:
            nemo_relay.scope.pop(parent, output={"probe": "passed"})
    return ["nemo_relay native import", "static plugin configuration validation",
            "native scope push/pop", "nested trace propagation"]



def exercise(group: str, out: Path) -> None:
    assert_native()
    checks = {"uvloop": exercise_uvloop, "matrix": exercise_matrix, "nemo": exercise_nemo}[group]()
    result = {
        "status": "passed", "group": group, "checks": checks,
        "python": sys.version, "platform": sys.platform, "machine": platform.machine(),
        "installed": sorted(
            ({"name": d.metadata["Name"], "version": d.version}
             for d in importlib.metadata.distributions()), key=lambda d: d["name"].lower(),
        ),
    }
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def inspect_native_linkage(environment: Path, payload: Path) -> dict:
    """Account for each extension dependency before claiming payload compatibility."""
    platform_libraries = {"libc.so", "libm.so", "libdl.so", "liblog.so", "libandroid.so", "libz.so"}
    payload_libraries = defaultdict(list)
    for root in (payload / "tools", payload / "runtime-libs"):
        for path in root.rglob("*.so*"):
            if path.is_file():
                payload_libraries[path.name].append(str(path.relative_to(payload)))
    native = [p for p in environment.rglob("*.so*") if p.is_file() and p.read_bytes()[:4] == b"\x7fELF"]
    local_libraries = {p.name for p in native}
    entries, undeclared = [], set()
    for path in sorted(native):
        needed = subprocess.check_output(["patchelf", "--print-needed", str(path)], text=True).splitlines()
        rpath = subprocess.check_output(["patchelf", "--print-rpath", str(path)], text=True).strip()
        dependencies = {}
        for name in needed:
            if name in payload_libraries:
                dependencies[name] = {"kind": "original-payload", "paths": payload_libraries[name]}
            elif name in local_libraries:
                dependencies[name] = {"kind": "candidate-wheel"}
            elif name in platform_libraries:
                dependencies[name] = {"kind": "android-system-abi"}
            else:
                undeclared.add(name)
                dependencies[name] = {"kind": "undeclared-runtime-dependency"}
        entries.append({"extension": str(path.relative_to(environment)), "needed": dependencies, "rpath": rpath})
    return {"extensions": entries, "undeclared_runtime_libraries": sorted(undeclared),
            "declared_added_runtime_libraries": []}


def build(source: Path, out: Path, group: str) -> None:
    assert_native()
    from packaging.markers import default_environment
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    import pm
    from scripts.termux import build_wheels as builder
    from scripts.termux.python_linkage import repair_wheel

    source, out = source.resolve(), out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lock_path = source / "uv.lock"
    lock_sha = source_sha(lock_path)
    pm.check_project_lock(source, python=Path(sys.executable), explicit=True)
    if source_sha(lock_path) != lock_sha:
        raise RuntimeError("Frozen lock check changed the source lock")
    graph = locked_closure(tomllib.loads(lock_path.read_text()), group, default_environment())
    requirements = out / "requirements.txt"
    requirements.write_text("".join(f"{n}=={p['version']}\n" for n, p in graph.items()), encoding="utf-8")
    resolved = out / "resolved.txt"
    resolved.write_text("".join(f"{n}\t=={p['version']}\t\t\n" for n, p in graph.items()), encoding="utf-8")
    compatible = set(sys_tags())
    build_set = []
    for name, package in graph.items():
        if not package.get("source", {}).get("registry"):
            raise ValueError(f"Probe currently requires a locked registry source: {name}")
        wheel_covered = any(
            bool(parse_wheel_filename(w["url"].rsplit("/", 1)[1])[3] & compatible)
            for w in package.get("wheels", [])
        )
        if not wheel_covered:
            build_set.append(name)
    (out / "build-set.txt").write_text("\n".join(build_set) + "\n", encoding="utf-8")
    wheelhouse = out / "wheelhouse"
    wheelhouse.mkdir(exist_ok=False)
    builder.build_wheels(build_set, {n: f"=={p['version']}" for n, p in graph.items()}, wheelhouse)
    builder.fetch_pure_wheels(build_set, {}, wheelhouse, resolved)
    builder.retag_all(wheelhouse, source / "scripts/termux/retag_wheel.py", "android_24_arm64_v8a")
    library = Path(sys.base_prefix) / "lib" / sysconfig.get_config_var("LDLIBRARY")
    if not library.is_file():
        raise RuntimeError(f"Bundled libpython unavailable: {library}")
    for wheel in sorted(wheelhouse.glob("*.whl")):
        repair_wheel(wheel, library)
    python = pm.build_requirements_environment(
        requirements.read_text().splitlines(), out=out / "environment",
        python=Path(sys.executable), wheelhouse=wheelhouse, offline=True, explicit=True,
    )
    subprocess.run([str(python), str(source / "scripts/termux/build_wheels.py"),
                    "--import-modules", *build_set], check=True)
    subprocess.run([str(python), str(Path(__file__).resolve()), "exercise", "--group", group,
                    "--out", str(out / "RUNTIME-PROBE.json")], check=True)
    evidence = {
        "schema_version": 1, "group": group, "status": "passed", "lock_sha256": lock_sha,
        "pyproject_sha256": source_sha(source / "pyproject.toml"),
        "packages": {n: p["version"] for n, p in graph.items()}, "native_builds": build_set,
        "wheels": [{"name": p.name, "sha256": source_sha(p), "size": p.stat().st_size}
                   for p in sorted(wheelhouse.glob("*.whl"))],
    }
    linkage = inspect_native_linkage(out / "environment", Path(os.environ["HERMES_PROBE_PAYLOAD"]))
    (out / "NATIVE-LINKAGE.json").write_text(json.dumps(linkage, indent=2) + "\n", encoding="utf-8")
    original = subprocess.run(
        [str(python), str(Path(__file__).resolve()), "exercise", "--group", group,
         "--out", str(out / "ORIGINAL-RUNTIME-PROBE.json")],
        env={**os.environ, "LD_LIBRARY_PATH": os.environ["HERMES_PROBE_ORIGINAL_LD_LIBRARY_PATH"]},
        check=False,
    )
    evidence["original_payload_runtime_passed"] = original.returncode == 0
    evidence["undeclared_runtime_libraries"] = linkage["undeclared_runtime_libraries"]
    evidence["qualification"] = "candidate-built; complete package and device validation remain required"
    evidence["status"] = "passed" if original.returncode == 0 and not linkage["undeclared_runtime_libraries"] else "failed"
    (out / "BUILD-PROBE.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if evidence["status"] != "passed":
        raise RuntimeError("Native build requires runtime inputs absent from the original payload; inspect BUILD-PROBE.json and NATIVE-LINKAGE.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("build", "exercise"))
    parser.add_argument("--group", required=True, choices=tuple(ANCHORS))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.phase == "exercise":
        exercise(args.group, args.out)
    else:
        if args.source is None:
            parser.error("--source is required for build")
        sys.path.insert(0, str(args.source.resolve()))
        build(args.source, args.out, args.group)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
