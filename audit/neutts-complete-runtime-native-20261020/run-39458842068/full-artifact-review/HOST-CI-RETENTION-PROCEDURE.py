"""Retain bounded original host CI evidence alongside the independent native success audit."""
import hashlib,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]);base=pathlib.Path(sys.argv[2]);monitor=pathlib.Path(sys.argv[3])
dest=root/"audit/neutts-complete-runtime-native-20261020/run-39458842068/full-artifact-review"
head="2d4408fea01af1721e3caca612624002a20c4494"
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,data):
 p=dest/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==data
 else:p.write_bytes(data)
 return {"path":name,"bytes":len(data),"sha256":sha(data)}
runs=[]
for kind,run,stamp,job,seconds,event in [
 ("push",39458842084,"20261020T163638Z",118752672409,"19.65","push"),
 ("pull-request",39458856008,"20261020T163719Z",118752722094,"25.00","pull_request")]:
 directory=monitor/str(run)
 runbytes=(directory/("run-"+stamp+".json")).read_bytes()
 jobbytes=(directory/("jobs-"+stamp+".json")).read_bytes()
 logbytes=(directory/("JOB-"+str(job)+".log")).read_bytes()
 r=json.loads(runbytes);jobs=json.loads(jobbytes)
 assert r["id"]==run and r["head_sha"]==head and r["conclusion"]=="success" and r["run_attempt"]==1 and r["event"]==event
 assert r["path"]==".github/workflows/ci.yml"
 selected=[j for j in jobs["jobs"] if j["id"]==job]
 assert len(selected)==1 and selected[0]["head_sha"]==head and selected[0]["conclusion"]=="success"
 lines=[s for s in logbytes.decode().splitlines() if re.search(r"\b1271 passed, 84 skipped, 631 subtests passed in "+re.escape(seconds)+r"s\b",s)]
 assert len(lines)==1
 files=[save("host-ci/"+kind+"/"+name,data) for name,data in [
 ("ORIGINAL-RUN.json",runbytes),("ORIGINAL-JOBS.json",jobbytes),("ORIGINAL-JOB.log",logbytes)]]
 runs.append({"run_id":run,"job_id":job,"event":event,"api_head_sha":head,"conclusion":"success",
 "passed":1271,"skipped":84,"subtests_passed":631,"seconds":float(seconds),"original_summary_line":lines[0],
 "originals":files,"scope":"Original host CI evidence associated by GitHub APIs with this head; not a native whole-gate pass."})
receipt={"schema":"historical-host-ci-originals/v1","native_run_id":39458842068,"source_commit":head,
 "runs":runs,"new_tests_run_by_review":False,"release_output":False}
