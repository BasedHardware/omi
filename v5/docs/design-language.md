# Omi design language (v5)

One design language for every v5 surface. It is expressed in code by
`react-native/src/design/` (tokens, `OmiThemeProvider`, primitives); this page
explains the rules those values encode. When a rule and a screenshot disagree,
fix the screen.

**Lineage.** v5 replaces the shipping Swift macOS app and the Flutter mobile
app (ADR-011). Both already share a recognisable Omi look, recorded in
`desktop/macos/Desktop/Sources/Theme/` + `desktop/macos/docs/ux-contract.md`
and `app/lib/ui/omi_tokens.dart` + `app/docs/ux-contract.md`. v5 keeps that
look's principles and reconciles the two into one system with two densities.
It does not copy either app pixel for pixel.

## Principles

1. **Quiet and monochrome.** Hierarchy comes from ink weight (transparency
   steps of one ink), not from hue. No purple, glows or decorative gradients
   (INV-UI-1).
2. **Colour means state.** Only errors (`danger`), live/recording
   (`live`), attention (`warning`) and the one actionable link on a surface
   (`link`) use colour. Selection is ink, never accent.
3. **Content before chrome.** Pages reached from the main navigation have no
   title; the navigation already says where you are. No filler hero text.
4. **Lists are rows, not slabs.** Rows are clear at rest, get a fill on hover,
   and an ink-weighted fill plus a separator when selected. Group headers are
   quiet labels (`OmiSectionLabel`), never filled uppercase bars.
5. **One way to do each job.** A button is `OmiButton`, a filter is `OmiChip`,
   a list row is `OmiRow`, a whole-surface state is `OmiPageState`. Restyle
   the primitive, not the call site.
6. **Every appearance is first-class.** Desktop ships light (the shipping Mac
   window is light glass) and dark; mobile ships dark and light. A screen is
   not done until both render correctly (check with the visual audit).

## Tokens (`src/design/tokens.ts`)

| Group | Roles |
| --- | --- |
| Surfaces | `canvas` (opaque page), `surface` (cards, sheets), `surfaceRaised` (controls on a surface), `surfacePressed` |
| Ink | `ink`, `inkSecondary` (safe on glass), `inkTertiary` (opaque surfaces only), `inkDisabled`, `onInk` |
| Edges and fills | `separator` (between blocks), `hairline` (control outlines), `fill` (hover / card on glass), `fillPressed`, `fillSelected` |
| State | `link`, `danger`, `live`, `warning`, `dangerSurface`, `liveSurface`, `scrim` |
| Type roles | `caption`, `footnote`, `subhead`, `body`, `headline`, `title`, `display`. Desktop is denser (body 14) than mobile (body 17); style by role, never by number. |
| Space | 2, 4, 8, 12, 16, 20, 24, 32, 40 |
| Radius | badge 6, chip 11, row 12, field 13, sheet 20, card/panel 22, pill (capsule) |
| Size | desktop control 32 / compact 26; mobile control 48 / compact 36 with 44-pt hit targets |
| Motion | quick 120 ms (press, hover), standard 240 ms (in-place change), emphasized 350 ms (arrive / leave); zero under Reduce Motion |
| Layout | reading column 640, list column 720, chat column 680 |

Light ink is near-black (`rgb(22,23,21)`), dark ink is near-white
(`rgb(244,245,242)`). Secondary ink stays at or above ~0.7 alpha so it is
readable on glass; tertiary is for opaque surfaces only.

## Components

- **Buttons** are capsules. Primary is an ink fill with `onInk` label (black
  on light, white on dark), never an accent fill. Secondary is a hairline
  outline. Destructive is `danger` fill. Press feedback is colour only (no
  scale bounce); busy keeps the size and swaps in a spinner.
- **Icon buttons** are circular and always carry a `label` (tooltip and
  screen-reader name).
- **Chips / segments** use `fillSelected` + separator when active and are
  clear otherwise.
- **Rows** (`OmiRow`): optional leading icon tile, `headline` title,
  `subhead` subtitle, `caption` meta. All rows in one list use the same shape,
  whether they hold a conversation, a task or a memory.
- **Page states** (`OmiPageState`): loading is one small spinner plus a label;
  error names what failed ("Couldn't Load Conversations") and offers
  **Try Again**; empty is a glyph, a Title Case title, one sentence and at most
  one action. Failed reads never claim to be empty.
- **Chat.** Your message sits in a quiet bubble on the right (`surfaceRaised`
  on mobile, `fillSelected` ink fill on desktop glass), at most 75% wide.
  Omi answers as flat, full-width text with no bubble and no avatar; the Omi
  mark appears only while Omi is thinking or writing. Day separators replace
  per-message times; actions sit in a small bar under a reply (visible on the
  newest, on hover or focus elsewhere). On desktop the transcript draws on
  the window glass in the chat column, never in a panel of its own. The
  composer is a capsule; send is an ink circle when enabled and Stop while
  Omi answers. Details: `docs/chat-ux.md`.
- **Toggles** look like switches (track + knob), ink track when on.
- **Glass (desktop).** Panels share one corner radius (22) and one soft
  shadow; cards inside a panel have no shadow. Tertiary ink is not allowed on
  glass.

## Words

Product names are "Omi", "Tasks" (never "Action items") and "Memories".
Title Case for buttons, menus, tabs and titles; sentence case for
descriptions, messages and toasts; one-character ellipsis "…"; "Try Again",
"Not Now". The add verb is "New".

## Checking your work

Run the visual audit (`bun run visual:audit` from `v5/`, see
`docs/verification.md`) before and after a UI change and read every pair in
`gallery.html` in both appearances. Screenshots are never committed.
