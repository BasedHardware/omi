# Mobile F1 telemetry inventory

Read-only map of what the Flutter app already emits for the four F1 intents
(capture start, pendant connect, conversation created, sync). F1's acceptance
is: each intent separates **transport** success from **task** success in one
query. This file is the design input, not the event registry.

Code as of `origin/main`. C1 session-generation is read from branch
`origin/task/msd-spine-a-seams` (capture OWNERSHIP.md and
`capture_session_owner.dart` on that branch); those files are not on `main`
yet. No PostHog project, warehouse, or production host was queried.
Live-volume questions are listed as owner questions at the end.

Load-bearing names already documented in `web/admin/docs/posthog-events.md`
are reused here; this inventory adds join keys, double-fire sites, and the
queries those events cannot answer.

C7 round-1 leftover: `c7_registry_test.dart` pending-passing is
`pendingContract` swallowing `UnimplementedError` by design
(`app/test/support/spine/contract.dart`). It is not a red-test failure. What
it still hides: `TestFailure` is swallowed too, so a broken legacy assertion
in the byte-identical test would stay green until the marker is removed. That
is the pending wrapper, not a C7 schema defect.

## PostHog client constraints (code only)

- Adapter: `app/lib/utils/analytics/adapters/posthog_adapter.dart`. Host
  `https://us.i.posthog.com`. `captureApplicationLifecycleEvents` is false.
  `track` is `Posthog().capture`. Do not call this host from an agent session.
- No API key / no adapter → `AnalyticsManager.track` is a no-op
  (`analytics_manager.dart:306-310`). Local `dev` + `local_dev` without a key
  emits nothing. Tests that need events inject an adapter.
- Platform gate: `PlatformService.isAnalyticsSupported` is `!kIsWeb`
  (`platform_service.dart:12`). Not a consent gate.
- Queue: 200 events, drop oldest; flush batch 20; three delivery attempts
  (`analytics_manager.dart:30-33, 325-328, 390-396`).
- Every flushed event gets `app_platform` plus `app_version` / `app_build`
  after init (`:39, :2202-2210`). Build provenance super-properties
  `git_sha` / `build_number` are SDK-registered, not per-event fields
  (`build_provenance.dart:38-41`).
- Identify sets person `$name` / `$email` (`analytics_manager.dart:302-304`).
  Signed-out capture is still a legitimate `track`.
- Property coercion drops nulls and stringifies unknown objects (`:2179-2193`).
  Nested maps from `device.toJson()` survive as maps.

Owner questions (need live data, not answered here): whether mobile and
backend listen events share one PostHog project; whether `recording_id` is
a queryable person-property or only an event property; dropped-queue rate in
the field.

## Correlation the C1 seam will give F1

On `main` today, capture has two counters, not one session generation:

- `_websocketInitGeneration` (`capture_controller.dart:492, 782, 911`) —
  bumped per transcription-socket attempt; stale sockets are stopped.
- `_sessionGeolocationGeneration` (`:1607, 1616`) — location snapshot fence.

Keep-alive reconnect (`:2005-2037, 2061-2066`) opens a new socket attempt
under a new websocket generation **without** minting a new recording id.

C1 (OWNERSHIP.md decision 5 on the seams branch, `CaptureSessionToken(generation, identity)`):
one owner `_sessionGeneration`, bumped on stop, dispose, and identity/source/device
replacement including same-id ABA. **Native mic and telemetry IDs remain the
correlation.** Configuration is a connect-attempt key *inside* a generation,
not a second capture generation. Capture a token before each await; check
after. DeviceProvider/SyncProvider generations are C2, not C1.

Consequence for F1: do not invent a mobile `session_generation` event
property. Reuse `recording_id`. C1 makes late socket/location work stop
mutating the wrong session; it does not replace the telemetry UUID.

---

## 1. Capture start

**Task:** the user asked to record (phone mic or pendant) and capture actually
produces audio. **Transport:** the transcription socket / STT path accepted
that audio. Those are different: a mic can record into WAL while the socket is
down (`onClosed` flips `record` → `interrupted`, `:1969-1975`, then keep-alive
retries the socket).

