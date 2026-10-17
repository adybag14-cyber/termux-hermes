# Packaging CI and selective planning at cea5b45

Source commit: cea5b45c7f3b0474c51706153c2cee848f29d181.

| Workflow | Run | Actual result |
|---|---|---|
| CI, push | 39065274383 | 394 passed in 1.83 seconds; Python compile, shell syntax and JSON validation succeeded. |
| CI, pull request | 39065277607 | 394 passed in 2.64 seconds; the same ordinary CI gates succeeded. |
| Candidate planning | 39065277688 | Planner succeeded with required=false and groups=[]; build job 117491544718 was skipped. |
| Component planning | 39065277615 | Planner succeeded with required=false and groups=[]; native job 117491546077 was skipped. |

The CI test counts describe two independent executions of the suite and are not added together. The PR job checked out generated merge commit 20bbecb36c7f554978984916410bdf98abb9d552; its API receipt binds parents 3d9086cfc190ba981e48e0276234064903315539 and cea5b45c7f3b0474c51706153c2cee848f29d181. Its tree 45cbbbf83b610743db838649982546f39db3ae25 exactly equals the source commit's tree.

Both planners checked out the exact source head and recorded the change basis as exact previous PR head. Their complete 128-path reports are retained in their planning summaries. An independent comparison with source parent 1136617b0c5983f1bdc5991126758c7892f4c94c matches those recorded path lists; the original planner logs do not print the previous-head SHA.

The planning runs did not build a new package or execute a native component probe. None of these four runs produced an artifact. Existing native and candidate evidence remains separate, as do the NeuTTS native workflows.

Each run directory retains the original GitHub run/jobs/artifacts API responses, a complete original job log compressed with a verified byte-for-byte gzip round trip, and a receipt with lengths, SHA-256 values and line references. The PR merge API receipt and exact-source workflow/planner hashes are retained at this directory's top level. The collection summary indexes every retained file except itself.
