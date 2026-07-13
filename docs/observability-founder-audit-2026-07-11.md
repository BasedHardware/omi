# Omi product trust and observability audit — 2026-07-11

## Executive verdict

Omi's product health is not proven red, but its observability integrity is red.
Several important surfaces can report green while the underlying path is broken,
unmeasured, or attributed to the wrong population. The largest opportunity is
not another dashboard. It is a product-wide proof contract: one accepted unit
of work, one authoritative terminal outcome, one opaque correlation identity,
and an explicit `PASS`, `FAIL`, or `NO_DATA` result tied to the deployed artifact.

This audit correlated repository behavior with the local Hermes project history,
PostHog, Sentry, DEV GCP logs, Kubernetes metadata, Secret Manager name inventory,
and Prometheus. The live investigation was read-only. No PostHog, GCP, Sentry,
dashboard, alert, secret, or deployment state was changed.

## Current truth

| Priority | Surface | Evidence | What the old signal implied | Actual conclusion |
| --- | --- | --- | --- | --- |
| P0 | Desktop Sentry | Seven days: 0 accepted errors, 788,989 rate-limited errors, 3,261,434 client discards | No recent issues | Error ingestion is blind, not healthy |
| P0 | Managed agent gateway | DEV 24h: 2 `chat_agent` attempts, both `/v1/messages` 503; overall fallback 2/791 = 0.253% | `/ready` 200 | Agentic managed lane was credential-unready and above the Stage-1 `<0.1%` gate |
| P0 | Gateway Prometheus | No live `llm_gateway_*` series and no gateway scrape job | Empty charts/alerts | Metrics existed in code but were not observed |
| P1 | macOS chat reliability | Seven complete days: 546 errors / 1,070 production macOS sends = 51.03% | Saved chart: 546 / 6,089 = 8.97% | Denominator mixed platforms and did not represent attempts |
| P1 | Streaming success | OpenAI streaming and Anthropic messages did not consistently record terminal completion | HTTP 200 / stream entry looked successful | Midstream failure and incomplete EOF could be counted as success or disappear |
| P1 | Chat session metadata | After synthetic cleanup, one session advertised 2,470 messages while 268 documents belonged to it | `message_count` and preview described current history | App-scoped message deletion removed documents without decrementing or resetting derived session metadata |
| P1 | Activity/adoption | 68.1% of clean macOS DAU user-days contained only start events; version chart was event-weighted | Active use and adoption | Launch reach and usage depth were conflated; chatty clients dominated version ranking |

Small samples should stay small: two failed managed agent turns prove a structural
configuration defect, not a stable population failure rate. Conversely, millions
of rejected Sentry events prove an ingestion outage, not millions of product bugs.

## The systemic forces

### 1. Green by silence

Readiness checked route shape but not the credential needed by the active
Anthropic lane. Gateway metric code existed without an authenticated scrape job.
Sentry returned no recent issues because its quota rejected all errors. A blank
or zero-valued surface must be a distinct `NO_DATA` state, never implicit success.

Required guard: every critical signal has an ingestion canary, a last-seen age,
and a `NO_DATA` alert. Readiness validates the dependencies needed by the routes
the service claims to serve.

### 2. Metric names outran their units

“macOS error rate” mixed a macOS numerator with an all-platform denominator.
“Adoption” counted events rather than latest-observed users. MAU counted any event,
while DAU mostly represented launch reach. This is a semantic ownership problem,
not a query typo.

Required guard: every metric owns a versioned contract containing:

- the product question and unit (`attempt`, `user-day`, `user`, `deployment`);
- numerator, denominator, filters, environment, and platform;
- terminal-state and cancellation semantics;
- complete-period and late-arrival policy;
- `NO_DATA` behavior, owner, and migration date.

### 3. Terminal state was not authoritative

Desktop Stop was counted as an error, success duration included post-answer
persistence, and a late bridge success could resurrect a revoked turn. Gateway
stream success was sometimes recorded at stream entry instead of completion;
fallback was sometimes recorded before the fallback path itself succeeded.

