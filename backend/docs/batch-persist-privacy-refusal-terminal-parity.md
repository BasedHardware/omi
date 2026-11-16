# Persist privacy refusal: typed custody instead of an anonymous worker fault

`error_class=BatchPrivacyBlocked stage=persist reason=unclassified` and the
pump lanes' `event=batch_pump outcome=retry exception_type=BatchPrivacyBlocked`
burn because the transactional privacy authority refuses units and lane steps
whose owner's account, data-protection setting, privacy generation or
conversation state changed while the unit's GPU window ran. The fence reads
the live documents inside the persist register's transaction — after decode,
VAD, diarization and ASR are all done — and refuses the unit's server
results. The refusal is deterministic on identical input: the pinned bytes,
payload and identity fields that produced it are exactly what every replay
sends. It is user intent, not a worker fault.

Failure-Class: FC-privacy-refusal-at-persist-walks-gpu-retry-ladder-as-unclassified-worker-fault

## What changed

### The GPU worker's persist boundary

- The persist booking boundary reads the fence's type through a dedicated
  classifier (`persist_loss_is_privacy_refusal` in
  `diarizer/batch_pipeline.py`) — never the refusal's message or its bounded
  reason token — and books the typed `persist_privacy_refused` custody
  handoff: a `ValidationFailureWork` with the closed
  `{stage: persist, reason: persist_privacy_refused}` pair, the same terminal
  route the `persist_payload_invalid` refusal rides. The chain ends at the
  first occurrence: one persist call, no re-strike sleeps, one GPU pass, the
  failure callback contract unchanged.
- The closed vocabulary gains the token
  (`WorkerValidationReason.PERSIST_PRIVACY_REFUSED`), so the per-attempt
  evidence, the store validators and every terminal key off the enum with no
  other code change. The token joins `VALIDATION_DISPOSITION_PERSIST_REASONS`
  in `utils/batch_pipeline/errors.py`, stage-scoped to `persist` like its
  payload-refusal sibling: the privacy authority raises inside the persist
  register's transaction, so the same token at any other stage — and a
  foreign shape at persist (the transport/contention families, `unknown`) —
  keeps its fault classification.
- All three fault channels demote together through the existing disposition
  family: the worker's fault line reports
  `event=batch_validation_disposition outcome=recovery_handoff` instead of
  `event=batch_worker_failed error_class=BatchPrivacyBlocked`, and both
  scheduler terminals (the verdict terminal and the recover sweep's
  lease-expiry cap terminal, which share `report_terminal_quarantine`)
  report `outcome=held_for_disposition` on INFO instead of the anonymous
  `batch_quarantined reason=worker_failed` ERROR line. The demotion is
  unconditional on pinned identity, like the payload refusal's.

### The pump's lane and maintenance loop

- A lane pass or maintenance sweep that meets the same fence mid-pass used to
  fall into the generic fault arm: the ERROR
  `event=batch_pump outcome=retry exception_type=BatchPrivacyBlocked` /
  `event=batch_maintenance outcome=retry exception_type=BatchPrivacyBlocked`
  line fired once per idle cycle forever, because every replay of the same
  step raises the same deterministic refusal. Both loops now carry a typed
  `BatchPrivacyBlocked` arm ahead of the generic fault arm: they report
  `outcome=privacy_blocked` on INFO (the `site=` field keeps any lane leak
  observable), take the normal idle backoff, and keep serving every other
  owner. Real faults keep the ERROR retry lines byte-for-byte; a refused
  unit itself is settled by the scheduler's park and the recovery sweep's
  fence-first privacy check, exactly as before.

### Custody semantics downstream (unchanged)

- The unit quarantines on attempt one with `recovery_state=held`, and the
  fenced recovery lane's own transactional privacy check runs before any
  recognition, so a refused unit settles through the existing
  revocation-only write without re-recognition. The persist transport and
  contention families keep their verdicts; a plain `RuntimeError` carrying a
  privacy-shaped message is not the fence and stays a retryable worker
  fault.

## Runbook

- `stage=persist reason=unclassified` privacy-shaped worker-fault lines and
  the pump/maintenance `exception_type=BatchPrivacyBlocked` ERROR retry
  lines should decay to zero after deploy; a residual rate points at a
  persist or lane path that reaches the fence outside the register
  transaction.
- The units now surface as
  `event=batch_validation_disposition ... stage=persist
  worker_reason=persist_privacy_refused` on INFO and settle in the recovery
  sweep's fence-first scan; they are refused, not lost — no audio is
  persisted for them by design, matching the owner's deletion/privacy
  change.
- Genuine transport and contention faults at persist keep their existing
  ERROR channels; only the deterministic privacy refusal joined the closed
  vocabulary, and only its lane reports demoted.
