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
- Only the transport families classify as a re-strikeable loss
  (`persist_loss_is_restrikeable`, a `google.api_core` `GoogleAPIError`
  isinstance check). Every typed custody fault — `StagedAudioInvalid`,
  `StagedArtifactInvalid`, `RetainedAudioInvalid`, `BatchValidationError`,
  privacy fences (`BatchPrivacyBlocked`, `PermissionError`), the
  bounded-payload and owner-binding `ValueError`s — and every other
  non-Google exception aborts the lane on the spot and the legacy fail path
  runs byte-for-byte as before.
- The atomic contention family joined the lane
  (Failure-Class: FC-persist-contention-exhaustion-discards-completed-gpu-results)
  as its second admission arm, `persist_loss_is_contention`: the artifact
  register's exhausted fresh-transaction budget
  (`FirestoreContentionExhausted`) and any exception whose cause chain
  classifies as transaction contention (a raw read-time `Aborted`, an
  expired-transaction rejection). An aborted or expired chain is atomic and
  wrote nothing, so a re-strike cannot double-write — the arm is strictly
  safer to replay than the uncertain-outcome transport arm above, whose
  registered-but-unwritten tolerance already covers the full persist
  replay. The lane's strike budget and kill switch are unchanged; a lost
  lease, a privacy fence, a policy refusal and every custody class stay
  outside it. The legacy lane kept this class out on the documented premise
  that contention "never reaches this boundary as `Aborted`" — production
  disproved the premise before the register wrapper shipped
  (`error_class=Aborted stage=persist` at ~131/12h on the worker channel,
  2026-11-12), and after the wrapper lands the same storm arrives as the
  exhausted class. Either shape discards a fully produced GPU result into
  the lease-recovery re-run cycle for a wave the next strike rides out; the
  pump's publication lane re-strikes the identical class with the same
  budget (`publication_loss_is_contention`), and this boundary joins it.
- A contention strike also honors the storm damper's measured window. The
  store stamps the window its damper actually armed for the exhausted label
  onto the raised chain's `retry_after`; `persist_restrike_storm_after`
  reads that stamp and the lane waits
  `max(ladder step, min(stamped retry-after, storm cap))` — the cap is
  `PERSIST_RESTRIKE_STORM_MAX_SECONDS = 4.0`, the store damper's own window
  ceiling (`FirestoreStore.STORM_DAMPER_CAP_SECONDS`), pinned as a literal
  in `diarizer/batch_pipeline.py` — so the replay lands after the armed
  window instead of colliding inside it, exactly the alignment the pump
  publication lane applies. A wait never shortens below the documented
  ladder step, the attempt budget never grows, and an exhaustion with no
  stamped window (the damper disabled, a foreign store, a raw `Aborted`)
  keeps the ladder byte-for-byte.
- The bare builtin `TimeoutError` family joined the strikeable verdict
  (Failure-Class: FC-persist-socket-transport-loss-discards-completed-gpu-results).
  The boundary's own deadline guards raise it unwrapped — the upload
  stream's 15-minute deadline (`utils/batch_pipeline/upload_policy.py`
  raises `TimeoutError('batch artifact upload deadline exceeded')` when a
  resumable upload exceeds its stream budget) and the 30-second
  registration grace (`ArtifactStore._write` raises
  `TimeoutError('artifact registration too old to begin upload')`) — and
  raw socket read timeouts surface as `socket.timeout`, the builtin's
  alias on Python 3.10+. None of the three is a `GoogleAPIError`, so the
  former Google-only verdict booked each one as a custody-class fault and
  discarded a completed GPU result for a burst the next strike survives
  (the `event=batch_worker_failed error_class=TimeoutError stage=persist`
  sensor family). A timeout says this attempt ran out of time, not that
  the pinned bytes or a fence refused the unit: disk-shaped `OSError`
  faults stay custody, the custody list above is unchanged, and the
  strike budget and kill switch are unchanged.
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
