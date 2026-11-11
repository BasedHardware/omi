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
tertiary       labelColor @ 0.68                a glance word — opaque surfaces only, never on glass
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

### The ladder is three rungs on an opaque surface and **two on glass**

> **On glass, `tertiary` is not available. Promote it to `secondary`.**

This is the single most consequential rule in this document, and it is arithmetic rather than taste.
A translucent panel's ground can only be as dark as the *faintest* rung anyone sets on it, and the
ground is what "glassmorphic" means. So whichever rung sits at the bottom decides how see-through
every panel in the app is:

| ladder on glass | ground over black | passthrough | bottom rung there |
|---|---|---|---|
| three rungs | 205.5/255 | 17.0% | `tertiary` 4.56:1 |
| **two rungs** | **154.1/255** | **34.8%** | **`secondary` 4.58:1** |

Twice the desktop, at the same 4.5:1. Everything else — the material, the corner, the shadow — is
identical between those two rows; the ladder is the whole difference. Three separate retunes of the
material and the scrim were shipped before this was understood, each moving the panel by a few levels
out of 255 and each correctly reported as no change at all.

**Every surface in the app is glass except the menu bar popover**, which is AppKit's own `NSPopover`
chrome (see *The glass*). So the popover keeps all three rungs and everything else gets two.

What this costs: a run that was `tertiary` because it is a *sentence* was on the wrong rung anyway
and is simply corrected. A run that was genuinely a glance word — the status on a permission row, a
card's `app · time` caption, a section header — loses a step of hierarchy and has to earn its
recession from size, weight, tracking or position instead. That is the price of the panel, paid
deliberately.

And it really is drop-or-nothing. To clear AA on the shipped ground `tertiary` would have to darken
to **0.796**, which is `secondary`'s 0.80 to within a hundredth — a third rung that measures as the
second is the same colour twice with an extra token to keep true. Asserted, not asserted-looking:
`InkGlassTests.testTheBottomRungIsWhatPaysForTheGlass` measures the rescue alpha and fails if it ever
comes apart from `secondary`.

Held four ways:

- `InkGlassTests.testTheLadderClearsWCAGAAOnTheGlass…` — `primary` and `secondary` clear AA on the
  real ground, in both system appearances, over both extreme desktops.
- `InkGlassTests.testTheBottomRungIsWhatPaysForTheGlass` — `secondary` clears AA by less than 0.30
  (the ground is *on* its floor, not above it) **and `tertiary` fails there** (so the ground cannot
  drift back up to where a third rung would fit).
- `InkGlassTests.testTheTimelinesHourLabelsClearWCAGAAOnTheGlass` — the timeline's hour marks, which
  are drawn in AppKit and hand an `NSColor` straight to an `NSAttributedString`, measured on the
  colour `RewindTrackView.hourLabelAttributes` actually carries.
- `InkGlassTests.testNoGlassSurfaceSetsTypeOnTheBottomRung` — a labelled **static tripwire** over
  `Sources/ContextApp`. Its default is "this file is glass", and every exception is declared per file
  *and per spelling*, as an exact count rather than a ceiling.

**The migration debt is paid.** Six glass files once carried nineteen `Ink.tertiary` call sites at
~3.6:1; all six are at zero and the debt list is gone rather than kept at its old numbers — a stale
allowance is an allowance to put the call sites back, which is precisely what a ceiling-shaped ratchet
had been licensing. The declarations that remain are the popover (not glass) and two *fills*.

**The rule is "no faint type on glass", not "no `Ink.tertiary` on glass".** The token is one spelling
of it. The sweep also looks for the system's own faint label steps and SwiftUI's hierarchical styles,
because the way this was actually broken never touched the token: the timeline set its hour labels in
`NSColor.tertiaryLabelColor` — 1.70:1 on the shipped ground, about half as legible as the rung the
rule bans. On that ground `secondaryLabelColor` is 2.98:1, `tertiaryLabelColor` 1.70:1 and
`quaternaryLabelColor` 1.21:1, all over a solid black desktop.

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
| `tertiary` (`labelColor` @ 0.68) | 5.2:1 | 6.3:1 |

That table is the **opaque** surface — the popover, and any sheet drawn on `surface` alone. On glass
the ground is not `surface` and the readings are different; see *The glass*.

`secondary` is held to AAA (7:1) over `surface` because it is the only step that carries whole
sentences — and on glass it is the *bottom* rung, where its alpha is set by the worst ground rather
than the best: over a solid black desktop it measures 4.58:1, eight hundredths above AA. That is what
pins it from both sides. It cannot be thinned (the glass falls under AA) and it must not be thickened
(contrast the rung does not need is opacity the panel paid for, which is what an opaque-looking panel
is made of).

`tertiary` is the glance step on the opaque surface only. It cannot go darker either — at 0.69 it is
7.8 L\* from `secondary` on a Dark sheet, under the 8 L\* the rungs are held apart by. On `surface`
the ladder is still three visible steps: L\* 15.6 / 35.0 / 45.7 in Light, 88.0 / 74.2 / 65.7 in Dark.

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

