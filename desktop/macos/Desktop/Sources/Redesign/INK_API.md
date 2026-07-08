# Ink design-system API (for redesign page authors)

Read `InkTheme.swift`, `InkType.swift`, `InkComponents.swift` for the source. This is the cheat sheet.
**Rules:** light mode only, explicit `Ink.*` colors (never system-semantic), **monochrome ink accent —
NO purple**, semantic color only (`Ink.live` green, `Ink.warn` orange, `Ink.danger` red). Match the
mockup's exact copy, layout, and voice (short, conversational, first-person-from-omi).

## Colors — `Ink.*`
`canvas` (app bg), `soft` (bars/rails), `surface` (cards), `surface2` (recessed/hover),
`ink` (strong text), `body`, `muted` (AI text), `faint`, `hair`/`hair2` (borders),
`accent`/`accentStrong`/`accentInk`/`accentTint`, `live`/`warn`/`danger`/`warnText`/`sentText`.
`Ink.avatarFill(for: "Name")` → deterministic avatar color.

## Type — modifiers on Text/View
`.inkDisplay(30)` serif hero · `.inkWordmark(20)` · `.inkH1()` · `.inkH2()` · `.inkH3()` ·
`.inkBody()` · `.inkSmall()` (muted 13) · `.inkCaption()` (faint 12) · `.inkEyebrow()` (uppercase
tracked) · `.inkMonoCaption()`. Raw fonts: `InkFont.serif/sans/mono(size, weight)`.

## Components
- `InkButton(title:, systemImage: nil, kind: .primary/.plain/.ghost, size: .sm/.md/.lg, fullWidth: false) { action }`
- `InkCard(padding: 24, recessed: false, radius: 14) { content }`
- `NextCard { content }` — hero "do this next" card (subtle warm radial)
- `InkBadge(text:, kind: .draft/.needs/.hold/.sent)`
- `InkPill(text:, systemImage: nil)`, `MemberBadge(text:)`
- `InkToggle(isOn: $bool)` (green when on)
- `LiveDot(color:, size:)`, `PresenceChips(capturing:, listening:)`
- `BuddyRing(diameter: 60, dot: 8, color: Ink.ink)` — the 8-dot rotating omi ring
- `InkStat(number: "1,923", label: "Remembered", size: 40)` — big serif number / tiny label

## Spacing / radii
`InkSpace.s1..s8` (4,8,12,16,24,32,48,80). `InkRadius.card/tile/next/pill`.

## Standard page shell
```swift
ScrollView {
  VStack(alignment: .leading, spacing: 24) { /* content */ }
    .frame(maxWidth: 840, alignment: .leading)          // per-screen max width from mockup
    .frame(maxWidth: .infinity, alignment: .center)
    .padding(.horizontal, 48).padding(.vertical, 44)
}
.frame(maxWidth: .infinity, maxHeight: .infinity)
.background(Ink.canvas)
```
Two-pane pages (memory, conversations, settings): `HStack(spacing: 0)` with a left panel on
`Ink.soft` + a trailing `Ink.hair` 1px divider, and a right `Ink.canvas` content area.

## Live wiring
The page is constructed in `DesktopHomeView.PageContentView` where these are in scope:
`appState` (AppState), `viewModelContainer` (`.dashboardViewModel`, `.memoriesViewModel`,
`.tasksViewModel`, `.tasksStore`, `.appProvider`, `.chatProvider`, `.taskChatCoordinator`),
and `$selectedTabIndex` (Binding<Int>) for navigation. Take exactly the deps you need via `@ObservedObject`.
Read the existing page (e.g. `MainWindow/Pages/MemoriesPage.swift`) to learn real property/method names —
reuse the SAME view model; do not invent APIs. Navigation indices: Home 0, Conversations 1, Ask/Chat 2,
Memory 3, Tasks 4, Focus 5, Insights 6, Rewind 7, Apps 8, Settings 9, Permissions 10, More 20.
