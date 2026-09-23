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
| Copy | `CopyButton(help:) { text }`; from a menu item, `OmiToastCenter.shared.copy(text, confirming:)` | `NSPasteboard.general.setString` |
| On/off setting | `OmiToggleStyle()` switch | `.checkbox` (checkboxes are only for picking items out of a list) |

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
- "More" is a `Menu`, never a popover.
- A detail that replaces a list hides the list's search and filter chrome, or retargets it to the
  detail. Typing in a search field never closes the detail as a side effect.
- Truncated titles carry `.help(fullTitle)`.

## Adding to this contract

Changing a rule here is a product decision: update the component, migrate its callers in the same
PR, and add or tighten a rule in `check_desktop_ux_contract.py` so the old pattern cannot come back.
