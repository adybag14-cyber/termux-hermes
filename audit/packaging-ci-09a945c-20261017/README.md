# Packaging CI and selective planning at 09a945c

Source commit: 09a945cff9e07243fb24e99d9a58a12d500eb18d.

| Workflow | Run | Actual result |
|---|---|---|
| CI, push | [39076074880](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076074880) | 590 passed in 2.72 seconds; Python compile, shell syntax and JSON validation succeeded. |
| CI, pull request | [39076077781](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076077781) | 590 passed in 3.16 seconds; the same ordinary CI gates succeeded. |
| Candidate planning | [39076077731](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076077731) | Planner succeeded with required=false and groups=[]; build job 117523413960 was skipped. |
| Component planning | [39076077834](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39076077834) | Planner succeeded with required=false and groups=[]; native job 117523416645 was skipped. |

The CI counts describe two independent executions of the suite and are not added together. The push reported 0 skipped tests and the PR reported 0. The separate Windows host test result is outside this CI collection.

The PR job checked out generated merge commit 7cbc286a4a71440b4c9ab46f19db36a4f646e552. Its original [API response](pr-test-merge-commit.json) binds parents 3d9086cfc190ba981e48e0276234064903315539 and 09a945cff9e07243fb24e99d9a58a12d500eb18d. Its tree fe5180b7cf6d8bea0a754701ddc1b18ce7c65ca3 exactly equals the [source commit](source-commit.json) tree.

Both planners checked out the exact source head and recorded the change basis as exact previous PR head. Their complete 56-path reports are retained in their planning summaries. The retained GitHub API comparison with source parent bd9b6350705429d8002b0aeda2aefe9e26d8d967 exactly matches the recorded path lists; the original planner logs do not print the previous-head SHA.

The planning runs did not build a package or execute a native component probe. None of these four runs produced an artifact. The separate audio-staging workflow and NeuTTS native workflows are outside this collection. These CI results establish no physical microphone, recording, VAD, model inference or release readiness.

Each run directory retains the original GitHub run/jobs/artifacts API response bytes, its complete original job log compressed with a verified byte-for-byte gzip round trip, and a receipt with byte lengths, SHA-256 values and log-line references. API responses and logs were captured with Python subprocess binary pipes; no Windows newline or text re-encoding was applied. Only derived JSON and this summary were serialized.

[Source input hashes](source-inputs.json) were measured from the GitHub Contents API at the exact full source SHA, decoded from Base64 and checked against each returned Git blob SHA-1. The original API responses are retained under source-api/. The complete original parent comparison response is retained as gzip with a verified byte-for-byte round trip and a [compact path receipt](parent-comparison.json). No local Git command was executed. The [collection summary](summary.json) indexes every retained file except itself.
