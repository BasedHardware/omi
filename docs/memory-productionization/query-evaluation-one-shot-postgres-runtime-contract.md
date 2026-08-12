# Route-free PostgreSQL query-evaluation runtime contract

Status: implemented and real-PostgreSQL qualified, inert by construction.

## Assembly

`createPostgresMemoryQueryEvaluationOneShotRuntime` is the only driver-level
assembly of the isolated read experiment. It composes the registered
production-neutral query root with the exact PostgreSQL query-input,
authoritative-graph, result/pair, and atomic grounding repositories.

The runtime exposes only two explicitly invoked bounded operations:

- `stageInput`: validate one opaque input ref, bounded query, and actual IANA
  timezone; load the current coherent graph under live experiment authority;
  materialize the exact graph-bound input; and append or replay it.
- `run`: execute the already-assigned baseline and selected shadow strategies
  for explicit repeats through the existing paired coordinator.

Construction opens no database connection and creates no route, timer, polling
loop, credential source, secret lookup, API-key pool, model default, cache,
promotion path, product mutation, graph mutation, or deployment behavior. The
codec root and model callback are explicit injected dependencies. Invalid or
accessor-bearing stage inputs fail before PostgreSQL is opened.

## Replay and grounding

Every query source load reconstructs and verifies the exact current graph
against the staged generation and digest. The producer performs final source
revalidation before atomic result-plus-grounding persistence. Complete stored
results and grounding replay without invoking the model; incomplete
persistence remains a closed stop rather than regeneration.

The pinned PostgreSQL 18.4 real test stages one empty authorized projection,
runs its baseline and selected shadow to deterministic query gaps with zero
model calls, persists and pairs both arms, then reconstructs the complete
runtime and replays the same pair with zero model calls. It also retains the
query-input restart, grant-revocation, immutable privilege, migration reapply,
and Bun 1.3.14/Node 24.19.0 parity gates.

## Explicit exclusions

- no production codec root or model credential;
- no fresh nonempty assertion-local model evidence or blind grading;
- no route, scheduler, continuous worker, Listen/Chat integration, deployment,
  traffic, promotion, or cohort action;
- no subject-tier, bystander/privacy, identity-authority, compose-voice, or
  data-disposition change.
