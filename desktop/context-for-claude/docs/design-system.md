# Context for Claude — design system

**The app is a native macOS app, so its palette is macOS's.** Every colour is a system semantic
colour or a fixed alpha on one, and the single accent is `NSColor.systemBlue` — a *named* system
colour, picked here rather than read off the machine. No hue is hand-mixed, so the app follows the
system's appearance with no override, no light-only assumption, and no second set of values for Dark.
Display type is **Open Runde**, bundled and ours; reading type is SF Pro.

This replaces an Anthropic palette (ivory `#FAF9F5` paper, `#141413` ink, clay `#D97757`) over New
York, which read as a piece of someone else's brand pasted into the menu bar.

Implemented in `Sources/ContextApp/Onboarding/Ink.swift`. Every colour and every type role in the app
comes from there — a colour literal anywhere else is a bug.

## Colour

Twelve roles. The right-hand column is the whole definition; there are no hex values to keep in sync.

```
surface        NSColor.controlBackgroundColor   the onboarding sheet, the popover ground
primary        NSColor.labelColor               headlines, row copy, the primary button fill
secondary      labelColor @ 0.80                a sentence someone reads
tertiary       labelColor @ 0.66                a word someone glances at
separator      NSColor.separatorColor           a rule between blocks
hairline       labelColor @ 0.22                the edge of something you press
accent         NSColor.systemBlue               the one actionable link
errorRed       NSColor.systemRed                the only place the app raises its voice
listeningGreen NSColor.systemGreen              the 7 pt live dot
rowFill        labelColor @ 0.045               onboarding permission-row fill
rowFillHover   labelColor @ 0.085               the same row under the pointer
rowHover       tertiaryLabelColor @ 0.12        a *menu* row under the pointer
wash           labelColor @ 0.06                the pressed state of anything with no fill
glow           white                            the finale's `plusLighter` overexposure
```

AppKit twins for the layers SwiftUI cannot reach: `nsSurface`, `nsPrimary`. There is deliberately no
`nsAccent` — a second definition of the accent is a second thing to keep true, and AppKit callers
that need it can say `NSColor(Ink.accent)`.

**Three steps of type colour, and no fourth.** `primary` → `secondary` → `tertiary`, chosen by what
the reader has to do with the text, not by how deep it sits in a stack:

| use | colour |
|---|---|
| headlines, row copy, anything with an action attached | `primary` |
| a sentence someone reads: prose, a status line, an upload note | `secondary` |
| a word someone glances at: `Granted`, `Sign out` | `tertiary` |

A state with something to do about it ("Not signed in…", "Not connected to Claude") gets full
`primary`, not less. `tertiary` is for a single word beside its subject and never for a sentence.

Why the two lower steps are **alpha on `labelColor`** and not `secondaryLabelColor` /
`tertiaryLabelColor`: the system's steps are 50% and 26% black in Light, tuned for dense system
chrome — an inspector row, a table cell, a menu — where the reader glances at a word beside its
subject. Over `surface` they measure 3.95:1 and 1.88:1, so the step that carries onboarding's prose
was under WCAG AA for body text (4.5:1) and the step below it was barely a shade. Onboarding is the
one screen that asks for sustained reading, and it was reported as hard to read.

Measured over `surface`, composited in linear light (`MenuBarPresentationTests` asserts these):

| step | Light | Dark |
|---|---|---|
| `primary` (`labelColor`, 0.85) | 14.9:1 | 12.2:1 |
| `secondary` (`labelColor` @ 0.80) | 7.8:1 | 8.3:1 |
| `tertiary` (`labelColor` @ 0.66) | 4.9:1 | 6.1:1 |

`secondary` is held to AAA (7:1) because it is the only step that carries whole sentences.
`tertiary`'s alpha is set by the *worst* ground rather than the best: on the glass over a solid black
desktop it falls to 4.55:1, and thinning it would put it under AA. The ladder is still three visible
steps — L\* 15.6 / 35.0 / 47.4 in Light, 88.0 / 74.2 / 64.3 in Dark. **`surface` is no longer the
whole ground on any window that wears the glass** — see *The glass* for the ladder measured there, and
for why `tertiary`'s alpha, not the scrim, is what caps how see-through every panel in the app can be.

