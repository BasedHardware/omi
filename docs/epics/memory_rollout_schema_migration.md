# memory rollout/control schema_version=1 migration and compatibility note

Status: local readiness documentation only. Production rollout remains **BLOCKED / NO-GO** and `production_rollout_approved=false`.

This note makes the canonical `users/{uid}/memory_control/state` contract explicit after the P1-1 parser hardening. It is local/read-only documentation; it does not mutate Firestore, run provider/cloud calls, approve rollout, or enable production traffic.

## Canonical `schema_version: 1` rollout document

Path: `users/{uid}/memory_control/state`.

Required top-level fields for default memory reads:

- `uid`: exact uid matching the path/authenticated uid. Missing or mismatched uid fails closed with `uid_mismatch`.
- `schema_version: 1`: exact canonical rollout/control schema version. Missing or unsupported versions fail closed with `unsupported_rollout_schema`.
- `grants`: canonical nested consumer grants only.

Canonical grant paths:

- `grants.mcp.default_memory`
- `grants.developer_api.default_memory`
- `grants.omi_chat.default_memory`
- optional `grants.mcp.archive`
- optional `grants.developer_api.archive`
- optional `grants.omi_chat.archive`

Default-memory reads require the matching nested `default_memory: true` for the exact consumer. Archive remains default-unavailable: `.archive` is only a separate server-owned capability for explicit Archive read paths and does not make Archive default-visible.

Example canonical document:

```yaml
uid: memory-schema-readiness-user
schema_version: 1
mode: read
mode_epoch: 7
cutover_epoch: 7
account_generation: 3
fallback_projection_ready: true
persistent_memory_writes_started: true
writes_blocked: false
stage_gates:
  shadow: passed
  write: passed
  read: passed
grants:
  mcp:
    default_memory: true
  developer_api:
    default_memory: true
  omi_chat:
    default_memory: true
    archive: true
vector_projection_commit_id: projection-commit-1
vector_repair_outbox_enabled: true
```

Compatibility/readiness checklist before any migration or rollout stage:

1. Inventory existing `users/{uid}/memory_control/state` docs for missing `uid`, missing/unsupported `schema_version`, missing `grants`, and non-canonical consumer keys.
2. Convert valid rollout docs to the canonical schema above with `schema_version: 1` before relying on them for default reads.
3. Do not infer or backfill grants from request scopes, MCP advertised tool metadata, app declarations, top-level legacy alias fields, or client-authenticated state.
4. Keep Archive unavailable by default; only explicit Archive reads may consult canonical `.archive` capability after default-read authorization passes.
5. Run the local static/readiness artifact: `python3 backend/scripts/rollout_schema_readiness.py`.

## Rejected legacy shapes

The parser intentionally rejects the following compatibility shapes. These names may appear only in rejected-shape examples/tests/docs, not in canonical rollout examples:

- Missing `schema_version` → `unsupported_rollout_schema`.
- Missing or mismatched `uid` → `uid_mismatch`.
- Top-level `mcp_default_memory_grant` without `grants.mcp.default_memory: true` → `missing_mcp_default_memory_grant`.
- Top-level `developer_default_memory_grant` or `developer_api_default_memory_grant` without `grants.developer_api.default_memory: true` → `missing_developer_default_memory_grant`.
- Top-level `chat_default_memory_grant` or `omi_chat_default_memory_grant` without `grants.omi_chat.default_memory: true` → `missing_chat_default_memory_grant`.
- Nested alias `grants.chat.default_memory` without `grants.omi_chat.default_memory: true` → `missing_chat_default_memory_grant`.
- Nested alias `grants.developer.default_memory` without `grants.developer_api.default_memory: true` → `missing_developer_default_memory_grant`.

## Global gate and write-convergence read semantics

Global and convergence gates are server-owned controls, separate from per-user rollout docs:

- `memory_control/global_read_gate`
- `memory_control/write_convergence_gate`

Reads of these gates use the same bounded Firestore `.get(timeout=2.0)` helper as `users/{uid}/memory_control/state` when the SDK supports the timeout argument. Timeout, permission, deadline, or transport exceptions fail closed with explicit low-cardinality reasons: `global_read_gate_read_failed` denies memory product reads and `write_convergence_gate_read_failed` keeps legacy write convergence not ready. Missing or malformed gate documents remain explicit fail-closed states (`missing_global_read_gate`, `malformed_global_read_gate`, `missing_write_convergence_gate`, `malformed_write_convergence_gate`) and do not expose Archive by default or make stale Short-term memory default-visible.

## Local readiness artifact

`backend/scripts/rollout_schema_readiness.py` emits a read-only JSON inventory with:

- `status: NOT_RUN`
- `read_only: true`
- `mutation_allowed: false`
- `network_or_provider_calls_executed: false`
- `firestore_reads_executed: false`
- `firestore_writes_executed: false`
- `canonical_schema_version: 1`
- canonical valid examples for `mcp`, `developer_api`, and `omi_chat`
- rejected legacy examples that are asserted to fail closed by `backend/tests/unit/test_rollout_schema_readiness.py`

This artifact is not a production inventory, migration execution, Firestore/IAM proof, benchmark, telemetry sink integration, approval, or cloud/provider validation.
