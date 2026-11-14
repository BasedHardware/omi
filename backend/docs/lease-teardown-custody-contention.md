# Flight-teardown custody reports on its honest channel

A GPU flight ends in four best-effort fenced store calls: the stop refund
(claimed behind a sibling's chain when SIGTERM or a fatal GPU error
arrived), the GPU-restart refund (`FatalGpuError`), the skipped refund (a
cancelled or lost decode's siblings) and the finished-lease release. Each
has a durable fallback that is the lease window itself: a lost refund lets
the unit wait out the lease until the fenced recovery sweep re-queues it,
and a lost release holds the fence past work that is already done.

All four sites booked every exception on the ERROR fault channel:

- `event=batch_flight outcome=lease_recovery` (stop and skipped refunds)
- `event=batch_gpu_restart outcome=lease_recovery`
- `event=batch_flight outcome=lease_release`

A contention loss on any of them is the designed fallback engaging, not a
worker fault. During a store storm each refunded or released lease reached
the production error sensor once more per flight teardown, on top of the
retry engine's own `firestore_transaction_contention outcome=exhausted`
storm signal — the same double-booking the pull lane
(`event=batch_pull outcome=backoff`, INFO), the deferred publication-drain
lane (`event=batch_merge_drain outcome=maintenance_backstop`, WARNING) and
the publication re-strike lane already retired.

## The contract now

`utils/batch_pipeline/teardown_custody.py` owns the family:

- `TEARDOWN_SITES` — the closed site table. Each frozen row names the
  historical event prefix and outcome token the site has always rendered
  (`lease_release` and both refund rows stay on `event=batch_flight`; the
  GPU-restart row keeps `event=batch_gpu_restart` with the ordinary
  `lease_recovery` token), the honest channel a closed contention loss
  reports on (`lease_release` → INFO, all refunds → WARNING), and the
  site's total attempt budget: the two live refund sites replay
  (3 total attempts), the GPU-restart refund and the release are
  single-attempt because their flight is already ending.
- `teardown_loss_is_contention` — the closed contention class:
  `FirestoreContentionExhausted` (including the Postgres job-store
  subclass) plus any exception whose cause chain classifies as atomic
  transaction contention — exactly the class the publication re-strike
  lane replays under.
- `contention_operation_field` — the losing store label stamped by
  `FirestoreStore.run`, moved here from `scheduler.py` (which re-exports
  it) so every contention reporter reads the same stamp the same way.
- `teardown_storm_after` — the measured storm window a replay must land
  after: the `retry_after` the store's damper stamped on the raised
  exhaustion, clamped at the store damper's own 4.0s window cap. Hostile
  or unstamped shapes return 0.0; never raises.
- `teardown_replay_delay` — the bounded doubling ladder (0.25s, 0.5s,
  capped at 2.0s) a replay waits before its next attempt.
- `report_teardown_custody_loss` — books one loss on its row's channel
  carrying the losing store label, the sanitized attempt and the storm
  window the damper had armed (`retry_after_ms`, `0` when unstamped).
- `replay_teardown_refund` — runs one site's fenced call to its row's
  budget. A closed contention loss replays on the ladder with every wait
  raised to the measured window (`max(ladder, storm)`), so the replay
  lands after the armed window instead of colliding inside it; the whole
  replay runs synchronously on the db-executor thread the fenced call
  already occupies (the same blocking-sleep precedent the re-strike
  lane's entry consult set). The replays stay silent, so a storm that
  converges logs nothing; past the budget the loss is reported once and
  the lease-expiry backstop owns the unit exactly as before. A
  non-contention fault reports on the historical fault line immediately
  without replaying — re-striking a real failure would only replay the
  same refusal.

The pump's four exits now drive `replay_teardown_refund` with their row:
a lost refund replays instead of stalling its unit for the full lease
window, and every contention loss reports on the honest channel.
Everything else — a revoked lease, an admission refusal, a real write
failure — keeps the historical ERROR line byte-for-byte. No durable
state, custody or metrics behavior changed; only the report channel, the
report fields and a lost refund's wait did.

## Suites

- `tests/unit/test_teardown_custody_family.py` (behavior: site table,
  classifier, storm reader, ladder, reporter, replay loop)
- `tests/unit/test_teardown_custody_pump_wiring.py` (live pump flight
  paths: release, GPU-restart refund, stop refund)
- `tests/unit/test_teardown_custody_source_pins.py` (site wiring and the
  moved label helper)
- `tests/unit/test_teardown_custody_grid_band_*.py` (frozen taxonomy
  grid: every (site × exception shape × storm stamp × store label ×
  attempt) tuple re-driven through the real boundary against its
  emit-time cross-verified expectation)

Failure-Class: FC-flight-custody-contention-losses-booked-as-production-faults
