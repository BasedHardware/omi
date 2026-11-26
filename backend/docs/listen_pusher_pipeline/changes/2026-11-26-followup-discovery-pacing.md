# Follow-up discovery can be paced per process; targeted wakes are timed

## What changed

Each `backend-integration` serving process runs the in-process projection follow-up sweep. When its queue
is empty, it reads a 100-row discovery page on every serving pass, whatever that page holds. Over the 24 h
ending 2026-11-26T03:32Z this cost about 15 attempts and about 792 batch-pipeline Firestore reads per
completion, and the work grew with instance count (SCA-3120, SCA-4454).

`BATCH_PIPELINE_PROJECTION_FOLLOWUP_DISCOVERY_INTERVAL_SECONDS` sets the minimum number of seconds between
two periodic discovery reads in one process. A paced pass counts as `outcome="discovery_paced"` and returns
before it reads anything. Targeted wakes (`discover=False`) and priority segments never wait on the
interval: they launch exactly as before, and a priority call that falls inside the interval still queues
its segments.

The new histogram `omi_batch_pipeline_projection_followup_targeted_start_seconds` measures how long a
targeted or priority wake waits before its attempt starts. The clock starts at the segment's first wake. It
keeps that first time when the same segment is queued again through either path, and stops when the attempt
starts, after both the local slot and the projector's shared follow-up semaphore are held. A wake whose task
is cancelled before then records nothing. The process holds at most 20,000 pending marks and drops the
oldest first.

## Rollout and flags

Default `0` (pacing off) on every host. No deploy config declares the key, so this image changes no
behaviour. Values outside 0–900 or that do not parse read as 0. It is registered in
`config/feature-flags.yaml` (owner `compute-headroom`, review by 2026-12-10).

Plan: ship at 0, then read a matched 1 h baseline of the histogram. Record a wake-latency threshold on
SCA-3120, then set `60` on `backend-integration` only, in its own config window. Rollback: set the key
to `0` explicitly. The config train applies only the keys it declares, so deleting the key leaves the
old value serving.

## Readback

On `backend-integration` during matched peak hours, compared with the baseline taken at 0:

- Follow-up attempts per completion and batch-pipeline reads per completion fall.
- Completions per input unit stay within 5% of the pre-change trend. On 2026-11-26 the slots 3 + tick 20 s
  window cut reads 32% but breached this guard at −8% and was reverted (SCA-4084), so the pacing step is
  judged on drain rate first. The oldest projection-drain age must not rise.
- Targeted wake-to-start p90 stays within the threshold recorded on SCA-3120.

## Evidence

- SCA-3120: the follow-up sweep cost analysis and the Owners' review of this change.
- SCA-4454: compute-headroom targets and the instance readbacks.
- PR [#26433](https://github.com/BasedHardware/omi/pull/26433).
