# Dedicated projection discovery pump

The [serving projection contract](../../listen_pusher_pipeline.mdx#dedicated-projection-pump)
can select one projection-only loop without starting serving maintenance,
record admission or quarantine dispatch. Unset env preserves the existing three
serving loops, sweep cadence and eight owner drains. No deploy configuration is
changed here; service shape remains a separate decision.

The dedicated loop offloads each sweep to `sync_executor`, schedules discovered or owed
projection follow-ups with `start_followups()` and the owed index flush after
each sweep, starts owed owner drains on the event loop, and emits a heartbeat with successful sweep count,
requested owners and elapsed time on every tick, including failed ticks. Failures
log their exception type and retry on the next tick. Durable projection receipts
and advisory owner claims are unchanged.

Hard bounds: pages 1-4, tick sleep 2-60 seconds, owner drains 1-16. Defaults
remain pages 1, tick 20 seconds and owner drains 8; malformed env keeps defaults.

Ramp owner: lead2, after David's deployment-shape decision. Safe start: a
**dedicated service**, N=4 instances, pages 1, tick 2 seconds, MAX_OWNER_DRAINS 8.
Never enable the pump on backend-integration itself: the selector is service-wide.
Serving sweeps stay ON until owner_drain advanced is at least 20 rows/s for
30 minutes. Before switching them off, install and verify a dedicated-service
missing/stale alert on `omi_batch_projection_pump_last_tick_seconds` (Unix time,
zero before the first completed tick; updated even on failed ticks).

Retain the read-rate alarm above +50% of pre-cutover and the owner_drain rows/s
floor of 70% of pre-cutover. Watch sweep elapsed time and executor saturation.
Evaluate claim_busy share (no higher than pre-cutover) after serving sweeps are
switched off, not during dual-running. If the gate is unmet, serving sweeps stay ON.

Rollback is env only, through new revisions: restore serving sweeps ON on the
existing service **first**, then set pump=false on the dedicated service and
owner drain capacity back to 8. This PR only adds code and unit coverage.
