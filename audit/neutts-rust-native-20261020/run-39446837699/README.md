# Successful original Rust native build and behavior evidence

Run [39446837699](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39446837699), job 118710892854, passed at source commit 73525752755f990926243396f34f5ba8e6148a03.

The original locked sources built Maturin, HF-Xet, Safetensors and Tokenizers on AArch64 Android CPython 3.14.6. The separate isolated two-distribution HF-Xet/Safetensors environment passed actual file hashing, TensorSpec serialization and rejection of corrupt input. Actual HF-Xet TLS token refresh accepted the trusted loopback identity and rejected an unknown CA and the wrong hostname before HTTP. Certificate verification and the production CA store were preserved. All 24 installed files were unchanged after execution.

REVIEW.json and the independent wheel/library review bind the original receipts to the exact source commit, verify every wheel RECORD payload and inspect the runtime shared-library ELF files, and compare loaded APT library bytes to their original archives. All 47,629 members of the complete 765,103,959-byte artifact were independently CRC/size/SHA-256 checked; all 53 small handoff members match the complete artifact byte for byte. The complete ZIP remains outside Git; its full member inventory is retained here. Original raw logs and diagnostics are preserved.

This run's Tokenizers result is a wheel build. The separately exercised 25-distribution runtime at 8995678 has its own exact wheel/input identities in audit/neutts-tokenizers-runtime-native-20261020/run-39447721557. No NeuTTS engine installation, model synthesis, physical microphone validation, version change or release is claimed.

The small handoff download-stage receipt was written before the complete archive was available. Its comparison field is the historical not-yet-compared state. The later FULL-DOWNLOAD-VERIFIED.json records the successful byte-for-byte comparison against the complete archive; the independent semantic review repeated that comparison for all 53 members. Both original download-stage receipts remain unchanged.
