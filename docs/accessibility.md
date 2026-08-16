# Accessibility measurements

This is a measurement of the production surfaces in this worktree against
published thresholds. It is not a redesign. Font sizes David already ruled
on (shortcut hint 9px and keycap 8px, 2026-08-17) are recorded as settled
and are not findings.

## Standards cited

| Threshold | Number | Source |
| --- | --- | --- |
| Body / UI text contrast | 4.5:1 | [WCAG 2.2 SC 1.4.3 Contrast (Minimum)](https://www.w3.org/TR/WCAG22/#contrast-minimum) |
| Large text contrast | 3:1 at ≥18.66px bold or ≥24px | same |
| Non-text UI / focus / component boundary | 3:1 | [WCAG 2.2 SC 1.4.11 Non-text Contrast](https://www.w3.org/TR/WCAG22/#non-text-contrast) |
| Focus visible | every keyboard-operable control | [WCAG 2.2 SC 2.4.7 Focus Visible](https://www.w3.org/TR/WCAG22/#focus-visible) |
| Keyboard | operable without a pointer; order follows reading order | [WCAG 2.2 SC 2.1.1 Keyboard](https://www.w3.org/TR/WCAG22/#keyboard), [SC 2.4.3 Focus Order](https://www.w3.org/TR/WCAG22/#focus-order) |
| Hit target | 44×44 CSS px | Apple HIG minimum; [WCAG 2.2 SC 2.5.5 Target Size (Enhanced)](https://www.w3.org/TR/WCAG22/#target-size-enhanced) (AAA). WCAG 2.2 AA SC 2.5.8 is 24×24; this lane used the 44px number the brief named, which already exists as `--min-tap-target`. |
| Text size floor (report only) | 11 CSS px | Apple HIG “at least 11 points”. WCAG 2.2 has no minimum font size (SC 1.4.4 is resize). |

Large-text 3:1 was not used as a relaxation: production body is 13–15px, so every text pair was scored at 4.5:1.

## Method

**Token contrast.** Relative luminance per WCAG 2.2 definition of relative
luminance; ratio `(L1 + 0.05) / (L2 + 0.05)`. Hex and `rgba()` tokens from
`frontend/packages/tokens/src/index.ts`. Translucent `raised` / `elevated`
and translucent content colours were composited **over that theme’s
`surface.canvas`**, then the ratio was taken against that composited panel.
That is the honest number for an opaque or known-canvas host. It is **not**
the number for HUD glass over a wallpaper.

**Glass / native material.** `desktopLightGlass` and `desktopDarkGlass` set
`glass.material: hudWindow` and production CSS applies `backdrop-filter`
over a multi-stop decorative gradient (web) or AppKit HUD (native,
`data-native-glass="true"`). The effective background is then a function of
the pixel behind the panel. Those pairs are **COULD NOT DETERMINE**. The
token-over-canvas figures below are the semantic fallback the web host
paints when it is not blurring a variable backdrop; they must not be quoted
as a native-glass result.

**Focus.** `frontend/scripts/probe-accessibility-focus.mjs` launches
headless Chrome (`--force-color-profile=srgb`), inlines production
`styles.css` into a `.production-shell` containing a native `button` and a
`details > summary`, then `element.focus({ focusVisible: true })` and
`getComputedStyle`. That is the layer a keyboard user sees. The probe is
not a `pnpm verify` gate — Chrome is not part of L1.

**Names.** Static scan of `packages/surfaces/src/production/**/*.tsx`: an
icon-only `button`/`a` whose only glyph is `ProductionIcon` / `ChromeIcon`
(`aria-hidden`) must have `aria-label` / `aria-labelledby` or other text.

**Hit targets.** CSS inventory of `min-height` / `min-width` on interactive
selectors versus `--min-tap-target` (44). Not a headed pixel census of every
route.

**Keyboard.** Source review of production click handlers: native
`button`/`a`/`input`/`select`/`textarea`/`summary`, plus the few
`tabIndex={0}` regions that already handle keys.

`src/dev/**` and `src/lab/**` were not measured.

A sibling lane is converting hardcoded desktop font sizes to tokens under a
zero-visual-change mandate. This lane did not change those values. Re-verify
sizes against the token file after that lane lands.

## Token text and focus (gated)

All four ratified themes. Composited over `surface.canvas` as described.
**PASS** means ≥4.5:1 for text, ≥3:1 for `focus`.

### mobileDark (opaque)

| Pair | canvas | raised | elevated |
| --- | ---: | ---: | ---: |
| content.primary | 21.00 | 16.39 | 12.31 |
| content.secondary | 13.08 | 10.87 | 8.52 |
| content.tertiary | 7.37 | 6.70 | 5.55 |
| accent as text | 9.38 | 7.32 | 5.50 |
| danger as text | 7.97 | 6.22 | 4.67 |
| success as text | 10.98 | 8.57 | 6.44 |
| warning as text | 9.78 | 7.63 | 5.73 |
| focus (non-text) | 9.38 | 7.32 | 5.50 |

Closest text pair: `danger` on `elevated` at **4.67:1**.

### mobileLight (opaque)

| Pair | canvas | raised | elevated |
| --- | ---: | ---: | ---: |
| content.primary | 17.48 | 18.72 | 15.89 |
| content.secondary | 7.82 | 8.10 | 7.42 |
| content.tertiary | 4.79 | 4.89 | 4.63 |
| accent as text | 5.59 | 5.98 | 5.08 |
| danger as text | 6.14 | 6.57 | 5.58 |
| success as text | 6.25 | 6.69 | 5.68 |
| warning as text | 6.80 | 7.28 | 6.18 |
| focus (non-text) | 5.59 | 5.98 | 5.08 |

Closest text pair: `content.tertiary` on `elevated` at **4.63:1**.

### desktopLightGlass — token over canvas only

Web-host semantic fallback. Native HUD / `backdrop-filter` over the
decorative gradient: **COULD NOT DETERMINE**.

| Pair | canvas | raised (composited) | elevated (composited) |
| --- | ---: | ---: | ---: |
| content.primary | 14.77 | 16.13 | 16.35 |
| content.secondary | 8.06 | 8.52 | 8.60 |
| content.tertiary | 5.43 | 5.65 | 5.68 |
| accent as text | 5.33 | 5.82 | 5.90 |
| danger as text | 5.86 | 6.40 | 6.49 |
| success as text | 5.97 | 6.51 | 6.60 |
| warning as text | 6.49 | 7.09 | 7.18 |
| focus (non-text) | 5.33 | 5.82 | 5.90 |

### desktopDarkGlass — token over canvas only

Same caveat as light glass. Dark-mode CSS still leaves `backdrop-filter` on
the panel, so the composited-over-canvas column is not the HUD result.

| Pair | canvas | raised (composited) | elevated (composited) |
| --- | ---: | ---: | ---: |
| content.primary | 17.96 | 15.46 | 12.38 |
| content.secondary | 11.03 | 9.84 | 8.19 |
| content.tertiary | 6.48 | 6.05 | 5.28 |
| accent as text | 8.52 | 7.33 | 5.87 |
| danger as text | 7.24 | 6.23 | 4.99 |
| success as text | 9.97 | 8.58 | 6.87 |
| warning as text | 9.28 | 7.99 | 6.40 |
| focus (non-text) | 8.52 | 7.33 | 5.87 |

`--content-soft` (`color-mix` 62% of primary) is declared in `styles.css`
and is unused as `color`. Not measured as text.

## Ungated boundary contrast (report only)

WCAG 2.2 SC 1.4.11 needs **3:1**. `--border` is the token; desktop also
uses `--control-border` (9% mix of primary) and `--glass-border` (11%).
None of these are gated.

| Theme / surface | `--border` | `--control-border` | `--glass-border` |
| --- | ---: | ---: | ---: |
| mobileDark canvas / raised / elevated | 1.27 / 1.45 / 1.46 | 1.17 / 1.31 / 1.32 | 1.23 / 1.40 / 1.41 |
| mobileLight canvas / raised / elevated | 1.29 / 1.29 / 1.28 | 1.20 / 1.21 / 1.20 | 1.26 / 1.26 / 1.25 |
| desktopLightGlass (token over canvas) | 1.12 / 1.12 / 1.12 | 1.19 / 1.19 / 1.19 | 1.24 / 1.24 / 1.24 |
| desktopDarkGlass (token over canvas) | 1.33 / 1.40 / 1.41 | 1.24 / 1.30 / 1.31 | 1.31 / 1.38 / 1.40 |

Glass-over-wallpaper for these hairlines is **COULD NOT DETERMINE**.

## What this lane fixed

### Chat agent-run `summary` ignored the focus token

`ChatProduction` renders a native `<summary>` inside `.production-shell`
(`chat-agent-run`). The shared focus contract listed `input, textarea,
select, button, a, [tabindex], [role=…]` and omitted `summary`. Chrome
therefore painted the UA ring (`outline-style: auto`, `outline-width: 1px`)
instead of `--focus` / `--focus-ring-width`.

That is an objective bug: the token already exists; the control ignored it.
`summary` was added to both the `:where()` contract and the `!important`
override in `frontend/packages/surfaces/src/production/styles.css`. No
palette or layout change.

Rendered-layer red-proof, `probe-accessibility-focus.mjs`, headless Chrome,
`focus({ focusVisible: true })`, `--focus` forced to `#FF00FF` so a
coincidental UA blue cannot pass. `button` stayed on the token in both
directions; only `summary` moved.

**Before** (`--without-summary`; token `#FF00FF`; summary still the UA
ring, 1px auto). Exit 0 on this mutation is the red:

```
"summary": {
  "outline": "rgb(153, 200, 255) auto 1px",
  "outlineColor": "rgb(153, 200, 255)",
  "outlineStyle": "auto",
  "outlineWidth": "1px",
  "matchesFocusVisible": true
}
```

**After** (current `styles.css`; same probe, same token). Exit 0:

```
"summary": {
  "outline": "rgb(255, 0, 255) solid 2px",
  "outlineColor": "rgb(255, 0, 255)",
  "outlineStyle": "solid",
  "outlineWidth": "2px",
  "matchesFocusVisible": true
}
```

Production tokens after the fix, same probe: light `#005FCC` →
`rgb(0, 95, 204) solid 2px` on both `button` and `summary`; dark
`#66B2FF` → `rgb(102, 178, 255) solid 2px` on both. The focus contract is
not platform-gated; `html[data-platform]` / `html[data-color-mode]` do not
override `summary` outline.

The consumer of the CSS is the agent-run `<summary>` in `ChatProduction`.
`chat-live-rendering.test.mjs` asserts that node is present inside
`.production-shell`. jsdom cannot compute `:focus-visible`; the ring is
the Chrome probe above. The Vite production bundle this run wrote
(`packages/surfaces/dist/assets/index-BUU12kYC.css`) contains
`:where(...,summary,...)` and
`.production-shell summary:focus-visible{outline:var(--focus-ring-width) solid var(--focus)!important}`.

## Gates (objective half only)

Added next to the existing `frontend/scripts/check-*.mjs` family and wired
into `frontend/package.json` `verify` (L1). None of these fail a reported
threshold.

| Check | What it fails on | What it does not fail on |
| --- | --- | --- |
| `check-accessibility-contrast.mjs` | Token text &lt; 4.5:1 or focus &lt; 3:1, all four themes, composited over canvas | `--border`, `--control-border`, `--glass-border`, glass-over-wallpaper, new palette values |
| `check-accessibility-focus.mjs` | Production focus contract missing a listed control (including `summary`) or not using `var(--focus)` | Hit targets, font size, computed rings (see `probe-accessibility-focus.mjs`) |
| `check-accessibility-names.mjs` | Icon-only production `button`/`a` with no accessible name | Decorative icons inside named controls |

Each check runs three self-test fixtures both directions before it looks at
production. Verbatim finder output, this run:

Focus self-test dropping `summary` from `:where()` only:

```
[":where() omits summary"]
```

Focus self-test with a literal outline colour instead of `var(--focus)`:

```
[":where() focus-visible outline does not use --focus / --focus-ring-width","summary:focus-visible override does not force var(--focus) with !important"]
```

The production-bug mutation (summary removed from `:where()` *and* the
`!important` override — what `--without-summary` does):

```
[":where() omits summary","missing .production-shell summary:focus-visible override","summary:focus-visible override does not force var(--focus) with !important"]
```

**Green** (current `styles.css`): `[]`, then

```
accessibility focus fence passed (packages/surfaces/src/production/styles.css; 11 controls; 3 self-test fixtures green).
accessibility contrast fence passed (WCAG 2.2 AA token pairs; 4 themes; 96 measurements; 3 self-test fixtures green).
accessibility names fence passed (packages/surfaces/src/production/**/*.tsx; 3 self-test fixtures green).
```

Names finder: icon-only button without `aria-label` → one hit
(`<button type="button"><ProductionIcon name="plus" /></button>`); with
`aria-label` → `[]`. Contrast finder: white-on-white → 24 failures;
black-on-white with `#005FCC` focus → 0.

## Hit targets (not gated)

`--min-tap-target` is 44px on every theme
(`frontend/packages/tokens/src/index.ts` `sharedInteraction`). Global
production CSS sets `button, select { min-height: var(--min-tap-target) }`.
Icon buttons, nav utilities, search fields, FABs, conversation star, chat
attach/send, listen primary, folder rows, and home result rows claim that
token or `rowMinHeight` (48 desktop / 52 mobile).

Places that **mention** `--min-tap-target` and then shrink it are not
interactive hit targets:

- `tasks.css` mobile `.tasks-group-heading`: `calc(var(--min-tap-target) - var(--space-xs))` → **40px**. Heading, not a control.
- `screen.css` `.screen-app-badge` / `.screen-timestamp-pill`: `calc(var(--min-tap-target) * 0.7)` → **30.8px**. `<span>`, not a control.

`input[type=range]` on Rewind is full-width; the UA thumb size was **COULD
NOT DETERMINE** from CSS (no explicit thumb width). If the thumb is below
44×44, fixing it is a layout change — a ruling, not a silent restyle.

No interactive production rule was found that sets a control’s
`min-height` below 44 while still claiming the token. This was a CSS
inventory, not a headed bounding-box census of every fixture.

## Keyboard (not gated)

Clickable production controls are native `button`, `a`, `input`, `select`,
`textarea`, or `summary`, plus:

- Task cards: `<article tabIndex={0}>` with Enter/Space and
  `:focus-visible` in `tasks.css`.
- Listen transcript / chat message list: `tabIndex={0}` scroll regions with
  arrow/page keys.

The command palette traps Tab, has a Close button, and registers Escape in
the command registry. Backdrop click-to-dismiss is pointer-only; keyboard
users are not stuck.

No production control the surfaces tests click was found to be
pointer-only. Focus order follows DOM / reading order on the routes
reviewed. Not a headed Tab walk of every fixture.

## Accessible names (gated)

Icon-only production controls already expose names (`aria-label` on add /
more / clear / star / nav utilities / FAB / attach, visible text on
labelled nav). The new names fence holds that.

`ProductionIcon` is `aria-hidden`. That is correct only while the parent is
named.

## Font sizes (not gated; 8px / 9px settled)

| Role | mobile | desktop | vs 11px HIG floor |
| --- | ---: | ---: | --- |
| display / title / heading / body / row / button | 34–15 | 28–13 | above |
| code | 13 | 12 | above |
| label / meta | 12 | **11** | at floor (desktop) |
| search / glyph / accessory | 21 / 18 / 17 | same | above |
| micro | **10** | **10** | below |
| hint | **9** | **9** | settled 2026-08-17, do not raise |
| kbd | **8** | **8** | settled 2026-08-17, do not raise |

`tasks.css` desktop shortcuts use `var(--type-hint-size)` and
`var(--type-kbd-size)` (the former 9px / 8px hardcodes). Left untouched.

## What needs David’s ruling

Ranked by who is affected and how badly, not by how easy it is. Numbers
attached. Do not treat these as a patch list.

1. **`--border` fails WCAG 1.4.11 on every theme, every surface.** Measured
   1.12:1 (desktopLightGlass, all three surfaces) through 1.46:1
   (mobileDark elevated). Need is **3:1**. Desktop also paints
   `--control-border` (`color-mix` 9% of primary) and `--glass-border`
   (11%) as field and panel edges; those measure 1.17–1.41:1. This is
   every hairline around fields, cards, and chips. Low-vision users lose
   component boundaries. Fixing it needs a **new colour** (or a heavier
   hairline that is still a design choice). Not a wrong-token swap.

2. **Glass / native HUD contrast is unverified.** Anyone on
   `desktopLightGlass` / `desktopDarkGlass` with translucency over a
   wallpaper or the decorative web gradient. Token-over-canvas (tables
   above) is not that picture. Ruling: either accept COULD NOT DETERMINE,
   or specify a compositing backdrop to measure against.

3. **`micro` is 10px** on all four themes (overflow / settings trigger).
   Below the 11px HIG floor. Affects a small chrome control, constantly
   visible on desktop memories/tasks headers. Changing it is a visual
   change. Hint 9 / kbd 8 are already settled — do not re-open those.

4. **Desktop `label` / `meta` sit on the 11px floor** (weight 500 / 400).
   Not below. Report only so a later type-scale pass does not drop them.

5. **Rewind range thumb** may be below 44×44 (COULD NOT DETERMINE from
   CSS). Affects anyone targeting the playhead without a keyboard. A 44px
   thumb is a layout change.

6. **Task card is an `<article tabIndex={0}>` without a widget role.**
   Keyboard works (Enter/Space). Screen-reader name/role/value is the
   contents, not a named button, and the card contains real buttons
   (check, edit, delete). Promoting it to `role="button"` would nest
   interactive elements. Needs a structure ruling, not a quiet ARIA patch.

7. **`content.tertiary` on mobileLight elevated is 4.63:1** — above 4.5,
   but the margin is 0.13. Metadata, placeholders, completed-task copy.
   A later palette tweak can drop it under AA without a layout change.
   Not a fail today.

Items 1–2 affect the most people and the most surfaces. Item 3 is smaller
chrome. Items 5–6 are one control each. Item 7 is a watch, not a fail.

## Verification this run

Commands from this worktree. `OMI_CORE_ROOT` / `OMI_PLATFORM_ROOT` unset,
so provenance used the git toplevel of this checkout.

| Gate | Result | Ref |
| --- | --- | --- |
| `bun test` | 2356 pass, 0 fail, 36 skip | bun test v1.3.14, 2392 tests / 349 files |
| `bun run lint:imports` | pass | `scripts/lint-import-graph.ts` |
| `bun run lint:closure` | pass | `scripts/lint-import-closure.ts` |
| `(cd frontend && pnpm -r build)` | pass | surfaces Vite bundle includes the summary focus contract |
| L1 `node integration/lanes.mjs L1` | PASS | receipt `L1-7c969225d6258f36` |
| L2 `node integration/lanes.mjs L2` | PASS after `pnpm -r build` (stamp had gone stale from later `frontend/` edits) | receipt `L2-1d44658e3d40ebaf` |
| L3 `node integration/lanes.mjs L3` | FAIL | iOS evidence launch exit 124 (probe wait). Not this lane's CSS. See below. |

L3 failed at `integration/dev-stack.sh --assert --lease` on iOS evidence,
exit 124, which `dev-run-ios.sh` returns when the 180s probe wait expires.
The script only reaches the iOS launcher after macOS evidence returns 0.
This is not a focus-ring regression: the same 124 happened on this
worktree before these files were committed, across simulator UDIDs and
TMPDIR. Variations this lane actually ran:

1. Default TMPDIR, iPhone 17e (`BA88B402-…`), ports 14852/18789/15290
2. Booted sim + `TMPDIR=/tmp/omi-l3-a11y-retry1`, iPhone 17 Pro Max (`D6B5BB2B-…`)
3. Later idle retry, same Pro Max, default TMPDIR, ports 14852/18789/15291
4. This agent: killed leftover gateway on 18789, `TMPDIR=/tmp/omi-l3-a11y-lane`, Pro Max, ports 14851/18788/15290

All four printed `ERROR: iOS evidence launch failed (124)`. Concurrent
dev-stack processes from other worktrees and two already-booted simulators
were present. L3 is therefore **not claimed**. Coordinator: re-verify L3
when the machine is not sharing simulators.
