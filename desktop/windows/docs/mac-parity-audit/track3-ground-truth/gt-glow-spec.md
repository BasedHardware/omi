# Implementation Spec: Focus Halo (Windows)

Researched 2026-07-14 after a first attempt shipped and looked wrong. The user's verbatim
complaints ARE the acceptance criteria:
- "the outline around the tabs are way too thick"
- "[the outlines] do not connect on the corners"
- "the whole screen outline only shows one long bar at the bottom a couple centimetres above the
  bottom of my screen. and its also very thick"

---

## 0. Root cause — NOT a DPI bug

`screen.screenToDipRect` was already in the failed code path. Fixing "DPI" fixes nothing.

**The bug is `GetWindowRect`'s invisible DWM border.** On Win10/11 `GetWindowRect` includes the
invisible resize border (~8px/side), and for a **maximized** window the frame deliberately hangs
off-screen. For a maximized window on 1920×1080 with a 40px taskbar, `GetWindowRect` ≈
`(-8,-8) → (1928,1040)`. Run that through the 4-band model (thickness 20, overlap 4):

| band | rect | visible? |
|---|---|---|
| top | y = −8−20 = **−28**, h 24 | **off-screen (above)** |
| left | x = −8−20 = **−28**, w 24 | **off-screen (left)** |
| right | x = 1920+8−4 = **1924** | **off-screen (right)** |
| bottom | y = 1040−4 = **1036**, h 24, full width | **visible — one long thick bar ~40px above the screen bottom** |

That is the user's report, derived from source. It is a **window-bounds semantics** bug.
`DWMWA_EXTENDED_FRAME_BOUNDS` is the fix and is the load-bearing change in this spec.

The other two complaints are structural consequences of the 4-window split:
- **"too thick"** — each band is `thickness + overlap = 24 DIP` of near-opaque gradient plus an
  8px blur. That is a 24px painted stripe: a border, not a glow.
- **"corners don't connect"** — by construction. Horizontal bands own the corners; vertical bands
  are inset and start below them. At each corner one band's mask fades downward while its
  neighbour's fades sideways, and the outer corner is a hard 90° edge. **Four axis-aligned
  rectangles with four mask axes cannot form a continuous rounded ring.** No tuning fixes it.

**Single-window is confirmed.** The 4-window trick is a macOS hit-testing workaround Windows does
not need: `setIgnoreMouseEvents(true)` makes the whole window click-through at the OS level.

---

## 1. Architecture — ONE persistent, parked, click-through window

Flags (mirror `bar/window.ts:178-207`, the proven local pattern):
```
frame: false, transparent: true, backgroundColor: '#00000000',
show: false, resizable: false, movable: false, skipTaskbar: true,
focusable: false, hasShadow: false,
webPreferences: { backgroundThrottling: false }
```
then `setAlwaysOnTop(true, 'screen-saver')` and `setIgnoreMouseEvents(true)` — **no
`{ forward: true }`** (the bar needs forwarding for interactive islands; the halo has none and
must not consume a single event).

