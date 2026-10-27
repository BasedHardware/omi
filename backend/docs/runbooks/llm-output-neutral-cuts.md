# Exact-input LLM cost cuts

Two independent kill switches default on. The rollout lead owns deployment
and runtime settings. Deploy the backend processing hosts for L1
and `llm-gateway` for embedding reuse. No client release or stored-data
migration is required.

| Switch | On | Set `false`, `off`, `0` or `no` to restore |
| --- | --- | --- |
| `MEMORY_L1_PROMPT_SCHEMA_TRIM_ENABLED` | Generation schema omits `archive_id`, `allowed_use`, `normal_search_allowed`, `is_stable_profile_fact`, `search_result_label` | The original full generation schema |
| `VERTEX_EMBEDDING_DEDUPE_ENABLED` | Reuse successful same-owner vectors for identical Vertex inputs | Every provider call, including duplicates in a batch; clears the local cache |

These switches are read on each call. Use the deployment's existing runtime-env
override mechanism for an operational kill; keep that override in the owning
manifest/Helm values before the next deploy. Rolling back the image also
restores the prior behavior. Cache entries are memory-only and disappear with
the gateway process.

## Output contracts

L1 still uses `WorkingObservationBatch` to parse responses and the existing
validators and deterministic ID derivation. Only the private prompt schema is
projected; provenance, evidence, speaker identity, policy and public models
are unchanged. Older/full-shaped responses remain accepted.

Vertex reuse is limited to company-managed `gemini-embedding-001` with a known
authenticated owner. The hash includes tenant and user, the complete endpoint
(project/location/model), and the exact Vertex instance (text, task type,
title). No text is truncated or normalized. BYOK retains its existing rejection
before any cache lookup; ownerless and other-model requests bypass reuse.

The cache stores hashes and copied finite vectors only. Each provider instance
has a hard 600-second TTL, LRU maximum of 512 entries and maximum of 262,144
scalar values (roughly 8 MiB of Python floats plus keys/containers). A hit never
extends TTL. Batch output retains every original position; independently
concurrent requests may race on a miss without sharing cancellation state.
Errors, invalid vectors and cancelled attempts do not populate cache entries.
Successfully completed items in an otherwise failed batch may be reused on a
retry. Existing fan-out, deadlines, cancellation and wire-error behavior remain.

## Validation and measurement

Synthetic corpus tests (no production user content):

- `test_l1_prompt_schema_parity.py`: complete parsed objects match with and
  without the derived fields, plus exact legacy-schema rollback.
- `test_vertex_embedding_reuse.py`: the real Vertex adapter returns identical
  vectors, order and wire shape on the fixed corpus while provider calls fall
  from nine to three. Covers scope, changed input, kill, failure, cancellation,
  finite responses, TTL, memory bounds and mutation isolation.

These are deterministic fixture/replay claims, not a live-model quality or
production savings claim. Synthetic provider responses cannot establish what
a generative model will choose on unseen inputs.

Before/after gateway queries, taken at explicit UTC anchors after a full
lookback window on each state:

```promql
sum by (lane,model) (increase(llm_gateway_cache_prompt_tokens_total{lane=~"omi:auto:(conv-structure|memory-l1)"}[24h]))
sum by (lane,model) (increase(llm_gateway_cache_read_tokens_total{lane=~"omi:auto:(conv-structure|memory-l1)"}[24h]))
sum by (lane,model) (increase(llm_gateway_cache_eligible_attempts_total{lane=~"omi:auto:(conv-structure|memory-l1)"}[24h]))
sum by (lane_id,model,outcome) (increase(llm_gateway_requests_total{lane_id=~"omi:auto:(conv-structure|memory-l1|gemini-embeddings)"}[24h]))
sum by (outcome) (increase(llm_gateway_vertex_embedding_inputs_total[24h]))
sum by (outcome) (increase(llm_gateway_vertex_embedding_input_characters_total[24h]))
```

Embedding outcomes are `submitted`, `cache_hit`, `batch_reuse`. Character
counters are exact input sizes, not vendor-reported billable units or tokens;
submitted includes failed attempts. Vertex accounting remains usage-not-reported
instead of fabricating tokens or prices on hits. Reconcile the character reuse
ratio with vendor usage/billing before booking dollars. The prompt counters
cover cache-eligible attempts only. Compare tokens per eligible attempt as well
as totals and failure rates; traffic changes and existing C5 reuse overlap.
Initial schema/prompt changes invalidate conservative successful-input
fingerprints and content-derived prefix keys, so cold caches may increase
spend temporarily. A gateway restart clears all vector entries.

Do not book the planning estimate as realized savings. OCR truncation, C6
owner-neutral prefix activation, model changes and new capacity are excluded.

Notes duplicate-capture removal is a separate draft and requires synthetic
live-model parity on the dev gateway before promotion (lead ruling 4f6613,
2026-10-27). It is not part of this release.