Required guard: one state owner decides the terminal outcome. Observability is a
projection of product state, never the product authority. Each accepted attempt
gets exactly one of `completed`, `failed`, or `cancelled`; fallback gets exactly
one of `recovered`, `degraded`, or `exhausted` after the alternate path terminates.

### 4. Cross-service traceability was manual

The two gateway 503s were matched to backend fallbacks by timestamps within 3ms.
The 51 gateway 401s could not be attributed safely. Desktop analytics, persisted
messages, local traces, and runtime attempts used unrelated identifiers.

Required guard: propagate one opaque request/turn identity through structured
logs and event properties. Never use UID, prompt text, or another user-derived
value as a metric label. High-cardinality IDs belong in logs/traces, not Prometheus.

### 5. Evidence drifted from the deployed artifact

Hermes project history documents strong narrative execution but repeated identity
drift: live-only configuration, a newer image overwritten by a stale deployment,
submission snapshots with changing schemas/tool sets, and rollout gates described
as seven-day checks while example queries used short windows. Component checks
were green while the reviewer-realistic or write-to-retrieval journey remained
unproven.

Required guard: every proof run records the expected and observed commit SHA,
image digest, sanitized config digest, route/scheduler target, exact time window,
step outcomes, cleanup outcome, and raw count lineage.

### 6. Derived state had no convergence owner

Desktop message writes incremented a session's `message_count`, but app-scoped
deletion removed only message documents. The live real-path gauntlet exposed a
2,202-message overstatement in one nonempty session. Preview and recency could
likewise point at a deleted message. This is the same structural class as a metric
whose numerator moves while its denominator does not: the derived value had no
owner responsible for inverse transitions or reconciliation.

Required guard: mutations update source records and their inverse counter/ID/
preview changes in the same bounded, preconditioned batch. Historical exact
repair follows a counts-only dry run and first converges the mixed legacy/v2
writers on one atomic ordering contract; it is bounded, idempotent, and separately
approved.

## Changes implemented in this PR

### Desktop product and metric integrity

- Added a typed chat attempt lifecycle with one started event and exactly one
  terminal completed/failed/cancelled event.
- Separated Stop and supersession from failures; browser setup, watchdog timeout,
  and tool stall remain typed failures.
- Ended query duration when the final answer becomes visible, before persistence
  and title generation.
- Added product-owned turn revocation. Late callbacks, successes, and failures
  cannot mutate or persist a revoked turn or overwrite a newer turn's bridge owner.
- Reused opaque `clientTurnId` to join analytics with persisted messages, and
  attached bounded runtime run/attempt IDs on completion.
- Split product origin (`main_chat`, `floating_text`, `floating_voice`, etc.) from
  canonical runtime surface, closing floating-as-main misattribution.
- Added schema-v2 input shape, partial-response, duration, surface, harness, and
  bounded error/cancel fields. The safe `error = error_class` alias remains for
  one migration release so existing Hermes/PostHog breakdowns do not go dark.
- Canonicalized tool dimensions against the checked-in capability manifest and
  collapsed unknown tools/failure codes, so decorated search queries, paths, and
  commands cannot become PostHog properties or unbounded dimensions.
- Drained bridge callbacks emitted before query return, preserved the first
  authoritative revocation cause, and made stuck-turn fallback finalize partial
  bubbles, tool rows, telemetry, and local traces exactly once.
- Removed raw onboarding text, notification/window titles, filesystem paths,
  OAuth/recording error messages, PTT query text, and session titles from product
  analytics or production breadcrumbs.
- Made production query traces shape-only and repaired trace directory/file modes
  to `0700`/`0600`; full content remains non-production debugging only.
- Changed clean app termination from a Sentry issue to a lifecycle breadcrumb.

### Gateway integrity

- Added an explicit Anthropic Messages surface with streaming/tool capability
  validation instead of pretending the agentic lane is OpenAI chat-completions.
- Readiness now fails when an enabled managed Anthropic lane has no credential;
  the Helm values wire the existing secret name into DEV and production manifests.
