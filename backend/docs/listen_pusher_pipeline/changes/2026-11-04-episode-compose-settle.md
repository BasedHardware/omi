# Episode composer: coalesce background evidence changes

Default-on `EPISODE_COMPOSE_SETTLE_ENABLED` adds a narrow speech/name/membership
trigger and a 10-minute background quiet window capped at 25 minutes. The
[environment contract](../../listen_pusher_pipeline.mdx#closed-episode-compose-cost-control)
describes rollback. Foreground reads promote pending work immediately.

The full composed fingerprint, paid-once lease, prompt inputs and membership
attachment path remain intact. Pending arrival timestamps are separate composer
metadata, not recorded episode boundaries. The retry task holds no worker while
waiting, is cancelled with the backend's tracked tasks, and uses no new queue
infrastructure. Pending metadata survives restarts; a later finalize or read
reconstructs the process-local queue. The cap bounds debounce on a running
process; it is not a durable execution SLA during instance shutdown.

Persisted pending work remains eligible for read recovery when the switch is
off; it then composes immediately. With the switch on, a later trigger preserves
the original pending-time cap, and a read bypasses settling. Failed pending-state
writes fall through to scheduling and immediate composition with the existing
fingerprint/lease checks, emitting shared fallback telemetry rather than losing
speech or name changes.

When the process-local settle queue reaches 10,000 entries, new work also falls
through to immediate composition with the normal fingerprint and paid-once lease.
Existing queued work is retained. Shared `omi_fallback_total` telemetry records
`component="conversation_notes"`, `from_mode="episode_compose_settling"`,
`to_mode="episode_compose_immediate"`, `reason="capacity_full"`, `outcome="degraded"`
so operators can see saturation without leaving pending notes stale.

Phase-shadow mismatches during settling are expected: `needs_compose` sees
pending freshness work while the read-only phase projection still says
`COMPOSED`. This does not change the phase decision.

Tests: `backend/tests/unit/test_episode_composer.py` exercises narrow triggers, genuine
late speech/name/membership/discard changes, settle/cap/restart behavior, read
promotion, stale/superseded retries, rollback and bounded metric labels.

## Legacy rollout

An existing episode with no `composed_evidence` is seeded for free when its full
fingerprint still matches. If that fingerprint changed, it gets one conservative
compose behind the background quiet window: the old hash cannot distinguish
new speech from label-only drift. Skipping that first uncertain change could
silently lose real late speech. After success the narrow gate applies normally;
there is no eager recompose wave or historical-data migration. Migration and
unchanged-fingerprint backfill are covered by the composer tests.

## Verify after deploy (operator follow-up; no deploy in this change)

Compare equal windows after the deployed revision is serving traffic, allowing
one complete 25-minute settle interval before interpreting savings:

- `sum(increase(omi_episode_compose_total{outcome="composed"}[24h])) /
  sum(increase(omi_episode_closed_total[24h]))`: currently about 19; should fall
  substantially. Also sum paid outcomes `composed|superseded|error|stale`.
- Compare `superseded`, `stale`, `error` and new `settling` outcomes. Confirm the
  skipped-trigger counter increases for `reason="evidence_unchanged"`.
- Check real late speech, membership and discard changes still update notes;
  opening the page must bypass debounce. Count latency separately from savings.
- From the Omi workspace, use `source ~/.local/bin/gcp-agent-env.sh ro-prod`
  then `python3 avo/firestore-reads/measure.py --hours 3` for aggregate caller
  rows. Compare `conversations:get_conversation`, `conversations:get_conversation_photos` and
  `episodes:get_episode`
  caller rows by service and collection against an equal baseline window, and
  check the caller-coverage/overflow fields. These are shared callers: attribute
  savings using skipped triggers and a stable finalize volume, not their raw
  totals alone. No account documents are needed.

Expected overlap-adjusted savings: $60–150/day in model spend. The design handoff
estimates 0.3–0.7M fewer conversation reads/day from gating roughly 108k no-op
composer evaluations; treat that as a pre-deploy estimate, not measured savings.
New real changes add small pending-state reads/writes, so verify net caller rows.
