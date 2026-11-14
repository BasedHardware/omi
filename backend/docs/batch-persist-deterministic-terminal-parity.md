# Batch persist deterministic terminal parity

Failure-Class: FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument

A completed GPU unit whose persist call the storage upload or the artifact
register refused with a 400-class ``InvalidArgument`` used to ride every
retry the platform owns: the re-strike lane burned its three in-process
strikes against the identical payload, the boundary booked an ordinary
retryable worker fault with no closed token, the job ladder re-ran the full
GPU pipeline — fetch, decode, VAD, windows, diarization, ASR, assembly —
four more times only to raise the same refusal at the same boundary, and
the exhausted unit terminal-quarantined with the anonymous
``stage=unknown worker_reason=unclassified`` shape before the lease-recovery
re-run fed the same bytes through the whole cycle again. In production this
surfaced as the ``event=batch_worker_failed error_class=InvalidArgument
stage=persist`` signature burning per attempt for units whose answer was
decided by their own request payload, plus four wasted GPU attempts per
stuck unit.

## What changed

- A persist refusal that identical input reproduces is now deterministic at
  the boundary. ``diarizer.batch_pipeline.persist_loss_is_deterministic``
  answers for the 400-class ``InvalidArgument`` the persist APIs raise for
  the unit's own request payload, read through the shared contention
  classifier so the verdict never depends on exception wording.
- The boundary books the refusal as the typed custody handoff the decode
  trio already rides: ``ValidationFailureWork`` with the closed
  ``{'stage': 'persist', 'reason': 'persist_payload_invalid'}`` evidence.
  The chain ends at its first occurrence — attempt economics match the
  decode trio — and the unit's audio custody stays intact for the fenced
  independent-recognizer recovery lane, whose fresh provider payload is
  exactly the escape the deterministic refusal could never produce
  in-place.
- Both fault channels demote the designed handoff: the worker's
  ``batch_worker_failed`` ERROR line and the scheduler's terminal
  ``batch_quarantined`` ERROR line report
  ``event=batch_validation_disposition`` instead, keeping every diagnostic
  field the fault channel carried. The arm is stage-scoped and
  unconditional like the fetch_decode trio: the persist refusal raises
  nowhere else, and a storage outage, a transport loss or the contention
  family at the persist stage keeps its real-fault ERROR classification.
- The expired-chain shape is untouched: a retired Firestore transaction
  reports itself as ``InvalidArgument`` ("transaction has expired"), is
  atomic, storm-shaped and replayable, and
  ``persist_loss_is_contention`` keeps it — the storm-windowed re-strike
  schedule stays authoritative for that family. The re-strike lane's
  budget, kill switch and uncertain-outcome semantics are unchanged for
  every class it already struck; only the booking after its budget
  exhausts changes, from a blind retryable fault to the typed custody
  handoff.

## Why typed and not a message list

Message matching drifts: the next deterministic persist raise site (a new
payload guard, a new register precondition) silently joins the ladder
again, and the only signal is the error signature burning in production.
The boundary reads the type through the shared contention classifier, so a
new deterministic fault is terminal by construction while the expired-chain
shape stays replayable, and the parity suite pins the classifier verdict
class by class so the two cannot drift apart.

## Verification

`backend/tests/unit/test_persist_deterministic_terminal_parity.py` pins the
boundary mapping and the custody handoff (attempt economics, gate-off
parity, expiry-shape parity, transport/contention parity);
`test_persist_deterministic_channel_parity.py` pins the channel demotion at
both logging sites, the closed-vocabulary admission and the hostile-input
contract; `test_persist_deterministic_ladder_stop_grid.py` pins the
classification matrix — every fault class the persist boundary can raise,
against the re-strike gate and the disposition verdicts — so a new fault
class cannot silently rejoin the ladder.
