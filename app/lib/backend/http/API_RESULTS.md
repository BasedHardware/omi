# Typed HTTP outcomes — C3 / C4

Builder: App core. Skeletons change no behavior. Protected `app/test/spine/c3_*`
acceptance runs in `TZ=UTC bash app/test.sh`; retire markers only. Evidence:
null-as-empty `cfaaaf2fb9db`, detail conflation `06597a0757cb`, locked Processing
`92738118b013`, terminal lookback `8a12cfdcca38` (#10975).

## Boundary and taxonomy

ApiResult<T> is success(data, rejectedRows) or failure(ApiProblem), never null.
Extract shared.dart's uncaught send once for legacy AND typed callers, preserving
headers/pool/timeouts/clock skew and AuthTokenResult. executeApi defaults to that
path; do not infer an error by wrapping nullable makeApiCall. Its `send` seam is
already-authenticated I/O; `execution` instead injects raw transport, header builder
and AuthService into the SAME production request path. Never choose defaults when
execution is supplied. Tests exercise 401→refresh→rebuilt headers→one replay,
transient refresh without expiration, terminal refresh, and repeated 401.
Reuse refreshAndReplayAfter401; expose its observed AuthTokenResult to the typed
caller so transient refresh is not collapsed into the returned original 401.
This is a result-preserving extraction, not a second auth policy/client/cache.
Unexpected programming errors propagate; catch decode errors only in decoding.

| Outcome | UI / retry |
| --- | --- |
| DNS/socket/TLS/timeout/client exception → transport | error; bounded/manual retry |
| Missing user/token, terminal refresh, final rejected 401 → authTerminal | authenticationRequired; existing AuthService owns expiration |
| transient refresh → authTransient | error, retain account; retry, never sign out |
| 404 → notFound; 403 → forbidden | distinct terminal unavailable/access-denied, never empty |
| 402 → paymentRequired | locked; stop Processing/polling; entitlement change or explicit refresh only |
| 422 → unprocessable | terminal, stop retry; retain unsent WAL and recovery/export |
| 429 → rateLimited | error; honor valid Retry-After seconds/date, otherwise existing bounded backoff |
| 5xx → server | error; bounded/manual retry |
| malformed envelope/all rows → decode | error, manual refresh; no automatic loop |
| other non-2xx → rejected | terminal, endpoint-specific refinement during migration |
| valid decoded 2xx empty list | success, empty UI |

Retryable permits an existing bounded policy; it creates no scheduler. Never
mark 402/422 recordings uploaded. Tombstones and 204 decoding are endpoint policy.
This addresses the HTTP subset of the 39/38 cohorts, NOT raw-exception snackbars,
WAL stall-as-complete, 200-with-zero-byte exports, or generated wire DTO drift.

## Consumers and degraded data

First endpoint family: conversation list/detail plus initial load,
forceRefreshConversations, detail lifecycle and ConversationsPage empty hero.
Second family: action-items list plus fetchActionItems, forceRefreshActionItems
and ActionItemsPage empty-tasks hero. composeTypedActionItemsProvider returns
the REAL provider using ActionItemsApi. Expose apiViewState; ActionItemsApiStatus
precedes empty/loading branches with localized accessible copy and retry only when
permitted. Error is a Semantics liveRegion. Keys: omi.action_items.error/.locked/
.terminal/.auth/.empty. A failed first load never shows the no-tasks hero.
composeTypedConversationProvider returns the REAL provider using ConversationApi.
Expose apiViewState; ConversationApiStatus precedes empty/loading branches with
localized accessible copy and retry only when permitted. Error is a Semantics
liveRegion. Keys: omi.conversations.error/.locked/.terminal/.auth/.empty.
No raw server detail. A failed first load never shows the new-account hero.
Transient/decode refresh retains known data WITH an error indicator; terminal
access/auth/entitlement projection hides protected data. 402/422 leave Processing
and do not poll until an explicit eligible change. Widget acceptance mounts the
real page, not just the extracted status widget; test fixtures inject collaborators
and may not replace the page's build method or initialize production globals.

Decode envelope once, rows independently: preserve valid order, count rejects,
show incomplete data. All-invalid nonempty input is decode failure. No whereType
blanking or content/IDs in telemetry. On partial decode or retained stale data,
call shared mobile recordFallback once per request: component/area=other,
from/to=none, reason=other, outcome=degraded, event=fallback_triggered. Emit only
these existing shared fields. ApiFallbackReason is internal; do NOT add
mobile_reason or pre-register C7 names. C7 may later assign bounded vocabulary
and consumers through its reviewed contract. Hard failure with no continuation
is not fallback. Inject the sink in tests; never emit bodies, URLs, credentials,
uid, transcripts, memories or exception messages.

## Migration and enforcement

C3: shared extraction/types, then list/detail endpoint family with real provider
and page behavior. C4 batches small files (<5 calls) when independently reviewable;
split large files by endpoint family plus direct consumers (users 43, apps 30,
conversations 28 calls). Neither one-file-per-PR nor all-callers-at-once is a bar.
Old/new entrypoints coexist only during this authorized migration; preserve
existing typed wrappers until their consumers move, then delete obsolete paths.

Follow PENDING_CONTRACTS.md's adoption rule: explicit adopted file/rule pairs in
app/contracts/api-result/boundary-baseline.json, zero baseline on adoption.
Unmigrated files may grow; inventory is informational. Partial large-file migration
keeps that file legacy until complete; new extracted typed files are constrained.
The shared lexical scanner is changed-file-only, with no whole-tree debt tax.
It ignores strings/comments; unrelated nulls/catches can false-positive in adopted
API files; aliases/wrappers can evade it. Behavioral contracts remain authoritative.
No auth/cache/streaming/multipart redesign, generic UI migration or device claim.
