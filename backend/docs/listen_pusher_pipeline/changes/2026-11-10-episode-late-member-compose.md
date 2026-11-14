# Episode composer: re-arm a composed closed episode when a member joins late

Default-on `EPISODE_COMPOSE_LATE_ATTACH_ENABLED` closes one gap in the class-7
finding of the 2026-11-10 Fable audit: episode notes written before the members
finish were not marked stale.

The settle job already re-arms a closed episode when a member finalizes
(`composer.schedule_for_conversation` compares the member's speech/name evidence
and stamps `compose_pending_since`). A sync intake attach can land after that
finalize and be suppressed by the attach memo, so the closed episode kept notes
that never saw the member. Production metadata on 2026-11-10 showed four sync
members attached to a composed closed episode with `composed_at` unchanged and
`compose_pending_since` empty.

`utils/episodes/late_member.py` is called from the two attach funnels:
`sync_attach.attach` (sync intake and the legacy rejoin) and
`batch_close.attach_closed_batch_capture` (batch audio close). It calls
`composer.schedule_for_conversation` after a member joins a **closed** episode
that already has `composed_at`. The call reuses the existing evidence compare:
it stamps `compose_pending_since` only when the member actually changed the
evidence, and the paid-once lease still dedupes. An unchanged fingerprint buys
no second paid compose. A live episode is untouched; it composes on close.

The signal has its own switch rather than riding `EPISODE_COMPOSER_THRIFT` (the
merged #25065 shipped it behind THRIFT). THRIFT is a cost control: turning it off
for cost reasons must not silently restore this correctness gap. Off restores the
previous attach behavior, where only a member finalize or a Home read could
notice the member.

Rollback: set `EPISODE_COMPOSE_LATE_ATTACH_ENABLED=false` (or `0`/`off`/`no`).
The attach path then behaves exactly as before. No data migration, no new
collection, no new index.

Tests: `backend/tests/unit/test_episodes_service.py` covers the legacy rejoin
path and the kill switch; `backend/tests/unit/test_episode_attach_review.py`
covers the recorded attach path and asserts a live episode schedules nothing;
`backend/tests/unit/test_episode_late_member.py` pins the switch as independent
of `EPISODE_COMPOSER_THRIFT`.
