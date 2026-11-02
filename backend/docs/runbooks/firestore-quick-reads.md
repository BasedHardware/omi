# Firestore structural query reads

PR #23442 now retains two default-on structural optimizations. The public catalog
and request-cohort cache changes were dropped during the 2026-10-27 main merge:
main already has public-list single-flight/Redis reuse and deadline-bounded shared
cohort observations. This PR adds no request or cross-request cache lifetime.

| Kill switch (`off` restores the prior path) | Scope | Origin |
| --- | --- | --- |
| `FSR_SMART_MERGE_PARTITION` | Unbounded discarded-barrier scan for explicit devices | `task:smart_merge_partition_lookup` |
| `FSR_KG_CITATION_INDEX` | Reverse-citation node lookup during KG pruning | `task:kg_citation_prune` |

## Index and policy gates

The lead must reconcile the generated manifest and verify
`conversations_smart_merge_device_preceding` READY before serving this source.
Use the existing schema approval/readiness path; this lane performs no applies,
access changes, production writes or deployment. A missing/building-index
`FailedPrecondition` falls back to the old query before returning rows; other
errors propagate. Both attempts retain the caller's transaction.

The finite predecessor lookup keeps its global six-row window. Missing or empty
device IDs retain the old scan so absent fields remain visible. Discarded barriers
stay unbounded within the same device, including deleted barriers. Only values
fully represented by the index are eligible: device and citation identifiers
over 1,500 UTF-8 bytes retain the original scan. Firestore documents
[index-value truncation and inconsistent query results](https://docs.cloud.google.com/firestore/quotas)
above that limit; this is optimization eligibility, not a new input restriction.
Main's donor
rebasing, source/lineage checks, open-loop extraction and retirement paths remain.

Firestore's native `memory_ids` array index is the reverse-citation writer: it
updates with existing node writes and covers historical data before serving.
There is no separate side collection or backfill. One query for at most 30 distinct memory IDs is materialized before mutations.
Larger retractions keep the original single scan, so overlapping citation chunks
cannot amplify reads. A missing index falls back before any write. Global surviving-node and orphan-edge scans remain: the
operation must still remove unrelated pre-existing dangling edges. No canonical
promotion, deletion/hold authority, transcription, speaker or Free-plan change.

## Measurement and economics

The 10-26 fleet caller pools are **16.749388M reads/day** for
`smart_merge:find_preceding_conversations` and **8.915616M/day** for
`knowledge_graph:prune_memory_citations_from_kg`. At $0.43–0.47/M and 30 days:

- Smart merge's entire caller pool is $216–236/month. The removable fraction is
  only explicit-device unbounded barriers multiplied by the off-device rows they
  currently download. The saved aggregate does not identify either fraction.
  **$0–236/month gross ceiling; no defensible point forecast.** The synthetic
  121-to-1 lookup is mechanism evidence, not the fleet traffic mix.
- KG removes only the first of two full node scans; the edge scan remains. Its
  full caller pool is $115–126/month, but this change's structural ceiling is
  **$0–63/month**, before empty-query floors and the unknown fraction of bulk retractions. The 206-to-106
  synthetic fixture corresponds to $56–61/month only if that graph shape holds
  fleet-wide; it is not a measured forecast.

The retained bundle's **$0–299/month** is an upper bound, before added composite
index storage and fallback overhead. Existing writes maintain the native indexes;
no new application document writes are introduced. New verified/realized savings
are **$0**. Earlier 22.5M/day predictions are retired, not booked.

Compare old and new callers together: smart merge's inner collector is attributed
to `smart_merge:collect` (including the unchanged finite query), KG's new lookup to
`knowledge_graph:_citation_nodes`, and remaining sweeps to the old prune caller.
Track both new origins, legacy callers, fallback counts, query/RPC latency,
merge/barrier correctness and graph-cleanup equivalence. After lead serving,
compare matched windows against the 10-24/25 billing baseline and confirm net
reads/writes/storage at D+1 in the billing export. A renamed caller is not saving.
