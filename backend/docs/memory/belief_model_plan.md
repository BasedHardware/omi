# Belief model implementation plan

Weights, not deletion. Flag off = today’s behavior. No new collections.

Flag: `MEMORY_BELIEF_MODEL_ENABLED` (`true`/`false`, default `false`).
Reader: `utils/memory/belief_model.py:belief_model_enabled()` — `os.getenv` at the
call boundary, never import-time. Same shape as
`canonical_consolidation.consolidation_enabled` (`os.getenv(..., "true")` at
`:452–454`) and `canonical_short_term_maintenance_cron` (`:473`).
Register `false` on request-path hosts and `memory-maintenance-job` in
`backend/deploy/runtime_env/_base.yaml` (compose; overlays stay unset = off).

---

## Rule 1 — currency is a read-side formula

`currency = 0.5 ** (days_since_last_evidenced / half_life_days)`; `1.0` when
`half_life_days` is null. Named-date claims use `valid_to` instead: after
`valid_to` the row is history. Bands: current `> 0.5`, fading `0.25–0.5`,
history `< 0.25`. No job writes currency; no job changes status on time alone.

**Today:** those numbers are not computed. `MemoryItem` has `valid_from` /
`valid_to` (`product_memory.py:208–209`) and `last_corroborated_at` (`:193`)
with no read consumer. `memory_item_to_memorydb` (`canonical_memory_adapter.py:292–382`)
maps `valid_to` → `invalid_at` and omits currency. Default list visibility is
status/layer only (`canonical_visibility_filter.py`).

**Seams:**

| What | Where | Today |
| --- | --- | --- |
| Pure formula + band + prior | new `utils/memory/belief_model.py` | does not exist |
| Attach to API rows | `memory_item_to_memorydb` `:292` | no `currency` / `band` / `as_of` |
| `/v3/memories` | `MemoryService` → adapter → `product_memory_read_service.py` | hide-nothing list; additive fields only |
| Chat/agent hedge | `chat_memory_adapter.py:83–91` formats `date:` from `updated_at` | no band, no `as_of` |
| Prompt/profile bar | `utils/llms/memory.py:110–128` | slotted `primary_user` facts only |
| JIT/proactive bar | `jit_trigger_contract.py:717–721` already requires `primary_user` | no currency band |

**Priors (extractor may override from wording; `user_asserted` / “remember this” → null):**

| class | `half_life_days` |
| --- | --- |
| identity, relationship | null |
| preference | 180 |
| state, plan | 30 (or `valid_to` if named date) |
| episodic | 7 |
| meta / session residue | 1 |
| meta / standing instruction | null |

Rows that predate this change have no `half_life_days`. **Derive the prior at
read time** from `user_asserted`, `kind`, `slot`, `tier`, `category` — no
backfill. Stored `half_life_days` wins when present.

---

## Rule 2 — only evidence events touch a row

Kinds: `restated` (reset `last_evidenced_at`, `corroboration_count += 1`,
append evidence pointer), `contradicted` (lower truth; supersede if the new
source is at least as authoritative), `resolved` (`valid_to = now`, keep the
row), `unrelated` (write nothing). Similarity is not evidence. Retrieval count
is not evidence. User correction / confirmation / edit is evidence. Nothing is
deleted by forgetting; `DELETE /v3/memories` stays the user-right tombstone.

**Today:** `corroboration_count` is initialized `0` (`memory_apply_store.py:765`)
and listed in `apply_long_term_patch_transaction` extra keys (`memory_apply.py:720–722`)
but **no production writer increments it**. Duplicate conversation/email rows
collide on deterministic `extraction_memory_id` and resolve via
`_existing_identical_add_row` (`canonical_memory_adapter.py:1408–1438`) without
mutating the existing row. `resolve_memory_conflict` (`utils/llm/memories.py:530`)
exists on the `memory_conflict` LLM lane and is unused on the canonical write
path. Consolidation *does* vector-neighbor + LLM route, including clock-aged
supersede (`canonical_consolidation.py:630–689`, `:1464`).

**Seams (flag on):**

| Event | Writer | Existing mutation |
| --- | --- | --- |
| Admission judge | new `utils/memory/belief_evidence.py`, called from `replace_conversation_sourced_memories` (`canonical_memory_adapter.py:1973`) and `write_canonical_extraction_memory` (`:1441`) | `apply_long_term_patch_firestore` extra updates + `memory_operations` journal (`metadata.evidence_event`) |
| Confirmation | `MemoryService.review(..., True)` `:3439` | restated |
| Correction / “that’s wrong” | `review(..., False)` and ledger edit `_ledger_correction_action_id` `:1733` | contradicted (+ supersede when the user supplies replacement text) |
| User delete | `MemoryService.delete` `:3494` | unchanged tombstone; journal the event pointer only |

Reuse `last_corroborated_at` as stored `last_evidenced_at`. Reuse
`superseded_by`, `valid_to`, `evidence[]`, `corroboration_count`. Put event
kind in `OperationLogicalPayload.metadata` (extra=forbid on the payload
fields themselves).

---

## Rule 3 — evidence at admission and retrieval, never by a clock

**Admission — where neighbors live today, and the extension:**

Conversation capture (`process_conversation.py:_extract_memories_canonical :1286`)
writes a replacement set and does **not** retrieve nearest existing memories.
The live neighbor fetch is consolidation’s
`gather_consolidation_candidates` (`canonical_consolidation.py:630`), which
calls `query_memory_vector_candidates` then the Luna consolidator.

