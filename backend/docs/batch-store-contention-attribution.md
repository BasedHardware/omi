# Batch pipeline: store transactions are attributable and advisory probes leave the ladder

Every batch-store transaction used to resolve its contention label from a
context variable whose default was the anonymous ``batch_pipeline_store``.
The scheduler, merge, provider-STT and shadow flows had already grown
static labels, but dozens of worker-hot call sites still ran unlabeled:
the whole quarantine-recovery custody family, speech redrive, terminal
empty disposition, staging, paid attempts, recognizer receipts, policy
loads, the artifact-missing repair path, the language shadow probes, the
leader lease, live registrations, admission reads and seals, intake
status and deleted-conversation proofs, partial prechecks, seal
registration, and the per-sweep maintenance reads. When any of them
exhausted its five-attempt budget, the log line still read
``operation=batch_pipeline_store ... outcome=exhausted`` — x709 per
30-minute window in production — and could not name the caller that
burned the budget, so an ``outcome=exhausted`` storm was unattributable
by construction.

The second half of the same storm was self-inflicted: several of those
sites ran pure single-document reads inside transactions. A read-only
body gains nothing from the transactional ladder — it takes no locks and
writes nothing — but it still joins a read set that Firestore aborts on
every concurrent write to the probed document. On hot job documents
(written by every lease heartbeat, completion, failure and queue
transition), a per-sweep advisory read could burn the entire shared
five-attempt budget of a worker transaction it never needed to
participate in, converting one busy owner into
``firestore_transaction_contention ... outcome=exhausted`` noise and, in
the merge drain, into ``event=batch_merge outcome=retry
exception_type=FirestoreContentionExhausted`` churn.

## What changed

- The ambient label default is retired. ``current_operation()`` returns
  ``None`` when no context is active, and ``FirestoreStore.run`` refuses
  an unlabeled call: the label comes from the explicit ``operation=``
  argument or an ambient ``store_operation`` / ``shadow_operation`` /
  ``pull_operation`` context, and with neither the call raises
  ``ValueError('static store operation label required')`` before any
  transaction opens — on the contention-retry path and on the kill-switch
  (``BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false``) path alike. Every
  remaining production call site now carries a static literal label
  (``batch_recovery_*``, ``batch_speech_redrive_*``,
  ``batch_terminal_empty_*``, ``batch_projection_release*``, ``batch_policy_*``
  loads, ``batch_artifact_*``, ``batch_language_shadow_*``,
  ``batch_leader_lease``, ``batch_live_*``, ``batch_admission_*``,
  ``batch_intake_*``, ``batch_partial_*``, ``batch_cap_hold_*``,
  ``batch_seal_register``, ``batch_provider_fence``,
  ``batch_merge_hold_release``, ``batch_recognizer_receipt``,
  ``batch_paid_attempt_settle``, ``batch_artifact_stage``,
  ``batch_content_ledger_accept``, ``batch_recover``), so the next
  ``outcome=exhausted`` storm names its caller on line one.
- Single-document advisory reads moved off the ladder onto a new
  ``Store.probe(table, key)`` point read (strongly consistent, ``{}`` when
  missing, same table/key semantics as the transactional ``get`` via the
  shared ``document_ref`` layout). Converted: the pump's maintenance
  owner lookup, the ordered-merge release probes and committed-result
  re-read, serving's owner discovery (complete and maintenance), live
  drain state checks, intake's prior-upload and repair-owner proof
  reads, the live-upload route probe, the artifact-reupload lineage
  read, the seal sweeper/repair/cluster classification reads, and the
  partial-flow ledger wait read. Each converted caller keeps its
  write-authority fences inside the transactions that act; the probe
  result is a hint, and the acting transaction re-verifies it.
- The pipeline simulator, the seal sweeper's read-only view, the replay
  runner facade and the unit-test memory stores implement the same
  ``probe`` surface, so parity lanes exercise the real split: probes read
  outside transactions, transitions stay transactional.

## Contracts that do not change

- The contention ladder itself: bounded attempts, equal-jitter delays,
  the expired-chain ceiling, deadline scoping and
  ``FirestoreContentionExhausted`` semantics are untouched; labeled
  transactions replay exactly as before, now with an attributable
  ``operation=`` on every retry, recovery and exhaustion line.
- Kill-switch semantics: ``BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false``
  still runs one unladder attempt per call — it now also requires a
  label, because attribution is orthogonal to retrying.
- Durability: probes never authorize a write; every deferred, failed,
  completed or quarantined transition still happens inside a
  lease-fenced transaction that re-reads its fences.

Failure-Class: FC-advisory-probe-reads-and-unlabeled-store-operations-exhaust-the-anonymous-contention-budget
