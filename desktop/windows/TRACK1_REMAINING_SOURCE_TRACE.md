# Track 1 — Remaining Gap Source Trace

Branch: `perf/windows-kg-worker`  
Date: 2026-06-19  
Traced by: automated source search

---

## 1. Chat Citation / Source Cards

| Field | Value |
|-------|-------|
| macOS source | `ChatProvider.swift:360–451` (`Citation` model), `CitationCardView.swift` (`CitationCardsView`), `ChatMessagesView.swift:244` (`onCitationTap`) |
| Windows source | `useChat.ts:279` (drops `done:` line), `ChatMessages.tsx` (no citation rendering) |
| Backend source | `chat.py:326–334` — streams `done: <base64 JSON>`, payload is `ResponseMessage` with `memories: List[MessageConversation]` (up to 5 items, each has `id`, `structured.title`, `structured.emoji`, `created_at`) |
| Data exists today | **YES** — backend sends cited conversation IDs and titles in every `done:` event |
| UI exists today | **NO** — Windows discards `done:` entirely at `useChat.ts:279` |
| Client-only or needs backend | **Client-only** — data is already in the SSE stream |
| Exact blocker | `parseChunk()` in `useChat.ts` returns `null` for `done:` lines; no citation state in `ChatMsg` |
| Recommended action | Parse `done:` base64 → JSON, attach `memories` to last assistant message, render `CitationCards` below bubble |
| Risk | Low |
| Effort | Small (2 files: `useChat.ts` + `ChatMessages.tsx`) |
| **Classification** | **IMPLEMENT_NOW** |

---

## 2. Overlay Drag / Resize / Agent Pills

Already resolved in Batch 7:
- Drag handle: ✅ `OverlayApp.tsx` `DragHandle` component with `-webkit-app-region: drag`
- Resize grip: ✅ `ResizeGrip` SVG at bottom-right; `window.ts` `resizable: true` + width locked
- Agent pill: ✅ `OmiPill` with green status dot

**Classification: DONE**

---

## 3. Settings — Integrations Tab

| Field | Value |
|-------|-------|
| macOS source | `SettingsSidebar.swift` has integrations section; `SettingsPage.swift` |
| Windows source | `IntegrationsTab.tsx` — fully implemented (Sticky Notes import + Google OAuth). NOT registered in `tabs.ts` or `Settings.tsx` |
| Data exists today | YES — `window.omi.readStickyNotes()`, `window.omi.googleConnect()` all wired |
| UI exists today | YES (built, just not registered) |
| Exact blocker | `tabs.ts` `SettingsTabId` union does not include `'integrations'`; `Settings.tsx` `TAB_COMPONENTS` map doesn't include it |
| Recommended action | Add `'integrations'` to `SettingsTabId`, add row to `SETTINGS_TABS`, add to `TAB_COMPONENTS` in `Settings.tsx` |
| Risk | Very low |
| Effort | Trivial (3-line change) |
| **Classification** | **IMPLEMENT_NOW** |

---

## 4. Settings — Shortcuts Tab

| Field | Value |
|-------|-------|
| macOS source | `SettingsSidebar.swift` section `.shortcuts` — overlay shortcut + PTT shortcut |
| Windows source | `preferences.ts` has `overlayShortcut?: string`; `App.tsx:126` pushes it to `window.omiOverlay.setAccelerator()`; `ShortcutSetupStep` in onboarding captures it |
| Data exists today | YES — `overlayShortcut` is stored in preferences and wired to main |
| UI exists today | NO — not exposed in Settings at all |
| Exact blocker | No `ShortcutsTab` component; not in `SETTINGS_TABS` |
| Recommended action | Create `ShortcutsTab.tsx` with a dropdown/select for common overlay accelerators; add to `tabs.ts` and `Settings.tsx` |
| Risk | Low |
| Effort | Small (1 new file + 3 registration changes) |
| **Classification** | **IMPLEMENT_NOW** |

---

## 5. Settings — Notifications Tab

