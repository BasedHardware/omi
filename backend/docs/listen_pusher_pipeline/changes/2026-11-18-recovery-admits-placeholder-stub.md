# Recovery admits a capture stub that only carries the placeholder title

Follow-up to `2026-11-17-notes-pending-title.md`. Listen builds before that change stamped every
in-progress capture stub with the fallback label "Discussion notes". Home and the summary readers
learned to treat it as untitled; self-heal recovery admission did not. `recovery_admission_refusal`
refused those rows with `protected_content`, so a stale stub never finalized, and sync pieces bridged
to it stayed deferred behind an `in_progress` target.

Changed, on by default with no flag and no provider call of its own. This is the critical-path
subset of #25619:

- `recovery.structured_has_protected_content` no longer counts the stored fallback labels
  (`home_titles.is_fallback_title`), an empty title or Home's "Transcribing…" label as a title. Any
  other title, including "Untitled" or "Conversation", still protects the row, unlike #25619's
  broader `summary_quality.valid_title` match. A gist joins the protected text fields, so a
  placeholder beside a gist still refuses. A user title, an overview, sections, tasks or events
  still protect the row.
- `recovery.stored_structure_is_replaceable` is the recovery guard in `process_conversation`. A
  short placeholder-only recovery gets the deterministic minimum instead of running the notes agent
  against a title it may not replace and failing as `RecoveryStructureUnavailableError`.

The predicate is shared, so the recovery discard commit (`database/conversations.py`) and the
dead-letter retry offer (`conversation_terminal_title.dead_letter_conversation_updates`) read the
same definition. A content-free placeholder stub's rule discard commits instead of dead-lettering, and
a dead-lettered placeholder stub with transcript text is offered a retry. #25619's
`recovery_discard_would_lose_content` reduces to this predicate on every stored shape, so that call
site is unchanged here. The terminal-title and empty-structure-minimum changes stay with #25619.

Exit for an admitted stub (prod sample, 2026-11-18):

- Sealed mobile `server_batch_only` stubs (about 90%) take the finalizer's server-batch branch
  (`utils/conversations/finalizer.py`, `server_batch_owned` and no transcript). `register_recording`
  writes the canonical `record_pending` batch job only when none exists for the record identity, and
  `complete_server_batch_capture` closes the row with Home's transcription wait. Recovery runs no STT;
  the batch pipeline transcribes the retained audio once.
- Plain live rows (about 10%) carry a live transcript and run normal recovery notes.
- A `batch_live_v1` row without the server-batch marker is never rule-discarded by recovery when it
  has audio files: its live text is only a preview. `process_conversation` keeps it as a recovery
  minimum (`relevance_decision.reason = batch_audio_owed`), so the finalizer registers the retained
  audio for batch instead of dropping the obligation with a discard.

The self-heal verifier accepts a completed job whose `finalization_outcome` is
`server_batch_capture` as valid output. That terminal writes no notes (the batch pipeline does,
later), so before this change every admitted server-batch stub paged `verify_not_rich` at critical
severity on the following tick.

Batch priority is unchanged. Registrations are written as FRESH, but `admit_record_units` demotes a
native record unit by its recording's end (`record_intake_priority`, on in prod), so these captures,
hours old, are admitted as RECENT behind live FRESH work. Registrations arrive no faster than the
self-heal admission cap.

The self-heal tick admits at most `MAX_HEAL_ADMISSIONS_PER_TICK` (10) rows per scan under the leader
lease, so the backlog drains at that bounded rate.

Evidence: `tests/unit/test_selfheal_recovery.py`, `tests/unit/test_notes_pending_title.py`,
`tests/unit/test_conversation_quiet_finalization.py`, `tests/unit/test_empty_structure_minimum_fallback.py`,
`tests/unit/test_recovery_discard_pipeline.py`, `tests/unit/test_terminal_relevance.py`,
`tests/unit/test_record_intake_priority.py`.
