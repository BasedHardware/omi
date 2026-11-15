# Skip recorded-boundary work for placed sync retries

Variant F now checks existing conversation placement after admission, stored privacy,
and short-speech gates, before querying recorded candidates, reading an episode,
or evaluating the boundary. A placed sync/late retry keeps its existing placement
without repeating that decision work. Cohort and kill-switch behavior is unchanged.

Source: Cubic P2 on [PR #24828](https://github.com/BasedHardware/omi/pull/24828).
Regression: `test_a_conversation_already_placed_is_never_asked_about_again`
in `backend/tests/unit/test_episode_f_join.py` rejects candidate queries,
episode reads, and boundary evaluation when the placement guard fires.

Contract: [Occasion conversations (episodes cohort)](../../listen_pusher_pipeline.mdx#occasion-conversations-episodes-cohort) in the pipeline contract, with the episode service in [`backend/utils/episodes/ARCHITECTURE.md`](../../../utils/episodes/ARCHITECTURE.md).

Rollback: revert this change. No new flags or rollout steps.
