# Packaging CI and selective planning at 0111f4d

Source commit: 0111f4dbd08e609e0e66811360875ee267b83d34.

| Workflow | Run | Actual result |
|---|---|---|
| CI, push | [39070524197](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39070524197) | 532 passed in 2.41 seconds; Python compile, shell syntax and JSON validation succeeded. |
| CI, pull request | [39070526887](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39070526887) | 532 passed in 4.05 seconds; the same ordinary CI gates succeeded. |
| Candidate planning | [39070526893](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39070526893) | Planner succeeded with required=false and groups=[]; build job 117507020967 was skipped. |
| Component planning | [39070526891](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39070526891) | Planner succeeded with required=false and groups=[]; native job 117507035633 was skipped. |

The CI counts describe two independent executions of the suite and are not added together. Both runs reported zero skipped tests. The separate Windows host test result is outside this CI collection.

The PR job checked out generated merge commit b532aa1dc1cfd66a33d0e1133bb296f21137d0cf. Its original [API response](pr-test-merge-commit.json) binds parents 3d9086cfc190ba981e48e0276234064903315539 and 0111f4dbd08e609e0e66811360875ee267b83d34. Its tree 387ad07830714c7ccacd77931b8ee806c45b6d1f exactly equals the [source commit](source-commit.json) tree.

Both planners checked out the exact source head and recorded the change basis as exact previous PR head. Their complete 47-path reports are retained in their planning summaries. The retained GitHub API comparison with source parent 38e99c23e8adae66825fc1dff73dcce7f373dac2 exactly matches the recorded path lists; the original planner logs do not print the previous-head SHA.

The planning runs did not build a package or execute a native component probe. None of these four runs produced an artifact. The separate audio-staging workflow and NeuTTS native workflows are outside this collection. These CI results establish no physical microphone, recording, VAD, model inference or release readiness.

Each run directory retains the original GitHub run/jobs/artifacts API response bytes, its complete original job log compressed with a verified byte-for-byte gzip round trip, and a receipt with byte lengths, SHA-256 values and log-line references. API responses and logs were captured with Python subprocess binary pipes; no Windows newline or text re-encoding was applied. Only derived JSON and this summary were serialized.

[Source input hashes](source-inputs.json) were measured from the GitHub Contents API at the exact full source SHA, decoded from Base64 and checked against each returned Git blob SHA-1. The original API responses are retained under source-api/. The complete original parent comparison response is retained as gzip with a verified byte-for-byte round trip and a [compact path receipt](parent-comparison.json). No local Git command was executed. The [collection summary](summary.json) indexes every retained file except itself.