Why the fills are **alpha on `labelColor`** rather than named fill colours, and the same reason the
type steps are: they have to composite correctly over both the onboarding sheet *and* the popover's
vibrant material. A wash that darkens in Light and lightens in Dark does; a fixed grey does not.
`rowHover` is the one exception that stays on `tertiaryLabelColor` — it is a fill nobody reads, and
it is supposed to be barely there.

Why the primary button is **not** accent-filled: a filled accent button owes a label colour legible
on it in both appearances, which is one more contrast pair to keep true. Inverting the label ladder
(`primary` fill, `surface` label) is high-contrast in both appearances by construction, and it leaves
the accent spent on the one link that needs it.

**No purple anywhere** — `INV-UI-1`. The accent used to be `NSColor.controlAccentColor`, the accent
the user picked in System Settings, on the reasoning that a borrowed brand is worse than a borrowed
hue. That was wrong in one specific way that no call site could correct: **macOS offers Purple
there**, so on that machine every ring, checkbox, toggle and link spending the accent rendered
purple. A rendered-pixel check cannot catch it either — every machine this was developed on has a
blue accent, so the guard came back green and the defect shipped anyway. The accent is therefore a
value this system picks. `InkAccentTests` holds the line three ways: the token's rendered pixel
through the shared `BrandColour` predicate, the token's *catalog identity* (which is what survives
being run on a blue Mac), and a labelled static tripwire over `Sources/ContextApp` for a view that
skips `Ink` and reaches for `controlAccentColor` inline.

One exposure of the same class is still open and is listed in that test: `AccentChoice.system`, the
default in the Appearance pane, resolves to `controlAccentColor` and tints the whole Settings window
with it. `SettingsTests.testSystemAccentIsTheUsersOwn` currently pins that behaviour deliberately.

### Appearance

There is **no `NSApp.appearance` override**, and there must never be one again. Pinning the process
to `.aqua` rendered a light popover inside a dark system menu — the loudest single reason the colours
read as wrong — and it silently overrode every AppKit surface the app does not draw itself: focus
rings, scrollers, the popover window's own background and corner rounding.

### The glass

**Every translucent surface in this app is one component: `InkGlassView`** — the onboarding card, the
timeline, the settings window, the menu bar popover, the search panels and the tutorial's coach
marks. One `NSVisualEffectView`, one scrim, one corner, one shadow, built in `InkGlass.swift` and
hosted everywhere else. A translucent surface has four numbers that have to agree and six windows
copy-pasting them is six chances to disagree.

**It is pinned to a light appearance** (`NSAppearance(named: .aqua)`, set on the panel view — or on
the whole window where there is a title bar to convert with it). `NSVisualEffectView` renders a
*different, dark* material in `.darkAqua`, and `controlBackgroundColor` resolves near-black there, so
on a Dark machine this surface read as a black slab pasted over the desktop rather than as glass. The
pin is also what makes `labelColor` — and therefore the whole `Ink` ladder — resolve **dark** on the
panel; a surface forced light whose type did not follow is white-on-white, which is nothing on screen
at all. `InkGlassTests.testTheTypeResolvesDarkOnTheLightGlass` is that assertion.

**The material is `.headerView`, and it was measured rather than picked.** Fourteen candidates were
put over solid black and solid white full-screen backdrops, pinned to `.aqua`, and sampled
(macOS 15.5, `.behindWindow`, `.active`). Solving each composite for its own opacity and tint:

| material | opacity | tint | material | opacity | tint |
|---|---|---|---|---|---|
| `headerView` | 0.800 | (255,255,255) | `hudWindow` | 0.525 | (221,221,221) |
| `titlebar` | 0.809 | (246,246,247) | `fullScreenUI` | 0.525 | (221,221,219) |
| `sidebar` | 0.903 | (228,228,228) | `popover` | 0.651 | (229,229,229) |
| `menu` | 0.776 | (227,227,227) | `underWindowBackground` | 0.906 | (222,222,222) |
| `toolTip` | 0.902 | (222,222,222) | `selection` | 0.902 | (200,200,200) |

