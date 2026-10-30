# Short-recording notes floor

`NOTES_SHORT_CLIP_FLOOR` is an `ops_kill` switch, on unless explicitly set to
`off`, `false`, `0`, or `no`. It serves independently of `NOTES_PACKET_V2_MODE`.
The existing notes-v2 serve cohort still implies the floor when this switch is off;
notes-v2 shadow comparisons continue when the independent floor is disabled.

A nonempty audio transcript below 4 seconds of transcript speech gets the
existing deterministic minimum. Known English captures also qualify below 12
words; the word rule is disabled for every other/unknown/multilingual capture
and for text containing non-ASCII letters, including mixed or mistagged unspaced
scripts (Thai, Lao, Khmer, Burmese, Japanese, Chinese including CJK extensions,
and Korean). Capture language controls this rule, never output-language preference.
Missing duration alone cannot floor a non-English/unknown capture. The minimum
has a nonempty title, deterministic emoji,
empty overview, no tasks/events, and `structured.title_provenance=server_minimum`.
It remains retained with its original transcript and audio. Photos, explicit
user-kept authority, user titles, existing non-minimum notes, user-selected summary
apps (explicit request, stored selection or preferred app), and explicit English
reminder phrasing bypass the floor. Existing notes include any non-minimum title
or provenance, overview, sections, tasks or events. An explicit Omi-summary request
also bypasses it. An unreadable app preference conservatively keeps full notes.
Reminder matching only covers English. Other languages retain notes for short
reminders of at least four seconds because they use duration only. All languages
remain subject to the duration rule unless otherwise exempt. Matching joins
segments and uses the existing Unicode/apostrophe normalization,
including a phrase split across segment boundaries. Stored manual titles survive model
deserialization as excluded read-only metadata, preserving the exemption during reprocessing.

Consumers use the persisted minimum marker rather than re-evaluating the switch:
memory extraction (both L1 and L2), summary apps, automatic folder assignment and
goal intelligence and summary embeddings/vector indexing are skipped. Normal and
completed-replay finalization both omit embedding work; the direct vector writer
also no-ops for minimum rows, including metadata-only requests. Title search
uses the separate Typesense title/overview index; minima need no semantic-summary
vector. Enriched replacements can be embedded normally. Minimums do not queue
lazy enrichment. Capture audio
work, creation webhooks and external integration delivery retain their normal path.
Recovery-only terminal minimum behavior remains scoped to recovery triggers.
A later enriched replacement without the marker admits derived work normally.

Only an audited `keep/rule/content_below_floor` minimum waives the first-summary
obligation. It clears pending summary debt and prevents repair retries without setting
`terminal_no_derived_effects`, so creation delivery remains admitted. Empty provider
outputs retain their summary debt; banked summaries and later meaningful enrichment
keep the existing summary guarantees.

This is a **server-only** compute contract. The desktop local summarizer is out
of scope and can still produce local notes before upload. The deterministic title
algorithm is unchanged. Its desktop mirror remains
`desktop/macos/Desktop/Sources/LocalInference/DeterministicConversationMinimum.swift`.

## Basis and monitoring

David's 2026-10-31 decision uses the supplied GLM aggregate report: approximately
15% of shadow evaluations were floor-eligible, and approximately 69% of eligible
clips had at most seven words. These are evaluations, not unique recordings or a
measured share of paid summaries; retries can inflate evaluations. This change
does not claim a measured dollar saving or perform production reads/writes.

Watch served floor decisions (including notes-v2 serves):

```promql
sum(increase(omi_notes_refactor_results_total{check="short_clip",outcome="minimum"}[1h]))
```

The counter increments only when a minimum is returned, not for shadow-only
eligibility. Monitor notes/task regressions alongside this volume, particularly
short commands without explicit reminder phrasing.

Rollback: set `NOTES_SHORT_CLIP_FLOOR=off` to restore previous admission outside
the existing notes-v2 serve cohort. Existing minimum rows retain their marker and
remain exempt from intelligence until actually enriched; rollback does not backfill.

## Verification

Run each test file in its own pytest process:

```bash
backend/.venv/bin/python -m pytest backend/tests/unit/test_short_clip_rollout.py
backend/.venv/bin/python -m pytest backend/tests/unit/test_short_clip_floor.py
backend/.venv/bin/python -m pytest backend/tests/unit/test_notes_packet_v2.py
backend/.venv/bin/python -m pytest backend/tests/unit/test_structured_emoji_never_defaults_to_brain.py
```

The rollout suite exercises the real structure and post-persistence boundaries
with synthetic input and mocked provider/storage leaves, including deferred
webhook delivery. It makes no network or production API calls.
