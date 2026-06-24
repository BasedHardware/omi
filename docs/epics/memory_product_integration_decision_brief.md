# V17 Memory Product Integration — Decision Brief

**Audience:** David / product decision maker  
**Source doc:** `docs/epics/v17_memory_product_integration_epic.md`  
**Purpose:** Condensed, human-reviewable version of the implementer Epic.  
**Status:** Updated with product terminology and rollout preferences.

---

## 1. Executive summary

We should integrate V17 as a **simple, gradual, whitelist-first memory upgrade** that does not break old memory behavior.

The product model should use intuitive names:

| Product term | Internal meaning | Default access |
|---|---|---|
| **Short-term memory** | Newly captured, high-recall, source-backed memory before L2 processing. | Included in Omi/agent default memory access. |
| **Long-term memory** | Clean, consolidated, durable memory after L2 processing. | Included in Omi/agent/default third-party memory access. |
| **Archive** | Older processed source-backed memory/context that is preserved and searchable, but no longer part of default long-term memory. | Explicit query only; not included by default. |

Important change from the earlier draft:

> We should **not** treat all L1 as “Archive.” New short-term memories should be directly available to Omi by default. Only items that have aged/passed through L2 processing and are no longer needed in default memory become Archive.

This gives us both:

1. **Fresh recall** — Omi can use recent short-term memory naturally.
2. **Clean durable personalization** — long-term memory stays consolidated and high-quality.
3. **Historical preservation** — archive stays queryable without flooding default memory.

---

## 2. Updated memory lifecycle

```text
Raw/source artifact
    ↓
Short-term memory
    ↓ L2 processing
Long-term memory  OR  Archive
```

### Short-term memory

Short-term memory is the first product-visible layer after extraction.

It should be:

- broad and source-backed,
- available to Omi by default,
- available to agent-mode memory tools,
- available to third-party integrations by default unless sensitive/private policy blocks it,
- time-bounded or lifecycle-managed so it does not grow forever.

Short-term memory should **not** require explicit archive search. It is part of the normal memory surface while fresh/relevant.

### Long-term memory

Long-term memory replaces the earlier “Durable memory” term.

It should be:

- consolidated,
- deduped,
- safer and more stable,
- used by chat, agents, apps, and third-party integrations by default,
- the main user-facing memory list.

### Archive

Archive is for source-backed memory/context that we preserve and can query, but do not include in default memory access.

Archive should be:

- searchable,
- source/provenance-backed,
- excluded from default Omi/agent/third-party access,
- opt-in for third-party integrations,
- usable when Omi explicitly searches older context.

### Context-only

We probably do **not** need a separate user-visible “Context only” state.

Recommended simplification:

- If it is useful enough to preserve but not stable enough for long-term memory, put it in **Archive**.
- If it is fresh and useful for near-term interaction, keep it in **Short-term memory**.
- If it is not useful/safe, reject/hide internally.

This avoids adding another confusing UI category.

---

## 3. Product principle

The key user promise should be:

> “Omi uses recent short-term memory and stable long-term memory by default, while preserving older source-backed context in Archive for explicit search.”

This is more intuitive than “Archive vs Durable.”

Users do not need to manage many states. They should mostly see:

- **Short-term** — recent things Omi may use now.
- **Long-term** — stable things Omi remembers about me.
- **Archive** — older preserved context, searchable when needed.

---

## 4. Why this still fits the benchmark result

The benchmark showed V17.9 Long-term/L2 is much cleaner than Base Omi projection:

| Metric | Base Omi projection | V17.9 Long-term/L2 |
|---|---:|---:|
| Avg utility/card | 0.386 | **1.404** |
| Positive rate | 66.7% | **87.2%** |
| Harmful/noisy per 100 contexts | 45.2 | **16.7** |
| Fabricated rate | 22.8% | **0.0%** |

But Base Omi had slightly more broad useful yield:

| Metric | Base Omi projection | V17.9 Long-term/L2 |
|---|---:|---:|
| Useful grounded safe memories / 100 contexts | **76.2** | 73.8 |

So we should not collapse everything into only Long-term memory.

The updated design preserves recall through **Short-term + Archive**, while using **Long-term** for clean durable personalization.

---

## 5. Old Omi memory migration

