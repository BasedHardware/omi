# Recovery treats a placeholder title as untitled

Follow-up to `2026-11-17-notes-pending-title.md` and
`2026-11-17-notes-pending-title-followup.md`. Those changes moved the summary and Home readers to
`home_titles` / `summary_quality.valid_title`. Four "has a title" checks on conversation rows were
left reading `str(title).strip()`, so a row that only carried the fallback label "Discussion notes"
still looked titled to them.

Changed, all on by default with no new flag and no provider call of their own:

- `recovery.stored_structure_is_replaceable` is the one rule for "recovery may replace this stored
  structure": not rich, no gist, and no real title. A placeholder label is not a title, so a row
  that only carries one is replaceable by the deterministic minimum; a real stored title and a
  `server_minimum` stand-in keep their previous meaning. `process_conversation` recovery's
  `stored_content_is_replaceable` and `empty_structure_minimum._eligible` both call it. A gist
  counts as content here but stays out of `structured_is_rich`, which also gates the typed
  recovery refusal: `summary_delivery.present` does not treat a gist as a summary, so widening
  that predicate would turn a refusal into a persist-time `SummaryOutputUnavailable`.
- `recovery.structured_has_protected_content` no longer counts a placeholder as a real title.
  **Gist protection is new here**: `gist` joins the protected text fields, so a gist-only row is
  newly refused recovery admission and quiet finalization, and newly loses
  `summary_retryable=True` at dead letter. That is intended: the Home card preview reads the gist,
  so a retry chip beside it would misdescribe the row. Its overview/gist test also uses
  `safe_body`, the same availability-narration filter `home_titles.notes_pending` applies, so the
  two readers agree about a row whose only text is "the transcript is unavailable".
- `conversation_terminal_title._title_update` gives a dead-letter or orphan row the deterministic
  title only when it has no real title and no protected content, so a placeholder headline beside
  real notes keeps its notes and its headline.
- The legacy (unstamped) branch of `home_step.classify` uses `notes_pending` instead of a
  non-empty title, so a completed row with only a placeholder and no transcript shows the bounded
  "Transcribing…" wait rather than a finished row. A row with notes keeps its notes visible; an
  empty title with a gist, section body, task or event now reads `ready` instead of the bounded
  transcribing wait, because those are notes. The wait is bounded by `finished_at`, then
  `created_at`; a row with neither stays `ready` rather than waiting forever.

Relaxing `structured_has_protected_content` admits placeholder-only rows that were previously
refused to normal processing, which may summarize them. The change adds no provider call of its
own.

`utils/summary_quality.py` is unchanged: its source is part of the notes prompt fingerprint.

Evidence: `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_empty_structure_minimum_fallback.py`,
`tests/unit/test_conversation_quiet_finalization.py`,
`tests/unit/test_terminal_relevance.py`, `tests/unit/test_dead_letter_visible_row_title.py`.
