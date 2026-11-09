# Persist re-strike lane: a transport-lost result upload replays before the GPU does

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results

The worker persist stage encrypts the finished unit result, registers it in
the durable deletion outbox, and uploads it to the staging bucket. When that
Google API transport faults — production books
`event=batch_worker_failed error_class=InvalidArgument stage=persist` in
tight bursts on distinct units, with a fully silent 29-hour window in
between — the worker today discards a completed GPU result (decode, VAD,
diarization and ASR all done) and books a transient worker fault with no
evidence token. Lease recovery then re-leases the unit and re-runs the
entire GPU chain to re-produce a result the worker already held in memory.
Users wait out the re-lease for a conversation whose words were finished
minutes ago, and the wasted inference pass adds load that feeds the same
contention family the store is already defending against.

The persist stage is deliberately *not* a typed custody boundary: the
closed worker-validation vocabulary keeps persist unevidenced rather than
inventing a token, because a persist loss is a transport fault, not a
verdict about the audio. This lane keeps that contract — it gives the same
persist call more chances to land before the fallback, instead of
reclassifying the fault.

## What changed

- `diarizer/batch_pipeline.py` adds `PipelineWorker._persist_with_restrike`,
  a bounded lane around the persist call at both call sites (the serial
  chain and the IO-executor overlap path). The first call is the legacy
  persist byte-for-byte; a transport loss under the gate is re-struck on the
  documented doubling backoff — 0.25s at strike 1, 0.5s at 2, 1.0s at 3
  (capped at 2.0s; `PERSIST_RESTRIKE_MAX_ATTEMPTS = 3`) — the same schedule
  as the pump's publication re-strike lane. The lane runs on the IO
  executor thread the persist call already occupies, so it never blocks the
  event loop and never holds a GPU chain slot; it only extends one IO
  worker's occupancy by the backoff window.
- Only the Google API transport family classifies as a re-strikeable loss
  (`persist_loss_is_restrikeable`, a `google.api_core` `GoogleAPIError`
  isinstance check). Every typed custody fault — `StagedAudioInvalid`,
  `StagedArtifactInvalid`, `RetainedAudioInvalid`, `BatchValidationError`,
  privacy fences (`BatchPrivacyBlocked`, `PermissionError`), the
  bounded-payload and owner-binding `ValueError`s, and the upload-deadline
  `TimeoutError` — and every non-Google exception aborts the lane on the
  spot and the
  legacy fail path runs byte-for-byte as before. Firestore contention never
  reaches this boundary raw: the artifact register's transaction wrapper
  replays contention internally and raises
  `FirestoreContentionExhausted` (a `RuntimeError`), which lands here as
  non-strikeable and keeps its own recovery lane.
- Custody is unchanged and each strike is independently durable. The
  durable deletion outbox registers every attempt before its upload, so a
  strike that never lands leaves the same registered-but-unwritten
  reference the uncertain-upload path already tolerates, and a strike that
  lands returns its own generation-pinned URI from its own fresh sealed
  stream (fresh nonce, fresh object name, fresh upload deadline).
- Telemetry stays bounded and honest. Each re-strike logs
  `event=batch_persist outcome=restrike_wait attempt=N delay_ms=D
  exception_type=E` at INFO and a landed lane logs
  `event=batch_persist outcome=restrike_committed attempt=N`. The terminal
  `event=batch_worker_failed` ERROR line now fires only past the lane, so
  the sensor's true-loss semantics are unchanged: fewer lines mean fewer
  actual discarded results, not quieter failures.
- The worker fault line becomes attributable. The unclassified
  `event=batch_worker_failed` ERROR line now carries a `site=` suffix
  computed by `utils.batch_pipeline.errors.error_site_field` — the static
  source file and line closest to the raise, never an exception message and
  never payload content (the same field the projection error channels
  already carry). A persist family that today books
  `reason=unclassified` with no raise-site hint becomes routable to its
  exact hop (storage upload vs artifact register vs payload builder) in the
  next occurrence.
- `config/batch_pipeline.py` adds the
  `BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED` kill switch (default on),
  registered in `config/flag_budget.json` under the batch record lane /
  rollout lead owner.

## What deliberately did not change

- The closed worker-validation vocabulary stays closed: persist remains
  unevidenced (`transient_failure_evidence` keeps returning None for the
  stage), so the scheduler's evidence contracts, store validators and
  quarantine diagnostics are untouched.
- The pump's publication re-strike lane, the store-level contention retry
  and storm damper, the fetch_decode typed custody trio and the recovery
  sweeps are unchanged. This lane composes with all of them: a persist that
  survives via re-strike publishes exactly like a first-attempt persist; a
  persist that exhausts the lane feeds the same `fail` booking and recovery
  re-lease as before.
- Durable state, evidence booking, correctness meters, custody and the
  bounded retry ladder are unchanged. The lane only gives the existing
  persist call more chances to land before the fallback.

## Rollback

Set `BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED=false` to restore the
immediate fault for every persist loss: no re-strike, the worker books the
transient fault on the first exception, and lease-expiry recovery owns the
item exactly as before. The `site=` suffix is a log-shape addition and
survives the kill switch; sensor substring matches on the fault line are
prefix-based and unaffected.
