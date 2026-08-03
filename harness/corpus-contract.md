# Stage A corpus contract

This contract is a public, synthetic-safe input boundary for the Stage A runner. A corpus is
an object with one trusted adapter configuration and ordered sessions. The runner receives its
path only from `argv`; it has no built-in corpus location.

Each segment supplies `event_id`, transcript `text`, `start_at` with an explicit RFC3339 offset,
`speaker_label` (display-only), `speaker_id` (a source-local diarization continuity key), and the
optional typed producer attestations `is_actor_user` and `person_id`. Those attestations can be
wrong. The adapter configuration—not a display rendering—supplies producer, contract, namespace
instance, asserted domain/scope, issuer, and authority-policy lineage for a `person_id`.

`revision_lineage`, `ingest_sequence`, and `settled_window_id` participate in the stable replay
order alongside event time and capture sequence. A segment is immutable at its lineage; a
correction is a new segment/revision, not an in-place edit.

The runner validates this schema before opening a model. `--validate-only` prints the canonical
digest and exits without model or database work.
