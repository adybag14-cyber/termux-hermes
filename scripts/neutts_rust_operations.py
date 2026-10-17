#!/usr/bin/env python3
"""Small real hf-xet and Safetensors operations plus local TLS identity gates.

The TLS client uses XetSession.new_file_download_group(token_refresh_url=...).
The exact upstream route eagerly fetches that URL through build_http_client.
All endpoint traffic is loopback; local:// CAS is used after the test token JSON.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import re
import ssl
import struct
import subprocess
import sys
import threading
import time
import traceback

PREFIX = Path("/data/data/com.termux/files/usr")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def module_origin(module, namespace):
    path = Path(module.__file__).resolve()
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(path.is_relative_to(site) and path.is_relative_to(site / namespace),
            "Native import origin escaped the exact isolated environment")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def hash_operation(work):
    import hf_xet
    import hf_xet.hf_xet as native
    raw = b"termux-hermes-native-hash-fixture\n" * 97
    path = work / "hash-input.bin"
    path.write_bytes(raw)
    first = hf_xet.hash_files([str(path)])
    again = hf_xet.hash_files([str(path)])
    require(len(first) == len(again) == 1 and first[0].hash == again[0].hash
            and re.fullmatch(r"[0-9a-f]{64}", first[0].hash)
            and first[0].file_size == len(raw), "HF Xet real file hashing failed")
    # Same byte count proves the content, rather than size alone, changes the hash.
    path.write_bytes(b"X" + raw[1:])
    changed = hf_xet.hash_files([str(path)])
    require(len(changed) == 1 and changed[0].file_size == len(raw)
            and changed[0].hash != first[0].hash, "HF Xet hash ignored a content change")
    return {"status": "passed", "version": importlib.metadata.version("hf-xet"),
            "origin": module_origin(native, "hf_xet"), "bytes": len(raw),
            "original_hash": first[0].hash, "changed_hash": changed[0].hash,
            "model_downloaded": False}


def safetensors_operation(work):
    import safetensors
    import safetensors._safetensors_rust as native
    values = (0.25, -1.5, 3.0, 42.0)
    raw = struct.pack("<4f", *values)
    tensors = {"fixture": {"dtype": "F32", "shape": [2, 2], "data": raw}}
    encoded = safetensors.serialize(tensors, metadata={"fixture": "termux-hermes"})
    decoded = dict(safetensors.deserialize(encoded))
    require(set(decoded) == {"fixture"} and decoded["fixture"]["dtype"] == "F32"
            and list(decoded["fixture"]["shape"]) == [2, 2]
            and bytes(decoded["fixture"]["data"]) == raw, "Safetensors native round-trip changed data")
    target = work / "fixture.safetensors"
    safetensors.serialize_file(tensors, str(target), metadata={"fixture": "termux-hermes"})
    file_decoded = dict(safetensors.deserialize(target.read_bytes()))
    require(bytes(file_decoded["fixture"]["data"]) == raw, "Safetensors native file serialization failed")
    rejected = []
    for label, invalid in (("truncated-header", b"\x10"), ("truncated-payload", encoded[:-1]),
                           ("invalid-header", struct.pack("<Q", 2) + b"{}" + raw)):
        try:
            safetensors.deserialize(invalid)
        except safetensors.SafetensorError as exc:
            rejected.append({"case": label, "error": str(exc)})
        else:
            raise RuntimeError("Safetensors accepted corrupt data: " + label)
    return {"status": "passed", "version": importlib.metadata.version("safetensors"),
            "origin": module_origin(native, "safetensors"), "dtype": "F32", "shape": [2, 2],
            "values": values, "serialized_sha256": hashlib.sha256(encoded).hexdigest(),
            "file_sha256": sha(target), "corrupt_inputs_rejected": rejected,
            "numpy_or_torch_dependency_not_requested": True}


class TokenServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, certificate, key, cas):
        self.requests = []
        self.tls_failures = []
        self.handshakes = 0
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(certificate, key)
        self.cas = cas
        super().__init__(("127.0.0.1", 0), TokenHandler)

    def get_request(self):
        plain, address = self.socket.accept()
        plain.settimeout(5)
        try:
            tls = self.context.wrap_socket(plain, server_side=True)
        except ssl.SSLError as exc:
            self.tls_failures.append({"reason": exc.reason, "error": str(exc)})
            plain.close()
            raise
        self.handshakes += 1
        return tls, address


class TokenHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requests.append({"method": "GET", "path": self.path})
        if self.path != "/token":
            self.send_error(404)
            return
        body = json.dumps({"accessToken": "local-test-only", "exp": int(time.time()) + 600,
                           "casUrl": "local://" + str(self.server.cas)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def verify_tls_outcome(case, result, server):
    require(result.get("stage") == "hf-xet-token-refresh"
            and result.get("expected_case") == case, "TLS child did not reach the exact public route")
    if case == "trusted":
        require(result.get("accepted") is True and server["handshakes"] >= 1
                and server["requests"] == [{"method": "GET", "path": "/token"}],
                "Trusted certificate did not complete the real HF token request")
    else:
        require(result.get("accepted") is False and result.get("exception_type")
                and not server["requests"] and server["handshakes"] == 0,
                "Invalid TLS identity reached HTTP or failed for a different stage")
        alerts = {"TLSV1_ALERT_UNKNOWN_CA", "SSLV3_ALERT_BAD_CERTIFICATE",
                  "TLSV1_ALERT_BAD_CERTIFICATE", "SSLV3_ALERT_CERTIFICATE_UNKNOWN",
                  "TLSV1_ALERT_CERTIFICATE_UNKNOWN"}
        require(server["tls_failures"] and any(r.get("reason") in alerts for r in server["tls_failures"]),
                "TLS rejection did not produce an actual certificate-related handshake alert")
    return True


def python_tls_control(url, certificate, expected_valid):
    import urllib.request
    context = ssl.create_default_context(cafile=str(certificate))
    require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED,
            "TLS fixture control disabled identity checks")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(url, timeout=8) as response:
            value = json.loads(response.read(4096))
            require(response.status == 200 and value["accessToken"] == "local-test-only",
                    "TLS fixture response differs")
    except Exception as exc:
        error = getattr(exc, "reason", exc)
        require(not expected_valid and isinstance(error, ssl.SSLCertVerificationError),
                "TLS fixture failed for something other than certificate validation")
        return {"accepted": False, "verify_code": error.verify_code,
                "verify_message": error.verify_message}
    require(expected_valid, "TLS fixture control accepted an invalid identity")
    return {"accepted": True, "check_hostname": True, "verify_mode": "CERT_REQUIRED"}


def issue_certificates(directory, evidence, run):
    directory.mkdir()
    evidence.mkdir()
    openssl = str(PREFIX / "bin/openssl")
    request_config = directory / "request.cnf"
    request_config.write_text("[req]\nprompt=no\ndistinguished_name=dn\n[dn]\nCN=Hermes-local-fixture\n")
    for label in ("trusted-ca", "untrusted-ca"):
        run([openssl, "req", "-config", str(request_config), "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "2",
             "-subj", "/CN=Hermes local fixture " + label,
             "-addext", "basicConstraints=critical,CA:TRUE",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign",
             "-keyout", str(directory / (label + ".key")), "-out", str(directory / (label + ".pem"))],
            "tls-generate-" + label, 30)
    records = []
    for index, (label, ca, ip) in enumerate((
        ("trusted", "trusted-ca", "127.0.0.1"),
        ("untrusted", "untrusted-ca", "127.0.0.1"),
        ("wrong-hostname", "trusted-ca", "127.0.0.2"),
    )):
        key, csr, cert = (directory / (label + suffix) for suffix in (".key", ".csr", ".pem"))
        ext = directory / (label + ".ext")
        ext.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                       "extendedKeyUsage=serverAuth\nsubjectAltName=IP:" + ip + "\n")
        run([openssl, "req", "-config", str(request_config), "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
             "-subj", "/CN=Hermes loopback fixture", "-keyout", str(key), "-out", str(csr)],
            "tls-request-" + label, 30)
        run([openssl, "x509", "-req", "-sha256", "-days", "2", "-set_serial", str(index + 10),
             "-in", str(csr), "-CA", str(directory / (ca + ".pem")),
             "-CAkey", str(directory / (ca + ".key")), "-extfile", str(ext), "-out", str(cert)],
            "tls-sign-" + label, 30)
        records.append({"case": label, "issuer": ca, "subject_alt_ip": ip, "sha256": sha(cert)})
    for path in directory.glob("*.pem"):
        (evidence / path.name).write_bytes(path.read_bytes())
    for path in directory.glob("*.key"):
        path.chmod(0o600)
    return records


@contextmanager
def serving_token(certificate, key, cas):
    server = TokenServer(certificate, key, cas)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    worker.start()
    try:
        yield server, "https://127.0.0.1:" + str(server.server_address[1]) + "/token"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)
        require(not worker.is_alive(), "Local TLS fixture server did not terminate")


def tls_operation(work, evidence, env, run):
    certs, cas = work / "tls-keys", work / "local-cas"
    cas.mkdir()
    certificates = issue_certificates(certs, evidence / "public-test-certificates", run)
    require(not any(k in env for k in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PYTHONHTTPSVERIFY")),
            "Unexpected alternate TLS override")
    results = []
    for case in ("trusted", "untrusted", "wrong-hostname"):
        cert, key = certs / (case + ".pem"), certs / (case + ".key")
        # Distinct listeners prevent a late alert from the independent Python
        # control from being misattributed to the real HF Xet client.
        with serving_token(cert, key, cas / (case + "-control")) as (control_server, control_url):
            control = python_tls_control(control_url, certs / "trusted-ca.pem", case == "trusted")
        with serving_token(cert, key, cas / case) as (server, url):
            result_path = evidence / ("hf-xet-tls-" + case + ".json")
            child_env = {**env, "SSL_CERT_FILE": str(certs / "trusted-ca.pem"),
                         "SSL_CERT_DIR": str(work / "empty-test-ca-directory")}
            Path(child_env["SSL_CERT_DIR"]).mkdir(exist_ok=True)
            command = [str(Path(sys.prefix) / "bin/python"), "-I", "-B", str(Path(__file__).resolve()),
                       "--tls-client", "--url", url, "--case", case, "--out", str(result_path)]
            command_record = run(command, "hf-xet-tls-" + case, 45, child_env)
            result = json.loads(result_path.read_bytes())
            snapshot = {"requests": list(server.requests), "handshakes": server.handshakes,
                        "tls_failures": list(server.tls_failures)}
            verify_tls_outcome(case, result, snapshot)
            results.append({"case": case, "status": "passed", "native_python_control": control,
                            "control_and_hf_listeners_separate": True,
                            "actual_hf_xet": result, "server": snapshot, "command": command_record,
                            "child_receipt_sha256": sha(result_path)})
    return {"status": "passed", "cases": results, "certificates": certificates,
            "public_api": "XetSession.new_file_download_group(token_refresh_url=...)",
            "upstream_route": "xet_pkg/xet_session/common.rs -> build_http_client -> DirectRefreshRouteTokenRefresher",
            "traffic": "loopback HTTPS token refresh, then local:// CAS with no file transfers",
            "production_ca_store_changed": False, "verification_disabled": False}


def tls_client(args):
    import hf_xet
    import hf_xet.hf_xet as native
    result = {"schema_version": 1, "stage": "hf-xet-token-refresh", "expected_case": args.case,
              "version": importlib.metadata.version("hf-xet"), "native_origin": module_origin(native, "hf_xet")}
    require(args.url.startswith("https://127.0.0.1:") and args.url.endswith("/token"),
            "TLS probe is restricted to its exact loopback URL")
    config = hf_xet.XetConfig().with_config("client.retry_max_attempts", 0)
    require(config.get("client.retry_max_attempts") == 0, "Bounded retry control was lost")
    session = hf_xet.XetSession(config=config)
    try:
        group = session.new_file_download_group(token_refresh_url=args.url)
        group.wait_to_finish()
        result["accepted"] = True
    except Exception as exc:
        result.update(accepted=False, exception_type=type(exc).__name__, error=str(exc))
    finally:
        session.sigint_abort()
    save(args.out, result)


def operations(work, evidence, env, run):
    require(sys.platform == "android" and sys.version_info[:3] == (3, 14, 6),
            "Real native CPython3.14.6 is required")
    work.mkdir()
    evidence.mkdir()
    return {"hf_xet": hash_operation(work),
            "safetensors": safetensors_operation(work),
            "hf_xet_tls": tls_operation(work, evidence, env, run),
            "tokenizers_full_runtime": "pending exact external PyYAML wheel and complete 25-node subset",
            "tiktoken_runtime": "pending separate native lock review",
            "models_downloaded": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls-client", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--case", choices=("trusted", "untrusted", "wrong-hostname"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    require(args.tls_client and args.case and args.url, "Only the bounded TLS child mode is a CLI")
    try:
        tls_client(args)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