**(a) NEVER `show()`/`hide()` this window.** Transparent frameless windows on Windows fade in via
the OS show-animation on every hide→show (electron#12130, #10069) — the same defect documented at
`bar/window.ts:96-131` as the pill "plummeting", which this repo has already paid for. **Reuse the
bar's park pattern verbatim:** create once, `showInactive()` once while parked at
`(-32000,-32000)`, and thereafter ONLY `setBounds()`. "Show" = setBounds(target); "hide" =
setBounds(parked). Include the paint-ack handshake (`bar:showAck` / `commitReveal`,
`bar/window.ts:374-428`): arm the renderer while parked, unpark on ack, ~150ms fail-open fallback.

**(b) DWM rounds OUR overlay window's corners** on Win11 and Electron can't opt out
(`roundedCorners` is macOS-only, electron#38834). If the halo's corners sit within ~8px of the
overlay window's corners, DWM clips them → "corners don't connect" a second time from a different
cause. **Fix with padding, no native call:** `WINDOW_PAD = 36` DIP vs a glow reach of ~20 DIP; the
~16px of transparent margin absorbs the clip. Do not touch `thickFrame`.

**(c) z-order** `'screen-saver'` puts the halo above the target — required, and harmless because
it's click-through.

**(d) Software rendering** is forced in dev (`dev/bench.ts:110-143`, SwiftShader). Constrains §3.

---

## 2. Coordinate spaces — exact sequence

- `GetWindowRect` → **physical px, INCLUDES the invisible DWM border.** Never the geometry source.
- `DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS=9, &RECT, 16)` → **physical px, the
  visually correct frame.** Documented gotcha: EFB is *not* DPI-adjusted — always raw physical,
  which is what we want (Electron is per-monitor-DPI-aware, so `GetWindowRect` is physical too;
  both are physical, only EFB is *correct*).
- `BrowserWindow.setBounds()` → **DIP.**
- `screen.screenToDipRect(null, rect)` → scales relative to the display nearest `rect`. Must be
  called on the **target rect, before any padding.**

```
1. hwnd = GetForegroundWindow()
2. validity gates (§6) — bail to "draw nothing" on ANY failure
3. physical = DwmGetWindowAttribute(hwnd, EXTENDED_FRAME_BOUNDS)   // fallback GetWindowRect
4. targetDip = screen.screenToDipRect(null, physical)              // physical -> DIP
5. isGlowableTarget(targetDip) else bail                           // MIN_TARGET_SIZE = 100
6. windowDip = inflate(targetDip, WINDOW_PAD)                      // pad AFTER conversion
7. verify windowDip intersects some display, else bail
8. win.setBounds(windowDip)
9. send renderer { mode, runId, pad, radius }
```
Steps 4→6 must not be swapped: `WINDOW_PAD` is a DIP quantity; padding a physical rect under-pads
at 150% and yields a visually thinner halo on scaled displays.

**Mixed-DPI multi-monitor:** a window straddling 100%/200% converts by one display's factor and is
a few DIP off on the far half. Electron exposes no better primitive; accept it.

**DELETE the `toDipRect(rect, scaleFactor)` fallback.** Dividing absolute screen coords by a scale
factor is only correct on a single monitor with origin at zero; on any real multi-monitor layout it
silently teleports the halo. If `screenToDipRect` throws, draw nothing.

### koffi additions to `nativeForeground.ts`
```
dwmapi.dll: int32 DwmGetWindowAttribute(void* hwnd, uint32 attr, _Out_ OMI_RECT* out, uint32 cb)
            // EXTENDED_FRAME_BOUNDS = 9, cb = 16, S_OK = 0; fills a RECT (l/t/r/b), not x/y/w/h
user32.dll: bool IsZoomed(hwnd)  bool IsIconic(hwnd)  bool IsWindowVisible(hwnd)
```
Export `getForegroundWindowFrame()` → `{ hwnd, rect /*EFB, physical*/, className, exePath,
maximized, minimized, visible }` sampled atomically in one `GetForegroundWindow()` call. Leave the
existing `getForegroundWindowRect()` alone (the bar's fullscreen suppression wants the raw rect).

---

## 3. Rendering — layered `box-shadow` on ONE rounded ring div

**An outer box-shadow is clipped to the region OUTSIDE the border-box** (CSS spec). So the interior
is guaranteed transparent — a perfect ring with a see-through center, no mask, no compositing
trick, and **continuous rounded corners by construction**. That is precisely what the 4-window
build could not do.

Rejected: SVG `feGaussianBlur` and `filter: blur()` (CPU Gaussian over a ~1900×1100 region under
SwiftShader — slow/jaggy; blur also bleeds inward, forcing a mask, which reintroduces the corner
seam that broke v1). `conic-gradient`+mask (a soft ring mask needs a blurred mask → same Gaussian
problem; a hard mask gives a border, not a glow). Canvas 2D (per-frame JS raster for what Skia does
declaratively).

**Animation rule: animate `opacity` ONLY.** Never animate `filter`, `box-shadow`, or a color
custom-property — each forces a full repaint of a screen-sized blurred shape every frame, which is
exactly what stutters on SwiftShader. Get the hue-shift by **cross-fading pre-rasterized hue
variants**: stack three ring divs (identical geometry, different shadow hues), each rasterized once,
with staggered opacity keyframes. For a gradient *across* the halo, give each layer a **static**
`mask-image: linear-gradient(...)` on a different diagonal (cheap — no filter, baked at raster).

```css
.halo-ring {
  position: absolute; inset: var(--pad);      /* 36px */
  border-radius: var(--radius);               /* 8px; 0 when maximized/snapped */
  background: transparent; will-change: opacity;
  box-shadow:
    inset 0 0 6px 0  rgba(var(--c), 0.26),    /* THE MAXIMIZED CODE PATH — see §6 */
    0 0 0 1px        rgba(var(--c), 0.40),    /* hairline; keeps it from reading as a smudge */
    0 0 5px 0        rgba(var(--c), 0.55),
    0 0 14px 2px     rgba(var(--c), 0.28),
    0 0 30px 7px     rgba(var(--c), 0.10);
}
.halo-ring.h1 { --c: 34 197 94;  mask-image: linear-gradient(135deg,#fff,#fff 40%,transparent); }
.halo-ring.h2 { --c: 74 222 128; mask-image: linear-gradient(135deg,transparent,#fff 60%,#fff); }
.halo-ring.h3 { --c: 16 185 129; }
.halo-ring.h2 { animation: halo-drift 2.4s ease-in-out infinite alternate; }
.halo-ring.h3 { animation: halo-drift 2.4s ease-in-out 1.2s infinite alternate; }
@keyframes halo-drift { from { opacity: 0 } to { opacity: 1 } }
.halo-run { position: fixed; inset: 0; animation: halo-envelope 3.5s linear both; }
```
(`--c` above is the FOCUSED/green set; the distracted set is the red equivalent.)
Keep `body { background: transparent; pointer-events: none }` and the `key={runId}` remount.

---

## 4. Numbers (all DIP/CSS px — scale automatically; keep every dimension out of physical space)

| param | value | why |
|---|---|---|
| `WINDOW_PAD` | **36** | Overlay inflation/side. Glow reach ~20; the extra ~16 absorbs DWM's rounding of our own window (§1b). |
| glow reach | **~20** | widest layer `spread + blur/2` = 7 + 15 = 22, alpha 0.10 → visually gone by ~20. |
| **perceived thickness** | **~5–6** | Where the bulk of the alpha lives. **This is the number the user judges.** v1's was **24**. |
| `--radius` | **8**, or **0** maximized/snapped | Win11 uses an 8px top-level radius, and corners are NOT rounded when snapped/maximized. Matching this makes the halo *hug* the window. |
| peak opacity | **0.85** | envelope max |
| `MIN_TARGET_SIZE` | 100 | keep |
| `GLOW_LIFETIME_MS` | 3500 | keep |
| **DELETE** | `GLOW_THICKNESS=20`, `GLOW_OVERLAP=4` | artifacts of the band model |

v1 = 20px outward + 4px inward of near-opaque gradient. v2 puts >90% of its alpha inside 6px and
tapers to nothing by 20px. Same outer extent, completely different read: **glow, not border.**

---

## 5. How real tools do it

One top-level `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` window
around the target, following it (Chrome/Teams/Loom/OBS capture indicators). `WS_EX_TRANSPARENT` is
what `setIgnoreMouseEvents(true)` sets; `WS_EX_NOACTIVATE` is what `focusable:false` sets. **We
already have the whole recipe — we just used four windows where they use one.** (Windows Graphics
Capture draws its yellow border in DWM itself, which is why it's not removable from OBS.)

**Following the window:** `setInterval` at **32ms** while the halo is up (≤3.5s → ~110 samples,
trivially cheap); re-read EFB and `setBounds` only when the DIP rect actually changed.

---

## 6. Failure modes — governing rule: **any failed gate ⇒ draw NOTHING**

Never show a partially-valid halo. The stray bar WAS a partially-valid halo.

| case | detect | do |
|---|---|---|
| no valid foreground window | null hwnd; className in shell denylist (`Progman`,`WorkerW`,`Shell_TrayWnd`,`Windows.UI.Core.CoreWindow`); `!IsWindowVisible` | **draw nothing** |
| EFB unavailable | HRESULT != S_OK | fall back to `GetWindowRect`; if that fails too, draw nothing |
| target too small | `!isGlowableTarget` | draw nothing |
| **rect off-screen/degenerate** | doesn't intersect any `screen.getAllDisplays()` bounds | **draw nothing — direct guard against the stray-bar class** |
| **maximized** | `IsZoomed` | EFB returns the true maximized bounds = work area, so an OUTWARD glow lands off-screen/under the taskbar and is invisible. → `radius: 0` and let the **`inset` shadow layer** carry it (it paints inside the window edge). **This is why the inset layer exists — it is the maximized code path, not decoration.** |
| snapped | EFB fills work area in one axis + touches a work-area edge | same as maximized |
| fullscreen (exclusive) | EFB == display bounds exactly | **draw nothing** — never paint over a fullscreen app/game |
| minimized mid-glow | `IsIconic`, or rect == (-32000,-32000) | dismiss (the 32ms tick catches it) |
| moved/resized mid-glow | follow tick sees changed DIP rect | `setBounds`; the CSS run keeps playing (ring is `inset: var(--pad)`, reflows with zero JS) |
| foreground switches app | existing `subscribeForegroundChange` + settle | dismiss (this logic in v1 was correct — keep) |

---

## 7. Concrete change list

- **Delete:** `glowEdgeRects`, `GlowEdge`, `GLOW_THICKNESS`, `GLOW_OVERLAP`, `toDipRect`, the
  four-window array, the `#/glow/<edge>` routes, the per-edge mask CSS.
- **`nativeForeground.ts`:** add the dwmapi/user32 bindings + `getForegroundWindowFrame()`.
- **`glowGeometry.ts`:** rewrite as `inflate`, `cornerRadiusFor({maximized,snapped})`,
  `intersectsAnyDisplay`, and the gate predicate. Keep it Electron-free.
  **`glowGeometry.test.ts` MUST include the regression case from §0** — the exact maximized rect
  (`x:-8, y:-8, w:1936, h:1048`) asserting **no window is shown**. That is the test that would have
  caught this bug.
- **`glowWindows.ts`:** one parked window + paint-ack handshake + 32ms follow tick.
- **`GlowWindow.tsx` / `glow.css`:** three-layer box-shadow ring; `--pad`/`--radius` from the
  `GlowPaint` payload.
- Public surface unchanged: `showGlow` / `dismissGlow` / `getCurrentGlow` / `glow:trigger` /
  `glowOverlayEnabled`.

**Sources:** MS Learn (DWMWINDOWATTRIBUTE, GetWindowRect, Geometry in Windows 11), Electron docs
(screen / custom window styles), electron#12130, #10069, #38834, #40515, gimp#1082.
