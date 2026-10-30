# Short-recording notes floor

`NOTES_SHORT_CLIP_FLOOR` is an `ops_kill` switch, on unless explicitly set to
`off`, `false`, `0`, or `no`. It serves independently of `NOTES_PACKET_V2_MODE`.
The existing notes-v2 serve cohort still implies the floor when this switch is off;
notes-v2 shadow comparisons continue when the independent floor is disabled.

A nonempty audio transcript below 12 words **or** 4 seconds of transcript speech
gets the existing deterministic minimum: a nonempty title, deterministic emoji,
empty overview, no tasks/events, and `structured.title_provenance=server_minimum`.
It remains retained with its original transcript and audio. Photos, explicit
user-kept authority, user titles, and explicit reminder phrasing bypass the floor.
Reminder matching joins segments, including a phrase split across segment boundaries.

Consumers use the persisted minimum marker rather than re-evaluating the switch:
memory extraction (both L1 and L2), summary apps, automatic folder assignment and
goal intelligence are skipped. Minimums do not queue lazy enrichment. Capture audio
work, creation webhooks and external integration delivery retain their normal path.
Recovery-only terminal minimum behavior remains scoped to recovery triggers.
A later enriched replacement without the marker admits derived work normally.

The deterministic title algorithm is unchanged. Its desktop mirror remains
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
