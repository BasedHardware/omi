# Universal memory operations

**Owner:** backend on-call

**Scope:** the universal canonical writer, dual-format reader, historical
compatibility adapter, and the retired Short-term maintenance job's follow-up
owners (inline required intake; Dream's sweep for retries).

There is no product UID enrollment, dogfood activation, or general account
backfill. Every authenticated user follows one memory/task authority. Existing
historical documents are read in place and materialized only when that item is
mutated. The retired JIT ledger drain and daily memory sweep no longer run;
`memory-maintenance-job` was retired with them on 2026-10-26 (dev-only, never
served production); their stored records remain available to export, deletion,
and retention paths.

## Controls

| Control | Owner | Meaning |
| --- | --- | --- |
| `MEMORY_ENABLED` | backend manifests | Canonical intake incident stop; unset fail-closes to off. Never a user selector. |
| inline required-intake switch | lane memreq | Kill switch for inline per-write L2 normalization; see the feature-flag registry row once memreq lands. |
| `MEMORY_CANONICAL_MAINTENANCE_ENABLED` / `MEMORY_MAINTENANCE_CAPTURED_AFTER` / `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` / `MEMORY_CANONICAL_MAINTENANCE_FLEX` | retired | Runtime-env validation rejects these from all Cloud Run jobs and canonical-memory service surfaces (Cloud Run and GKE). |

`MEMORY_ENABLED_USERS` and code-owned product UID lists are retired. Runtime
validation rejects a reintroduced per-user memory inventory and any
reintroduction of the retired maintenance switch or deploy window.

## Deploy order

1. Run the hermetic memory pipeline, universal service/mutation, task
   no-drop/no-duplicate, privacy/export, runtime-env, and OpenAPI compatibility
   contracts for the exact SHA.
2. In a non-production project, deploy that SHA with two or more synthetic
   authenticated users: historical-only, canonical-only, and mixed rows.
3. Verify identical logical IDs, ordering, lifecycle/device/visibility policy,
   duplicate suppression, and cross-UID isolation across REST, chat, MCP, tools,
   and developer surfaces.
4. Verify inline required processing at write time and Dream's scheduled sweep
   identity/cadence; the retired maintenance job no longer deploys.
5. Exercise the global stop and restore path. Record revision, image digest,
   project/database identity, Scheduler/job result, and content-free counters.
6. Deploy the same universal reader before enabling canonical intake in
   production. Do not add a canary UID or enrollment document.

## Content-free observations

Record counts only: canonical rows returned, historical rows returned,
canonical-over-historical suppressions, override/tombstone suppressions,
malformed historical rows, cursor failures, pending/terminal maintenance rows,
outbox lag/dead letters, and historical cleanup failures. Do not log memory
content, embeddings, or provider payloads.

The universal repository exports these low-cardinality Prometheus counters:

- `memory_universal_read_origin_total{origin="canonical|historical"}`;
- `memory_historical_suppression_total{reason="canonical_identity|canonical_state"}`;
- `memory_historical_materialization_total{outcome="not_needed|committed"}`.

Alerting must aggregate those fields without UID, memory ID, or content labels.

## Incident actions

1. Keep the universal dual-format reader deployed. Rolling back to a
   legacy-only reader can hide newly canonical data and is forbidden.
2. Stop inline per-write L2 cost with the inline required-intake kill switch
   (lane memreq; its registry row names the env). Pausing the Dream sweep stops
   only retry/backlog cost, not new inline calls.
3. Stop scheduled retry/backlog work by pausing the Dream sweep Scheduler
   (`dream-agent-sweep-hourly`); continue authoritative reads.
4. If new intake itself is unsafe, use the global memory incident mode owned by
   the deployment. Never route selected UIDs to a legacy writer.
5. Preserve canonical items, historical rows, overrides, tombstones, journals,
   and outbox state. Physical deletion requires separate approval.
6. After repair, restore globally, run one bounded Dream sweep execution with
   `--wait`, then confirm a later Scheduler execution and provider lag recovery.

## Required rollback rehearsal

The rehearsal must show that stopping new canonical processing does not hide
historical or canonical data, does not resume a legacy writer, and does not
make task intelligence unavailable. Cross-origin deletes remain suppressed by
canonical tombstones/overrides while providers drain.