### Recommended default

Do **not** rewrite the whole product memory system at once.

Use a whitelist rollout:

1. Keep old memory logic working exactly as-is for everyone by default.
2. Enable the new memory system for selected internal/test accounts only.
3. Import old memories for those accounts into the new pipeline.
4. Backfill progressively.
5. Compare old vs new behavior before expanding.

### Where old memories should go

Old Omi memories should become **Short-term or Archive candidates**, not automatically Long-term.

Recommended handling:

| Old memory type | Migration target |
|---|---|
| Recent/high-confidence/manual old memories | Short-term candidate, prioritized for Long-term backfill/review. |
| Older/source-backed memory | Archive first, then eligible for backfill. |
| Noisy/uncertain/sensitive memory | Keep preserved with flags; do not automatically expose as Long-term. |

This preserves data while avoiding silent promotion of stale or low-quality facts.

---

## 6. Progressive Long-term backfill

Backfill should be gradual and boring.

It should:

1. Pick a small batch from Short-term/Archive.
2. Compare against existing Long-term memories.
3. Add/update/merge Long-term memory only when confident.
4. Otherwise leave the source-backed item in Short-term or Archive.
5. Record what happened so we can audit and rerun safely.

Backfill should **not**:

- bulk-promote everything,
- create a giant user review queue,
- inflate product analytics,
- break old memory behavior,
- require many config flags to understand,
- require users to manually curate everything.

---

## 7. Rollout model

Use a simple whitelist-first rollout.

### Phase 1 — Shadow/dry-run

- Old memory system remains active.
- New extraction/backfill runs for whitelisted test users only.
- No user-visible behavior changes unless explicitly enabled.
- Compare old vs new outputs.

### Phase 2 — Whitelist write test

- Enable Short-term/Long-term writes for selected internal accounts.
- Old paths still remain available as fallback.
- Keep backfill rate small.
- Validate deletion/export/account-purge behavior follows existing codebase conventions.

### Phase 3 — Whitelist read test

- For selected accounts, Omi reads:
  - Long-term memory,
  - Short-term memory,
  - not Archive unless explicitly queried.
- Third-party integrations receive Long-term + Short-term by default, not Archive.

### Phase 4 — Gradual cohort expansion

- Expand by account allowlist/cohort.
- Keep kill switch and rollback path.
- Monitor quality, cost, latency, deletion/export correctness, and support issues.

---

## 8. Configuration should stay simple

Avoid a pile of toggles.

Recommended minimal config:

| Config | Purpose |
|---|---|
| `V17_MEMORY_ENABLED_USERS` or allowlist | Who is on the new system. |
| `V17_MODE` | `shadow`, `write`, or `read`. |
| `V17_BACKFILL_ENABLED` | Whether progressive backfill runs for enabled users. |
| `V17_BACKFILL_DAILY_LIMIT` | Simple safety cap. |
| `V17_ARCHIVE_OPT_IN_ENABLED` | Whether Archive search can be explicitly used. |

Keep internal sub-flags only if implementation truly needs them, but do not make product rollout depend on many independent toggles.

---

## 9. UI/UX should stay simple

Do not build a heavy memory-management product first.

MVP UI should show:

- **Long-term** memories.
- **Short-term** memories if useful/recent.
- **Archive** as a separate/searchable area, not the default list.
- Simple source/provenance where available.
- Simple delete/edit controls using existing product conventions.

Avoid making users sort through many states like:

- context-only,
- hidden,
- rejected,
- pending route,
- patch type,
- L1/L2 internals.

If users want to manage memory more deeply, they can chat with Omi:

- “Remember that…”
- “Forget that…”
- “What do you remember about X?”
- “Search my older memories for…”

Agent mode should expose memory-management tools so Omi can help manage memories conversationally.

---

## 10. Third-party/default access policy

Recommended default:

| Consumer | Gets Long-term | Gets Short-term | Gets Archive |
|---|---:|---:|---:|
| Omi chat | Yes | Yes | Explicit search only |
| Omi agent mode | Yes | Yes | Tool/explicit search only |
| Third-party integrations | Yes | Yes | Opt-in only |
| Admin/debug/eval | Configurable | Configurable | Configurable |

Sensitive/private controls still apply.

