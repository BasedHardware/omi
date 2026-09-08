# Mac→Windows Parity Audit — WAL / Sync / Offline

> **Re-audited 2026-08-22.** Scope unchanged from the 2026-08-20 pass: write-ahead log (raw
> audio buffering) for BLE wearable devices, storage sync (BLE SD-card pull), WiFi sync, and
> cloud-sync reconciliation — plus, as a comparison point, Windows' own offline resilience for
> its realtime STT path. Windows baseline re-checked directly against source:
> `desktop/windows/src/renderer/src/capture/{liveMicSession,liveRescue,liveStore,meetingSession,
> AudioSessionHost}.ts`, `desktop/windows/src/renderer/src/hooks/useRecorder.ts`,
> `desktop/windows/src/renderer/src/lib/sync/{outbox,outboxSweep,conversationSync,
> segmentRetention,backfill,mergeLanes}.ts`, `desktop/windows/src/main/ipc/omiListen.ts`,
> `desktop/windows/src/main/integrations/{syncState,syncStateLogic}.ts`, plus `git log`/`git show`
> on all of the above (and on `WIRING-AUDIT.md`) to date every claim.

> **Headline correction: this file's own "offline resilience" section was already wrong on the
> day it was written, and stayed wrong for over a month.** The 2026-08-20 audit describes
> Windows' realtime listen path as having "no fallback path" on a mid-session socket drop and
> "no automatic reconnect-and-resume for a live conversation" — but the fixes for exactly those
> two gaps (silence keepalive so the socket never starves, and reconnect-with-resume +
> from-segments rescue on exhaustion) were committed **35–37 minutes after** this very file was
> added to the repo: the doc landed at `66e150275c` (2026-07-13 11:34 ET), and
> `5b5ef25b81`/`445967cf24`/`97a9841eca` (the keepalive/watchdog fix, the live-mic reconnect+rescue
> fix, and the app-lifetime outbox-sweep fix) landed at 12:09–12:11 the same day — all more than
> five weeks before the audit's nominal 2026-08-20 date, and confirmed still present and wired up
> in the current tree. `WIRING-AUDIT.md`'s own status header (written 13:37 that same day) already
> recorded C1/C2 as fixed; this file simply never got the memo. Separately, the old file's Mac
> citation `APIClient.swift:5495-5545` for `uploadLocalFilesV2`/`fetchSyncJobStatus` is now stale
> for an unrelated reason — that file was split on 2026-07-16 (`c7ca348b04`) and those two
> functions live in `Services/APIClient/APIClient+Messages.swift:104` and `:125`;
> `APIClient.swift` itself is down to 1164 lines. And the old file's repeated `BUILD_PLAN.md`
> citations (quoted "DEFERRED (Chris 2026-07-10)" text, `BUILD_PLAN.md:227-228`) point at a file
> that does not exist anywhere in this repo's git history under that name — the underlying
> claim (BLE/Phase 7 deferred) independently checks out against current source and against three
> other audit files that assert the same thing, but the specific file/line citation could not be
> verified and should not be trusted at face value.

## Changed since the 2026-08-20 audit

