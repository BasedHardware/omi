# A row with no notes keeps no title

The shared note policy added on 2026-11-16 gives generated notes with an unusable headline the
deterministic label "Discussion notes". The conversation writer applied it to every write that
carried a `structured` map, including the in-progress stub a listen socket creates and the raw
completion of a batch capture, neither of which has notes. Episodes already kept the honest
pending presentation for an unprocessed row; conversations did not.

Three effects followed for a stamped batch capture:

- Home presented it as a finished row. `transcribing_hold.applies` and `home_step.classify` read
  any non-empty title as "has notes", so the row left the bounded "Transcribing…" presentation
  and showed "Discussion notes" with no summary and no expiry.
- The batch projection did not register the first-summary obligation. `stamp_projection_debt`
  skipped rows that already had a title, so the row had no `summary_due_at` for the repair sweep
  and depended on one enrichment attempt.
- The expired empty-capture rule stopped classifying a stamped zero-content stub as noise.

Changes, all on by default with no new flag, read or provider call:

- `database/conversations.py:_quality_processing_notes` leaves the title empty when
  `home_titles.notes_pending` holds (no usable title, overview, gist, section body, task or
  event) and neither a user title nor a stored valid title exists. A stored stand-in title is kept;
  a stored placeholder is cleared. Generated notes with an unusable headline still get the label.
- `summary_delivery.stamp_projection_debt` treats a placeholder as untitled, so rows stamped before
  this change are enrolled when their transcript lands.
- `transcribing_hold.applies`, the `processing` branch of `home_step.classify`,
  `empty_capture.applies` and `legacy_empty_wire.project` treat a placeholder as untitled.
- `home_titles.placeholder_title_wire`, applied at the same API exits as the transcribing hold,
  serves a row that carries only the fallback label as untitled. It matches the two labels
  `title_or_fallback` produces and nothing else, and never changes a user title or a row with notes.

Rows already stamped are healed on read; no stored row is rewritten and no backfill runs. A stamped
row whose transcript landed before this change, and whose enrichment attempt failed, keeps a
transcript with no registered obligation; the verification query in the PR counts that residue.

This note does not cover the transcript stall of the same window, where a source-reuse result
without its marker blocked each owner's ordered projection chain (#25597).

Evidence: `tests/unit/test_notes_pending_title.py`.
