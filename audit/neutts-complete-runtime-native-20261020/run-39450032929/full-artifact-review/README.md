# First complete NeuTTS dependency runtime: fully verified failure

This directory supplements the historical partial diagnosis in its parent. It verifies the entire artifact from run [39450032929](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39450032929), job 118722085474, at source commit `88e2810572a85f1050909ee8373527e983927766`. The native run failed. No complete dependency runtime pass is claimed.

## Exact failure boundary

The isolated child stopped during its first installed-file inventory:

```text
AttributeError: module '_complete_preparation' has no attribute 'safe_relative'
```

The trace leads from `runtime_case` through the unchanged shared `installed_inventory` and `installed_wheel_bytes` functions. The exact executed preparer did not expose the required adapter. The child retained stage `inputs`; its first inventory did not complete, runtime closure validation was not reached, and none of the eleven native operation groups ran. The outer receipt records stage `complete-native-runtime`, and the container exit code is 1.

This is an orchestration interface failure. The artifact does not establish a failure or success of any of the unexecuted complete-environment operations. The subsequent source correction and retry are separate evidence.

## What completed before the failure

The original receipts show all seven scientific foundation checks passed. Native APT authenticated the original signed index with insecure repository exceptions disabled. The 19 extra package requests matched the original versions; the install used the verified cache with `--no-download`. The before and after package inventories match only that exact plan. The already installed GMP library was verified without an additional install, and no compiler was installed.

The preparation lock describes 116 dependency distributions and 183 active edges, including the original selected `fsspec[http]` extra. The isolated installation manifest records 105 wheels and 11 copied APT Python payloads. This review independently binds every wheel archive and all 142 APT archives to their original pinned byte length and SHA-256, and compares the installation manifest with the original lock. The copied-payload receipts retain their original metadata and RECORD declarations. These are input and installation facts; they do not substitute for the inventory and runtime checks that the failed child never completed. Foundation support packages `pip` and `torchcodec` remain separately disclosed outside the 116-node graph.

The original raw `pip check` returned 1. Its eleven diagnostics concern the original Termux APT wheel-tag convention. The raw result is retained alongside the separate report of no missing or conflicting requirements. Neither metadata nor supported tags were rewritten.

The host disconnected the exact identified container before the isolated child began. Its inspection has no attached networks, and the child reported only loopback with no route. The recorded limits remain UID 1000, two CPUs, 6 GiB memory, and 512 PIDs.

## Complete artifact verification

| Evidence | Verified value |
|---|---|
| Artifact ID | 12278206483 |
| Whole archive bytes | 416,408,782 |
| Whole archive SHA-256 | `d39ff082c5ee1de4c0b2c9363e74db976927bff6afe8eee570d4805e44862b9e` |
| ZIP members | 760, each read to EOF and checked for CRC, byte length, and SHA-256 |
| Uncompressed member bytes | 443,613,837 |
| Recorded executed source inputs | 115, totaling 82,623,930 bytes |
| Source binding | Every recorded input matches its blob at exact commit `88e2810` |
| Native operation groups reached | 0 |

The archive reader also checked normalized safe paths, unique member names, original names, regular or directory types, encryption rejection, supported compression, and finite member and total size bounds. The whole archive remains outside the repository; the compressed full inventory and the original APIs, job log, source bindings, preparation records, setup results, installation manifest, and failure receipts are retained here.

`FULL-DOWNLOAD-VERIFIED.json` records the first full-integrity phase and truthfully leaves semantic review pending at that point. `NATIVE-FAILURE-REVIEW.json` is the later interpretation and binding result. `SELECTED-ORIGINAL-MEMBERS.json` identifies the 76 retained original artifact members.

The eight historical files in the parent directory were compared byte for byte with commit `11f7bb6` and left unchanged. The four members previously fetched by bounded ranges equal the corresponding members in the fully verified archive. Their earlier partial-verification claims remain an accurate historical record.

## Scope

The review executed no target code, new native operations, or new tests. The NeuTTS engine remains excluded with its original `>=3.10,<3.14` Python requirement. This audit does not certify speech synthesis, gated model access, device audio, production admission, or a release. No model, dependency metadata, version pin, admission flag, or release output was changed.
