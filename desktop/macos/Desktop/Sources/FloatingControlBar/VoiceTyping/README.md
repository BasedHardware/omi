# Voice typing package map

This directory contains the policy values, transcription adapters, insertion
boundary, and short-lived recovery helpers used by `VoiceTypeSession`.
`PushToTalkManager` remains the owner of the microphone and turn lifecycle;
these files do not create a second lifecycle or capture path.

- `DeadlinedOperation.swift` — bounded async work for transcription and polish.
- `DictationFormatter.swift` — local filler, punctuation, and capitalization cleanup.
- `DictationPolisher.swift` — finite skip policy and bounded online rewrite acceptance.
- `DictationTranscriber.swift` — backend and local transcription fallback adapter.
- `OfflinePTTQuestionRecovery.swift` — owner-scoped, five-minute unsent question recovery.
- `PTTRecoveryActions.swift` — recovery and undo actions presented by the bar/menu.
- `PTTRoutePolicy.swift` — key-down network and route selection.
- `TextInsertionSink.swift` — exact-target AX insertion, clipboard fallback, and verified undo receipt.
- `VoiceTypeAudioTrim.swift` — bounded opening and turn audio slices.
- `VoiceTypeCommandParser.swift` — `type` wake-word and payload decision policy.
- `VoiceTypeOpeningDecoder.swift` — exact-opening singleflight decode cache.
- `VoiceTypeSession.swift` — dictate-or-ask latch and release delivery policy.
- `VoiceTypeWakeWordProbeSchedule.swift` — advisory mid-hold probe schedule.
