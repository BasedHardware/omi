# Batch abstention display (stage 1)

PR #21981 preserves uncovered batch words under distinct `BATCH_UNASSIGNED_` keys.
Those keys must remain distinct for provenance and correction, but must not look
like extra people. The presentation boundary `utils/speakers/display.py` now labels
prefix/source/status-marked batch abstentions `Unknown speaker`, with no letter,
name, participant count, overflow slot or episode voice-order slot. Real voices
keep first-appearance letters; explicit wearer `You` rows are unchanged.

The default-on kill switch `SPEAKER_ABSTENTION_UNKNOWN_LABEL_ENABLED` uses
`config.refactor_modes.default_on`; false restores the previous labels in both
`display_participants` and `developer_speaker_names`. No storage change, backfill,
client change or new localization string. Contract: [speaker abstention display](../../listen_pusher_pipeline.mdx#batch-abstention-display).

Confirmed through the shared boundary and consumer tests:

- Conversation API `speaker_name`, including preserved developer API values.
- Speaker-review context and task-review evidence excerpts (mobile already localizes these labels).
- MCP transcript-search text and structured `speaker_label` hits use `[unassigned speech]`.
- LLM transcript text and memory transcripts use `[unassigned speech]` per gap.
  Compact inputs retain distinct citation keys and null identity bindings, with
  the same explicit unassigned-speech marker on each segment. Retrieval chunk,
  shared-chat and merge normalizers use this prompt presentation as well.
- Episode moment input uses unassigned-speech semantics; gaps do not spend its bounded voice-order ledger.
- Analytics row labels; distinct gap rows and speech totals remain intact, participant count unchanged.

The fictional fixtures and before/after server API/excerpt text images live in
[UI evidence](../../../../.agent-artifacts/ui-evidence/speaker-abstention/README.md).
These are server-output renders, not client-screen acceptance. Stage 2 owns the
wire abstention flag and client naming; renders pending David.

Acceptance metric in the fixtures: distinct attributed labels shown (including
`You`, excluding `Unknown speaker`) minus `len(participant_speaker_ids)` is zero.
The tests also assert distinct gap keys, unchanged input rows, marker precedence,
letter stability, overflow exclusion and kill-switch restoration.

Mobile numbering, macOS `SpeakerLabelFormatter`, and web `TranscriptView`/chip
formatters are **not fixed by stage 1**; they belong to stage 2. UI-facing API,
review and analytics labels stay `Unknown speaker`, using the existing mobile
excerpt localization. Shared text is never a shared identity: prompt keys and
per-segment citations remain distinct. Raw scoped IDs, evidenced participant IDs,
abstention keys, words and speech seconds are shown separately in the snapshots
and remain unchanged; no speaker metric is modified to hide fragmentation.

The six snapshot cases include one voice/two gaps, two voices/separate unknown
speech, a manual wearer receipt, mixed capture epochs, zero-duration point keys,
and historical `BATCH_UNASSIGNED_` fallback keys sharing old numeric ID -1.
Tests assert no text loss or label-based deduplication.
