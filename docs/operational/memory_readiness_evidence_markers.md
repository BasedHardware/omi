# Memory production readiness evidence markers

Operational evidence markers for memory rollout readiness tests and cutover gates. This file records **what must remain true** before production cutover — not iteration history.

Full Oracle milestone reviews and implementation journals live in the benchmark repo under `docs/research-logs/pipeline-memory/`.

**Status:** production rollout remains **BLOCKED / NO-GO**; `production_rollout_approved=false`.

---

## Rollout schema (P1-1)

- `rollout_schema_readiness.py`
- `schema_version=1`
- canonical nested `grants.<consumer>.default_memory`
- `production_rollout_approved=false`

## MCP API key scope (P0-1/P0-6)

- `mcp_api_key_scope_readiness.py` with default `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`; default mode performs no Firestore reads or writes.

## App/key memory grant assignment (P0-1/P0-6)

- `app_key_memory_grant_assignment_readiness.py` with default `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`; default mode performs no Firestore reads or writes.

## Shared ns2 legacy isolation (P0-5)

- `shared_ns2_legacy_isolation_readiness.py` with default `status=NOT_RUN`, `read_only=true`, and `mutation_allowed=false`; default mode performs no Pinecone query or mutation.
- legacy queries exclude memory schema records instead of letting memory Short-term/Long-term/Archive/stale/tombstoned candidates consume legacy result slots.
- No real Pinecone shared `ns2` proof was run because provider credentials/config were unavailable.

## Vector search provider proof (P0-7)

- `vector_search_provider_readiness.py`, a safe-by-default provider-proof/readiness artifact for the real Pinecone/Firestore evidence still required before production rollout.
- provider pagination/refill semantics
- No real Pinecone/Firestore provider proof was executed.
- load/recall/latency criteria remain **NOT_RUN**.

## Tools FastAPI TestClient gap (P1-5/P1-3)

- `p1_5_tools_fastapi_testclient_readiness.py`
- FastAPI `TestClient` production-dependency proof remains BLOCKED/NOT_RUN

## Cutover evidence checklist (P0-8)

- `cutover_evidence_readiness.py`
- Oracle P0-8
- T20 repair/projection-consistency
- T21 `/v3` compatibility and cursor pagination
- T22/T23 external writes and caller coverage
- milestone Oracle/final approval requires `docs/operational/memory_readiness_evidence_markers.md` updated with final approval section before production cutover.

## F4 before F5 real-service evidence (2026-06-20) {#f4-before-f5-real-service-evidence-2026-06-20}

- memory-V3-F5 real-service read-only evidence preparation
- F5 script preparation is allowed; shared non-production `--execute` requires explicit gate match; production `--execute` and runtime activation remain **NO-GO**.