### Emitted today

| Event | Phase | Emitter | Properties |
|---|---|---|---|
| `Recording Started` | outcome of *audio actually flowing* | `RecordingLifecycleTelemetry.markStarted` `:50-58`; call sites `capture_controller.dart:1729` (phone live `onRecording`), `:1855` (phone batch after `startBatch`), `:1932` (pendant, only if `recordingState == deviceRecord` after `_resetState`) | `recording_id` (client UUID), closed `recording_source` = `phone_mic_live\|phone_mic_batch\|phone_mic_batch_auto\|pendant_live\|pendant_batch` |
| `Recording Completed` | terminal after start | `:60-74`; `:1774, 1797, 1953`, `dispose` `:1585` | start fields + `duration_seconds` + closed `reason` = `user_stopped\|device_disconnected\|mode_changed\|pipeline_closed\|unknown` |
| `Recording Start Failed` | terminal without start | `:77-88`; permission `:1697, 1812`; native/BLE miss `:1757, 1864, 1934`; `complete()` of an unstarted prepare (`:62-64`) | start id/source + closed `failure_class` including `pipeline_closed` (the dictionary omits that class; trust the code) |
| `Phone Mic Recording Started` / `Stopped` | UI tap, not capture proof | `processing_capture.dart:165, 172, 181`; `conversation_capturing/page.dart:71, 88`; `battery_info_widget.dart:260, 264` | none |
| `Transcribe Later Toggled` | setting | `capture_controller.dart:646` | `enabled` bool |
| `Transcribe Later Recording Captured` / `Processed` | local .bin appearance / user process | `local_recordings_provider.dart:101, 258` | optional `duration_seconds` |
| Backend `Transcript Started` / `Completed` / `Failed` / `Cancelled` | STT transport | `backend/utils/observability/transcription.py` (see posthog-events.md) | `recording_id`, `conversation_id` when allocated |

Prepare (`:43-48`) mints `recording_id` and sends it on `/v4/listen` as
`client_conversation_id` (`capture_controller.dart:903`,
`transcription_service.dart:125-126`). Backend
`select_recording_session_id` (`transcribe_decisions.py:220-237`) uses that
id unless a silence rollover mints a new one. HomePage passes
`connectedDevice`, which is null when disconnected
(`app/lib/pages/home/page.dart`). Prepare is skipped only when both the
argument and `_recordingDevice` are null (`:1906-1912`); a remembered
`_recordingDevice` still mints.

### Transport vs task, and the query that cannot answer it

Reuse `Recording Started` as **task** success of "capture produces audio"
(the class comments it that way: prepare is not a claim, `:10-12`).

There is **no mobile event** for transcription-socket connect/fail. Keep-alive
(`:2005-2038`) calls `_reconnectActiveCapture` (`:2061-2077`) every 15s without
a new `Recording Started`. Early returns that also emit nothing:
batch mode (`:841-843`), `decision.blockSocket` (`:865-871`), unsupported
custom-STT codec refuse (`:886-890`), `openConversationSocket` returning null
(`:906-909`), stale generation after connect (`:911-914`).

Backend `Transcript Started` is **not** socket-accept. `start_live_transcription`
(`backend/routers/listen/runtime.py`) runs from `_mark_first_audio` after a
frame is accepted (`backend/routers/listen/receiver.py`). Custom STT returns
before constructing `LiveSTTAttempt`, so those sessions have no Transcript *.

Query you would run today:

```
Recording Started
  where recording_source in (phone_mic_live, pendant_live)
```

What it cannot answer: a socket that connected but produced no transcript
versus a socket that never connected (keep-alive looping) versus audio in WAL
with `recordingState == interrupted`. Backend `Transcript Started` requires a
first accepted audio frame, so socket-up-empty and never-connected both look
like "no Transcript *". `Transcript Cancelled` only exists after an accepted
attempt. All three can sit under one `Recording Started` / one `recording_id`.

