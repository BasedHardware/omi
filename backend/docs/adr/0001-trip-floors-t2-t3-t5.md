# 0001. Batch ramp trip floors for T2, T3 and T5

- Status: Accepted
- Date: 2026-10-25
- Deciders: two-lane rollout lead, rulings `9b89da` (T5, 07:35Z) and `6da743` (T3), under the product owner's soft latency bound (David, 2026-10-25 ~09:10Z) and the T1–T6-only ruling (05:12Z)
- Owner: infra (trip registry and backtests)
- Review by: 2026-11-01, or the 100% step, whichever is first

## Context

From 10-18 to 10-24, 23 of 39 batch ramp failures were the gate, not the product:
a p95 over n=3, 302.7s against a 300s limit, a single failed unit against a 2%
ratio. A ratio over a tiny denominator, or a latency threshold read as loss,
rolled prod back with no user harm. Accepted audio is durable while it waits, so
latency and recoverable holds are not loss.

## Decision

Trips are cohort-scoped (units the change admitted). Rollback authority requires
a passing backtest receipt; without one a trip acts as a freeze.

- **T2 lost speech.** Any single unrecovered unit of 120s or more: rollback, no
  floor. The 0.2% ratio of lost speech only counts once the denominator reaches
  3,600 speech-seconds. Only measured speech counts ([ADR 0002](0002-unknown-vad-freezes.md)).
- **T3 wedge.** An obligation older than 900s or a job older than 1,800s is
  FREEZE + alert at or below 50%, rollback only above 50%. Units whose latest
  decision is `allowance_exhausted` are policy holds and excluded. Backstops that
  always roll back: record latency p95 above 30 min sustained for 30 min; any
  admitted unit 2h without a terminal state; wedged units above 5% of admitted
  for 30 min, with at least 20 admitted.
- **T5 failed_held.** Rollback only when terminal batch units ≥ 50 AND
  failed_held ≥ 2 AND failed_held / terminal > 2%. Below the floor, > 2% is
  FREEZE + alert to the operator lane and the lead. Baseline: 1/168 (0.6%).
- T1 (custody) and T4 (route) have no floor: one event is real harm.

## Consequences

- Small denominators no longer roll back; they freeze expansion and page an owner.
- A real wedge still rolls back through the backstops, so the latency bound holds.
- Every floor change must be a parameter change plus one backtest run, recorded
  here as a superseding ADR.

## Implemented in

omi-workspace `infra/rollout/trips.toml` (`T2_*`, `T3_*` with
`freeze_at_or_below_percent = 50`, `T5_failed_held_over2pct` with its `thin`
case), read by `trip_backtest.py` and `ramp_controller.py`; the batch ramp
observer. The registry rows should cite `ADR-0001` (follow-up for infra).
