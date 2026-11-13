# Privacy-purge lane storm gate

The privacy-purge lane's three transactions — the per-job unlink
(`batch_purge_job_unlink`), the owner fairness sweep
(`batch_purge_owner_fairness`) and the erased-result watermark write
(`batch_purge_result_erase`) — write the same hot
`control`/`queues`/`owners`/`jobs`/`results` rows the batch-store labels
storm on. The lane used to hand each body to a bare `client.transaction()`:
no retry ladder, no storm damper, and the SDK's default same-id commit loop
replaying one transaction id inside whatever contention window the store
lane had already measured — the exact collision the damper exists to space
out, with an expiry retirement the SDK never retries and an anonymous
exhaustion that named no label, armed no window and adopted no fleet view.

## Behavior

`run_purge_transaction` joins the process storm damper the same way every
batch-store entry and the projection and retention lanes do:

- Entry consult: before its first attempt, the chain waits out the label's
  residual window (fleet-adopted, spill share-capped; logged at INFO as
  `event=batch_purge_job_unlink_backoff`,
  `event=batch_purge_owner_fairness_backoff` or
  `event=batch_purge_result_erase_backoff`). The first attempt is never
  gated.
- One fresh transaction per rung: the SDK same-id replay is gone — the
  bounded engine owns the whole budget (five bodies, not five replays of
  one id), so an expiry retirement and an exhaustion are both recoverable
  and attributable.
- Mid-ladder spacing: every rung after a measured collision re-peeks the
  label's residual and adds it to the rung's equal-jitter wait (logged as
  `scope=mid_ladder`); from the third failed rung the rung also spaces
  itself by the store damper's capped wave ladder.
- Exhaustion stamp: when the chain exhausts, the damper's applied window is
  stamped onto the raised `FirestoreContentionExhausted.retry_after` and
  the label's window is armed, so the purge's next re-strike — and the
  store lane's next entry of that label — lands after the window. A purge
  that measures a storm now damps the lanes it was colliding with, instead
  of feeding them.
- Success clearing: a committed purge write clears the ladder only when no
  concurrent arm bumped the generation since the entry consult.

The damper is resolved per call through `_purge_storm_damper`, which reads
`shared_storm_damper(namespace)` — the same process-shared, fleet-mirrored
damper every store of the namespace uses — and therefore returns `None`
while either contention kill switch is off. A dormant damper leaves the
bare bounded ladder byte-for-byte: five fresh transactions, equal-jitter
rungs, nothing recorded, and the historical row effects unchanged (objects
erase before metadata; `mirror_refresh` still runs only after a committed
chain).

Failure-Class: FC-privacy-purge-chain-collides-inside-armed-storm-window