Under the flag, **new claims look for the rows they touch** (ingest-scaled):

1. After candidates are parsed, for each new claim call
   `query_memory_vector_candidates` (same helper as consolidation; cap ~5).
2. Judge with `get_llm('memory_conflict')` (`model_config.py` lane
   `gpt-5.6-luna` / openai — already the conflict lane). Prompt lives next to
   the judge in `belief_evidence.py` (no new prompt-file tree). Structured
   output:

   ```
   EvidenceEventJudgment
     event: restated | contradicted | resolved | unrelated
     target_memory_id: str | None
     rationale: str
   ```

3. Apply the event to the **existing** row. Unrelated / empty neighbors →
   ordinary add. Similarity score never writes by itself.

**Retrieval:** chat/JIT citation does not write. Only `review` / edit /
explicit correction on the existing routes write, as in Rule 2.

---

## Fields (reuse first)

| Field | Action | Models |
| --- | --- | --- |
| `half_life_days: Optional[float]` | **add** | `MemoryItem` `product_memory.py:162`, `DurableMemoryPatch` `memory_contracts.py:510`, `memory_apply.py` extra-item allowlist `:720`, create path `memory_apply_store.py:765` |
| `last_evidenced_at` | **reuse** `last_corroborated_at` | already on `MemoryItem:193` |
| `valid_to` | **reuse** | `MemoryItem:209`, patch `:515` |
| `belief_class` | **not stored**; extractor writes `half_life_days` / `valid_to` from class+wording | — |
| `subject_scope` | stop defaulting new extraction to `primary_user`; add enum value `media_screen` | `MemorySubjectScope` `product_memory.py:53`, defaults at `memory_contracts.py:207` and `:511`, `MemoryItem:205`, `daily_memory_sweep.py:480` |
| `corroboration_count`, `superseded_by`, `evidence[]` | reuse | already on item + apply extra keys |

`MemoryDB` (`models/memories.py`) gets additive optional `currency`,
`currency_band`, `as_of` for `/v3` and chat. Released OpenAPI allows optional
response fields.

Extractor (`working_observations.py` L1 prompt `:153–162` plus
`extract_memories_from_text`): classify subject (`primary_user` / `third_party`
/ `media_screen`) and class/horizon (including meta split: standing instruction
→ null half-life; session residue → 1). Do not default `subject_scope` to
`primary_user` when the model omits it — leave unset / `third_party` rather than
invent user facts. `user_asserted` still forces null half-life.

---

## Time-only transitions to gate

These **write status from the clock**. Under the flag they must not.

| Transition | File:line | Today | Flag on |
| --- | --- | --- | --- |
| Expired ST → `reject_or_hide` | `short_term_promotion.py:267–268` | disposition from `expires_at <= now` | skip; still audit/log |
| Apply `route=reject` “TTL expired before durable admission” | `short_term_promotion.py:297–324` | hides/archives the row | do not call `apply_consolidation_decision` |
| Lifecycle eval of expiry | `short_term_lifecycle.py:167–177` | `remain_short_term` + requires decision (read-side still shows until apply) | unchanged eval; the *apply* is gated above |
| Consolidation LLM promote/archive/supersede | `canonical_consolidation.py:971+`, `:1464` | may supersede on “outdated” including age | keep content/gist routes; prompt: do not supersede/archive on age alone. `_is_promotable_for_consolidation :435` uses expiry as **eligibility**, not a status write — leave it |
| Sweep candidate retention 7d | `daily_memory_sweep.py:160` | drops staged *candidates*, not memory rows | leave |
| Sweep `subject_scope=primary_user` defaults | `:480`, `:3603`, `:4086` | misattributes gist rows | classify; do not default to user |

Consolidation into a gist that keeps source rows as evidence stays allowed.

---

## Tests

| File | Covers |
| --- | --- |
| **new** `tests/unit/test_belief_model.py` | currency, null half-life, `valid_to` → history, bands, read-side prior from `user_asserted` / tier / category, no I/O |
| **new** `tests/unit/test_belief_evidence.py` | restated increments + timestamp; contradicted supersedes when authorized; resolved sets `valid_to`; unrelated writes nothing; similarity-only does not write; flag off is a no-op |
| `test_canonical_extraction_subject_wiring.py` | extraction payload subject is not forced `primary_user`; media/third-party kept |
| `test_ws_b_short_term_lifecycle.py` / `test_short_term_lifecycle.py` | flag on: expiry does not `reject`; flag off: existing TTL reject still applies |
| `test_canonical_consolidation.py` | flag on: age-alone archive/supersede not applied by TTL helper |
| `test_chat_memory_adapter.py` | fading/history lines include `as_of` |
| `test_product_memory_read_service.py` or `test_memory_read_api.py` | list exposes `currency_band` + `as_of`, hides nothing extra |
| runtime-env tests only if `_base.yaml` gains the flag | default `false` |

---

## Deliberately out of scope

- Backfill of `half_life_days` (read-side prior is enough).
- Learned truth scores, use-weight, retrieval-count loops.
- New Firestore collections / services / eval harness / shadow gate.
- Hard-refusal of credentials and durable source exclusions (separate admission work).
- Changing user `DELETE` into a soft hide — that remains the user-right tombstone.
- Client UI chrome; API fields only.
- Rewriting consolidation into a gist engine (allowed as-is if source rows remain).