`sheet`, `windowBackground`, `contentBackground` and `underPageBackground` are opaque in `.aqua`.

The choice is not "which is most translucent" — it is **"which passes the most desktop through at a
fixed legibility floor"**, which is a different question with a different answer. Writing the ground
over a black desktop as `255·s + tint·a·(1−s)` and the desktop's share as `(1−a)(1−s)`, a **pure white
tint is optimal**: it is the only tint for which brightening the panel costs nothing in passthrough.
`.headerView` is the only translucent candidate that measures pure white. At the shared floor it
passes **12.8%** of the desktop; `titlebar` and `hudWindow` pass 11.6%, `popover` 11.2%, `sidebar`
6.7%.

The pin, not the machine, decides: re-run under a Light system and under a Dark one, the sampled
composites are identical, and a live render over a neutral desktop is pixel-identical between the two.

**The scrim is `surface` @ 0.36**, flat and full-bleed, painted over the material and under the
content. It is not a style choice — it is the floor of the label ladder. Measured through the real
material over the two extreme desktops, in both system appearances:

| step | black desktop | white desktop |
|---|---|---|
| `primary` | 11.87:1 | 14.94:1 |
| `secondary` | 6.86:1 | 7.79:1 |
| `tertiary` | 4.55:1 | 4.92:1 |

`tertiary` is the binding rung, and it needs a ground of **219/255** to clear WCAG AA — which for a
pure-white material at 0.800 opacity is a scrim of 0.295. 0.36 is that floor plus a margin, and the
margin costs 1.2 points of passthrough (12.8% rather than 14.1%).

**The number worth knowing before re-tuning this**: the panel can never pass more than
`1 − 219/255 = 14.1%` of the desktop while `tertiary` stays at `labelColor` @ 0.66, because the
material is already the brightest thing available. A request for a more see-through panel than that
is a request to darken the bottom rung of the type ladder — a change to `Ink`, and to every opaque
surface in the app, not to the scrim.

A scrim only *under the copy* would be the speech bubble's grey slab drawn a second time, so it is
full-bleed. `InkGlassTests` asserts the ladder on a two-layer model of this ground — checked against
the real composite to under 1/255 — and `InkGlass.measuredMaterialOpacity` / `measuredMaterialTint`
record the samples the model needs, because a material's opacity is not published and cannot be
derived.

**The corner is 22 pt**, continuous, and it is one value for every panel: a 56 pt bar and a 760 pt
timeline rounded differently read as two products. **The edge is `labelColor` @ 0.06** — much fainter
than `hairline` (0.22), which is the outline of a *control*; a panel that needs a drawn border is a
panel whose brightness and shadow are not doing their job.

**The shadow is broad and faint**: 34 pt radius, 0.24 opacity, 10 pt down. Almost all of the floating
quality comes from this, and the wrong shadow is not a missing one but a tight dark one. It is cast
from a `shadowPath` and masked so it never falls *under* the panel — behind a 13%-transparent surface
a filled blurred rounded rect is very much visible. A floating panel's window is therefore larger than
the panel by `InkGlassStyle.floating.inset` (56 pt), because a borderless window clips at its own
bounds and a panel drawn edge to edge has nowhere to cast into.

**Three styles, and they are not variations on a theme.** `.floating` is a free-floating object over
the desktop (rounded, edged, ambient shadow, inset). `.fullBleed` is the inside of an ordinary titled
window — the timeline, settings — square and shadowless because the window frame already owns both.
`.panel(cornerRadius:)` fills its host exactly, for a surface something else already positions and
shadows.

