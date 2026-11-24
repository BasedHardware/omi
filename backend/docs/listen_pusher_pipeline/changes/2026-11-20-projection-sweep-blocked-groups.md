# Projection sweep blocked attempts

The integration reader appends `blocked_groups` to each contention sweep
summary. Each JSON array element contains a normalized reason, the committed
result's worker image digest and the number of blocked attempts. The counts
from both sweep pages sum to that summary's `blocked` total. Repeated attempts
count again. A sweep with blocks that would otherwise omit the contention
summary uses `action=sweep_blocked`.

Release deploys the reader through the normal backend-integration revision
rollout. After the revision has served for 30 minutes, run:

```sh
backend/scripts/projection_sweep_blocked_counts.sh "$PROJECT" "$REVISION"
```

An all-`unknown` digest window is valid reader evidence when committed results
lack producer provenance. An empty window or a per-sweep mismatch fails the
readback. Returning traffic to the previous revision restores its earlier log
format. The script requires a revision that emits the group array.

The M1 command test runs the release script on two real sweep summaries with
four synthetic blocked attempts. Both the plain-text and structured log paths
contribute to the same `unknown` bucket. Changing one summary's total makes
the command fail.

[Projection contention and replay](../../listen_pusher_pipeline.mdx#batch-projection-contention-and-replay) · [Reader PR #25885](https://github.com/BasedHardware/omi/pull/25885)
