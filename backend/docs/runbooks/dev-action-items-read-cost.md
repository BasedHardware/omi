# Developer action-item read cost

This change targets `GET /v1/dev/user/action-items`. It requires **no new index,
backfill, scheduler, dependency or serving-path Firestore write**. Parent-owned
aggregate evidence on 2026-10-19 showed about 661 reads/request, 1,047 reads/cache
miss and 36.83% hits. Every miss in that hour was stored (1,063/1,063); the
256 KiB cache admission limit therefore does not explain that traffic. Counts
were about 1,180 reads/hour across all action-item callers versus about 1.117M
query reads/hour at this endpoint. These aggregates cannot identify the dominant
bucket, effective limit/offset, filtered traffic fraction, or writer churn.

## Filtered compatibility scan

The released default list reads incomplete rows first, sorts the bounded prefix,
then fills from completed rows. If incomplete rows do not fill the page, a
compatibility scan of `min(2000, max(8 * (offset + limit), 128))` can run. The
existing two-count canonical-completion proof only ran for unfiltered lists.
Conversation/date-filtered lists therefore still paid for this scan after the
completion backfill, even when every stored row had boolean `completed`.

Filtered Developer default lists now reuse that **owner-wide** proof before the
compatibility scan. The existing `completed in [false, true]` count runs first,
then the whole collection count. Equality proves no legacy row can exist in a
filtered subset. It uses the existing automatic single-field index, not a new
compound count query. Different counts, probe failure or any noncanonical value
retain the old scan. No migration marker or negative result persists. A legacy
row in another conversation can still cause an unnecessary scan; it cannot hide
a matching legacy row. Concurrent-write consistency is the same as the existing
unfiltered proof, not a transactional snapshot guarantee.

The active query must also have returned fewer documents than its bounded
`need + 32` limit. A saturated prefix can have over 32 deleted rows: the old
compatibility scan then refills canonical active rows beyond that prefix. That
scan is preserved even with canonical completion data. Explicit completion
filters, unfiltered reads, old callers, projection, sort, hard caps and slicing
retain their previous behavior. Missing `deleted`/`is_locked` fields remain
visible. Locked rows remain filtered after pagination; filtering them earlier
would change released page semantics.

`tests/unit/test_dev_action_items_read_cost.py` drives the real ASGI route,
response validation, cache, list reader and budget with an injected query fake.
Large 3,000-row cost models also call the real reader directly to keep the unit
CPU budget focused on scans. The fake models Firestore boolean/missing-field
matching, ordering, projection, empty-query floors and count billing. Local
fixtures show these list-read equivalents
(auth excluded), with identical response bytes and headers:

| Fixture: canonical completed backlog, conversation filter | Before | After |
| --- | ---: | ---: |
| 1,000 rows, limit 100 | 933 | 135 |
| 3,000 rows, limit 100 | 933 | 139 |
| 3,000 rows, limit 1,000 | 3,033 | 1,039 |
| 3,000 rows, offset 500, limit 100 | 2,633 | 639 |

These are conditional per-miss savings, not production forecasts. Warm cache
hits still reauthorize and issue no list reads. Unfiltered/explicit-completion
traffic, legacy-containing accounts and saturated active prefixes have no new
scan saving. Owner-wide count charges grow with the entire collection, including
rows outside the requested subset; very large owners with tiny filtered windows
can pay more counts than the avoided scan. A direct-reader fixture with 2,001
canonical owner rows and one matching conversation row pins this tradeoff:
3 list reads before versus 8 after (including two 3-read owner-wide counts),
with identical results. The independent probe switch and
component metrics support detecting that case. Large limits, offsets and the retained 32-row slack still cost
reads. The slack participates in the final product sort; simply removing it
changes page contents. Determining aggregate savings requires new telemetry and
parent-owned measurements of the running release.

## Writer and cache churn

All SDK commit fences remain mandatory, including ambiguous failures, retries,
non-list fields, sync, bulk and overlapping writers. Post-write callbacks cannot
replace these fences. Empty unlock/batch-reorder paths already avoid writes;
changing only their first-party version bump does not affect the Developer SDK
version. Removing invalidation for actual writes would make cached responses
stale.

