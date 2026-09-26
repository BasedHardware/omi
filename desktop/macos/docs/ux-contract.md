# Desktop UX contract

The macOS app's interaction rules, and the one component that implements each. Read this before
adding a control, a page, a panel, a toast, a date, or a confirmation. If the component you need
does not exist, extend the shared one and update this file in the same PR; do not draw a local
variant.

Guard: `INV-UI-2` ([`product/invariants/desktop-ux-contract.md`](../../../product/invariants/desktop-ux-contract.md))
runs `.github/scripts/check_desktop_ux_contract.py`, a no-increase ratchet over the patterns below.

## 1. Leaving a surface

There are exactly two ways out, and they mean different things.

| The surface… | Control | Where | Component |
|---|---|---|---|
| **replaced** the page you were on (drill-in, detail, transcript, recap) | `‹ Destination` | leading edge of its header | `BackChip("Conversations")` |
| **floats over** the page (side panel, sheet, card, popup) | xmark | trailing edge of its header | `DismissButton` |

- A `BackChip` names where it goes ("‹ Summary", "‹ Rewind"). Plain "Back" only when the
  destination has no name a reader would recognise.
- Back returns to **where the reader came from**, not to a fixed page. Record the origin when you
  open the surface (see `ChatFirstNavigationModel.openDailyRecap`).
- Never an xmark on something that replaced the page, never a chevron on something floating.
- On the notch's black glass (floating-bar cards) the xmark is `NotchDismissButton` /
  `.notchDismissOverlay(accessibilityLabel:)`: the same glyph and "Dismiss (Esc)" tooltip as
  `DismissButton`, drawn in `NotchGlass` colors, 24 pt target. A card whose only exit is "go away"
  labels that button **Dismiss**, never Skip or Close.

### Escape

Esc removes the **innermost layer first**, one layer per press:

`modal → editor → panel/drill-in → selection/search → (page) → Chat → hide window`

- Every surface that shows a `BackChip` or `DismissButton` consumes Esc for the same action with
  `.onEscapeKey(priority: .content)` (or `.modal` for modals). Both controls advertise "(Esc)" in their
  tooltip, so an unhandled Esc is a lie the UI tells.
- Only after every layer on a page is gone does Esc fall through to the shell, which returns to Chat
  (the home surface), and then hides the window. Esc never switches between peer tabs.

## 2. Controls

| Need | Use | Not |
|---|---|---|
| Icon-only action | `OmiIconButton("trash", help: "Delete conversation", isDestructive: true)` | a hand-sized `Image` in a `.buttonStyle(.plain)` |
| Icon that opens a menu | `OmiIconMenu(systemName:help:) { … }` | `Menu` with `.borderlessButton` (shows a stray chevron, drops the fill) |
| Text action | `OmiButtonStyle(.primary / .secondary / .destructive, size: .regular / .compact)` | a filled `Capsule`/`RoundedRectangle` label, `.bordered`, `.borderedProminent` |
| Open / Install on an app card | `AppActionButton` (compact primary, one size on every card) | a second, smaller copy for small cards |
| Copy | `CopyButton(help:) { text }`; from a menu item, `OmiToastCenter.shared.copy(text, confirming:)` | `NSPasteboard.general.setString` |
| On/off setting | `OmiToggleStyle()` switch | `.checkbox` (checkboxes are only for picking items out of a list) |
| Selected / on state | neutral ink: `GlassShell.pillFill` for nav rows, `PageGlass.chipFill` / `SettingsSelection` for chosen options, `OmiToggleStyle` (ink track) for switches | an `Ink.accent` / system-blue fill; the accent is reserved for the one actionable link on a surface |
| Editing a long text setting in its own window (assistant prompts) | `AssistantPromptEditorView`: a draft, Cancel (Esc), Save (⌘↩), Reset to Default bottom-left behind `.shellConfirmation` | saving on every keystroke, a "Done" button |

