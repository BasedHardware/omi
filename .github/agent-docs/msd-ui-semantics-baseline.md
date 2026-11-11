# Semantics baseline — what a screen reader is handed today

Cut from `origin/main` (`591d701323`) on `task/msd-ui-semantics-baseline`. No app
code. This is a hermetic `flutter_test` walk of the semantics tree, not a
VoiceOver or TalkBack pass.

B1 says semantics work must improve real screen-reader behaviour, not just add
identifiers. B2 is about to stamp `omi.<surface>.<control>` across nine
surfaces. The numbers below are the measurement that requirement did not have.

Harness: `app/test/support/semantics_tree.dart`. Inventory:
`app/test/widgets/semantics_baseline_test.dart`.

## How this was measured

`WidgetTester.ensureSemantics()` then a depth-first walk of
`pipelineOwner.semanticsOwner.rootSemanticsNode`. Each node records label,
value, hint, tooltip, **identifier**, the flags that matter (button, header,
textField, enabled, focusable, image, link, selected), and the actions the
brief named (tap / longPress / increase / decrease / scroll*).

**Unnamed control** = an activate/edit node (button, textField, link, slider,
checkbox/toggle, tap, longPress, increase, decrease) whose label, value, hint,
and tooltip are all empty. `Semantics.identifier` is **not** counted as a
name — Flutter does not expose it to users.

**Unnamed scroll** = a scrollable viewport with no name and no activate
action. Reported separately; it is usually the list, not an icon-only button.

**Unhelpful** = an activate node whose spoken name is empty, a bare number, an
`IconData(U+…)` debug string, or the addressability grammar `omi.(token)+`.

Host is macOS `flutter_test`. `Platform.isIOS` / `Platform.isAndroid` are
false, so Apple sign-in is not built.

## Flutter already separates the machine id from the spoken name

Use it. Do not invent a second channel.

