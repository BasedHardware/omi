# Recovery treats a placeholder title as untitled

Follow-up to `2026-11-17-notes-pending-title.md` and
`2026-11-17-notes-pending-title-followup.md`. Those changes moved the summary and Home readers to
`home_titles` / `summary_quality.valid_title`. Four "has a title" checks on conversation rows were
left reading `str(title).strip()`, so a row that only carried the fallback label "Discussion notes"
still looked titled to them.

Changed, all on by default with no new flag and no provider call of their own:

- `recovery.stored_structure_is_replaceable` is the one rule for "recovery may replace this stored
  structure": not rich, and no real title. A placeholder label is not a title, so a row that only
  carries one is replaceable by the deterministic minimum; a real stored title and a
  `server_minimum` stand-in keep their previous meaning. `process_conversation` recovery's
  `stored_content_is_replaceable` and `empty_structure_minimum._eligible` both call it.
- `recovery.structured_has_protected_content` no longer counts a placeholder as a real title, so
  quiet finalization, the recovery discard fence and the `summary_retryable` decision do not treat
  a placeholder-only row as holding an earlier summary. A user title, a real title, an overview,
  gist, sections, tasks or events still protect the row. `gist` joins the rich and protected
  fields: Home already reads a non-empty gist as note content, and the deterministic minimum
  writes a blank one.
- The legacy (unstamped) branch of `home_step.classify` uses `notes_pending` instead of a
  non-empty title, so a completed row with only a placeholder and no transcript shows the bounded
  "Transcribing…" wait rather than a finished row. A row with notes, or with an empty title and
  notes, keeps its previous result.

Relaxing `structured_has_protected_content` admits placeholder-only rows that were previously
refused to normal processing, which may summarize them. The change adds no provider call of its
own.

`utils/summary_quality.py` is unchanged: its source is part of the notes prompt fingerprint.

Evidence: `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_empty_structure_minimum_fallback.py`.