| Field | Value |
|-------|-------|
| macOS source | `SettingsSidebar.swift` `.notifications` section: task/focus/insight/memory/daily-summary notification toggles |
| Windows source | `NotificationsTab.tsx` — **IMPLEMENTED** |
| **What was added** | (1) **Proactive insights** toggle + interval dropdown + notification style (Omi / Windows) + denylist textarea. (2) **Recording saved** Windows notification toggle. (3) **Focus analysis** toggle + interval dropdown + sustained-distraction alert toggle + **Screenshot vision analysis** sub-toggle (sends 1-2 Rewind frames to Gemini Vision; falls back to text-OCR). All wired to `preferences.ts` with live `onPreferencesChange` subscriptions. |
| **Classification** | **DONE** |

---

## 6. Settings — Devices Tab (BLE)

| Field | Value |
|-------|-------|
| macOS source | `DeviceType.swift` — device types, battery, manufacturer info; iOS `OmiBleManager.swift` (CBUUID `2A19` = battery level); Android `OmiBleManager.kt` (`00002a19-...`) |
| Windows source | `DevicesTab.tsx` — **IMPLEMENTED (Web Bluetooth connect + battery)** |
| **What was added** | (1) Full connect flow: `requestDevice({ acceptAllDevices:true, optionalServices:['battery_service','device_information'] })` → `gatt.connect()` → phase machine: scanning→connecting→reading→connected. (2) Battery Service (`0x180F/0x2A19`): `getUint8(0)` → show percentage; -1 sentinel if service absent. (3) Device Information Service (`0x180A`): read `manufacturer_name_string` + `model_number_string` via `TextDecoder`. (4) Disconnect button + `gattserverdisconnected` event → disconnected phase. (5) Persist last device name/id to localStorage `omi.ble.lastDevice.v1`. (6) Local Web Bluetooth type stubs (dom lib doesn't include these). |
| **Not implemented** | Full Omi firmware pairing, OTA updates, live audio streaming. Omi-specific GATT service UUIDs are not documented in the repo. |
| **Classification** | **DONE** (BLE connect + standard battery/device-info GATT read) |

---

## 7. Conversations — Starred Filter

| Field | Value |
|-------|-------|
| macOS source | `APIClient.swift:418` `setConversationStarred()`, `APIClient.swift:373` `listConversations(starred:)`, `ConversationListView.swift` star toggle |
| Windows source | `Conversations.tsx` — `CloudConversation` type has no `starred` field; filter only has All/Chat/Recording |
| Backend source | `PATCH /v1/conversations/{id}/starred?starred=bool` exists; `GET /v1/conversations` returns `starred` field in response |
| Data exists today | YES — backend returns `starred` and supports toggle |
| UI exists today | NO |
| Exact blocker | `CloudConversation` type missing `starred`; no star UI or filter chip |
| Recommended action | Add `starred` to type; add `Star` toggle button on row hover; add Starred filter chip |
| Risk | Low |
| Effort | Small (1 file) |
| **Classification** | **IMPLEMENT_NOW** |

---

## 8. Conversations — Folders / Date Filter

| Field | Value |
|-------|-------|
| macOS source | `FolderManagementViews.swift` (`FolderTabsStrip`), `ConversationsPage.swift` (date popover + filter buttons) |
| Windows source | `Conversations.tsx` — **IMPLEMENTED (Batch 10)** |
| Backend source | `GET /v1/folders` returns user folders; `GET /v1/conversations?folder_id=X` filters by folder; both exist |
| **What was added** | (1) **Date filter dropdown** — "All time / Today / This week / This month" dropdown (client-side, uses `sortAt` timestamp). Button shows current selection, checkmark on active item. (2) **Folder tab strip** — loads `/v1/folders` on mount; shows scrollable horizontal pill strip (colored dot + name + count); clicking re-fetches `/v1/conversations?folder_id=X`. Absent when user has no folders. (3) **Compact view toggle** — `LayoutList` icon button switches between compact (macOS-style: emoji badge + title + timestamp in one line) and expanded (with preview) modes. Persisted to localStorage. (4) **macOS-style timestamps** — cloud rows show "10:43 AM" / "Yesterday, 10:43 AM" / "Jan 29, 10:43 AM" instead of raw `toLocaleString()`. (5) **Emoji badge in compact mode** — 36×36 rounded-xl container with ring, matching `ConversationRowView.swift` compact layout. |
| **Not implemented** | Folder create/edit/delete UI — requires CRUD sheets and significant new UI; out of scope for a parity sprint. Folder assignment on individual conversations (move-to-folder) also deferred. |
| **Classification** | **DONE** (date filter + folder filter strip + compact mode + timestamp polish) |

---

## 9. Insights History Page

| Field | Value |
|-------|-------|
| macOS source | `InsightPage.swift`, `InsightStorage.swift`, `InsightAssistant.swift` — proactive local insight generation |
| Windows source | `Insights.tsx` — **IMPLEMENTED** |
| Data exists today | YES — `insightRecent(limit)` IPC returns `InsightRecord[]` from SQLite; insight engine runs continuously |
| **What was added** | (1) `/insights` route and `InsightsPanel` in `MainViews.tsx`. (2) **Insights** nav item (Lightbulb icon) in `Sidebar.tsx`. (3) `Insights.tsx` page: category filter tabs (All / Productivity / Communication / Learning / Health / Other), search field, insight cards (category badge, headline, advice, sourceApp + timestamp footer, expandable reasoning), Refresh button. |
| **Classification** | **DONE** |

---

## 10. Tasks — Grouping & Filter Chips

| Field | Value |
|-------|-------|
| macOS source | `TasksPage.swift` — date buckets |
| Windows source | `Tasks.tsx` — **ALREADY FULLY IMPLEMENTED**: `bucketOf()`, `BUCKET_ORDER`, `openGroups` with Overdue/Today/Tomorrow/Upcoming/No-date sections; Open/Done/All filter chips |
| **Classification** | **ALREADY_DONE** |

---

## 11. Focus Page

| Field | Value |
|-------|-------|
| macOS source | `FocusPage.swift`, `FocusAssistant.swift`, `FocusModels.swift` — proactive session detection |
| Windows source | `Focus.tsx` — **IMPLEMENTED** |
| Data used | `rewindFrames(todayStart, now)` for today's app activity; `rewindGetSettings()` for interval; localStorage for manual sessions |
| **What was added** | (1) **Manual focus timer** — Pomodoro-style start/stop with optional label; sessions saved to localStorage history (keep last 100). (2) **Today's app activity** (Rewind-powered) — groups today's captured frames by app, estimates time per app (gap × captures), classifies apps as `focus` (editors/code), `distract` (media/social), or `neutral`. (3) **Stats row** — Focus time, Distraction time, Focus Rate %, Total tracked time. (4) **App breakdown list** with progress bars colored by class. (5) **Session history** — scrollable list of manual timer sessions with duration, timestamp, delete. (6) Empty/loading states; "Rewind required" notice when screen capture is off. |
| **Vision analysis added** | Three-tier classification engine: (1) **Vision** — selects 1-2 most recent Rewind frames with stored JPEGs, fetches via existing `rewind:frameImage` IPC (already path-validated), sends as `inlineData` parts to Gemini Vision with 8 s timeout; returns `visualEvidence` field. In-memory cache avoids duplicate Gemini calls within a session. (2) **Text/OCR** — `summarizeActivity()` → Gemini text prompt (same pattern as insightEngine). (3) **Heuristic** — keyword match on exe/app name; no network. Public entry `analyzeFocus(frames, useVision)`. |
| **UI additions** | Method badge in analysis card (Vision / Text-OCR / Heuristic); `visualEvidence` description shown when vision method used; fallback note "Vision unavailable — used text-OCR/heuristic" when vision enabled but fell through. |
| **Classification** | **DONE** (manual timer + Rewind app-activity breakdown + Gemini Vision three-tier classifier) |

---

## 12. Rewind OCR Overlay / Fullscreen / Export

| Field | Value |
|-------|-------|
| macOS source | `RewindPage.swift` — OCR text panel, export menu (markdown/JSON/PDF), date picker |
| Windows source | `Rewind.tsx` / `RewindPlayer.tsx` — **FULLY IMPLEMENTED** |
| Backend/data | `latestRewindFrame()` returns `{imagePath, ocrText, ts}`. OCR text available per frame. |
| Data exists today | YES |
| UI exists today | YES — implemented |
| **What was added (Batch 9)** | (1) **OCR text panel**. (2) **Fullscreen button**. (3) **JSON export**. |
| **What was added (current batch)** | (4) **Markdown export** — "MD" button downloads `omi-rewind-{date}.md`; each frame becomes a `## HH:MM:SS` section with **App/Window** header + OCR text body. (5) **Date filter** — `<input type="date">` in header; selecting a past date calls `rewindFrames(dayStart, dayEnd)` and renders that day's frames (live polling continues only for today). |
| **Remaining gap** | PDF export — requires native library (not implemented). |
| **Classification** | **DONE** (OCR panel + fullscreen + JSON + Markdown + date filter) |

---

## 13. Rewind Export

| Field | Value |
|-------|-------|
| Windows source | `Rewind.tsx` — **IMPLEMENTED (Batch 9)**: JSON export via blob URL download |
| **Classification** | **DONE** (JSON export implemented; PDF not implemented — requires native dependency) |

---

## 14. Screen Context Chat Button

| Field | Value |
|-------|-------|
| macOS source | Explicit "What's on screen" button in `ChatPage.swift` |
| Windows source | `useChat.ts:253` — `readCurrentScreen()` is called **automatically** on EVERY message and prepended as context. Already always-on. |
| **Classification** | **ALREADY_PRESENT** (implicit always-on) |

---

## 15. Settings — Support / About Tab

| Field | Value |
|-------|-------|
| macOS source | `SettingsSidebar.swift` `.about` section — app icon + name + version, Visit Website, Help Center, Privacy Policy, Terms of Service, Software Updates, Report an Issue |
| Windows source | `SupportTab.tsx` — **IMPLEMENTED (Batch 11)** |
| Data exists today | YES — version from package.json via vite `define`, runtime versions from `window.electron.process.versions` |
| **What was added** | (1) **App identity card** — omi logo + "omi" name + "Version 1.0.0 for Windows" + Electron/Node runtime versions. (2) **Visit Website** → `https://omi.me`. (3) **Help & Docs** → `https://help.omi.me`. (4) **Report an Issue** → `https://github.com/BasedHardware/omi/issues`. (5) **Privacy Policy** → `https://www.omi.me/privacy`. (6) **Terms of Service** → `https://www.omi.me/terms`. (7) **Local data note** — explains screen frames/transcripts/KG are stored on-device only. All links open in system browser via `window.open` → existing `setWindowOpenHandler` → `shell.openExternal`. |
| **Not implemented** | Native auto-install (electron-updater install blocked by nvm/npm junction corruption; no CI publish config). GitHub API checker covers version comparison + download link. |
| **Tab reorder** | Integrations moved before Shortcuts to better match macOS flow (connection setup → shortcut config). Support added at the end matching macOS's About position. |
| **Classification** | **DONE** (Support/About tab implemented) |

---

## Summary

| Priority | Item | Files | Status |
|----------|------|-------|--------|
| ✓ | Integrations tab (wired in Batch 6) | `tabs.ts`, `Settings.tsx` | Done |
| ✓ | Shortcuts tab in Settings | `tabs.ts`, `Settings.tsx`, `ShortcutsTab.tsx` | Done |
| ✓ | Chat citation cards | `useChat.ts`, `ChatMessages.tsx` | Done |
| ✓ | Conversations starred filter | `Conversations.tsx` | Done |
| ✓ | Support/About tab | `tabs.ts`, `Settings.tsx`, `SupportTab.tsx` | Done in Batch 11 |
| ✓ | Rewind OCR overlay + fullscreen + JSON export | `Rewind.tsx`, `RewindPlayer.tsx` | Done in Batch 9 |
| ✓ | Rewind Markdown export + date filter | `Rewind.tsx` | Done in current batch |
| ✓ | Insights history page | `Insights.tsx`, `MainViews.tsx`, `Sidebar.tsx` | Done in current batch |
| ✓ | Memories category filter tabs | `Memories.tsx` | Done in current batch |
| ✓ | Memory graph interactivity | `Memories.tsx` | Done in current batch |
| ✓ | Conversations row actions (edit/copy/delete) | `Conversations.tsx` | Done in current batch |
| ✓ | Conversations folder CRUD (create/delete) | `Conversations.tsx` | Done in current batch |
| ✓ | Insight settings in Settings (via Rewind tab) | `RewindTab.tsx` | Already present |
| ✓ | Conversations move-to-folder | `Conversations.tsx` | Done — `PATCH /v1/conversations/{id}/folder` |
| ✓ | Memory inline edit | `useMemories.ts`, `Memories.tsx` | Done — `PATCH /v3/memories/{id}?value=` |
| ✓ | Conversation copy shareable link | `Conversations.tsx` | Done — visibility=shared + h.omi.me URL |
| ✓ | Conversation multi-select merge | `Conversations.tsx` | Done — `POST /v1/conversations/merge` |
| ✓ | Speaker display names (person_id → name) | `ConversationDetail.tsx` | Done — people[] from GET /v1/conversations/{id} |
| ✓ | BYOK — settings UI + header injection | `BYOKTab.tsx`, `tabs.ts`, `Settings.tsx`, `apiClient.ts`, `preferences.ts` | Done — X-BYOK-* headers, SHA-256 fingerprints, POST /v1/users/me/byok-active |
| ✓ | Chat audio file attachment | `useChat.ts`, `Home.tsx` | Done — paperclip → POST /v2/voice-messages multipart, SSE stream |
| ✓ | Speaker label assignment | `ConversationDetail.tsx` | Done — click chip → person picker, GET /v1/users/people, PATCH assign-speaker |
| ✓ | Software updates — "Check for Updates" link | `SupportTab.tsx` | Done — GitHub releases link (no auto-updater: no publish config) |
| ✓ | Focus page | `Focus.tsx`, `Sidebar.tsx`, `MainViews.tsx` | Done — manual timer + Rewind app-activity breakdown (no proactive ML) |
| ✓ | Notifications settings | `NotificationsTab.tsx`, `tabs.ts`, `Settings.tsx`, `useRecorder.ts`, `preferences.ts` | Done — insight notifications tab + recording-saved Web Notification |
| ✓ | Check for Updates | `SupportTab.tsx` | Done — GitHub API release check (available/up-to-date/error); no electron-updater needed |
| ✓ | Devices tab — BLE connect + battery | `DevicesTab.tsx` | Done — scan→connect, Battery Service read (0x180F/0x2A19), Device Info Service (0x180A), disconnect, last-device localStorage |
| ✗ | Auto-update native feed | — | Blocked — npm junction still points to nvm v22.9.0; electron-updater install fails; no publish config in CI. GitHub API checker is the mechanism; SupportTab shows installed vs. latest version. |
| ✓ | Proactive focus detection (Vision-tier) | `focusEngine.ts`, `Focus.tsx`, `NotificationsTab.tsx`, `preferences.ts` | Done — three-tier (Vision → Text-OCR → Heuristic); Gemini Vision via existing rewind:frameImage IPC |
| ✗ | Native BLE pairing | — | No `noble` or `node-ble` addon; Devices tab shows honest unsupported state |
| ✓ | Tasks grouping | — | Already done |
| ✓ | Screen context | — | Already present |
| ✓ | Overlay drag/resize/pill | — | Done in Batch 7 |
