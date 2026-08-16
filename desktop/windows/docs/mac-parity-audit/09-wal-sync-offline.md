# Mac→Windows Parity Audit — WAL / Sync / Offline

> Scope: write-ahead log (raw audio buffering) for BLE wearable devices, storage sync (BLE SD-card pull), WiFi sync, and cloud-sync reconciliation. Windows baseline checked: `src/renderer/src/lib/sync/` (conversation outbox), `src/main/integrations/syncState.ts` + `syncStateLogic.ts` (Google integrations sync state — unrelated to audio), `src/main/ipc/omiListen.ts` (realtime STT WebSocket session).

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| WAL raw-audio buffering (BLE device frames) | `WAL/WALService.swift`, `OmiWAL/WALModel.swift` | **Absent** | H |
| WAL `.bin` on-disk format + filename convention | `OmiWAL/WALModel.swift` (`generateFileName`, `WALSyncUploadFileName`) | **Absent** | M |
| Cloud upload via `POST /v2/sync-local-files` | `WAL/WALService.swift` (`uploadWalToCloud`), `APIClient.swift` | **Absent** | H |
| Upload reconciliation (poll job status, dedupe, retry) | `WAL/WALSyncReconciler.swift`, `WAL/WALCloudSyncLogic.swift` | **Absent** | M |
| BLE SD-card storage sync (pull backlog off device flash) | `WAL/StorageSyncService.swift` | **Absent** | M |
| WiFi sync (device SoftAP + TCP bulk transfer) | `WAL/WifiSyncService.swift`, `Bluetooth/WifiSyncTypes.swift` | **Absent** | L |
| Storage Sync UI (progress, pending badge, error/retry) | `WAL/StorageSyncView.swift` | **Absent** | L |
| Offline resilience for Windows' own realtime audio path | (N/A — different architecture) | **Weaker** (no disk fallback if WS drops mid-session) | M |
| Conversation-record (post-STT) sync resilience — Windows' analogous "WAL" | (N/A — Mac has no equivalent; Mac WALs raw audio, not finished conversations) | **Present**, arguably stronger than Mac for this narrower case | — |

## Spotted-first: architectural framing

Mac's WAL and Windows' "conversation sync" solve **different problems** and are not directly interchangeable:

