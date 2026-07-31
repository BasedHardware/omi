# INV-CAPTURE-1: One durable conversation timeline

**Status:** proposed

**Statement:** Pendant storage records, BLE packets, retry ranges, local files,
live transcript messages, and backend jobs are transport artifacts of one
chronological conversation timeline. They must never become independent
user-visible conversations merely because capture crossed a storage boundary,
a connection dropped, an app restarted, or a transfer was retried.

## Authoritative flow

1. The pendant durably records ordered audio with enough sequence and capture
   time information to recover a missing range. Pendant storage is capture
   authority until the next layer has durably accepted the same coverage.
2. The companion app assembles ordered coverage into the current logical
   conversation before presenting, uploading, or deleting it. Physical ring
   ranges and fixed-duration archives remain internal.
3. Live preview is a projection of that open conversation. Reconnect reclaims
   the same conversation identity and reconciles preview segments; it does not
   start a new conversation solely because BLE or the transcription socket
   changed sessions.
4. The app uploads one idempotent logical artifact or multipart job for one
   conversation window. Retries reuse its identity and source coverage. VAD may
   classify assembled audio, but individual noise fragments are not independent
   upload jobs.
5. The backend monotonically projects the accepted timeline into transcript,
   conversation, and summary state. Late recovery inside the conversation
   boundary updates the same conversation in timestamp order and invalidates
   derived work that depended on the incomplete transcript.

The configured conversation-silence duration is the semantic boundary. A BLE
disconnect, WebSocket close, five-minute archive rollover, app lifecycle event,
or upload retry is not a conversation boundary.

## Scheduling and power

- Live capture owns the next available BLE transfer slice.
- Missing coverage in the still-open conversation may be repaired
  automatically because it restores the active user experience.
- Older history requires an explicit Sync action or the existing Auto Sync
  opt-in. Charging increases the budget for authorized work; it does not grant
  authority to drain history.
- Authorized historical transfer runs in bounded slices and yields whenever
  live coverage is available. If concurrent transfer cannot preserve live
  transcription on a platform/device pair, historical transfer pauses.
- Audio is acknowledged or deleted from the pendant only after the next
  authoritative layer has durably stored its identity and coverage.

## User-visible contract

- **Connected** means the paired pendant has a usable capture path. Bluetooth
  attachment without ready GATT/audio ownership is connecting or degraded.
- **Listening** means the live transcription service accepted the session and
  the app is feeding it ordered audio. If audio is being retained for recovery
  while STT reconnects, the UI says so; it must not claim Listening.
- Sync shows logical conversations, not physical storage fragments. A logical
  row has playable audio or an explicit retained/remote-only explanation.
- Retry reports a bounded reason and keeps durable data. Refreshing one surface
  must not make a newer conversation disappear because another projection is
  stale.
- Android, iOS, and desktop share the same conversation, scheduling, retry, and
  projection policy. Native code owns transport mechanics only. A surface that
  has not implemented durable ring recovery must say so; it cannot claim
  parity.

## MUST NOT

- Upload, transcribe, summarize, or render raw one-to-nine-second ring/storage
  fragments as separate conversations solely because those files exist.
- Run automatic deep backlog transfer by default, including while charging.
- Let backlog transfer delay or disable live capture.
- Acknowledge a range before durable acceptance, or create a new retry identity
  for the same range.
- Clear the live preview or create a new conversation solely on transport
  reconnect.
- Show Listening after the live socket closes or before server readiness.
- Apply platform-specific conversation boundaries or backlog policy.

## Guard tests

- `app/test/unit/conversation_audio_assembler_test.dart` — ordered assembly,
  overlap/deduplication, and conversation-window grouping.
- `app/test/unit/local_wal_sync_test.dart` — raw-fragment exclusion, logical
  upload grouping, idempotent coverage, and bounded historical batches.
- `app/test/providers/sync_provider_sync_wal_wake_test.dart` — explicit backlog
  authority and live-priority scheduling.
- `app/test/services/capture/conversation_session_window_test.dart` and
  `app/test/services/capture/live_transcript_preview_test.dart` — conversation
  identity and preview continuity.
- `app/test/providers/capture_provider_test.dart` and
  `app/test/widgets/transcription_paused_warning_test.dart` — honest live
  readiness state and reconnect recovery.
- `app/test/services/capture/device_audio_streaming_policy_test.dart` — no live
  tail consumption before transcription readiness.
- `app/e2e/BLE_RELIABILITY_ACCEPTANCE.md` — Android/iOS physical-device parity,
  disconnect recovery, logical backlog, throughput, and deterministic audio.

## Path globs

- `omi/firmware/**`
- `app/lib/services/capture/**`
- `app/lib/services/wals/**`
- `app/lib/providers/sync_provider.dart`
- `app/lib/pages/conversations/**`
- `app/android/**/ble/**`
- `app/ios/**/Ble/**`
- `desktop/**`
- `backend/routers/transcribe.py`
- `backend/routers/sync.py`
- `backend/utils/stt/**`

## PR rule

Name `INV-CAPTURE-1` in every PR that changes a path above and state which
authoritative boundary and physical acceptance rows the change preserves. The
invariant remains proposed until its behavior and guard surfaces are unchanged
for seven days.