Single-item ordinary/linked updates now compare the effective patch against the
snapshot they **already must read**. Exactly identical stored scalar fields acknowledge
success without updating `updated_at`, committing or bumping versions. Missing
fields, changed values/types, structured values, untrusted subclasses, explicit
`updated_at` touches, transforms and
conditional chat journal edits retain the write path. Linked updates still
validate goal/workstream relationships transactionally. Completion follow-up
reconciliation still runs. Batch sync entries with no existing pre-read remain
unchanged: introducing read-before-write to suppress them would add cost. This
is a bounded source of avoided churn; its production frequency is unmeasured.
No additional read is introduced. The reused current `completed_at` may be a
real SDK `DatetimeWithNanoseconds`: the exact trusted SDK type is accepted by
identity only, so ordinary and linked completion replays remain optimized.
Distinct timestamp objects retain writes, including nanosecond changes hidden
by Python datetime equality. Collections, transforms and arbitrary equality
overrides are never used to establish a no-op. The mutation intentionally preserves the old
stored timestamp for a true no-op; changing data still stamps `updated_at`.

Effective pagination was already clamped before cache addressing. Equivalent
`start_date`/`end_date` instants now normalize to UTC in cache keys only, including
Firestore's interpretation of naive datetimes as UTC. Handler/filter values,
`completed=None` versus `false`, null/empty conversation filters and credential,
owner, app/key and budget isolation remain distinct. No broader page cache is
introduced. Cache diagnostics add fixed `skip_status`, `skip_truncated`,
`skip_body_size`, `skip_expired`, `skip_disabled`, `skip_version_changed` outcomes;
use `hit/(hit+miss)` rather than all diagnostic outcomes as the hit denominator.

## Controls and telemetry

Each new control defaults on; only trimmed, case-insensitive `false` disables it.

| Control | `false` |
| --- | --- |
| `OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED` | Restore filtered compatibility scans. |
| `OMI_DEV_ACTION_ITEMS_SKIP_NOOP_WRITES_ENABLED` | Restore single-item identical-patch timestamp/commit writes. |
| `OMI_DEV_ACTION_ITEMS_CACHE_NORMALIZE_ENABLED` | Restore date representation-sensitive cache keys. |
| `OMI_DEV_ACTION_ITEMS_READ_DETAILS_ENABLED` | Stop new component/page/filter metrics. |

Existing response-cache, version-cache and external-list metrics switches remain
independent. Writer fencing stays active regardless of reader switches. New
controls are registered in the feature-flag registry. No runtime values changed.

`omi_dev_action_items_firestore_reads_by_component{component}` partitions the
SDK request total into `auth`, `incomplete`, `completed`, `legacy`, `count` and
`other`, including empty-query floors and failed requests. Components are scopes
around actual SDK reads, not hand-counted extra charges. Auth includes all
pre-handler dependencies; `other` covers unclassified work after handler entry.
The holder closes at the final response body, excluding detached work. Component
`_sum` values add to `omi_external_list_firestore_reads_per_request_sum` for this
route. Disabling the existing external-list metrics switch also stops these
request components; its previous total accounting stays unchanged.

`omi_dev_action_items_request_shapes_total{filters,completion,cache}` counts
four fixed filter shapes (`none`, `conversation`, `date`, `conversation_date`),
three completion modes and cache hit/miss. This exposes the filtered default
miss fraction without recording filter values.

`omi_dev_action_items_page_parameter{parameter="limit"|"offset"}` observes
clamped effective numeric values including cache hits, using fixed histogram
buckets. Offsets above 25,000 record 25,001 (the overflow bucket) so arbitrary
accepted integers cannot overflow telemetry floats; request values stay unchanged.
`omi_dev_action_items_page_rows_total{stage}` counts origin rows at
`deleted`, `locked`, `invalid`, `slack`, `offset`, `returned` stages. These are
filter/overfetch diagnostics, not additional reads or mutually exclusive charge
components. Repeated bucket scans can fetch the same document more than once.
They run only on origin processing; cached response bytes retain the original filtering. No UID,
query, document ID, credential, URL or other dynamic label is added.

```promql
# Read-rate partition; divide by the existing route request rate for means.
sum by (component) (rate(omi_dev_action_items_firestore_reads_by_component_sum[1h]))
histogram_quantile(0.95, sum by (parameter, le) (rate(omi_dev_action_items_page_parameter_bucket[1h])))
sum by (stage) (rate(omi_dev_action_items_page_rows_total[1h]))
```

The local fake is not a Firestore emulator/planning oracle or production auth
acceptance. Query runtime drivers exercise both probe modes across existing
filter combinations. The generated index manifest must remain unchanged; run
the Firestore guard suite before shipping. SDK write-surface tests separately
cover invalidation. Parent owns aggregate prod verification, review and release.
