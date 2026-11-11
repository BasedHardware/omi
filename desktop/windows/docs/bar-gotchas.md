# Bar window & motion gotchas (read BEFORE touching bar animations)

The floating bar is a transparent, frameless, always-on-top, **non-focusable** Electron
window. That combination has several Windows-specific pathologies that cost days to
diagnose (July 2026). Every one of them is invisible to the "obvious" instruments —
DOM inspection, DevTools animation panels, synthetic-input tests — so read this first.

## The four traps

### 1. The OS fades in every hidden→shown transparent window (fix: never hide it)

Windows plays a ~300ms alpha fade on the **window surface** every time a transparent
frameless HWND goes hidden→shown. It is DOM-independent (plays even with all DOM
opacity forced to 1), and cannot be disabled — `DWMWA_TRANSITIONS_FORCEDISABLED`
no-ops, and turning off OS animations breaks transparent windows entirely
(electron/electron#45730). Any renderer-side entrance animation you write plays *on
top of* this fade and looks broken.

**Standing fix (do not undo):** the bar is a **persistent window** — shown once at
startup parked off-screen at (-32000,-32000), then only ever moved via `setBounds`
park/unpark, never `hide()`/`show()`. Logical visibility is the `barOnScreen` flag in
`src/main/bar/window.ts` (`win.isVisible()` is always true after priming and must not
be used as truth). If you add any code path that calls `hide()`/`show()`/
`showInactive()` on the bar window, you have reintroduced the fade.

### 2. Content pinned to a resizing box rides the resize (fix: clip-reveal)

The expand/collapse animations resize the bar's surface box by hundreds of px. Any
content **bottom-pinned** to the moving edge visibly slides with it (the "plummet").
An opacity-hold (keep content invisible until the box seats, then fade in) is NOT a
fix — the hold *is* a black flash.

**Standing pattern:** **clip-reveal.** Entering content renders at its FINAL seated
layout, fully opaque, from the first frame, top-anchored in window space; the growing
`overflow: clip` surface reveals it downward. Collapse is the mirror: the shrinking
box conceals stationary content. No opacity/scale animation on entering conversation
content. Encoded in `BarChatSurface.test.tsx` ("no enter-animation class",
"overflow:clip") — if those tests fight you, you're re-adding the plummet.

Repro needs a TALL thread — fake-auth threads are short, so the box delta is tiny and
the bug hides. `scripts/repro-listconvo.mjs` injects a tall thread via `chat:state`.

### 3. Mounting or resizing an `<Orb>` blinks the logo (fix: one hoisted orb)

Each `<Orb>` mount initializes a WebGL canvas (visible re-init flash), and changing an
existing orb's size/preset props rebuilds its animator through a retry — also a blink.

**Standing pattern:** exactly ONE `<Orb>` in the bar, hoisted above all fading layers
in `BarApp.tsx`, moved between its pill seat and panel-header seat by a
**transform-only FLIP** (translate + scale on the wrapper). The old inline mount
points are spacers. Encoded in `bar.orb.test.ts` (exactly one Orb; wrapper transitions
transform only).

### 4. Hardware clicks are eaten; synthetic clicks are not (verification blind spot)

On this transparent non-focusable window, real trackpad/mouse clicks can be swallowed
(DComp alpha hit-testing / `MA_NOACTIVATEANDEAT`) while **SendInput/CDP-injected clicks
work fine** — so click tests pass while the user's physical clicks do nothing.

**Standing fix:** main-process click detection — a 16ms `GetAsyncKeyState(VK_LBUTTON)`
edge watch (`src/main/bar/keyState.ts` + the clickWatch in `window.ts`, pure logic in
`watchdog.ts`). Never verify bar click behavior with injected clicks alone; the only
trustworthy click test is a physical one (or the GetAsyncKeyState path itself).

## Working on bar motion — the fast loop

- **electron-vite dev does NOT restart the main process** on `src/main` edits, and
  renderer HMR is unreliable for animation judging. Always restart the app and pin the
  commit before judging any motion change.
- `[bar-diag]` (dev-only, `src/main/bar/window.ts`) logs every transition:
  prime/park/unpark, reveal/hide, watch state. Read it before theorizing.
- Drive the bar without touching the user's cursor: keyboard-only synthetic input
  (Shift+Space tap = summon) + DOM `.click()` via CDP covers the whole flow.
- Committed harnesses: `scripts/realflow-bar.mjs` (live CDP flow driver + per-frame
  rect/opacity sampling), `scripts/capture-bar-expand.mjs` (filmstrips),
  `scripts/repro-listconvo.mjs` (tall-thread plummet repro). Renderer-space probes
  can never see window-surface effects (trap 1) — for those, capture real frames of
  the desktop (GDI window capture) with DOM opacity pinned to 1.
- Regression suites that pin the mechanisms: `src/main/bar/watchdog.test.ts`,
  `bar.orb.test.ts`, `BarChatSurface.test.tsx`, `barDisplay.test.ts`, `e2e/bar.spec.mjs`.

## Shell panels: `display:none` makes ResizeObserver read 0 (not bar-specific)

Not a bar trap, but the same "hidden→shown paints wrong for a frame" family, so it
lives here. `MainViews` keeps every page mounted and hides the inactive ones with a
`hidden` class (`display:none`, see `panelClass`). A `display:none` ancestor makes a
`ResizeObserver` fire a 0×0 rect and `offsetHeight`/`clientWidth` read 0. If a size
cache stores that 0, the next time the page is shown React paints with the stale 0 and
then snaps to the real size a frame later — the intermittent home-card / Rewind-timeline
glitch on nav return.

**Standing fix:** never write a non-positive measurement into a cached size. Route every
ResizeObserver/`offsetHeight`/`clientWidth` cache through `keepLastPositive(prev, measured)`
(`src/renderer/src/lib/measure.ts`) so a re-shown panel renders at its last real size up
front. Callers keep their own pre-measure fallback (e.g. `useElementWidth(ref) || 600`)
for the genuine first-paint-before-layout window. Pinned by `lib/measure.test.ts`; live
by navigating Home → another tab → back and confirming the widget row does not snap from
48px.