save("HOST-CI-REVIEW.json",(json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode())
save("HOST-CI-RETENTION-PROCEDURE.py",pathlib.Path(__file__).read_bytes())

readme="""# Complete dependency runtime: independently verified native success

[Run 39458842068](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39458842068), job 118752673393, passed at exact source @@2d4408fea01af1721e3caca612624002a20c4494@@. This audit independently verifies the complete artifact and the actual native results for the isolated **116-distribution / 183-edge dependency gate**.

The NeuTTS engine remains excluded. Its original Python requirement stays @@>=3.10,<3.14@@. No selected speech-model weights were loaded and no speech synthesis or physical-device/audio certification is claimed.

## Complete artifact and source verification

Artifact @@12281349229@@ is **416,333,967 bytes**, SHA-256 @@46d6181b7db063c8a80d39d81236576b8899a57185b2e8dc418c554f5886ca75@@. The complete archive was independently downloaded and hashed. All **763 members** passed path/type, size, CRC and SHA-256 checks, totaling **450,201,880 uncompressed bytes**. A compact inventory retains every member's identity; the full archive remains in the outside Devbox evidence workspace.

Every one of the **122 recorded source inputs**, totaling **90,298,687 bytes**, was re-read from the exact executed Git commit and matched its recorded digest. All **105 wheel archives** and **142 APT archives** match the executed lock and original package pins.

## Actual passed gates

Seven scientific-foundation cases passed. Native APT authenticated the original retained signed snapshot, and the exact plan installed or reinstalled 19 additional pinned packages. Before/after APT inventories match that plan; inherited GMP was verified without reinstalling it. No compiler was installed.

The isolated runtime contained exactly **116 visible distributions**, consisting of 105 wheels and 11 complete original APT Python payload copies. Before and after operations, the installed inventory verified the same **29,140 site files**, and wheel RECORD validation verified the same **13,818 rows** across 105 wheels. Original package metadata and APT RECORD files remained unchanged. Global site packages were hidden. Pip and Torchcodec are explicitly disclosed foundation support outside the graph.

All eleven operation groups completed, in executed source order:

| Group | Measured scope |
| --- | --- |
| Foundation and audio | Real Numba JIT, CFFI, MsgPack, LibYAML, scikit-learn, Audioop and Torchaudio operations. |
| Non-Rust | AES/SHA/GCM and invalid-tag controls; Pandas data operations; SentencePiece training and roundtrip on a synthetic local corpus. |
| HF-Xet | Actual native hashes of an original and modified local fixture. |
| Safetensors | TensorSpec serialization/file roundtrip with retained backing buffer and corrupt-input rejections. |
| Tokenizers | Real WordPiece literal vectors, offsets and batches; Byte-BPE training with Unicode roundtrips. |
| Hub, HTTP and YAML | Offline Hub cache-miss behavior, loopback-only HTTPX/AIOHTTP/FSSPEC requests and actual PyYAML C API. |
| Tiktoken | Native CoreBPE, six fixed local vectors, literal vocabulary, special-token controls and threaded batches. |
| Phonemizer | Actual stressed/unstressed eSpeak output, RPDS and XXHash, with bounded retention of original constructor-created libraries. |
| Llama CPU | CPU backend and default-context inspection only; no model loaded and no inference tested. |
| Perth public watermark | Safe CPU weights-only strict loading of the original public bundled checkpoint, actual public API on one-second mono float32 synthetic audio at 24/32 kHz, and in-memory WAV roundtrips. |
| Complete integration | Actual NeuCodec/Torchtune/TorchAO imports; Torch/NumPy, Datasets/Arrow/Parquet, Pillow, lxml and psutil operations; local Transformers configuration; exact original Torch helper identity, contiguous/transposed strides and optional symbolic realization. |

The final integration exercised the corrected TorchAO import boundary. Its two helpers came from the pinned original @@torch._inductor.kernel.flex.common@@ module; function identity and behavior were checked, with no replacement functions.

## Final native provenance and integrity

The final native map records **246 extension files**, **178 APT libraries**, **six pinned image files**, and **ten exact eSpeak asset copies** across 1,288 mapping rows. No rejected mapping category or deleted library remains in the original classification.

This independent review rehashed every mapped extension and APT library from the verified original wheel or APT archive, plus the original Torch provider source: **425 original members**. It streamed **55 original APT archives**, without extracting/installing or executing their contents. The reported extension/library hashes and ELF class/endianness/AArch64 identities match those bytes. The six image members match the exact pinned image-file manifest; their native ownership checks are retained separately, without claiming this review downloaded the image again. Every eSpeak copy matches the exact input asset.

Before/after installed inventories and RECORD results are identical. The exact container was disconnected from Docker networking before the native child, and the final network recheck again reported only loopback. The loopback HTTP fixture is preserved as part of the measured operation. Original limits were two CPUs, 6 GiB, 512 PIDs and UID 1000; these test limits are not a measured device-memory requirement.

Raw @@pip check@@ still exits 1 with exactly eleven original APT platform-tag diagnostics and no missing/conflicting declared requirements. These diagnostics are retained. Metadata and supported tags were not rewritten to produce a nominal pip pass.

## Scope and historical evidence

The Perth checkpoint is the original public watermark model. Its clean/watermarked confidence values are retained; every rounded confidence remains zero. No quality threshold, speech-model behavior, microphone/audio-device result or generated-speech claim is inferred.

The successful dependency gate does not admit the 117-distribution engine graph, change NeuTTS's Python bound, or prove its import, default constructor, full codec/reference encoding, selected-model loading or synthesis. It changes no release or production admission.

Both original host CI runs associated with this source passed: push run 39458842084 and PR run 39458856008 each report **1,271 passed tests, 84 skips and 631 passed subtests**. Raw terminal APIs and logs are retained under @@host-ci/@@.

All **287 previously frozen files** from the three failed native runs were independently checked and remain unchanged. Those failed runs remain separate historical records.

## Retained records

- @@NATIVE-SUCCESS-REVIEW.json@@: scoped interpretation, all original operation results, source/input identities and final-gate conclusions.
- @@NATIVE-LOADED-MEMBER-REVIEW.json@@: independent original-member hash/ELF checks and original archive identities.
- @@EXECUTED-SOURCE-BINDINGS.json@@: all 122 exact executed source bindings and historical freeze checks.
- @@FULL-MEMBER-INVENTORY.json.gz@@: complete verified artifact member inventory.
- @@artifact/@@: original runtime, component, APT, installation, mapping, network and input receipts/logs.
- @@integration-source/@@: exact corrected TorchAO import and unchanged original Torch/Torchtune source members.
- @@host-ci/@@ and @@HOST-CI-REVIEW.json@@: original push/PR CI evidence.
- The retained fetch, selection and review procedures describe the independent verification.

This review performed no new native operation, package installation or test, and made no product-source, Git, workflow, model-access or release changes.
""".replace("@@",chr(96))
save("README.md",readme.encode())
print(json.dumps({"status":"host-ci-originals-and-success-scope-retained","run_count":len(runs),"native_operation_groups_completed":11}))
