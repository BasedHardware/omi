# B2 remaining surfaces — read-only inventory

Cut from `origin/main` (`37c2fb558b`). No app code in this branch. B1 catalog
and oracle live on `task/msd-ui-b1-chat`; this file reads **current `main` widgets**
against B1’s grammar (`omi.<surface>.<control>` plus optional qualifier;
`AddressKey.row(surface, opaqueId)` → `omi.<surface>.row.r{sha256}`) and against
`check_app_addressability.py`’s interactive-constructor vocabulary.

Interactive counts below are **source constructor calls** that the ratchet would
charge on a changed file (same scan as `debt()`), not runtime instances.

B1’s explicit `controls[]` catalog is journey-sized. Touching a file still
requires a namespaced key on **every** matching constructor in that file (or the
unkeyed baseline cannot grow). Dialog-only buttons are listed separately
because `checkSurface` uses `skipOffstage: true` / `findsOneWidget`.

Hot files (single-lane): `app/lib/pages/home/page.dart`, `app/lib/main.dart`,
`app/lib/pages/conversation_detail/page.dart`, `app/lib/pages/chat/page.dart`,
`app/lib/services/capture/capture_controller.dart`.

---

## Grammar used throughout

| Kind | Shape | Opaque id |
|---|---|---|
| Static | `omi.<surface>.<control>` | — |
| Qualified static | `omi.<surface>.<control>.<qualifier>` | e.g. `omi.tasks.toggle.done_today` |
| Dynamic row | `AddressKey.row('<surface>', opaqueId)` | **record id**, never list index, never date |

Do not hash `conversationIdx`. `ConversationListItem` already has
`ServerConversation.id` (`app/lib/backend/schema/conversation.dart`). Preview
rows on home pass `conversationIdx: index` in the 0–2 preview slice
(`home_content.dart` `HomeConversationsPreview`) — that index is not the
conversations-tab position and must not qualify the key.

Catalog `role` is only `button` / `textField` and `action` only `tap` /
`setText`. Flutter `Checkbox` / `Switch` / custom-painted toggles cannot be
declared in `controls[]` as B1’s schema stands.

---

## 1. home

**Owners:** `app/lib/pages/home/home_content.dart` (`HomeContentPage`, catalog
widget), `app/lib/widgets/bottom_nav_bar.dart` (tab row), shell
`app/lib/pages/home/page.dart` (**hot**). `main.dart` not required for tab
addressability.

**Reach:** IndexedStack tab 0 of `HomePage` (`_ensurePageInitialized` case 0).
Route row today: `kind: tab, tab: 0`, fixture `identity-empty`, `auth:
signed_in`, `profile: local_dev`, `ready_provider: null`.

**Shell tabs (one `InkWell` constructor, four runtime instances)** in
`_buildTab`:

| Runtime tab | Proposed key |
|---|---|
| 0 Home | `omi.home.tab_home` |
| 1 Conversations | `omi.home.tab_conversations` |
| 2 Tasks | `omi.home.tab_tasks` |
| 3 Apps | `omi.home.tab_apps` — **not in B1 catalog** |

Keys must be passed into `_buildTab(index)`; a single `key:` on the shared
constructor cannot be unique.

**On-stage interactives in `home_content.dart` (3 `GestureDetector`):** section
title + “View all” (`_buildSectionHeader`), daily-recap card
(`_buildSummaryCard`). Propose `omi.home.view_all_conversations`,
`omi.home.view_all_recaps`, `omi.home.view_all_mindmap`. Recap cards:
`AddressKey.row('home', summary.id)` once an id is confirmed on `DailySummary`.

**On-stage interactives in hot `page.dart` (3 `GestureDetector`):** body unfocus;
chat bar opens `ChatPage`; nested mic opens `ChatPage(autoStartVoice: true)`.
Propose `omi.home.chat_bar`, `omi.home.chat_voice`. `HomeRecordButton` is a
separate widget.

**Cannot key / assert the way B1 assumes**

1. **Four tabs, catalog has three.** `BottomNavBar` always builds Apps at index
   3. B1 `checkSurface` for home only knows home/conversations/tasks.
