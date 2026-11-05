# Batch pipeline: the owner FIFO link lives on the queue document

Every batch unit joins its owner's FIFO through `_append`, which used to
store the link on the job documents themselves: appending a unit read the
queue's tail job, wrote a ``next`` pointer into it, and wrote the queue and
control documents. The tail job of a streaming owner is the unit that is
in flight — its document is written every 20 seconds by the lease
heartbeat, once by the worker's completion or failure transition, and
promoted or spliced by the pull's head-priority pass. Every append
therefore joined a read-write set it never needed, and the resulting
read-time conflicts under streaming load exhausted the shared
five-attempt contention budget: admission answered 503 for whole bundles
(the client re-uploads them, amplifying the storm), the maintenance pump
logged ``event=batch_maintenance outcome=retry
exception_type=FirestoreContentionExhausted``, and units died at attempt
5 into ``batch_quarantined ... stage=unknown worker_reason=unclassified``
— the same exhaustion cascade the contention family fixed elsewhere
(persist registration, shadow slot ring).

## What changed

- The owner-priority queue document now carries the FIFO as a bounded
  ``items`` array (``link_mode: 'fifo_array'``). `_append` converts a
  legacy chain in place — walking ``head -> next`` once, verifying the
  chain ends at the mirrored tail and fits the bounded migration cap —
  and afterwards appends by extending the array. The appended unit's job
  document never joins the append's read or write set; the queue and
  control documents (which appends already wrote) are the only shared
  writers left.
- The pull walk advances by popping the array (the mirrors ``head`` and
  ``tail`` stay maintained), the head-priority promotion splices purely
  in the array, and ``ready_predecessor`` resolves through the array
  with the transaction's buffered view — the legacy ``next`` index
  query misses in-transaction splices by construction, so the array is
  also more correct there, not just cheaper.
- Purge unlinks by index repair in array mode and skips the
  predecessor query and its next-pointer rewrites entirely.
- Mixed-version rolls are safe in both directions. An older binary
  chaining onto a converted queue either seeds a chain beside an empty
  array or continues the mirrored tail's chain; the array-aware walk
  and appends absorb such stragglers row by row (bounded, idempotent).
  A legacy chain longer than the migration cap is never guessed at:
  conversion is vetoed with a one-minute probe backoff instead, and the
  queue stays legacy until it fits or drains. A straggler chain deeper
  than the cap during a roll refuses the whole append (the admission
  retries), because a partially folded array would strand the remainder.
- Every previously unlabeled worker-hot batch mutation now runs under a
  static attributable operation label (``store_operation``):
  ``batch_admit``, ``batch_heartbeat``, ``batch_complete``, ``batch_fail``,
  ``batch_defer``, ``batch_release``, ``batch_recover``,
  ``batch_merge_commit``, ``batch_provider_stt``. Contention lines no
  longer blend into the unlabeled ``batch_pipeline_store`` default, so an
  ``outcome=exhausted`` storm names the caller that burned the budget.

## Contracts that do not change

- ``BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED=false`` stops creating array
  queues (appends chain exactly as before). It does not strand work:
  queues already converted always drain through the array-aware walk,
  regardless of the flag, because the representation on the queue
  document is the authority for draining.
- Lease, privacy, admission and merge semantics are untouched: tokens,
  attempt ladders, DRR deficit accounting, ring membership and the
  ``MAX_ACTIVE_OWNERS`` / write-budget bounds behave exactly as before,
  and the pull walk leases the same units in the same order for the
  same backlog (the parity suites pin the order equality across the
  flag).
- The owners-document revision fence still serializes admission with
  merge for one owner; nothing about the ordered-commit protocol moved.
- Failure-Class: FC-queue-link-on-hot-job-doc-crosses-inflight-writers-and-exhausts-admission
