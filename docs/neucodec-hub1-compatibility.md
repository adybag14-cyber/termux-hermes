# NeuCodec 0.0.4: compatibility with Hugging Face Hub 1.x

The isolated [source patch](../patches/next-stable/neucodec-hub1-download.patch)
repairs a concrete downloader API failure in the exact NeuCodec 0.0.4 source.
It is preparation for the next stable Hermes version. It does not change the
current package, the scientific foundation, engine dependency metadata, model
identities, numerical precision, or watermark behavior.

The [audit receipt](../audit/neucodec-hub1-20261017.json) binds the source archive,
patch, before/after tests, original metadata and replayed source files.

## Why the default engine needs this fix

NeuTTS 1.4.1 requires Transformers 5.1.0. That Transformers version requires
`huggingface-hub>=1.3.0,<2.0`. NeuCodec 0.0.4 still unconditionally passes
`proxies=` and `resume_download=` to `hf_hub_download` in its checkpoint and
metadata downloads. Hub 1.x has removed both parameters; even the default
`proxies=None` causes Python argument binding to fail before the checkpoint can
load.

The exact inspected contracts are Hub 0.27.1, 1.3.0, 1.24.0 and 1.31.0. Source
hashes and parameter names are retained in the audit. The
[official migration guide](https://github.com/huggingface/huggingface_hub/blob/v1.24.0/docs/source/en/concepts/migration.md)
explains the replacement: downloads resume automatically, and proxy
configuration belongs to the HTTP client or the `HTTP_PROXY` /
`HTTPS_PROXY` environment. Downgrading Hub below 1.0 would violate the pinned
Transformers requirement.

Primary requirement evidence:
[NeuTTS 1.4.1](https://pypi.org/pypi/neutts/1.4.1/json),
[Transformers 5.1.0](https://pypi.org/pypi/transformers/5.1.0/json),
[NeuCodec 0.0.4](https://pypi.org/pypi/neucodec/0.0.4/json).

## Resulting behavior

A small shared adapter inspects the callable's supported parameters. With a
legacy Hub function, it forwards the original proxy and resume arguments. With
Hub 1.x, it uses the documented automatic resume behavior and leaves the
supported request arguments unchanged.

A nonempty per-call proxy configuration cannot be silently discarded. The
patch rejects it with an actionable error explaining the supported global
environment or client-factory configuration. A shared public-entry preflight
performs that check before delegating to Hub's `from_pretrained`, which may
fetch `config.json` before calling NeuCodec's own loading hook. The private
hook also validates direct callers.

The same adapter covers the full NeuCodec and distilled-codec checkpoint
download, and the existing ONNX decoder download. It retains the upstream
`meta.yaml` request. It forwards the caller's token, immutable revision,
cache directory, offline setting and force-download setting without
substitution, preserves explicit `token=False`, and propagates the original
download error without retries or alternate hosts.

This shared fix does not make the ONNX decoder a reference encoder. The actual
Hermes default still requires the full NeuCodec model and Wav2Vec2-BERT reference
encoding.

## Verification and limits

The exact source input is
`neucodec-0.0.4.tar.gz`, SHA-256
`994c9367b691b96c30247ebe5f3d9b7088411ff640b8df2f0dd9e1efe39f6f42`.
All 20 archive members were recorded before editing. The source was staged as
an isolated baseline without committing it; the patch replays cleanly from
that index and the replayed files match the actual edited files.

The final canonical test file has 34 cases. The original source produces
20 failures and 14 passes. The patched source passes all 34. Tests execute
the actual two loading-method bodies and actual class inheritance layouts,
with strict old/new downloader signatures and recording model/client
fixtures. They verify argument identity, proxy preflight, original-error
propagation, no global environment changes, and the unchanged checkpoint
selection/filtering behavior. CPython 3.10 syntax validation, whitespace
validation, clean-baseline application and reverse application also pass.

These are host source regressions on Windows CPython 3.14.2. The fixtures do
not execute Torch, download any model, authenticate to Hugging Face or perform
native Bionic synthesis. Full synthesis additionally needs the separately
audited native engine closure and authorized access to the exact gated default
model repositories.
