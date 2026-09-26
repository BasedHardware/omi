# Parakeet final-pass shadow (phase 1)

The streaming transcript remains the sole record. Live pusher WebSocket
finalization runs `finalize_persisted_conversation` on the standalone pusher
GKE pod via its pusher router; the durable Cloud Tasks fallback runs that same function on the
backend-sync Cloud Run host. The listen WebSocket itself dispatches these
finalization paths; it does not run the finalizer. After a finalization job owns
its lease, `finalizer.py` schedules a best-effort shadow pass in the *same
process* before `process_conversation`. The finalizer never awaits audio,
Parakeet, Redis, or the comparison write. Orderly shutdown cancels the tracked
coroutine, but an already running thread can continue until process exit. A
killed pod or Cloud Run revision can lose that in-flight work.
There is no shadow retry, so the result document can remain absent. Canonical
finalization remains durable and independent. Do not enable shadow on Cloud Run
until it has a separate durable dispatch. Two process-local slots bound
concurrency, and a shared Redis Lua reservation caps aggregate audio
milliseconds by UTC day. Redis failure denies the pass. The default cap is
zero.

## Controls

`TRANSCRIPTION_SHADOW_ENABLED` defaults false. `TRANSCRIPTION_SHADOW_KILL_SWITCH`
blocks admission even when enabled. `TRANSCRIPTION_SHADOW_UID_ALLOWLIST` is a
comma-separated exact UID allowlist; otherwise a stable UID hash is compared
with `TRANSCRIPTION_SHADOW_PERCENT` (default 0). The shared daily cap is
`TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS` (default 0). All five controls are
declared off in the dev listen/pusher values and dev backend-sync runtime
manifest. No production values change. `TRANSCRIPTION_SHADOW_UPLOAD_GRACE_SECONDS`
defaults 70 so the pusher has time to flush its 60-second audio batch.
`TRANSCRIPTION_SHADOW_TIMEOUT_SECONDS` defaults 600; provider calls are also
bounded by the existing Parakeet client timeout. A worker checks the deadline
between slices. Background jobs are cancelled on orderly process shutdown.

Only conversations with `private_cloud_sync_enabled` and registered
`audio_files` qualify. The worker reads only chunk timestamps registered in
those files. Each chunk is decoded and clipped by its own timestamp; the dense
playback MP3 and the potentially drifting live `started_at` are never used to
position pass words. The pass restores the first-word offset removed by
`postprocess_words`. A batch slice is at most 90 seconds, below the 120-second
provider limit and well below 100 MB for PCM16 mono at 16 kHz. Each slice gets
the offline-sync speaker matcher; conversation-wide clustering uses extracted
segment embeddings and enrolled voiceprints. No speaker embedding cache or
other canonical artifact is written by this path.

## Results and phase-2 gate

The private `users/{uid}/conversations/{conversation_id}/transcription_shadow_results/v1`
document stores only bounded scalar metrics: outcome, latency, captured
audio seconds, coverage, missing tail seconds, word-level edit distance to
the streaming transcript, word counts, owner-attributed seconds, speaker
counts, estimated clock offset, and remap success/safety. No transcript text,
UID label, audio, embeddings, or identity receipts are copied there. This
subcollection has one fixed-ID child and a fixed set of scalar fields, so its
size is bounded independently of transcript length. No backend API or client
reads it: the only production code reference is the shadow writer, and
conversation reads load only the parent document. The result transaction reads
the durable account-deletion marker and the conversation parent, refusing a
write once account deletion starts or the conversation is deleted;
the conversation delete path sweeps children again after deleting the parent
to catch a child committed during its first enumeration. Account deletion's
recursive user wipe removes results committed before its deletion marker.
Prometheus labels contain only
the closed outcome vocabulary.

Outcomes are `ok`, `failed`, `timeout`, `partial_audio`, `no_audio`, and
`skipped_budget`. A duplicate Redis reservation exits without counting or
writing a second result. A tail gap over five seconds or coverage below 95% is
`partial_audio`; this is expected on silence-timeout finalization when the
pusher's last upload has not arrived. Legacy Opus file durations can
underestimate decoded PCM; the worker atomically reserves any excess before
another provider call and stops if the daily cap is exhausted. Audio coverage uses stored chunk times
and the finalization wall-clock end; it is a measurement, not evidence that the
live transcript clock is correct. `word_distance` is a bounded WER-style edit
distance with the live words as denominator; it is null above 4,000 words or
when the live side has no words.

`segment_remap.py` estimates drift from distinctive matching text and maps
old segment IDs by time overlap. It expands source references and manual
speaker receipts over splits, rejects conflicting receipts on merges, and
rejects all concurrent target overlaps even when their text similarity differs,
rejects translations whose changed segmentation would duplicate or concatenate
whole translated sentences. Any unresolved, ambiguous, or unsafe annotation
sets `remap_safe=false`. Phase 2 must require safe remap as well as coverage and
owner-attribution parity before promoting a record. Shadow metrics do not
establish Parakeet's real-audio accuracy or a safe production capacity curve.

Durable shadow dispatch needs its own delayed Cloud Task, OIDC worker route,
idempotent lease/attempt receipt, retry policy, and runtime wiring. Reusing the
finalization task would couple retries and acknowledgement to canonical
processing, so this is a separate follow-up before a Cloud Run ramp.
