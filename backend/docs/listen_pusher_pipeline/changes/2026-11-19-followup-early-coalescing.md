# Projection follow-up read reduction

A periodic page can discover several ready siblings from one upload. The
[follow-up contract](../../listen_pusher_pipeline.mdx#projection-discovery-progress)
allows a duplicate to skip its read-only session check if the same process
already completed a probe on that page. The first live privacy and deletion
walk must cover the later sibling's full privacy scope. A fresh, bounded
token read certifies the unchanged authority revision. Incomplete probes,
errors, refusals, missing evidence, and invalidation take the full path.
Every mutation retains its original privacy and custody fences.

Set `BATCH_PIPELINE_FOLLOWUP_EARLY_COALESCE_ENABLED=false` to restore the
original check order. Compare six-hour Firestore privacy and projection
session reads per completed audio-second on backend-integration. Use
`omi_batch_pipeline_projection_followup_outcomes_total{outcome="early_check_skipped"}`
to measure how often the fast path actually fires.
