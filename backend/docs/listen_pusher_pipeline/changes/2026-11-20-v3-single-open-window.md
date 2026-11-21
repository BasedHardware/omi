# One open conversations v3 window per owner

## What changed

`commit_projection` rejects a plan with multiple `in_progress` rows. Page continuation,
future-dated speech, and fresh fragments split around published rows could each produce such
a plan. Reconcile parked the owner and could keep rejecting the same plan after backoff,
leaving Home stale.

The planner lets only the latest stretch remain open. When it preserves published speech,
only the fresh fragment that reaches the original window's final line can inherit its open
state. If the final line belongs to a finished row, a fresh prefix can enter processing
on that pass. The change uses the existing line ownership and audio claim rules.

## Rollout and flags

The original planner fix merged on November 19 in [PR #25800](https://github.com/BasedHardware/omi/pull/25800).
The follow-up ships with the regular backend rollout. Neither change introduces a flag or
changes conversations v3 admission. The shared runtime source sets `CONVERSATIONS_V3_STAGE=beta`.
Rollback is a code revert.

Check serving revisions on the reconcile runtimes before measuring recovery. Pending work is
retried after lease backoff, and a successful commit clears the park. Within an hour of serving,
check that leases parked for `multiple_open_conversations` and the rate of
`omi_conversations_v3_blocked_total{reason="multiple_open_conversations"}` fall to near zero.

## Evidence

- The [original PR](https://github.com/BasedHardware/omi/pull/25800) records the production baseline and read-only replay.
- The [fragmentation regressions](../../../tests/unit/test_conversations_v3_fragmentation.py)
  cover continuation, interleaved published speech, and an open stretch ending in retained speech.
- See the [pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
  and the [reconcile runbook](../../runbooks/conversations-v3.md) for admission, lease backoff, and counters.
