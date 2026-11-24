# Enrichment

`outbox.py` owns durable enrichment obligations, task bindings, leases and
settlement. `admission.py` shares custody and delivery checks between workers.
`consumer.py` connects the enrichment queue to `callback.py`, which runs
conversation reprocessing. `early_abort.py` fences superseded work before LLM
calls. `smart_refresh.py` loads the worker for owed survivor refreshes.

`custody.py` transfers obligations when a conversation is absorbed.
`fresh_demotion.py` moves overdue work out of the reserved fresh lane.
`scan.py` stores the watchdog's bounded scan checkpoint.

`age_gate.py` parks historical debt while preserving its custody fields.
`unpark.py` is the digest-approved operator path that reopens eligible parked
rows and wakes their persisted bindings through the outbox. `redrive.py` is the
operator path for re-waking overdue, committed summary debt. Follow the
[age-gate runbook](../../docs/runbooks/enrichment-age-gate.md) when operating on
parked debt.
