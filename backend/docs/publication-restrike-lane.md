# Publication re-strike lane: a contention-lost transition replays before the GPU does

Failure-Class: FC-publication-contention-discards-completed-gpu-results

Every worker publication transition — `batch_complete`, `batch_fail`,
`batch_defer` — is a lease-fenced single-document transaction behind the
store's bounded five-attempt contention budget. When that budget exhausts,
the pump's catch site marks the segment lost and logs
`event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted`.
The durable fallback is correct but expensive: the lease expires (up to
120 seconds), lease recovery re-leases the unit, and the worker re-runs the
entire GPU chain — decode, VAD, ASR, persist — to re-produce a result the
pump already held in memory. Users wait out the expiry plus a full
inference pass for a conversation whose results were finished minutes ago;
the wasted GPU pass also adds load that feeds the same contention family.

## What changed

- `utils/batch_pipeline/pump.py` splits the legacy `_publish` try body into
  `_publish_transition` (the same single fenced scheduler call, verbatim)
  and adds `_restrike_publication`, a bounded lane that replays exactly the
  transition that lost — never a re-derived one — with the documented
  doubling backoff: 0.25s at re-strike 1, 0.5s at 2, 1.0s at 3 (capped at
  2.0s; `PUBLICATION_RESTRIKE_MAX_ATTEMPTS = 3`). The whole lane stays an
  order of magnitude under the 120-second lease window, so the fence that
  authorized the first attempt still authorizes the re-strike.
- Only the bounded contention budget classifies as a re-strikeable loss
  (`publication_loss_is_contention`): `FirestoreContentionExhausted` —
  including the Postgres job-store subclass — and any exception whose cause
  chain is atomic transaction contention (`Aborted`, expired-transaction
  retirement). A revoked lease, an admission refusal or a real write
  failure aborts the lane on the spot and the legacy catch site runs
  byte-for-byte as before.
- Safety rides the production lease fence. Each re-strike is the same
  fenced transaction, so if the lease died while the lane waited, the
  transition is rejected exactly like a stale replay and the pump returns
  False without a lost marker — the durable decision, not a lane verdict.
  `batch_complete` is additionally idempotent on replay: a job already in
  `result_ready` re-answers `matches_persisted`, closing the ambiguous
  commit window instead of double-committing.
- Telemetry stays bounded and honest. Each re-strike logs
  `event=batch_publication outcome=restrike_wait attempt=N delay_ms=D
  exception_type=E` at INFO and a landed lane logs
  `event=batch_publication outcome=restrike_committed attempt=N
  accepted=true|false`. The terminal
  `event=batch_completion outcome=retry` ERROR line now fires only past the
  lane, so the sensor's true-loss semantics are unchanged: fewer lines
  mean fewer actual discarded results, not quieter failures.
- The lane waits through `asyncio.sleep` only (never a blocking sleep),
  holds one publication-concurrency gate slot while it runs, and composes
  with the store-level storm damper: a re-strike that lands inside an
  armed damper window waits out the residual spacing inside
  `store.run` exactly like any other entry of the label.
- `config/batch_pipeline.py` adds the
  `BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED` kill switch (default on),
  registered in `config/flag_budget.json` under the batch record lane /
  rollout lead owner.

## What deliberately did not change

- The deferred publication-drain lane (the `batch_merge_drain` family) is
  untouched: it converges the owner's ordered merge after an accepted
  publication; the re-strike lane recovers the publication transition
  itself. They compose — a drain after a re-struck publication behaves
  exactly like a drain after any accepted publication.
- The `batch_merge outcome=retry` line at the drain lane's attempt cap is
  unchanged, as is every non-publication catch site.
- Durable state, evidence booking, correctness meters, custody and the
  lease-expiry recovery loop are unchanged. The lane only gives the
  existing transition more chances to land before the fallback.

## Rollback

Set `BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED=false` to restore the
immediate fallback for every publication loss: no re-strike, the catch site
marks the segment lost on the first exception, and lease-expiry recovery
owns the item exactly as before.
