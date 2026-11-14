# Fresh enrichment priority

`ENRICHMENT_FRESH_TASKS_QUEUE` reserves dispatch slots for new user-facing
enrichment and pending first summaries whose conversation finished within
`ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN` (default30 minutes;0 disables new priority
admission). Use `finished_at`, falling back to `created_at` only when absent.
Unknown, invalid, future or unavailable metadata stays on the established queue.
A newly created obligation for an old conversation does not become fresh.
It uses the existing enrichment handler,
audience and invoker. Background backfill and lazy derived effects retain their
queues, including when the backfill queue is not configured.

Before deploying the production manifest, the rollout lead must provision
`enrichment-fresh` in the same project/location as `enrichment`, with permission
for the existing producers to enqueue and the existing invoker to call the
handler. Production permanently uses 30 concurrent deliveries and 10 dispatches/s
(2026-11-10 ruling 008024); primary enrichment independently stays 300/25. This isolates queue
scheduling; it does not establish spare backend executor or LLM capacity. Check
handler 5xx, 409 delivery-budget cuts, executor wait, LLM request latency/errors
and title age before raising the cap. The new queue must exist before activation;
`backend/deploy/ops/prod.yaml` reconciles these limits through config-train.
The operational Firestore-pressure guard may temporarily reduce live fresh
concurrency to 15 while retaining 10 dispatches/s; Git remains 30/10. Only
`cl2-deploy` applies production config. Re-evaluate the 168h age gate after the
backlog drains; this capacity change does not alter admission policy. Track owed
first summaries older than 15 minutes, targeting less than 1%.
Staging maps the reserved queue to `staging-enrichment-fresh`, with an intentional
5-concurrent/2-per-second ops contract. Its existing `create_queues.sh` helper
provisions this queue before staging deployment; the lane did not run it.

The normal bounded sweep promotes only due unleased user-facing rows bound to
the old enrichment queue whose conversation is within that same freshness window.
Older backlog retains its queue and continues draining at its existing capacity.
Its CAS retains the handler/auth identity and changes queue and
task token together. An old delivery becomes stale; a lost replacement enqueue
is recovered by the existing sweep. Active leases, background backfill, custom
bindings and lazy effects are not migrated. The old queue is not purged: it
contains both background work and stale deliveries that must drain normally.

Capacity rollback: make a targeted fresh config edit to 15 concurrent / 10
dispatches/s and coordinate its application with `cl2-deploy`; preserve primary
300/25. Never revert this entire PR or restore fresh 5/2 during backlog.

Routing rollback: remove `ENRICHMENT_FRESH_TASKS_QUEUE` from the deployed configuration
and leave both queues running until admitted obligations drain. Valid bindings
survive rollback. Pausing `enrichment-fresh` is an emergency stop, not a complete
rollback: already promoted rows wait there until it resumes. Never delete either
queue or task population to undo this change.
