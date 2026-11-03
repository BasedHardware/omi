# No-engine phones use the existing on-screen preview

A granted phone can have no usable on-device speech engine. The Dart app now
reports that terminal verdict before its ordinary refusal flush and stops
requesting local preview for the rest of the capture. Listen rescinds the grant
one-way and may attach visible Modulate restore. Raw custody and batch record
ownership are unchanged.

Wire ordering, the closed counter labels, and the default-on
`LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED` kill switch are documented in the
[mobile local-preview contract](../../listen_pusher_pipeline.mdx#mobile-local-preview-lane-kill-switch-default-on).
The existing restore cohort and durable server batch ownership remain required;
15 seconds visible dwell and hide-to-close keep the cost bound on screen.

The rollout lead deploys the server first, then ships the Dart mobile build.
PR #24508 was open when implementation started; its server-batch-only grants and
grant-based restore gate compose with this declaration-and-grant rescind.

Evidence: `tests/unit/test_local_preview_lane.py`,
`tests/unit/test_visible_restore.py`, and the app's local-preview admission,
routing, controller, and fixture-render tests. No production access or deployment
is part of this implementation lane.
