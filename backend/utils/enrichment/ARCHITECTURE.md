# Enrichment package

The durable outbox is the authority for owed work; Cloud Tasks wakes are hints.
HTTP adapters in `routers/enrichment.py` and sync/finalization callers preserve
that ownership. A retry must retain/rearm the durable obligation; a quiet period
or a successful HTTP ACK alone does not prove conversation completion.

| Module | Responsibility |
| --- | --- |
| `outbox.py` | Durable trailing-edge enrichment obligations and retry state. |
| `admission.py` | Shared custody admission and deferred-delivery seams. |
| `custody.py` | Atomic content-free transfer for absorbed conversations. |
| `consumer.py` | Enrichment adapter for the shared queue-consumer protocol. |
| `callback.py` | Conversation processing after new transcript segments land. |
| `early_abort.py` | Stop stale work before LLM processing when a newer revision owns it. |
| `age_gate.py` | Reversible parking of historical debt without deleting obligations. |
| `unpark.py` | Digest-approved operator path that reopens eligible parked rows and wakes their persisted bindings through the outbox. |
| `fresh_demotion.py` | Move stale first summaries off the reserved fresh queue. |
| `scan.py` | Bounded watchdog discovery with CAS keyset checkpoints. |
| `redrive.py` | Scoped operator re-wake of overdue committed summary debt. |
| `smart_refresh.py` | Refresh an owed smart-merge survivor. |
| `retry_reason.py` | Pure closed exception classification shared by HTTP adapters. |
| `__init__.py` | Package marker. |

Keep persistence/lease fences in the outbox and custody layers. The retry helper
may classify existing typed signals but must not read content, schedule work,
construct clients, or decide whether an obligation is complete. HTTP response
mapping belongs in the adapters; heavyweight worker RPC dependencies remain
separate from the enrichment binding.

Follow the [age-gate runbook](../../docs/runbooks/enrichment-age-gate.md)
when operating on parked debt.

Contracts: [pipeline](../../docs/listen_pusher_pipeline.mdx). Behavioral coverage:
[consumer route](../../tests/unit/test_enrichment_route.py),
[batch RPC and adapter](../../tests/unit/test_batch_pipeline_serving.py).
