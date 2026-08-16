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

## Test it locally

One command from this repo root:

```bash
bun run app
```

That reuses `integration/dev-stack.sh --up` when 4851/8788 are already serving, otherwise boots them with `OMI_SEED_PERSONA=demo` and `OMI_STT_ENGINE=mlx-whisper`, then launches the headed macOS shell (`frontend/shells/macos/scripts/dev-run-macos.sh`, route conversations / Activity, origin `http://127.0.0.1:5290`).

Expect **Demo User** (empty email) and a fictional recent week: Harborline Cafe / Cedar Loop / Fable and Wick people and places, conversations with transcripts in a few folders, tasks (some linked to those conversations), and a short chat history. Chat generation goes through the **local test gateway** on 8788, not a real model.

Persona off (default): omit `OMI_SEED_PERSONA` and every seeded byte stays the historical QA fixture. Persona on: `OMI_SEED_PERSONA=demo`. Stop the stack with `integration/dev-stack.sh --stop`. Headless-safe check: `integration/dev-app.sh --accept`.
