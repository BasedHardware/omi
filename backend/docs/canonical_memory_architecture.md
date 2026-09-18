---
title: Universal Memory Runtime Architecture
description: One memory authority over canonical writes and retained historical data.
---

> - **Domain vocabulary:** [backend/docs/memory/domain_model.md](memory/domain_model.md)
> - **Convergence record:** [backend/docs/epics/universal_memory_task_convergence.md](epics/universal_memory_task_convergence.md)
> - **Operations:** [universal-memory-operations.md](runbooks/universal-memory-operations.md)

Every authenticated account uses the same memory and task logic. Canonical
`memory_items` own all new writes and lifecycle transitions. Existing
`users/{uid}/memories` rows remain readable in place through a bounded,
read-only historical adapter, so general availability does not require an
account backfill.

## Lifecycle in one view

```text
Conversation, explicit memory, import, API, plugin, integration
                              │
                              ▼
                 canonical Short-term capture
                              │
                              ▼
       required normalization → TTL audit/expiry settlement
                              │
                              ▼
       one terminal consolidation route per pending item
             ┌────────────────┼───────────────┐
          promote       archive/review      reject
             │                 │              │
             ▼                 └──────┬───────┘
 atomic Long-term admission            ▼
 receipt + graph assertion       outside default access
 item + commit + operation
 projection/vector outbox
             │
             ▼
 universal reads = canonical items + retained historical adapter
                  → policy → stable-ID dedupe
```

Broad capture creates Short-term; consolidation owns the only new Long-term
route; the atomic apply transaction owns state; derived providers never own a
memory.

## Universal repository

All released REST, chat, agent, MCP, developer, tool, integration, export, and
account-lifecycle surfaces enter `MemoryService`. The service merges:

- canonical items, which are authoritative;
- historical rows, adapted to the released response model without mutation;
- durable historical overrides/tombstones, which suppress materialized or
  deleted historical copies.

Canonical wins a same-ID collision. One visibility, lifecycle, device,
locked-memory, sorting, and pagination policy applies after origin merge. A UID
list, enrollment document, client header, or physical store never chooses a
different product path.

## Capture and atomic apply

All new intake is canonical Short-term. Explicit writes can return a pending
receipt to the first-party memory list; protected chat, agent, MCP, developer,
and search consumers exclude pending raw text until required processing
completes.

Conversation extraction validates that every quote reference is grounded in a
transcript segment before source replacement. Failure preserves previous
state; a valid empty result retracts the previous source-owned cohort.
The broad L1 prompt excludes unidentified non-primary speakers, self-hedging
attribution, and generic product/company descriptions unless they express an
owner decision, preference, constraint, plan, or commitment. Named people and
known relationship roles remain eligible.

An owner rejection becomes bounded negative feedback instead of suppression
only. Extraction receives up to eight newest non-restricted active or
terminally hidden rejections from active sources in the last 30 days, at
user-message priority after the shared conversation cache breakpoint.
Consolidation receives the same set once in volatile batch context; it does not
depend on a rejected vector neighbor because rejected items are removed from
vector projection. The prompt-safe set is cached in-process for five minutes
and invalidated on memory mutation.

`memory_apply_store.py` applies the UID/account/source-generation and
idempotency fences in one Firestore transaction. It advances control/head,
item, commit, operation journal, graph assertion, and projection/vector outbox
state together.

## Lazy historical mutation

Historical data is not bulk migrated. When a historical-only memory is edited,
reviewed, relabeled, archived, or deleted, the service:

1. validates the historical row and request;
2. writes the canonical representation with the same public ID;
3. commits an active override or tombstone;
4. cleans the obsolete historical row/vector best-effort.

The suppression record commits before cleanup, preventing duplicate or
resurrected reads across retry/crash/provider outages. This path performs no
LLM call and no general re-embedding. Batch operations prevalidate before their
first mutation.

## Maintenance and Long-term admission

The dedicated `memory-maintenance-job` inventories bounded canonical pending
work, not users from an allowlist and not an unbounded account scan. Each pass:

1. prioritizes UIDs with items in the final 24 hours of the Short-term TTL via
   a lifecycle-metadata-only query, independently of the registry cursor and
   per-user cooldown;
