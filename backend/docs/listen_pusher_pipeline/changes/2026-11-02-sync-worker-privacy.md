# Sync worker privacy scope and shadow counters

S3 exposes the coordinator as `run_full_pipeline_background_async`; the session
privacy cancellation test follows that name without weakening its assertions.
Both inline and Cloud Tasks coordinator entry remain scoped before rollout
warmup, including cancellation. The worker now also opens a fresh privacy
attempt before its first await, covering preflight, ledger convergence and
terminal cleanup outside the separately scoped coordinator. Closed holders
cannot be reused by late executor leaves.

The isolated worker child previously lost its process-local privacy counters
at exit. Its supervisor now exposes `/metrics`, reads the child's Prometheus
mmap counters while it runs, and folds the final values after reaping the
process group, including forced termination. Each child gets an owned temporary
directory, removed after folding; retained storage is bounded by the seven
existing counter families rather than completed-job count. Parent environment
is unchanged. The worker chart includes PodMonitoring by default; this patch
does not install or deploy it.

See [privacy shadow qualification](../../runbooks/privacy-check-shadow.md).
The 14-day window requires installed-worker coverage and successful scrapes;
hermetic results are not live qualification. No enforcement or admission lever
changes. Revert this patch to roll back code/chart changes.

Verification: selected capture, Cloud Tasks, worker, writer-token and privacy
suites through `backend/test.sh`; worker regressions exercise live allow/block,
real candidate memo hits and a missing-token-bump stale-allow mismatch. A real
child process proves both live/shadow counters survive normal exit and SIGKILL
without double counting or per-job file growth. Cancellation tests cover each
entrypoint before its first await and the real worker-to-coordinator call.
