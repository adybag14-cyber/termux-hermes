# Packaging CI and selective planning at 54c7f99

Source commit: 54c7f99263041949eb5513a535c0e663916e78d8.

| Workflow | Run | Actual result |
|---|---|---|
| CI, push | [39072136399](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39072136399) | 558 passed in 3.09 seconds; Python compile, shell syntax and JSON validation succeeded. |
| CI, pull request | [39072139074](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39072139074) | 558 passed in 3.00 seconds; the same ordinary CI gates succeeded. |
| Candidate planning | [39072139004](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39072139004) | Planner succeeded with required=false and groups=[]; build job 117511793801 was skipped. |
| Component planning | [39072139089](https://github.com/adybag14-cyber/termux-hermes/actions/runs/39072139089) | Planner succeeded with required=false and groups=[]; native job 117511791019 was skipped. |

The CI counts describe two independent executions of the suite and are not added together. Both runs reported zero skipped tests. The separate Windows host test result is outside this CI collection.

The PR job checked out generated merge commit 7d9a1bedfc8a49e5806c3c24c46b7f2af6f88b66. Its original [API response](pr-test-merge-commit.json) binds parents 3d9086cfc190ba981e48e0276234064903315539 and 54c7f99263041949eb5513a535c0e663916e78d8. Its tree d6192e5292117c38c353cd7506a790530d6f9a93 exactly equals the [source commit](source-commit.json) tree.

Both planners checked out the exact source head and recorded the change basis as exact previous PR head. Their complete 68-path reports are retained in their planning summaries. The retained GitHub API comparison with source parent 0111f4dbd08e609e0e66811360875ee267b83d34 exactly matches the recorded path lists; the original planner logs do not print the previous-head SHA.

The planning runs did not build a package or execute a native component probe. None of these four runs produced an artifact. The separate audio-staging workflow and NeuTTS native workflows are outside this collection. These CI results establish no physical microphone, recording, VAD, model inference or release readiness.

Each run directory retains the original GitHub run/jobs/artifacts API response bytes, its complete original job log compressed with a verified byte-for-byte gzip round trip, and a receipt with byte lengths, SHA-256 values and log-line references. API responses and logs were captured with Python subprocess binary pipes; no Windows newline or text re-encoding was applied. Only derived JSON and this summary were serialized.

[Source input hashes](source-inputs.json) were measured from the GitHub Contents API at the exact full source SHA, decoded from Base64 and checked against each returned Git blob SHA-1. The original API responses are retained under source-api/. The complete original parent comparison response is retained as gzip with a verified byte-for-byte round trip and a [compact path receipt](parent-comparison.json). No local Git command was executed. The [collection summary](summary.json) indexes every retained file except itself.
