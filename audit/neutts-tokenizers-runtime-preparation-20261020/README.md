# Complete original Tokenizers runtime preparation

This retains the original 25-distribution, 29-edge Tokenizers/Hub/fsspec[http] subset and every selected wheel. The graph and interpreter requirements are unchanged. The isolated native gate checks the installed inventory before and after actual WordPiece/BPE, local HTTP, local-only Hub cache, native PyYAML, HF Xet hashing, and Safetensors serialization operations.

The three Rust wheels come from run 39440363583 at 4a95a07086a0b88d209485ac7a01cdd40e268f40. All three builds passed original-source, Cargo, backend, wheel RECORD and native ELF verification. The overall run failed in the old Safetensors test API, so this handoff does not certify their aggregate runtime. Its original receipts and the API correction are retained in audit/neutts-safetensors-api-fix-20261020.

The host preparation passed with all 25 actual wheels and both original LibYAML/GMP ownership archives. Only LibYAML is an additional APT install; GMP is provenance only. HOST-PREPARED-INPUTS.json is an input verification receipt, not a native runtime pass.

The new workflow is preparation-branch-only and read-only. It uses the pinned native ARM64 Android image and seven-case scientific foundation, installs the exact complete wheel set in a fresh isolated environment, then disconnects its owned container from external networks before local operations. It installs no compiler. Full NeuTTS, gated model access, physical microphone/VAD and release publication remain outside this gate.