`Phone Mic Recording Started` cannot be the attempt: UI fires it *after*
`streamRecording()` returns (`battery_info_widget.dart:263-264`), including
when the controller already `failStart`ed (`:1697, 1757`).

### Correlation

`recording_id` on the lifecycle trio. Same value as `client_conversation_id`.
C1 leaves this id as the correlation (OWNERSHIP.md decision 5 on the seams branch). Websocket
generation is the connect-attempt key inside that recording, not a join field
on events.

Cheapest add if F1 must see socket transport on mobile: one
`Transcription Socket` attempt/outcome pair tagged with the **existing**
`recording_id`, emitted from `_connectTranscriptionSocket` on the success
path after the generation check (`:911-914`) **and** on each early return
above. Do not mint a second uuid. Alternative: a backend socket-accept event;
do not add both.

### Double-fire / drop

| Site | Twice? | Never? |
|---|---|---|
| `markStarted` | Guarded by `_startedEmitted` (`:51`). Re-entry with a live id is a no-op prepare (`:44`). HomePage (`page.dart` ~500-503) re-runs `streamDeviceRecording(device: connectedDevice)` on init; a live id stays quiet, a cleared id while BLE is still up mints a new Started. | Pendant: if `_initiateDeviceAudioStreaming` returns before `deviceRecord` (`:1275-1283` connection null), `failStart` instead. Phone live: if `onRecording` never fires, dispose/`complete` emits `Recording Start Failed` / `pipeline_closed`. |
| Phone-mic UI events | Three widgets can all fire Started on one user tap path (list card, capturing page, battery widget). Pause/resume on the capturing page is another Started/Stopped pair. | Pendant paths never emit them. Can fire after `failStart` (UI waits for `streamRecording()` then tracks Started). |
| `_onBatchStalled` (`:1874-1885`) | Does **not** `complete` before `_startPhoneMicBatch`. Same `recording_id`; second `markStarted` is a no-op. If the restart hits `failStart` after start already emitted, `failStart` becomes `complete(pipeline_closed)` and `_clear`s. | No Started/Completed pair around a successful stall restart. |
| `_onMicStalled` / `_resumeMicRecording` (`:293-353, 2096-2101`) | `onRecording` in resume does **not** call `markStarted`. Same `recording_id` continues. | Native restart failure is logged; no `Recording Start Failed`. |
| `dispose` `:1585` then `stopStream*` | First `complete` `_clear`s; second is a no-op (`:61`). | — |
| Keep-alive reconnect | No new lifecycle events. | Socket transport failures are invisible on mobile. |

---

## 2. Pendant connect

**Task:** the user's Omi (or other BLE device) is the capture source. **Transport:**
GATT/BLE session is up. Connected-but-not-recording is the outage-looks-like-empty-account
shape for this intent.

### Emitted today

| Event | Phase | Emitter | Properties |
|---|---|---|---|
| `Device Connected` | BLE session start (id change) | `device_provider.dart:171-172` `setConnectedDevice` when `isNewConnection` (`:156`) | **Spreads `device.toJson()`** (`analytics_manager.dart:656-664`) including raw `id`, `name`, `serialNumber` (`bt_device.dart:724-739`), plus closed `device_vendor` / `hardware_family` / `type` and hashed `transport_device_id` / optional `hardware_id`. Person: vendor, family. The Flutter dictionary row lists only the closed/hashed fields; the macOS row says no free-text names. Mobile code still sends `name`. |
| `Device Paired` | first id×uid | `:174-178` | same toJson spread + person `has_paired_device`, `first_paired_at` |
| `Device Disconnected` | BLE callback after cleanup | `:579` `onDeviceDisconnected` | **none** — no device id, no session id |
| `Device Session Ended` | `setConnectedDevice(null)` with a recorded start | `:180-201` | `duration_seconds`, bounded `reason`, optional `hci_reason_code`, vendor/family/model/firmware. No hashed transport id on this event. Dictionary mentions `reconnect_attempt_count` currently `0`; this method does not set it. |
| `Recording Started` `pendant_*` | capture task | see §1 | `recording_id`, source |
| `Connect Device Page Opened` / `Get Omi Device Clicked` | funnel, not connect | posthog-events.md | none |
| `Mobile Background Resource Session` | background vitals | `background_resource_telemetry.dart` | connected booleans, device **type** enum, BLE byte deltas; no device id |

