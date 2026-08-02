# Context for Claude — design system

**The app is a native macOS app, so its palette is macOS's.** Every colour is a system semantic
colour and the single accent is `NSColor.controlAccentColor` — whatever the user picked in System
Settings. Nothing is hand-mixed, so the app follows the system's appearance with no override, no
light-only assumption, and no second set of values for Dark. Display type is **Open Runde**, bundled
and ours; reading type is SF Pro.

This replaces an Anthropic palette (ivory `#FAF9F5` paper, `#141413` ink, clay `#D97757`) over New
York, which read as a piece of someone else's brand pasted into the menu bar.

Implemented in `Sources/ContextApp/Onboarding/Ink.swift`. Every colour and every type role in the app
comes from there — a colour literal anywhere else is a bug.

## Colour

Twelve roles. The right-hand column is the whole definition; there are no hex values to keep in sync.

```
surface        NSColor.controlBackgroundColor   the onboarding sheet, the popover ground
primary        NSColor.labelColor               headlines, row copy, the primary button fill
secondary      NSColor.secondaryLabelColor      a sentence someone reads
tertiary       NSColor.tertiaryLabelColor       a word someone glances at
separator      NSColor.separatorColor           a rule between blocks
hairline       labelColor @ 0.22                the edge of something you press
accent         NSColor.controlAccentColor       the one actionable link
errorRed       NSColor.systemRed                the only place the app raises its voice
listeningGreen NSColor.systemGreen              the 7 pt live dot
rowFill        labelColor @ 0.045               onboarding permission-row fill
rowFillHover   labelColor @ 0.085               the same row under the pointer
rowHover       tertiaryLabelColor @ 0.12        a *menu* row under the pointer
wash           labelColor @ 0.06                the pressed state of anything with no fill
glow           white                            the finale's `plusLighter` overexposure
```

AppKit twins for the layers SwiftUI cannot reach: `nsSurface`, `nsPrimary`, `nsAccent`.

**Three steps of type colour, and no fourth.** `primary` → `secondary` → `tertiary`, chosen by what
the reader has to do with the text, not by how deep it sits in a stack:

| use | colour |
|---|---|
| headlines, row copy, anything with an action attached | `primary` |
| a sentence someone reads: prose, a status line, an upload note | `secondary` |
| a word someone glances at: `Granted`, `Sign out` | `tertiary` |

A state with something to do about it ("Not signed in…", "Not connected to Claude") gets full
`primary`, not less. `tertiary` is for a single word beside its subject and never for a sentence.

Why the fills are **alpha on `labelColor`** rather than named fill colours: they have to composite
correctly over both the onboarding sheet *and* the popover's vibrant material. A wash that darkens in
Light and lightens in Dark does; a fixed grey does not.

Why the primary button is **not** accent-filled: `controlAccentColor` is the user's choice, so its
luminance is unknowable and no single label colour is legible against every accent. Inverting the
label ladder (`primary` fill, `surface` label) is high-contrast in both appearances by construction,
and it leaves the accent spent on the one link that needs it.

**No purple anywhere** — `INV-UI-1`. Note that the accent is the *user's* value, not one this system
picks; that is the only way an accent can be native.

### Appearance

There is **no `NSApp.appearance` override**, and there must never be one again. Pinning the process
to `.aqua` rendered a light popover inside a dark system menu — the loudest single reason the colours
read as wrong — and it silently overrode every AppKit surface the app does not draw itself: focus
rings, scrollers, the popover window's own background and corner rounding.

### Backdrop

Nine blobs, at the same nine unit positions as ever — the geometry has never changed, the colour has.
Every blob is now the **same** colour, `primary` (`labelColor`), and differs only in alpha:

| unit position (x, y) | alpha |
|---|---|
| −1.25, −1.20 | 0.16 |
| −0.25, −1.25 | 0.11 |
|  0.35, −1.25 | 0.08 |
|  1.20, −1.05 | 0.15 |
|  1.25,  0.05 | 0.12 |
|  1.20,  1.15 | 0.14 |
|  0.05,  1.25 | 0.13 |
| −0.75,  1.20 | 0.17 |
| −1.25,  0.45 | 0.10 |

