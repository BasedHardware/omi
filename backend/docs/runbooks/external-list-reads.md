# Developer API and MCP list reads

The three Developer API GET lists (`/v1/dev/user/conversations`, `/v1/dev/user/memories`,
`/v1/dev/user/action-items`) and REST `GET /v1/mcp/memories` share a short response cache
and HTTP outcome measurement. The staged-task promote POST uses the same HTTP counter and its
own physical-empty probe. Hosted MCP JSON-RPC tools are outside this cache and rollout.

## Behavior and rollback

All five independent env levers default **on**. Only a case-insensitive, whitespace-trimmed
`false` disables a lever; unset, `0`, and other values leave it on.

| Lever | Disable with `false` |
| --- | --- |
| `OMI_EXTERNAL_LIST_METRICS_ENABLED` | Stop the four-route HTTP outcome counter. |
| `OMI_EXTERNAL_LIST_CACHE_ENABLED` | Bypass all response cache reads/writes; run the original handlers. |
| `OMI_MCP_MEMORY_LIST_BUDGET_ENABLED` | Restore the prior growing-prefix MCP compatibility scan with no shared budget. |
| `OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED` | Restore unbudgeted Developer conversation offsets and omit new guidance/truncation headers. |
| `OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED` | Restore control + full projection for every staged promote poll. |

Full behavior rollback sets all five to `false`. No deployment/env values are changed by this PR.
Cache keys include budget lever states, so switching either budget off cannot replay its headers/results.
No data migration, extra Firestore write, index, rate-limit, boost, or daily ladder change is required.
The existing memory keyset paths and the existing Developer memory/action-item budgets stay in place.

## Cache contract

Cache lookup happens inside the sync handler after dependencies (auth, scope, rate limiting,
account access) and route-level memory grants, parsing/validation, and transcript rate limits.
A hit cannot bypass these gates; permission revocations are rechecked on each request. It saves
list/content reads, not every auth/grant read. Existing dependency auth caches retain their own semantics.
The key hashes owner UID, persisted app/key context, a digest of the presented credential (including
legacy keys), route and normalized parsed effective query. Defaults and clamped pagination normalize;
all accepted filters, cursor, and page positions participate. Effective document allowances also
participate: resolving a different per-request limit cannot reuse a page cached under another limit.
The owner/context-aware resolver runs after auth and validation, before cache lookup. Category multiplicity is retained to match
the existing cursor filter fingerprint. Signed MCP `uml` continuation requests bypass response caching
so the original reader rechecks their independent expiry/snapshot authority on every call. Ignored query parameters retain existing
acceptance and get a fresh ignored-parameter header on hits.

Redis uses the existing connection configuration with 200 ms socket/connect timeouts. Bodies are the
final FastAPI response-model bytes, AES-GCM encrypted with the existing per-user derived key; the
opaque cache key is authenticated as associated data. Neither identity nor query/content appears in
Redis key names or metric labels. Entries have at most 256 KiB of body and 8 KiB of envelope allowance;
larger responses are served normally. Entries expire after 10 seconds; there is no process-local payload
cache. Global memory/eviction remains owned by Redis. Concurrent misses can duplicate origin work;
there is no lock or single-flight guarantee. Successful eligible responses submit short cache
populations with context to the existing db pool without awaiting them. A nonblocking 32-slot
process-local bound covers queued/running populations (at most 8 MiB of eligible bodies). Saturation
or submission failure skips population; errors, truncation, oversized or expired bodies never queue.
Future completion, failure or cancellation releases the slot. Workers recheck the query-start expiry
after queue delay; queueing never extends freshness or delays the completed origin response.

**Up to 10 seconds of stale list data after any user write is accepted**, including deletes, edits,
locked-state changes and writes from other clients. There is no write invalidation. The expiry is fixed
before the origin query and stored in the encrypted envelope. Redis `SET PX` receives only the remaining
milliseconds after query/serialization time; the envelope rejects expired content even if socket delay
makes Redis retain bytes slightly longer. Requests taking 10 seconds cannot populate the cache.
Reads reject expired envelopes even if Redis
returns them. A late older writer cannot extend freshness: its entry retains its earlier expiry.
This assumes synchronized service/Redis wall clocks, as other absolute-expiry runtime contracts do.
Only successful nontruncated pages are stored. Errors, `X-Omi-List-Truncated: true` and
`X-Scan-Truncated: true` responses bypass storage. Cache I/O, encryption or decode faults fail open
through the shared fallback telemetry without logging payloads or exceptions.