Connect path: `onDeviceConnectionStateChanged` (`:1046-1063`) debounces connect
100ms / disconnect 500ms, then `_handleDeviceConnected` / `onDeviceDisconnected`.
Reconnect after a drop sets `connectedDevice` null first, so the next connect
to the same id is `isNewConnection` again.

### Transport vs task, and the query that cannot answer it

`Device Connected` is BLE transport. `Recording Started` where
`recording_source` starts with `pendant_` is capture task.

```
Device Connected
  left join Recording Started
    on time-window and hashed transport id
```

What it cannot answer:

1. Join is **time-order only**. `Device Connected` has hashed `transport_device_id`;
   `Recording Started` has no device hash. `Device Disconnected` has neither.
2. Socket-up / audio-flowing is still the §1 gap.
3. A connected Limitless that records on-device (`capture_controller.dart:1302-1303`)
   can sit in `deviceRecord` without a live phone timer; `Recording Started` still
   fires if `_resetState` reached `deviceRecord` (`:1931-1932`), which is "BLE
   stream set up", not "pendant wrote audio".

A count of `Device Connected` minus `Recording Started pendant_*` in a window
is not "connected but silent": reconnect bursts inflate Connected, and
phone-mic sessions inflate Started.

### Correlation

Nothing shared. Cheapest key given this code: put the existing hashed
`transport_device_id` (and `hardware_family`) on `Recording Started` when
source is pendant, and on `Device Disconnected` / `Device Session Ended`.
Do not add a new connect uuid until C2 owns DeviceProvider. C1 does not
fence device connect (OWNERSHIP.md decision 7 on the seams branch).

### Double-fire / drop

| Site | Twice? | Never? |
|---|---|---|
| `setConnectedDevice` | Every BLE drop + reconnect (debounced 100/500ms). Same physical session can be many Connected/Disconnected/Session Ended triples. | `isNewConnection` false if the same id is still `connectedDevice` (keep-alive at the transport that never nulled the provider). |
| `Device Paired` | Deduped in prefs per uid×id (`:207-214`). | uid empty → no pair event (`:210`). |
| `onDeviceDisconnected` | After debounce; firmware DFU (`prepareDFU` `:1072-1078`) disconnects and will emit. | Disconnect for a device that is neither `connectedDevice` nor `pairedDevice` is ignored (`:1059`). |
| Analytics `deviceDisconnected` vs `deviceSessionEnded` | Both fire on a session end (Ended inside `setConnectedDevice(null)`, Disconnected after). | Ended requires `sessionStartedAt`; Disconnected does not carry duration. |

---

## 3. Conversation created

**Task:** captured audio became a kept conversation the user can open.
**Transport:** bytes reached `/v4/listen` or `/v2/sync-local-files` and the
server accepted them. A 202 upload or a live socket with empty VAD is
transport without task.

### Emitted today

| Event | Phase | Emitter | Properties |
|---|---|---|---|
| `Memory Created` | client saw a `ServerConversation` | `capture_controller.dart:2444` from `_processConversationCreated`; callers `ConversationEvent` `:2276-2279` and `forceProcessingCurrentConversation` `:2389` | Historical name (there is no `Conversation Created` PostHog event). `memory_id` = server conversation id; `memory_result` = `discarded\|saved`; `conversation_source`; `duration_seconds`; `timestamp`; `action_items_count`; `transcript_language`; hardware type/firmware; **plus transcript_length / transcript_word_count / speaker_count derived by reading `convo.getTranscript()`** (`analytics_manager.dart:819-863`). Not the transcript text. |
| `Recording Started/Completed` | capture envelope | §1 | `recording_id` — **same UUID as `memory_id` when listen honors `client_conversation_id`** (backend tests + posthog-events.md). Rollover mint is the exception (`transcribe_decisions.py:235-237`). |
| `Recording Upload Completed` `result=accepted\|completed` | HTTP transport of WAL | §4 | `upload_attempt_id`, optional `recording_id` = WAL `conversationId` |
| Backend `Transcript Completed` | STT delivered nonempty text | posthog-events.md | `recording_id` |
| `LastConversationEvent` | fetch-and-upsert | `:2289-2290, 2447-2458` | **no analytics** |
| `ConversationProcessingStartedEvent` | in-progress | `:2251-2273` | **no analytics**; starts 30s auto-sync fallback |

