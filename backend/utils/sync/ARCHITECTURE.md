# utils/sync — Offline Sync pipeline

Server side of Offline Sync: devices upload captured audio in batches, the
pipeline turns them into conversations, and a durable artifact pass builds the
per-conversation playback audio. Admission, spend, and rate limits guard the
whole path.

## Flow

```
upload -> lanes (fresh vs backfill) -> capture_manifest (byte binding)
       -> pipeline (decode -> VAD -> fair-use -> STT -> conversation merge)
       -> merge_dedupe / merge_audio (merge survivors)
       -> conversation_artifact_protocol -> conversation_artifact_worker
          (fingerprinted, fenced playback artifact build)
```

## Modules

- `lanes.py` — authoritative fresh/backfill classification for uploads.
- `capture_manifest.py` — short-lived server-signed manifests binding fresh
  sync bytes to a conversation.
- `content_id.py` — stable, privacy-safe identities for sync batches across
  job re-uploads.
- `backfill.py` — Redis-backed admission and daily spend guards for historical
  sync recovery.
- `rate_limit.py` — privacy-safe response and telemetry primitives for sync
  rate limits.
- `pipeline.py` — the sync local-files pipeline: decode, VAD, fair-use, STT,
  conversation merge; owns the run lock and lease renewal.
- `files.py` — codec plumbing (length-prefixed Opus decode to WAV and
  friends) used by the pipeline.
- `merge_dedupe.py` — shrink-only merge dedupe for offline sync transcript
  segments.
- `merge_audio.py` — private-cloud audio backing for partial merge survivors.
- `playback.py` — PCM/WAV conversion helpers for playback assets.
- `conversation_artifact_protocol.py` — durable row identity and opaque
  content/task generations for the playback artifact contract (fingerprint
  naming keeps rebuild tasks idempotent).
- `conversation_artifact_worker.py` — builds one source-fenced conversation
  playback artifact per task; upload precedes the stamp so a stamped
  fingerprint always implies a servable blob.
