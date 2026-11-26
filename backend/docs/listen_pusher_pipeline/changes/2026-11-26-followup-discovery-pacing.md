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
SCA-3120, then set `60` on `backend-integration` only, in its own config window. The rollback is below.

## Readback and guards

Each guard is read on 1 h windows on `backend-integration`, against a matched 1 h baseline taken at `0`.
Throughput comes first. Breaching any guard reverts the step.

1. **Completions per input unit** stay within ±2% of the matched baseline, and within 5% of the same day's
   pre-change trend. On 2026-11-26 the slots 3 + tick 20 s window cut reads 32% but breached this guard at
   −8% and was reverted (SCA-4084).
2. **Follow-up and completion p90 latency** rise by 15 min or less.
3. **Targeted wake-to-start p90** (`omi_batch_pipeline_projection_followup_targeted_start_seconds`) stays at
   or below the baseline plus the threshold recorded on SCA-3120 before the step.
4. **Neither oldest-age gauge** (`omi_batch_projection_drain_oldest_age_seconds` or
   `omi_batch_projection_obligation_oldest_age_seconds`) rises by more than 10 min.
5. **An independently measured eligible stock** does not grow. `followup:candidates` does not count.
6. **blocked + retry + claim_busy per completion** does not rise.

**Expected effect:** follow-up attempts per completion and batch-pipeline reads per completion fall.

**Rollback:** set the key to `'0'` explicitly, then verify that the serving revision's env reads `0`. The
config train only updates the keys it declares, so deleting the key leaves the old value serving.

## Evidence

- SCA-3120: the follow-up sweep cost analysis and the Owners' review of this change.
- SCA-4454: compute-headroom targets and the instance readbacks.
- PR [#26433](https://github.com/BasedHardware/omi/pull/26433).
