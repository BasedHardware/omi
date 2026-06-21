# V17 memory UI/UX prescription — desktop-first

**Status:** First desktop iteration in progress.  
**Scope:** Establish a maintainable UI/UX pattern for V17 memory tiers on desktop before broadening to mobile/web.  
**Product source of truth:** `docs/epics/v17_memory_normative_architecture.md`.

## Product rules the UI must preserve

| Rule | UI consequence |
|---|---|
| Product tiers are exactly `short_term`, `long_term`, `archive`. | Treat tier as a first-class field, never as category/tag/visibility. |
| Default memory access is Short-term + Long-term. | Desktop default list/filter is **Default = Short-term + Long-term**. |
| Archive requires explicit Archive operation/query. | Archive is a separate explicit filter/search scope; never silently included in default list. |
| Keep UI minimal. | Show tier labels/filter/provenance/delete; do not expose lifecycle internals as management UI. |
| Legacy `/v3/memories` remains during rollout. | Missing tier decodes as Long-term for backward compatibility. |

## Oracle status for this slice

Oracle was requested for a prescriptive UI/UX review. The first browser-backed run failed while uploading attachments, and the compact retry stalled for more than 10 minutes with repeated `no thinking status detected yet`. This implementation therefore follows the three subagent audits plus the already-locked V17 normative architecture. A follow-up Oracle review should be run on the committed slice before treating this as final cross-surface design.

## Oracle/subagent consensus prescription

The first maintainable slice should avoid a large redesign. Add V17-aware primitives underneath the existing memory UI:

1. **Normalize data first.** Add an explicit client `MemoryTier` model and decode both legacy and V17 response shapes.
2. **Keep tier orthogonal to category.** Existing category filters (`Manual`, `About You`, `Insights`, `Workflow`) remain secondary.
3. **Guard default access in the client cache and view model.** Even if a backend bug returns Archive rows, the default desktop list filters to Short-term + Long-term.
4. **Make Archive explicit.** Users must select the `Archive` tier filter before Archive rows render or bulk actions apply to them.
5. **Show provenance lightly.** Cards show source label when available; detail tooltip/sheet should present `Provenance & Metadata` without exposing raw evidence internals yet.
6. **Keep deletes authoritative.** UI delete still calls backend delete; do not reinterpret delete as archive.
7. **Write tests against fixtures/model behavior.** Local test readiness starts with decode/filter/mapping tests and evolves into UI/e2e once Mac CI/dev hardware runs the app.

## Desktop information architecture

### Header controls

| Control | Default | Behavior |
|---|---|---|
| Search | empty | Searches within current tier scope. |
| Tier filter | `Default` | `Default`, `Short-term`, `Long-term`, `Archive`. |
| Category filter | `All` | Secondary filter using legacy category field. |
| Add | manual memory | Manual creation remains legacy-compatible; backend assigns V17 tier until write API is finalized. |
| Management | visibility/delete | Bulk actions operate only on current visible scope. |

### Tier labels

| Wire value | Label | User meaning |
|---|---|---|
| `short_term` | Short-term | Fresh source-backed memory while useful. |
| `long_term` | Long-term | Stable memory Omi can use by default. |
| `archive` | Archive | Older/source-backed context only used when explicitly requested. |

### Empty/error states

| State | Copy/default |
|---|---|
| Default empty | `No default memories yet` / explain that Short-term and Long-term appear here. |
| Archive empty | `No archived memories found` / explain Archive is explicit historical context. |
| Search empty | `No matching memories` scoped to current tier. |
| Load error | Existing retry pattern; do not silently fall back to legacy when enrolled V17 read fails. |

## First macOS implementation slice

Implemented/expected in this slice:

- `MemoryTier` model with labels/icons/default-access helper.
- `ServerMemory` decodes `tier`, `memory_tier`, `memory_id`, `captured_at`, `expires_at`.
- Missing tier defaults to Long-term for legacy compatibility.
- SQLite `memories` gets a `tier` column via migration, defaulting legacy rows to `long_term`.
- Local reads/search/counts default to `[.shortTerm, .longTerm]`.
- View model has a `MemoryTierFilter`; Archive renders only after explicit selection.
- Cards show tier badge and source/provenance label where available.
- Tooltip shows tier and Short-term expiration when present.
- Pure tests cover decode/filter/record roundtrip.

## What not to change before dev-cloud backend proof

- Do not add production-only archive query semantics before backend API contract is proven in dev-cloud.
- Do not make client-side Archive filtering the authority; it is only defense-in-depth.
- Do not rename/deprecate legacy categories yet.
- Do not expose processing internals (`context_only`, L1/L2, ledger head, generation, convergence) in UI.
- Do not let client select UID/mode/tier access authority.

## Windows desktop integration points

Windows/Electron should follow the same architecture but with a TypeScript normalization layer:

```ts
type MemoryTier = 'short_term' | 'long_term' | 'archive'

type DesktopMemory = {
  id: string
  content: string
  tier: MemoryTier
  defaultAccessible: boolean
  provenanceLabel?: string
  category?: string | null
  tags?: string[]
  createdAt: string
  updatedAt: string
  expiresAt?: string | null
}
```

Rules:

- Map legacy `id` and V17 `memory_id` into one `id`.
- Map missing tier to `long_term` for legacy records.
- Default list and local-agent context exclude Archive.
- Archive tab/filter is explicit.
- Bulk delete/select-all is scoped to the current tier/search view.
- Export/import should eventually preserve tier/provenance and require explicit Archive inclusion.

## Mobile integration points

- Add `MemoryTier` separately from `MemoryCategory` and `MemoryVisibility`.
- Do not encode tier into `category`.
- Default API retrieval should omit Archive by server default or request `tiers=short_term,long_term` once supported.
- Mobile item UI can show a compact tier badge and provenance chip.
- Archive belongs behind explicit filter/search; not in normal memory list.
- Offline/pending memory serialization must preserve tier/provenance once writes support it.
- Existing delete undo should stay delete-specific; archive should be a separate action if introduced.

## Web integration points

The current web memory surface is mostly public/shared conversation memory, not the signed-in `/v3/memories` manager.

If V17 tiering reaches web:

- Add tier as a facet/field, not as `structured.category`.
- Public/search defaults should exclude Archive unless explicitly product-approved and permissioned.
- Shared-memory pages must handle archived/deleted/not-found cleanly with cache invalidation semantics.
- Keep personal atomic memory DTO separate from shared conversation-memory DTO.

## Test-ready definition

Desktop local/client readiness requires:

- Model tests for legacy + V17 decode.
- Filter tests proving default excludes Archive and explicit Archive includes only Archive.
- Storage tests proving persisted tier roundtrips.
- UI/e2e update proving header tier filter, badge rendering, Archive explicitness, detail provenance, and delete/undo.
- Cross-surface fixture contract reused by mobile/web/Windows before broad rollout.

## Remaining follow-ups

1. Add backend-supported `tiers`/Archive query contract after dev-cloud proof planning confirms the API shape.
2. Update macOS e2e `memories.yaml` once a Mac runner/dev machine can exercise UI.
3. Add Windows normalization/component tests.
4. Add mobile schema/provider/widget tests.
5. Create a shared V17 memory client fixture under `docs/fixtures` or `testing/fixtures`.
