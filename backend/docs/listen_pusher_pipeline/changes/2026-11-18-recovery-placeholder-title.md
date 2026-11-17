# Recovery treats a placeholder title as untitled

Follow-up to `2026-11-17-notes-pending-title.md` and
`2026-11-17-notes-pending-title-followup.md`. Those changes moved the summary and Home readers to
`home_titles` / `summary_quality.valid_title`. Three "has a title" checks on the recovery and
terminal path were left reading `str(title).strip()`, so a row that only carried the fallback label
"Discussion notes" still looked titled to them.

Changed, all on by default with no new flag and no provider call of their own:

- `recovery.stored_structure_is_replaceable` is the one rule for "recovery may replace this stored
  structure": no notes and no real title. A placeholder label is not a title, so a row that only
  carries one is replaceable by the deterministic minimum; a real stored title and a
  `server_minimum` stand-in keep their previous meaning. `process_conversation` recovery's
  `stored_content_is_replaceable` and `empty_structure_minimum._eligible` both call it, so the
  predicate has one owner. "No notes" is `recovery._has_note_content`, which is deliberately
  broader than `structured_is_rich`: the latter verifies a fresh enrichment landed and must stay
  aligned with `summary_delivery.present`, so it cannot gain a gist, people, insights, claim
  provenance, a meeting kind or a salience verdict without turning the typed recovery refusal into
  a persist-time `SummaryOutputUnavailable`.
- `recovery.structured_has_protected_content` no longer counts a placeholder as a real title, and
  now shares `_has_note_content`. **New protection**: a gist, participants, insights, note claims,
  `meeting_type` and `salience` now make a row ineligible for recovery admission, the recovery
  discard fence and `summary_retryable=True` at dead letter. That is intended: the Home card
  preview reads the gist, and the rest are enrichment the deterministic minimum would drop.
  Overview and gist use the note policy's narration filter, so a row whose only text is "the
  transcript is unavailable" has no notes and is still replaceable.
- `conversation_terminal_title._title_update` gives a dead-letter or orphan row the deterministic
  title only when it has no real title and no protected content, so a placeholder headline beside
  real notes keeps its notes and its headline.

Not changed: the Home step. `home_step.classify`'s legacy branch still reads a non-empty title, so
an unstamped row that only carries a placeholder still reads `ready` rather than the bounded
wait. That presentation rule belongs with the `transcribing_hold` receipt gate, and widening it
here would hide transcript-bearing rows on list reads that omit `transcript_segments`.

Residual, bounded and documented rather than repaired: an `in_progress` row whose only stored
content is a gist is now refused recovery admission, and the quiet check retires its obligation, so
no path closes it. Before this change the same row with a placeholder title was already refused; a
gist-bearing row that never reached notes is rare, and the Home processing-age presentation hides
it after `HOME_PROCESSING_MAX_AGE_SECONDS`. A repair pass over that cohort is a later, separately
approved write.

Relaxing `structured_has_protected_content` admits placeholder-only rows that were previously
refused to normal processing, which may summarize them. The change adds no provider call of its
own.

`utils/summary_quality.py` is unchanged: its source is part of the notes prompt fingerprint.

Evidence: `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_empty_structure_minimum_fallback.py`,
`tests/unit/test_conversation_quiet_finalization.py`,
`tests/unit/test_terminal_relevance.py`, `tests/unit/test_dead_letter_visible_row_title.py`.
