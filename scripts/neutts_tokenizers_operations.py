#!/usr/bin/env python3
"""Actual local Tokenizers and selected Hub/fsspec operations; no model downloads."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import threading

BODY = b'{"fixture":"termux-tokenizers","values":[1,2,3]}\n'
WORDPIECE_TEXT = "HELLO unaffable caf\u00e9!"
WORDPIECE_IDS = [1, 3, 5, 6, 7, 8, 9, 2]
WORDPIECE_OFFSETS = [(0, 0), (0, 5), (6, 8), (8, 11), (11, 15), (16, 20), (20, 21), (0, 0)]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def origin(module):
    path = Path(module.__file__).resolve()
    site = Path(sys.prefix) / "lib/python3.14/site-packages"
    require(path.is_relative_to(site), "Actual module escaped the isolated installed environment")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def tokenizer_operations(work):
    import tokenizers
    import tokenizers.tokenizers as native
    from tokenizers import Tokenizer, decoders, models, normalizers, pre_tokenizers, processors, trainers

    vocabulary = {"[UNK]": 0, "[CLS]": 1, "[SEP]": 2, "hello": 3, "world": 4,
                  "un": 5, "##aff": 6, "##able": 7, "cafe": 8, "!": 9}
    tokenizer = Tokenizer(models.WordPiece(vocab=vocabulary, unk_token="[UNK]"))
    tokenizer.add_special_tokens(["[UNK]", "[CLS]", "[SEP]"])
    tokenizer.normalizer = normalizers.Sequence(
        [normalizers.NFD(), normalizers.Lowercase(), normalizers.StripAccents()])
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.decoder = decoders.WordPiece(prefix="##")
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    encoded = tokenizer.encode(WORDPIECE_TEXT)
    require(encoded.ids == WORDPIECE_IDS, "WordPiece literal token IDs differ")
    require(encoded.offsets == WORDPIECE_OFFSETS, "Unicode/source offsets differ")
    require(encoded.tokens == ["[CLS]", "hello", "un", "##aff", "##able", "cafe", "!", "[SEP]"],
            "WordPiece literal tokens differ")
    require(tokenizer.decode(encoded.ids) == "hello unaffable cafe!",
            "WordPiece decoder cleanup or subword merge differs")
    pair = tokenizer.encode("hello", "world")
    require(pair.ids == [1, 3, 2, 4, 2] and pair.type_ids == [0, 0, 0, 1, 1],
            "Pair template or segment IDs differ")
    require(pair.special_tokens_mask == [1, 0, 1, 0, 1] and pair.attention_mask == [1] * 5,
            "Pair attention/special-token masks differ")
    require(tokenizer.encode("unknown").ids == [1, 0, 2], "Unknown-token behavior differs")

    saved = work / "wordpiece.json"
    tokenizer.save(str(saved))
    serialized = tokenizer.to_str()
    for restored in (Tokenizer.from_file(str(saved)), Tokenizer.from_str(serialized)):
        check = restored.encode(WORDPIECE_TEXT)
        require(check.ids == WORDPIECE_IDS and check.offsets == WORDPIECE_OFFSETS,
                "Native tokenizer serialization changed the literal result")
    rows = tokenizer.encode_batch([WORDPIECE_TEXT] * 64)
    require(len(rows) == 64 and all(row.ids == WORDPIECE_IDS for row in rows),
            "Native batched WordPiece encoding differs")
    try:
        Tokenizer.from_str('{"broken":')
    except Exception:
        pass
    else:
        raise RuntimeError("Tokenizer accepted truncated JSON")

    training = ["hermes termux hermes termux", "caf\u00e9 and tea", "hello \u4e16\u754c",
                "spaces  and\ttabs", "line one\nline two"]
    byte_bpe = Tokenizer(models.BPE(unk_token="[UNK]"))
    byte_bpe.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    byte_bpe.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=280, min_frequency=2, show_progress=False,
                                  special_tokens=["[UNK]"],
                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet())
    byte_bpe.train_from_iterator(training * 4, trainer=trainer, length=len(training) * 4)
    require(257 < byte_bpe.get_vocab_size() <= 280, "BPE trainer did not perform bounded merges")
    for text in training + ["unseen \U0001f642 \u03a9"]:
        require(byte_bpe.decode(byte_bpe.encode(text).ids) == text,
                "Byte-level native BPE failed a Unicode/whitespace round trip")
    encoded_batch = byte_bpe.encode_batch(training * 16)
    require(len(encoded_batch) == 80
            and [byte_bpe.decode(row.ids) for row in encoded_batch] == training * 16,
            "Native batched BPE encoding differs")
    return {"status": "passed", "version": importlib.metadata.version("tokenizers"),
            "python_origin": origin(tokenizers), "native_origin": origin(native),
            "wordpiece": {"input": WORDPIECE_TEXT, "expected_ids": WORDPIECE_IDS,
                          "actual_ids": encoded.ids, "actual_offsets": encoded.offsets,
                          "pair_ids": pair.ids, "pair_type_ids": pair.type_ids,
                          "batch_count": len(rows), "serialized_sha256": hashlib.sha256(saved.read_bytes()).hexdigest()},
            "byte_bpe": {"training_rows": len(training) * 4, "vocab_size": byte_bpe.get_vocab_size(),
                         "batch_count": len(encoded_batch), "unicode_round_trips": len(training) + 1},
            "model_downloaded": False}


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def respond(self, body):
        require(self.client_address[0] == "127.0.0.1", "Non-loopback HTTP client")
        self.server.requests.append({"method": self.command, "path": self.path})
        if self.path != "/fixture.json":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(BODY)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(BODY)

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def log_message(self, *args):
        pass


@contextmanager
def fixture_server():
    server = FixtureServer(("127.0.0.1", 0), FixtureHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, name="tokenizers-loopback", daemon=True)
    thread.start()
    try:
        yield server, "http://127.0.0.1:" + str(server.server_port) + "/fixture.json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        require(not thread.is_alive(), "Owned loopback server did not stop")


def dependency_operations(work):
    import aiohttp
    import fsspec
    from fsspec.asyn import sync
    import httpx
    import huggingface_hub
    import yaml
    import yaml._yaml
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    require(yaml.__with_libyaml__, "The original native PyYAML extension is unavailable")
    value = yaml.load("fixture: [1, 2, 3]\n", Loader=yaml.CSafeLoader)
    require(value == {"fixture": [1, 2, 3]}
            and yaml.load(yaml.dump(value, Dumper=yaml.CSafeDumper), Loader=yaml.CSafeLoader) == value,
            "Actual LibYAML load/dump failed")
    with fixture_server() as (server, url):
        filesystem = fsspec.filesystem("http", skip_instance_cache=True,
                                      client_kwargs={"trust_env": False, "timeout": aiohttp.ClientTimeout(total=10)})
        try:
            require(filesystem.cat_file(url) == BODY, "fsspec[http]/aiohttp local body differs")
            require(filesystem.info(url)["size"] == len(BODY), "fsspec HTTP size differs")
            with httpx.Client(trust_env=False, timeout=5) as client:
                response = client.get(url)
                require(response.status_code == 200 and response.content == BODY,
                        "Actual HTTPX/HTTPCore local body differs")
        finally:
            if filesystem._session is not None:
                sync(filesystem.loop, filesystem._session.close, timeout=10)
        requests = list(server.requests)
        require(len(requests) >= 3 and all(row["path"] == "/fixture.json" for row in requests)
                and {row["method"] for row in requests} <= {"GET", "HEAD"},
                "Unexpected loopback dependency requests")
    cache = work / "empty-hub-cache"
    cache.mkdir(mode=0o700)
    try:
        hf_hub_download("termux-hermes/offline-fixture", "tokenizer.json",
                        cache_dir=str(cache), local_files_only=True)
    except LocalEntryNotFoundError as exc:
        missing = type(exc).__name__
    else:
        raise RuntimeError("An empty local-only Hub cache unexpectedly resolved a model")
    require(not list(cache.rglob("*")), "Local-only cache miss created unreviewed files")
    return {"status": "passed", "pyyaml": {"version": importlib.metadata.version("pyyaml"),
                                          "native_origin": origin(yaml._yaml), "actual_c_api": True},
            "http": {"body_sha256": hashlib.sha256(BODY).hexdigest(),
                     "requests": requests, "loopback_only": True,
                     "aiohttp_origin": origin(aiohttp), "fsspec_origin": origin(fsspec),
                     "httpx_origin": origin(httpx)},
            "hub": {"version": importlib.metadata.version("huggingface-hub"),
                    "origin": origin(huggingface_hub), "local_only_cache_miss": missing},
            "gated_weights_requested": False, "model_downloaded": False}