- A control that changes **what Omi records** (the top bar's microphone, and any future capture
  switch with more than on/off) opens a menu naming the choices, marks the current one and says under
  each what it records (`ShellListeningModeMenu`). It never cycles through modes on click: one stray
  click must not start recording. A two-state capture toggle whose tooltip names the result is fine.
- Status dots on the top bar's capture icons: filled green = recording now, green ring with a hollow
  centre = armed (on, waiting for a call), hollow = off, filled red = blocked (`ShellStatusDot`).
  The glyph never changes with state or mode; the off-slash and mode badge are drawn on it.
- Icon buttons come in three diameters: 22 (inline), 28 (headers — default), 32 (top bar).
- `help` is required and doubles as the accessibility label. An icon without words is only a control
  for people who already know what it does.
- Click targets are `Button`s. `.onTapGesture` is for gestures on content (double-click to edit), not
  for controls: it gives no pointer feedback, no keyboard reach, and no accessibility role.

## 3. Destructive actions

One policy:

| The delete… | Pattern |
|---|---|
| can be deferred and restored (single memory, single task) | delete immediately, show `UndoToast` for `OmiFeedbackTiming.undo` |
| cannot be undone (conversation, account, bulk delete, reset, clear chat) | `.shellConfirmation(title:message:confirmTitle:)` naming the consequence |

- Never neither. Never both.
- The system `.alert` is not used in the main window: it dims the whole transparent window onto the
  wallpaper (see `ShellConfirmationDialog.swift`). Prompts that need a text field use
  `dismissableSheet`.
- An undo toast has no close button. Nothing in it means "destroy this sooner".
- Destructive icon buttons are `isDestructive: true` (red glyph); destructive text buttons are
  `OmiButtonStyle(.destructive)`. Sign Out is `.secondary`, not the page's primary button.

## 4. Feedback timing

`OmiFeedbackTiming`: confirmations 1.5 s, undo 5 s, informational cards 8 s (paused on hover).
Billing, trial and error cards that need an action persist until acted on.

The floating bar applies this through `FloatingBarNoticePolicy`: confirmations use
`FloatingBarNoticePolicy.confirmation`; every timed notch card pauses while the bar is hovered
(Interject lengthens informational cards to reading time, 4–14 s); `.trial` cards and any card sent
`isPersistent` stay until acted on, dismissed, or Esc. A new card picks a row there rather than
starting its own timer.

## 5. Dates, times, durations

Use `OmiDateFormat`; never a `DateFormatter.dateFormat` string (they ignore locale and the 24-hour
clock).

| Style | Example | Use |
|---|---|---|
| `time` | 10:43 AM | a row inside a day group |
| `dayHeader` | Today · Yesterday · Wednesday, Sep 23 · Sep 23, 2025 | group headers |
| `timestamp` | Yesterday, 10:43 AM | a date standing alone |
| `range` | Sep 23, 2026, 10:17 – 11:19 AM | a conversation's span |
| `relative` | 5 min ago | freshness, never the only date |
| `offset` | 3:38 · 1:02:05 | a position inside a recording |
| `duration` | 8s · 42m 10s · 1h 5m | a length |

A row inside a day group shows only the time. Group rows by the same date the row displays.

## 6. Speakers

`SpeakerLabelFormatter` is the only way to name a transcript speaker — in bubbles, participant lists
and every copied transcript. "You", then the assigned person's name, then "Speaker N" (1-based,
matching mobile). Raw diarization labels (`SPEAKER_00`) never reach the UI.

A transcript turn is drawn by `SpeakerBubbleView`, live or saved: name · time in the name row, the
user's bubble in `Ink.rowFillHover`, other speakers in `PageGlass.speakerTints`. A capture must not
change its look when it is saved.

Find inside a transcript is `TranscriptFindField` over `TranscriptSearchModel`: ⌘F opens it, ⌘G /
⇧⌘G (Return / ⇧Return) step with wraparound, "N of M" counts, and Esc (`.editing`) clears and closes
it before the pane's own Esc.

## 7. Typography, radius, spacing

