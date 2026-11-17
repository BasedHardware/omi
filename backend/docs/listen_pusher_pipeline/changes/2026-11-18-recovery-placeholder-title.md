# Recovery treats a placeholder title as untitled

Follow-up to `2026-11-17-notes-pending-title.md` and
`2026-11-17-notes-pending-title-followup.md`. Those changes moved the summary and Home readers to
`home_titles` / `summary_quality.valid_title`. Four "has a title" checks on conversation rows were
left reading `str(title).strip()`, so a row that only carried the fallback label "Discussion notes"
still looked titled to them.

Changed, all on by default with no new flag, read or provider call:

- `process_conversation` recovery's `stored_content_is_replaceable` uses `valid_title`, so a row
  whose stored structure is not rich and whose only title is a placeholder is replaceable by the
  deterministic minimum. A real stored title, a `server_minimum` stand-in and a user title keep
  their previous meaning.
- `empty_structure_minimum._eligible` (the same predicate, evaluated after enrichment) uses
  `valid_title` for the same reason.
- `recovery.structured_has_protected_content` no longer counts a placeholder as a real title, so
  quiet finalization, the recovery discard fence and the `summary_retryable` decision do not treat
  a placeholder-only row as holding an earlier summary. A user title, a real title, an overview,
  sections, tasks or events still protect the row.
- The legacy (unstamped) branch of `home_step.classify` uses `untitled_pending` instead of a
  non-empty title, so a completed row with only a placeholder and no transcript shows the bounded
  "Transcribing…" wait rather than a finished row. A row with notes keeps its previous result.

`utils/summary_quality.py` is unchanged: its source is part of the notes prompt fingerprint.

Evidence: `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_empty_structure_minimum_fallback.py`.
