# Mobile UX contract

The Flutter app's interaction rules, and the one primitive that implements each. Read this before
adding a page, a sheet, a control, a dialog, a toast, a date, a speaker name or a prompt. If the
primitive you need does not exist, extend the shared one under `lib/ui/` and update this file in
the same PR; do not draw a local variant.

Primitives live in `lib/ui/` (`omi_tokens.dart`, `components/`, `feedback/`, `format/`,
`prompts/`). This is the mobile twin of the macOS contract (`desktop/macos/.../ux-contract.md`,
INV-UI-2): same rules where the platforms agree, platform-correct where they do not.

Guard: `INV-UI-3` ([`product/invariants/mobile-ux-contract.md`](../../product/invariants/mobile-ux-contract.md))
runs `.github/scripts/check_mobile_ux_contract.py`, a per-file no-increase ratchet over the
hand-rolled patterns named below (rule ids in `code`). A deliberate exception ends its line with
`// omi-ux-allow: <rule> -- <reason>`. Run it on your files before you push:

```bash
python3 .github/scripts/check_mobile_ux_contract.py --report app/lib/pages/foo.dart
```

## 1. Leaving a surface

There are exactly two ways out, and they mean different things.

| The surface… | Control | Where | Primitive |
|---|---|---|---|
| **replaced** the page you were on (pushed page, detail, settings page) | back | leading edge of its app bar | `OmiBackButton()` (`OmiBackButton.circled()` when the header floats over content) |
| **floats over** the page (sheet, full-screen modal, viewer, tutorial) | close (X) | trailing edge of its header | `OmiCloseButton()`, plus swipe-down where the platform offers it |

- One glyph family: `OmiBackButton` draws the platform's back glyph (iOS chevron, Android arrow).
  Never `Icons.arrow_back*`, `FontAwesomeIcons.arrowLeft` / `chevronLeft` or a leading
  `Icons.chevron_left` (`raw-back-glyph`).
- Never an X on a pushed page, never a back chevron on something that floats.
- **System back and the iOS edge swipe always do what the on-screen control does.** A multi-step
  flow makes each step a real route (or a nested `Navigator`) so the swipe steps back one step;
  `PopScope(canPop: false)` that disables the swipe is a bug unless it guards unsaved input (§4).
- Push with `routeToPage(context, page)`, or `omiPageRoute(builder)` when you need a `Route`
  (`pushReplacement`). Never `PageRouteBuilder` for a push: it has no iOS back swipe
  (`page-route-builder`).
- **Chat is a normal pushed page everywhere** (D1): no `fullscreenDialog`, leading
  `OmiBackButton`, from every entry point (home chat bar, mic, deep link, app detail, quick
  action, "Ask Omi").
- **Conversation detail has no body-wide horizontal swipe to another conversation** (D2).
  Transcript / Summary tabs are swipeable where that does not fight a row's `Dismissible`. No
  prev/next controls replace it.
- **Android system back on a non-Home tab returns to the Home tab** before it exits the app (D6).
- Deep links and notification taps open inside the existing Home: pop to the first route, then push
  the destination (parent before child) — `HomeNavigation.openRoute(route)`
  (`lib/pages/home/home_navigation.dart`); a flow's final Done returns with
  `HomeNavigation.returnHome(context)`. Never push or `pushReplacement` a second `HomePageWrapper`.
  A missing target says so (`OmiFeedback.info`).

## 2. Sheets

- Every bottom sheet is `showOmiSheet(...)`, or `OmiSheetScaffold` around content that is already a
  widget. It owns the top radius (`OmiRadius.xl`), the 36×4 drag handle, the optional title row
  with a trailing `OmiCloseButton`, safe-area and keyboard insets, and `isScrollControlled`. Never
  a raw `showModalBottomSheet` (`raw-bottom-sheet`) and never a hand-drawn handle.
- A sheet that edits something is `showOmiEditSheet(...)` / `OmiEditSheet(isDirty:, ...)`, with
  explicit Save and Cancel. It owns the swipe-down itself, because the framework's sheet drag pops
  without consulting `PopScope`. Swipe-down, tap-outside, the close X and system back on a **dirty**
  sheet ask first (`confirmDiscardChanges`): `showOmiConfirm(title: l10n.discardChangesTitle, message:
  l10n.discardChangesMessage, confirmLabel: l10n.discard, cancelLabel: l10n.keepEditing,
  destructive: true)`. A clean sheet just closes.
- A progress sheet that cannot be cancelled blocks back with `PopScope` and pops with its **own**
  context, never the page's.

## 3. Controls

