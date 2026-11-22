# 2026-11-20 Historical sit-down timing for V3 repair

An operator can run a bounded, single-owner `rederive-live` repair with
`--historical-sitdown` to group eligible historical conversations using a
900-second silence gap and a 3,600-second landing lock. Ordinary derive keeps
its existing timing.

The historical planner checks decoded speech across partition seams. It
refuses forced cuts, missing landing timestamps and unsettled stretches. The
repair run records its timing pair, and each derive attempt checks that the
worker has cohesion enabled and both matching timing settings.

## Rollout and rollback

`CONVERSATIONS_V3_BACKFILL` defaults to off. Historical sit-down timing also
requires an explicit operator opt-in and a settled window. Start with the
read-only estimate. Before scheduling an approved repair, verify all backfill
task workers serve this code and the matching settings. Pause dispatch before
routing an unfinished timed run to an older worker. Use `undo --run` for an
applied repair when its custody checks permit restoration.

## Verification

The [live re-derive tests](../../../tests/unit/test_conversations_v3_live_rederive.py)
cover timing opt-in, worker configuration drift, partition boundaries and
rollback. The worker reported 252 passing backend tests at `64a07d0`, including
the inherited rollback cases. [Hosted backend checks](https://github.com/BasedHardware/omi/actions/runs/44781277132)
are tracked separately.

[Recording-derived conversations V3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
· [Backfill and repair runbook](../../runbooks/conversations-v3.md#backfill-and-repair-per-owner)
