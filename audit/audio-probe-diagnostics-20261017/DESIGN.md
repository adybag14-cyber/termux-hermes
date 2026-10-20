# Audio runtime failure diagnostics

Native run 39075197287 at 09dda7a9e7e55977e846742064cd7b4fa32978bc completed its first fresh preparation and failed inside the subsequent readiness worker. The exact original run, 81-member proof ZIP and full text receipts are preserved in the adjacent native-run audit. Its child stderr contains only the generic failure of the strict sounddevice exception-type predicate; the original exception details were not retained by that version.

This change preserves that failure and adds evidence for the next native run. Main now records the error's type/message, exception-chain type/module/message/args, and formatted original traceback in audio-readiness-failure.json. It also emits the full traceback to retained stderr. If receipt writing fails, the original traceback and nonzero exit still survive.

Every existing function except main remains byte-identical, including the whole runtime worker, full preparation/probe verification, numerics, explicit pinned audio libraries, exact PortAudioError predicate, runtime mappings, payload preservation, launcher-version check, and native success receipts. The preparation helper is unchanged. The original 118 test bytes remain intact, with seven new parameterized host regression cases appended.

The new tests exercise actual Python exception chaining, CLI nonzero behavior, durable diagnostics, suppressed/explicit causes, and a real filesystem write failure. They do not simulate or certify Android, sounddevice imports, a native dependency pass, audio initialization, capture, or VAD.

The import's underlying cause is still unknown. Exact upstream sounddevice source performs library discovery before PortAudio initialization, but that source observation is not a diagnosis. No generic failure is reclassified as an expected missing-framework condition. A root-reviewed native retry must expose the actual exception before further compatibility changes.