| Need | Use | Not |
|---|---|---|
| Text action | `OmiButton` — `.primary` (white fill, black label), `.secondary`, `.destructive`, `.tertiary`; size regular (48) or compact (36 visual, 44 target); `isLoading` | `ElevatedButton.styleFrom(...)` with a local colour, height or radius |
| Icon-only action | `OmiIconButton(icon, label: …)` — `label` is required and is the tooltip and the screen-reader name | a bare `GestureDetector`/`InkWell` around an `Icon`, an `IconButton` with no tooltip |
| Header circle button | `OmiIconButton` filled-circle style (`HeaderCircleButton` is an alias) | a 36 pt circle with a 36 pt target |
| On/off setting | `OmiSwitch` in an `OmiSettingsRow` | a checkbox, a purple/green/indigo switch |
| Settings list | `OmiSettingsGroup` of `OmiSettingsRow`s under an `OmiSectionHeader` | a hand-built row per page |
| Search | `OmiSearchField(placeholder: l10n.searchConversations)` | a styled `TextField` per page |
| Loading indicator | `OmiSpinner` (small / regular / large) | `CircularProgressIndicator(` with a local colour and stroke (`raw-spinner`) |

- Every tappable control is at least **44×44 pt** (48 dp on Android is fine), including the label
  next to a checkbox (`OmiCheckboxRow`).
- A button label is a verb in Title Case ("Save", "Delete Task", "Try Again"). A button that is
  busy keeps its size and shows a spinner in place of or beside its label.
- A disabled control looks disabled. A Send that cannot send is not white.
- The accent is white/neutral (INV-UI-1, no purple). Colour is for state (danger, success), not
  decoration.

## 4. Destructive actions

One policy, and never neither:

| The delete… | Pattern |
|---|---|
| can be deferred and restored — a **memory**, a **task**, a goal | delete at once, `OmiFeedback.undo(...)` for 5 s; **no** confirmation dialog |
| is a **conversation** | confirm (`showOmiConfirmWithOptOut`, "Don't ask again" allowed) **and** always an Undo toast backed by the provider's pending-delete window, which is at least `OmiFeedbackTiming.undo` (D5) |
| cannot be undone — a local recording file, forget/unpair device, clear chat, sign out, account deletion, bulk delete | `showOmiConfirm(..., destructive: true)` every time; **never** "Don't ask again" |

- The confirm button is a verb naming the action — "Delete", "Forget Device", "Clear Chat",
  "Sign Out" — never "OK", "Confirm" or "Yes". The message names the consequence.
- `destructive: true` makes the button red (Material) or `isDestructiveAction` (iOS), and makes
  Cancel the default choice.
- An undo toast has no close button. Nothing in it means "destroy this sooner"; a replaced or
  swiped-away undo commits.
- "Don't ask again" only where an Undo backs the action.
- A bulk delete (several conversations) confirms every time and, when the provider can defer it,
  also offers Undo.
- A row's long-press opens `showOmiRowMenu(context, title:, actions: [OmiMenuAction(...)])` — the
  same menu shape on conversations, memories and tasks (Open first, Delete last and destructive);
  multi-select is a "Select" entry in that menu, not the long-press itself.
- Swipe-to-delete follows the same table: `confirmDismiss` shows the confirm for things that cannot
  be undone; restorable things dismiss and show Undo. A swipe means the same thing on every row of a
  list.

## 5. Dialogs

`lib/ui/feedback/omi_dialogs.dart` is the only dialog system (`raw-dialog` counts
`AlertDialog(` / `CupertinoAlertDialog(`):

| Need | Call |
|---|---|
| a question with two answers | `await showOmiConfirm(context, title:, message:, confirmLabel:, destructive:)` → `bool` |
| the same with "Don't ask again" (only when Undo backs it, §4) | `await showOmiConfirmWithOptOut(...)` → `OmiConfirmResult(confirmed, dontAskAgain)` |
| information with one button | `await showOmiAlert(context, title:, message:, okLabel:)` |
| a widget for `showDialog(builder:)` | `OmiAlertDialog(title:, message:, content:, actions: [OmiDialogAction(...)])` |

- Adaptive: `CupertinoAlertDialog` with `CupertinoDialogAction`s on iOS, `AlertDialog` elsewhere.
  Cancel is always present (localized) and always closes. Titles are Title Case questions
  ("Delete Conversation?").
- Legacy entry points (`ConfirmationDialog`, `OmiConfirmDialog`, `AppDialog`) are thin
  adapters over the same widget; they accept `destructive`. New code calls the functions above.

## 6. Feedback (toasts)

`OmiFeedback` (`lib/ui/feedback/omi_feedback.dart`) is the only toast (`raw-snackbar` counts
`SnackBar(`). One at a time; a new one replaces the current.

