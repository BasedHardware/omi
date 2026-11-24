# Five-minute batch projection prechecks

SCA-3508 allows an assignment precheck with no prior projection receipt to reuse
an owner privacy decision for five minutes. The original Firestore snapshot
bounds the deadline. The Redis slot carries the last invalidation revision and
the decision together. Successful privacy-authority commits rotate the slot.
Scope, coverage, age and generation must match before reuse. A Redis failure
falls back to the current path.

Projection assignment, follow-up proof export and other write transactions
retain transactional privacy certification. GPU workers still use the live path
pending evidence for a Redis binding or a job-scoped attestation.

Deferred conversation deletes arm a separate batch purge ten minutes after the
Firestore commit. The job starts discovery again, survives a completed immediate
pass and uses the existing short, transactionally fenced destructive units.
It retries held accounts and unknown remote outcomes. The same collection and
dispatcher carry both obligations. Watch
`omi_batch_pipeline_privacy_post_window_sweeps_total` for durable completion and
`omi_batch_pipeline_privacy_post_window_operations_total` for reprocessed
Firestore, Postgres and object-storage work. Operation counts include retries.

Before canary, set `bpp_tokenless_owner_shadow` to a positive percent and observe
six hours with evaluated samples and zero `mismatch_outside_window` on
`omi_batch_pipeline_privacy_tokenless_owner_shadow_total`. Measure eligible
lookups, hits, and invalidations on
`omi_batch_pipeline_privacy_tokenless_owner_cache_total`, and compare net
Firestore reads per compute completion to the matched baseline. The inverse
`bpp_tokenless_owner_cache=0` restores the phase-one read path and stops arming
new delayed obligations. Previously armed jobs still run.

The broader budget assumes reusable decisions in write-bearing paths. Before
admitting those paths, establish account, protection and recording-policy
late-write coverage across their sinks. In particular, a delayed sweep needs to
distinguish stale writes from writes under the newer policy.