Archive should not silently flow to third-party integrations by default.

---

## 11. Deletion/export/account-purge policy

Follow existing codebase conventions wherever possible.

From the current backend, relevant existing conventions include:

- memory delete paths in `backend/database/memories.py`,
- conversation delete and cascade behavior in `backend/routers/conversations.py`,
- vector deletion in `backend/database/vector_db.py`,
- account purge behavior in `backend/routers/users.py`.

Plan adjustment:

- Do not invent a separate deletion philosophy for V17.
- Extend existing deletion/export/account-purge paths to cover Short-term, Long-term, Archive, vectors, lineage, and backfill metadata.
- Keep the user-facing semantics consistent with today’s product.
- Preserve raw artifacts by default unless the existing deletion/account-purge flow deletes them.

---

## 12. Raw artifacts policy

Default should be:

> Keep raw/source artifacts by default.

Reason:

- They are needed for provenance.
- They support reprocessing and backfill.
- They reduce risk of silent memory degradation.
- They help users trust where a memory came from.

If raw artifacts are already ephemeral in some path, we should make that explicit and observable rather than pretending they were preserved.

---

## 13. Vector/search policy

Prefer KISS: avoid a separate Archive vector namespace unless we prove we need it.

Recommended starting point:

- Use the existing memory vector namespace if feasible.
- Add strict metadata fields:
  - `memory_tier = short_term | long_term | archive`
  - `uid`
  - `visibility`
  - `sensitive/risk flags`
  - `source_deleted/tombstoned`
- Query filters decide what default memory access can return.

Default queries:

| Query type | Included tiers |
|---|---|
| Default Omi memory | Long-term + Short-term |
| Third-party default | Long-term + Short-term |
| Archive search | Archive only, explicit |
| Admin/eval | Configurable |

Separate vector namespace can remain a fallback if metadata filtering becomes unsafe, leaky, or operationally confusing.

---

## 14. Safety gates

Do not expand rollout if any of these fail:

- Old memory behavior breaks for non-whitelisted users.
- Whitelisted users cannot roll back to old behavior.
- Any old/source record has unknown migration outcome.
- Deletion/export/account purge misses new memory data.
- Default Omi/third-party queries return Archive without explicit opt-in.
- Backfill creates duplicates or floods Long-term memory.
- Raw artifact preservation regresses.
- Sensitive/secret data enters Long-term or third-party access incorrectly.
- Benchmark/eval hides useful memories in Archive to make Long-term look better.

---

## 15. Key decisions now mostly resolved

| Topic | Updated direction |
|---|---|
| Naming | Use **Short-term**, **Long-term**, **Archive**. Avoid “Durable” and avoid exposing L1/L2. |
| Context-only | Do not make it a major user-visible state. Use Short-term or Archive instead. |
| Rollout | Whitelist-first, old logic untouched by default. |
| Config | Keep simple: allowlist + mode + backfill cap + archive opt-in. |
| UI | Keep simple; users can manage via chat/agent memory tools. |
| Deletion | Follow existing codebase conventions. Extend coverage, don’t reinvent. |
| Vectors | KISS: same namespace with strict metadata filters first; separate namespace only if needed. |
| Raw artifacts | Keep by default. Report ephemeral/drop paths honestly. |
| Third-party | Long-term + Short-term by default; Archive opt-in only. |

---

## 16. Bottom line

This product model is better than the earlier Archive/Durable/Context-only framing.

It is simpler for users:

- **Short-term:** what Omi can use now.
- **Long-term:** what Omi reliably remembers.
- **Archive:** older preserved context Omi can search when needed.

It also supports a safer rollout:

- old memory remains untouched for everyone by default,
- whitelist accounts can test the new system,
- backfill can run progressively,
- raw artifacts stay preserved,
- deletion follows existing conventions,
- third-party access stays useful without exposing Archive by accident.

Recommended next implementation wave:

1. Add simple allowlist/mode config.
2. Define Short-term / Long-term / Archive DTO fields and metadata.
3. Audit existing deletion/export/account-purge paths and extend them minimally.
4. Add vector metadata filters for memory tiers.
5. Run whitelisted shadow extraction/backfill without changing old behavior.
6. Compare old vs new memory behavior before any broader rollout.
