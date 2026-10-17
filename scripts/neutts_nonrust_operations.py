"""Real, bounded model-free operations for the six isolated native components.

These functions are called only after the native runner verifies the installed
distribution inventory, file bytes and real Android interpreter. Host tests
inspect their contracts; they do not replace native execution with import mocks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def audioop_operation(work):
    import audioop
    samples = struct.pack("<5h", 0, 1000, -1000, 32000, -32000)
    require(audioop.max(samples, 2) == 32000, "audioop PCM maximum differs")
    require(audioop.mul(samples, 2, 0.5) == struct.pack("<5h", 0, 500, -500, 16000, -16000),
            "audioop signed PCM scaling differs")
    raw = struct.pack("<16h", *range(0, 16000, 1000))
    complete, final = audioop.ratecv(raw, 2, 1, 16000, 8000, None)
    first, state = audioop.ratecv(raw[:16], 2, 1, 16000, 8000, None)
    second, streamed_final = audioop.ratecv(raw[16:], 2, 1, 16000, 8000, state)
    require(first + second == complete and streamed_final == final,
            "audioop streaming sample-rate state differs")
    return {"pcm_scaling": "passed", "sample_rate_conversion": "passed",
            "streaming_state": "passed", "input_frames": 16,
            "output_frames": len(complete) // 2}


def crypto_operation(work):
    from Cryptodome.Cipher import AES
    from Cryptodome.Hash import SHA256
    from Cryptodome.Math.Numbers import Integer
    from Cryptodome.Util import _raw_api
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
    cipher = AES.new(key, AES.MODE_ECB).encrypt(plaintext)
    require(cipher.hex() == "69c4e0d86a7b0430d8cdb78070b4c55a", "AES standard known-answer mismatch")
    nonce, message = b"\0" * 12, b"Termux native authenticated encryption"
    encrypted, tag = AES.new(key, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(message)
    decoded = AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(encrypted, tag)
    require(decoded == message, "AES-GCM round trip differs")
    rejected = False
    try:
        AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(
            encrypted, bytes([tag[0] ^ 1]) + tag[1:])
    except ValueError:
        rejected = True
    require(rejected, "AES-GCM accepted an invalid authentication tag")
    require(SHA256.new(b"abc").hexdigest()
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "SHA256 known-answer mismatch")
    require(int(Integer(17).inverse(3120)) == 2753, "Native integer modular arithmetic differs")
    return {"aes128_standard_vector": "passed", "aes_gcm_roundtrip": "passed",
            "invalid_tag_rejected": True, "sha256_standard_vector": "passed",
            "modular_inverse": "passed", "raw_loader_backend": getattr(_raw_api, "backend", None)}


def yaml_operation(work):
    import yaml
    import yaml._yaml
    require(yaml.__with_libyaml__ is True, "PyYAML silently omitted the LibYAML extension")
    require(yaml._yaml.get_version() == (0, 2, 5), "Unexpected linked LibYAML version")
    document = "language: café\nvalues: [1, 2, 3]\nactive: true\n"
    value = yaml.load(document, Loader=yaml.CSafeLoader)
    require(value == {"language": "café", "values": [1, 2, 3], "active": True},
            "LibYAML C loader returned unexpected values")
    dumped = yaml.dump(value, Dumper=yaml.CSafeDumper, allow_unicode=True)
    require(yaml.load(dumped, Loader=yaml.CSafeLoader) == value, "LibYAML C round trip differs")
    rejected = False
    try:
        yaml.load("[unfinished", Loader=yaml.CSafeLoader)
    except yaml.YAMLError:
        rejected = True
    require(rejected, "LibYAML C loader did not propagate malformed input")
    return {"libyaml_accelerator": True, "libyaml_version": [0, 2, 5],
            "unicode_structured_roundtrip": "passed", "malformed_input_rejected": True}


def pandas_operation(work):
    import numpy as np
    import pandas as pd
    frame = pd.DataFrame({"key": ["a", "b", "a"], "value": [1.0, 3.0, 2.0]})
    totals = frame.groupby("key")["value"].sum()
    require(totals.to_dict() == {"a": 3.0, "b": 3.0}, "Native pandas group reduction differs")
    require(np.array_equal(frame["value"].to_numpy(), np.array([1.0, 3.0, 2.0])),
            "pandas/NumPy native interchange differs")
    dates = pd.date_range("2024-02-28", periods=3, freq="D")
    require([x.strftime("%Y-%m-%d") for x in dates]
            == ["2024-02-28", "2024-02-29", "2024-03-01"], "Native datetime boundary differs")
    require(pd.Series(["café", "termux"]).str.len().tolist() == [4, 6],
            "pandas Unicode string operation differs")
    joined = frame.merge(pd.DataFrame({"key": ["a", "b"], "weight": [10, 20]}), on="key")
    require(joined["weight"].tolist() == [10, 20, 10], "Native pandas join differs")
    return {"group_reduction": "passed", "numpy_interchange": "passed",
            "leap_day_datetime": "passed", "unicode_strings": "passed", "join": "passed",
            "numpy_version": np.__version__, "pandas_version": pd.__version__}


def sklearn_operation(work):
    import cloudpickle
    import joblib
    import narwhals
    import numpy as np
    import scipy
    import sklearn
    import threadpoolctl
    from sklearn.cluster import KMeans
    from sklearn.linear_model import LinearRegression
    from sklearn.utils import _openmp_helpers

    require(_openmp_helpers._openmp_parallelism_enabled() is True,
            "scikit-learn was built without OpenMP")
    require(_openmp_helpers._openmp_effective_n_threads() == 2,
            "scikit-learn did not honor the two-thread OpenMP budget")
    points = np.tile(np.array([[0., 0.], [0., 1.], [1., 0.],
                               [10., 10.], [10., 11.], [11., 10.]]), (128, 1))
    model = KMeans(n_clusters=2, init=np.array([[0., 0.], [10., 10.]]),
                   n_init=1, random_state=0, algorithm="lloyd").fit(points)
    centers = model.cluster_centers_[np.argsort(model.cluster_centers_[:, 0])]
    require(np.allclose(centers, [[1 / 3, 1 / 3], [10 + 1 / 3, 10 + 1 / 3]],
                        rtol=0, atol=1e-11), "Native OpenMP KMeans centers differ")
    x = np.arange(8, dtype=np.float64).reshape(-1, 1)
    linear = LinearRegression().fit(x, 2 * x[:, 0] + 1)
    require(np.allclose(linear.predict([[8.], [9.]]), [17., 19.], rtol=0, atol=1e-12),
            "scikit-learn/SciPy linear solve differs")
    values = joblib.Parallel(n_jobs=2, prefer="threads")(
        joblib.delayed(pow)(i, 2) for i in range(6))
    require(values == [0, 1, 4, 9, 16, 25], "Joblib threaded operation differs")
    closure = cloudpickle.loads(cloudpickle.dumps(lambda value: value + 7))
    require(closure(4) == 11, "Declared Cloudpickle dependency failed closure serialization")
    return {"compiled_openmp": True, "effective_openmp_threads": 2,
            "kmeans_samples": len(points), "kmeans_centers": centers.tolist(),
            "scipy_linear_solve": "passed", "joblib_threads": "passed",
            "cloudpickle_closure": "passed", "threadpools": threadpoolctl.threadpool_info(),
            "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__,
                         "scipy": scipy.__version__, "joblib": joblib.__version__,
                         "narwhals": narwhals.__version__, "threadpoolctl": threadpoolctl.__version__}}


def sentencepiece_operation(work):
    import sentencepiece as spm
    work.mkdir(parents=True, exist_ok=True)
    corpus = work / "synthetic-corpus.txt"
    line = "hello world café ABC termux native sentence pieces test text.\n"
    corpus.write_text(line * 64 + "hello café world ABC.\n" * 64, encoding="utf-8")
    prefix = work / "synthetic-tokenizer"
    spm.SentencePieceTrainer.train(
        input=str(corpus), model_prefix=str(prefix), model_type="bpe",
        vocab_size=64, character_coverage=1.0, shuffle_input_sentence=False,
        input_sentence_size=0, num_threads=2, hard_vocab_limit=False)
    processor = spm.SentencePieceProcessor(model_file=str(prefix) + ".model")
    ids = processor.encode("hello world", out_type=int)
    require(ids and all(isinstance(x, int) and x >= 0 for x in ids), "Native tokenizer produced invalid IDs")
    require(processor.decode(ids) == "hello world", "Native tokenizer round trip differs")
    normalized = processor.decode(processor.encode("ＡＢＣ café", out_type=int))
    require(normalized == "ABC café", "Standard Unicode normalization differs")
    raw = Path(str(prefix) + ".model").read_bytes()
    restored = spm.SentencePieceProcessor(model_proto=raw)
    require(restored.encode("hello world", out_type=int) == ids, "Serialized tokenizer round trip differs")
    return {"trainer": "passed", "tokenizer_roundtrip": "passed",
            "standard_unicode_normalization": "passed", "serialized_model": "passed",
            "synthetic_tokenizer_created": True, "model_downloaded": False,
            "synthetic_model_bytes": len(raw), "synthetic_model_sha256": hashlib.sha256(raw).hexdigest(),
            "piece_count": processor.get_piece_size()}


OPERATIONS = {
    "audioop-lts": audioop_operation,
    "pycryptodomex": crypto_operation,
    "pyyaml": yaml_operation,
    "pandas": pandas_operation,
    "scikit-learn": sklearn_operation,
    "sentencepiece": sentencepiece_operation,
}


def run_operations(names, work):
    require(set(names) <= set(OPERATIONS), "Unreviewed native operation")
    results = []
    for name in names:
        result = OPERATIONS[name](work / name)
        results.append({"component": name, "status": "passed", "checks": result})
    return results