**Reduce Transparency is honoured**, and it is the one branch in the file: the ground goes fully
opaque and the material is *removed*, not covered. `InkGlassView.apply(reduceTransparency:)` takes the
setting rather than reading it, because the domain that holds it cannot be written even by `defaults`,
so a view that read it directly would have an accessibility path nothing could assert. The shadow
stays — the panel is still a floating object and still has to read as one.

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
| intro hero | semibold | 34 | −1.19 | −0.035 | 1.10 |
| step headline | semibold | 27 | −0.81 | −0.03 | 1.18 |
| "First…" | semibold | 27 | −0.81 | −0.03 | — |
| body prose | regular | 17 | −0.17 | −0.01 | 1.55 |
| permission row copy | medium | 15 | −0.15 | −0.01 | 1.40 |
| status label | regular | 12 | — | — | — |
| button label | semibold | 15 | −0.15 | −0.01 | — |

Every size is one step up from the ladder that shipped (32/25/15/13/11/14), because onboarding was
reported as being set too small to read comfortably. Nothing else about a role changed — same face,
same colour, same leading multiple — so the card reads as the same design at a size that does not ask
the reader to lean in. Two thresholds bound the change and are asserted: every reading role stays
under the 22 pt display threshold, so it is still SF Pro; and `prose` stays under 18 pt, so WCAG still
treats it as normal text and the label ladder's bar stays 4.5:1 rather than the 3:1 large-text
allowance. **The bar must not get easier because the type got bigger.**

The tracking ladder is converted from `em` **at each size**, and this is the rule a size change
breaks silently: tracking is stored in points, so a role that grows and keeps its old point value has
quietly loosened — bigger letterforms with the same gap between them. Recompute from the `em`, which
is the fixed part. Tight at display, barely there at body, and **nothing at 12 pt or under** — there,
tightening closes the counters faster than it locks the words up. The hero's −0.035 em is the
signature: at display size a round, wide sans falls apart unless the words lock up.

`InkType.minimumSize` (12 pt) is the floor, and the status label sits exactly on it — which is why
that role is also the one with no tracking. The hero is the largest thing on any screen and stays that
way. Row copy is medium rather than regular because a row's sentence sits beside a heavier headline
and regular goes weedy next to it.

**None of these roles appear in the menu bar popover.** That surface is a menu and is set in plain
SF Pro at system sizes — see below.

Line-height multiples tighter than the face's own leading (1.10, 1.18, 1.40) cannot be expressed
through `.lineSpacing`, which is defined as non-negative — those roles render at the face's natural
leading. `InkTextStyle.leadingDelta` is the escape hatch for a caller laying out lines itself.

## Layout

Two column widths, and the difference between them is deliberate.

- **Reading column 488 pt** (`contentMaxWidth`) — a headline and the sentences under it, centred.
  At 17 pt prose that is a little under 80 characters a line, the top of the range a paragraph stays
  readable across. Wider is not more generous; it is a longer distance for the eye to travel back
  along.
- **List column 560 pt** (`permissionsMaxWidth`) — the permissions step and the other left-aligned
  cards. This is what pays for the larger type: a permission row is not a paragraph but a sentence
  with a checkbox before it and a status word after it, and those fixtures take ~116 pt out of the
  row before the sentence starts. At 488 pt and 15 pt row copy every row wrapped to two lines and the
  setup preamble ran to five, putting the card 23 pt past the window. 560 pt is the card's own width
  (reading column plus both gutters), and it is also as wide as the column should go: 560 plus its
  padding leaves 80 pt of glass either side, and content that runs closer than that to a rounded edge
  reads as content that did not fit.
- Page padding **36 pt horizontal, 34 pt vertical**. The vertical figure is *not* a place to find
  height for bigger type: it is the only thing keeping a 34 pt headline off a rounded corner, and
  height is the dimension the cards actually run out of — the window is fixed and does not scroll.
- Everything centred, except the permissions, value, connector and tutorial steps, which are
  left-aligned and take the list column.
- Vertical rhythm: 28, 22, 18, 14, 12, 10, 8, 6.
- The onboarding window is 720 × 640 pt, and all of it is legible area — there is no falloff now.
- The foot of the card is a reserved band, `InkLayout.progressBandHeight` (44 pt), that the progress
  dots live in. It is subtracted from the height a card's content is laid out in, so the dots can
  never land on the content — which they did, inside the fourth permission row and on top of the
  "Show me the row" button, while they were an overlay pinned 62 pt off the bottom edge.