There is **no exemption left in that sweep, and there must not be a new one**. One used to be listed
here and in the test: `AccentChoice.system`, the default in the Appearance pane, resolved to
`controlAccentColor` and tinted the whole Settings window with it, pinned by a
`SettingsTests.testSystemAccentIsTheUsersOwn`. `AccentChoice` and that test have both since been
deleted, and what survived them was a whole-file exemption with nothing to exempt — the worst state
for one to be in, because it reads as settled and stays green while licensing the *next*
`Color(nsColor: .controlAccentColor)` added to that file. Skipping a file is a hole; if an exception
is ever genuinely needed, the shape to copy is `InkGlassTests`'s per-spelling exact counts.

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

**The material is `.hudWindow`, and the number that decides that is the material's own opacity — not
the scrim.** This corrects an argument that stood here for two releases and is the reason two separate
attempts to make these panels see-through changed nothing anybody could perceive.

Every candidate was re-sampled on this machine (macOS 26, `.behindWindow`, `.active`, pinned `.aqua`)
over solid black, mid-grey and white full-screen backdrops, **at scrim zero** — each material at its
most transparent, which is the honest way to rank them:

| material | ground over black | passthrough | material | ground over black | passthrough |
|---|---|---|---|---|---|
| `hudWindow` | 136.2/255 | **41.2%** | `menu` | 188.4/255 | 18.8% |
| `fullScreenUI` | 136.2/255 | 41.2% | `titlebar` | 208.0/255 | 15.4% |
| `popover` | 163.7/255 | 29.4% | `headerView` | 212.9/255 | 16.2% |
| `selection` | 193.4/255 | 8.5% | `sidebar` / `underWindowBackground` | 213.9/255 | 7.9% |

`sheet`, `windowBackground` and `contentBackground` are opaque in `.aqua`.

**The old ranking asked the wrong question.** It held the ground fixed at 209.1/255 and asked which
material passed the most desktop *there*, concluding that a pure white tint was optimal and
`.headerView` won. But 209.1 is not the legibility floor — it is well above it. The floor is the
darkest ground on which the *faintest rung the panel carries* still clears WCAG AA over a solid black
desktop. `.headerView` is ~84% opaque white on its own, so its ground *bottoms out at 212.9/255*: it
cannot reach any plausible floor at any scrim, and the scrim is worth four points of ground in total.
That is exactly what was observed — dropping the scrim 0.36 → 0.10 moved the onboarding card from
228.0/255 to 217.0/255, eleven levels out of 255, and was reported as no change at all.

`.hudWindow` is 59% opaque at a near-white tint (232/255), so it *can* be scrimmed a long way down.
Measured on the real material over a real banded desktop (`.aqua`, `.behindWindow`, `.active`,
sampled out of a `screencapture`):

| material / scrim | ground over black | passthrough | bottom rung there |
|---|---|---|---|
| `headerView` @ 0.10 (shipped, three-rung) | 217.0/255 | 14.5% | `tertiary` 4.74:1 |
| `hudWindow` @ 0.56 (shipped, three-rung) | 205.5/255 | 17.0% | `tertiary` 4.56:1 |
| `hudWindow` @ 0.115 | 151.2/255 | 35.9% | `secondary` 4.48:1 — **under AA** |
| **`hudWindow` @ 0.14** | **154.1/255** | **34.8%** | **`secondary` 4.58:1** |
| `hudWindow` @ 0.00 — *the material's ceiling* | 136.2/255 | 41.2% | `secondary` 3.96:1 ✗ |

The pin, not the machine, decides: re-run under a Light system and under a Dark one, the sampled
composites are identical.

**The scrim is `surface` @ 0.14**, flat and full-bleed, painted over the material and under the
content. Its alpha is **not comparable across materials and must never be read as a translucency
figure** — it is a fraction of whatever the material left. Reading this number as "how see-through the
panel is" is what let three retunes ship without changing the picture. The quantities to reason about
are the **ground** and the **passthrough**. The ladder on the shipped ground, measured through the
real material over the two extreme desktops, in both system appearances:

| step | black desktop | white desktop |
|---|---|---|
| `primary` | 6.34:1 | 13.78:1 |
| **`secondary`** (the bottom rung on glass) | **4.58:1** | 7.46:1 |
| ~~`tertiary`~~ — *not available on glass* | 3.61:1 ✗ | 5.09:1 |

**The floor is the bottom rung, and the ground sits on it rather than above it.** Three points of
ground thinner and `secondary` is under AA. `InkGlassTests` holds this from three sides — it fails if
the ground goes under the floor, if the rung ever clears AA by more than 0.30, *and* if `tertiary`
ever clears AA there (which would mean the ground had drifted back up to a three-rung panel).

### What the glass is, and what it still cannot be

**A light panel over a dark desktop cannot show all of it, and no amount of tuning changes that.**
Dark type needs a light ground; the ground is pinned at the bottom rung's floor; so the whole range
the panel occupies across every desktop that can exist is **154.1…242.8 of 255** — an 89-level span,
against the 43 levels a three-rung panel had.