One colour is the point, not a shortcut. `labelColor` is near-black in Light and near-white in Dark,
so a low-alpha wash of it **darkens a light sheet and lightens a dark one** — both read as shading
across a sheet, which is the whole intent of the field. Nine fixed hues cannot do that: a tone tuned
to look like light on paper looks like dirt on a dark ground. Saturated colour here would read as
nine coloured lights, which is a bug and not a backdrop.

The alphas keep the previous warm field's relative intensity (its tones sat 5–9% off its paper) and
are nudged up, because a 3% wash that reads as shading on white is invisible as light on near-black.

Each blob is a radial gradient from its colour to clear at radius 0.65 of the frame. The stack is
blurred **24σ** and composited at **0.55** peak opacity over a **`surface` @ 0.985** floor. Past ~0.6
the wash stops looking like light across the sheet and starts looking like a stain on it.

The floor stops just short of opaque: the last one and a half per cent let the desktop through as
a tint, which is what keeps the oval reading as a sheet lying on the screen rather than a window
pasted over it — and it is little enough that `primary` type holds its full contrast over any
desktop, in either appearance.

Two masks, both elliptical, both essential:

- The **composite** mask — floor and field together, never each layer separately — stops
  `[0, 0.52, 0.78, 0.92, 1]` at alphas `[1, 1, 0.72, 0.26, 0]`. This is the only thing between a
  rectangular window and a visible box on the desktop. Alpha reaches zero before the frame edge, so
  there is nothing left to clip at the corners.
- The **hollow**, on the field alone: stops `[0, 0.54, 0.72, 1]`, alphas `[1 − clarity·0.82, 1, 1, 0]`
  with farthest-corner radius (√2⁄2). `clarity` goes 0 → 1 over 280 ms when the step settles, which
  empties the centre so headline copy sits on a clean sheet.

**No rectangle may appear at any point, in any state.** Anything that paints the window edge —
a shadow, an opaque root layer, an `NSVisualEffectView` — puts back the border the mask exists to
remove.

## Type

**Open Runde above the display threshold, SF Pro below it.** One threshold —
`Font.inkDisplayThreshold = 22 pt` — decides which, because the split is a fact about the role and
every role already encodes its role in its size. A headline is never 15 pt here and body copy is
never 24. Nothing takes a flag at a call site.

Open Runde is a geometric sans with rounded terminals: distinctive, and ours rather than borrowed. It
replaces New York, which was reached for as a stand-in for Anthropic's editorial serif and therefore
carried a brand this app has no business wearing. Reading type stays SF Pro, which is what a native
macOS app should be setting body copy in anyway, and which is also where a bundled face buys least.

Bundled as `Resources/Fonts/OpenRunde-{Regular,Medium,Semibold,Bold}.otf`, copied into the bundle by
`scripts/build.sh`, and registered at launch by `ContextAppDelegate.registerBundledFonts()` with
`CTFontManagerRegisterFontsForURL(.process)`. `InkFonts.invalidate()` runs straight after, so nothing
can keep a system-font stand-in it cached before registration.

They are **OpenType/CFF**, not TrueType: both the bundle copier and the launch-time registrar accept
`.otf` and `.ttf`. An extension filter that knows only about `.ttf` silently drops every face.

Faces resolve by **PostScript name** — `OpenRunde-Regular`, `OpenRunde-Medium`, `OpenRunde-Semibold`
(lowercase `b`), `OpenRunde-Bold` — because the family + weight route does not dependably reach them.
Two consequences:

- A name that does not resolve fails **silently**, degrading the whole display ladder to SF Pro with
  nothing on screen to say so. `MenuBarPresentationTests` asserts every name resolves.
- `Text.bold()` on a Semibold headline has no bolder member to resolve to and the emphasis quietly
  vanishes. `RandomizedText` names `OpenRunde-Bold` outright instead.

A face that will not register costs a typeface, not a launch: `InkFonts.resolve` returns the SF Pro
font **and** SF Pro's metrics together, so the drawn face and the measured face can never disagree.

| role | weight | size | tracking | em | line height |
|---|---|---|---|---|---|
| intro hero | semibold | 32 | −1.12 | −0.035 | 1.10 |
| step headline | semibold | 25 | −0.75 | −0.03 | 1.18 |
| "First…" | semibold | 25 | −0.75 | −0.03 | — |
| body prose | regular | 15 | −0.15 | −0.01 | 1.55 |
| permission row copy | medium | 13 | −0.13 | −0.01 | 1.40 |
| status label | regular | 11 | — | — | — |
| button label | semibold | 14 | −0.14 | −0.01 | — |

