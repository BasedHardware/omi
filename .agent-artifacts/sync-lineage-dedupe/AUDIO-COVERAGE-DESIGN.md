# Round 3: source-frame audio coverage (2026-10-03)

File:line evidence below was inspected at `628e1d7569`; subsequent main integration can shift line numbers. The source identity protocol, not those wall-clock offsets, is the consumer contract.

## Decision and release boundary

Do not suppress a WAL using text, `created_at`, wall-clock overlap, a connected socket, or `send()` success. Today's ordinary shipped-client path has no shared frame identity at the server; a server-only rollout cannot meet the measured doubling gate. Implement a dormant server consumer of the EXISTING opt-in S1 source-position signal. Join authenticated same-origin/same-device live receipts to uploaded WAL claims by `(capture_root, clock_epoch, mono channel, rate_hz, source frame ordinal)`, then remove only positively proven live-received frames before VAD/STT. Missing, malformed, conflicting, unsupported, or out-of-bounds evidence retains the original audio. No Flutter changes or S1 runtime enablement in this round.

## File:line evidence, phone and device

- `app/lib/services/audio_sources/ble_device_source.dart:6-10,30-43`: BLE carries packet id/index in three bytes; BOTH the WAL payload and live socket strip that header. The packet key stays phone-local; it is not in uploaded audio.
- `app/lib/services/capture/capture_controller.dart:1771-1800`: the same frame goes to WAL and socket. Pendant frames deliberately are NOT marked synced by transport send: that is not transcript confirmation.
- `app/lib/services/wals/local_wal_sync.dart:1267-1303`: in-memory `_frameSynced` identifies WHICH frames, but starts false; the S1 path separately allocates monotone frame ordinals and clock epochs, with restored WAL high-water marks.
- `app/lib/services/wals/local_wal_sync.dart:571-683`: whole chunks are retained when any frame is unsynced; only a contiguous `syncedFrameOffset` PREFIX is persisted, not the bitmap. Chunk accumulation must not be mistaken for a full received/missed ledger.
- `app/lib/services/wals/local_wal_sync.dart:702-714`: disk WAL is repeated little-endian length + payload, without BLE key, frame timestamp, or received bit. `wal.dart:430` puts phone wall-clock start in filename.
- `app/lib/services/capture/capture_controller.dart:118-120`: S1 root is disabled unless the mobile build has `CAPTURE_EVIDENCE_V1_DARK_WRITE=true`.
- `app/lib/services/sockets/transcription_service.dart:238-255`: when enabled, source root/epoch/ordinal control precedes exactly its binary payload on the ordered socket; no server ACK exists in the normal transport path.
- `app/lib/services/wals/local_wal_sync.dart:55-82,1480-1484,1722-1726`: S1 upload claims map each filename to root/epoch/start/count/rate/codec/channel in bounded `X-Omi-Capture-Evidence`. Both automatic and manual uploads carry it when enabled.

## File:line evidence, server

- `backend/routers/listen/receiver.py:1643-1704`: successful decode, not client send, advances the server sample cursor. Optional source claims bind to the next binary message and map source ordinals to those decoded samples.
- `backend/utils/audio_timeline.py:195-249`: `CaptureTimeline.next_sample` counts ONLY received/decoded PCM on one socket. A missed frame does not advance it; reconnect restarts it. Thus neither sample cursor nor arrival wall time alone identifies a WAL frame.
- `backend/routers/listen/receiver.py:397,464-468`: `_capture_start_sample` is server-local provider mapping; it is not a shared WAL coordinate.
- `backend/utils/capture_evidence.py:197-215,226-311`: validates source controls and persists bounded positive frame runs, detecting conflicts/compaction. `incomplete` is not proof of absent frames; only retained positive runs can justify removing audio. Reject nonzero conflicts entirely.
- `backend/routers/listen/transcripts.py:427-440`: existing opt-in snapshot piggybacks received runs for the owning generation. `backend/database/conversations.py:2856-2857` replaces the snapshot, so lost/overwritten runs reduce recall, never justify extra removal.
- `backend/routers/sync.py:935-938,1247,1500,1930,2100`: same optional file claims already survive admission, inline execution and Cloud Tasks execution; currently gated by S1 dark-write.
- `backend/utils/sync/files.py:59-88,180-203,252-297`: length-prefixed frames decode in original order, and optional `decoded_frame_samples` gives exact WAV sample offsets for each ordinal (including a decoded prefix of corrupt input).
- `backend/utils/sync/pipeline.py:2023-2026,2101-2118`: existing mapping can bridge WAL source ordinals to decoded samples. `:974-1008` projects VAD offsets from the filename's phone-clock start, not the live server clock.
- `backend/routers/listen/transcripts.py:880-887`: legacy live start = first socket arrival + provider offset; it can be backdated and differs from the WAL's phone-clock start. There is no universally valid constant offset or `created_at` boundary.

