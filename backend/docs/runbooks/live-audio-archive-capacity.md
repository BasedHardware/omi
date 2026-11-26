# Live audio archive capacity

`get_live_archive_executor()` is shared by **durable and best-effort** live archive
encoding and storage within one Python process. `AUDIO_DURABLE_OUTBOX_ENABLED`
defaults to `true`. This change therefore bounds the default durable path too;
it is not limited to an optional best-effort rollout.

The pool has eight workers and 32 queue slots: at most 40 unfinished submissions
are admitted per process. If none completes, submission 41 raises
`ExecutorSaturatedError` immediately. The queue does not add throughput. Each
archive allows up to four in-flight packs, so ten archives each submitting four
unfinished packs can consume the entire pool. This is an admission example,
not a supported concurrent-user count. Normal packing, reconnects, multi-channel
capture, storage latency and simultaneous disconnect flushes change the demand.

The durable path sets `failed`, records `record_would_drop('raw_pack')`, retains
the original uncommitted pack and frame identity, and propagates the failure at
`ensure_durable()`. It publishes neither a custody receipt nor a deferred
coverage acknowledgement for that pack. The producer remains unacknowledged;
recovery depends on a later successful retry/client retention. This is a visible
availability failure, not proof that arbitrary load is safe. Best-effort mode
instead disables that archive and records a capacity fallback.

`test_durable_live_archive_saturation_retains_custody_and_propagates_at_barrier`
fills the real 8+32 pool, verifies rejection, retained custody, barrier failure,
withheld acknowledgements and permit recovery. This is deterministic correctness
evidence, **not a production load test**.

Before enabling this change in production, the deployment owner must approve
the pool size using measured per-process active/queued work, commit latency,
pack arrival rate, reconnect/disconnect bursts, saturation and raw-commit failure
rates. A rough steady-state requirement is arrival rate below eight divided by
mean service time (seconds); tail latency and bursts require separate headroom.
Verify actual process/replica counts and downstream storage quotas in the deployed
configuration; repository defaults do not establish the live operating envelope.
Do not increase the pool simply to hide overload. A rollout with sustained queue
growth or custody refusal needs intervention before expanding traffic.

No production traffic measurements or sizing approval are supplied by this PR.
Production storage lifecycle application also remains an operator action under
[`storage-lifecycle/README.md`](../../deploy/storage-lifecycle/README.md), including
its required review and bucket checks. Unit tests and CI do not apply that policy.
