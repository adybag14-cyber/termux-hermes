# Public component preparation checkpoint — 2026-10-20

The published package remains unchanged. This checkpoint fixes HF-Xet's Android
ABI3 linkage and adds separate native preparation gates for the complete original
Tiktoken base runtime and the public Perth watermarking runtime.

The failing original HF artifact was downloaded in full and its whole SHA-256,
all 47,595 member CRCs/sizes/digests, original source pins and selected diagnostic
members were checked. The pinned Python 3.14.6 runtime exports the reported
_Py_FalseStruct symbol. Its ABI3 forwarding stub has no own selected exports,
and the failing HF extension omitted a DT_NEEDED entry for that stub.
The correction scopes --push-state,--no-as-needed, -lpython3,
--pop-state to HF's build environment. Original source archives, Cargo locks,
ABI3 tag, dependency declarations and native OpenSSL TLS selection remain fixed.

The new native gate requires the built HF extension to retain libpython3.so,
checks the exact original stub and real interpreter bytes, and requires both
to be present among the actual APT-owned mappings in a fresh runtime. Successful
host regressions do not substitute for that pending native operation result.

Related upstream linkage discussion:
- https://github.com/PyO3/pyo3/issues/6165#issuecomment-4906131258
- https://peps.python.org/pep-0738/#linkage

The separate Tiktoken gate preserves the reviewed Cargo lock and original
Setuptools backend. The separate Perth gate preserves its exact public bundled
checkpoint and uses only the narrowly reviewed resource-path correction.
Their native results were pending at this checkpoint. The original NeuTTS
Python bound remains unchanged and full speech synthesis remains unverified.

Previous commit b8f2415 passed 1,100 CI tests and 208 subtests with 84 skips.
This audit preserves the original API results and decoded job log. The focused
host suites overlap other tests and must not be added together as independent
coverage totals.