- OpenAI and Anthropic streams record one terminal outcome only after a valid
  terminal marker, with pre-output/midstream phase, credential source, TTFB, and
  bounded error class. Client/consumer cancellation is not counted as an error.
- Generated or propagated opaque request IDs now join client fallback decisions,
  gateway logs, errors (including unexpected 500s), and response headers.
- Gateway-to-legacy fallback is recorded only after the alternate path terminates.
  Cancellation emits a cancelled request but deliberately emits no invented shared
  `recovered`/`degraded`/`exhausted` fallback outcome.
- Added authenticated Prometheus scrape jobs and longer latency buckets, plus
  bounded auth/pre-route rejection counters and an observability self-failure signal.

These chart/runtime effects require review before deployment; the PR itself does
not mutate GCP.

### Persistence metric integrity

- Message deletion now decrements each affected session counter in the same
  bounded Firestore batch as document deletion.
- The same batch removes legacy `message_ids` and clears a preview only when it
  names a deleted message, so neither mixed-schema trace metadata nor the visible
  summary points at a removed record.
- Message and session update-time preconditions make overlapping clears exactly
  once: a losing batch re-queries instead of applying a second decrement, while
  a bounded retry cap prevents a hot session from pinning a synchronous worker.
- Regression tests cover the normal inverse transition, overlapping-clear race,
  and persistent-conflict error path.

This closes forward drift for the v2 deletion path. It deliberately does not
claim the already-inflated 2,202-message historical gap is repaired; doing that
safely requires the separately reviewed writer-convergence/backfill decision D6.

### Bounded follow-up found outside this slice

`GoalsAIService` still writes raw prompts, goal titles, and a user-text prefix to
local logs. That predates this telemetry boundary and should be removed in a small
privacy-focused follow-up with a log-content regression test; this PR does not
silently widen into the goal-generation subsystem.

The named-bundle proof run also found that a derived automation port can collide
with a bundle from another worktree: the new app launched, failed to bind, and
`omi-ctl` reached the other bundle before token ownership exposed the mismatch.
`run.sh` should require a post-launch port-owner handshake (bundle ID plus launch
token), then retry a new derived port or fail immediately. No other bundle was
stopped or modified during this audit.

## Decisions that require discussion before live mutation

### D1 — Restore Sentry as a trustworthy emergency channel

Recommendation:

1. Restore quota or reduce the ingest plan deliberately.
2. Add a temporary inbound filter for known old-client heartbeat and clean-shutdown
   issue fingerprints; do not filter real exceptions globally.
3. Promote a desktop build containing the breadcrumb fixes through beta/stable.
4. Add an ingest canary and alert on `accepted_errors = 0 AND rejected_errors > 0`.

Exit gate: a synthetic canary is accepted, a real test exception is searchable,
normal launch/termination produces no issue, and rejected volume is below budget.

### D2 — Publish PostHog reliability v2 without rewriting history

Recommendation:

- Create a new attempt-outcome insight from `telemetry_schema_version = 2`:
  completed / started, failed / started, cancelled / started, and terminal coverage.
- Filter production macOS in every series and use distinct `attempt_id`.
- Deprecate, but do not silently rewrite, legacy insight `LXEMscAj`.
- Replace event-weighted adoption with latest-observed user version/build cohorts.
- Rename all-events MAU and start-only DAU as reach metrics; add meaningful-use
  cohorts separately.
- Preserve the already-corrected dynamic latest-version chart `1XIp5SHf`.

Exit gate: a fixture cohort produces known ratios, cancellation never increases
error rate, started equals terminal after the lateness window, and every insight
links to its metric contract.

### D3 — Roll out the repaired DEV gateway deliberately

Recommendation:

1. Review and deploy the existing-secret Anthropic ExternalSecret/env wiring,
   credential-aware readiness, application instrumentation, and authenticated
   Prometheus scrape configuration to DEV only.
2. Decide whether to provision DEV `PERPLEXITY_API_KEY` or mark web search as an
   explicitly excluded/degraded managed lane. Do not let it be implicitly green.
3. Review the new `anthropic.messages` surface/capability contract and keep its
   generated inventory guard green as routes evolve.
