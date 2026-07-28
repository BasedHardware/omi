# Context for Claude — design system

The app and the product site (`archit-lal.github.io/Periphery`) are one product, so they are one
system: warm paper, warm near-black ink, a bronze accent, Open Runde throughout. The palette below
is the site's `:root` block, copied value for value. Values are exact; do not round them.

Implemented in `Sources/ContextApp/Onboarding/Ink.swift`. Every colour and every type role in the
app comes from there — a literal hex anywhere else is a bug.

## Colour

The site's seven variables, keeping the site's names:

```
paper   #FBF8F4   every surface: the onboarding oval, the popover
ink     #171412   primary type, the primary button fill, the granted checkbox
mid     #6B625B   secondary type: prose, the popover's status lines            5.6:1 on paper
faint   #A39A92   tertiary type: a status word, a count, "Quit"                2.6:1 on paper
line    #E6DFD6   rules and card hairlines
bronze  #8F6420   the one accent — an actionable link, and nothing else
red     #C9352B   the site's card outline; here, the error colour (`Ink.errorRed`)
```

**Three steps of type colour, and no fourth.** `ink` → `mid` → `faint`, chosen by what the reader
has to do with the text, not by how deep it sits in a stack:

| use | colour |
|---|---|
| headlines, row copy, anything with an action attached | `ink` |
| a sentence someone reads: prose, a status line, an upload note | `mid` |
| a word someone glances at: `Granted`, `Quit`, `Sign out`, the idle dot | `faint` |