`Manual Memory Created` (`analytics_manager.dart:1000`) is typed text, not
this intent.

### Transport vs task, and the query that cannot answer it

```
Memory Created
  where memory_result = 'saved'
```

That is the task numerator, and it **cannot** tell:

1. Transport success without a conversation: upload `result=accepted` (202)
   while the reconciler has not finished (`local_wal_sync.dart:830-843`). No
   "processing completed" mobile event. Backend transcript events cover live
   listen only, not the sync-jobs worker.
2. Transport failure that looks like an empty list: `makeApiCall` returning
   null is a different class (C3). For this intent, a listen session that
   disconnects before `ConversationEvent` (`:2262-2271` fallback only wakes
   WAL sync) emits **no** `Memory Created`.
3. Discard vs empty: discarded still emits `Memory Created`
   (`memory_result=discarded`). Filter that. Transcript word count is a
   content-derived proxy; F1 should not require it (C7 privacy: do not migrate
   this payload byte-for-byte).
4. `forceProcessingCurrentConversation` can emit `Memory Created` for a
   conversation whose `recording_id` was already completed.

Join `Recording Started.recording_id = Memory Created.memory_id` is the one
query that almost works for **live** capture. It fails when the server rolls
over the recording session id, and it does not apply to Transcribe Later until
upload stamps a conversation id onto the WAL.

### Correlation

Live: `recording_id` / `client_conversation_id` / conversation `id`.
Offline: WAL `conversationId` stamped from `event.memory.id`
(`capture_controller.dart:2409, 2254`) then passed as upload `recording_id`
(`local_wal_sync.dart:808`). Before stamp, upload events omit `recording_id`
(`sync_upload_gate.dart:394`).

C1 does not add a conversation uuid. Keep `recording_id`.

### Double-fire / drop

| Site | Twice? | Never? |
|---|---|---|
| `ConversationEvent` + later `forceProcessing` | Possible two `Memory Created` for one user-visible conversation if both paths run. No client-side dedupe on `memory_id`. | Processing-started without ConversationEvent: fallback syncs WAL, no Memory Created. |
| `LastConversationEvent` | — | Upsert with no event. |
| Discarded create | Emits, with `memory_result=discarded`. | — |

---

## 4. Sync

**Task:** captured bytes are a durable conversation on the server (live
listen already counted in §3; this intent is the **offline/WAL** path).
**Transport:** `/v2/sync-local-files` admitted and HTTP 200/202.

There is no `Sync Started` PostHog event. `WalSyncs.syncAll` writes
`DebugLogManager.logEvent('sync_started', …)` (`wal_syncs.dart:256-261`) —
local debug, not analytics.

### Emitted today

| Event | Phase | Emitter | Properties |
|---|---|---|---|
| `Recording Upload Started` | HTTP attempt after admission | `SyncUploadGate.upload` `:175-187` → manager `:484-501` | `upload_attempt_id` (new uuid per HTTP call), optional `recording_id`, `file_count`, `total_bytes`, `claims_live_capture`, `upload_source=offline_audio_queue` |
| `Recording Upload Completed` | HTTP 200 or 202 | `:198-209` | + `duration_seconds`, `result=completed\|accepted` |
| `Recording Upload Failed` | thrown after admission | `:216-236, 248-268` | + `failure_class` = `rate_limited\|timeout\|network\|authentication\|server\|unknown` |
| (none) | BLE onboard-storage **download** | `storage_sync.dart` / `sdcard_wal_sync.dart` / `ring_storage_sync.dart` `syncAll` | Debug logs only. Those files later upload via the phone WAL gate. |
| (none) | reconciler `uploaded` → `synced` | `recording_transfer_coordinator.dart` `_tryReconcile` | No PostHog. 202 `accepted` is not task success. |
| (none) | coordinator `wake` | `WakeTrigger` `:9` | Coalesced; no event per wake. |

