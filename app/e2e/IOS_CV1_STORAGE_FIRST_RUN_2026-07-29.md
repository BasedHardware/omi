# iOS CV1 Storage-First Acceptance — 2026-07-29

This is the physical-device evidence record for the storage-authoritative CV1
path in [`BLE_RELIABILITY_ACCEPTANCE.md`](./BLE_RELIABILITY_ACCEPTANCE.md).
It records the passing durability result and the timeline defect exposed by
the final server result. It does not claim the unrun iOS Bluetooth-radio or
manual historical-backlog cases.

## Fixture

| Item | Value |
|---|---|
| Phone | iPhone 13 Pro Max, iOS 26.5.2 |
| App | isolated Omi Dev build; production API and Firebase project |
| Candidate source | `3bf17faf7a` |
| Pendant | Omi CV1, identifier ending `1240` |
| Firmware | storage-authoritative `3.0.29` candidate |
| App policy | automatic offline sync off |
| Initial/final reported battery | 56% / 54% |

The build passed
`scripts/verify_ios_physical_test_auth_config.sh` before installation. The
production iOS app was not replaced. Do not publish the raw logs, WAL manifest,
or recording filename: they contain account and complete device identifiers.

## Physical results

| Case | Result | Evidence |
|---|---|---|
| Authenticated isolated build | Pass | The dev app retained the signed-in account, loaded Conversations, and connected to the exact paired CV1 on firmware 3.0.29. |
| Automatic deep backlog policy | Pass | Device Settings showed Auto-Sync off. Current-conversation recovery proceeded without authorizing the historical queue. |
| No-client storage interval | Pass | Every Omi app process was terminated for a 25-second marker interval. The same installed build then relaunched, reclaimed the exact pendant, and resumed live capture without a manual reconnect. |
| Canonical conversation assembly | Pass | The phone published and reconciled one `synced` canonical WAL containing 14,077 Opus frames, 281.54 seconds of decoded audio, and the full before/offline/after interval. The encoded artifact SHA-256 was `2cc31ec80d554b5fff7c76df03ea837499517cf9f2a9d880314ef0805c8e5ad3`. |
| Offline speech recovery | Pass | Independent local Whisper transcription of the canonical audio recovered the complete offline marker, including `Cobalt River 913`, followed later by the post-reconnect marker `Silver Pine 826`. |
| Final content chronology | Pass | The server-generated conversation included the offline and post-reconnect markers in the same result. |
| Final duration/timeline | **Fail** | The resulting card reported 11 seconds although the canonical source was 281.54 seconds. Content survived, but its transcript origin was still the post-reconnect live session. |
| iOS Bluetooth Settings off/on | Not run | WebDriverAgent compiled and signed, but XCTest timed out while enabling automation mode before a session existed. An app-process outage is not a substitute for a radio-toggle result. |
| Battery | Observation only | The displayed drop from 56% to 54% includes build, reconnect, automation, TTS, upload, and processing time; it is not a controlled battery benchmark. |

## Rebased process-relaunch rerun

A second isolated build from the rebased PR reproduced an iOS-only readiness
gap before the fix. CoreBluetooth retained the physical pendant link across
process termination, so the relaunched app observed the peripheral as
`connected`. `connectPeripheral` returned without rediscovering services, no
notification transitions followed, and Dart never received a fresh
`onDeviceReady`. This is the concrete "connected but no live preview" failure;
it is not a difference in the phone-side canonical assembler.

The fixed build treats an already-connected peripheral as a GATT recovery
request. It reassigns the delegate and rediscovers services, which republishes
readiness after Flutter has installed its callback. On the physical rerun:

- app launch began at `16:38:34`;
- native revalidation began at `16:38:35.779`;
- required notification transitions completed between `16:38:36.414` and
  `16:38:37.645`;
- no manual device selection or reconnect was required.

The redwood / offline cedar / post-reconnect sequoia marker interval produced
20 immutable ring WALs containing 2,253 Opus frames. Their pendant sequence
ranges formed one exact contiguous interval, `[1490992, 1491492)`, including
the audio captured while the app process was absent. This rerun proves
transport recovery and durable source coverage. It does not replace the
earlier canonical/server chronology test: production still lacks the backend
replacement contract described below.

## Timeline-defect diagnosis

The app requests a canonical transcript replacement by adding
`transcript_mode=replace` to `POST /v2/sync-local-files`. The current backend
route does not declare or consume that parameter. It instead merges recovered
segments into the existing live conversation while keeping the live
conversation's later `started_at`. Earlier recovered segments therefore receive
negative relative offsets, and the app's duration calculation reports only the
latest positive transcript end.

This is not an audio-loss failure: the canonical artifact and final summary
both contain the offline material. It is an app/backend contract gap, and the
candidate must not claim correct final timeline reconstruction until that
contract is implemented and tested end to end.

## Local evidence

- `/tmp/omi-ios-storage-first-recovery-20260729-live.log`
- `/tmp/omi-ios-storage-first-runner-syslog.log`
- `/tmp/omi-ios-storage-first-wals-latest.0iAw1m/wals.json`
- `/tmp/omi-ios-storage-final-wals.XXXXXX.json`
- `/tmp/omi-ios-canonical-recovered.wav`
- `/tmp/omi-ios-offline-window.txt`
- `/tmp/omi-ios-post-window.txt`
- `/tmp/omi-ios-reconnect-conversation.png`
- `/tmp/omi-ios-storage-first-rebased-reconnect-live-20260729.log`
- `/tmp/omi-ios-storage-first-recoveryfix-reconnect-live-20260729.log`
- `/tmp/omi-ios-wals-after-reconnectfix-20260729.json`

## Remaining acceptance work

- Implement the canonical replacement contract with atomic transcript/timeline
  ownership, then rerun this exact marker case and require an approximately
  282-second final conversation with no duplicate text.
- Reprocess one completed canonical conversation once per batch, not once per
  VAD segment.
- Run the physical iOS Bluetooth Settings off/on case after XCTest automation
  is available, including foreground, background, and locked-screen reconnect.
- Authorize one bounded manual historical-backlog snapshot and prove it
  resumes without starving live continuity.
- Run an unplugged quiet/speech cycle long enough to compare 3.0.29 battery use
  with the prior firmware.