- Type: `.scaledFont(size: OmiType.<rung>)` — micro 10, caption 11, body 13, subheading 15, heading 20,
  title 28, display 40. It applies Omi's typeface and the user's text-size setting; `.font(.system(size:))`
  applies neither.
- Radius: `OmiChrome` / `PageGlass` tokens. Spacing: `OmiSpacing`.
- Illustrations that draw miniature UI at a fixed scale (onboarding previews) are the exception; mark
  the line `// omi-ux-allow: <rule> -- <reason>`.

## 8. Words

| Say | Not |
|---|---|
| Omi | omi (in UI copy) |
| Tasks | Action items, To-dos |
| Memories | Facts |
| Apps | Plugins (Integrations is a section of Apps) |
| Conversations — recorded conversations | "conversation" for the chat thread; the chat is **Chat** |
| Rewind — screen history | Screen capture history |
| Try Again | Retry, Try again |
| Not Now | Later |

- Buttons and menu items: Title Case ("Copy Transcript", "Edit Title…"). Descriptions and tooltips:
  sentence case, no trailing period.
- "…" (one character) only when the action asks for more input before it acts. Never "...".
- A search placeholder says what it searches: "Search conversations", "Search memories".
- A count badge says what it counts ("388 segments"), or has a tooltip that does.

## 9. Page chrome

- Page actions sit trailing in the page's query toolbar: `[secondary…] [More] [primary]`. The add
  verb is **New** ("New Task", "New Memory").
- "More" is `PageMoreMenu(help:accessibilityIdentifier:) { … }`, never a popover and never a
  hand-built `Menu` (its label inherits the accent tint and renders blue).