2. **Semantics already wrap the `InkWell`.** Identifier/label must live on the
   keyed `InkWell` (chat needed `ExcludeSemantics` on the child). Today
   `Semantics(button, selected, label: semanticLabel)` is the parent;
   putting `ValueKey` + identifier only on `Semantics` leaves the interactive
   constructor unkeyed for the ratchet.
3. **`HomePage` still arms `Future.delayed(2s)` in `_checkForAnnouncements`**
   (`page.dart` ~635) and does not cancel it on dispose. Tab prewarm uses
   `Timer` at 350/530/710/890ms, also uncancelled. On Flutter 3.44
   `invariantTester` this fails `_verifyInvariants` the same way chat did.
   The cancellable-timer fix is on `task/msd-ui-home-announcement-timer`,
   **not** on `main`.
4. **Conversation rows on the home tab.** `HomeConversationsPreview` builds
   `ConversationListItem` when `_nonDiscardedConversationCount >= 3`.
   IndexedStack keeps visited tabs mounted, so the same `conversation.id` can
   be onstage on home **and** conversations. `findsOneWidget` on
   `AddressKey.row('conversations', id)` then fails. `identity-empty` and
   `conversation-one` (one record) hide the preview, so the B1 fixture
   happens to dodge this; production does not.
5. **Chat bar is not `ChatPage`.** Cataloguing `omi.chat.input` on home would
   be the wrong surface. Home chat bar is a push to chat.
6. **`getDailySummaries` in `initState`** is a live HTTP call. Hermetic
   `identity-empty` still hits the network; recap controls appear while
   loading even when empty.

**Size:** 2 PRs. First: `bottom_nav_bar.dart` only (not hot) — three catalog
tabs, leave Apps uncatalogued or add it in the same PR. Second: hot
`page.dart` chat bar **after** the announcement timer is on `main`, plus
`home_content.dart` headers. Do not combine with `conversation_detail`.

---

## 2. conversations

**Owners:** `app/lib/pages/conversations/conversations_page.dart`
(`ConversationsPage`),
`app/lib/pages/conversations/widgets/conversation_list_item.dart`. Not hot.
Also: `recording_list_item.dart`, `capture_gap_list_item.dart`,
`date_list_item.dart`, `folder_tabs.dart`, `search_widget.dart`.

**Reach:** IndexedStack tab 1. `kind: tab, tab: 1`, fixture
`conversation-one` (`seeded-conv-j1-0001`), `signed_in`, `local_dev`,
`ready_provider: conversations`.

**Static (page chrome, 1 `IconButton` already keyed
`Key('conversation_map_button')` — not namespaced):** propose
`omi.conversations.map`. Search/folder chips live in sibling files.

**Dynamic rows** (`_ConversationListRowKind` in `conversations_page.dart`):

| Kind | Widget | Qualification |
|---|---|---|
| conversation | `ConversationListItem` | `AddressKey.row('conversations', conversation.id)` — B1 already pins the hash of `seeded-conv-j1-0001` |
| recording | `RecordingListItem` | `AddressKey.row('conversations', 'recording:' + recording.id)` so ids cannot collide with conversation ids |
| captureGap | `CaptureGapListItem` | `AddressKey.row('conversations', 'gap:' + eventId)` |
| dateHeader | `DateListItem` | not a row record; `omi.conversations.date.<iso>` only if the header is interactive |

The list already sets `ValueKey(row.conversation!.id)` on the **item widget**,
not on the inner `GestureDetector`. The ratchet requires the key on the
interactive constructor. Child keys do not cover the parent.

**Inner interactives on `ConversationListItem` (5):** outer `GestureDetector`
(open / selection toggle / paywall), selection `Checkbox`, two `TextButton`s
(merge UI). Checkbox cannot enter `controls[]` under B1’s role enum.

**Cannot key / assert as B1 assumes**

1. **`onTap` is not “open detail”.** In selection mode it toggles selection;
   if `conversation.isLocked` it routes to `UsagePage`. B1
   `accessibleTap(row) → visibleRoute == conversation_detail` is false in
   those states. Fixture must keep selection mode off and the seeded row
   unlocked.