2. drains previously committed outbox work;
3. normalizes required submissions;
4. settles TTL expiry;
5. asks `canonical_consolidation.py` for an exact item-addressed partition into
   promote, archive, review, or reject;
6. commits each route through canonical apply and drains new outbox work.

Only consolidation can issue the promotion receipt required for a new
Short-term to Long-term transition. Invalid/partial model output mutates
nothing. Revision-scoped attempts, leases, bounded retries, review quarantine,
and scan cursors prevent poison-row starvation and repeated LLM cost.
Time reaching the TTL is not itself a route: an active Short-term item remains
default-readable until canonical apply records a terminal disposition. This
prevents a missed maintenance pass from silently deleting memory while the
expiry queue continues to prioritize it.

Knowledge-ledger account cutover is not part of this serial maintenance pass.
`knowledge-ledger-drain-job` reads at most 20 canonical apply-control documents
per hourly execution with its own generation-fenced cursor, rechecks the shared
JIT rollout authority before every account and row mutation, and publishes the
cutover only after the complete-union proof succeeds. A maintenance timeout
therefore cannot starve writer-mode convergence, and a killed drain execution
or any account-level failure does not advance its page cursor. The deploy lane
grants the scheduler service account `run.invoker` on the drain job before it
creates or resumes the hourly trigger.

The text-free `canonical_memory_decision_path.v1` log joins capture regime and
grounded attribution to later applied or blocked routes by UID and memory ID.
It emits only categorical decision fields and counts, never transcript, quote,
memory, or model-rationale text.

## Search, graph, and projections

Keyword/vector providers return candidates only; every result hydrates against
the universal authoritative reader before return. Restricted, archived,
superseded, and tombstoned items remain excluded even while provider cleanup
lags.

User review preserves that same append-only boundary. Restoring a superseded
`knowledge_ledger.v1` fact does not reopen or mutate its historical row. The
authenticated memories API follows the selected fact's bounded successor chain
to the current fact, then appends a fresh replacement with retry-stable explicit
user evidence. Malformed, cross-identity, restricted, locked, or no-longer-current
chains fail closed.

A standalone closed `knowledge_ledger.v1` fact has no successor chain, but an
explicit user reopen may append one fresh current tail through the same apply
boundary. The source row remains closed and immutable. The transaction fences
owner, account/source generations, source revision/content hash, lifecycle,
source/evidence privacy state, sensitivity, lock, and rejection state before
staging content or preserved evidence. A source-keyed reopen receipt makes a
different concurrent request fail closed, while the operation journal and
deterministic row identity make the same request UUID an exact retry/readback.

`projection_sync` and `vector_sync` outbox events are the retry authority.
Restricted items are delete-only. `memory_graph_assertions/{memory_id}` is the
graph authority; retained historical graph data is a bounded read overlay and
cannot admit or mutate a memory.

## Privacy, export, and deletion

Single/batch/default/delete-all, source replacement, export, and account
deletion close over both physical formats through the universal service.
Canonical tombstones and historical override tombstones remove data from reads
immediately; external provider cleanup may finish asynchronously. Export emits
each live logical item once. Account-generation fences prevent old leases from
resurrecting a recreated account.

## Operational boundary

`MEMORY_MODE`, maintenance/consolidation switches, and cursor settings are
global readiness, incident, cost, and integrity controls. There is no
`MEMORY_ENABLED_USERS` runtime binding and no product enrollment command.

The universal dual-format reader is the rollback floor. Operators may stop new
canonical processing globally but must not roll back to a legacy-only reader,
which could hide new canonical data. Physical historical deletion requires a
separate evidence-backed approval.

## Primary seams

| Concern | Code |
| --- | --- |
| Universal service | `backend/utils/memory/memory_service.py` |
| Canonical adapter | `backend/utils/memory/canonical_memory_adapter.py` |
| Historical override paths | `backend/database/memory_collections.py` |
| Atomic persistence | `backend/database/memory_apply_store.py` |
| Required processing | `backend/utils/memory/canonical_required_processing.py` |
| Terminal routing | `backend/utils/memory/canonical_consolidation.py` |
| Scheduled orchestration | `backend/utils/memory/canonical_short_term_maintenance_cron.py` |
| Outbox delivery | `backend/database/memory_outbox_worker.py` |
| Public API | `backend/routers/memories.py` |
