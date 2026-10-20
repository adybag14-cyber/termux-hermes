# Second complete NeuTTS dependency runtime: fully verified failure

This directory retains the original evidence from run [39452440876](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39452440876), job 118730511837, at source commit `11f7bb6e069e3ee00b5d530997b7d91b690c1781`. The native run failed. This review is separate from the first failed run and claims no complete dependency runtime pass.

## Exact failure boundary

The child again stopped during its first installed-file inventory, this time with:

```text
ProbeError: Installed wheel file bytes changed
```

The trace reaches `compatibility_probe_neutts_nonrust.py`, line 402, in `installed_wheel_bytes`. That check requires installed contents to match either the original member or the permitted script-shebang rewrite. The complete preparer's previously missing `safe_relative` adapter is present in the exact executed source, so this is a distinct subsequent inventory failure.

The original generic diagnostic does not identify the first rejected installed member. Independently inspected original inputs do prove a concrete collision: both Einx 0.4.3 and Phonemizer 3.3.0 install `docs/source/conf.py`, with different bytes. Both originals cannot remain unchanged at the same installed path.

| Original wheel | Member bytes | Member SHA-256 |
|---|---:|---|
| `einx-0.4.3-py3-none-any.whl` | 1,635 | `386f1a451b02667af9c1b3337bbad94972c4031af9a1f757b7186a33e587dcd2` |
| `phonemizer-3.3.0-py3-none-any.whl` | 2,051 | `8ff1bfe77a14e0bec2e5d34e8fb3f92e155c12ee32778ff1d817e29936fdfce4` |

`ORIGINAL-CROSS-WHEEL-COLLISIONS.json` preserves the original scan of all 105 wheels, which found one shared target with different payloads. `ORIGINAL-INPUT-COLLISION-REVIEW.json` independently binds these two exact members, their CRCs, and their original RECORD rows to the fully verified retry artifact. The proven input collision is separate from the narrower native observation: the old generic stderr does not establish which member first triggered the rejection. This audit claims no correction or subsequent retry outcome.

The child retained stage `inputs`. Its first installed-file inventory did not finish, runtime closure validation was not reached, and none of the eleven native operation groups ran. The outer receipt records stage `complete-native-runtime`, and the container exit code is 1. No retry success is claimed.

## Completed setup and retained limits

All seven original scientific foundation checks passed. Native APT authenticated the original signed index with insecure repository exceptions disabled. The exact 19-package extra-install plan matched the original version pins and before/after package inventories; installation used the verified cache with `--no-download`. The existing GMP library was verified without another install, and no compiler was installed.

The original input graph remains 116 dependency distributions and 183 active edges, including the selected `fsspec[http]` extra. The installation manifest records 105 wheels and 11 copied APT Python payloads. This review independently compares those manifest records with the original lock and binds all 105 wheel archive bodies and all 142 APT archive bodies to the pinned byte lengths and SHA-256 values. These are input and installation facts. The native inventory and complete runtime checks remained incomplete.

The raw `pip check` exit code remains 1, with eleven original Termux APT wheel-tag diagnostics. The original report separately records no missing or conflicting requirements. Neither metadata nor supported tags were rewritten. Foundation support packages `pip` and `torchcodec` remain disclosed outside the dependency graph.

The host disconnected the exact recorded container before the isolated child ran. The original inspection has no attached networks, and the child reports only loopback with no route. The limits remain UID 1000, two CPUs, 6 GiB memory, and 512 PIDs.

## Complete verification

| Evidence | Verified value |
|---|---|
| Artifact ID | 12278513966 |
| Whole archive bytes | 416,408,851 |
| Whole archive SHA-256 | `0024d291eeb977de65bff4c39712ca6dee4f3ba31b10b4a725378fb89fc423e3` |
| ZIP members | 760; each CRC, actual size, and SHA-256 checked |
| Uncompressed member bytes | 443,614,091 |
| Recorded executed source inputs | 115, totaling 82,624,081 bytes |
| Source binding | Every recorded input matches exact commit `11f7bb6` |
| Native operation groups reached | 0 |

The archive reader also checked member-path normalization and safety, uniqueness, original names, regular or directory types, encryption rejection, supported compression, and finite member and total size bounds. The whole ZIP remains outside the repository. This directory retains its compact full inventory, original APIs and job log, source bindings, setup and installation evidence, failure receipts, and review procedures.

The original child result is 1,793 bytes, SHA-256 `99fbdf75ccbd788be106f49e9769478c2aecb422e886a1dbb91c5801599566ac`. The original stderr is 1,209 bytes, SHA-256 `93e3857e08a4719b4e58a059deb672ca7da3f63d08bf170209d7224135ce3af9`. Both match the earlier bounded diagnostic retrieval.

`FULL-DOWNLOAD-VERIFIED.json` records the integrity phase and truthfully leaves interpretation pending at that point. `NATIVE-FAILURE-REVIEW.json` records the subsequent bounded interpretation. `SELECTED-ORIGINAL-MEMBERS.json` identifies the retained original members.

All 91 files in the first run's frozen full-artifact audit were rechecked against manifest SHA-256 `7cae5c9f1b96e6b0099da474135202f3813a51020f62de70bf57ff5936197191` and remain unchanged. This retry audit does not overwrite earlier evidence.

## Scope

This review executed no target code, new native operations, or new tests. The NeuTTS engine remains excluded with its original `>=3.10,<3.14` Python requirement. Speech synthesis, gated model access, device audio, production admission, and release readiness are not certified. No dependency metadata, version pin, admission flag, source implementation, or release output was changed by this review.
