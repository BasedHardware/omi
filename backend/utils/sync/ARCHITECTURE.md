# Sync utilities

This package owns uploaded-audio sync admission, decoding, transcription orchestration, persistence fencing, and playback reconstruction.

## Boundaries

- `pipeline.py` is the coordinator. It owns job/run leases, segment processing, persistence fences, and terminal outcomes.
- `files.py`, `content_id.py`, and `capture_manifest.py` validate and normalize uploaded files and their identities.
- `lanes.py`, `backfill.py`, and `rate_limit.py` classify work and enforce admission policy.
- `merge_audio.py` and `merge_dedupe.py` contain deterministic merge helpers.
- `playback.py` reconstructs and serves persisted audio artifacts.
- `provenance.py` and `telemetry.py` provide bounded attribution and operational labels.

Keep HTTP routing and database implementations outside this package. New helpers should remain deterministic where possible; changes that mutate a sync job must preserve the run-lease and conversation-persistence fences in `pipeline.py`.
