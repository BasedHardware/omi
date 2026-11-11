# Expanded episode detail and follow-up tasks

David approved PR #25022 via relay-cl1 c3ee4c: full notes expanded, no Summary label,
follow-ups add canonical tasks. Member metadata carries the existing Home classifier
and structured overview, before neutralizing minimum titles. The existing lock bit
also travels with members so a direct detail read retains locked-row behavior. No new classifier,
query, index or task store. Contract: [episode projection](../../listen_pusher_pipeline.mdx).

The client reads full retained membership on opening detail so Home's below-floor
projection stays unchanged. Unknown classifications remain visible; only `noise`
folds. Discarded, deleted and merged donors stay hidden. Existing conversation rows
own navigation, paywall/locking, menus and swipe deletion; failed/retryable rows keep
their recovery presentation.

`mobile-episode-detail-redesign-disabled` is a default-false kill flag read through
the existing mobile analytics adapter (one-second bound). True restores the prior
layout on next page open. No remote row or rollout changes in this PR.

Follow-ups call ActionItemsProvider.createActionItem -> POST /v1/action-items with
conversation_id and Idempotency-Key. Since composer text has no item-level source
id, the first retained non-noise conversation anchors the episode-level follow-up
(falling back to the first retained member). Keys hash episode id and text; pending
and saved buttons disable further taps, and retries/reopens reuse the server key.

Evidence/tests: app/test/widgets/episode_redesign_render_test.dart,
app/test/widgets/episode_follow_up_test.dart, and test_episode_member_presentation.py.
Synthetic fixtures only; renders and their manifest live in
.agent-artifacts/ui-evidence/episoderedesign/.
