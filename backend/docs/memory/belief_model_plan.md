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

---

## Implementation report

Branch `feat/memory-belief-model`. Flag `MEMORY_BELIEF_MODEL_ENABLED`, unset = off.

### What landed

| SHA | Commit |
| --- | --- |
| `95c8b0126f` | `docs(memory): belief model implementation plan` |
| `c390f26620` | `feat(memory): read-side currency, band, and half-life priors` |
| `f95e2efd77` | `feat(memory): extractor subject scope, half-life, and meta split` |
| `d2dc2d12ca` | `feat(memory): attach currency, band, and as_of on reads` |
| `58422f46c4` | `feat(memory): evidence events and skip time-only forget` |
| `8dbede3e58` | `fix(memory): keep resolved rows listed as history` |
| `f9f09a6741` | `fix(memory): satisfy pyright on belief-model seams` |
| `86f1c9c1e8` | `fix(memory): keep belief reads off the Gate F consolidation ratchet` |
| `ea139b987e` | `docs(memory): belief model implementation report` |
| `17cda05adf` | `feat(memory): backfill belief class so legacy rows get a real prior` |
| `b1110a20bc` | `fix(memory): stop sending high-truth writes to third_party` |
| `4e85c291f8` | `fix(memory): keep rejected consolidation rows listed as residue` |
| `0b63c06d07` | `fix(memory): keep the admission judge off the API create path` |

Rule 1: `utils/memory/belief_model.py` computes currency/band at read time. Stored `half_life_days` wins; else `belief_class`; else `user_asserted` → null. Unclassified `long_term`/`archive` rows do not decay until backfill classifies them; unclassified `short_term` uses the state prior (30d). `/v3` overlay, chat `as_of`, JIT proactive bar.

Rule 2–3: `utils/memory/belief_evidence.py` judges admission neighbors (`memory_conflict` LLM) only when a neighbor scores ≥ `ADMISSION_JUDGE_MIN_SCORE` (0.75, override `MEMORY_BELIEF_ADMISSION_MIN_SCORE`). `MemoryService.write` / `write_canonical_external_memory` schedule the judge on `llm_executor` and do not wait. Conversation `replace_conversation_sourced_memories` still admits inline. Review True→restated, False→contradicted without supersede. User delete stays a tombstone.

Time-only: `short_term_promotion.run_canonical_short_term_ttl_lifecycle` skips `reject_or_hide` when the flag is on. Consolidation prompt forbids archive/supersede on age alone. Under the flag, consolidator `reject` stays listed (`tier=archive`, `status=active`, `belief_class=meta_residue`); flag off still hides.

Backfill: `backend/scripts/backfill_belief_classes.py` (`--uid` required, `--dry-run` default, `--apply` writes). Callable `utils/memory/belief_backfill.py`. Cheap lane `memory_category`. Writes `belief_class` / `half_life_days` / `subject_scope` / optional `valid_to` through apply (`mutation_kind="belief_backfill"`). Never changes `status`, `tier`, `expires_at`, or content.

### What did not land

- No `MEMORY_BELIEF_MODEL_ENABLED=false` in `backend/deploy/runtime_env/_base.yaml`. Unset already fails closed to off; registering it is a deploy-knob follow-up (runtime-env tests would need updating).
- Sweep gist `subject_scope=primary_user` defaults (`daily_memory_sweep.py`) unchanged. Classification is on the extraction write path and the per-uid backfill.
- No adapter-level I/O test for `update_canonical_memory_review`; mapping is covered by `test_belief_evidence.py` (`patch_for_evidence_event`).
- `run-unit-ci.sh --changed-files` selected 1030 files because `product_memory.py` / `memory_contracts.py` fan out. Full pytest of that set was not run; typecheck of the typed boundary was.

### Deviations from the plan