| Kind | Call | Stays | For |
|---|---|---|---|
| confirm | `OmiFeedback.confirm(context, msg)` | 1.5 s | the reader just did it ("Saved", "Copied") |
| info | `OmiFeedback.info(context, msg)` | 4 s | something the reader did not directly cause |
| error | `OmiFeedback.error(context, msg, actionLabel: l10n.tryAgain, onAction:)` | 8 s, with close | a failure; offer Try Again when retrying can help |
| undo | `final undone = await OmiFeedback.undo(context, msg, onUndo:)` | 5 s, no close | deferred deletes (§4); commit when it resolves `false` |
| progress | `OmiFeedback.progress(context, msg)` | until replaced (≤ 1 min) | ongoing work, replaced by its result |

- Neutral surface with a small coloured status icon; never a red or green slab (white on red fails
  contrast). Floating, above the home tab bar and chat bar.
- Code without a `BuildContext` uses `AppSnackbar` (same toasts on the global navigator).
- An informational toast has no "OK" action.

## 7. Copying

`await OmiClipboard.copy(context, text, what: l10n.transcript)` (`raw-clipboard` counts
`Clipboard.setData(`). Empty text is not copied and nothing is shown. It confirms with "Copied" /
"Transcript copied" — except on Android 13+, where the system chip already confirms. A copy made by
something else (a selection toolbar) calls `OmiClipboard.confirmCopied(context)`.

## 8. Dates, times, durations

