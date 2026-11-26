# Retire the episode boundary experiment

The November 22 readback found 0% episode-boundary serving and an empty serving
allowlist on the sampled Cloud Run and GKE workloads. SCA-3692 removes the
experiment's hold and close overrides during listen rollover, its override of
episode joining, and its smart-merge veto. The existing silence timeout,
occasion span limit, recording rotation and episode review policy continue
to decide those paths. [Conversation lifecycle contract](../../listen_pusher_pipeline.mdx#2-conversation-lifecycle-silence-timeout-path)

The retirement removes `EPISODE_BOUNDARIES_MODE`,
`EPISODE_BOUNDARIES_MODE_SERVE_PERCENT`, `EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S`
and `EPISODE_BOUNDARIES_MODE_SHADOW_PERCENT`. Calls, relevance and the speaker
roster still consume shared evidence. The writer keeps its 5% sample and the
same `episode_boundaries_mode:shadow` salt so the same owners stay in the sample.
Calendar polling retains its 60-second bound. The authenticated endpoint and
account-erasure fence continue to protect evidence writes.

Paired fixtures exercise shared call and relevance inputs for sampled and
unsampled owners. The suite also checks poll cadence, owner isolation and the
erasure fence. [Boundary evidence tests](../../../tests/unit/test_episode_boundary_evidence.py)
