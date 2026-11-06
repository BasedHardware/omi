# Atomic completion for zero-preview server-batch captures

Follow-up (c) from [PR #24693](https://github.com/BasedHardware/omi/pull/24693).
The Home flash is **INFERRED, not reproduced**. The old writer split is confirmed
in code: conversation completion preceded fanout completion and job completion.

After `register_recording` accepts the durable batch obligation, the zero-preview
branch now calls one lifecycle/database transaction. It reads job and conversation
before writes, fences dispatch generation/lease epoch, immutable binding/revision,
record ownership, external marker and privacy, and requires `processing`. It writes
conversation completion plus the existing lifecycle terminal relevance decision,
fanout completion, job success and projection increments together. Same-generation
replay accepts only this primitive's committed terminal and repeats no increments.
Lost leases write nothing. An inadmissible capture/binding terminally fences only
the current job, leaving the conversation untouched and counting stale once.

Quiet checks, people-cache invalidation and enabled search synchronization run
after commit, including direct replay. Normal processed persistence, deferred
minimum persistence, generic lifecycle `complete`, and normal external fanout stay
unchanged. No new flag; revert this PR to roll back. Persisted job fields remain
compatible with the existing outer worker acknowledgement.

Validation: strict-transaction tests enforce read-before-write ordering, privacy,
binding, relevance, replay and effect ordering. The local Firestore emulator suite
injects failure before commit, lost response after commit and an aborted attempt,
and exercises lease/privacy/binding fences and concurrent redelivery with actual
projection transforms. No production access or deployed/UI acceptance is claimed.

Ordering contract: [durable finalizer](../../listen_pusher_pipeline.mdx#21-durable-finalization-ownership).
