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

Tests: `tests/unit/test_episode_composer.py` exercises narrow triggers, genuine
late speech/name/membership/discard changes, settle/cap/restart behavior, read
promotion, stale/superseded retries, rollback and bounded metric labels.

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
