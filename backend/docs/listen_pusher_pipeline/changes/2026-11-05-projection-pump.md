# Dedicated projection discovery pump

The [serving projection contract](../../listen_pusher_pipeline.mdx#dedicated-projection-pump)
can select one projection-only loop without starting serving maintenance,
record admission or quarantine dispatch. Unset env preserves the existing three
serving loops, sweep cadence and eight owner drains. No deploy configuration is
changed here; service shape remains a separate decision.

The dedicated loop offloads each sweep to `sync_executor`, starts owed owner
drains on the event loop, and emits a heartbeat with successful sweep count,
requested owners and elapsed time on every tick, including failed ticks. Failures
log their exception type and retry on the next tick. Durable projection receipts
and advisory owner claims are unchanged.

Ramp owner: lead2, tonight (2026-11-05). Start with a pump service of N=3-4,
verify owner_drain rows/s stays at least 70% of pre-cutover and claim_busy ratio
does not exceed pre-cutover, then disable serving sweeps only after at least
30 minutes stable. Rollback: restore serving sweeps, disable the pump, and return
owner drain capacity to eight. This PR only adds code and unit coverage.