## Consumer specification (B)

New `SYNC_WAL_AUDIO_COVERAGE_ENABLED`: default ON, explicit non-on token OFF; additionally require existing lineage cohort and recording-origin proof. Do not enable S1 dark-write as part of this PR. When S1 claims are absent, execute the original audio path without added lookup/decode mapping or coverage log.

Reuse the existing bounded indexed lineage lookup, projecting `capture_evidence` only for the flagged consumer. Query the WAL's wall envelope with a 1-hour candidate-discovery allowance on both sides (NOT an identity rule), at most 8+1 generation rows plus the existing bounded origin query. A truncated/degraded lookup abstains. Validate source/device/lock/deletion provenance before using receipts; never compare another device or root. Positive source runs can be used from an incomplete envelope only when structurally valid and conflicts=0; absent/evicted runs remain novel. Never use sync-derived receipts as live proof. No new serving query shape or index.

For each decoded WAV, subtract verified live frame intervals from `[source_frame_start, source_frame_start + decoded_frame_count)`. Decode all Opus frames first so predictor state is preserved. Split remaining intervals into separate WAVs BEFORE VAD, without concatenating gaps or retiming later audio. Each filename remains original phone-clock start plus retained sample offset/rate; derivative maps adjust source start and sample offsets. Add at most 250ms of whole-frame context per side (zero if the next whole frame exceeds the bound); never bridge a large covered hole. Cap 32 output intervals per file; if exceeded, retain the whole file. All-covered files legitimately yield no STT/enrichment; report received-audio suppression separately from expected silence. Preserve retry/ledger semantics and cleanup ownership. Log bounded counts/seconds/method only, never root/UID/filename/text.

## Smallest client change / David's decision

For a new capture, the existing Dart implementation already supplies the required exact signal: enable `--dart-define=CAPTURE_EVIDENCE_V1_DARK_WRITE=true` in an app build (0 Dart source lines), and separately admit S1 on backend-listen plus sync admission/worker services. Existing WALs without root/ordinal cannot be repaired retroactively. The phone does NOT need to infer server receipt or send a guessed bitmap: receipt comes from server-observed positive runs. A standalone missed-frame bitmap would require a new server ACK protocol plus persistence of the full bitmap at `local_wal_sync.dart:586-660,1284-1303` and upload encoding at `:55-82`; do not implement that weaker/incomplete transport inference here. Future high-recall work may need a durable ACK/range ledger because current S1 snapshots are bounded/replaceable; no production gate claim follows from this dormant consumer.

## Consequences on the supplied measured shape

- Speech before live began: no positive live ordinal coverage, so retained, irrespective of wall skew.
- Audio the socket missed / decode failed: no receipt, retained. Pre-live and missed audio are the sync value this design preserves.
- Same capture already received but transcribed poorly (e.g. English rendered as Vietnamese): suppressed by this rule even though a second STT might improve it. Receipt does not prove transcript quality; this loss of re-transcription value is an explicit product tradeoff, not a false claim that all 52% new-value speech is retained.
- Separate legitimate second utterance: different ordinal/root, retained even if identical wording. Clock disagreement of +40s/+20min/+1735s cannot create identity; discovery bounds or missing evidence only miss repeats.
- Today's shipped/default-OFF S1 apps: no audio suppression; <=10% gate remains blocked pending David's app/coverage decision and coordinator measurement.

## Follow-through (C–G)

Remove unauthenticated lexical matching from the production default path; retain a pure conservative diagnostic/fallback only when the caller supplies independently verified FULL incoming-capture coverage. Bound raw live input and candidate interval search BEFORE tokenization/sort. Exact sync retries remain separate from lexical identity.

Replace creation-time overlap choice. Use proven source-frame ownership when available; without that, a same-origin compatible stamp among the strict matches is a safe routing fallback but not a dedupe proof. If no such stamp exists and ownership is ambiguous, defer/fail retryably rather than minting a duplicate or arbitrarily choosing from a clock already known to drift. `started_at` in the legacy path is not a trustworthy shared audio boundary; report this limitation.

Gate overlap and additional lineage diagnostics independently. All ROUND-3 behavior flags OFF must match the frozen main path in persisted payloads, return values, enrichment and log formatting; document any diagnostic-only differences that cannot be proved. Replay uses successive 2–5-segment intakes and a pure JSON source-frame coverage description. Run saved-row/audio-consumer proofs, mutation checks, pinned formatter/typecheck, metadata/preflight and final pushed-head full CI. Do not widen, deploy, alter smart-merge files, edit Flutter, or author production queries through delegated work.
