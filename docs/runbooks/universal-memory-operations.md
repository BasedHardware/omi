# Universal memory operations

**Owner:** backend on-call

**Scope:** the universal canonical writer, dual-format reader, historical
compatibility adapter, and Short-term maintenance job.

There is no UID enrollment, allowlist, dogfood activation, or general account
backfill. Every authenticated user follows one memory/task authority. Existing
historical documents are read in place and materialized only when that item is
mutated.

## Controls

| Control | Owner | Meaning |
| --- | --- | --- |
| `MEMORY_MODE` | backend + maintenance manifests | Global readiness/incident declaration. Never a user selector. |
| `MEMORY_V3_GET_ENABLED` | backend manifests | Deprecated, non-authoritative declaration pending manifest cleanup. Never a user selector. |
| `MEMORY_CANONICAL_MAINTENANCE_ENABLED` | `memory-maintenance-job` only | Enables scheduled Short-term normalization, TTL audit, consolidation, and outbox drain. |
| `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` | maintenance job | Global L2 cost/incident switch. Required processing, TTL audit, and outbox ownership remain independent. |
| consolidation batch/candidate caps | maintenance job | Bound one L2 call and one pass. |
| cursor secret/version/TTL | backend | Unused by the live route; removal requires confirming no separate consumer owns the binding. |

`MEMORY_ENABLED_USERS` and code-owned product UID lists are retired. Runtime
validation rejects a reintroduced per-user memory inventory.

## Deploy order

1. Run the hermetic memory pipeline, universal service/mutation, task
   no-drop/no-duplicate, privacy/export, runtime-env, and OpenAPI compatibility
   contracts for the exact SHA.
2. In a non-production project, deploy that SHA with two or more synthetic
   authenticated users: historical-only, canonical-only, and mixed rows.
3. Verify identical logical IDs, ordering, lifecycle/device/visibility policy,
   duplicate suppression, and cross-UID isolation across REST, chat, MCP, tools,
   and developer surfaces.
4. Verify the dedicated maintenance job and Scheduler identity/cadence. The job
   must advance the bounded, content-free account-registry cursor without
   scanning the users collection or repeating one fixed page.
5. Exercise the global stop and restore path. Record revision, image digest,
   project/database identity, Scheduler/job result, and content-free counters.
6. Deploy the same universal reader before enabling canonical intake or
   maintenance in production. Do not add a canary UID or enrollment document.

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

Maintenance receipts additionally report retryable outbox failures, dead
letters, acknowledgement failures, processed accounts, and cursor progress.
Alerting must aggregate those fields without UID, memory ID, or content labels.

## Incident actions

1. Keep the universal dual-format reader deployed. Rolling back to a
   legacy-only reader can hide newly canonical data and is forbidden.
2. Stop L2 cost or bad consolidation with
   `MEMORY_CANONICAL_CONSOLIDATION_ENABLED=false`.
3. Stop scheduled mutation with
   `MEMORY_CANONICAL_MAINTENANCE_ENABLED=false`; continue authoritative reads.
4. If new intake itself is unsafe, use the global memory incident mode owned by
   the deployment. Never route selected UIDs to a legacy writer.
5. Preserve canonical items, historical rows, overrides, tombstones, journals,
   and outbox state. Physical deletion requires separate approval.
6. After repair, restore globally, run one bounded maintenance execution with
   `--wait`, then confirm a later Scheduler execution and provider lag recovery.

## Required rollback rehearsal

The rehearsal must show that stopping new canonical processing does not hide
historical or canonical data, does not resume a legacy writer, and does not
make task intelligence unavailable. Cross-origin deletes remain suppressed by
canonical tombstones/overrides while providers drain.
