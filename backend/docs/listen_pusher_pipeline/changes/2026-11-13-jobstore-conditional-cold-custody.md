The dark Jobstore D source now binds ordinary typed journal records to a
conditional Firestore cold destination. Original admission generation identifies
the grouped recording outbox; the original per-record PG custodian persists
before any remote cold write. Cold rows preserve source bodies and exact
original deadlines. They create no runnable FS queue, wakes or new TTL.

The actual retained-copy account/conversation adapter deletes original cold
references under real hold/unit-token, privacy and namespace authority checks,
then retains a durable per-record suppression barrier. Delayed covered source
pages cannot recreate erased copies. Journal checkpoints advance only after
acknowledgement and still match their observed source epoch. SQL slots/guards
end before FS I/O. Actual emulator/private-PG tests exercise lost replies,
authority races and process exits around cold-copy and cold-erasure COMMIT.

This source is not selected by a production runtime. Unsupported cohorts,
legacy outbox generations and cross-epoch original handoffs refuse. Journal
retirement, original intake/staging/late-object proofs, real GCS C4, final
erasure/reverse certificates and runtime orchestration remain gates. No env,
serving wire contract, rollout, activation or savings change is made.
See the [retained-copy lifetime inventory](../../jobstore/d-retained-copy-lifetimes.md).
