# Batch final-pass artifact lifecycle diagnostics

The speaker final pass now distinguishes cleaned artifact receipts from live
registered artifacts. A no-URI row with `expires_at` is the metadata left after
retention deletes the GCS object, not another live registration schema. It
returns `skipped_expired` / `artifact_cleaned` after the existing owner,
generation and erasure checks. URI binding and generation-pinned downloads
remain required for live objects. No flags or retention/deadline defaults change.
Budgeted artifact privacy checks now use the same bounded read-only snapshots
as reference lookup, including post-download and retained-source checks.

The read-only owner lab reports per-conversation read-phase wall time, received
GCS bytes, reserved bytes and object count, including failures. Conversation
loading is timed separately. Conflicting PCM overlaps remain a whole-pass
refusal; unmatched stored segment IDs retain their labels and permit partial
coverage only where other segments have evidence.

See the [local evidence and retry timing](../../../testing/owner_lab/validation/2026-11-05-speaker-final-pass-artifact-lifecycle.md)
and [harness instructions](../../../testing/owner_lab/README.md#batch-speaker-final-pass-repro).
