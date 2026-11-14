# Lake transcript deletion and key shredding

Explicit conversation deletion now purges lake objects for the conversation and
its sync merge donors before deleting Firestore metadata. Lake transport failure
returns retryable 503 with deletion intent retained; success stays 204. This
includes a failed verified-absence check. Deletion durably fences every
conversation and donor before listing. Writers check the fence before and after
upload; a candidate finishing after the final listing self-deletes its new
generation and refuses publication. Retries never delete reused objects.

Account wipe purges the lake prefix after cell/directory purge and before the
Firestore user subtree. It destroys wrapped space keys last, after Typesense and
memory registry cleanup, leaving a permanent content-free tombstone. Prefix purge
is skipped only when the bucket is unset; key destruction is unconditional.

Lake writes remain default off. The shipped ordering, bounded writer drain,
rollback semantics and accepted seven-day PITR tail are in the
[object lake contract](../../../deploy/storage-lifecycle/LAKE.md). The O1 wipe gate
is `test_lake_wipe_step.py::test_o1_wipe_coverage_gate_and_crash_retry`; real key
contention coverage is in `test_space_key_destroy_contention_firestore.py`.