`faint` is 2.6:1 on paper. That is fine for a single word next to its subject and wrong for a
sentence — when a line matters, it gets `mid`. A state with something to do about it ("Not signed
in…", "Not connected to Claude") gets full `ink`, not less.

Derived, because the site has no equivalent:

```
surface       #F3EEE5      permission-row fill — paper on paper
surfaceHover  #ECE5D9      the same row under the pointer
inkHairline   ink @ 0.28   a drawn edge: the secondary button, the empty checkbox
inkWash       ink @ 0.06   the pressed state of anything with no fill of its own
```

`line` is right for a rule between blocks and too faint for the edge of something you press.

One hue sits outside the site palette: **listening green `#2E8B57`**, the live dot in the popover.
The site never had to say "on"; a 7 pt dot does, and green is the only colour that says it without
a label.

**No purple anywhere** — `INV-UI-1`.

### Backdrop

Nine blobs, at the same nine unit positions as ever — the geometry did not change, the colour did:

| unit position (x, y) | hex |
|---|---|
| −1.25, −1.20 | `#E8D9C6` |
| −0.25, −1.25 | `#F0E2D2` |
|  0.35, −1.25 | `#EFE4D3` |
|  1.20, −1.05 | `#E2DFD6` |
|  1.25,  0.05 | `#E6E3D8` |
|  1.20,  1.15 | `#EBE5D4` |
|  0.05,  1.25 | `#F1E6D0` |
| −0.75,  1.20 | `#EEDDCB` |
| −1.25,  0.45 | `#E9DCCC` |

Every tone is a warm neutral a step or two below `paper`, so the field reads as shading across a
sheet rather than as nine coloured lights. Saturated colour on paper reads as dirt.

Each blob is a radial gradient from its colour to clear at radius 0.65 of the frame. The stack is
blurred **24σ** and composited at **0.55** peak opacity over a **`paper` @ 0.985** floor. Past ~0.6
the wash stops looking like light across the sheet and starts looking like a stain on it.

The floor stops just short of opaque: the last one and a half per cent let the desktop through as
a tint, which is what keeps the oval reading as a sheet lying on the screen rather than a window
pasted over it — and it is little enough that ink type holds its full contrast over any desktop.

Two masks, both elliptical, both essential:

- The **composite** mask — floor and field together, never each layer separately — stops
  `[0, 0.52, 0.78, 0.92, 1]` at alphas `[1, 1, 0.72, 0.26, 0]`. This is the only thing between a
  rectangular window and a visible box on the desktop. Alpha reaches zero before the frame edge, so
  there is nothing left to clip at the corners.
- The **hollow**, on the field alone: stops `[0, 0.54, 0.72, 1]`, alphas `[1 − clarity·0.82, 1, 1, 0]`
  with farthest-corner radius (√2⁄2). `clarity` goes 0 → 1 over 280 ms when the step settles, which
  empties the centre so headline copy sits on clean paper.

**No rectangle may appear at any point, in any state.** Anything that paints the window edge —
a shadow, an opaque root layer, an `NSVisualEffectView` — puts back the border the mask exists to
remove.

## Type

**Open Runde at 400 / 500 / 600 / 700, and nothing else.** The site resolves `--sans`, `--disp` and
`--mono` all to Open Runde; so does the app. Bundled as
`Resources/Fonts/OpenRunde-{Regular,Medium,Semibold,Bold}.otf` and registered at launch by
PostScript name — `OpenRunde-Regular`, `OpenRunde-Medium`, `OpenRunde-Semibold`, `OpenRunde-Bold`.

They are **OpenType/CFF**, not TrueType: both the bundle copier (`scripts/build.sh`) and the
launch-time registrar accept `.otf` and `.ttf`. An extension filter that knows only about `.ttf`
silently drops every face in the product.

Medium and Semibold each ship as their **own single-face family** ("Open Runde Semibold" / Regular),
so:

- Asking for family + weight never finds them. The PostScript name is the only reliable handle.
- `Text.bold()` on a Semibold headline has no bolder member to resolve to and the emphasis quietly
  vanishes. `RandomizedText` names `OpenRunde-Bold` outright instead.

| role | weight | size | tracking | em | line height |
|---|---|---|---|---|---|
| intro hero | semibold | 32 | −1.12 | −0.035 | 1.10 |
| step headline | semibold | 25 | −0.75 | −0.03 | 1.18 |
| "First…" | semibold | 25 | −0.75 | −0.03 | — |
| body prose | regular | 15 | −0.15 | −0.01 | 1.55 |
| permission row copy | medium | 13 | −0.13 | −0.01 | 1.40 |
| status label | regular | 11 | — | — | — |
| button label | semibold | 14 | −0.14 | −0.01 | — |

The tracking ladder is the site's, converted from `em` at each size: tight at display, barely there
at body, **nothing below 12 pt** — under 12 pt, tightening a geometric sans only closes its
counters. The hero's −0.035 em is the signature: at 32 pt a round, wide sans falls apart unless the
words lock up.

The hero is the largest thing on any screen and stays that way. Row copy is medium rather than
regular because 13 pt regular goes weedy on a paper card.

Line-height multiples tighter than the face's own leading (1.10, 1.18, 1.40) cannot be expressed
through `.lineSpacing`, which is defined as non-negative — those roles render at the face's natural
leading. `InkTextStyle.leadingDelta` is the escape hatch for a caller laying out lines itself.

## Layout

- Content column max width **488 pt**; the permissions step uses the same width, left-aligned.
- Page padding **36 pt horizontal, 34 pt vertical**.
- Everything centred, except the permissions step, which is left-aligned and stretched.
- Vertical rhythm: 28, 22, 18, 14, 12, 10, 8, 6.
- The onboarding window is 720 × 520 pt. Roughly a third of that is falloff.

## Buttons

Primary: **ink** fill, **paper** label, **stadium** (fully rounded), min height 42 pt, 24 pt
horizontal padding, Open Runde 14 semibold. Secondary: same metrics, clear fill, ink label, 1 pt
`inkHairline` border. No rounded rectangles for actions — always a full pill.

Pressed **lightens** — primary drops to ink @ 0.82, secondary fills with `inkWash`. On paper,
letting the surface through is the only direction that reads as give. Colour only, no scale: a pill
this size bouncing reads as a toy.

## Permission row

`surface` fill, 1 pt `line` hairline, corner radius 13, 14 pt horizontal / 11 pt vertical padding —
paper on paper. A fill strong enough to read on its own would box three sentences into three grey
slabs. Hover goes to `surfaceHover`.

Leading: an 18 × 18 checkbox, corner radius 6, 1 pt `inkHairline`, filling **ink with a paper
checkmark** when granted (180 ms). Then an 11 pt gap, the first-person sentence in `ink`, then the
status word in `faint`, 11 pt: `Granted` / `Open` / `Checking` / `Action required`.

The whole row is tappable and requests the capability.

## Menu bar popover

320 pt wide, `paper` background, 16 pt horizontal / 14 pt vertical padding. `ink` for the state
line, `mid` for the sentences under it, `faint` for the two quiet exits ("Sign out", "Quit") — the
site's own footer-link treatment. `line` hairlines between blocks. **Bronze on exactly one thing:**
the "Connect" link, the only place in the popover with something to press that is not a button.

The app sets `NSAppearance(named: .aqua)` at launch. Every surface it draws is paper in both system
appearances, so the AppKit chrome it does not draw — the popover window's background and corner
rounding, focus rings, scrollers — has to be told the same thing, or a dark-mode Mac frames a light
popover in a dark shell.

## The sign-in callback page

The loopback OAuth page in `LoopbackCallbackServer` is the app's one web surface, and it opens in
the same browser as the product site. It is held to the site's palette: `#FBF8F4` ground, `#171412`
heading, `#6B625B` body, `#C9352B` when sign-in failed, Open Runde first in the stack.

## Motion

| element | spec |
|---|---|
| step transition | 240 ms `easeOut`, fade + slide from y +0.015 |
| word reveal | 1200 ms total; each word delay = 0.05 + random·0.18; opacity = easeOutExpo of `((t − delay) / 0.62)` clamped |
| backdrop fade-in | 900 ms easeOut, 0 → 0.55 |
| backdrop rise | 1800 ms easeOut; blobs start `(1 − rise)·0.72` lower |
| backdrop drift (while working) | 14 s loop; blob i orbits `cos(t·2π + i·0.71)·0.16` in x, `sin(phase·0.83)·0.12` in y |
| settle | 280 ms easeOut on `clarity` |
| checkbox | 180 ms |
| press | 90 ms |
| finale glow burst | 550 ms ease-out over a full-screen edge glow |

The finale burns the sheet out from its edges: a radial `paper` gradient in `plusLighter`, which
drives the outer ring to white. On a light surface that is the only exit visible at all — a fade to
transparent would just be paper becoming paper.

**Honour Reduce Motion everywhere.** `NSWorkspace.shared.accessibilityDisplayShouldReduceMotion`
→ all durations zero, word reveal jumps to 1, drift stops, the backdrop renders its resolved state
immediately. Everything routes through `InkReduceMotion`, so honouring it is a call rather than a
discipline nobody keeps.

## Window chrome

Borderless, shadowless, floating, fixed 720 × 520 centred on the screen the pointer is on:

```swift
styleMask = [.borderless]
isOpaque = false; backgroundColor = .clear; hasShadow = false
level = .floating
collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
contentView = <clear, first-mouse-accepting>   // never layer-backed with a colour
```

A shadow would trace the window's rectangle around an oval that has no edge — the one thing that
gives the illusion away. There is deliberately **no `NSVisualEffectView`**: its material is a
rectangle, and every way of masking one down to an ellipse leaves a faint straight edge somewhere.
The surface is painted entirely in SwiftUI, where a single elliptical mask is exact.

## The mark

Eight dots on a 260 pt canvas, centre 129.5, dot radius 17.2. Dots 0/2/4/6 (N, E, S, W) sit at
radius 86.71; the diagonals at 91.92. `angle(i) = i·π/4` clockwise from due north;
`direction(θ) = (sin θ, −cos θ)`. Each dot is a solid circle over a blurred glow circle (blur 9·scale,
alpha 0.3). It draws in `ink` by default.

In the menu bar the Context mark renders at 18 pt as a template image, which the system tints for
the menu bar's own light/dark state. The onboarding spotlight ring is the one exception to the
palette's direction: it is drawn in **paper**, because it lands on the menu bar — the system's
surface, and routinely dark.

## Voice

First person, lowercase ambition, no jargon, one thought per screen. The app asks in its own voice —
"I would like to see your screen, so I know what you're working on" — and never explains itself
twice. If a sentence could be deleted without losing meaning, delete it.

## What the previous system had that this one does not

The app was dark: a `#171716` ink surface, `#FFFCEC` cream type, a saturated nine-blob field,
Literata headlines over Inter body. Deliberately dropped, not overlooked:

- **The cream alpha ladder** (0.08 / 0.35 / 0.50 / 0.55 / 0.70) and the separate white ladder for
  permission rows. Two ladders of translucency over a dark floor became one explicit three-step
  text hierarchy — `ink` / `mid` / `faint` — plus named surfaces. An alpha is a value; a role is a
  decision.
- **Literata, and the serif/sans split.** The site has no serif, so neither does the app. "First…"
  no longer contrasts with the step headline by face; both are Open Runde at one headline size.
- **The −2.07 tracking on 46 pt Literata.** That number was a serif's signature. The hero keeps a
  signature, at the site's own −0.035 em.
- **The intro hero's drop shadow** (black 50 %, blur 18, offset 0/1) and the whole `InkTextShadow`
  mechanism. A dark shadow under type on paper is grime; there is no shadow anywhere in the system
  now.
- **`cursorBlue` `#96C4FF`.** The one actionable link is bronze. A light blue would be both
  invisible on paper and off-palette.
- **`errorRed` `#FFB4AB`**, a pale red tuned for a dark ground, replaced by the site's `#C9352B`.
- **`NSVisualEffectView` behind the card**, already gone before this pass and not coming back: a
  behind-window material takes its brightness from whatever is on the desktop, which is exactly what
  a paper floor must not do.
