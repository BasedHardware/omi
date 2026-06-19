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
| Windows source | None |
| Backend source | Proactive assistant system (`ProactiveAssistantsPlugin.swift`, `InsightAssistant.swift`, `FocusAssistant.swift`). No equivalent on Windows. |
| Data exists today | NO — Windows has no proactive assistant backend |
| Exact blocker | Windows has no notification generation pipeline |
| **Classification** | **DO_NOT_DO_NOW** — proactive assistant infrastructure absent |

---

## 6. Settings — Support / Devices / Assistants Tabs

| Field | Value |
|-------|-------|
| macOS source | `SettingsSidebar.swift` has `.about`, device section, Crispo support widget |
| Windows source | None |
| Exact blocker | Windows has no Bluetooth device pairing, no Crisp.chat, no proactive assistant config |
| **Classification** | **DO_NOT_DO_NOW** |

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
| macOS source | `FolderManagementViews.swift`, `ConversationListView.swift` — `folderId` param to API |
| Windows source | None |
| Backend source | `GET /v1/conversations?folder_id=X` and folder CRUD endpoints exist |
| Data exists today | YES for date filter; YES for folders (API exists) |
| Exact blocker | Would require significant new UI (folder list sidebar, folder assignment) |
| **Classification** | **DO_NOT_DO_NOW** — too wide, diminishing returns vs other items |

---

## 9. Insights History Page

| Field | Value |
|-------|-------|
| macOS source | `InsightPage.swift`, `InsightStorage.swift`, `InsightAssistant.swift` — proactive local insight generation |
| Windows source | None |
| Exact blocker | Windows has no proactive assistant backend; insights are generated locally by the macOS app |
| **Classification** | **DO_NOT_DO_NOW** |

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
| Windows source | None |
| Exact blocker | Requires screen activity analysis + proactive assistant. Not viable without major backend work. |
| **Classification** | **DO_NOT_DO_NOW** |

---

## 12. Rewind OCR Overlay / Fullscreen / Export

| Field | Value |
|-------|-------|
| macOS source | `RewindPage.swift` — OCR text panel, export menu (markdown/JSON/PDF) |
| Windows source | `Rewind.tsx` shows `RewindPlayer` but no OCR text overlay. OCR text stored per frame (`frame.ocrText`) in `db.ts:latestRewindFrame()` |
| Backend/data | `latestRewindFrame()` returns `{imagePath, ocrText, ts}`. OCR text is available per frame. |
| Data exists today | YES — `ocrText` field exists on Rewind frames |
| UI exists today | NO — OCR text not surfaced in UI |
| Recommended action | Add OCR text toggle panel below the frame player in `Rewind.tsx`. Low risk, high parity value. |
| Risk | Low |
| Effort | Small |
| **Classification** | **IMPLEMENT_NOW** (but lower priority than integrations/citations/shortcuts) |

---

## 13. Rewind Export

| Field | Value |
|-------|-------|
| Windows source | `window.omi.listRewindFrames()` returns frames with `imagePath + ocrText`. Can export as JSON or plain text. |
| **Classification** | **IMPLEMENT_PARTIAL** (JSON/text export only; PDF requires native library) |

---

## 14. Screen Context Chat Button

| Field | Value |
|-------|-------|
| macOS source | Explicit "What's on screen" button in `ChatPage.swift` |
| Windows source | `useChat.ts:253` — `readCurrentScreen()` is called **automatically** on EVERY message and prepended as context. Already always-on. |
| **Classification** | **ALREADY_PRESENT** (implicit always-on) |

---

## Summary

| Priority | Item | Files | Risk |
|----------|------|-------|------|
| 1 | Integrations tab (already built, just unwired) | `tabs.ts`, `Settings.tsx` | Very low |
| 2 | Shortcuts tab in Settings | `tabs.ts`, `Settings.tsx`, new `ShortcutsTab.tsx` | Low |
| 3 | Chat citation cards | `useChat.ts`, `ChatMessages.tsx` | Low |
| 4 | Conversations starred filter | `Conversations.tsx` | Low |
| — | Rewind OCR overlay | `Rewind.tsx`, `RewindPlayer.tsx` | Low |
| ✗ | Focus page | — | Very high / infeasible |
| ✗ | Insights page | — | Very high / infeasible |
| ✗ | Notifications settings | — | High / infeasible |
| ✓ | Tasks grouping | — | Already done |
| ✓ | Screen context | — | Already present |
| ✓ | Overlay drag/resize/pill | — | Done in Batch 7 |