- **The content budget is `OnboardingWindow.cardContentHeight`** — the pane, less the page's vertical
  margins, less that band. 492 pt today.

**Resolved — the by-hand permission card's overflow.** When Accessibility is not granted, the
permissions step draws its headline, preamble and four rows *and* the by-hand choreography panel
underneath. That needs 505 pt, and the card had 452, so SwiftUI compressed the rows and three of the
four sentences truncated mid-word. Neither column width nor padding could fix it — the four rows
cannot come back to one line at any width the sheet will hold, so the panel is always the overflow —
so the card took the second of the two options this note used to offer and **grew to fit its tallest
state**. Two things keep it fixed:

- `InkPermissionRow`'s sentence is `.fixedSize` vertically, so a row wraps and can never truncate.
  Too little room is now a measurement that fails rather than copy that quietly disappears.
- `PermissionsCardLayoutTests` measures the real `PermissionsCard` through `NSHostingView` in every
  state the flow reaches and asserts each fits `cardContentHeight`. Longer copy, a fifth row or a new
  panel fails that test rather than shipping.

## Buttons

The onboarding sheet's only action shape, and the popover has none of them.

Primary: **`primary`** fill, **`surface`** label, **stadium** (fully rounded), min height 42 pt, 24 pt
horizontal padding, the button-label role (15 semibold, and SF Pro like every role under the display
threshold). Secondary: same metrics, clear fill, `primary` label, 1 pt `hairline` border. No rounded
rectangles for actions — always a full pill.

Pressed **lets the surface through**: primary drops to `primary` @ 0.82, secondary fills with `wash`.
Colour only, no scale: a pill this size bouncing reads as a toy.

## Permission row

The same row renders on two surfaces that must not look alike, selected by `InkPermissionRow(native:)`.

**Onboarding (`native: false`) — a card.** `rowFill`, 1 pt `separator` hairline, corner radius 13,
14 pt horizontal / 11 pt vertical padding. A fill strong enough to read on its own would box three
sentences into three grey slabs. Hover goes to `rowFillHover`.

Leading: an 18 × 18 checkbox, corner radius 6, 1 pt `hairline`, filling **`primary` with a `surface`
checkmark** when granted (180 ms). Then an 11 pt gap, the first-person sentence in `primary` at the
row-copy role, then the status word in `tertiary` at the status-label role: `Granted` / `Open` /
`Checking` / `Action required`. The checkbox and the two gaps take ~116 pt out of the row before the
sentence starts, which is why the list column is wider than the reading one.

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
| settle | 280 ms easeOut |
| checkbox | 180 ms |
| press | 90 ms |
| finale glow burst | 550 ms ease-out over a full-screen edge glow |

The finale burns the sheet out from its edges: a radial `glow` gradient in `plusLighter`, which
drives the outer ring to white. `plusLighter` only ever adds, so the exit has to be the brightest
value available or there is nothing to burn out to — over a dark sheet, adding a dark grey is
invisible. On a light sheet a fade to transparent would just be the surface becoming the surface.

**Honour Reduce Motion everywhere.** `NSWorkspace.shared.accessibilityDisplayShouldReduceMotion`
→ all durations zero and the word reveal jumps to 1. Everything routes through `InkReduceMotion`, so
honouring it is a call rather than a discipline nobody keeps. Reduce *Transparency* is separate and
routes through `InkReduceTransparency`; see *The glass*.

## Window chrome

Borderless, shadowless, floating, fixed 720 × 640 centred on the screen the pointer is on:

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

The onboarding spotlight ring is drawn in **white over a dark halo**, because it lands on the menu
bar — the system's own surface, routinely dark *and* routinely light, so nothing that is a single
colour is guaranteed to show up there, the accent included.

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
- **`NSVisualEffectView` behind the card.** This one *did* come back — see *The glass*.
  The original objection was right and is unchanged: a behind-window material takes its brightness
  from whatever is on the desktop. What was missing was the answer to it, which is a scrim thick
  enough that the material never sets the type's ground on its own, chosen by measurement rather
  than by eye.

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