Callers of the gate: `local_wal_sync.dart:806, 1004`;
`local_recordings_provider.dart` `uploadNativeBatchRecording` (`:223, 523-529`)
(Transcribe Later file — **no `conversationId` argument**, so upload events
omit `recording_id`). Admission
failures (rate limit, cutover quarantine) throw **before** Started (`:166-173`).

### Transport vs task, and the query that cannot answer it

```
Recording Upload Completed
  where result = 'completed'
```

`result=completed` is HTTP 200 with inline processing (`local_wal_sync.dart:813-828`).
`result=accepted` is 202 — bytes stored, job outstanding (`:830-843`).

What it cannot answer:

1. **202 vs processed conversation.** No mobile event when the reconciler
   marks `WalStatus.synced`. Join to `Memory Created` by `recording_id` only
   works after the WAL was stamped; live-capture claim batches may stamp
   first (`capture_controller.dart:2409` then `_autoSyncSessionWals`).
2. **BLE drain vs cloud upload.** A long ring-buffer download with no HTTP
   yet looks like "sync is stuck" with zero upload events.
3. **Coordinator pass vs upload.** `wake(foregrounded)` that discovers an
   empty backlog (`RecordingTransferDrainResult.skipped`) is silent.
4. `claims_live_capture` is a server-claim flag, not "this is the live
   session." Do not treat it as task success.

### Correlation

`upload_attempt_id` joins Started/Completed/Failed for **one HTTP**.
Retries mint a new attempt id. `recording_id` joins to capture/conversation
**when present**. C1 recovery (`requestRecovery` / same
`RecordingTransferCoordinator`) coalesces wakes (`recording_transfer_coordinator.dart:191-221`)
so F1 should not emit per wake; emit per admitted HTTP (already the case).

C2 will own SyncProvider construction; do not wait for it to use
`upload_attempt_id`.

### Double-fire / drop

| Site | Twice? | Never? |
|---|---|---|
| Each `_uploadGate.upload` | New `upload_attempt_id`. Retries after `miss` are new attempts, which is correct for transport. | Rate-limit / quarantine: no Started (not an HTTP attempt). |
| `wake` coalescing | At most one extra serial pass (`:191-192`). | Background wakes no-op if not foreground (`:197`). |
| Transcribe Later `local_recordings_provider` | Own HTTP via the same gate. | `transcribeLaterRecordingProcessed` is a UI process tap (`:258`), not upload proof. |
| Device BLE `syncAll` | — | No upload events until files land on phone WAL. |

---

## Proposed F1 event set

Fewer events that answer the four queries. **Reuse** means keep the wire name
and join key; payload privacy fixes are allowed and are not "new events".

