# Bound v3 live stretches to three hours

Continuous background speech can keep resetting the silence and lock clocks.
The first line whose recorded start is at least three hours after the
stretch's first line starts a new stretch. The planner preserves the cut even
if the outline tags the next conversation as a continuation. The earlier live
stretch locks independently of new speech landing in the same recording, and
its windows proceed through normal processing. The successor can stay live.

The [v3 runtime contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
documents the default-on switch and its rollback. The live builder increments
`omi_conversations_v3_window_cap_cuts_total` when a committed cap boundary
creates a successor, so repeated reconciliation of the same successor does
not increment it. For release readback, check the increase in this counter and
verify that no live window exceeds three hours plus the configured lock delay.