## Read bounds and client compatibility

For MCP's global-sort compatibility paths (`created_desc`, `manual_first`, non-keyset `updated_desc`),
the enabled lever reads one mixed canonical/historical window instead of repeatedly rereading prefixes
of 100 through 5000.
The same `ListReadBudget` reaches canonical scans, dual historical index windows, status batches, and
hydration. The existing 5000 outer window, filtering, ordering, legacy rows, array shape and cursor
fingerprints remain. Local slicing/filtering issues no further source reads. One operation also avoids
exhausting the memory resilience whole-operation retry allowance across successful batches.
Non-global `scoring_desc` compatibility pages (offsets or old offset cursors) keep the released
incremental collector with no new shared budget, including when the core receives a budget directly.
This avoids reading 5000 raw rows for shallow pages and continues past activity-only batches.
The existing scoring/updated keyset branch retains its own bounded paging and retry behavior.

Budget exhaustion sets both the existing `X-Scan-Truncated: true` and shared
`X-Omi-List-Truncated: true`; internally `scan_truncated` and `has_more` stay true even for empty pages.
A short partial globally sorted page does not establish complete account coverage. Only an in-window
continuation gets a cursor. Clients needing a traversal should use the existing scoring/updated keyset
path rather than retrying the same exhausted offset.

Developer conversation `offset>0` reads pass one shared budget into card and legacy
transcript/folder/starred list readers. Skips charge the budget before Firestore executes the offset;
an offset beyond the allowance returns an explicitly truncated 200, never a newly introduced 4xx.
The additive `X-Pagination-Guidance` header recommends starting cursor paging at offset zero without
transcript/folder/starred options; those options can use narrower date windows. An incomplete page
keeps `X-Omi-Has-More: true`. No input-acceptance tightening or production census is included.
Auxiliary folder/speaker rendering and conversation decryption retain their existing behavior and
are not part of the offset reader's document accounting.

The shared defaults are 24 seconds (request-start anchored, derived from HTTP timeout with headroom)
and 25,000 charged documents. Materialized memory RPCs charge the entire bounded result and can
overshoot by up to one current bounded RPC window, which can contain 7000 historical rows
(the 5000 candidate maximum plus 2000 hidden-row scan slack). This list budget is not an exact
billing ceiling.
Auth/grants, fixed policy reads, and auxiliary render reads are outside this list-document allowance.

## One injectable API document-limit resolver

`utils.other.list_budget.resolve_list_read_max_documents(owner_uid=..., context=...)` is the single
factory seam for the document allowance. Developer memories/action-items, budgeted conversation
card/transcript/folder/starred offsets, and MCP global-sort compatibility lists pass their authenticated
owner and authorization context through `list_read_budget_for_request`. No client-supplied UID or
read-limit header is trusted. Cache keys include the resulting allowance; limits are resolved even
on a warm cache hit. Budget kill switches still select the original paths, and scoring/keyset
boundaries above stay in place.

The resolver currently performs no entitlement read: a positive `OMI_LIST_READ_MAX_DOCUMENTS`
keeps its existing override, otherwise the fallback is 25,000. The existing 24-second default,
`OMI_LIST_READ_BUDGET_SECONDS`, GET-timeout headroom, middleware start stamp, and explicit internal
factory overrides keep their semantics. A future plan `api_max_reads_per_request` source belongs in
this one resolver (David ruling 2026-10-18), rather than individual routes. This adds neither a ladder,
daily count admission nor a plan change. Exhaustion stays a truncated 200 with the existing
continuation rules, never a new 4xx.

## Empty staged-task promote polls

Old desktop clients may poll `POST /v1/staged-tasks/promote` every 60 seconds. With
`OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED` on, two unfiltered `limit(1).select([])` queries check
`users/{uid}/staged_tasks` and `users/{uid}/candidates` before the control-fence read. Only physical
emptiness of **both** stores proves the released response can be returned early:
`{"promoted":false,"reason":"No staged tasks available","promoted_task":null}`.

No field predicate or field order excludes legacy rows. Any row is inconclusive, including completed,
hidden, malformed or other-generation rows: the unchanged control/eligibility/merge projection decides
what can be promoted. Candidate precedence and suppression of historical duplicates are unchanged.
A probe failure uses the original reader and shared fallback telemetry. There is no negative cache,
writer invalidation, new write, migration or index; the registered query driver proves both unfiltered
collection shapes use built-in indexes. Nonempty polls pay one or two extra bounded probes.