| Intent | Event | Reuse? | Query it makes possible |
|---|---|---|---|
| Capture start | `Recording Started` / `Completed` / `Start Failed` | **Reuse** as-is (`recording_id`, `recording_source`) | Attempt/outcome of audio flowing. Started is the task numerator. |
| Capture start | `Transcription Socket` attempt + terminal (`connected` / `failed` / `cancelled` / `skipped`), properties: existing `recording_id`, closed `failure_class` | **Add one pair, or add a backend socket-accept event — not both.** Emit from `_connectTranscriptionSocket` after the generation check and on each early return (batch skip, STT block, codec refuse, null socket). | The query today's events cannot answer: socket-up-empty vs never-connected. Backend `Transcript Started` is first accepted audio frame, not socket accept. Custom STT has no Transcript *. |
| Capture start | Backend `Transcript Started/Completed/Failed/Cancelled` | **Reuse** (already emitted server-side) | Join by `recording_id` for "did STT accept audio / deliver text". Owner question: same PostHog project as mobile? |
| Capture start | `Phone Mic Recording Started/Stopped` | **Do not use** for F1 | UI-tap series; can fire after `failStart`. Leave for C8. |
| Pendant connect | `Device Connected` / `Disconnected` / `Session Ended` | **Reuse names**; **stop spreading `toJson()`** (raw `id`/`name`/`serialNumber`). Keep hashed `transport_device_id` on Connected **and add it to Disconnected and Session Ended**. | BLE transport session with a join key. |
| Pendant connect | `Recording Started` `pendant_*` | **Reuse**; add hashed `transport_device_id` when source is pendant | Connected ⋈ Started: transport vs actually capturing. |
| Conversation created | `Memory Created` | **Reuse name and `memory_id` / `memory_result` / `conversation_source`**. **Drop** transcript-derived length/word/speaker fields (C7 privacy; not needed for the query). | Task: `memory_result=saved`. Join to `Recording Started` on `recording_id = memory_id` for live listen. |
| Conversation created | (no new "Conversation Created" alias) | Do not dual-emit | Dictionary already forbids the rename. |
| Sync | `Recording Upload Started/Completed/Failed` | **Reuse** (`upload_attempt_id`, `recording_id`, `result`, `failure_class`) | Transport of `/v2/sync-local-files`. Filter `result=accepted` vs `completed`. |
| Sync | `Recording Sync Reconciled` (or equivalent) once WAL status becomes `synced`, properties: `recording_id`, `job_id` (opaque), closed `result` | **Add** one terminal, from the reconciler path that already mutates `WalStatus.synced` | `Upload Completed accepted` ⋈ Reconciled: transport vs processed. Without this, 202 is a lie for task success. |
| Sync | Per-`wake` or BLE-download events | **Do not add** | Coordinator coalescing and BLE drain are not the HTTP contract. Device-download failure can wait; it is not the empty-account confusion (that is HTTP/listen). |

Intent → one query after this set:

1. **Capture start:** `Recording Started` minus (`Transcription Socket failed` ∪ no socket event ∪ backend `Transcript Failed`) vs `Transcript Completed`, joined by `recording_id`.
2. **Pendant connect:** `Device Connected` left join `Recording Started` where `recording_source like pendant_%` on `transport_device_id` + time bound.
3. **Conversation created:** `Memory Created` `memory_result=saved` joined to `Recording Started` or `Recording Upload Completed` on `recording_id`/`memory_id`. Discarded is visible, not silent.
4. **Sync:** `Recording Upload Completed` ⋈ `Recording Sync Reconciled` on `recording_id` (or `upload_attempt_id` if stamped). `accepted` without Reconciled is in-flight, not success.

Do not pad bool toggles. Do not wait for C1's generation integer to appear on
events. Do not mark `analytics_manager.dart` adopted until C8.

## Where this inventory is most likely wrong

1. **`recording_id = conversation id` on every live session.** True for the
   documented listen path and backend unit tests. Wrong if a mobile listen
   rollover mints a new server id (`transcribe_decisions.py:235-237`) or if
   some sources omit `client_conversation_id`. A single field capture of
   production listen query params would confirm; that is an owner/staging
   question, not a production PostHog pull from this lane.
2. **Pendant `Recording Started` means audio is flowing.** The pendant
   `markStarted` is "state became `deviceRecord` after `_initiateDeviceAudioStreaming`"
   (`:1931-1932`), which is "BLE listener attached", not a native `onRecording`
   callback (phone live has that callback; pendant does not). Limitless
   onboard recording may therefore over-count task success.
3. **Upload `recording_id` always joins capture.** Phone WAL uploads pass
   `conversationId: batchWals.first.conversationId` and omit the property when
   that string is null/empty (`sync_upload_gate.dart` `_basePayload`).
   Transcribe Later `uploadNativeBatchRecording` never passes `conversationId`
   at all, so those HTTP events have no `recording_id` even after a file is
   associated with a conversation in the UI. Treating missing `recording_id`
   as a broken join will mis-read Transcribe Later.

Secondary risk: Device Connected payload may already have been cleaned in a
commit not yet on this `main`; the `toJson()` spread is what this tree emits.
Verify before F1 changes that event.