The tracking ladder is converted from `em` at each size: tight at display, barely there at body,
**nothing below 12 pt** — under 12 pt, tightening a geometric sans only closes its counters. The
hero's −0.035 em is the signature: at 32 pt a round, wide sans falls apart unless the words lock up.

The hero is the largest thing on any screen and stays that way. Row copy is medium rather than
regular because 13 pt regular goes weedy on a card.

**None of these roles appear in the menu bar popover.** That surface is a menu and is set in plain
SF Pro at system sizes — see below.

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

The onboarding sheet's only action shape, and the popover has none of them.

Primary: **`primary`** fill, **`surface`** label, **stadium** (fully rounded), min height 42 pt, 24 pt
horizontal padding, Open Runde 14 semibold. Secondary: same metrics, clear fill, `primary` label, 1 pt
`hairline` border. No rounded rectangles for actions — always a full pill.

Pressed **lets the surface through**: primary drops to `primary` @ 0.82, secondary fills with `wash`.
Colour only, no scale: a pill this size bouncing reads as a toy.

## Permission row

The same row renders on two surfaces that must not look alike, selected by `InkPermissionRow(native:)`.

**Onboarding (`native: false`) — a card.** `rowFill`, 1 pt `separator` hairline, corner radius 13,
14 pt horizontal / 11 pt vertical padding. A fill strong enough to read on its own would box three
sentences into three grey slabs. Hover goes to `rowFillHover`.

Leading: an 18 × 18 checkbox, corner radius 6, 1 pt `hairline`, filling **`primary` with a `surface`
checkmark** when granted (180 ms). Then an 11 pt gap, the first-person sentence in `primary`, then the
status word in `tertiary`, 11 pt: `Granted` / `Open` / `Checking` / `Action required`.

**Menu bar (`native: true`) — a menu item.** See the next section. No fill at rest, no border, no
tracking, no drawn checkbox.

The whole row is tappable on both surfaces and requests the capability.

## Menu bar popover

**This surface is a menu, so it is drawn like one.** It sits beside every other menu bar extra on the
machine; a filled row capsule and letter-spaced type are the single clearest tell that a panel was
drawn by a website rather than by macOS. None of the `InkType` roles appear here.

- 320 pt wide, 12 pt horizontal / 8 pt vertical padding, 6 pt between groups.
- `Divider()` between groups — never a hand-drawn `Rectangle`.
- Row height **22 pt**, the height AppKit gives a menu item (`InkPermissionRow.menuRowHeight`).
  Capability rows abut at spacing 0.
- Row text: plain **SF Pro at `NSFont.systemFontSize`**. Secondary lines (the transcript line, an
  upload note, a paused reason, a connector note) at `NSFont.smallSystemFontSize`.
- **One left edge, 18 pt in**: a 12 pt checkmark column plus the 6 pt gap after it. Lines that sit
  outside a row are inset by hand to land on it. A menu whose text has two left margins is the other
  half of looking counterfeit.
- No fill at rest. Under the pointer a row takes `rowHover` on a 4 pt corner radius.
- Capability rows: a leading checkmark when granted (the column stays open when not, so granted and
  ungranted titles align), the noun in `primary`, the status trailing in `tertiary`.
- The live dot is 7 pt, `listeningGreen` when capturing and `tertiary` when paused, in that same
  12 pt column.
- `Pause`/`Resume` and `Quit` are **menu commands**, not buttons: full-width 22 pt rows, titles in
  `primary`, `⌘Q` trailing in `secondary`. A command set in `tertiary` inside a 22 pt row reads as
  disabled, which is the opposite of what either of these is.
- **`accent` on exactly one thing:** the "Connect" link, the only place in the popover with something
  to press that is not a command row. "Sign out" stays a quiet trailing link in `tertiary`.

Colour is `Ink` throughout, which is system semantics, so the panel follows the menu bar's own
appearance. There is no appearance override on the popover or on the process.

## The sign-in callback page

The loopback OAuth page in `LoopbackCallbackServer` is the app's one web surface, and it is the one
deliberate exception to everything above: a browser page cannot read macOS semantic colours, so it
carries fixed values and pins `color-scheme: light`. It opens in the same browser as the product site
and is held to that site's palette: `#FBF8F4` ground, `#171412` heading, `#6B625B` body, `#C9352B`
when sign-in failed, Open Runde first in the font stack.

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

