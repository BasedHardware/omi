# Recovery for stranded provider transcription jobs

SCA-3362 adds a job-side scan to the existing provider-STT maintenance tick. The
outbox sweep can skip an old open wake and only searches open rows. The new scan
can recover running jobs whose wakes have aged out, gone missing, or closed.

Every two minutes the scan considers up to 25 `provider_running` jobs enqueued
at least six hours ago. That age matches the existing batch census alert. A
Firestore transaction rechecks the job, privacy fence, and wake before replacing
it, while preserving live leases and recent wakes. The worker reconciles the
existing provider attempt. It can settle a saved result or handle an abandoned
attempt without making another call under the same token. Expired audio is
ineligible for paid failover.

The scan starts with the serving revision on the existing maintenance schedule.
After rollout, verify a fresh census oldest-age sample and use a read-only count
to confirm zero production jobs in `provider_running` with an enqueue age of
six hours or more.

See the [provider routing contract](../../listen_pusher_pipeline.mdx#cohort-scoped-legacy-sync-retirement),
the [batch census runbook](../../runbooks/batch-stuck-census.md), and
[PR #26120](https://github.com/BasedHardware/omi/pull/26120) for test evidence.
