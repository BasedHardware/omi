# Developer API and MCP list reads

Remaining action-item reads: [filtered compatibility scans and telemetry](dev-action-items-read-cost.md).

Round 2 changes and the current savings model: [Developer API / promote read cuts](devapi-reads-r2.md).

The three Developer API GET lists (`/v1/dev/user/conversations`, `/v1/dev/user/memories`,
`/v1/dev/user/action-items`) and REST `GET /v1/mcp/memories` share an encrypted response cache (ten seconds except write-versioned action items at fifteen minutes)
and HTTP outcome measurement. The staged-task promote POST uses the same HTTP counter and its
own write-invalidated negative cache. Hosted MCP JSON-RPC tools are outside this cache and rollout.

## Behavior and rollback

All env levers default **on**. Only a case-insensitive, whitespace-trimmed
`false` disables a lever; unset, `0`, and other values leave it on.

| Lever | Disable with `false` |
| --- | --- |
| `OMI_EXTERNAL_LIST_METRICS_ENABLED` | Stop the four-route HTTP outcome counter. |
| `OMI_EXTERNAL_LIST_CACHE_ENABLED` | Bypass all response cache reads/writes; run the original handlers. |
| `OMI_MCP_MEMORY_LIST_BUDGET_ENABLED` | Restore the prior growing-prefix MCP compatibility scan with no shared budget. |
| `OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED` | Restore unbudgeted Developer conversation offsets and omit new guidance/truncation headers. |
| `OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED` | Restore control + full projection for every staged promote poll. |

Full behavior rollback also disables the four round-2 levers documented in the linked runbook. No deployment/env values are changed by this PR.
Cache keys include budget lever states, so switching either budget off cannot replay its headers/results.
No mandatory data migration, extra serving-path Firestore write, index, rate-limit, boost, or daily ladder change is required. The optional task-completion backfill is separately authorized and never runs from a GET.
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
larger responses are served normally. Base entries expire after 10 seconds; write-versioned Developer action-item entries expire after 900 seconds; there is no process-local payload
cache. Global memory/eviction remains owned by Redis. Concurrent misses can duplicate origin work;
there is no lock or single-flight guarantee. Successful eligible responses submit short cache
populations with context to the existing db pool without awaiting them. A nonblocking 32-slot
process-local bound covers queued/running populations (at most 8 MiB of eligible bodies). Saturation
or submission failure skips population; errors, truncation, oversized or expired bodies never queue.
Future completion, failure or cancellation releases the slot. Workers recheck the query-start expiry
after queue delay; queueing never extends freshness or delays the completed origin response.

**For unversioned memories, conversations and MCP entries, up to 10 seconds of stale list data after a user write is accepted**, including deletes, edits,
locked-state changes and writes from other clients. These unversioned entries have no write invalidation. Task entries use the SDK commit fences documented in round 2. The expiry is fixed
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

## Developer memory tail: reuse read windows

`OMI_DEV_MEMORY_REUSE_READ_WINDOWS_ENABLED` defaults on; `false` restores the
previous repeated-prefix implementation. This affects Developer memory reads only.
No stored marker, migration, index, entitlement change, or serving-path write is needed.

One admitted `MemoryService.read` attempt retains both historical metadata windows
and their snapshot cursors across adapter, mixed-view, and sparse-category expansions.
Only the suffix of a larger prefix is fetched; smaller rounds use the exact original
prefix slice. Both timestamp streams remain: legacy rows missing `updated_at` still
enter through `created_at`. Visibility, canonical precedence, final ordering,
hydration of returned rows, and the 5000-row compatibility window are unchanged.
Status lookups (including absent canonical/override results) are reused across category
windows in that same attempt. Canonical queries and hydration retain their existing paths.

State belongs to one user/client and is dropped on return, failure, or whole-operation
retry. There is no cross-request negative cache or assumption that history was migrated.
Retained snapshots contain the existing metadata projection, never content; each of the
two windows is bounded by the existing 5000 candidates plus 2000 hidden-row slack.
The existing incremental-window kill switch still disables seeking when set to `false`.
The existing shared list budget charges every actual suffix/status/hydration fetch.
Exhaustion keeps the truncated 200, `X-Omi-Has-More`, and in-window next offset rules.

