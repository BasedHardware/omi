# Name a voice across its recording

Recording-wide edits apply the existing same-scope carry rule to every episode
member, including earlier members. The all-user conversation entry point also
covers same-scope conversations without episode membership. Each member retains
its own replayable receipt. An encrypted latest-decision map lets later rollovers
inherit a late correction even when the preceding member has no such voice.
Legacy rows use the existing deterministic segment IDs and conversation-local
speaker matching. Diarization, embeddings and cross-scope voice linking are unchanged.

Mobile naming defaults to the recording and reports the applied line count.
Selection spans member transcripts and sends one grouped assignment request.
Naming remains available while notes regenerate; live edits queue. A stale-speaker
409 restores optimistic labels and asks the user to select the lines again.

Deploy API and live receipt/carry consumers before shipping the mobile build.
The default-on `RECORDING_SPEAKER_RENAME_ENABLED` kill switch reports disabled when off;
mobile falls back to explicit IDs in the old single-conversation assignment endpoints on disabled/404.
Off also restores previous-member rollover carry. Existing episode admission remains;
the conversation entry point provides recording correction outside that cohort.
Only the rollout lead deploys.

The [receipt and ordering contract](../../listen_pusher_pipeline.mdx#transactional-manual-speaker-boundaries)
defines fan-out, scope fencing, legacy behavior and trailing regeneration.
Fixture evidence lives in
[backend regressions](../../../tests/unit/test_recording_speakers.py),
[mobile selection tests](../../../../app/test/widgets/recording_speaker_selection_test.dart)
and the [before/after render manifest](../../../../.agent-artifacts/ui-evidence/lane-speakerrename/evidence.json).

Review fixes: live selection, optimistic labels and future live defaults use the exact
scope/provider-label pair, including through reconnects. Discovery excludes discarded
rows (also rechecked inside each assignment transaction). Episode membership is bounded
before hydration; the non-episode path uses the indexed `recording_speaker_scopes` array,
stamped before transcript encryption on every transcript write. It never scans historical
transcripts. Bounded origin/session queries also find historical unindexed members;
no production backfill is part of this PR. Budgets are 64 discovered members, 10,000 hydrated/target lines,
and 30 scopes per indexed lookup; over-budget requests fail before any assignment write
with HTTP 413 / `recording_speaker_limit_exceeded`.

Fan-out remains per-conversation transactional, with **per-conversation outcomes** in the
response. A late stale or failed member cannot turn earlier successes into a blanket 409;
mobile retains successful labels and rolls back only unsuccessful members (including Undo).
Same-value recording retries validate the current receipt, voice default and latest decision
map, then return without any writes, generation bump or learning job.

Coverage is conservative because legacy origin stamps and later index repairs can
both miss intermediate generations. `complete` additionally requires every discovered
member to have `recording_speaker_scopes_at_creation: true`, no excluded members,
and successful assignment of every member. Only transactions creating an absent
conversation stamp that marker when its transcript scope index is present (including
an empty live transcript). Ordinary writes preserve existing provenance but cannot
add it; rename repairs never set it. Thus indexed c0/c2 cannot certify an invisible
legacy c1. Any missing proof returns `partial`, and mobile reports only the available
conversations. This needs no generation-chain assumption, new query, index or migration.