The counted offline fixture models a physically empty poll as two empty queries (zero returned rows,
two minimum billed reads), versus the prior control read plus two empty collection queries (three
minimum billed reads). This is a one-read reduction per eligible poll, not a zero-read result. The
~40M reads/day supplied snapshot alone does not reveal eligible request counts. If all of those reads
were this three-read empty path, the ceiling would model ~13.3M fewer reads/day; terminal/nonempty
stores and the added probes reduce or can negate that saving. Measure the eligible mix and actual
origin reads/request after an authorized deploy; no deployed saving is claimed.

## Measurement and export

`omi_external_list_http_requests_total{route,outcome}` is emitted by pure ASGI middleware outside the
GET timeout middleware. It also counts the exact staged promote POST; `route` is one of these five normalized paths; `outcome` is one of
`success`, `truncated`, `auth_error`, `validation_error`, `rate_limited`, `server_error`, `other`.
It includes dependency 401/403/429, query 400/413/422 and timeout/server failures. Four GET lists plus
the staged promote POST only; raw query
strings, UID, keys and apps are never labels. `omi_external_list_cache_total{route,outcome}` counts
`hit`, `miss`, `stored`; disabled, truncated and oversized writes are not `stored`.

Both counters register in the default Prometheus registry through `utils.observability.external_lists`,
exported by the authenticated
`routers/metrics.py` `/metrics` endpoint and `utils.metrics` sidecar port 9090 `/metrics` started in
`main.py`. `backend/deploy/cloud_run_gmp_sidecar.yaml` keeps `omi_.*`, so both reach Managed
Prometheus for backend and backend-integration. The old `list_read_*` series do not match that filter.
The in-cluster Stackdriver mirror only imports selected families from backend-integration; use the
direct GMP query surface for these measurements. No exporter/workflow/deploy change is included.
There is no new per-request read histogram: the existing read-origin scope has aggregate counters,
not a cheap isolated per-request count. Use the existing origin metric as numerator.

After an **authorized** deploy, verify its reported `OMI_BACKEND_RELEASE_SHA` and actual counter samples
in both services; code/tests alone do not establish collection. Compare a first clean hour and day,
then seven days. Keep errors, 429s, truncation, cache hit ratio, latency and origin reads/request visible.
No cohort ramp is needed for this default-on change. The deploying owner performs these checks and
rolls back the affected lever if errors/truncation or client compatibility regress.

```promql
sum by (route, outcome) (increase(omi_external_list_http_requests_total[1h]))
sum by (route, outcome) (increase(omi_external_list_cache_total[1h]))
```

Use `omi_firestore_billed_reads_by_origin_total` with existing `origin` labels
`http:/v1/dev/user/conversations`, `http:/v1/dev/user/memories`,
`http:/v1/dev/user/action-items`, `http:/v1/mcp/memories`, and the separate
`http:/v1/staged-tasks/promote` (sum collection/kind dimensions).
Divide each service+origin read delta by the corresponding service+route HTTP counter delta, and
also report successful/truncated request denominators separately from auth/429 rejects. Do not add
caller totals to origin totals or mix hosted tool traffic with REST. Trace sampling/scaling and
empty-query billing mean this is an origin read proxy; reconcile with the Firestore origin aggregate
and billing over the same window. Cache-hit metrics measure avoided list work, not billed savings.

## Savings model, not a deployed result

The supplied 2026-10-18 one-hour origin snapshot scaled to 24h reports 122,887,440 reads/day across
these routes: conversations 32,618,424; Developer memories 31,421,808; action items 31,278,216;
MCP memories 27,568,992. At $0.048/100k reads and 30 days this models $1769.58/month.
A hypothetical 25% aggregate reduction is 30,721,860 reads/day or **$442.39/month**; it is not a forecast.
A stable identical query polled every 2 seconds can model 80% cached list polls; every 5 seconds 50%;
every 10+ seconds no reuse. Auth/grant reads, cache eligibility, writes, concurrency and changing queries
reduce that saving. Request counts and duplicate-poll share were unavailable in the supplied evidence.

The nested-reader test counts actual fake-store canonical, adaptive dual-window, status and hydration
reads for mixed canonical/historical rows, including hidden rows and a legacy row missing `updated_at`.
It compares the enabled single-window path and unchanged prior path with equal ordered results.
It also exhausts a small shared allowance and verifies honest truncation and bounded physical work.
These offline fixtures demonstrate mechanisms, not production distribution or deployed savings.