- **Mac WAL** buffers **raw Opus audio frames** streamed continuously off a BLE wearable (Omi pendant), because the pendant has no reliable network of its own and the Mac may itself be offline/asleep/out of Bluetooth range for stretches. The unit of durability is a chunk of undecoded audio; the backend does STT server-side after upload.
- **Windows conversation sync** (`src/renderer/src/lib/sync/outbox.ts`, `conversationSync.ts`) buffers **already-transcribed conversation records** (mic + system-audio segments produced by Windows' own local realtime STT pipeline over `/v4/listen`), and reliably POSTs the finished conversation once via `/v1/conversations/from-segments` with a CAS-based outbox and unconfirmed-dedupe protocol. There is no raw audio in this path at all — audio never touches disk, only text segments do (in SQLite, via `window.omi.updateLocalConversationSync`).

This means: Windows has **no BLE wearable device support at all** (Phase 7 of `BUILD_PLAN.md` is explicitly deferred — "**DEFERRED (Chris 2026-07-10): skip this phase for now; revisit after the rest ships**"), so the entire Mac WAL/StorageSync/WifiSync subsystem has **zero Windows counterpart**, not a weaker one. `BUILD_PLAN.md:228` already earmarks the exact fix: "Offline audio: buffer wearable frames in the WAL `.bin` format ... and upload via `POST /v2/sync-local-files` — this is exactly the pipeline that endpoint was built for (unlike Phase 3's screen sessions). Reuse the Flutter WAL flow as the contract reference."

---

## WAL raw-audio buffering

**What it is**: A local write-ahead log that captures every audio frame coming off a connected BLE device in near-real-time, chunked into ~60s segments, so that no audio is lost if the network, backend, or app itself goes away mid-stream.

**Where (Mac)**: `desktop/macos/Desktop/Sources/WAL/WALService.swift` (singleton `@MainActor` service); model in `desktop/macos/Desktop/Sources/OmiWAL/WALModel.swift`.

**How it works**:
- `startRecording(device:codec:)` begins accumulating frames in memory (`currentFrames: [Data]`); each `addFrame(_:synced:)` call appends one Opus frame.
- Two timers drive chunking: `chunkTimer` fires every `chunkSizeInSeconds + newFrameSyncDelaySeconds` (75s) and creates a new WAL if the unsynced frame count crosses `lossesThresholdFrames` (10s worth, 1000 frames @ 100fps); `flushTimer` fires every `flushIntervalInSeconds + newFrameSyncDelaySeconds` (105s) and persists any `.memory`-storage WALs to disk.
- `createWalFromCurrentFrames()` builds a `WALEntry` (status `.miss`, storage `.memory`) and calls `writeFramesToDisk`, which appends `[uint32 little-endian length][frame bytes]` per frame to a `.bin` file, then promotes the entry to `.disk` and persists `wals.json` once the write completes (background thread, not blocking the main actor).
- On-disk file naming: `WALEntry.generateFileName()` → `audio_<device>_<codec>_<sampleRate>_<channel>_fs<samplesPerFrame>_<timerStart>.bin`, e.g. `audio_AA:BB:CC_opus_16000_1_fs160_1720000000.bin`. `samplesPerFrame` is the Opus decoder frame size in *samples* (not encoded byte length) — a historical `_fsN`-as-byte-length bug is corrected on upload via `WALSyncUploadFileName.normalizedForUpload`.
- Metadata persistence: `wals.json` (all `WALEntry` records) plus an automatic `wals_backup.json` copy-before-overwrite, so a crash mid-write doesn't corrupt the index; `loadWals()` falls back to the backup file if the primary fails to decode.
- SD-card and WiFi paths reuse the same `WALEntry`/file model but start from `createSdCardWal` (storage `.sdcard`) and fill in via `updateWalWithDownloadedData`, which writes frames synchronously (`writeFramesToDiskAndWait`) so the caller can chain straight into `syncToCloud()`.

**Windows status**: **Absent.** No BLE device connection exists, so there is no frame source to buffer. No `.bin`-format file writer, no chunking timers, no `wals.json`-equivalent index anywhere in `desktop/windows/src` (confirmed via grep for `.bin`/`audio_.*fs`/WAL-shaped writers — zero matches).

**Value / notes**: High — this is the entire durability story for wearable-sourced conversations. Blocked entirely on BLE support (Phase 7). `BUILD_PLAN.md:227-228` already specifies porting this exact model from `app/lib/services/wals/wal_service.dart` (Flutter) when that phase resumes.

---

## Cloud upload (`POST /v2/sync-local-files`) + reconciliation

**What it is**: Once a WAL is on disk, it's uploaded to the backend for server-side decode + STT + conversation creation, with a job-based ack (200 done vs 202 queued+job_id) and background polling to resolve queued jobs to a terminal state.

**Where (Mac)**: `WAL/WALService.swift` (`syncToCloud()`, `uploadWalToCloud(_:)`), `WAL/WALCloudSyncLogic.swift` (pure state-transition logic), `WAL/WALSyncReconciler.swift` (polling), `APIClient.swift:5495-5545` (`uploadLocalFilesV2`, `fetchSyncJobStatus`).

**How it works**:
- `syncToCloud()` iterates all WALs with `status == .miss && storage == .disk`, uploads each via multipart POST to `v2/sync-local-files` (filename-normalized per above). A `syncRateLimited` API error aborts the batch early (leaves remaining WALs `.miss` for a later pass) rather than hammering the endpoint.
- Result handling (`WALCloudSyncLogic.applyUploadResult`): server `.done` → `status = .synced` immediately; server `.queued(jobId)` (HTTP 202) → `status = .uploaded`, `jobId` recorded, `uploadedAt` stamped. **Never marks `.synced` without an explicit 200/202 ack** (comment is explicit about this — no optimistic completion).
- Reconciliation (`WALSyncReconciler.reconcileUploadedWals`): groups all `.uploaded` WALs by `jobId`, does one `GET /v2/sync-local-files/{job_id}` per distinct job, and applies `WALCloudSyncLogic.applyReconcileFetch`:
  - `.transient` (network hiccup) → no change, retried later.
  - `.notFound`/`.forbidden` → durable failure; WAL reverts to `.miss` (if the local file still exists, for re-upload) or `.corrupted` (if the file is gone) — `.forbidden` is called out as distinct from a retryable transport error because refreshing auth already happened upstream, so a 403 here means "will never succeed," not "try again."
  - `.ok` + terminal status `completed` → `.synced`.
  - `.ok` + terminal status `failed`/`partial_failure` → reverts to `.miss` for re-upload; the comment notes the backend dedupes re-uploaded successful segments by conversation/timestamp, so blind re-upload of a partial failure is safe.
- If any WALs remain `.uploaded` after the immediate reconcile pass (job still queued/processing server-side), `scheduleReconcileRetryIfNeeded()` schedules exactly one follow-up `syncToCloud()` 30s later so in-flight jobs eventually resolve without a caller-driven poll loop.
- Cleanup: `cleanupOldWals(olderThanDays: 7)` deletes `.synced` WALs (and their backing files) older than the cutoff, to bound local disk growth.

**Windows status**: **Absent.** No upload target exists (no local WAL to upload). The endpoint `/v2/sync-local-files` is referenced only in `src/renderer/src/lib/omiApi.generated.ts` (generated OpenAPI client stub) — never called anywhere in Windows application code.

**Value / notes**: High, but strictly downstream of BLE support — there's nothing to reconcile until frames exist to buffer. The reconciler's dedup/retry/terminal-state design (especially the `.forbidden` vs `.transient` distinction and the 30s follow-up poll) is a solid reference implementation to port as-is once Phase 7 lands.

---

## Storage sync (BLE SD-card pull)

**What it is**: When a wearable has been recording locally to its own flash/SD storage (e.g. it was out of BLE range, or the app wasn't running), this pulls the backlog off the device over BLE once reconnected.

**Where (Mac)**: `WAL/StorageSyncService.swift`.

**How it works**:
- `checkForStorageData()` queries the device's storage list (`[totalBytes, currentOffset]`) via the active `DeviceConnection`.
- `startSync(device:codec:)` only proceeds if `bytesToDownload >= minBytesToSync` (10s worth of audio, 8000 bytes) — avoids a sync cycle for negligible backlog. Creates a `.sdcard`-storage `WALEntry` via `WALService.createSdCardWal`.
- Transfer runs as a cancellable `Task`, sending a `StorageCommand.read` BLE write then consuming a stream of packets (`connection.getStorageStream()`). Packet parsing branches on size: `standardPacketSize` (83B: 3-byte header + 80B frame), `packedPacketSize` (440B: multiple length-prefixed frames), or a variable-size fallback (`parseFramesFromData`, handles padding to block boundaries).
- Every frame is validated against `OpusFrameValidator.validTocBytes` before being kept — corrupt/misaligned frames are silently dropped rather than corrupting the WAL.
- `stopSync()` (user-cancel or app teardown) still persists whatever was downloaded so far via `updateWalWithDownloadedData`, so a partial BLE transfer isn't wasted.
- On completion (`finishSync`), the WAL is finalized on disk and `walService.syncToCloud()` is invoked directly (before releasing `isSyncing`), specifically to avoid a race where a second concurrent BLE download could see `isSyncing == false` and skip its own cloud sync.
- `clearDeviceStorage()` sends a `StorageCommand.clear` write to free device flash after a confirmed successful sync.

**Windows status**: **Absent** — no BLE `DeviceConnection`/`DeviceProvider` equivalent exists at all in `src/main` or `src/renderer`.

**Value / notes**: Medium — matters specifically for the "device was recording while the companion app wasn't around" scenario, which is common for a wearable used across multiple days/machines. Blocked on Phase 7.

---

## WiFi sync

**What it is**: A faster bulk-transfer alternative to BLE storage sync for devices that support WiFi — the device stands up its own WiFi access point (SoftAP), the Mac connects to it directly, and audio backlog streams over TCP instead of the much slower BLE GATT link.

**Where (Mac)**: `WAL/WifiSyncService.swift`; error/validation types in `Bluetooth/WifiSyncTypes.swift`.

**How it works**:
- Multi-step handshake, all over the existing BLE connection first: (1) optionally push WiFi credentials to the device (`setupWifiSync(ssid:password:)`, gated by `WifiCredentialsValidator` — SSID ≤32 bytes, password 8–63 bytes UTF-8); (2) `startWifiSync()` tells the device to bring its AP up; (3) `startStatusMonitoring` subscribes to a BLE status-code stream (`WifiStatus`: `off/shutdown/on/connecting/connected/tcpConnected`) rendered via `displayName`; (4) `waitForDeviceReady` polls `status.isActive` with a 60s timeout; (5) once active, fetch storage list + send `StorageCommand.read` over BLE exactly as in `StorageSyncService`; (6) open a raw `NWConnection` TCP socket to the device's fixed SoftAP IP `192.168.4.1:12345`; (7) `receiveData()` loops on `NWConnection.receive`, parsing length-prefixed Opus frames from the byte stream with block-boundary padding logic near-identical to the BLE path's `parseFramesFromData`, with a 5-minute (`transferTimeout`) hard cap; (8) `finishSync()` tears the SoftAP down first (`cleanup()`, which calls `connection.stopWifiSync()` over BLE) *before* calling `syncToCloud()`, specifically so the Mac regains its normal internet route before trying to upload.
- Transfer-speed tracking: `speedSamples` keeps a rolling 3-second window of `(timestamp, bytes)` samples to compute `transferSpeed` for UI display.
- Every failure path routes through `cleanup()` (cancel tasks, close TCP, tell device to stop WiFi, reset all `@Published` state) so a failed WiFi sync always leaves the device and app in a consistent recoverable state rather than stuck mid-transfer.

**Windows status**: **Absent** — no WiFi-AP connection logic, no TCP device-transfer client, no WiFi credential setup UI.

**Value / notes**: Low relative to BLE storage sync — it's a speed optimization for large backlogs, not a capability gap on its own (BLE storage sync alone already covers correctness). Only worth building after BLE storage sync exists and backlog-size telemetry shows BLE transfer time is actually a user complaint.

---

## Storage Sync UI

**What it is**: In-app surface showing device connection/battery status, sync progress (bytes, speed, ETA), pending-WAL count badge, and manual BLE-Sync/WiFi-Sync/Stop controls.

**Where (Mac)**: `WAL/StorageSyncView.swift` (`StorageSyncView` full panel + `StorageSyncIndicator` compact toolbar badge).

**How it works**: Pure SwiftUI observing `StorageSyncService`, `WifiSyncService`, `WALService`, and `DeviceProvider` as `@ObservedObject`s — no independent state. Shows a progress bar (`progress.percentComplete`), formatted byte counts/speed/ETA, a WiFi-specific status line during WiFi transfers, and a dismissible error banner. The compact `StorageSyncIndicator` shows either a spinner+percent while syncing or a pending-count badge (`walService.pendingWals.count`) when idle, meant for a toolbar/header.

**Windows status**: **Absent** — no equivalent surface exists (nothing to show, since there's no WAL/device pipeline). Windows conversation-sync UI (in `Conversations.tsx`) shows sync state per-conversation (`pending`/`failed`/`unconfirmed`/`done` with a manual retry action) but that's for the finished-conversation outbox, not raw-audio backlog.

**Value / notes**: Low standalone — trivially follows once the underlying services exist.

---

## Windows' own offline resilience (realtime STT path) — comparison point, not a Mac feature

Not a literal Mac→Windows gap (Mac's WAL exists for a *different* audio source — BLE device — that Windows doesn't have), but worth flagging as the closest analogous risk on Windows: Windows' own mic/system-audio capture streams PCM over a WebSocket to `/v4/listen` in real time (`src/main/ipc/omiListen.ts`). If that WebSocket drops **after** reaching `OPEN`:
- `feedSession()` only buffers audio while `readyState === CONNECTING` (a small bounded pre-handshake buffer, `PCM_PENDING_MAX_BYTES`, oldest-dropped-first). Once `OPEN`, audio is sent with a bare `ws.send(pcm)` and no fallback path — if the socket dies mid-send or the backend becomes unreachable mid-session, in-flight/subsequent audio is not retried or persisted to disk; it's simply lost until (if) the caller establishes a new session.
- `killSession`/`ws.on('close', ...)` just emits a `'closed'` event and drops any pending buffer — there's no automatic reconnect-and-resume for a live conversation/screen session.
- The one exception is PTT: a hold released **before** its socket reaches `OPEN` falls back to batch-transcribing the renderer's locally-retained raw buffer (comment in `omiListen.ts:159-164`) — but this only covers the connect-race window, not a mid-session drop.
- Once segments *do* arrive, `segmentRetention.ts` keeps them safely in memory for the life of the session, and `conversationSync.ts`'s outbox (CAS claim, ambiguous/definite failure classification, unconfirmed-dedupe via `/v1/conversations` list match) gives strong resilience for **getting a completed conversation's transcript to the cloud** — arguably comparable in rigor to Mac's WAL reconciler, just for a different unit of data (finished transcript vs raw audio) and only after a session ends successfully enough to produce segments.

**Value / notes**: Medium. If backend connectivity drops mid-meeting on Windows, the audio for that gap is unrecoverable (no local raw-audio fallback recording), whereas Mac's WAL is specifically designed to survive exactly this failure mode for its BLE audio source. This is an architectural difference (Windows has no on-device recording buffer at all for its live-capture path — Mac's WAL is unique to the BLE pendant, not the Mac's own mic capture) rather than a strict regression, but it's the nearest thing to a Windows-side "offline audio loss" risk in this problem space.

## Spotted outside my scope

- `src/main/integrations/syncState.ts` / `syncStateLogic.ts` is Google Gmail/Calendar integration sync-state (processed-ID tracking, bounded to 1000 IDs), unrelated to audio/WAL — confirmed not relevant to this audit's scope despite the "sync" naming; flagging in case another area's audit conflates it.
- Windows' conversation outbox (`outbox.ts`/`conversationSync.ts`) explicitly documents (code comment) that **prod does not honor `client_session_id`** for `/v1/conversations/from-segments`, making blind retries duplicate conversations — this drove the CAS+dedupe design there. Worth flagging to whichever audit covers backend API parity/contracts, since it's a backend behavior gap, not a client one.
- Mac's `WALService` fallback/telemetry: none of the WAL sync paths call `DesktopDiagnosticsManager.recordFallback` despite containing several fail-open/retry/mode-change branches (rate-limit abort, reconcile revert-to-miss, forbidden-job handling) — worth a note for whoever audits fallback-telemetry compliance against the root `AGENTS.md` contract, though that's a Mac-side observation, not a parity gap.