Physical-read parity and savings fixtures: `tests/unit/test_dev_memory_read_windows.py`.
They cover mixed canonical/legacy rows, missing timestamps, tied timestamps, suppression,
sparse categories, deep offsets, request isolation, and budget exhaustion.

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
`OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED` on, the route reads the account-generation
control fence **first on every poll**, then checks a per-UID/generation/version negative cache.
A hit returns the exact released response:
`{"promoted":false,"reason":"No staged tasks available","promoted_task":null}`.

On a miss, the **unchanged complete** compatibility projection reads historical staged rows
and Candidates, with its existing eligibility, generation, terminal suppression and merge ordering.
Only an empty projection populates a boolean marker. Terminal, malformed, other-generation and
non-staged Candidate history can therefore coexist with a cheap warm empty response. Legacy rows
missing `completed`, timestamps or scores remain visible. Nonempty requests perform zero additional
Firestore probe queries and retain the original selection. No response/user content is cached.

The TTL is **one hour**, spanning a 60-second poll plus jitter. This is independent of the
unversioned GET routes' ten-second response cache and the versioned task cache. The absolute Redis expiry (PXAT) is captured before the
origin projection; slow/expired fills cannot extend freshness. Cache I/O is synchronous in the
existing sync route, uses a lazy Redis client with 100ms socket/connect bounds, and never queues
executor work. Read, fill and invalidation faults record shared fallback telemetry and preserve
original reads/mutation results. Flag-off promote reads do no negative-cache Redis I/O.

Each UID has a random healthy version with a seven-day TTL. An atomic Redis Lua lookup
initializes a missing version with a fresh UUID, never a fixed reusable token. The marker key
includes authenticated UID (hashed), fresh account generation and the version captured **before**
projection. Fill compares that version again and can only address its captured key; a concurrent
write cannot bless an old result under a new key. Hits recheck the version after the marker read.

Before mutation, an atomic Lua command sets the negative version to a non-cacheable busy sentinel
and records a unique writer token. Busy readers bypass **both negative hits and fills**, running
the original projection with its existing Candidate compatibility-cache semantics. In `finally`,
every covered writer rotates the existing `fsr:s5:candidates:version:{uid}` compatibility version,
even if its mutation raised after a partial commit. Only a confirmed rotation plus a confirmed
begin may release that writer's token. Atomic completion publishes a fresh negative version only
when every overlapping writer has completed successfully. It never locks or serializes mutations.

A compatibility SET failure, missing/uncertain writer token or poisoned overlapping writer leaves
negative caching disabled. A failed completion retains the busy sentinel. Lost replies cannot
retry the mutation; if completion actually published a version before its reply was lost, every
dependency had already been confirmed. Busy/poison state has **no automatic expiry**: timeouts
must not turn an unconfirmed mutation into a cacheable empty projection. An abandoned writer can
therefore leave a UID bypassed until an operator reviews/resets that cache state; no automatic
repair or production mutation is included here. Monitor `bypass` and invalidation faults alongside
reads/request. The Lua commands require Redis scripting; a denied/unavailable EVAL fails open to
the original read/mutation, without making the negative cache a request prerequisite.
An operator must confirm that no mutations are in flight before resetting this cache state.

All eight legacy staged mutation owners invalidate before mutation and in `finally`: create,
delete, complete promotion, suppress terminal, batch scores, promote, clear and conversation-item
recovery. Router retirement delegates to delete; migration/reconciliation delegates to Candidate
owners. The existing Candidate invalidation decorator now surrounds its five mutation entrypoints
(create/coalesce, compatibility score, resolve task, resolve without mutation, reconcile migrated)
with the same coordinator. Workstream Candidate resolution also invalidates conservatively,
even though its subject is outside staged compatibility. Claim/reservation helpers only write
resolution-claim records, not either projected collection. No other in-tree application writer was
found for these collections. Recursive account-subtree erasure also uses the before/finally
fence, including partial erasure failures. Account-generation changes always select a new key.

