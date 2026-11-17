# Recovery treats a placeholder title as untitled

Follow-up to `2026-11-17-notes-pending-title.md` and
`2026-11-17-notes-pending-title-followup.md`. Those changes moved the summary and Home readers to
`home_titles` / `summary_quality.valid_title`. Three "has a title" checks on the recovery and
terminal path were left reading `str(title).strip()`, so a row that only carried the fallback label
"Discussion notes" still looked titled to them.

Changed, all on by default with no new flag and no provider call of their own:

- `recovery.stored_structure_is_replaceable` is the one rule for "recovery may replace this stored
  structure": no content and no real title. A placeholder label is not a title, so a row that only
  carries one is replaceable by the deterministic minimum; a real stored title and a
  `server_minimum` stand-in keep their previous meaning. `process_conversation` recovery's
  `stored_content_is_replaceable` and `empty_structure_minimum._eligible` both call it, so the
  predicate has one owner.
- Replacement is blocked by more fields than admission is. `_has_replace_blocking_content` also
  counts a gist, participants, insights, note claims, `meeting_type` and `salience`, because the
  deterministic minimum would drop them. `structured_is_rich` is unchanged: it verifies a fresh
  enrichment landed and must stay aligned with `summary_delivery.present`.
- `recovery.structured_has_protected_content` no longer counts a placeholder as a real title. It
  shares `_has_stored_text_content` (overview, gist, sections, tasks, events), which uses the note
  policy's narration filter, so a row whose only text is "the transcript is unavailable" has no
  content and is still replaceable. **New protection**: a gist now blocks recovery admission, the
  recovery discard fence and `summary_retryable=True` at dead letter. That is intended: the Home
  card preview reads the gist, so a retry chip beside it would misdescribe the row. Enrichment-only
  fields (participants, insights, note claims, `meeting_type`, `salience`) deliberately do not block
  admission: the quiet check retires an obligation on a refusal without closing the row.
- `conversation_terminal_title._title_update` keeps its promise that a kept visible terminal row
  leaves titled: a blank title is always replaced, and a placeholder label is replaced unless real
  notes sit beside it (that row keeps its notes and its headline).

Not changed: the Home step. `home_step.classify`'s legacy branch still reads a non-empty title, so
an unstamped placeholder-only row still reads `ready` rather than the bounded wait. That rule
belongs with the `transcribing_hold` receipt gate; widening it here would hide transcript-bearing
rows on list reads that omit `transcript_segments`.

Residual, documented rather than repaired: an `in_progress` row whose only stored content is a
gist is refused recovery admission, and the quiet check retires its obligation, so no path closes
it. The same row with a placeholder title was already refused before this change, so the new
exposure is a gist-bearing row with an empty title. Such a row is rare, it is not hidden by the
Home processing-age bound (that bound applies to `processing`/`merging`, not `in_progress`), and it
stays presented as an in-progress capture. Closing it needs a repair pass that keeps the gist, a
later and separately approved write.

Relaxing `structured_has_protected_content` admits placeholder-only rows that were previously
refused to normal processing, which may summarize them. The change adds no provider call of its
own.

`utils/summary_quality.py` is unchanged: its source is part of the notes prompt fingerprint.

Evidence: `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_empty_structure_minimum_fallback.py`,
`tests/unit/test_conversation_quiet_finalization.py`,
`tests/unit/test_terminal_relevance.py`, `tests/unit/test_dead_letter_visible_row_title.py`.
