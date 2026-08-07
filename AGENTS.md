# platform — backend rewrite code

The canonical repo for omi's backend rewrite (TypeScript memory system).
Decisions are NOT made here — they live in the sibling
`omi-as-a-platform-project-tracker` (specs' adjudication YAML, ADR-001..005,
deprecations). Read `docs/implementation-charter.md` there before building.

## Ground rules

- **Never invent domain names.** 58 naming decisions are open in
  `omi-domain-language-tracker`. Use the legacy name and mark every such site
  `// domain-pending(<ITEM-ID>)` (e.g. `// domain-pending(DIV-DOMCORE-008)`)
  so the ratified concept map can rename mechanically. No marker, no merge.
- **Spec items with `status: open` or `decision: null` = stop and ask.**
  `change` decisions: read `decision_detail` + notes; only `remove:` authorizes
  deletion (and owes a DEP record).
- Data-destructive operations, user-data disposition, new authority classes:
  David decides, always.
- Output-preserving refactors only while an evaluation run is live (check with
  the coordinator before touching `drivers/sqlite/dream.ts` hot paths).

## Working here

- `bun install && bun test` — 265 tests, keep green. Import-graph lint runs in
  the test suite.
- `core/` contracts and orderings; `drivers/` storage + model adapters;
  `harness/` pipeline runners. `NOTES.md` has the architecture narrative.
- No benchmark data lives in this repo and none may be added — evaluation
  corpora are machine-local under the workspace `data/` dir (gitignored).
- Sync discipline: `make sync` at start, `make up` when done (workspace root).
