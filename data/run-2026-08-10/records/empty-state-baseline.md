# Empty-state baseline — served surfaces (M2 / D-3)

Measured 2026-08-10 against `lane/grok-polish` @ `aac098b87a` (clean, tracking
`origin/core/foundation`). No surface code changed for this record.

## Verdict on the "1 of 8" measurement

**Agree, with one qualification.**

Counting production surfaces that expose a distinct `data-empty-kind` attribute:
exactly **1 of 8** — `MemoriesPlatformProduction`. That is the right yardstick for
the worked example's shape.

Qualification (does not overturn the count): `MemoriesProduction` and
`ConversationsProduction` already branch true-empty copy (`*.emptyTitle` /
`*.emptyBody`) away from filter-miss copy (`common.noResults`) when
`refresh.phase === "ready" && rows.length === 0`. They still lack `data-empty-kind`,
and both still send non-ready zero-row states down the `common.noResults` branch.
So they are copy-partial, attribute-fail — not a second met surface.

Out of scope for implementation (fixture-only): Chat, Listen, Settings. They are
included only in the 8-count above.

---

## In-scope surfaces

### 1. MemoriesPlatformProduction (platform Memories — served when selection is platform)

| Reachable empty condition | How it becomes reachable | Today | Planned `data-empty-kind` |
|---|---|---|---|
| Recall envelope absent | `recall.kind === "unknown"` and zero loaded items | Distinct UI + `data-empty-kind="recall-unknown"` | `recall-unknown` (already) |
| Declared query gap | known recall with `queryGap: true`, zero items | Distinct UI + `data-empty-kind="query-gap"` | `query-gap` (already) |
| Empty known projection | known recall, not a gap, zero items | Distinct UI + `data-empty-kind="empty-projection"` | `empty-projection` (already) |
| Client filter miss | items loaded, local search leaves `visibleItems.length === 0` | Distinct UI + `data-empty-kind="filtered-out"` | `filtered-out` (already) |

Conflated today: none among these four. **Bar met.** Worked example; do not redo.

### 2. MemoriesProduction (legacy Memories — served when selection is legacy)

| Reachable empty condition | How it becomes reachable | Today | Planned `data-empty-kind` |
|---|---|---|---|
| True empty | `ready` and `rows.length === 0` | `memories.emptyTitle` + `memories.emptyBody` — no attribute | `empty-projection` |
| Filter miss | visibility chip and/or local search leave `visibleRows.length === 0` while not true-empty | `common.noResults` — no attribute | `filtered-out` |

Conflated today:

- Non-ready zero rows (`initial-loading` / `unavailable` / `saved-but-refresh-failed`
  with an empty list) fall through to the same `common.noResults` branch as a real
  filter miss. Refresh notices still render separately; the empty region lies.

### 3. TasksProduction

| Reachable empty condition | How it becomes reachable | Today | Planned `data-empty-kind` |
|---|---|---|---|
| True empty | `ready` and `rows.length === 0` | `tasks.emptyTitle` + `tasks.emptyBody` — no attribute | `empty-projection` |
| Filter miss | `rows.length > 0` but the local description query matches nothing | Still renders the three day groups; each empty group shows `lifecycle.empty` ("Nothing here yet") — **no surface-level filter-miss** | `filtered-out` |

Not surface empty-kinds (leave alone):

- Per-group empty inside a non-empty filtered set (`lifecycle.empty` under Today /
  Tomorrow / Later while another group still has cards) — day-bucket emptiness, not
  "the query returned nothing."
- `initial-loading` with zero rows → `common.loading` (refresh state).
- `unavailable` with zero rows → `lifecycle.unavailable` (refresh state).

Conflated today: a full filter miss is indistinguishable from "every day bucket is
empty," and there is no `data-empty-kind` on the true-empty branch either.

### 4. ConversationsProduction

| Reachable empty condition | How it becomes reachable | Today | Planned `data-empty-kind` |
|---|---|---|---|
| True empty | `ready` and `rows.length === 0` | `conversations.emptyTitle` + `conversations.emptyBody` — no attribute | `empty-projection` |
| Filter miss | starred / folder chip and/or local search leave `visibleRows.length === 0` while not true-empty | `common.noResults` — no attribute | `filtered-out` |
| Detail miss | `detailId` set, row absent from loaded list | `conversations.detailNotFound` — no attribute | `detail-not-found` |

Conflated today: same non-ready zero-row → `common.noResults` fall-through as
MemoriesProduction.

Note on `folder:${folder.id}` (line ~312): used as `ProductionFilterOption.value`
only; chips render `folder.name` via `option.label`. Not a user-visible storage id.
Recorded here for M4; no empty-state action.

### 5. HomeProduction

| Reachable empty condition | How it becomes reachable | Today | Planned `data-empty-kind` |
|---|---|---|---|
| True empty | combined refresh allows the empty region, spine has zero rows, and no filter is active (`kind === "all"` and query blank) | `common.noResults` (and clear-search only when a needle exists) | `empty-projection` |
| Filter miss | kind chip ≠ all and/or query needle active, `results.length === 0` | Same `common.noResults` | `filtered-out` |

Conflated today: true-empty and filter-miss share one branch and one string. The
`filtering` boolean already exists in the component and is unused for presentation.

Catalog keys already present that may supply true-empty copy without inventing voice:
`home.startTyping` ("Start typing to search what's saved"). Final key choice deferred
to M2 implementation (catalog → legacy → adjacent), recorded then.

---

## Out-of-scope production surfaces (count only)

| Surface | `data-empty-kind` today | Notes |
|---|---|---|
| ChatProduction | none | Fixture-only; has true-empty title/body. Not this lane. |
| ListenProduction | none | Fixture-only; no list empty branch found in a quick grep. Not this lane. |
| SettingsProduction | none | Fixture-only; no list empty branch found in a quick grep. Not this lane. |

---

## Implementation order (from brief)

- **M2:** Tasks + Home — introduce `data-empty-kind`, surface-level filter-miss for Tasks,
  split Home's empty branch.
- **M3:** Conversations + Memories (legacy `MemoriesProduction`) — add the attribute to
  the existing copy split; fix non-ready fall-through; add `detail-not-found` on
  Conversations. Leave `MemoriesPlatformProduction` untouched.
- **M4:** raw-identifier sweep of all eight; Conversations folder option values are
  option values, not rendered text (see above).

## Kind vocabulary

Reuse the worked example's names where the condition matches:

- `empty-projection` — nothing exists in the loaded projection yet (true empty).
- `filtered-out` — something exists (or a filter is active on Home) and the client
  filter excluded everything.
- Platform-only extras stay platform-only: `recall-unknown`, `query-gap`.
- Conversations-only: `detail-not-found` for a missing detail id.
