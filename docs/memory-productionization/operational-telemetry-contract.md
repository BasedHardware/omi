# Content-safe operational telemetry contract

Status: pre-registered, production-neutral P8 boundary.

## Scope

This contract defines one low-cardinality operational event boundary for the
service, PostgreSQL adapter, durable-memory workers, authority fences, and work
backlog. It does not select a metrics vendor, logging backend, runtime, route,
database client, deployment, alert threshold, or SLO.

Existing QA evidence counters remain producer/consumer test arbiters. Existing
model-call telemetry remains a separate prompt-coordinate contract. Neither is
silently reinterpreted as production service health.

## Privacy and cardinality boundary

Operational events contain only a version, one closed event family, closed
stage/outcome values, bounded integers, and null where the measure does not
apply. They contain none of:

- account, principal, credential, grant, session, request, run, job, evidence,
  claim, entity, memory, conversation, or device identifiers;
- routes, URLs, headers, tokens, queries, SQL, model prompts, responses,
  excerpts, filenames, stack traces, exception text, provider bodies, or
  arbitrary labels/tags;
- timestamps supplied by request/work data; the eventual sink owns collection
  time; or
- digests that can become stable cross-event user or content correlation keys.

The exact families are:

1. `service`: closed operation class, outcome, HTTP status class, duration,
   and in-flight count;
2. `database`: pool/transaction/migration/query stage, closed outcome,
   duration, and bounded pool active/idle/waiting counts;
3. `worker`: closed memory work kind and lease/produce/stage/append/deliver/
   recover stage, closed outcome, duration, attempt, producer-call count, and
   materialization count;
4. `fence`: read/write/work/projection door, closed admission/refusal outcome,
   and whether the refused envelope was preserved; and
5. `backlog`: closed work kind, ready/leased/retry-wait/dead counts, and oldest
   ready age.

No extension field or caller-defined string is accepted. A new metric label is
a schema revision and cardinality/privacy review.

## Availability and behavior

- Builders accept unknown input, reject proxies/accessors/classes/extras,
  detach values, and return deeply frozen plain data.
- All numbers are finite safe integers in explicit ranges. Overflow,
  contradiction, and impossible state fail closed before the sink.
- The sink is synchronous and injected. It may enqueue into its own bounded
  implementation, but this boundary never awaits it.
- Missing sinks, malformed events, and sink exceptions become a local
  `not_emitted` result. They never change an HTTP response, fence decision,
  lease, retry, model result, graph commit, or database transaction.
- The event emitter never writes files, reads environment variables, opens a
  network connection, logs, or imports a vendor SDK.
- Production composition must count dropped/rejected telemetry through a
  separate process-level bounded health counter. That counter itself carries
  no dynamic label.

## Semantic rules

- Service success is recorded after the response exists, not at dispatch.
- Database success is recorded after commit/rollback completion as applicable;
  acquiring a pool slot is distinct from executing a transaction.
- Worker success is recorded from the durable work outcome, never merely from
  dispatch or model return. Dead/failure is not abstention.
- Fence telemetry is derived from the exact typed decision the fence produced.
  A caller cannot supply a free-form refusal reason.
- Backlog gauges come from one coherent database snapshot/frontier. Absence of
  a scanner or failed query is `unavailable`, never an all-zero backlog event.
- Per-account debugging belongs in separately authorized, retention-bounded
  support tooling; it must not be added as an operational metric label.

## Acceptance tests

1. Exact valid event for every family is detached, deeply frozen, and
   byte-stable.
2. Extras, missing keys, wrong enums, NaN/infinity/fractions/negative/overflow,
   contradictions, getters, proxies, classes, sparse/decorated arrays, and
   hostile strings are rejected without executing attacker code.
3. A corpus of owner IDs, tokens, query/SQL text, excerpts, provider bodies,
   ANSI/newlines, and stack traces cannot appear in any serialized event.
4. Missing/throwing sinks and rejected events leave the wrapped operation's
   return, exception, and call count unchanged.
5. Concurrent owner operations produce the same closed event bytes when their
   operational outcome/counts are the same.
6. Instrumented service, database transaction, formation dispatch, and fence
   tests prove events are emitted only at the semantic producer point.
7. Backlog unavailability cannot emit zeros; a coherent snapshot can.
8. Import-graph tests prevent vendor, environment, filesystem, and route/model
   dependencies from entering the telemetry core.

## Exclusions and gates

- No default sink, exporter, dashboard, alert, sampling policy, retention
  policy, or production activation in this unit.
- No raw OpenTelemetry attributes or arbitrary structured logging facade.
- No production-readiness claim before the exact image and load gate proves the
  chosen sink bounded under backpressure and useful at forecast cohort load.
