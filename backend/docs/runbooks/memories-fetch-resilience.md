# Memories fetch burst diagnosis and read resilience

## October 9, 2026 evidence

Read-only production Cloud Logging queries run on October 11 covered
`2026-10-09T15:00:00Z` through `2026-10-09T21:00:00Z`, project `based-hardware`.
Logs were retained. These are observed log entries, not unsampled traffic totals
or unique client failures; load-balancer and Cloud Run request entries can overlap.

Query: `timestamp>="2026-10-09T15:00:00Z" AND timestamp<="2026-10-09T21:00:00Z" AND httpRequest.requestUrl:"/v3/memories" AND httpRequest.status>=429`.
The query returned 495 entries with a 5,000-entry limit (not truncated):

- 360 load-balancer 429 entries had `statusDetails=denied_by_security_policy`,
  policy `prod-omi-backend-api-cloud-armor-policy`, priority `99`, action
  `THROTTLE`, outcome `DENY`, and `RATE_LIMIT_THRESHOLD_EXCEED`.
- The `backend` Cloud Run service had 22 request entries with status 503,
  44 with 504, and 19 with 500. Eleven additional 503 entries belonged to
  `omi-web-app` and reported malformed responses/instance connection errors.
- Backend 503s occurred across five revisions, with latency 6.1–24.3 seconds.
  Examples: `16:01:34.129915Z` (6.279s, `backend-c19d832-37929369543-1`),
  `16:42:10.711845Z` (6.713s, `backend-bb33e0e-37955979193-1`), and
  `20:18:48.556765Z` (6.336s, `backend-e9c7915-37983189865-1`).

A second query, restricted to `resource.type="cloud_run_revision"` and
`resource.labels.service_name="backend"` over the same window, matched
`"memory unavailable" OR "memory scan" OR "Memory scan" OR "first-page cursor" OR "DeadlineExceeded" OR "ServiceUnavailable"`.
It returned 1,672 entries (limit 5,000): 1,648 first-page cursor fallback warnings
with `detail=Memory scan budget exceeded` (1,146 historical; 502 canonical).
Hourly warning counts from 15:00Z through 20:00Z were 400, 321, 245, 199, 251, 232.
No matching ServiceUnavailable trace was found in that query. A separate
severity>=ERROR query showed Firestore `get_all` DeadlineExceeded traces at
20:33:07Z, 20:35:00Z, 20:35:01Z and 20:51:12Z, mapped to
`ListReadBudgetExhausted` while hydrating historical memories.

**Conclusion:** Cloud Armor is a confirmed source of the 429 burst component.
For backend 503/504s, expensive memory scans exhausting budgets and Firestore
read deadlines are the strongest observed mechanism. This does not establish
Firestore capacity saturation, Pinecone failure, or deploy transients as the
root cause: old logs lack per-failure structured attribution and request-correlated
exception details. Multiple revisions alone are not evidence of rollout failure.
The current router already avoids offset fallback for the typed scan-budget
exhaustion detail; that case must never be retried as a transient provider fault.

## Code behavior

MemoryService `read`, `read_page`, and `search` retry only typed transient
Firestore/Pinecone exceptions, including typed causes under a 503. There are
at most two attempts, with 25–75ms jitter. A one-second retry **admission** window
is shared across cursor/offset fallback through the original list budget.
No retry starts without 50ms headroom or after document/time exhaustion.
This does not preempt an in-flight SDK call: list RPCs still use the existing
request deadline/document allowance, and SDK internal retry policies remain in
force. Search retains its existing provider timeouts. No writes are retried.

Each operation has a thread-safe process-local circuit: three exhausted
transient requests open it for five seconds; one half-open probe can recover.
Peer calls fail fast with 503 and `Retry-After: 5`. Permanent errors retain their
status and never open the circuit. The circuit has three fixed keys, no user
registry, and is not a distributed capacity controller. Existing successful
historical-only degradation remains unchanged.

`memory_store_read` logs operation, outcome, attempts, exception class and
elapsed_ms for recovered retries and failed calls. `memories_503` logs endpoint
route template, uid_hashed (first 16 SHA-256 hex digits), exception class and
elapsed_ms once per handler-emitted 503, including async mutations and nested
router registration. Neither log emits provider messages or memory content.
Edge denials and middleware-generated failures still require edge/middleware logs.

## Operations recommendation

Review rule 99's live enforcement key and scope; sampled rate-limit keys are
IP addresses, so the documented Authorization budget must not be assumed to
match this rule. Give sync polling a separate budget from memories/goals/chat,
review burst allowance and retry feedback, and validate allow/deny logs before
changing limits. This PR makes no Armor or other infrastructure changes.
Track scan truncation and Firestore deadline rates alongside these new logs;
retries do not solve slow query/index/read-amplification problems. Server retries
cannot recover a request denied before it reaches the backend.
