# Preparing a native CUA package candidate

This preparation creates a distinct, unpublished Debian package from the exact
e271 Hermes candidate. The new package retains Debian version 0.22.2-1 and the
original Python dependency selection. It adds the reviewed Hermes CUA source
changes, the verified native CUA driver, its PM descriptor, and the driver's
declared APT library dependencies. It does not publish, install, or certify the
result.

The original input is the successful candidate from run
[39048514731](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39048514731),
head e271e922a2e71fd18591c45e9b98b8c7f9fffe02, artifact 12107225801.
Its Debian SHA-256 is
1e4e58fe17a1800f23ababcb2724e92b8904829eae3284569db52dbc672ca76a.
The input artifact and installed original package remain unchanged.

## Required inputs

Run the augmenter in the disposable native Termux container, using that original
candidate's interpreter at its real installation prefix. The four-file verified
fetch output must contain the original .deb, candidate-receipt.json, raw
CANDIDATE-IDENTITY.json, and raw venv-selection.json.

Other inputs are:

- The exact 67,709-byte experimental cua-hermes-integration.patch, SHA-256
  8bbfddbbacfd508db35de6158e4c1a2c06423b84cd5f4ed621d4955fcd529edd.
  Its 19 declared source paths are pinned individually in the augmenter.
- The driver just built and tested by the native CUA harness, and its exact SHA.
  The augmenter reads its actual ELF header and dynamic library table.
- CUA-SOURCE-RECEIPT.json with SHA-256
  47c43e002a868f0387e02142a9c623e5790c2656076959688abc3e93a6ec6167.
- A separate canonical build-source directory containing
  scripts/build/agent.py, inputs.py, launchers.py, and launcher_wrapper.py.
  Each file is SHA-bound. Actual byte comparisons in both the preserved main
  source and isolated CUA source confirm that all four match upstream commit
  d923a5eb487a17c0a68801bba9ef0f56c81040a8. The candidate intentionally trims its
  build scripts, so these four files must be supplied separately.
- The actual packaging checkout HEAD and a new output directory.

The full source reference trees f49c77b666cef7fd5235cdd786556908527b532e and
bf1356eda991ea38dcb3c5866d0d97be3d7eb3e6 describe replay of the experimental patch.
The current patch includes a follow-up limited to four display/status strings in
hermes_cli/tools_config.py and tools/computer_use/permissions.py. It identifies
both sealed and explicit external drivers correctly and uses a neutral
cua-driver provider label; source and packaging
mechanics are unchanged. The earlier native explicit-driver receipt retains
its original patch identity.

The augmented app comes from the candidate's trimmed app plus that patch. Its
tree is not asserted to equal either full reference tree.

## Native invocation

The caller supplies the original candidate's normal loader environment. The
following are harness paths, not device installation instructions:

~~~bash
"$PREFIX/lib/hermes-agent/venv/bin/python" -I -B \
  /source/scripts/prepare_cua_hermes_candidate.py \
  --candidate-dir /candidate \
  --patch /source/patches/next-stable/cua-hermes-integration.patch \
  --assembly-source /hermes-build-inputs \
  --driver "$OUT/bin/cua-driver" \
  --driver-sha256 "$verified_driver_sha256" \
  --source-receipt "$OUT/CUA-SOURCE-RECEIPT.json" \
  --packaging-commit "$CUA_PROBE_HEAD_SHA" \
  --out "$OUT/prepared-cua-candidate"
~~~

The script uses dpkg-deb, git, and du. It requires actual native AArch64 CPython
3.14.6 from the installed original payload. It rejects output paths that overlap
an input or the installed package. Neither an installer nor a resolver is run.

## Dependency and source identity

The application environment stamp hashes the frozen UV lock, selected extras,
locked Python artifact and target, plugin-member selection, and bundled-wheel
catalog SHA. It does not hash application or PM source code. PM's dependency
runtime identity hashes pm/pyproject.toml, pm/uv.lock, and the final interpreter
path.

These inputs are unchanged by the experimental CUA patch. The native worker
recomputes the application stamp with the staged PM and requires it to equal
the original native receipt. It also recomputes both PM runtime input identities
at the final interpreter path and requires equality. A change causes preparation
to fail with a rebuild requirement; the script never invents a replacement stamp.

Canonical AgentInputs/assemble regenerates the payload layout and launchers.
The bundled-wheel catalog is regenerated from the original wheel bytes and
original locks and must reproduce the original descriptor exactly. The complete
original venv, PM runtime, wheelhouse, runtime libraries, existing tools, and
tools/facts.json are checked byte for byte, including link targets and modes.
The original built frontend products and application metadata must remain
unchanged as well.

A fresh worker is started through the original installed canonical PM runtime
with bootstrap disabled. It imports the staged app's own PM, not the reference
build tree's PM. It calls stage_source_built_tool only after canonical assembly.
The source-built driver is separate from remote-download facts and contains its
exact source receipt and binary SHA. Passive PM selection is checked against
that sealed entry without any driver/runtime/install-root authority override.

## Runtime library contract

The actual ELF from successful native run
[39056267366](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39056267366)
uses /system/bin/linker64 and declares exactly:

| ELF library | Provider |
| --- | --- |
| libX11.so | Termux main libx11 |
| libXi.so | Termux main libxi |
| libc.so, libdl.so, libm.so | Android/Bionic platform |

The current official termux-main index places both libx11 and libxi in main;
x11-repo is not needed to resolve these two dependencies. The augmenter reads
the actual input driver's ELF table again and refuses unknown dependencies or a
different loader/search path. The new control file declares
Depends: libx11, libxi, with empty Pre-Depends. APT remains responsible for their
transitive closure. All other control fields are preserved, except the
recomputed Installed-Size.

The private Bot Desktop still requires the product's normal desktop packages.
Declaring the ELF library closure does not certify a working desktop or grant
access to an Android phone's UI.

## Output and subsequent validation

The new output directory contains three sibling files:

| File | Meaning |
| --- | --- |
| hermes-agent_0.22.2-1_aarch64-cua-candidate.deb | Distinct same-version candidate |
| prepared-cua-receipt.json | Exact input, source, driver, control and dependency identities |
| CUA-PREPARED-PAYLOAD.json | Complete no-follow payload inventory |

Before publication of that local output directory, the new .deb is extracted
again and its complete payload and control files must equal the prepared tree.
The original input files and original installed payload are checked again.

The receipt has status prepared-candidate, published=false, and
version_bumped=false. It explicitly leaves both native default CUA integration
and installed package/reinstall/optional-PM lifecycle required-pending.

The next authorized native stage must install this new package, run Hermes
from its own payload/app/pm, find the resident driver without external overrides,
exercise the registered computer_use handler with omitted delivery mode,
verify ordinary foreground approvals and viewer leases against the owned X11
fixture, and check cleanup. A separate clean lifecycle stage must satisfy the
declared runtime libraries through signed APT without a compiler installation,
then verify upgrade/reinstall and the ordinary optional SDK path.

Physical phone UI, microphone/VAD, AT-SPI content, background input, and
history/preview are outside this package experiment.

## Host validation

The focused packaging test file is tests/test_prepare_cua_hermes_candidate.py.
It tests source-path and byte boundaries, preserved dependency files, output
isolation, control-field preservation, exact ELF loader/library policy,
duplicate metadata, and no-follow inventories. The ordinary host interpreter
is rejected by the native preparation entry point. These checks do not stand
in for native package construction or runtime validation.

Exact preparation identities and captured host results are recorded in
[audit/cua-candidate-augmentation-preparation-20261017.json](../audit/cua-candidate-augmentation-preparation-20261017.json).