`OmiDateFormat.of(context)` (locale and the device's 24-hour setting) and `OmiDuration`. Never a
pattern string: `DateFormat('h:mm a')`, `dateTimeFormat('MMM d', …)` (`date-pattern`) force English
order and a 12-hour clock on everyone.

| Style | en_US example | Use |
|---|---|---|
| `time` | 10:43 AM (10:43 on a 24-hour clock or locale) | a row inside a day group |
| `dayHeader` | Today · Yesterday · Wed, Sep 23 · Wed, Sep 23, 2025 | group headers (today gets a header too) |
| `date` | Sep 23, 2026 | a date standing alone |
| `dateTime` | Sep 23, 2026 10:43 AM | an absolute moment (details, exports) |
| `timestamp` | 10:43 AM · Yesterday at 10:43 AM · Sep 21 10:43 AM | a moment in a feed or chat |
| `timeRange` | 10:17 – 11:19 AM | a span; across days both ends carry the date |
| `OmiDuration.offset` | 0:05 · 3:38 · 1:02:05 | a position in a recording, time remaining |
| `OmiDuration.compact` | 8s · 4m 10s · 42m · 1h 5m | a length — the list row and the detail page use the same one |
| `OmiDuration.long` | 12 mins 34 secs | screen-reader labels and sentences |

A row inside a day group shows only the time. Group rows by the same date the row displays.

## 9. Speakers

`SpeakerNames.forSegments(segments, people:, l10n:)` (`lib/ui/format/speaker_names.dart`) is the
only way to name a transcript speaker — bubbles, the edit-segment and tag-speaker sheets,
participant lists, the speaker filter and every copied, shared or exported transcript
(`TranscriptSegment.segmentsAsString` uses it).

- The owner is **You** in the app; exports use the owner's given name, else "You".
- A speaker assigned to a person shows the person's name (live people list first).
- Omi's own speaker is **Omi**, never "Speaker 100".
- Everyone else is **Speaker N**, N dense per conversation (1, 2, 3… in order of first
  appearance, skipping the owner and Omi). Never a raw id, never a gap. Naming a person does not
  renumber the others. `TranscriptSegment.getDisplaySpeakerId` returns the same N.
- The speaker filter is "Filter by speaker" (`l10n.filterBySpeaker`), never the loudspeaker string
  `phoneSpeaker`.

## 10. Tokens

`lib/ui/omi_tokens.dart`, dark only. Where you touch code, replace literals with tokens
(`color-literal`, `font-size-literal`, `radius-literal`); new code has none.

- **Colour** `OmiColors`: `surface0` (page black), `surface1/2/3` (card / elevated / pressed),
  `border`, `textPrimary` / `textSecondary` / `textTertiary` (tertiary no darker than ~#8E8E93, ≥ 4.5:1
  on surface1), `accent` (white — INV-UI-1) / `onAccent`, `success`, `warning`, `danger`,
  `dangerSurface`. `AppStyles` and `ResponsiveHelper` palettes are legacy.
- **Type** `OmiType`: an iOS-like ramp (11 / 13 / 15 / 17 / 20 / 24 / 28 / 34) as `TextStyle`s.
- **Radius** `OmiRadius`: sm 8 · md 12 · lg 16 · xl 24 · pill. **Spacing** `OmiSpacing`: 4 · 8 · 12 · 16 · 20 · 24 · 32.
- **Motion** `OmiMotion`: quick 150 ms (a control answering a press), standard 250 ms (content
  changing in place), emphasized 400 ms (a surface arriving or leaving). Read durations through
  `OmiMotion.of(context)`, which is zero under Reduce Motion.
- **Haptics** `OmiHaptics`: `selection()` for tabs, segments and navigation, `light()` for
  toggles, `medium()` for record start/stop and completions, `success()` / `error()` for outcomes.
- The theme (`buildOmiTheme()`) sets the app bar (black, centred title, white icons), the spinner,
  snackbar, dialog and switch colours, so an unstyled widget already looks right.

## 11. Words

All user-facing text is `context.l10n.<key>`, added with `scripts/l10n.py` with real translations
for every locale (`hardcoded-text` counts `Text('…')` with letters in it).

| Say | Not |
|---|---|
| **Omi** | omi, OMI |
| **Task(s)** (D3) | Action Item(s), To-Do(s) |
| **Memories** | Facts |
| **Try Again** | Retry, Try again |
| **Not Now** (postpone) | Later, Maybe Later, No |
| **Sign Out**, **Forget Device**, **Clear Chat**, **Delete** (the verb for the action) | OK, Confirm, Yes |

- **Title Case** for buttons, menu items, tabs, navigation titles, dialog titles ("Delete Task?",
  "Copy Transcript"). **Sentence case** for descriptions, messages, placeholders, tooltips and
  toasts ("Task deleted").
- "…" (one character) for ongoing states ("Saving…") and an action that asks for more input; never
  "..." (`three-dot-ellipsis`).
- A search placeholder says what it searches, without an ellipsis: "Search conversations".
- A count says what it counts ("5 conversations · 3 tasks") or has a semantic label; never a bare
  number next to an icon.
- Emoji are not punctuation in titles or buttons.

## 12. Settings

- Everyday settings live in top-level Settings (D4): data & privacy, export/import, transcription,
  conversation display and timeout, payment methods, phone calls. Developer Settings keeps only
  developer tools (webhooks, MCP, API keys, firmware channels, experiments).
- A setting applies when it changes. A page with a Save button is an editor (§2): it guards unsaved
  edits.
- Language is chosen in one place.

## 13. Page states

| State | Primitive | Carries |
|---|---|---|
| first load | `OmiLoadingState` (or a skeleton that previews the layout, with a timeout) | one `OmiSpinner` |
| load failed | `OmiErrorState(message:, onRetry:)` | the cause in words and **Try Again** |
| nothing here / nothing matches | `OmiEmptyState(icon:, title:, message:, action:)` (`glyph: FaIcon(…)` instead of `icon:` where the screen's glyphs are FontAwesome) | Title Case title, one action when it is how the page gets its first row |

- Pull-to-refresh refreshes what the page shows. A failed load always offers Try Again.

## 14. Prompts

`PromptQueue.instance.enqueue(id, PromptPriority.x, show: (context) => …)`
(`lib/ui/prompts/prompt_queue.dart`) presents every startup and background prompt: upgrade alert,
announcements, changelog, device tutorial, firmware notice, plan sheet, review request, Bluetooth
guidance.

- One modal prompt at a time, by priority (critical › high › normal › low), deduplicated by id.
- **Never while recording, on a call or during a firmware update.** The home shell sets
  `PromptQueue.instance.blocked` and calls `pump()` when that changes.
- A prompt is marked seen only on an explicit answer (a button or the close X), never on a stray
  barrier tap. Postpone is **Not Now**, and it postpones; it does not silence forever.

## 15. Permissions

- Ask with a pre-prompt that says why — `OmiPermissionRow` (`lib/ui/components/omi_permission_row.dart`):
  title, one-sentence reason, and one action for its state (Allow → the system prompt; Allowed;
  Open Settings) — then the system prompt. Continue never fires a system prompt by itself.
- Permanently denied → the row says so and offers **Open Settings** (`l10n.openSettings`).
- Ask when a feature needs the permission ("Always" location only when a feature requires it).

## 16. Accessibility

- Every icon-only control has a label (`OmiIconButton` requires one); decorative icons are excluded
  from semantics.
- Targets ≥ 44 pt (§3).
- Text scales: containers of text use **min-height**, not fixed height; test at 200 %.
- Contrast: body text ≥ 4.5:1 on its surface; no grey darker than `textTertiary` for text.
- Motion honours Reduce Motion (`OmiMotion.of`); live status changes (toasts, recording state) are
  announced (`OmiFeedback` marks its text as a live region).

## Adding to this contract

Changing a rule here is a product decision: update the primitive, migrate its callers in the same PR,
and add or tighten a rule in `check_mobile_ux_contract.py` (with a failing case in
`test_check_mobile_ux_contract.py`) so the old pattern cannot come back.