- A repeated row control (a summary's "Add to Tasks", "Transcript") appears on hover or keyboard
  focus, in space the row already reserves, and is also a VoiceOver action on the row. A control
  that shows state (added, in flight, failed, linked) stays visible. See `ConversationActionItemRow`.
- A detail that replaces a list hides the list's search and filter chrome, or retargets it to the
  detail. Typing in a search field never closes the detail as a side effect.
- Truncated titles carry `.help(fullTitle)`.

## 10. Page states

A page body that has no rows yet is in one of three states, and each has one component
(`MainWindow/Components/GlassPageStates.swift`). Do not draw a local glyph-title-button stack.

| State | Component | Carries |
|---|---|---|
| First load | `GlassLoadingState(label: "Loading tasks…")` | one regular spinner, body text in `Ink.secondary` |
| Load failed | `GlassErrorState(title: "Couldn't Load Tasks", message:, retry:)` | `exclamationmark.triangle`, **Try Again** as `OmiButtonStyle(.secondary, size: .compact)` |
| Nothing here / nothing matches | `GlassEmptyState(systemImage:title:message:) { actions }` | glyph at `OmiType.title`, title at subheading semibold, body message |

- Every state picks a `placement`: `.page` fills the page body or a sidebar column, `.scrolling` sits
  inside a `ScrollView` and keeps `QueryShellLayout.minimumBodyHeight`, `.panel` takes its intrinsic
  size inside a self-sizing panel (`TransparentWindowStatusPanel`).
- Empty-state actions are `OmiButtonStyle(.secondary, size: .compact)` ("Clear Search", "Clear
  Filters"), or one `.primary` when the action is how the page gets its first row ("New Memory").
- Titles are Title Case: "No Matching Tasks", "Couldn't Load Memories".
- A skeleton (Apps' shimmer grid) may replace `GlassLoadingState` where it already previews the
  layout that will land. Do not add a new one.
- `ContentUnavailableView` is not used: it brings the system's type and grey, not the glass rungs.

**Spinners.** A page's first load is `GlassLoadingState`. Every other spinner — in a button, a row,
a toolbar, a field, a "Loading more…" footer — is `ProgressView().controlSize(.small)`. Never
`.scaleEffect` a `ProgressView`: it blurs the arcs and leaves the layout frame at the unscaled size
(rule `scaled-progress-view`). A spinner inside a button replaces or sits beside the label; the
button keeps its `OmiButtonStyle`.

## 11. Page headers

One rule for which pages carry a title, and one style for it.

| The page is… | Title | Example |
|---|---|---|
| reached from a top-bar pill (Chat, Brain: Activity/Conversations/Memories/Rewind/Brain Map, Tasks, Apps) | **none** — the lit pill and the search placeholder already name it | "Search memories" |
| a drill-in with no pill of its own (Goals, Daily recap, Settings) | `BackChip(origin)` leading, then `GlassPageHeader(title:subtitle:)`, page actions trailing | `‹ Tasks  Goals` |
| a pill page opened as a drill-in (Rewind from a task's evidence or a Chat citation) | no title; a `BackChip(origin)` leads its section row (`DrillInBack` environment value) | `‹ Tasks  Activity · Rewind …` |
| a window of its own (standalone Rewind) | the same `GlassPageHeader` style at the leading edge | `Rewind ⌘⌥R` |

- `GlassPageHeader`: title `OmiType.subheading` (15) semibold `Ink.primary`, optional subtitle
  `OmiType.caption` `Ink.secondary`, one line each. Content headlines inside a page (a recap's
  headline, a goal's title) sit below it at `OmiType.heading` and are not page titles.
- A drill-in with no pill lights **no** pill in the top bar (Goals), or the pill of the page it was
  opened from (Daily recap). It never claims Chat.
- Settings' sidebar title (20 pt bold) is not yet on this rule.

## 12. Keyboard

| Keys | Does | Where | Owner |
|---|---|---|---|
| ⌘F | focus the page's search field | every page with one: Chat (the query bar), Activity, Conversations, Memories, Tasks, Apps, Rewind, Brain Map, Settings | `FindCommandRouter` via `QuerySearchBar`, `OmiSearchField`, `RewindSearchBar`'s caller, the Settings sidebar |
| ⌘F | find in transcript | a conversation's transcript pane | the transcript's own find field, `FindCommandPriority.detail` (beats the page) |
| ⌘N | New Task / New Memory | Tasks, Memories | the page's primary add action |
| Esc | leave the innermost layer | everywhere | §1 |
| ⌘⌥R | open Rewind | anywhere | global hotkey |

- ⌘F is registered by the **shared field**, never by a page: a search field that uses
  `.focusesOnFind(_:)` gets it, in the window it is mounted in, only while it is mounted and not
  hidden. A find field on something opened over the page registers `.detail` and wins. When nothing
  claims ⌘F the key passes on, so a page whose search is hidden while a detail is open (Conversations)
  leaves ⌘F to the detail.
- A page's primary add action carries ⌘N (`.keyboardShortcut("n", modifiers: .command)`) and says so
  in its tooltip.

## 13. Motion

Three tokens, in `Theme/OmiMotion.swift`, all off under Reduce Motion:

| Token | Curve | For |
|---|---|---|
| `.quick` | ease-out 0.12 s | a control answering a press, hover or toggle; Esc and pill switches |
| `.standard` | ease-in-out 0.24 s | content changing in place: a row, a panel, a list, a scroll, an onboarding step |
| `.emphasized` | spring 0.35 / 0.86 | a surface arriving or leaving: a sheet, a card, a toast |

- Use `.omiAnimation(.standard, value:)` and `OmiMotion.perform(.quick) { … }`. A raw `.animation(…)`
  or `withAnimation(…)` ignores Reduce Motion.
- `InkMotion` is the first-run duration table (word reveal, finale glow, press). `InkReduceMotion` and
  `OmiMotion` read the same setting; `.standard` is `InkMotion.stepTransition`, so an onboarding step
  and a page change share one tempo. New code uses the tokens.
- Older call sites that pass their own curve to `OmiMotion.withGated` are gated and migrate to a
  token when touched.

## Adding to this contract

Changing a rule here is a product decision: update the component, migrate its callers in the same
PR, and add or tighten a rule in `check_desktop_ux_contract.py` so the old pattern cannot come back.