2. **Duplicate onstage keys** with `HomeConversationsPreview` (see home #4).
3. **`conversationIdx` is analytics, not identity.** Preview passes a 0–2
   index. Hashing it would collide across days.
4. **Existing `Key('conversations-key')` / `Key('conversation_map_button')`
   fail `AddressKey.valid`.** Replacing them is a ratchet win; they are not
   catalog keys.
5. **Row label.** Catalog `label_en` is `Open Journey one seeded conversation`.
   The row has no such `Semantics.label` today; title comes from
   `structured.title`. Need an explicit semantics label (chat pattern), not
   the visible title, if the catalog string is kept.

**Size:** 1 PR for the seeded conversation `GestureDetector` + `// omi-route:
conversations`. A second PR if recordings/gaps/search are keyed. Independent
of hot files.

---

## 3. conversation_detail (hot)

**Owner:** `app/lib/pages/conversation_detail/page.dart`
(`ConversationDetailPage`). **Hot.** Widgets/summary sheets in the same
directory are pulled in; #14311 added summary-selection `InkWell`s in this
file.

**Reach:** push from a list row (`routeToPage` → `ConversationDetailPage`).
`kind: push`, fixture `conversation-one`, `signed_in`, `local_dev`,
`ready_provider: conversations`. `record_id` required (B1 already encodes
this).

**Scan:** 19 unkeyed interactives in `page.dart` alone (`IconButton` 5,
`GestureDetector` 7, `InkWell` 4, `TextButton` 2, `TextField` 1).

B1 catalog wants two:

| Control | Constructor | Proposed key | Visible / tooltip today |
|---|---|---|---|
| Back | `AppBar` `IconButton` (~689), `automaticallyImplyLeading: false` | `omi.conversation_detail.back` | no tooltip, no `Semantics.label` |
| Ask | `IconButton` tooltip `context.l10n.askAboutThisConversation` (~726) | `omi.conversation_detail.ask` | English **“Ask about this”** |

Star (~759) sets `onPressed: null` while `_isTogglingStarred`; share similarly
while `_isSharing`. B1 requires `isEnabled == Tristate.isTrue` for catalogued
controls — do not catalog those unless the fixture guarantees they stay
enabled.

**Cannot key / assert as B1 assumes**

1. **Catalog `label_en` “Ask about this conversation” ≠ l10n “Ask about this”**
   (`askAboutThisConversation` in `app_en.arb`). `checkSurface` asserts
   `data.label == item['label_en']`. Either the catalog string changes or a
   dedicated semantics label is added (chat’s `chatSendSemanticsLabel`
   pattern). Do not invent a match by changing production copy in this
   inventory.
2. **Back has no accessible name.** Empty semantics label fails the same
   assert against catalog `"Back"`.
3. **`isFromOnboarding: true` does not `Navigator.pop`.** It
   `pushAndRemoveUntil(HomePageWrapper)`. B1’s `handlePopRoute` / back-key
   path assumes pop. Fixture must use the list-push path.
4. **Changed-file ratchet:** any edit of this hot file for two keys still
   sees 19 unkeyed constructors. Baseline cannot grow. B2 must key all 19,
   extract widgets first, or only touch a new extracted file.
5. **Summary-tab `InkWell`s (#14311)** are mutually exclusive with transcript
   controls; not all 19 are onstage at once. `findsOneWidget` +
   `skipOffstage: true` will miss off-tab controls. Do not put every control
   in the B1 journey catalog.

**Size:** 2 PRs, last in the stack. (1) extract app-bar actions to a non-hot
file and key back/ask there. (2) remaining on-stage debt. Never pair with
`app/lib/pages/home/page.dart`.

---

## 4. memories

**Owners:** `app/lib/pages/memories/page.dart` (`MemoriesPage`), rows in
`app/lib/pages/memories/widgets/memory_item.dart`. Not hot. Opened from settings, not a tab.

**Reach:** push. `kind: push`, fixture `memories-empty`, `signed_in`,
`local_dev`, `ready_provider: memories`.

**Static:** `FloatingActionButton` `heroTag: 'memories_fab'` →
`omi.memories.create`. Tooltip is `createMemoryTooltip` = **“Create new
memory”**; B1 catalog `label_en` is **“Create memory”**. Same label mismatch
as Ask.

Other page.dart interactives (10): filter `TextButton`s / `ElevatedButton`s /
`IconButton`s — propose `omi.memories.filter_*` only for on-stage empty-state
buttons the journey actually taps.

**Dynamic:** `GestureDetector` in `memory_item.dart`. Qualify
`AddressKey.row('memories', memory.id)`.

**Cannot key / assert as B1 assumes**

1. **Label mismatch** catalog vs tooltip (above).
2. **`onTap` is null when `!_canEditMemory(memory)`.** B1
   `isEnabled == true` fails for locked/ledger rows. Empty fixture has no
   rows; creating via FAB opens a dialog (`showMemoryDialog`) — the FAB is
   the catalog control, not a row.
3. **FAB `backgroundColor: Colors.deepPurple`.** Off-brand (INV-UI-1); not an
   addressability blocker, but a B2 PR that touches this constructor will
   show up on the brand check.

**Size:** 1 PR (route + FAB + `memory_item` row key). Not hot.

---

## 5. tasks

**Owner:** `app/lib/pages/action_items/action_items_page.dart`
(`ActionItemsPage`). Not a named hot file; 31 interactive constructors in
one file.

**Reach:** IndexedStack tab 2. `kind: tab, tab: 2`, fixture `identity-empty`,
`signed_in`, `local_dev`, `ready_provider: tasks`.

**Static:** FAB `heroTag: 'action_items_fab'` → `omi.tasks.create`. Hidden
when `ActionItemsProvider.isSelectionMode` (`_buildFab` returns
`SizedBox.shrink()`). Category headers / menus: `omi.tasks.filter.*` as
qualified statics.

**Dynamic:** row `GestureDetector` (~1370) opens the edit sheet or toggles
selection. Qualify `AddressKey.row('tasks', item.id)`. Nested complete-toggle
`GestureDetector` (~1404) is a second interactive on the same row —
`omi.tasks.complete` cannot be unique; use
`AddressKey.row` is one key per widget, so the toggle needs
`omi.tasks.toggle.<hashed-id>` or a qualifier on a static control that is
illegal (not unique). Correct shape: a second hashed control is **not**
`AddressKey.row` (that helper always uses `.row.`). Propose
`omi.tasks.complete.r{sha256(item.id)}` via a sibling helper, or fold
complete into the row tap (behavior change — out of scope).

**Completion UI is not a Flutter `Checkbox`.** `_buildCheckbox` is a
`Container` / `CustomPaint`. The ratchet will not demand a key on it; the
wrapping `GestureDetector` will.

**Cannot key / assert as B1 assumes**

1. **FAB vanishes in selection mode.** Catalog `findsOneWidget` fails if
   selection is on. Fixture must not enable it.
2. **Most of the 31 constructors are sheets/dialogs** (`TextButton` cancel/
   confirm, `TextField`s in `_showCreateActionItemSheet`). Offstage until
   opened. Putting them in `controls[]` breaks `skipOffstage: true`.
3. **Catalog label “Create action item”** vs tooltip
   `createActionItemTooltip` “Create new action item” vs sheet title
   `createActionItem` “Create Action Item”.
4. **Changed-file blast radius:** keying the FAB in this file still counts
   all 31. Extract the FAB/row into a widget file, or key everything you
   leave in `action_items_page.dart`.

**Size:** 2 PRs. (1) extract FAB + row widget, catalog create. (2) row
complete-toggle grammar. Tab index is independent of home’s hot file if
`page.dart` is not touched.

---

## 6. settings

**Owner:** `app/lib/pages/settings/settings_drawer.dart` (`SettingsDrawer`).
Not hot. Opened as `showModalBottomSheet` (`SettingsDrawer.show`).

**Reach:** `kind: sheet`. Fixture `identity-empty`, `signed_in`, `local_dev`,
`ready_provider: null`.

**Static:**

| Control | Constructor | Proposed key |
|---|---|---|
| Done | `GestureDetector` → `Navigator.pop` (~818), visible only when `!_isSearching` | `omi.settings.done` |
| Profile | `_buildSettingsItem` → `GestureDetector` (~131) for `context.l10n.profile` (~496) | `omi.settings.profile` |
| Search | header `GestureDetector` / `TextFormField` | `omi.settings.search` |

`_buildSettingsItem` is **one** `GestureDetector` constructor for every row
(profile, notifications, plan, memories, devices, …). Keys must be a
parameter of the helper, same as `_buildTab`.

**Cannot key / assert as B1 assumes**

1. **Done is not onstage in search mode** (`ValueKey('normal-header')`
   swapped for cancel). Default `_isSearching == false` is fine; a test that
   focuses search first loses Done.
2. **Sheet vs page.** B1 pop path uses `OmiKeys.settingsDone` then
   `pump(1s)` and expects `find.byType(pageType)` gone. A modal sheet pop is
   not a `PageRoute`; `handlePopRoute` may dismiss it, but
   `visibleRoute` ownership lives in the B1 adapter (not on `main`).
3. **Memories is a settings row**, not the memories route. Tapping it pushes
   `MemoriesPage` without going through `navigate('memories')` until the
   adapter maps it.

**Size:** 1 PR. Parameterize `_buildSettingsItem`, catalog profile + done.
Not hot.

---

## 7. onboarding

**Owners:** `app/lib/pages/onboarding/wrapper.dart` (`OnboardingWrapper`, 12
`TabController` steps, auth = index 0),
`app/lib/pages/onboarding/auth.dart` (`AuthComponent`). Not hot.

**Reach:** `kind: onboarding`. Fixture `signed-out`, `auth: signed_out`,
`profile: local_dev`. If `AuthService.isSignedIn()` and `!forceAuthPage`,
`initState` **skips auth** and jumps to consent/name/home
(`wrapper.dart` ~104–118). The fixture must be actually signed out.

**Auth interactives (`auth.dart`, 6):**

| Button | Guard | Proposed key |
|---|---|---|
| Apple `ElevatedButton` | `Platform.isIOS \|\| Platform.isAndroid` | `omi.onboarding.apple` |
| Google `ElevatedButton` | always | `omi.onboarding.google` (B1 catalog) |
| Local-dev `OutlinedButton` | `provider.isLocalDevProfile` | `omi.onboarding.local_dev` |
| Privacy / terms | `TapGestureRecognizer` (not in ratchet vocabulary) | cannot be keyed by the current scanner |

**Wrapper (3):** skip/back `IconButton`s and a `GestureDetector`, mostly
**after** name page (`index > kNamePage`). Not onstage on auth.

**Cannot key / assert as B1 assumes**

1. **`dart:io` `Platform` is the host, not `debugDefaultTargetPlatformOverride`.**
   macOS `flutter test` has `Platform.isIOS == false` and
   `Platform.isAndroid == false`, so the Apple button is **absent** in the
   default B1 runner. Google is present. iOS simulator runs show both.
2. **Local-dev is the `local_dev` sign-in**, hardcoded English
   `'Sign in (local dev)'`, not l10n, not Google. Cataloguing only Google
   means a local_dev journey cannot sign in through the catalogued control
   without hitting real OAuth.
3. **Google’s accessible label is `signInWithGoogle`**, which should match
   catalog `"Sign in with Google"` if Semantics are added on the
   `ElevatedButton` itself (label is currently the `Text` child).
4. **12-step machine.** Consent, permissions, FindDevices, speech profile
   are later indexes. B1’s single `onboarding.google` control does not
   address them. After sign-in the wrapper **leaves** the auth page.
5. **B1 `buildShell` on the chat branch always returns `HomePage`**, so
   pending onboarding never pumps this widget until that adapter grows a
   signed-out shell. That is adapter work, not this surface’s widgets.

**Size:** 1 PR for auth (Google + local-dev). Later steps are a different
PR after signed-out `buildShell` exists. Not hot.

---

## 8. devices

**Owner:** `app/lib/pages/capture/connect.dart` (`ConnectDevicePage`). Not
hot. Embeds `FindDevicesPage`.

**Reach:** push. `kind: push`, fixture `identity-empty`, `signed_in`,
`local_dev`, `ready_provider: null`.

| Control | Constructor | Proposed key |
|---|---|---|
| Back | leading `GestureDetector` → `Navigator.pop` (~60) | `omi.devices.back` |
| Guide | bottom `GestureDetector` `_showConnectionGuide` (~141) | `omi.devices.guide` |
| Store | `TextButton` `key: Key('get_omi_device_button')` (~135) | `omi.devices.store` (existing key is not namespaced) |
| Gear | `IconButton` → `DeviceSettings` (~83) | `omi.devices.settings` |

**Dynamic:** scanned devices inside `FindDevicesPage` (not this file).
Qualify `AddressKey.row('devices', btId)` when that file is in the changed
set.

**Cannot key / assert as B1 assumes**

1. **Guide and store hide when `onboardingProvider.isConnected`**
   (`bottomNavigationBar` returns `SizedBox.shrink()`). A connected fixture
   loses both catalogued-adjacent controls. `identity-empty` should stay
   disconnected.
2. **Catalog `label_en` “Connection guide” ≠ l10n `connectionGuide`
   “Connection Guide”.** Same exact-label trap as Ask / Create.
3. **Back is a `GestureDetector`, not `IconButton`.** Fine for the ratchet
   (`GestureDetector`+`onTap`). No semantics label today vs catalog
   `"Back"`.
4. **`FindDevicesPage` interactives are not in `connect.dart`.** Changing
   only `connect.dart` does not force keys on the scanner list.

**Size:** 1 PR (back + guide + route). Not hot.

---

## Cross-cutting (every remaining surface)

| Issue | Code reason |
|---|---|
| SemanticsHandle teardown | Flutter 3.44 `invariantTester` runs before `addTearDown`; B1 `checkSurface` still does `ensureSemantics` + `addTearDown(dispose)`. Architect revision; builders must not edit the oracle. |
| Uncancelled home timers | `Future.delayed(2s)` announcement + prewarm `Timer`s on `main`. Any surface that pumps `HomePage` inherits this until the timer branch lands. |
| Catalog roles | Only `button`/`textField`. Checkboxes, switches, custom complete-circles cannot be journey-catalogued without a schema change. |
| `findsOneWidget` | IndexedStack + shared row widgets (home preview vs conversations) duplicate keys. |
| Label exact match | Several B1 `label_en` strings already disagree with `app_en.arb` tooltips. |
| Ratchet vs catalog size | Journey catalog can stay tiny; **changed-file** still bills every interactive constructor in the edited file. |

---

## Recommended order (hot files late, independent)

1. **settings** — sheet, parameterized helper, not hot.
2. **devices** — small `connect.dart`, not hot; needs disconnected fixture.
3. **memories** — FAB + `memory_item.dart`, not hot; label mismatch to resolve in catalog or semantics string.
4. **conversations** — row `GestureDetector` + seeded id; do **not** key home preview in the same PR if that would duplicate onstage keys.
5. **onboarding auth** — Google + local-dev; blocked on signed-out `buildShell` (B1 adapter), not on `main` widgets.
6. **tasks** — extract FAB/row out of the 31-constructor file first.
7. **home tabs** — `bottom_nav_bar.dart` only; wait for announcement-timer on `main` before pumping `HomePage` in a green surface test.
8. **conversation_detail** — last; extract app bar out of the hot file; fix Ask/Back labels; never in the same PR as `app/lib/pages/home/page.dart`.

**home/page.dart chat bar** sits with (7) or after it; it is the only home
control that requires the hot file.

Rough PR count: **10–12** if extraction is used to keep ratchet blast small;
**8** if each surface is willing to key every constructor in the files it
touches.
