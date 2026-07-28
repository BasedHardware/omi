# Context for Claude — design system

Lifted from omi-v4's onboarding, translated to SwiftUI/AppKit. Values are exact; do not round them.

## Colour

```
cream           #FFFCEC   text, buttons, chips
ink             #171716   button label on cream, window root layer
listening green #2E8B57
cursor blue     #96C4FF
error           #FFB4AB
```

Cream alpha ladder — used constantly, so name them:

| alpha | use |
|---|---|
| 0.08 | idle keycap / glass warm tint |
| 0.35 | borders, hairlines |
| 0.50 | dimmed secondary text |
| 0.55 | secondary button outline |
| 0.70 | hint and prompt text |

White alpha, permission rows only: `0.05` surface, `0.45` checkbox border + status label,
`0.82` row copy.

Backdrop blobs — nine radial gradients placed just outside the frame, in this order:

| unit position (x, y) | hex |
|---|---|
| −1.25, −1.20 | `#A85E46` |
| −0.25, −1.25 | `#C78067` |
|  0.35, −1.25 | `#D4AE87` |
|  1.20, −1.05 | `#4E687C` |
|  1.25,  0.05 | `#8EAFA9` |
|  1.20,  1.15 | `#A6AA79` |
|  0.05,  1.25 | `#C6A760` |
| −0.75,  1.20 | `#B86958` |
| −1.25,  0.45 | `#9B6174` |

Each blob is a radial gradient from its colour to clear at radius 0.65 of the frame. The whole stack
is blurred **24σ**, then masked by an oval radial gradient with stops `[0, 0.54, 0.72, 1]` and
alphas `[1 − clarity·0.82, 1, 1, 0]`. `clarity` goes 0 → 1 over 280 ms when the step settles, which
hollows the centre so text stays legible.

**No purple anywhere** — `INV-UI-1`.

## Type

Bundled: `Inter-Regular/Medium/SemiBold/Bold`, `Literata-Regular/SemiBold`, registered at launch.
Literata is for headlines only; Inter carries every other run of text.

| role | font | size | weight | tracking | line height |
|---|---|---|---|---|---|
| intro hero | Literata | 46 | medium | **−2.07** | 1.08 |
| step headline | Literata | 38 | medium | −1.2 | 1.2 |
| "First…" | Inter | 38 | medium | −1.5 | — |
| body prose | Inter | 20 | medium | −0.3 | 1.5 |
| permission row copy | Inter | 15 | regular | — | 1.35 |
| status label | Inter | 12 | regular | — | — |
| button label | Inter | 16 | semibold | — | — |

The −2.07 tracking on 46 pt Literata is the signature move. In SwiftUI: `.tracking(-2.07)`.

The intro hero carries a shadow: black at 50 %, blur 18, offset (0, 1).

## Layout

- Content column max width **820 pt**; the permissions step narrows to **620 pt**.
- Page padding **45 pt horizontal, 58 pt vertical**.
- Everything centred, except the permissions step, which is left-aligned and stretched.
- Vertical rhythm between elements: 40, 28, 26, 18, 16, 12, 10, 8.

## Buttons

Primary: cream fill, ink label, **stadium** (fully rounded), min height 56 pt, 32 pt horizontal
padding, Inter 16 semibold. Secondary: same metrics, clear fill, cream label, 1 pt cream-55 % border.
No rounded rectangles for actions — always a full pill.

## Permission row

5 %-white fill, corner radius 16, 16 pt horizontal / 14 pt vertical padding. Leading: a 20 × 20
checkbox, corner radius 6, 1 pt white-45 % border, filling cream with an ink checkmark when granted
(180 ms). Then 13 pt gap, the first-person sentence at 82 % white, then the status word at 45 % white,
12 pt: `Granted` / `Open` / `Checking` / `Action required`.

The whole row is tappable and requests the capability.

## Motion

| element | spec |
|---|---|
| step transition | 240 ms `easeOut`, fade + slide from y +0.015 |
| word reveal | 1200 ms total; each word delay = 0.05 + random·0.18; opacity = easeOutExpo of `((t − delay) / 0.62)` clamped |
| backdrop fade-in | 900 ms easeOut, 0 → 0.74 |
| backdrop rise | 1800 ms easeOut; blobs start `(1 − rise)·0.72` lower |
| backdrop drift (while working) | 14 s loop; blob i orbits `cos(t·2π + i·0.71)·0.16` in x, `sin(phase·0.83)·0.12` in y |
| settle | 280 ms easeOut on `clarity` |
| checkbox | 180 ms |
| finale glow burst | 550 ms ease-out alpha fade over a full-screen edge glow |

**Honour Reduce Motion everywhere.** `NSWorkspace.shared.accessibilityDisplayShouldReduceMotion`
→ all durations zero, word reveal jumps to 1, drift stops.

## Window chrome

Borderless, shadowless, floating, full `visibleFrame`:

```swift
styleMask = [.borderless]
isOpaque = false; backgroundColor = .clear; hasShadow = false
level = .floating
collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
setFrame(NSScreen.main!.visibleFrame, display: true)   // visibleFrame, not frame — avoids grey bands
contentView?.layer?.backgroundColor = ink.cgColor      // never clear
```

Behind the SwiftUI content sits an `NSVisualEffectView`, `material = .hudWindow`,
`blendingMode = .behindWindow`, `isEmphasized = true`, masked by a radial alpha gradient with stops
`[0, 0.32, 0.58, 0.8, 1]` → alphas `[1, 0.95, 0.72, 0.32, 0]`. Full-bleed — any inset leaves a
visible dark ring.

## The mark

Eight dots on a 260 pt canvas, centre 129.5, dot radius 17.2. Dots 0/2/4/6 (N, E, S, W) sit at
radius 86.71; the diagonals at 91.92. `angle(i) = i·π/4` clockwise from due north;
`direction(θ) = (sin θ, −cos θ)`. Each dot is a solid circle over a blurred glow circle (blur 9·scale,
alpha 0.3).

In the menu bar the same geometry renders at 18 pt as a template image; while capturing, dots pulse
in sequence at 0.9 s per lap, and the pulse stops entirely when paused.

## Voice

First person, lowercase ambition, no jargon, one thought per screen. The app asks in its own voice —
"I would like to see your screen, so I know what you're working on" — and never explains itself
twice. If a sentence could be deleted without losing meaning, delete it.