[`SemanticsProperties.identifier`](https://github.com/flutter/flutter/blob/3.44.5/packages/flutter/lib/src/semantics/semantics.dart)
(Flutter 3.44.5, `semantics.dart` ~1993–2014):

> Provides an identifier for the semantics node in native accessibility
> hierarchy.
>
> **This value is not exposed to the users of the app.**
>
> It's usually used for UI testing with tools that work by querying the
> native accessibility, like UIAutomator, XCUITest, or Appium. It can be
> matched with `CommonFinders.bySemanticsIdentifier`.
>
> On Android, this is used for `AccessibilityNodeInfo.setViewIdResourceName`
> (`resource-id`). On iOS, `UIAccessibilityElement.accessibilityIdentifier`.
> On web, `flt-semantics-identifier`.

`Key` / `ValueKey` is a **widget-tree** identity for `find.byKey`. It is also
not spoken. `Semantics.label` (and tooltip, for `IconButton`) is the human
string.

**Rule for B2:** `omi.<surface>.<control>` and `AddressKey.row(...)` go on
`Key` and/or `Semantics.identifier`. The spoken name is `context.l10n.*` (or
an existing `semanticLabel` / `tooltip`). Never assign the grammar to
`label`, `hint`, or `tooltip`. If Flutter already has a visible `Text` child,
do not also copy the machine id onto `Semantics.label` — the child already
names the control, and a wrapper label would concatenate or replace it.

`HeaderCircleButton` and `BottomNavBar._buildTab` already do this split:
l10n `semanticLabel` on `Semantics.label`, widget `key` left for the
address. Chat's `ChatJumpToLatestButton` / `ChatFollowUpChip` same pattern.
That is the habit to copy, not a new one to design.

## Where the grammar would read badly if it leaked into a label

These are the B2 catalog keys against a control that is icon-only or whose
visible text is a different English phrase. A VoiceOver user would hear the
dotted identifier instead of a word.

| Grammar | Surface | Why it reads badly |
|---|---|---|
| `omi.home.tab_home` (and `_conversations`, `_tasks`, `_apps`) | home tabs | Tabs are icon-only. Today they announce l10n `Home` / `Conversations` / `Tasks` / `Apps`. Replacing that with `omi.home.tab_home` is a regression. |
| `omi.settings.done` | settings Done | Visible text is l10n `Done`. `omi.settings.done` is not English. |
| `omi.settings.search` | settings search icon | Icon-only `GestureDetector` wrapping `Icons.search`. No tooltip today. The defect is the missing name, not the missing key — a leaked grammar would name it `omi.settings.search`. |
| `omi.devices.back` | ConnectDevicePage back **and** DeviceSettings leading | `FaIcon(chevronLeft)` / `IconButton` with no tooltip. Would announce `omi.devices.back`. |
| `omi.devices.settings` | ConnectDevicePage gear | `IconButton` + `FaIcon(gear)`, no tooltip. |
| `omi.conversation_detail.back` | detail AppBar back | `IconButton` + `FaIcon(arrowLeft)`, no tooltip, no `Semantics.label`. Found unnamed in this dump. |
| `omi.conversation_detail.ask` | detail Ask | Today announces l10n **“Ask about this”**. Catalog `label_en` was “Ask about this conversation”. Putting the key in the label would say `omi.conversation_detail.ask`. Putting the catalog English on `Semantics.label` would **desync** from arb. |
| `omi.conversations.row.r{sha256}` | conversation rows | A hash is not a title. The row already speaks the emoji+title (`🧠` / `Standup notes`). |
| `omi.memories` graph / management keys | memories header | `ElevatedButton` wrapping `FaIcon` brain / sliders, no `semanticLabel`. Grammar-as-label would replace silence with `omi.memories.graph`. |

Existing `Key('get_omi_device_button')` and `Key('chat_followup_chip')` are
also machine ids. They are not currently copied into `Semantics.label`. Keep
it that way when they are renamed to `omi.*`.

## Per-surface dump

Inventory order. Counts are activate-controls unless noted. **This is not an
accessibility pass** — see limits below.

### 1. home

**Pumped:** `BottomNavBar` + `HomeConversationsPreview` (one fixture row).

**Not pumped:** `HomePage` (uncancelled Timers, Firebase). `HomeContentPage`
(`getDailySummaries` HTTP in `initState`). Section headers / “View all” live
in `HomeContentPage` and were not in this slice.

| | |
|---|---|
| Interactive | 4 |
| Unnamed controls | **0** |
| Unnamed scroll | 0 |
| Unhelpful | 0 |
| Headers | 0 |
| Duplicate labels | 0 |

The four tabs announce `Home`, `Conversations`, `Tasks`, `Apps`, are buttons,
and the selected tab is flagged `selected`. That is the one surface that
already meets B1’s “icon-only control has a name” bar.

The preview `ConversationListItem` did **not** appear as an interactive node
in this pump (8 nodes total, all tab-related). The same widget on the
conversations surface did. Do not read “0 unnamed” as “home rows are named”.

### 2. conversations

**Pumped:** `SearchWidget` + `FolderTabs` + `ConversationListItem` +
`EmptyConversationsWidget`.

**Not pumped:** `ConversationsPage` (CaptureProvider, LocalRecordingsProvider,
folder/goals refresh).

| | |
|---|---|
| Interactive | 7 |
| Unnamed controls | **1** |
| Unnamed scroll | 0 |
| Unhelpful | 0 |
| Headers | 0 |

Named: search field (`Search conversations...`), Speaker (tooltip
`phoneSpeaker`), New Folder (`HeaderCircleButton` + l10n), All, Starred, the
row title/emoji.

**Unnamed:** calendar `IconButton` wrapping `FaIcon(calendarDays)` — **no
tooltip** (`search_widget.dart` ~167). Speaker next to it has a tooltip; the
calendar does not.

Date headers from the full page were not in this slice, so “no headers” is
not a claim about the conversations tab.

### 3. conversation_detail (hot)

**Pumped:** `ConversationDetailPage` with a cached fixture conversation
(review prompt suppressed via prefs `has_first_conversation`).

| | |
|---|---|
| Interactive | 12 |
| Unnamed controls | **7** |
| Unnamed scroll | 0 |
| Unhelpful | 0 |
| Headers | 0 |

Named: **Ask about this** (l10n tooltip on the Ask `IconButton`), Summary
pill, title field `Weekly recap`, No Folder, Private.

**Unnamed (icon-only AppBar / chrome, matching the inventory):** Back
(`FaIcon(arrowLeft)`, no tooltip), star, share, search, overflow, plus a
body-level tap absorber. This is the founding illustration of B1’s fear:
B2 can key `omi.conversation_detail.back` while VoiceOver still hears
nothing — or, if someone “fixes” it by stuffing the key into `label`, hears
`omi.conversation_detail.back`.

### 4. memories

**Pumped:** `MemoriesPage` after an injected empty fetch.

| | |
|---|---|
| Interactive | 7 |
| Unnamed controls | **4** |
| Unnamed scroll | 1 |
| Unhelpful | 0 |
| Headers | 1 (`Memories` AppBar title) |

Named: search field, `Create new memory`.

**Unnamed:** graph `ElevatedButton`+`FaIcon(brain)`, management
`ElevatedButton`+`FaIcon(sliders)`, AppBar back (default leading, white
`iconTheme`, no tooltip override), and one further tap control on the empty
state. The header buttons are the B2 temptation listed above.

### 5. tasks

**Pumped:** `ActionItemsPage` empty list (stubbed fetch, integrations already
“loaded”).

| | |
|---|---|
| Interactive | 2 |
| Unnamed controls | **1** |
| Unnamed scroll | 0 |
| Unhelpful | 0 |
| Headers | 0 |

Named: `Create Action Item`.

**Unnamed:** page-body `GestureDetector(onTap: () {})` — a hit-test absorber
with no name (`action_items_page.dart` ~527). Goals `HeaderCircleButton`
(`addGoal`) is not on stage when there are no goals.

### 6. settings

**Pumped:** `SettingsDrawer` (disconnected device, so Device Settings row
hidden).

| | |
|---|---|
| Interactive | 15 |
| Unnamed controls | **1** |
| Unnamed scroll | 1 |
| Unhelpful | 0 |
| Headers | 0 |

Named from visible `Text`: Done, Profile, Notifications, Plan & Usage,
Offline Sync, Integrations, Permissions, Feedback / Bug, Help Center,
Developer Settings, What's New, Referral Program, Sign Out. GestureDetector
rows inherit the title. That is acceptable **until** someone wraps them in
`Semantics(label: 'omi.settings.profile')`.

**Unnamed:** header search `GestureDetector` + `Icons.search`, no tooltip
(`settings_drawer.dart` ~803).

### 7. onboarding

**Pumped:** `AuthComponent` with listeners off, `isLocalDevProfile` false.

**Not on stage:** Sign in with Apple (`Platform.isIOS \|\| Platform.isAndroid`
is false on this host). Local-dev button (production-family stub). 12-step
machine after sign-in.

| | |
|---|---|
| Interactive | 3 |
| Unnamed controls | **0** |
| Unhelpful | 0 |
| Headers | 0 |

Named: **Sign in with Google** (visible `Text`), Privacy Policy and Terms of
Use as `link`+tap from `RichText` recognizers. Google does not need a
duplicate `Semantics.label` of the catalog string; the child already names
it. Apple, when built on a device, has the same visible-text pattern.

### 8. devices

**Pumped:** `DeviceSettings`.

**Not pumped:** `ConnectDevicePage` — `FindDevicesPage.scanDevices` requires
`ServiceManager.instance`. Connect chrome (back chevron, gear without
tooltip, store `TextButton`, guide `GestureDetector`) was **not** in this
tree. Store/guide would be named from l10n if that page is pumped on a
device; back/gear would not.

| | |
|---|---|
| Interactive | 12 |
| Unnamed controls | **1** |
| Unnamed scroll | 1 |
| Unhelpful | 0 |
| Headers | 1 (`Device Settings`) |

Named: Double Tap, Device Name, Device ID, Firmware, Offline Sync,
Diagnostics, Hardware Revision, Model Number, Manufacturer, Unpair Device.

**Unnamed:** AppBar `IconButton` + `FaIcon(chevronLeft)`, no tooltip
(`device_settings.dart` ~944). Same class of defect as ConnectDevicePage
back.

### 9. chat

**Pumped:** `ChatJumpToLatestButton` + `ChatFollowUpChip`.

**Not pumped:** `ChatPage` — waits on architect B1 teardown (`#14315`).

| | |
|---|---|
| Interactive | 2 |
| Unnamed controls | **0** |
| Unhelpful | 0 |

Both already set `Semantics.label` from a human string (`Latest`, the
follow-up question) and keep `Key` separate. The composer, mic, and message
list were not measured.

## Totals from reachable pumps

Activate-controls with **no accessible name:** 1 + 7 + 4 + 1 + 1 + 1 = **15**
across conversations, conversation_detail, memories, tasks, settings,
devices. Home tabs and the pumped onboarding/chat widgets added **0**.

**Unhelpful grammar / icon-data / bare-number names: 0.** The app is not yet
leaking `omi.*` into labels. B2 is the change that could start that leak.

**Headers** are almost unused (`Memories`, `Device Settings` AppBar titles).
Home section titles, conversation date rows, and settings groups are not
`Semantics(header: true)`. Reading order in the dump is Flutter's child
visit order, not VoiceOver rotor order.

**Images:** no `isImage` node without a name in these pumps. The Summary pill
on conversation_detail is flagged `image` **and** has a name.

## What this tree cannot see

Do not file these numbers as an accessibility certification.

- **Real focus / swipe order.** The walk is tree order. VoiceOver/TalkBack
  focus, keyboard focus, and `traversalSortNode` /
  `traversalParentIdentifier` behaviour are not exercised.
- **Gesture conflicts.** A `GestureDetector` that wins against the screen
  reader’s swipe, or a scroll view that eats the rotor, does not show up as
  a count.
- **Announcement timing.** Polite vs assertive live regions, `setState`
  chatter, snackbars vs `SemanticsService.announce`, delayed labels after
  async load — the dump is one frame.
- **Rotor / headings navigation.** One or two `isHeader` flags is not “the
  rotor works”.
- **Platform embedding.** Android `resource-id` vs iOS
  `accessibilityIdentifier` vs TalkBack grouping of merged nodes.
- **Offstage / another route.** `skipOffstage: true` is how B1’s catalog
  asserts; this dump is whatever was on stage after one pump.
- **Full pages not pumped** (HomePage, ConversationsPage, ChatPage,
  ConnectDevicePage). Their unnamed counts are **lower bounds**.

## Recommendation for B2 (do not add this to the contract in this turn)

**Yes — each B2 surface PR needs an accessibility acceptance criterion**,
and it should assert the split Flutter already gives, not a second labelling
scheme.

Per surface, after the keys land, a widget test that reuses
`dumpSemanticsTree` should assert:

1. **No grammar in the spoken name.** For every activate-control,
   `accessibleName` does not match `^omi(\.[a-z0-9_]+)+$`. That is the
   agent-only-label tripwire. Cheap, hermetic, fails closed on the actual
   defect B1 described.
2. **Identifier is allowed to be the grammar.** If a node has
   `identifier: omi.…`, that is success, not a failure. `Key` the same.
3. **Icon-only controls that this baseline marked unnamed** (calendar,
   settings search, detail Back/star/share/search/overflow, memories
   graph/sliders, devices back, connect back/gear when that page is
   pumped) must **gain an l10n `tooltip` / `Semantics.label`**, not an
   `omi.*` label, in the same PR that keys them — or the PR leaves them
   unnamed and the criterion records the count so it cannot grow.
4. **Unnamed activate-control count on that surface does not increase**
   versus the table above. A ratchet on the count, not a mandate to reach
   zero in the keying PR, unless the keyed control is icon-only (then it
   must be named, because keying it is the moment a bad label gets baked
   in).

What it should **not** assert: that `find.byKey(omi.…)` exists *and* that
`find.bySemanticsLabel(omi.…)` exists. That is how the agent-only habit
starts. Catalog `label_en` is documentation for the journey; the spoken
string is the arb string.

The architect owns whether that criterion lives next to `checkSurface` or
as a sibling test. This turn does not add it.
