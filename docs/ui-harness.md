# UI state harness

This is the agent entry point for iterating the macOS app UI across every
fixture state the surface lab can render. Do not read `src/lab/main.tsx` to
discover states — generate the manifest.

All commands below are from the **platform repo root**. Captures are written
under `frontend/packages/surfaces/.build/ui-harness/` (gitignored). Never
commit PNGs.

The lab stays backend-free. These commands do not call a service and do not
need credentials.

## List every state

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs manifest
```

Writes `frontend/packages/surfaces/.build/ui-harness/manifest.json`.

Each `states[]` entry has:

- `id` — stable, filesystem-safe (`{surface}.{state}.{platform}.{locale}.{raw|polish}`)
- `url` / `path` — the exact query that renders that state
- `surface`, `state`, `platform`, `locale`, `polish`
- `viewport` — `390×844` mobile, `1280×800` desktop
- `shell.reachable` — whether the macOS shell can capture this state as itself

Override the output path with `--out /absolute/or/relative.json`.

## Capture one state

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs capture --id memories.normal.desktop.en-US.raw
```

Headless Chrome, no backend. Writes `<id>.png` and `summary.json` into a new
run directory under `.build/ui-harness/`.

`summary.json` records `id`, `url`, `bytes`, `viewport`, `renderMs`, and any
`consoleErrors` seen while rendering. A state that logs an error is still
captured; it is reported, not silenced.

## Capture all states

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs capture
```

Renders the full generated matrix. Bound: one Chrome, sequential navigations,
fonts awaited, animations disabled. Measured: **260 states, 60160 ms**
(`~60s`) with 0 console errors. Use `--out DIR` to choose the run
directory, `--limit N` while debugging.

## Capture through the macOS shell

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs capture --shell
```

Requires a built surfaces dist:

```bash
pnpm --filter @omi-core/surfaces build
```

Then launches the existing macOS shell (does not edit it) with
`OMI_SURFACE_QUERY` set to each desktop fixture URL and
`WKWebView.takeSnapshot` via `OMI_SNAPSHOT_PATH`.

### States the shell cannot reach as themselves

| States | Why |
| --- | --- |
| Every `*.mobile.*` id | GlassHost fixture windows have a 760px minimum width. `390×844` mobile chrome is browser-only. `platform=mobile` CSS inside a desktop-sized native window is not the polish target. |
| `?lab=1` picker chrome | Not a fixture state. The harness captures the fixture URLs the lab opens (`?qa=…`), not the lab index. |

Desktop raw and polish fixture ids, including `conversation-detail`, are
reachable. The shell always appends `nativeGlass=1`; browser captures do not.
Compare shell runs to shell runs.

Loopback **5290 is an origin**, not a preference. Shell capture refuses to start
if another process already holds that port. It never kills a sibling shell.

One state:

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs capture --shell --id settings.ready.desktop.en-US.polish
```

## Diff two runs

```bash
node frontend/packages/surfaces/scripts/ui-harness.mjs diff \
  --before frontend/packages/surfaces/.build/ui-harness/browser-<stamp-a> \
  --after  frontend/packages/surfaces/.build/ui-harness/browser-<stamp-b>
```

Method: **per-pixel RGBA with channel tolerance 8**. A pixel counts as changed
when any RGBA channel differs by more than 8. That absorbs Chrome's 7–62
pixel compositor jitter without hiding a token or layout edit. Each changed
id gets a side-by-side PNG (`before | magenta gap | after`) and a `diff.json`
listing `changedPixels`, `totalPixels`, and `delta` (changed / total).

There are no baseline images in the repo. Capture, edit, recapture, diff.

## Add a new state

1. Append the state name to the fixture array the lab already imports
   (`FIXTURE_STATES`, `CONVERSATION_FIXTURE_STATES`, `CHAT_FIXTURE_STATES`,
   `POLISH_EVIDENCE_STATES.<domain>`, …).
2. Implement the fixture factory case for that name.
3. If it is a **new surface**, add a row to `SURFACES` / `MATRIX_SURFACES` in
   `frontend/packages/surfaces/src/lab/catalog.ts` (the lab UI reads the same
   catalog).
4. Re-run `manifest`. The new id must appear; `ui-harness.test.mjs` fails if a
   quoted fixture state is missing.

Do not hand-edit the manifest.

## Iterate one visual change

```bash
pnpm --filter @omi-core/surfaces build
node frontend/packages/surfaces/scripts/ui-harness.mjs capture --out frontend/packages/surfaces/.build/ui-harness/before
# edit the surface CSS or component
pnpm --filter @omi-core/surfaces build
node frontend/packages/surfaces/scripts/ui-harness.mjs capture --out frontend/packages/surfaces/.build/ui-harness/after
node frontend/packages/surfaces/scripts/ui-harness.mjs diff \
  --before frontend/packages/surfaces/.build/ui-harness/before \
  --after frontend/packages/surfaces/.build/ui-harness/after
```

Package scripts (from `frontend/packages/surfaces`): `pnpm harness manifest`,
`pnpm harness capture`, `pnpm harness:capture -- --id …`, `pnpm harness diff`.

Browser capture serves the **built** `dist/` (`vite preview`). Rebuild after
an edit before recapturing:

```bash
pnpm --filter @omi-core/surfaces build
```
