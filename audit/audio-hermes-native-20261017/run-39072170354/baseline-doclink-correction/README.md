# Audio preparation: inherited FFmpeg documentation link

## Finding and correction

Native run 39072170354 reached the final payload link check after both canonical
Python environments, the 100 + 2 wheel catalog union, generated-bytecode
normalization, and the strict original-payload preservation oracle had passed.
Its failure was the unchanged FFmpeg copyright symlink:

- Path: `tools/ffmpeg/data/data/com.termux/files/usr/share/doc/ffmpeg/copyright`
- Target text: `../../LICENSES/GPL-3.0.txt`
- Missing contained destination: `tools/ffmpeg/data/data/com.termux/files/usr/share/LICENSES/GPL-3.0.txt`

The original and post-build inventories contain exactly the same link row,
including POSIX mode 0777. The correct GPL text is already present in both at
`runtime-libs/share/LICENSES/GPL-3.0.txt`, 35,149 bytes, SHA-256
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.

The old checker combined target existence and containment into one error. The
correction keeps the normal link policy strict and records this one inherited,
unresolved documentation link separately. It preserves the original tool files,
facts, symlink target text, modes, and existing license bytes.

Recognition requires the exact complete original payload inventory SHA-256
`dade6143af33f29c3d219578e68683269c1664f036e556f8399ff8a225be48b6`,
the identical current/original link row, the exact path and target text, an
unchanged missing lexical destination without a redirected parent, and the
original license row plus an independent check of its actual bytes. The original
inventory is captured immediately after extraction of the already verified,
pinned e271 candidate .deb.

Working links remain relative, resolvable and contained. Missing executables,
missing libraries, other missing documentation links, absolute links, escapes
and cycles fail. The inherited copyright link is excluded from `contained_links`
and appears under `baseline_missing_documentation_links` with
`working: false` and `status: preexisting-missing-documentation-target`.
The preparer saves the complete distinction in `evidence/payload-links.json`
and includes the separate issue record in its main preparation receipt.

The existing `allowed_changes` oracle is byte-for-byte/AST unchanged.
Adding the absent license destination, retargeting the tool symlink, or replacing
it with a regular file still fails that oracle. No package repair was made.

## Exact native evidence

The input archive was read from the sibling original-run directory without
modification:

- `termux-audio-environment-proof.zip`: 16,680,109 bytes; SHA-256
  `a44a317a8d55a623eab9e8d0f051e0e5f1de83f23c6523d145395764686a911f`
- All 76 unique ZIP members were independently read, CRC checked, sized and
  SHA-256 recorded in `input-provenance.json`.
- The original inventory has 32,504 entries; the post-build inventory has 39,037.
- The post-build inventory has 77 relative symlinks. Metadata resolution finds
  76 present destinations and the one missing documentation destination above.
- Seventy-six symlink rows are identical before and after the canonical rebuild.
  The existing canonical rebuild already changes original `venv/bin/python`
  from its absolute installed-package path to a contained relative target.
  The audit records this explicitly. For original-inventory metadata lookup
  only, that original absolute installed path is rebased to its package member;
  the corrected preparer never accepts absolute prepared links.
- The unchanged original-payload oracle replay passes with the same 6,750
  reviewed preparation changes before and after the checker correction.

The GPL text used for the host regression was read as a single bounded member
from the already verified CUA candidate .deb cache, with the entire .deb SHA-256
checked first. Its bytes also match the original native inventory's exact pin.
No executable was run from that package.

## Validation and limits

The complete existing test file passed **118 tests, zero failures and zero
skips** on the Windows Devbox Python 3.14.2 interpreter with the same actual
canonical PM source fixture used by prior audio reviews.

All 90 existing test cases are preserved. The 28 added cases exercise recognition
and truthful reporting, full source-inventory binding, absent verification
input, changed symlink text/mode, missing or altered license bytes/mode, a
symlink substituted for the license, stale inventory versus actual file bytes,
missing runtime and unrelated documentation targets, absolute and relative
escapes, an escaping ancestor, a loop, an internally redirected destination,
and attempted payload repairs.

The first run passed the 90 existing and 27 new cases. The new internal-parent
redirection negative exposed a Windows resolution detail; the correction now
checks the lexical destination's own resolved path as well. The second full
run passed all 118. Both raw runs are retained.

`replay_baseline_doclink.py` independently verifies the real native input
pins, replays the actual saved inventories and unchanged preservation oracle,
then executes the actual old and corrected checker functions on a small
host filesystem fixture containing the exact pinned GPL bytes. The old checker
reproduces the known failure and the corrected checker preserves every fixture
entry while identifying the missing link separately.

That host fixture substitutes only its own inventory hash to account for its
small size and Windows metadata. It is **not** a reconstructed native payload
and does not prove native POSIX mode semantics. The genuine native inventory
hash and link/license rows are checked separately against the production
constants. A native retry remains necessary to prove the corrected full
preparation path, subsequent audio initialization, and the runtime probe.

No microphone was accessed, no physical capture/VAD result was claimed, no
release was created, and no production admission was changed.

## Files frozen for parent review

Only these repository paths were edited:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `scripts/prepare_audio_hermes_environment.py` | 75,630 | `9c0186ac96cb897fee764a51995b0834586b7c953439092e6b184097753dad88` |
| `tests/test_audio_hermes_preparation.py` | 43,058 | `060a870039f6af702ce2e59b8399d01fb712effe4a8b5423104d1fb42f9bcc98` |

The original 32,970-byte test-file prefix is unchanged. Before/after source
copies, the exact patch, full test logs/XML, native inventory replay,
source/ZIP provenance, and this explanation are saved in this newly owned
evidence directory. No staging, commits, pushes, dispatches or frozen non-Rust
pipeline edits were performed.
