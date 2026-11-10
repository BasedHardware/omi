# Episode composer: keep paid composes

Default-on `EPISODE_COMPOSER_THRIFT` stops throwing away composer calls that
were already paid for. It is the first item of the 2026-11-10 LLM-efficiency
report (`data/run-2026-11-08-pipeline-refactor/fable-llm-efficiency-2026-11-10.md`,
section 4). The [environment contract](../../listen_pusher_pipeline.mdx#closed-episode-compose-cost-control)
describes rollback.

## What changes

- **One repair retry on a parse failure.** The retry prompt carries only the
  malformed reply, never the transcripts or member summaries. The facts are
  already in the reply, so re-sending the episode would pay for the same input
  twice. A repair that also fails is a second paid failure.
- **A short episode may ship a title and lede with no chapters.** "Short" is at
  most 15 minutes of recorded member time (`COMPOSER_SHORT_EPISODE_SECONDS`).
  The lede is the page; a sectionless reply is not a failed compose. A longer
  episode with no sections is still a failed compose.
- **A superseded result is stored, not discarded.** When a member arrives, a
  transcript upgrades or a discard lands during the call, the paid result is
  written and the episode is marked pending (`compose_pending_since`). The
  settle timer refreshes it with the new evidence. A compose that landed after
  this call started is never clobbered (`composed_at` guard).
- **Paid failures stop at two per evidence** (`COMPOSER_MAX_PAID_FAILURES`).
  One attempt plus one repair retry is the whole budget; a third paid failure
  on the same evidence cannot produce a different result. New evidence starts
  the count again.

## Trigger label

`omi_episode_compose_total` and `omi_episode_compose_seconds` now carry a
bounded `trigger` label: `close`, `read`, `member_final` or `settle`. A new
`omi_episode_compose_calls_total{trigger,outcome}` counts each paid model call,
including `trigger="repair"`, so the repair share and the origin of composes are
visible. Labels are bounded; no uid is ever a label.

## Rollback

Set `EPISODE_COMPOSER_THRIFT` to `false`, `0`, `off` or `no`. That restores
the previous behavior: no repair retry, a sectionless reply is always a failed
compose, a superseded result is discarded, and the four-failure cap
(`COMPOSER_MAX_FAILURES`) applies. The trigger labels stay; they are additive
telemetry.

## Tests

`backend/tests/unit/test_episode_composer.py` covers the repair retry and its
prompt contents, a failed repair counting two paid failures, the two-failure
cap, short-episode acceptance, long-episode rejection, superseded results stored
and pending, the kill switch restoring each old path, and the trigger labels for
close/read/member_final/settle/repair.

## Verify after deploy (operator follow-up; no deploy in this change)

Compare equal windows after the deployed revision is serving traffic, allowing
one complete 25-minute settle interval before interpreting savings:

- `sum(increase(omi_episode_compose_calls_total[24h]))` by `trigger`: the
  `repair` share should be small and the `close`/`member_final` split should
  match the report's repair-wave inference.
- `sum(increase(omi_episode_compose_total{outcome="error"}[24h]))` and
  `{outcome="superseded"}` should fall; `composed` should hold or rise.
- `sum(increase(omi_episode_compose_total{outcome="composed"}[24h])) /
  sum(increase(omi_episode_closed_total[24h]))` should fall toward one.
- Check that a short episode with a lede and no chapters renders, and that a
  superseded episode shows the kept summary until its settled refresh.

Expected saving: about 4,800 composer calls a day, near 16% of composer spend
(the report's measured errors, superseded and conflict share). Treat that as a
pre-deploy estimate, not measured savings.