| Item | Old audit said | Actually (2026-08-22) |
|---|---|---|
| Silence-starved `/v4/listen` socket (WIRING-AUDIT C1) | Implied still live: "no fallback path... if the socket dies mid-send" | **Fixed since 2026-07-13** (`omiListen.ts:97-144`, commit `5b5ef25b81`). A 30s-idle silence keepalive (`b'\x00'*320`) plus a 60s dead-socket watchdog now run on every conversation-mode socket. |
| No reconnect for the continuous mic session (WIRING-AUDIT C2) | "no automatic reconnect-and-resume for a live conversation/screen session" | **Fixed since 2026-07-13** (`liveMicSession.ts` + `liveRescue.ts`, commit `445967cf24`). Up to 10 capped-backoff reconnects RESUME the same server-side conversation via `client_conversation_id`; on exhaustion, retained segments are rescued through the sync outbox as a dedupe-checked from-segments upload. |
| Sync-outbox retry only on page mount | Not mentioned (out of this file's stated scope, but relevant context for the "conversation-record sync resilience" claim) | **Fixed since 2026-07-13** (`outboxSweep.ts`, commit `97a9841eca`). An app-lifetime 60s timer (started in `App.tsx` at sign-in) now matches Mac's unconditional launch-time timer; page-mount retry still also runs, sharing the same throttle. |
| "Windows' own offline resilience" framed as one undifferentiated risk | One generic paragraph covering "Windows' mic/system-audio capture" | **Needs to be three separate answers.** The always-on continuous mic lane (`liveMicSession.ts`) is now genuinely resilient to network blips and short outages. The manual screen-session lanes (`useRecorder.ts`, mode `'transcribe'`) and the meeting system-audio lane (`meetingSession.ts`) still have **no reconnect at all** on a mid-session drop — `onError` just logs and gives up, matching the old audit's description exactly for those two lanes only. |
| App-crash-mid-recording durability | Not distinguished from network-blip loss | **Still genuinely absent**, and correctly flagged as still-open in `WIRING-AUDIT.md`'s deferred list ("Stream 4"). Retained segments (`liveRescue`'s `SegmentRetainer`, `segmentRetention`'s `SegmentStore`) live only in renderer memory until a conversation finalizes or the rescue path fires — a hard process crash mid-conversation loses whatever hasn't been flushed to SQLite yet, on every lane, still today. |
| Mac citation `APIClient.swift:5495-5545` | Cited as the location of `uploadLocalFilesV2`/`fetchSyncJobStatus` | **Stale.** File split 2026-07-16; functions now at `Services/APIClient/APIClient+Messages.swift:104,125`. `APIClient.swift` is 1164 lines total. |
| `BUILD_PLAN.md:227-228` / Phase-7 quote | Cited twice as the source of the deferred-BLE decision and the "reuse the Flutter WAL flow" plan | **Unverifiable** — no file by that name exists anywhere in git history. The deferred-BLE *conclusion* still holds (corroborated independently below and by `00-INDEX.md`, `08-bluetooth-wearables.md`, `14-sequencing-plan.md`), but this specific citation cannot be checked and may have always been a hallucinated pointer to an out-of-repo planning doc. |
| WAL / cloud-upload / storage-sync / WiFi-sync / Storage-Sync-UI subsystems | Absent | **Still absent**, re-confirmed by grep (`sync-local-files` appears only in the generated OpenAPI stub; zero `Bluetooth`/BLE/GATT/device-connection code in `desktop/windows/src`, zero `noble`-style BLE dependency in `package.json`). No status change on these five rows. |

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| WAL raw-audio buffering (BLE device frames) | `WAL/WALService.swift`, `OmiWAL/WALModel.swift` | **Absent** | H |
| WAL `.bin` on-disk format + filename convention | `OmiWAL/WALModel.swift` (`generateFileName`, `WALSyncUploadFileName`) | **Absent** | M |
| Cloud upload via `POST /v2/sync-local-files` | `WAL/WALService.swift` (`uploadWalToCloud`), `Services/APIClient/APIClient+Messages.swift` | **Absent** | H |
| Upload reconciliation (poll job status, dedupe, retry) | `WAL/WALSyncReconciler.swift`, `WAL/WALCloudSyncLogic.swift` | **Absent** | M |
| BLE SD-card storage sync (pull backlog off device flash) | `WAL/StorageSyncService.swift` | **Absent** | M |
| WiFi sync (device SoftAP + TCP bulk transfer) | `WAL/WifiSyncService.swift`, `Bluetooth/WifiSyncTypes.swift` | **Absent** | L |
| Storage Sync UI (progress, pending badge, error/retry) | `WAL/StorageSyncView.swift` | **Absent** | L |
| Continuous mic session resilience (reconnect+resume, silence keepalive, crash-rescue) | (N/A — different architecture; nearest Mac analogue is the WAL surviving a BLE drop) | **Present, fixed 2026-07-13** — resumes across network blips; still no protection against a full process crash | M |
| Screen-session / meeting system-audio lane resilience | (N/A) | **Weaker** — no reconnect on drop; whatever was captured before the drop still syncs, nothing after it does | M |
| Conversation-record (post-STT) sync resilience — Windows' analogous "WAL" | (N/A — Mac has no equivalent; Mac WALs raw audio, not finished conversations) | **Present**, app-lifetime retry sweep added 2026-07-13; arguably stronger than Mac for this narrower case | — |

## Spotted-first: architectural framing

Mac's WAL and Windows' "conversation sync" solve **different problems** and are not directly interchangeable:

- **Mac WAL** buffers **raw Opus audio frames** streamed continuously off a BLE wearable (Omi pendant), because the pendant has no reliable network of its own and the Mac may itself be offline/asleep/out of Bluetooth range for stretches. The unit of durability is a chunk of undecoded audio; the backend does STT server-side after upload.
- **Windows conversation sync** (`src/renderer/src/lib/sync/outbox.ts`, `conversationSync.ts`) buffers **already-transcribed conversation records** (mic + system-audio segments produced by Windows' own local realtime STT pipeline over `/v4/listen` or `/v2/voice-message/transcribe-stream`), and reliably POSTs the finished conversation once via `/v1/conversations/from-segments` with a CAS-based outbox and unconfirmed-dedupe protocol. There is no raw audio in this path at all — audio never touches disk, only text segments do (in SQLite, via `window.omi.updateLocalConversationSync`/`insertLocalConversation`).

This means: Windows has **no BLE wearable device support at all** — reconfirmed this pass by grep for `Bluetooth`/BLE/GATT/device-connection terms across `desktop/windows/src` (only two unrelated hits, both comments about preferring a non-Bluetooth *system* microphone) and for a `noble`-style BLE dependency in `package.json` (none) — so the entire Mac WAL/StorageSync/WifiSync subsystem still has **zero Windows counterpart**, not a weaker one. This is corroborated independently by `00-INDEX.md`, `08-bluetooth-wearables.md`, and `14-sequencing-plan.md`, all of which treat Phase 7 (BLE/wearables) as deferred; only the specific `BUILD_PLAN.md` citation for that decision is unverifiable (see the callout above).

---

## WAL raw-audio buffering

**What it is**: A local write-ahead log that captures every audio frame coming off a connected BLE device in near-real-time, chunked into ~60s segments, so that no audio is lost if the network, backend, or app itself goes away mid-stream.

**Where (Mac)**: `desktop/macos/Desktop/Sources/WAL/WALService.swift` (singleton `@MainActor` service); model in `desktop/macos/Desktop/Sources/OmiWAL/WALModel.swift`. Re-verified this pass: both files still exist, last touched 2026-08-07; the chunking constants are unchanged (`chunkSizeInSeconds = 60`, `flushIntervalInSeconds = 90`, `newFrameSyncDelaySeconds = 15`, `lossesThresholdFrames = 1000`).

**How it works** (unchanged from the prior audit, re-confirmed against current Mac source):
- `startRecording(device:codec:)` begins accumulating frames in memory (`currentFrames: [Data]`); each `addFrame(_:synced:)` call appends one Opus frame.
- Two timers drive chunking: `chunkTimer` fires every `chunkSizeInSeconds + newFrameSyncDelaySeconds` (75s) and creates a new WAL if the unsynced frame count crosses `lossesThresholdFrames` (10s worth, 1000 frames @ 100fps); `flushTimer` fires every `flushIntervalInSeconds + newFrameSyncDelaySeconds` (105s) and persists any `.memory`-storage WALs to disk.
- `createWalFromCurrentFrames()` builds a `WALEntry` (status `.miss`, storage `.memory`) and calls `writeFramesToDisk`, which appends `[uint32 little-endian length][frame bytes]` per frame to a `.bin` file, then promotes the entry to `.disk` and persists `wals.json` once the write completes (background thread, not blocking the main actor).
- On-disk file naming: `WALEntry.generateFileName()` → `audio_<device>_<codec>_<sampleRate>_<channel>_fs<samplesPerFrame>_<timerStart>.bin`, e.g. `audio_AA:BB:CC_opus_16000_1_fs160_1720000000.bin`.
- Metadata persistence: `wals.json` (all `WALEntry` records) plus an automatic `wals_backup.json` copy-before-overwrite, so a crash mid-write doesn't corrupt the index.
- SD-card and WiFi paths reuse the same `WALEntry`/file model but start from `createSdCardWal` (storage `.sdcard`) and fill in via `updateWalWithDownloadedData`.

**Windows status**: **Absent, unchanged.** No BLE device connection exists, so there is no frame source to buffer. No `.bin`-format file writer, no chunking timers, no `wals.json`-equivalent index anywhere in `desktop/windows/src` (re-confirmed via grep for `.bin`/`audio_.*fs`/WAL-shaped writers and for `WALEntry`/`wals.json`/`StorageSyncService`/`WifiSyncService` — zero matches).

**Value / notes**: High — this is the entire durability story for wearable-sourced conversations. Blocked entirely on BLE support (Phase 7, deferred; see the callout above re: the unverifiable `BUILD_PLAN.md` citation for the deferral itself — the deferral is corroborated by three other audit files regardless).

---

## Cloud upload (`POST /v2/sync-local-files`) + reconciliation

**What it is**: Once a WAL is on disk, it's uploaded to the backend for server-side decode + STT + conversation creation, with a job-based ack (200 done vs 202 queued+job_id) and background polling to resolve queued jobs to a terminal state.

**Where (Mac)**: `WAL/WALService.swift` (`syncToCloud()`, `uploadWalToCloud(_:)`), `WAL/WALCloudSyncLogic.swift` (pure state-transition logic), `WAL/WALSyncReconciler.swift` (polling), **`Services/APIClient/APIClient+Messages.swift:104` (`uploadLocalFilesV2`) and `:125` (`fetchSyncJobStatus`)** — corrected from the prior audit's `APIClient.swift:5495-5545`, which is now wrong: that monolithic file was split on 2026-07-16 (`c7ca348b04`) and is down to 1164 lines; the sync-upload functions moved to the dedicated extension file.

**How it works** (re-confirmed against current Mac source, logic unchanged):
- `syncToCloud()` iterates all WALs with `status == .miss && storage == .disk`, uploads each via multipart POST to `v2/sync-local-files`. A `syncRateLimited` API error aborts the batch early.
- Result handling (`WALCloudSyncLogic.applyUploadResult`): server `.done` → `status = .synced` immediately; server `.queued(jobId)` (HTTP 202) → `status = .uploaded`, `jobId` recorded. Never marks `.synced` without an explicit 200/202 ack.
- Reconciliation (`WALSyncReconciler.reconcileUploadedWals`): groups `.uploaded` WALs by `jobId`, does one `GET /v2/sync-local-files/{job_id}` per distinct job, applies `WALCloudSyncLogic.applyReconcileFetch` (`.transient` → retry later; `.notFound`/`.forbidden` → durable failure; `.ok`+`completed` → `.synced`; `.ok`+`failed`/`partial_failure` → revert to `.miss`).
- `scheduleReconcileRetryIfNeeded()` schedules one follow-up `syncToCloud()` 30s later for still-`.uploaded` WALs.
- `cleanupOldWals(olderThanDays: 7)` deletes `.synced` WALs older than the cutoff.

**Windows status**: **Absent, unchanged.** No upload target exists (no local WAL to upload). The endpoint `/v2/sync-local-files` is referenced only in `src/renderer/src/lib/omiApi.generated.ts` (generated OpenAPI client stub, `/v2/sync-local-files` and `/v2/sync-local-files/{job_id}` path entries at lines ~8550/8560/16333/16358) — never called anywhere in Windows application code (re-confirmed: `grep -rn "uploadLocalFilesV2\|sync-local-files"` outside the generated file returns nothing).

**Value / notes**: High, but strictly downstream of BLE support. The reconciler's dedup/retry/terminal-state design is a solid reference implementation to port as-is once Phase 7 lands.

---

## Storage sync (BLE SD-card pull)

**What it is**: When a wearable has been recording locally to its own flash/SD storage, this pulls the backlog off the device over BLE once reconnected.

**Where (Mac)**: `WAL/StorageSyncService.swift`.

**How it works**: Unchanged from the prior audit — `checkForStorageData()` queries the device's storage list; `startSync` proceeds only if `bytesToDownload >= minBytesToSync` (8000 bytes); transfer runs as a cancellable `Task` parsing BLE packets by size class; `stopSync()` still persists partial downloads; `finishSync` calls `walService.syncToCloud()` directly to avoid a concurrent-download race; `clearDeviceStorage()` frees device flash after a confirmed sync.

**Windows status**: **Absent, unchanged** — no BLE `DeviceConnection`/`DeviceProvider` equivalent exists at all in `src/main` or `src/renderer`.

**Value / notes**: Medium — matters for the "device was recording while the companion app wasn't around" scenario. Blocked on Phase 7.

---

## WiFi sync

**What it is**: A faster bulk-transfer alternative to BLE storage sync — the device stands up its own WiFi access point (SoftAP), the Mac connects directly, and audio backlog streams over TCP instead of BLE GATT.

**Where (Mac)**: `WAL/WifiSyncService.swift`; error/validation types in `Bluetooth/WifiSyncTypes.swift`. Both files still present, unchanged in structure.

**How it works**: Unchanged from the prior audit — credential handshake over BLE, SoftAP bring-up, status monitoring, a raw TCP socket to `192.168.4.1:12345`, length-prefixed frame parsing with a 5-minute hard cap, teardown-before-upload sequencing, and rolling transfer-speed tracking for UI display.

**Windows status**: **Absent, unchanged** — no WiFi-AP connection logic, no TCP device-transfer client, no WiFi credential setup UI.

**Value / notes**: Low relative to BLE storage sync — a speed optimization, not a standalone capability gap. Only worth building after BLE storage sync exists.

---

## Storage Sync UI

**What it is**: In-app surface showing device connection/battery status, sync progress, pending-WAL count badge, and manual BLE-Sync/WiFi-Sync/Stop controls.

**Where (Mac)**: `WAL/StorageSyncView.swift` (`StorageSyncView` full panel + `StorageSyncIndicator` compact toolbar badge).

**Windows status**: **Absent, unchanged** — no equivalent surface exists (nothing to show, since there's no WAL/device pipeline). Windows conversation-sync UI (`Conversations.tsx`) shows sync state per-conversation (`pending`/`failed`/`unconfirmed`/`done` with a manual retry action calling `resyncConversation`), but that's for the finished-conversation outbox, not raw-audio backlog.

**Value / notes**: Low standalone — trivially follows once the underlying services exist.

---

## Windows' own offline resilience (realtime STT path) — comparison point, not a Mac feature

Not a literal Mac→Windows gap (Mac's WAL exists for a *different* audio source — BLE device — that Windows doesn't have), but this is the closest analogous risk on Windows, and the prior audit's single paragraph on it was both stale and too coarse-grained: **resilience now differs materially by capture lane**, and the lane the prior audit implicitly described (any drop is fatal, no reconnect, no fallback) is only still true for two of the three lanes.

**The silence-starvation fix (was WIRING-AUDIT C1), confirmed present**: `omiListen.ts:97-144` (commit `5b5ef25b81`, 2026-07-13). The backend closes a conversation-mode `/v4/listen` socket after 90s with no received data; Windows' renderer-side VAD gate drops silence before feeding, so a quiet stretch used to silently starve the socket. `serviceConversationSocket` now runs every 15s (`SERVICE_CHECK_MS`) and, for `mode === 'conversation'` sockets only: (a) force-closes (so the client reconnects) any socket that hasn't delivered *anything* — not even a ping — for 60s (`WATCHDOG_STALE_MS`, a dead/half-open-TCP watchdog), and (b) otherwise sends a `b'\x00'*320` silence keepalive (10ms of 16kHz mono silence, the documented contract frame) once 30s (`KEEPALIVE_IDLE_MS`) has passed since the last real audio feed. Keepalives reset the backend's inactivity timer without counting as fed audio in `listenStats`, so the soak/VAD-gate harnesses still see a flat byte delta across real silence.

**The no-reconnect fix (was WIRING-AUDIT C2), confirmed present, mic-only**: `liveMicSession.ts` + `liveRescue.ts` (commit `445967cf24`, 2026-07-13). The always-on continuous mic session — the one that owns backend-side conversation creation for plain (non-screen-session) recording — now:
- Carries a client-generated `clientConversationId` per conversation and resends it on every reconnect, so the backend resumes the SAME in-progress conversation (`transcribe.py` keys on `client_conversation_id`) instead of stranding it.
- Reconnects with capped exponential backoff (2s→4s→8s→16s→32s, jittered, up to `MAX_RECONNECT_ATTEMPTS = 10`, ~operationally a few minutes of budget) on any retryable drop; a 429 backs off from a 5s floor instead of hammering a just-rate-limited server.
- Retains every backend segment in memory (`createSegmentRetainer`, upserting refinements by id) for the life of the current conversation.
- On reconnect exhaustion (an extended outage), pushes the retained segments through `syncLocalConversation` as an `'unconfirmed'` from-segments row — `'unconfirmed'` specifically so the outbox's dedupe-against-cloud check runs first and adopts a conversation the backend managed to finalize server-side before concluding it needs to create a new one.
- Quota/entitlement/sign-in errors are treated as terminal (no point burning the reconnect budget on a wall that won't move) and surface immediately instead of being retried.

**What is still NOT covered by the fix — and where the old audit's description remains accurate**: two other capture lanes stream over the same main-process listen socket infrastructure but do not use `liveMicSession`'s reconnect logic at all:
- **Manual screen-session recording** (`useRecorder.ts`, mode `'transcribe'` for both mic and system-audio lanes when "record screen" is active): `onError: (e) => console.error(...)` — a mid-session drop is logged and nothing else happens. Whatever was captured before the drop is still retained via `segmentRetention.ts`'s `SegmentStore` and does get synced via from-segments when the user stops the session, but nothing spoken after the drop is recovered, and the user gets no visible signal that transcription silently stopped.
- **Meeting auto-capture's system-audio lane** (`meetingSession.ts`, `startLane('system', 'transcribe')`): same pattern — `onError` calls back to the caller (`args.onError`) which the meeting UI surfaces as a toast, but there is no reconnect attempt for that socket. (The meeting's *mic* lane, when delegated to the continuous session per the C6 double-session fix, does inherit `liveMicSession`'s resilience — but only because it's the same session, not because `meetingSession.ts` itself added reconnect logic.)

**Still open regardless of lane — app-crash-mid-recording durability**: none of the three lanes persist raw retained segments to SQLite until a conversation finalizes (silence timeout, manual stop, backend boundary event, or the reconnect-exhaustion rescue). A full process crash mid-conversation loses whatever was only in the in-memory `SegmentRetainer`/`SegmentStore`, on every lane, today. This is listed as still-deferred in `WIRING-AUDIT.md`'s "Deferred, still open" line ("app-crash-mid-recording segment durability (Stream 4)") and this pass found no evidence it has since been addressed (no relevant commits in `git log` for `liveMicSession.ts`, `liveRescue.ts`, or `segmentRetention.ts` since 2026-07-30).

**Once segments do arrive**: `segmentRetention.ts`/`liveRescue.ts` keep them safely in memory for the life of the session, and `conversationSync.ts`'s outbox (CAS claim via `claimConversationForPosting`, ambiguous/definite failure classification via `classifyPostError`, unconfirmed-dedupe via a `/v1/conversations?limit=30` list match on `started_at`/`finished_at` with a 2s tolerance) gives strong resilience for getting a completed conversation's transcript to the cloud — this part of the prior audit's description held up unchanged on re-verification, and as of 2026-07-13 the retry now also runs on an app-lifetime 60s timer (`outboxSweep.ts`, started from `App.tsx` at sign-in) rather than only when the Conversations page happens to be mounted, closing the specific gap WIRING-AUDIT flagged as a Major ("A PTT-only user's failed sync is wedged for the whole session").

**Value / notes**: Medium, revised down from the prior pass's implicit framing. The continuous-mic lane — almost certainly the highest-volume capture path — is now genuinely resilient to network blips and short backend outages, arguably comparable to Mac's WAL reconciler in rigor for that lane. The remaining exposure is narrower than the old audit implied: (1) screen-session and meeting system-audio lanes still have zero reconnect, and (2) no lane survives a hard process crash mid-conversation. Neither is a BLE-shaped problem and neither requires Phase 7 to fix — both are addressable with the same reconnect/rescue pattern already proven out in `liveMicSession.ts`/`liveRescue.ts`.

## Spotted outside my scope

- `src/main/integrations/syncState.ts` / `syncStateLogic.ts` is Google Gmail/Calendar integration sync-state (processed-ID tracking, bounded to 1000 IDs), unrelated to audio/WAL — reconfirmed this pass, still not relevant to this audit's scope despite the "sync" naming.
- Windows' conversation outbox (`outbox.ts`) still documents (code comment, unchanged) that **prod does not honor `client_session_id`** for `/v1/conversations/from-segments`, "verified live 2026-07-10." `WIRING-AUDIT.md`'s Minor section already flags this as possibly stale itself (backend allegedly shipped uuid5 idempotency 2026-06-29, i.e. *before* the "verified live" date — "probably deploy lag; re-verify before trusting either claim"). This pass did not have backend access to re-verify either claim; flagging again for whichever audit covers backend API contracts, since the discrepancy is unresolved on both sides five weeks later.
- Mac's `WALService` fallback/telemetry: re-confirmed this pass, none of the WAL sync paths call `DesktopDiagnosticsManager.recordFallback` despite containing several fail-open/retry/mode-change branches — still worth a note for whoever audits fallback-telemetry compliance, though that's a Mac-side observation, not a parity gap.
- `WIRING-AUDIT.md` lists reconnect/BYOK-on-listen-socket as an "Unassigned high-priority" item as of 2026-07-13; BYOK headers were in fact separately shipped two days later (`ce2b22233e`, 2026-07-15, `byokSttHeaders` in `omiListen.ts:31-40`) — worth flagging to whichever audit covers BYOK/transcription specifically, since this file's scope is sync/offline, not auth headers, but it's adjacent enough to the same file that it's easy to miss.