The remaining moves are exhausted, and each was checked rather than assumed:

- **The material.** `.hudWindow` and `.fullScreenUI` are the thinnest macOS ships in `.aqua`; at scrim
  zero they bottom out at 136.2/255, and the shipped ground is 18 levels above that. There is at most
  6% more passthrough available in the whole material catalogue and it is below the contrast floor.
- **A third rung.** Gone, and it is what bought the current panel. Going further means spending
  `secondary` too, which leaves one type colour and no ladder at all.
- **Dark glass** — what "glassmorphic" usually means over a dark desktop — is **worse** under the same
  rule, because the binding case inverts: light type on a dark ground is worst over a *white* desktop,
  and a two-rung dark ladder caps out well under the 34.8% a light one reaches.

**Everything left that reads as glass costs no contrast**, so it is all spent: the broad ambient
shadow, and a **specular top edge** — white @ 0.50, one point tall, top edge only, clipped by the
panel's corner. A bright line where a light source above would catch the panel is the difference
between a rectangle of pale grey and an object with a face on it, and because it *brightens* the
ground it can only help dark type. Both are worth more now than they were, because a ground at 154
has real desktop moving under it for them to sit on. Both are hidden under Reduce Transparency along
with the material: there is no glass there for light to catch.

A scrim only *under the copy* would be the speech bubble's grey slab drawn a second time, so it is
full-bleed. `InkGlassTests` asserts the ladder on a two-layer model of this ground — checked against
the real composite to about 3/255 — and `InkGlass.measuredMaterialOpacity` / `measuredMaterialTint`
record the samples the model needs, because a material's opacity is not published and cannot be
derived. **Re-take those samples rather than adjusting them**: the pair that stood here before were
`.headerView` at 0.800/pure-white from macOS 15.5, and re-measured it is 0.835 — which is why the
documented passthrough (18.0%) never matched the panel anyone was looking at (14.5%).
`GlassRenderHarness` (`CONTEXT_GLASS_RENDER=1`) renders the card over a dark synthetic desktop and
samples its own output, which is the check that could not have passed while the panel was a slab.

**The corner is 22 pt**, continuous, and it is one value for every panel: a 56 pt bar and a 760 pt
timeline rounded differently read as two products. **The edge is `labelColor` @ 0.06** — much fainter
than `hairline` (0.22), which is the outline of a *control*; a panel that needs a drawn border is a
panel whose brightness and shadow are not doing their job.

**The shadow is broad and faint**: 34 pt radius, 0.24 opacity, 10 pt down. Almost all of the floating
quality comes from this, and the wrong shadow is not a missing one but a tight dark one. It is cast
from a `shadowPath` and masked so it never falls *under* the panel — behind an 18%-transparent surface
a filled blurred rounded rect is very much visible, and more so now than at the old scrim: the thinner
the ground, the more of the panel's identity the shadow and the edge are carrying. A floating panel's window is therefore larger than
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
row-copy role, then the status word in **`secondary`** at the status-label role: `Granted` / `Open` /
`Checking` / `Action required`. `secondary` and not the glance rung because this card is on glass —
see *The ladder is three rungs on an opaque surface and two on glass*; the status still reads as
subordinate to the sentence beside it, which is `primary`. The checkbox and the two gaps take ~116 pt
out of the row before the sentence starts, which is why the list column is wider than the reading one.

**Menu bar (`native: true`) — a menu item.** See the next section. No fill at rest, no border, no
tracking, no drawn checkbox.

The whole row is tappable on both surfaces and requests the capability.

## Menu bar popover

**This surface is a menu, so it is drawn like one.** It sits beside every other menu bar extra on the
machine; a filled row capsule and letter-spaced type are the single clearest tell that a panel was
drawn by a website rather than by macOS. None of the `InkType` roles appear here.

**It is also the one surface in the app that is not `InkGlassView`** — an `NSPopover` brings its own
frosted chrome from a window this process does not own — which is why it is the one surface that
keeps all three rungs of the ladder. Every `tertiary` below is on that basis.

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
- **`accent` on repair links only.** A repair link is the press that fixes a line the popover has
  just said is broken: "Connect" on the connector line, "Sign in" on the account line. There is at
  most one per line and they are the only presses on this surface that are not command rows. "Sign
  out" stays a quiet trailing link in `tertiary` — it is a link on a line that is already settled,
  and a settled line asking for attention is the popover crying wolf.
- **The account line always has a way back in.** It carried "Sign out" and nothing to undo it, which
  made signing out a one-way door: onboarding does not run twice, there is no Dock icon, no window
  menu and no account pane, so a signed-out user had no route to an account anywhere in the product.
  Signed out, the trailing link is "Sign in"; pressing it discloses two provider commands
  ("Continue with Google", "Continue with Apple") on the shared left edge and turns the link into
  "Not now", so the disclosure is not a one-way door either. While the browser round trip is open
  the line reads "Waiting for your browser…" and offers *nothing* — a second press cannot start a
  second sign-in. `AccountPresentation` owns every one of those branches as a value and
  `AccountPresentationTests` holds them; the view has no judgement of its own.

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