The finale burns the sheet out from its edges: a radial `glow` gradient in `plusLighter`, which
drives the outer ring to white. `plusLighter` only ever adds, so the exit has to be the brightest
value available or there is nothing to burn out to — over a dark sheet, adding a dark grey is
invisible. On a light sheet a fade to transparent would just be the surface becoming the surface.

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

Two marks. Both are template-black at the point they meet AppKit, so the system owns their colour.

**The menu bar mark** (`MenuBar/ContextMark.swift`) — a round head, two oval eyes, two curved legs,
drawn as vectors on a 20 × 20 design box and rendered at 18 pt, the size it is displayed at. It is
`NSColor.black` with **`image.isTemplate = true`**, which is not a detail: a template image inverts
itself for a light or dark menu bar and dims with the status item when the app is inactive. It shipped
once as non-template clay and looked wrong on half the machines it ran on. `MenuBarPresentationTests`
asserts the template flag.

**The eight-dot mark** (`OmiMark`) — eight dots on a 260 pt canvas, centre 129.5, dot radius 17.2.
Dots 0/2/4/6 (N, E, S, W) sit at radius 86.71; the diagonals at 91.92. `angle(i) = i·π/4` clockwise
from due north; `direction(θ) = (sin θ, −cos θ)`. Each dot is a solid circle over a blurred glow
circle (blur 9·scale, alpha 0.3). It draws in `primary` by default, and `templateImage(size:)` is its
AppKit form.

The onboarding spotlight ring is drawn in **`nsAccent` @ 0.9**, because it lands on the menu bar —
the system's own surface, routinely dark *and* routinely light, so neither end of the label ladder is
guaranteed to show up there.

`Resources/ContextForClaude.icns` still carries the old palette and is regenerated separately.

## Voice

First person, lowercase ambition, no jargon, one thought per screen. The app asks in its own voice —
"I would like to see your screen, so I know what you're working on" — and never explains itself
twice. If a sentence could be deleted without losing meaning, delete it.

## What the previous systems had that this one does not

The app has worn three palettes. Each drop was deliberate.

**The dark system** — a `#171716` ink surface, `#FFFCEC` cream type, a saturated nine-blob field,
Literata headlines over Inter body:

- **The cream alpha ladder** (0.08 / 0.35 / 0.50 / 0.55 / 0.70) and a separate white ladder for
  permission rows. Two ladders of translucency became one explicit three-step text hierarchy. An
  alpha is a value; a role is a decision.
- **Literata and the serif/sans split.** "First…" no longer contrasts with the step headline by face;
  both are Open Runde at one headline size.
- **The −2.07 tracking on 46 pt Literata**, a serif's signature. The hero keeps a signature at
  −0.035 em.
- **The intro hero's drop shadow** and the whole `InkTextShadow` mechanism. There is no shadow
  anywhere in the system now.
- **`cursorBlue` `#96C4FF`** and **`errorRed` `#FFB4AB`**, both tuned for a dark ground.
- **`NSVisualEffectView` behind the card**, and not coming back: a behind-window material takes its
  brightness from whatever is on the desktop, which is exactly what a sheet must not do.

**The Anthropic system** — ivory `#FAF9F5` paper, `#141413` ink, clay `#D97757`, New York display:

- **The whole hand-mixed palette.** It was another company's, it needed a light-only appearance
  override to hold together, and it was unreadable in Dark because the tones were fixed and the
  material behind them was not. System semantics replace all of it and are appearance-correct for
  free.
- **`NSApp.appearance = .aqua`.** Deleted. See *Appearance* above.
- **The warm clay/manilla/kraft backdrop.** Nine fixed warm tones became one neutral colour at nine
  alphas, which shades correctly in both appearances.
- **New York**, reached for as a stand-in for Tiempos. A borrowed serif is still borrowed.
- **The clay, non-template menu bar mark.** Back to template black.
- **The onboarding sheet's card chrome in the menu bar** — the filled row capsule
  (`quaternaryLabelColor` @ 0.5), `.inkStyle` tracking, 42 pt button pills and hand-drawn hairlines.
  The popover is a menu now.
