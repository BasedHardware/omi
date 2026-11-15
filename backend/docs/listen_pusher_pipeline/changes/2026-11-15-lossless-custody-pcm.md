# Smaller lossless storage for new custody PCM

Superseded for encoder concurrency and the wall-clock bound by
[the pusher codec-latency budget](2026-11-15-pusher-codec-latency-budget.md):
one process-local slot and a 0.4 s shared budget now replace the two-slot,
per-child-only bound described below. Everything else here still holds.

SCA-2302. Listen and pusher now share `audio_pcm_storage.compact_pcm` at their
existing immutable capture boundary. Mono PCM16 can use FLAC only if a fresh
decode reproduces every original byte and saves at least 5%. Silence compresses
well; the decision needs no speech detector, provider call or new service.
Quiet speech retains all its samples. Native Opus, PCM8, mobile original files,
PCM projections and all historical objects retain their current behavior.

Optional work has a 16 MiB input bound, two process-local slots, one codec
thread and a two-second timeout per encode/decode subprocess. Every error,
busy slot or insufficient saving falls back to PCM before the unchanged
media-plus-manifest commit/ACK barrier. Existing FLAC readers serve receipts,
playback, frame gaps and recovery. No expiration, deletion, bucket rule,
storage-class change or rewrite job is introduced.

The default-on writer kill switch is documented in the
[pipeline contract](../../listen_pusher_pipeline.mdx#durable-audio-outbox-default-on)
and the [custody runbook](../../runbooks/audio-durable-outbox.md#lossless-pcm-storage-new-writes).
Release owns review of record, merge, coordinated listen/pusher rollout,
30-minute canary and serving proof. Disable compression to restore new PCM
writes while preserving reads of committed FLAC. No GCP access is needed for
implementation or hermetic verification.

Verification: `test_audio_pcm_storage.py` uses real FFmpeg for silent, quiet,
mixed and incompressible synthetic PCM. It covers exact decoded bytes, content
identity and retry, encryption, gaps and frame selection, listen and pusher,
writer rollback and fallback on unavailable/busy/timed-out/corrupt encoding.
The existing durable-outbox, custody-frames and gapped-pack suites guard receipt
failure boundaries and existing original-format readers. Local evidence is
not a production cost or silence-accuracy estimate.

The margin-owner follow-up adds a histogram for the optional codec delay,
zero-initialized outcome counters, real child-process timeout and busy-capacity
custody-commit tests, and quantitative canary queries/rollback thresholds in
the runbook. This makes the added delay measurable while leaving the existing
representation and custody decision unchanged. Credit net savings only after
eligible production byte savings and compute cost have been measured.
