# V17 T20 Vector Readiness / Remaining Gates

**Date:** 2026-06-19  
**Scope:** T20-R shared-namespace V17 vector search over the existing `ns2` memory namespace, with authoritative `memory_items` hydration and concrete default-vector callers.  
**Status:** Ready for milestone review / Oracle review prep as an implementation milestone, not production cutover approval.

## Executive summary

T20 now has concrete default vector paths for the product route, Omi chat tool, MCP REST, MCP SSE/streamable HTTP, and developer API. These paths use existing `ns2` only as a candidate source, then hydrate through authoritative `users/{uid}/memory_items` policy before returning results.

The milestone is substantially complete for default V17 vector search surfaces that were already selected. No new vector surfaces or explicit Archive vector routes were added in this slice. Production cutover remains blocked on the remaining gates below, especially Oracle review, real cloud/Pinecone/Firestore validation, benchmark validation, production metrics aggregation, and the explicit Archive vector policy decision.

## Commit chain

| Commit | Added |
|---|---|
| `0f22ed289` | Existing-namespace V17 vector metadata/filter gateway seam: deterministic V17 vector IDs, metadata builders, default vs explicit-Archive Pinecone filters, fail-closed vector-hit parsing, and `query_v17_memory_vector_candidates(...)` over existing `ns2`; legacy `search_memories_by_vector(...)` untouched. |
| `aaee67639` | Hydrated V17 vector search service/gateway: `fetch_default_v17_vector_memory_search(...)` queries vector candidates, loads authoritative `memory_items`, hydrates/filter/ranks results, surfaces rejected counts, and keeps Archive default-invisible. |
| `4e11d7be8` | Concrete product route: `GET /v17/memory/vector/search`, gated by persisted Omi-chat default-read rollout state before vector or `memory_items` reads. |
| `fe67f2380` | Omi chat vector caller: `search_v17_default_chat_memories_vector_text(...)` and LangChain `search_memories_tool` wiring before legacy vector fallback. |
| `010b7306e` | MCP REST vector caller: `search_v17_default_mcp_memories_vector(...)` wired into `/v1/mcp/memories/search` before legacy vector fallback. |
| `e09aafc20` | MCP SSE/streamable HTTP vector caller: `routers/mcp_sse.py` `search_memories` tool now reuses the MCP hydrated vector adapter before legacy vector fallback. |
| `a8aac6806` | Developer API vector caller/endpoint: `search_v17_default_developer_memories_vector(...)` and `GET /v1/dev/user/memories/vector/search`, gated by developer default-read rollout/grant before hydrated vector search. |

## Current guarantees covered by tests

- **Default Archive-free behavior:** default vector filters and hydrated item policy include eligible Short-term + Long-term only; Archive is excluded by default.
- **Stale Short-term exclusion:** authoritative hydration/read policy excludes stale/expired/non-default Short-term even if vector candidates include those IDs.
- **Archive explicit-only:** no explicit Archive vector route was added for product, chat, MCP REST, MCP SSE, or developer API. Existing explicit non-vector Archive product search remains separate.
- **Fail-closed rollout gates:** disabled, missing, malformed, uid-mismatched, unsupported, or no-grant rollout states fail closed before vector lookup and before `users/{uid}/memory_items` reads where applicable.
- **Legacy fallback untouched:** legacy vector behavior remains the fallback/unchanged path for non-enabled callers and existing legacy functions are not repurposed as authoritative V17 paths.
- **Authoritative hydration:** vector results are candidates only; returned results are from authoritative `memory_items` hydration with policy decisions and vector-score ordering preserved after filtering.

## Verification run for this milestone artifact

Run from `/root/workspace/omi-memory-ingestion-pipeline` unless noted.

```bash
cd /root/workspace/omi-memory-ingestion-pipeline
for c in 0f22ed289 aaee67639 4e11d7be8 fe67f2380 010b7306e e09aafc20 a8aac6806; do git show -s --format='%h %s' $c; done
```

Result:

```text
0f22ed289 feat: add V17 vector metadata filter seam
aaee67639 feat: add V17 hydrated vector search service
4e11d7be8 feat: add V17 product vector search route
fe67f2380 feat: wire V17 chat vector memory search
010b7306e feat: wire V17 MCP vector memory search
e09aafc20 feat: wire V17 MCP SSE vector memory search
a8aac6806 feat: wire T20 developer API vector search
```

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_default_read_rollout_decision.py -q
```

Result:

```text
15 passed in 0.11s
```

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_*.py -q
```

Result:

```text
173 passed, 1 warning in 1.28s
```

Warning is the pre-existing `models/memories.py:108` Pydantic V1-style `@validator` deprecation warning.

```bash
cd /root/workspace/omi-memory-ingestion-pipeline
python3 backend/scripts/scan_async_blockers.py
```

Result: exit 0 with pre-existing findings only:

```text
HIGH async helpers with blocking: 41
STRUCTURAL mixed await+sync DB: 10
```

## Not run / not claimed

- Oracle review was **not** run for this milestone artifact.
- Real Pinecone validation was **not** run.
- Real Firestore/cloud validation for these vector paths was **not** run.
- Benchmark/no-silent-data-loss validation for vector search quality, latency, and recall was **not** run.
- Production metrics aggregation/central `/metrics` integration was **not** completed; current default-read metric rendering remains a local/admin export seam.
- Production rollout/cutover is **not** approved by this artifact.

## Remaining gates / decisions

1. **Oracle milestone review:** submit this T20 status plus T19/T21 read/caller context for review; apply required fixes before any production read/vector cutover.
2. **Explicit Archive vector policy:** decide whether to add a capability-gated explicit Archive vector path, continue with non-vector Archive search only, or defer until benchmark/user evidence justifies vectorized Archive. No default Archive exposure is permitted.
3. **Projection/vector consistency:** validate V17 outbox/upsert/delete/tombstone/idempotency behavior against real vector projection flows, including stale-version rejection and delete/tombstone precedence.
4. **Real service validation:** run cloud/Pinecone/Firestore integration checks with representative metadata, malformed metadata, stale vectors, cross-user vectors, and tombstoned/deleted sources.
5. **Benchmark validation:** run vector recall/precision/latency comparison anchored to Base Omi and V17 default read policy; verify Archive returned-by-default remains zero.
6. **Production metrics aggregation:** promote low-cardinality rollout/vector counters into the real ops metrics path only after selecting the central collector and cardinality rules.
7. **Next P0 gate after review:** continue source-of-truth queue toward T22/23-R API semantics/app capabilities, unless Oracle identifies T20/T19/T21 fixes that must land first.

## Recommended next action

Treat T20 default vector implementation as ready for milestone review/Oracle prep, not production launch. The next implementation slice should either address Oracle findings from this review or proceed to the next ticket-source-of-truth P0 gate (`T22/23-R` API semantics/app capabilities) while preserving the current guarantees: stale Short-term excluded by default, Archive explicit-only, rollout fail-closed, and legacy fallback untouched.