4. Run managed and forwarded-BYOK streaming probes through completion and injected
   midstream failure, then soak for seven complete days.

Exit gate: readiness reflects the intended provider set; Prometheus observes a
smoke increment; every request has one terminal metric/log; managed `chat_agent`
has successful traffic; fallback rate is `<0.1%`; no unexplained 401 cohort remains.

No production gateway rollout is implied. Production feature flags were off and
no production gateway deployment was present during this audit.

### D4 — Make proof runs a product primitive

Recommendation: add a repo-owned proof envelope and runner used by memory,
gateway, ChatGPT review, and release qualification:

```yaml
proof_id: opaque-id
journey: memory_write_to_retrieval
expected:
  commit_sha: ...
  image_digest: ...
  config_digest: ...
window:
  start: ...
  end: ...
steps:
  - name: write
    outcome: PASS | FAIL | NO_DATA
    request_id: ...
cleanup:
  outcome: PASS | FAIL
```

First golden journeys:

1. Desktop query: submit → first output → completed/cancelled/failed → persistence.
2. Gateway managed agent: backend → gateway → provider stream completion → no fallback.
3. Memory: write → ST → hourly LT → retrieve across surfaces → delete → no retrieval.
4. ChatGPT reviewer: callback variants → OAuth → tool call → indexed query → response.

### D5 — Enforce one product mind across surfaces

Hermes evidence shows memory tier visibility/durability and ChatGPT capability copy
can diverge across desktop, API, MCP, and reviewer artifacts. Add a shared capability
manifest and cross-surface contract test before expanding the surface area. A feature
is not launched when only its read path or metadata path is green.

### D6 — Reconcile historical session metadata without a blind write

The code fix keeps previously consistent sessions consistent through app-scoped
deletion. It deliberately does not erase prior drift: an already-inflated session
retains its residual gap even after all remaining documents are cleared. Before
any live backfill:

1. Run a counts-only dry run that compares stored `message_count` with an aggregate
   count of `chat_session_id`, emitting no message text or preview.
2. Quantify affected users/sessions, read cost, maximum drift, and legacy records
   missing either session field.
3. Review a bounded idempotent repair job with per-user limits, checkpointing,
   last-update preconditions, audit output, and rollback snapshots.
4. First migrate legacy and v2 message writers to one atomic message-plus-session
   metadata transition; current writers do not all order those writes the same way.
5. Repair preview/recency only when the current preview belongs to a deleted or
   absent latest record; do not infer user content.

Exit gate: dry-run totals reconcile, a seeded concurrent-write test cannot be
clobbered, rerunning is a no-op, and sampled sessions match source-document counts.

## Thirty-day operating plan

| Week | Outcome | Proof |
| --- | --- | --- |
| 1 | Merge code integrity fixes; restore Sentry ingest; review DEV gateway rollout | Canaries accepted; focused suites green; no live prod change |
| 2 | Deploy DEV gateway slice and PostHog v2 shadow metrics | Managed probe completes; scrape target up; v2 fixture ratios exact |
| 3 | Add proof envelope and deploy convergence guard | Same runner proves gateway + one memory journey against exact digest |
| 4 | Seven-complete-day soak and founder review | Terminal coverage, fallback, latency, no-data, and artifact identity reviewed together |

## Evidence lineage

- Sentry organization/project: `omi-nk3/omi-desktop`, explicit seven-day and
  thirty-day outcome windows ending 2026-07-11/12 UTC.
- PostHog project: `302298`, seven complete UTC days, production macOS filters
  applied independently from saved insights.
- GCP DEV project: `based-hardware-dev`, explicit 24-hour log window
  `2026-07-10T06:35:59Z` to `2026-07-11T06:35:59Z`.
- Secret inspection was name/metadata only; no secret versions or values were read.
- Hermes sources included the July 2026 canonical-memory, LLM-gateway,
  PostHog-metric-cleanup, ChatGPT-submission, and codebase-guardrail projects.

All external findings must be refreshed immediately before a rollout decision;
this document is a dated evidence snapshot, not a claim that live state is static.
