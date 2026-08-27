# conversations

Destination `/conversations`: day-grouped gallery of conversations and recaps.

- `api.ts` — HTTP (list, merge, folders, people, audio, daily summaries)
- `model.ts` — timeline grouping, panel sizing, selection from `?id=`/`?recap=`
- `ui/` — split view, detail panel (summary/actions tabs), gallery
- `recaps/` — recap detail; a recap leads its day, it is not a separate rail
- hooks — people, list, recaps, detail, and search are moonshine signal stores

Public entry: `index.ts`.
