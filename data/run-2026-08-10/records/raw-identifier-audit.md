# Raw-identifier audit — all 8 production surfaces (M4)

Measured 2026-08-10 on `lane/grok-polish` after M3 (`c17ad159bf`).
Bar: no raw storage identifiers on screen. Fix only what is user-visible.

## Method

Grep each `*Production.tsx` for `.id`, `folder:`, `opId`, digests, provenance,
and inspect every match: is it rendered text, an option/DOM value, a React key,
a `data-*` attribute, or a URL param?

## Per-surface findings

| Surface | Sites inspected | User-visible storage id? | Notes |
|---|---|---|---|
| MemoriesPlatformProduction | `data-proposition-id={item.id}`; lineage `<dd>{row.value}</dd>` (synthesisVersion / inputDigest / outputDigest); citation *count* only | **No** | Ids are DOM attrs only. Digests are intentional lineage display (not record storage ids); citation refs stay off-screen by design (`citationSummary`). |
| MemoriesProduction | `data-memory-id`; React keys; store ops by id; provenance/category labels; dead-letter keys | **No** | Provenance is a content prefix (`omi:`), not a record id. |
| TasksProduction | `data-task-id`; React keys; store ops; dead-letter keys | **No** | Existing test already bans rendering `task.source` / `task.provenance`. |
| ConversationsProduction | `folder:${folder.id}` filter option values; `<option value={folder.id}>{folder.name}</option>`; `data-conversation-id`; href `?conversation=`; dead-letter keys | **No** | See ruling below. |
| HomeProduction | React keys `memory:${id}` / `conversation:${id}`; href with conversation id | **No** | Keys and URL params are not on-screen text. |
| ChatProduction | no id render sites in sweep | **No** | |
| ListenProduction | no id render sites in sweep | **No** | |
| SettingsProduction | dead-letter keys; identity email | **No** | Email is account identity, not a storage record id. |

## Ruling: `ConversationsProduction.tsx` `folder:${folder.id}`

**Legitimate option value, not rendered text.**

- `ProductionFilterChips` renders `{option.label}` only (`ProductionPrimitives.tsx:93`).
  The `value` (`folder:${folder.id}`) is internal chip state.
- Detail `<select>` uses `value={folder.id}` with visible children `{folder.name}`.

No code change.

## Result

Checked all eight. **Zero user-visible storage-identifier defects.** The one
flagged site was an option value. No fix commit required beyond this record.
