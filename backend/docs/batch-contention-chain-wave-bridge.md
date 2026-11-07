# Batch contention chain: the delay schedule bridges one abort wave

Status: shipped on the batch record lane. Owner: batch record lane / rollout lead.

## What problem this solves

The bounded contention chain (`database/firestore_transaction_retry.py`) gives
one Firestore transaction five attempts. Its inter-attempt gaps are equal-jitter
draws whose high bound doubles per attempt; under the former 1.0 s cap the four
gaps of the default chain summed to 1.2-2.4 s. A contention storm on one hot
document lasts as long as its writers keep committing — routinely longer than
that window — so every attempt landed inside the wave, the chain ended at
`firestore_transaction_contention operation=... attempt=5/5 outcome=exhausted`
(the largest worker error family in the Loop S sensor, x2239/30m at its peak),
and only the NEXT store entry — the storm damper's spaced re-strike — ever
found the document quiet. The chain itself never got a chance to land after
the wave it was fighting.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave

## Design

The delay cap `_MAX_DELAY_SECONDS` moves from 1.0 s to 4.0 s:

- Attempts 1-3 keep their exact former rungs (`0.2s / 0.4s / 0.8s` high
  bounds): a transient single-abort collision still recovers immediately and
  the default three-attempt inner chain (`database/_client.run_transactional`)
  is bit-for-bit unchanged.
- The fourth rung grows from 1.0 s to 1.6 s (high bound), so the default
  five-attempt chain's gaps now sum to 1.5-3.0 s and attempt 5 can start up
  to 3.0 s after the first abort — past waves that the former schedule
  exhausted inside (attempt 5 started at 2.4 s at maximum jitter).
- From the sixth attempt the former cap flattened every rung to 1.0 s. The
  4.0 s cap restores the doubling ladder's tail (`3.2s, 4.0s, ...`) for the
  longer opt-in budgets (`max_attempts >= 6`, e.g. the `transient=True`
  callers), and matches the ceiling the store-level storm damper
  (`FirestoreStore.STORM_DAMPER_CAP_SECONDS`) already ships for
  post-exhaustion spacing — one agreed scale for "how long a store entry may
  wait on a hot document".

The wave bridge and the damper divide the storm honestly: the chain tries to
land after the wave inside its own budget; only a chain that still exhausts
arms the damper's per-label spacing. Deadline-scoped callers (the sync
handler, the projection claim lease) are unchanged. They are the only callers
whose wall clock this change could ever touch, and their reserve gate is
unchanged:: the 30 s reserve floor
still dominates the 4 s cap, so a retry the gate admits can always afford its
jitter sleep, and the accepted `deadline + one in-flight attempt` bound holds
at maximum jitter.

## Rollout

No flag. The change is observable only as fewer `outcome=exhausted` chains
during storms and slightly longer no-deadline chains (bounded by the rung
table above); the kill switches that already govern this path
(`BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`,
`BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED`) are unchanged, and with
retry disabled the chain does not run at all. Rollback is reverting the single
constant plus its documentation.

## In-tree coverage

- `tests/unit/test_contention_retry_wave_bridge.py` — the bridged-wave
  recovery scenario, the rung table and budget windows.
- `tests/unit/test_contention_retry_rung_table_pin.py` — the rung table rung
  by rung, former-schedule comparisons, gap sums for chains of every depth.
- `tests/unit/test_contention_retry_deadline_gate_matrix.py` and
  `tests/unit/test_contention_retry_deadline_wave_bounds.py` — the reserve
  gate, sleep truncation and accepted wall bounds.
- `tests/unit/test_batch_store_wave_bridge_recovery_parity.py` — the store
  boundary: a bridged wave never arms the damper; a storm still does.
- `tests/unit/test_batch_exhaustion_publication_contract_matrix.py`,
  `tests/unit/test_batch_merge_and_recover_authority_contracts.py`,
  `tests/unit/test_batch_wave_bridge_twin_and_chain_boundaries.py`,
  `tests/unit/test_batch_wave_bridge_docs_taxonomy_parity.py` — the caller
  contracts, twin independence and docs/log taxonomy parity.
