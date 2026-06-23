# WS-K — Client parity (needs local build)

> **Backend slice landed (WS-K):** `MemoryDB` API responses now include additive `layer`
> derived from `memory_tier` via `tier_to_layer()` in `models/memory_domain.py`.
> Persisted Firestore `tier` / API `memory_tier` is unchanged. This doc tracks the
> **client/runtime** work that requires a local desktop or Flutter build to verify.

## Morning-review checklist

- [ ] Desktop decodes `layer` from `/v3/memories` (and falls back from `memory_tier` / `tier`)
- [ ] Desktop local cache (`RewindDatabase`) stores `layer` column or derives on read
- [ ] Desktop conversation delete passes `cascade=true` (Q8 — coordinate with server-default flip)
- [ ] Flutter `memory.dart` gains optional `layer` field
- [ ] Flutter `memories.dart` provider uses `layer` when canonical cohort is enabled
- [ ] E2E: canonical-cohort user sees layer badges; legacy user unchanged

## API contract (backend — done)

| Field | Source | Notes |
|-------|--------|-------|
| `memory_tier` | Persisted / legacy API field | Unchanged; `short_term` / `long_term` / `archive` |
| `layer` | **Computed at serialization** | Same semantics as `memory_tier`; Q6 ratified name |
| `tier` | Optional client alias | Desktop already accepts `tier` **or** `memory_tier`; backend does not emit `tier` today |

Routes using `response_model=MemoryDB` (GET/POST `/v3/memories`) automatically include `layer`.

## Desktop (macOS) — files to change

### 1. `desktop/macos/Desktop/Sources/APIClient.swift` — `ServerMemory`

**Decode rule (additive):**

```swift
// Prefer explicit layer when backend sends it (WS-K); else derive from tier aliases.
let layerValue = try container.decodeIfPresent(MemoryTier.self, forKey: .layer)
let tierValue = try container.decodeIfPresent(MemoryTier.self, forKey: .tier)
let memoryTierValue = try container.decodeIfPresent(MemoryTier.self, forKey: .memoryTier)
// Resolve: layer > tier > memory_tier > default .longTerm (legacy)
// tierIsExplicit: true when any of layer/tier/memory_tier was present
```

Add `case layer` to `CodingKeys`. Map `layer` to the existing `MemoryTier` enum (same string values).

### 2. `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`

Mirror `MemoryLayer` / keep `MemoryTier` alias; document that `layer` is the canonical product field.

### 3. `desktop/macos/Desktop/Sources/Rewind/Core/RewindDatabase.swift`

- Local `memories` table has `tier` column today.
- **Option A (simpler):** keep storing `tier`; on sync from server, write `layer` if present else `tier`/`memory_tier`.
- **Option B:** add `layer` column in a migration; populate from server `layer` field.
- Reconciliation: server `layer` wins over locally derived values when `tierIsExplicit`.

### 4. `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`

Filter/query by `layer` (or map `tier` column → layer at read time). Tier filters on `MemoriesPage` should use layer semantics.

### 5. `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift`

Already partially shipped: tier filters + `tierIsExplicit` badges (WS-F). Wire badge label to `layer` when `tierIsExplicit`.

### 6. Proactive-assistant local memory upload

Audit paths that write memories around the seam; ensure uploaded payloads do not bypass canonical tier/layer policy.

### 7. Conversation delete — `cascade=true` (Q8)

**Relationship to WS-J:** Server still defaults `cascade=false` pending sign-off (§11b). Mobile passes `cascade=true`; **desktop omits it**, so memory evidence is not tombstoned on conversation delete.

**Client fix (WS-K):** when deleting a conversation, call the API with `cascade=true` (or wait for server default flip + still pass explicitly for older servers).

Search: `deleteConversation` / conversation DELETE in `APIClient.swift`.

### 8. Tests — `desktop/macos/Desktop/Tests/ServerMemoryV17DecodingTests.swift`

Add fixtures with `"layer": "short_term"` (no `tier`/`memory_tier`) and with all three fields consistent.

## Flutter — files to change

### 1. `app/lib/backend/schema/memory.dart`

Add optional `layer` field:

```dart
final String? layer; // short_term | long_term | archive
```

Decode: `layer ?? tier ?? memoryTier ?? 'long_term'`.

### 2. `app/lib/backend/memories.dart` (or `MemoriesProvider`)

When building UI models for canonical cohort, prefer `layer` for badges/filters. Legacy cohort: ignore `layer`, no new chrome.

### 3. Conversation delete

Mirror mobile: ensure `cascade=true` on conversation delete API call.

## Verification (requires local build)

### Desktop named bundle

```bash
cd desktop/macos && ./scripts/omi-auth-dump.sh   # once, from Omi Dev
OMI_APP_NAME="omi-ws-k-layer" ./scripts/omi-auth-seed.sh com.omi.omi-ws-k-layer
cd desktop/macos && OMI_APP_NAME="omi-ws-k-layer" OMI_SKIP_TUNNEL=1 ./run.sh
```

1. `./scripts/omi-ctl navigate memories`
2. Confirm canonical-cohort memories show Short-term / Long-term badges from `layer`.
3. Legacy user: no badges; `layer` in JSON ignored safely.
4. Delete a conversation with linked memories → memories tombstoned when `cascade=true`.
5. `agent-swift screenshot /tmp/ws-k-evidence.png`

### Flutter

```bash
cd app && flutter test test/backend/memory_layer_decode_test.dart  # after adding
```

### Backend (no local app — already testable)

```bash
cd backend && python3 -m pytest tests/unit/test_ws_k_layer_field.py -q
```

## Out of scope for WS-K backend slice

- Renaming persisted Firestore `tier` → `layer` (WS-G; may never happen)
- Removing `memory_tier` from API responses
- Server-default `cascade=true` flip (needs Q8 sign-off per §11b)
- Desktop Rust backend direct Firestore reads (WS-L carry-forward)