The final invalidation also fences fills started during a mutation, and runs on errors because a
multi-batch writer may have committed a prefix. Writers invalidate even when their local read flag
is off, protecting enabled readers on other revisions. With healthy Redis, a completed normal write
is visible to the next poll. If compatibility invalidation fails after a confirmed busy fence,
the original compatibility entry may still return its baseline stale empty result for its own TTL
(default 30 seconds); it can never acquire a new one-hour negative lease. Recovery/expiry of that
compatibility entry exposes pending work even while negative caching stays bypassed.

Immediate visibility cannot be guaranteed when Redis does not confirm the pre-write fence itself,
or when old deployed/external writers bypass these hooks. A previously published marker may then
survive until its original one-hour deadline. Redis eviction/loss of coordinator metadata is also
outside durable mutation authority: random versions prevent ABA reuse, and a missing completion
token poisons rather than releases the cache, but simultaneous lost state and unavailable fences
cannot provide a distributed visibility guarantee. Disable the read lever during a coordinated
older-writer rollback or when immediate freshness is required through Redis faults. No new
negative-cache lease is published following a known dependency-invalidation failure.

If a cold empty projection costs R modeled billed Firestore reads (including its control read), a
warm hit costs **one control read**, even with retained history. Stable polls every 60 seconds with
a one-hour TTL avoid 59 of 60 unchanged-empty origin scans;
average reads become `1 + (R - 1) / 60` before writes, jitter, cache faults or the independent Candidate
cache affect the mix. The long-TTL kill switch restores the former 90-second model. The offline fixtures measure R=3 for physically empty stores and R=581 with
retained history; warm hits cost 1 in both. No extra Firestore writes, new query, index, migration,
rate limit or production configuration change is added. The supplied ~40M reads/day snapshot does
not establish logical-empty frequency or R, so no 40M-read or deployed saving is claimed.

## Measurement and export

`omi_external_list_http_requests_total{route,outcome}` is emitted by pure ASGI middleware outside the
GET timeout middleware. It also counts the exact staged promote POST; `route` is one of these five normalized paths; `outcome` is one of
`success`, `truncated`, `auth_error`, `validation_error`, `rate_limited`, `server_error`, `other`.
It includes dependency 401/403/429, query 400/413/422 and timeout/server failures. Four GET lists plus
the staged promote POST only; raw query
strings, UID, keys and apps are never labels. `omi_external_list_cache_total{route,outcome}` counts
`hit`, `miss`, `stored`; disabled, truncated and oversized writes are not `stored`.
`omi_staged_promote_empty_cache_total{outcome}` separately counts bounded negative-cache outcomes
`hit`, `miss`, `stored`, `expired`, `version_changed`, `invalidated`, `unavailable` and
`invalidation_unavailable`, `bypass`. It has no UID, generation, client or query labels.

The HTTP/list counters register through `utils.observability.external_lists`; the negative-cache
counter registers through `database.staged_promote_cache`. All use the default Prometheus registry,
exported by the authenticated
`routers/metrics.py` `/metrics` endpoint and `utils.metrics` sidecar port 9090 `/metrics` started in
`main.py`. `backend/deploy/cloud_run_gmp_sidecar.yaml` keeps `omi_.*`, so all reach Managed
Prometheus for backend and backend-integration. The old `list_read_*` series do not match that filter.
The in-cluster Stackdriver mirror only imports selected families from backend-integration; use the
direct GMP query surface for these measurements. No exporter/workflow/deploy change is included.
The new `omi_external_list_firestore_reads_per_request{route}` histogram uses the existing SDK read amounts and shared request trace holder. It includes dependency/auth reads and zero-read hits, and closes before response background work. See round 2 for query examples.

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

## Historical round-1 savings model, not a deployed result

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