- **Stored `belief_class`.** Plan said “not stored.” Identity’s prior is null, which is indistinguishable from a missing `half_life_days` on a legacy row. Numeric `half_life_days` still wins.
- **Per-uid backfill.** Plan said read-side prior is enough. Existing rows carry no class, so `long_term`/`archive` were decaying as state. Backfill is flag-gated, idempotent, and does not change status/tier/content.
- **Honest unclassified fallback.** `derive_half_life_days` no longer invents a state prior from category/tier for `long_term` rows with no class.
- **`resolved` does not set `status=superseded`.** That would hide the row from the default list. Currency with `valid_to` in the past is band=history; `/v3` still lists it.
- **`last_evidenced_at` is `last_corroborated_at`.** No new stored field.
- **Conversation named-date `valid_to`** is taken from MemoryDB `invalid_at` on the extraction write (that dump has no `valid_to`).
- **`belief_view_for_record` does not spell `promotion`.** Gate F’s `consolidation_symbol` regex matches that substring under `utils/memory/*.py`. The audit-bag category is still read.
- **Review(False)** lowers confidence and does not supersede. Replacement-text edits still go through the existing ledger correction path.
- **Subject scope.** Manual/API/developer-API/integration/`user_asserted` writes default `primary_user` unless the payload sets `subject_scope`. Only conversation-extracted claims go through `classify_model_about`. Media keyword heuristic deleted; `media_screen` is extractor-provided only.
- **Consolidator `reject`.** Flag on: listed residue, not `hidden`. Flag off: byte-identical hide. `belief_class` is an extra item update, not a `logical_payload` field (unknown keys would land in `metadata` and fail the patch digest).
- **Admission judge is not on the API create path.** Similarity score decides whether to ask (`ADMISSION_JUDGE_MIN_SCORE=0.75`); it never writes. Conversation post-processing stays inline.

### Tests

`cd backend` then `BACKEND_UNIT_TEST_FILE_LIST=<list> bash test.sh` (`test.sh` ignores positional paths). Venv `backend/.venv`.

| File | Result |
| --- | --- |
| `tests/unit/test_belief_model.py` | 21 passed |
| `tests/unit/test_belief_backfill.py` | 8 passed |
| `tests/unit/test_belief_evidence.py` | 11 passed |
| `tests/unit/test_canonical_extraction_subject_wiring.py` | 16 passed |
| `tests/unit/test_working_observations_extractor.py` | 22 passed |
| `tests/unit/test_memory_api_contract.py` | 7 passed |
| `tests/unit/test_memories_archive_and_read_contracts.py` | 11 passed |
| `tests/unit/test_chat_memory_adapter.py` | 13 passed |
| `tests/unit/test_jit_trigger_contract.py` | 27 passed |
| `tests/unit/test_memory_read_api.py` | 13 passed |
| `tests/unit/test_ws_b_short_term_lifecycle.py` | 14 passed |
| `tests/unit/test_canonical_consolidation.py` | 64 passed |
| `tests/unit/test_canonical_consolidation_apply.py` | 11 passed |

`backend/scripts/typecheck.sh`: 0 errors (PYRIGHT_PYTHON=backend/.venv/bin/python).

`OMI_PR_BODY_FILE=$PWD/.cursor/plans/pr-body.md make preflight`: **28 checks passed** in 211.15s (lane=local, base=`origin/main` merge-base `38d95fdca55e`). Bare `make preflight` fails without a PR: line-count ratchet and invariant/failure-class citations live in the PR body. Needed body fields:

```
INV-MEM-1
INV-MEM-3
INV-MEM-4
INV-TASK-2
Failure-Class: none
Line-Count-Exception: backend/database/memory_apply_store.py | 2883 -> 2885 | Persist half_life_days / belief_class on create.
Line-Count-Exception: backend/utils/conversations/process_conversation.py | 2793 -> 2815 | Flag-gated subject/horizon classification on extraction write.
Line-Count-Exception: backend/utils/memory/canonical_consolidation.py | 2337 -> 2348 | Reject stays listed as residue under the belief flag.
Line-Count-Exception: backend/utils/memory/canonical_memory_adapter.py | 3593 -> 3701 | Admission/review evidence events and belief overlay on the existing mutation owner.
Line-Count-Exception: backend/utils/memory/memory_service.py | 3949 -> 3951 | Attach public belief overlay on product search dicts.
```

Counts are vs current `origin/main` on the synthetic merge (main has grown `process_conversation.py` since the branch point).

### Open questions

1. Should deploy compose pin `MEMORY_BELIEF_MODEL_ENABLED=false` explicitly?
2. Should sweep gist rows classify `subject_scope` instead of defaulting `primary_user`?
3. Dogfood: run `python scripts/backfill_belief_classes.py --uid …` dry-run, inspect class/scope distribution, then `--apply` with the flag on.
