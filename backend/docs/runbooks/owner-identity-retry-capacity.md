# Late identity retry capacity

Read-only production evidence cutoff: 2026-10-14 01:40 UTC, trailing 12 hours.
Source: `sum by(stage,reason)(increase(omi_owner_identity_retry_total{pass="late"}[12h] @ 1791942000))`
through the production Prometheus Kubernetes service proxy. Rounded extrapolated
counter increases: entry 59,749; slot-limit skip 41,512; deferred 16,612;
eligible 2,133; committed 2,118. Repair outcomes: owner added 10, removed 26,
identity updated 78. Commits can be identity no-ops.

## Lost conversations

`routers/pusher.py:process_private_cloud_queue` is the sole scheduler caller.
It collects up to 128 manifest-updated conversations and submits once after
session drain. It ignores False. The legacy scheduler has no durable queue or
later trigger on rejection; waiters expire after 230 seconds. A new session
uploading another manifest for the same conversation can trigger again. First
finalization also resolves identity, but is not a guaranteed late-audio retry.
No automatic sweep repairs previously skipped rows.

41,512 is candidate submissions, including waiter expiry/cancellation, not
unique conversations. Deduplication lasts only while process-local work owns
IDs; later sessions and other pods can count them again. The metric labels are
only pass/stage/reason. Distinct permanent losses are **not identifiable** from
these aggregates (approximately 0–41,512 possible); counting them requires a
privacy-preserving longitudinal ledger of skips and subsequent outcomes that
does not currently exist. Production account data was not read.

## Per-attempt resources

- Rejection/ID-only waiting: zero Firestore reads, zero executor threads.
- Each scan: one conversation document read, including misses. If photos are
  absent and `has_photos` is not false, also a photos query, billed at least one
  read even when empty, or one per returned photo.
- Processing/in-progress candidates can be scanned six times (initial plus
  five completion rechecks), without consuming an eligible pass.
- Eligible nonempty resolution: one additional manual-receipt document read;
  successful CAS: two reads (conversation plus account-deletion marker) per
  transaction execution. Hence the ordinary no-photo early-exit commit costs
  four reads. Contention can repeat the two CAS reads.
- Paths reaching voiceprint matching add one owner-user read and one subscription
  read; paid users add `max(1, people documents)` plus learning-ledger projection
  reads for people with job pointers. Early placement refusals avoid these.
  Late repair disables owner-profile recovery; there are no recovery reads.
- One storage-executor thread per running round; two concurrent rounds maximum
  per process, at most 26 across the 13 pusher pods observed during this audit
  (28 at 14 pods). Sleeping/waiting consumes no thread. Naively doubling or
  quadrupling workers permits 52/104 threads fleet-wide at 13 pods, 56/112 at 14.
- The five-second resolver budget is advisory, not CPU time or a hard wall
  timeout; network/storage/model waits, transcript decoding and vector work vary.
  The measured trailing-window whole-pusher CPU average was 9.90 cores.
  It includes live streaming/upload/other work; retry CPU-seconds per attempt
  and incremental CPU cost are not available from current metrics.

## Capacity scenarios, not measured forecasts

For an illustrative steady-state model, use entry minus slot-limit skips:
18,237 retained submissions/12h, and assume all are scanned once, unchanged
eligible mix (2,133/18,237), unchanged commit mix (2,118/2,133), no photos,
completion rechecks, profile reads or transaction retries. Multiply throughput
by capacity, capped at 59,749 submitted candidates/12h. Batch/pass ceilings and
burstiness can invalidate linear scaling. The two-worker coalescing flag does
not multiply throughput by a known factor.

| Model | Candidate scans/day | Eligible/day | Commits/day | Core reads/day | Added reads/day |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current | 36,474 | 4,266 | 4,236 | 49,272 | 0 |
| 2× throughput | 72,948 | 8,532 | 8,472 | 98,544 | 49,272 |
| 4× capacity, demand capped (3.276× throughput) | 119,498 | 13,976 | 13,878 | 161,427 | 112,155 |

Core reads = scans + 3 × eligible (normal receipt/CAS path); these are scenario
floors, **not observed billing**. Shared database-caller metrics cannot separate
retry scans/profile reads from other users of the same functions. The exclusively
late CAS caller observed 4,263 reads/12h, or 8,527/day, including retries/in-flight
transactions; this is not the total retry read count.

Firestore's [free read quota](https://docs.cloud.google.com/firestore/quotas)
is 50,000/day for one eligible database, shared with other workload reads.
The 2× scenario alone is about 1.97 quotas/day; the demand-capped 4× scenario
is 3.23. Dollar cost depends on database location/edition and existing free-quota
consumption; no database location or billing account was inspected.

## Recommended flag and acceptance

Recommend `OWNER_IDENTITY_RETRY_COALESCE_ENABLED=true` for a monitored canary
when this draft is approved and deployed by the lead. Default remains false.
Sixteen bounded UID cohorts replace competition between overlapping batches;
the existing two workers, 128 distinct candidates and eight eligible passes
remain. Queue TTL, overflow and pod restarts can still lose candidates.

Expected direction: fewer repeated submissions competing for slots, more
eligible/committed attempts if metadata admission was limiting. There is no
measured multiplicative effect. A 2× recovery scenario gives 4,266 eligible and
4,236 commits per 12h; demand-only ceiling at unchanged mix is about 6,988 and
6,939. These are planning scenarios, not rollout promises. Fresh merged IDs wake
completion waits for arrival-only worker rounds; older processing IDs keep their
scheduled rechecks. Arrival wakes consume no completion recheck slot and cannot
reset the deadline or eight-pass budget. Slot releases wake the oldest waiter with
FIFO admission; polling remains the fallback. Suppressed resubmissions, including
previous transient exits, emit a matching entry and `skipped/cohort_seen` without
resetting budgets. In-flight duplicates emit `deferred/in_flight`, not skips.

Canary readout: `skipped/queue_limit`, `skipped/queue_expired`, `skipped/cancelled`,
`deferred/coalesced`, `eligible/candidate` and `cas_committed/done`, plus
`skipped/cohort_seen`, pass-limit skips and billed reads. `skipped/slot_limit`
is legacy and goes quiet when this flag is on; owner-added remains the
product-success metric. Roll back with false plus a process restart; no stored
schema or historical conversation changes are required.
