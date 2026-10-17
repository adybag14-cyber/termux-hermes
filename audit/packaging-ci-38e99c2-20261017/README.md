# Packaging CI and selective planning at 38e99c2

Source commit: 38e99c23e8adae66825fc1dff73dcce7f373dac2.

| Workflow | Run | Actual result |
|---|---|---|
| CI, push | [39068819974](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39068819974) | 503 passed in 3.14 seconds; Python compile, shell syntax and JSON validation succeeded. |
| CI, pull request | [39068822844](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39068822844) | 503 passed in 3.06 seconds; the same ordinary CI gates succeeded. |
| Candidate planning | [39068822848](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39068822848) | Planner succeeded with required=false and groups=[]; build job 117502006210 was skipped. |
| Component planning | [39068822855](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39068822855) | Planner succeeded with required=false and groups=[]; native job 117502006667 was skipped. |

The CI counts describe two independent executions of the suite and are not added together. Both runs reported zero skipped tests. The separate Windows host test result is outside this CI collection.

The PR job checked out generated merge commit 4c0ffc97cea3c868c70690a33120d04e1502afea. Its original [API response](pr-test-merge-commit.json) binds parents 3d9086cfc190ba981e48e0276234064903315539 and 38e99c23e8adae66825fc1dff73dcce7f373dac2. Its tree 4d19722709144aa37d356df1d29ecfcf14aa8f9b exactly equals the [source commit](source-commit.json) tree.

Both planners checked out the exact source head and recorded the change basis as exact previous PR head. Their complete 27-path reports are retained in their planning summaries. An independent comparison with source parent 7fe51dd96c6523d7336906cedef29cdc6304daaf exactly matches the recorded path lists; the original planner logs do not print the previous-head SHA.

The planning runs did not build a package or execute a native component probe. None of these four runs produced an artifact. The separate audio-staging workflow and NeuTTS native workflows are outside this collection. These CI results establish no physical microphone, recording, VAD, model inference or release readiness.

Each run directory retains the original GitHub run/jobs/artifacts API response bytes, its complete original job log compressed with a verified byte-for-byte gzip round trip, and a receipt with byte lengths, SHA-256 values and log-line references. API responses and logs were captured with Python subprocess binary pipes; no Windows newline or text re-encoding was applied. Only derived JSON and this summary were serialized.

[Source input hashes](source-inputs.json) were measured with git show at the exact source commit. The [collection summary](summary.json) indexes every retained file except itself.
