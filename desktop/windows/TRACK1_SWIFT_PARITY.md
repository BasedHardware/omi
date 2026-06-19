# Track 1 – Swift macOS ↔ Windows Parity Audit

**Branch:** `perf/windows-kg-worker`  
**Date:** 2026-06-18  
**Goal:** Bring the Electron/React Windows app as close as possible to the Swift/SwiftUI macOS app for judging.

---

## Quick Legend

| Status | Meaning |
|--------|---------|
| ✅ Works | Functionally equivalent; visually close |
| 🟡 Partial | Feature exists but is incomplete or visually different |
| ❌ Missing | Feature does not exist in Windows build |
| ❓ Unknown | Cannot determine from source alone |

| Priority | Meaning |
|----------|---------|
| P0 | Judge sees it in the first 30 seconds |
| P1 | Judge finds it in first 2 minutes of exploration |
| P2 | Judge finds it in deeper testing |

---

## Parity Table

### 1. App Shell / Main Window

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/OmiApp.swift`, `Sources/MainWindow/DesktopHomeView.swift`, `Sources/MainWindow/SidebarView.swift` |
| **Windows source** | `src/main/index.ts`, `src/renderer/src/App.tsx`, `src/renderer/src/components/layout/Sidebar.tsx` |
| **macOS sidebar items** | Dashboard · Conversations · Memories · Tasks · Rewind · Apps · Settings (7 items) |
| **Windows sidebar items** | Dashboard · Conversations · Memories · Tasks · Rewind · Apps · Settings (7 items — **exact match**) |
| **Status** | 🟡 Partial → improved (Batch 6) |
| **Visual gap** | macOS uses a native `NavigationSplitView` look; Windows uses a custom CSS rail. Font scaling (Cmd++/−) absent. Item count now matches macOS exactly (7). |
| **Functional gap** | No Goals or Insights page in nav. No Focus page. Dashboard merges widgets + chat rather than being a separate dedicated route. |
| **Proposed fix** | Add Goals and Insights as top-level sidebar items. Promote Dashboard to its own route separate from the merged Home/chat page. |
| **Priority** | P0 |

---

### 2. Onboarding Flow

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/OnboardingView.swift`, `Sources/OnboardingFlow.swift`, `Sources/Onboarding*StepView.swift` (17 steps) |
| **Windows source** | `src/renderer/src/pages/Onboarding.tsx`, `src/renderer/src/components/onboarding/*.tsx` (13 steps) |
| **macOS steps** | Welcome · Voice Shortcut · Floating Bar Shortcut · Voice Demo · Floating Bar Demo · Notifications · Permissions · Language · Goal · Tasks · Data Sources · Exports · BYOK · Trust · How Did You Hear · File Scan · Chat |
| **Windows steps** | Name · Language · How Did You Hear · Trust · Screen Permission · Build Profile · Mic Permission · Automation Permission · Shortcut Setup · Voice Intro · Ask Demo · Goal · Auto-Created Tasks |
| **Status** | 🟡 Partial |
| **Visual gap** | Windows has a 3D BrainMap visualization (Three.js) during profile building; macOS has a progress-dot stepper with illustrated step views. Overall feel differs. |
| **Functional gap** | Windows missing: BYOK step, Exports step, Data Sources connector step, Floating Bar demo step, Notifications permission step. Windows has extras macOS lacks (Automation Permission, Build Profile, 3D brain). |
| **Proposed fix** | Low-value for judging parity — onboarding style differs but both function. If time permits, add a Floating Bar demo step and a Data Sources / integrations step to match macOS flow. |
| **Priority** | P2 |

---

### 3. Login / Sign-In

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/SignInView.swift`, `Sources/AuthService.swift` |
| **Windows source** | `src/renderer/src/pages/Login.tsx` |
| **macOS methods** | Sign in with Apple, Sign in with Google |
| **Windows methods** | Sign in with Google only |
| **Status** | ✅ Works (Apple Sign-In is macOS-only; Google-only is correct for Windows) |
| **Visual gap** | Minimal. macOS has a centered card; Windows has a centered 420px column. Both show the Omi logo. |
| **Functional gap** | None that applies to Windows. |
| **Proposed fix** | None required. |
| **Priority** | — |

---

### 4. Chat / AI Conversation

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/ChatPage.swift`, `Sources/MainWindow/Components/ChatMessagesView.swift`, `Sources/MainWindow/Components/ChatInputView.swift`, `Sources/Chat/CitationCardView.swift`, `Sources/Chat/SelectableMarkdown.swift` |
| **Windows source** | `src/renderer/src/pages/Home.tsx`, `src/renderer/src/components/chat/ChatMessages.tsx` |
| **Status** | 🟡 Partial → improved (Batch 5) |
| **Visual gap** | macOS renders a dedicated full-page chat view. Windows merges chat with home/dashboard widgets; the chat bar collapses the widget area on first message. |
| **Functional gap** | **Improved (Batch 5):** `Markdown.tsx` now renders headings with proper size hierarchy (h1/h2/h3), code blocks with language label + monospace font + dark background, accent-colored links (`--accent` color), and bold/italic/inline code. Chat thread is now text-selectable (overrides global `user-select:none`). Avatar alignment changed to `items-start` for taller messages. Message spacing improved (`space-y-3`). Streaming and reveal animation preserved. **Remaining gaps:** citation cards (no citation data exists in `ChatMsg` type — the API does not return source references at `/v2/messages`; this is a backend gap, not a frontend gap), audio attachment support. |
| **Proposed fix** | (1) Citation cards require backend to return source metadata in the message stream — document as remaining gap. (2) Future: separate Chat into its own route if desired. |
| **Priority** | P1 — IMPROVED |

---

### 5. Floating Overlay / "Ask Omi" Popup

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/FloatingControlBar/FloatingControlBarWindow.swift`, `Sources/FloatingControlBar/FloatingControlBarView.swift`, `Sources/FloatingControlBar/AgentPillsWindow.swift` |
| **Windows source** | `src/main/overlay/window.ts`, `src/renderer/src/components/overlay/OverlayApp.tsx`, `src/renderer/src/components/overlay/Waveform.tsx` |
| **Status** | 🟡 Partial → improved (Batch 7) |
| **Visual gap** | Windows has Acrylic/Mica DWM backdrop and waveform visualization. Missing: hover-expand behavior (macOS collapses to a 14px breathing pill at rest, expands on hover; Windows always shows the full panel). macOS has separate agent pill floating window for background agents. |
| **Improvements (Batch 7)** | (1) **Drag handle** — made more visible (h-7, 3px bar, 40px wide, 60% opacity). (2) **Resize** — window is now `resizable: true` with `minWidth/maxWidth` locked to 336px and `minHeight: 80`; the bottom edge can be dragged to make the window taller or shorter. (3) **Resize grip** — 3-dot SVG grip at bottom-right mirrors macOS `ResizeHandleView`. (4) **Agent pill** — "Omi" pill with green status dot above the input row, matching the visual style of macOS `AgentPillsRowView`; no real agent VM backend on Windows so this shows the default agent only. |
| **Remaining gaps** | Agent VM backend (spawn/track agents, follow-ups) not on Windows. macOS hover-compact behavior not implemented. Voice-playback animation for AI audio responses missing. PTT uses mic only (macOS uses system audio too). |
| **Test status** | `npm run typecheck` ✅ · `npm run build:win` ✅ · Drag works (CSS `-webkit-app-region: drag`) · Resize functional (native OS resize, width locked) · Input/buttons clickable (`overlay-no-drag`) · Waveform and PTT unchanged · Entrance/exit animations preserved |
| **Priority** | P1 — IMPROVED |

---

### 6. Recording / Listening State UI

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Components/LiveTranscriptView.swift`, `Sources/MainWindow/Components/AudioLevelWaveformView.swift`, `Sources/RecordingTimer.swift`, `Sources/AudioLevelMonitor.swift` |
| **Windows source** | `src/renderer/src/components/recording/RecordingStatusBar.tsx` (new, Batch 4), `src/renderer/src/components/recording/ContinuousRecordingHost.tsx`, `src/renderer/src/components/GlobalRecordButton.tsx`, `src/renderer/src/lib/liveConversation.ts` |
| **Status** | 🟡 Partial → improved (Batch 4) |
| **Visual gap** | Now shows a pulsing rose dot + "Listening" / "Connecting…" label + MM:SS elapsed timer + last-6-words transcript snippet in the sidebar (above mic/screen toggles) when the live session is active or manual recording runs. Collapsed sidebar shows just the dot with a tooltip. Still missing: waveform bars, audio level visualization. |
| **Functional gap** | No waveform/audio-level bars (would require real-time audio level IPC from main). Live transcript snippet shows the tail of the last recognized segment. |
| **Proposed fix** | Audio level bars deferred — would require new IPC from the WebAudio pipeline. |
| **Priority** | P1 — IMPROVED |

---

### 7. Transcript / Conversation History

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/ConversationsPage.swift`, `Sources/MainWindow/Pages/ConversationDetailView.swift`, `Sources/MainWindow/Components/ConversationListView.swift`, `Sources/MainWindow/Components/ConversationRowView.swift` |
| **Windows source** | `src/renderer/src/pages/Conversations.tsx`, `src/renderer/src/pages/ConversationDetail.tsx`, `src/renderer/src/pages/LiveConversation.tsx` |
| **Status** | 🟡 Partial → improved (Batch 10) |
| **Visual gap** | macOS uses a master-detail split view. Windows uses a flat list with click-to-navigate. |
| **Improvements (Batch 10)** | (1) **Date filter** — dropdown (All time / Today / This week / This month), client-side against `sortAt`. (2) **Folder tab strip** — loads `/v1/folders`, shows scrollable pill strip with colored dot + name + count; clicking folder re-fetches `/v1/conversations?folder_id=X`; hidden when no folders. (3) **Compact view** — macOS-style single-line row: 36×36 emoji badge with rounded-xl ring background, title, macOS-style timestamp (today→time-only, yesterday→"Yesterday, HH:MM AM", etc.), star on right. Toggle persisted to localStorage. (4) **macOS-style timestamps** — cloud rows in expanded mode now show "10:43 AM" / "Yesterday, 10:43 AM" / "Jan 29, 10:43 AM" to match `ConversationRowView.swift`'s `formattedTimestamp`. |
| **Remaining gaps** | Folder create/edit/delete UI; move-to-folder per conversation; master-detail split view; batch merge; speaker name editing. |
| **Priority** | P1 — IMPROVED |

---

### 8. Rewind / Timeline

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/Rewind/UI/RewindPage.swift`, `Sources/Rewind/UI/RewindTimelineView.swift`, `Sources/Rewind/UI/RewindTimelinePlayerView.swift`, `Sources/Rewind/UI/SearchResultsFilmstrip.swift`, `Sources/Rewind/Core/RewindDatabase.swift` |
| **Windows source** | `src/renderer/src/pages/Rewind.tsx`, `src/renderer/src/components/rewind/RewindPlayer.tsx`, `src/renderer/src/components/rewind/RewindTimelineBar.tsx`, `src/renderer/src/components/rewind/RewindThumbnailStrip.tsx`, `src/renderer/src/components/rewind/RewindSearchBar.tsx` |
| **Status** | 🟡 Partial → improved (Batch 9) |
| **Visual gap** | Windows timeline bar and thumbnail strip are implemented. Search is surfaced. macOS has an always-visible OCR panel; Windows has a toggleable panel (matches intent, slightly different interaction). |
| **Improvements (Batch 9)** | (1) **OCR text panel** — "Text" toggle button in Rewind header shows/hides a collapsible panel below the player with the current frame's OCR text, selectable, with "No text captured" empty state. (2) **Fullscreen button** — `Maximize2` icon floats top-right of the screenshot; clicking opens the existing full-screen overlay (click anywhere to dismiss). Click-on-image also still works. (3) **JSON export** — "Export" button (only shown when frames exist) downloads `omi-rewind-{date}.json` with timestamp, app, windowTitle, ocrText per frame — no new IPC, uses browser blob download in Electron renderer. |
| **Remaining gaps** | PDF export (needs native library); Markdown export (deferred). No per-frame app-icon badge (macOS shows app icons on thumbnail strip). |
| **Priority** | P0 — IMPROVED |

---

### 9. Screen OCR / Context Capture

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/Rewind/Core/RewindOCRService.swift`, `Sources/ScreenCaptureService.swift`, `Sources/ProactiveAssistants/Core/GeminiClient.swift` |
| **Windows source** | `src/main/ocr/helperProcess.ts`, `src/main/ocr/helperProtocol.ts`, `src/renderer/src/lib/screenContext.ts`, `src/main/rewind/ocrService.ts` |
| **Status** | 🟡 Partial |
| **Visual gap** | No user-visible gap — OCR is a background feature. Both platforms surface it through Rewind and chat context. |
| **Functional gap** | Windows has the infrastructure (Win-OCR-Helper.exe, `screenContext.ts`) but the "What's on my screen?" chat integration is not prominently surfaced in the chat UI. macOS exposes a toggle in both menu bar and Settings → Assistants. Windows only exposes a toggle in Settings → Rewind. |
| **Proposed fix** | Surface the screen-context feature in chat as a suggested prompt or toolbar button. Ensure Settings → Privacy/Rewind makes the toggle discoverable. |
| **Priority** | P2 |

---

### 10. Settings

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/SettingsPage.swift`, `Sources/MainWindow/SettingsSidebar.swift`, `Sources/MainWindow/Pages/PermissionsPage.swift`, `Sources/MainWindow/Pages/ShortcutsSettingsSection.swift` |
| **Windows source** | `src/renderer/src/pages/Settings.tsx`, `src/renderer/src/components/settings/` |
| **macOS sections** | General · Assistants · Devices · Integrations · Shortcuts · Notifications · Support · About |
| **Windows sections** | General · Memories · Rewind · Integrations · Shortcuts · Privacy · Account · Advanced · **Support** (Batch 11) |
| **Status** | 🟡 Partial → improved (Batch 11) |
| **Visual gap** | macOS settings use a sidebar rail + right-panel pattern with section groupings. Windows uses a tabbed horizontal navigation with a search bar. Both are dark-themed but the layout and terminology differ significantly. |
| **Nav change (Batch 6)** | Settings is now a first-class sidebar nav item (after Apps), matching macOS sidebar order exactly. |
| **Tab reorder (Batch 11)** | Integrations moved before Shortcuts (matches macOS: integrations/connections before keyboard shortcuts). Support tab added at end (matches macOS: About at bottom of sidebar). |
| **Support/About tab (Batch 11)** | App identity card (omi logo + name + version + Electron/Node), Visit Website, Help & Docs, Report an Issue (GitHub), Privacy Policy, Terms of Service, local data note. All links open in system browser. |
| **Remaining gaps** | Notifications tab (proactive notification config — infeasible, no Windows notification pipeline). Devices/Bluetooth (hardware-only, infeasible). Assistants enable/disable panel (no proactive assistant infra on Windows). Software Updates UI (Sparkle macOS-only; electron-builder updater could be wired in future). |
| **Priority** | P1 — IMPROVED |

---

### 11. System Tray / Menu Bar

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/OmiApp.swift` (AppDelegate.setupMenuBar), `Sources/FloatingControlBar/GlobalShortcutManager.swift` |
| **Windows source** | `src/main/index.ts` (setupTray, buildTrayMenu) |
| **macOS features** | Status bar icon, right-click menu: Screen Capture toggle, Audio Recording toggle, Open Omi, Check for Updates, Reset Onboarding, Report Issue, Signed-in email, Sign Out, Quit |
| **Windows features** | Tray icon with left-click to open, right-click menu: Open Omi, Screen Capture toggle (checkbox, reads/writes rewind settings, broadcasts rewind:settings to renderer), Quit Omi. Close-to-tray: X button hides the window instead of closing. |
| **Status** | ✅ Implemented (Batch 2) |
| **Visual gap** | Windows tray menu does not yet show signed-in email or mic toggle (mic state lives in renderer localStorage; adding it would require IPC bridging — deferred). |
| **Functional gap** | Mic toggle and "Check for Updates" not yet in tray menu. Screen capture toggle is wired and syncs with the sidebar toggle via rewind:settings broadcast. |
| **Proposed fix** | Add mic state IPC bridge if needed in a future batch. |
| **Priority** | P0 — **DONE** |

---

### 12. Notifications

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/ProactiveAssistants/Services/NotificationService.swift`, `Sources/FloatingControlBar/FloatingControlBarView.swift` |
| **Windows source** | `src/renderer/src/components/ui/ToastHost.tsx`, `src/renderer/src/lib/toast.ts`, `src/main/insight/toastWindow.ts` |
| **Status** | 🟡 Partial |
| **Visual gap** | macOS uses native UNUserNotificationCenter banners (appear in the OS notification center). Windows uses in-app toasts and a custom Electron popup window for insights. The insight popup window is close to macOS's in-app notification banner behavior. |
| **Functional gap** | Windows insight toasts exist but are not wired to the OS notification center (`new Notification()` or `Electron.Notification`). macOS notifications route to specific screens on click; Windows insight toasts do not have click routing. |
| **Proposed fix** | Send OS-level notifications via `Electron.Notification` API for key events (insight generated, memory created, recording saved). Wire click action to navigate to the relevant page. |
| **Priority** | P2 |

---

### 13. Integrations / Plugins

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/ProactiveAssistants/Assistants/`, various reader services, `Sources/MainWindow/Pages/AppsPage.swift` |
| **Windows source** | `src/renderer/src/components/settings/tabs/IntegrationsTab.tsx`, `src/main/integrations/`, `src/renderer/src/pages/Apps.tsx` |
| **macOS integrations** | Gmail, Google Calendar, Apple Notes, File System, Bluetooth Devices (Omi hw/Fieldy/Frame/Limitless/Plaud/Bee), Browser extensions |
| **Windows integrations** | Gmail (conditional flag), Google Calendar (conditional flag), Sticky Notes (Windows), File System |
| **Status** | 🟡 Partial |
| **Visual gap** | macOS has a dedicated Integrations section in Settings with OAuth status cards per integration. Windows buries integrations under Settings → Advanced with conditional feature flags (`VITE_ENABLE_GOOGLE_INTEGRATION`). |
| **Functional gap** | Windows Google integrations require `VITE_ENABLE_GOOGLE_INTEGRATION=true` build flag to appear. No Bluetooth device pairing. No browser extension integration. |
| **Proposed fix** | (1) Ensure `VITE_ENABLE_GOOGLE_INTEGRATION` is enabled in the dev/release build. (2) Move the integrations sub-section from Advanced → its own Settings tab. (3) Bluetooth/browser extensions: out of scope for Windows. |
| **Priority** | P1 |

---

### 14. Dashboard Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/DashboardPage.swift`, `DailyScoreWidget.swift`, `TodaysTasksWidget.swift`, `GoalsWidget.swift`, `FocusSummaryWidget.swift`, `RecentConversationsWidget.swift` |
| **Windows source** | `src/renderer/src/pages/Home.tsx`, `src/renderer/src/components/home/QuickTaskWidget.tsx`, `src/renderer/src/components/home/QuickGoalsWidget.tsx`, `src/renderer/src/components/home/QuickConversationsWidget.tsx` |
| **Status** | 🟡 Partial → improved (Batch 3) |
| **Visual gap** | Sidebar now shows "Dashboard" label. Widget grid now shows Tasks + Goals (top row) + Recent Conversations (full-width bottom row). Still missing: DailyScore, FocusSummary widgets. Chat flow preserved below widgets. |
| **Functional gap** | No DailyScore or FocusSummary widget. Conversations widget fetches from /v1/conversations and shows 3 most recent with emoji, title, relative time. |
| **Proposed fix** | Add DailyScore and FocusSummary if backend endpoints exist — deferred to future batch. |
| **Priority** | P0 — IMPROVED |

---

### 15. Memories Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/MemoriesPage.swift`, `Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift` |
| **Windows source** | `src/renderer/src/pages/Memories.tsx`, `src/renderer/src/hooks/useMemories.ts` |
| **Status** | 🟡 Partial |
| **Visual gap** | macOS shows a list with category tabs (Manual, About You, Insights, Workflow). Windows shows a card grid with a 3D WebGL brain graph. The 3D graph is an impressive Windows-exclusive but the category/filter UI from macOS is absent. |
| **Functional gap** | Missing: category tab filtering, star/favorite toggle per memory, tag filtering. Memories is not accessible from the main sidebar on Windows — it's buried inside Settings. |
| **Proposed fix** | (1) Add Memories to the sidebar as a top-level nav item (most impactful). (2) Add a category/tag filter row above the memory grid. (3) Add a star/favorite icon on each memory card. |
| **Priority** | P0 (sidebar placement), P2 (category filter) |

---

### 16. Tasks Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/TasksPage.swift` |
| **Windows source** | `src/renderer/src/pages/Tasks.tsx` |
| **Status** | 🟡 Partial |
| **Visual gap** | macOS groups tasks by temporal bucket (Today / Tomorrow / Later / No Deadline). Windows shows a flat list. macOS has multi-filter UI (Status, Date, Category, Source, Priority, Origin); Windows has no filter UI. |
| **Functional gap** | Missing: task grouping by date bucket, filter chips, batch select, priority indicators per task, category badges. |
| **Proposed fix** | (1) Group task list by Today / Upcoming / Later / No Date — compute bucket from due date, add section headers. (2) Add filter chips row (Status: open/done, Date: today/upcoming). These are the most visible gaps. |
| **Priority** | P1 |

---

### 17. Rewind Search (sub-feature)

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/Rewind/UI/RewindSearchBar.swift`, `Sources/Rewind/Services/RewindIndexer.swift`, `Sources/Rewind/Core/RewindDatabase.swift` |
| **Windows source** | `src/renderer/src/components/rewind/RewindSearchBar.tsx` (built but hidden), `src/main/rewind/ocrService.ts` |
| **Status** | ❌ Missing (hidden in build) |
| **Visual gap** | macOS has a prominent search bar at top of Rewind page with filmstrip results. Windows has the component built but commented out / not rendered. |
| **Functional gap** | Search over OCR content is not available to user in Windows build despite backend implementation existing. |
| **Proposed fix** | Render `RewindSearchBar` in `Rewind.tsx`. Wire `rewind:search` IPC call through to the existing `ocrService.ts`. This is infrastructure already built — just needs to be surfaced. |
| **Priority** | P0 |

---

### 18. Insights Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/InsightPage.swift` |
| **Windows source** | `src/main/insight/toastWindow.ts` (toast-only, no page) |
| **Status** | ❌ Missing |
| **Visual gap** | macOS has a full Insights page (chronological feed of AI-generated insights, category filter, detail expansion). Windows only shows insights as ephemeral toast popups with no persistent log. |
| **Functional gap** | No way to review past insights. No insight history page. |
| **Proposed fix** | Create a simple `/insights` page that lists past insights (fetched from backend or stored locally). Add to sidebar nav. Reuse the toast data model that `toastWindow.ts` already populates. |
| **Priority** | P1 |

---

### 19. Goals Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/GoalsHistoryPage.swift` |
| **Windows source** | `src/renderer/src/pages/Goals.tsx` |
| **Status** | 🟡 Partial |
| **Visual gap** | Goals page exists on Windows with progress bars and suggestion. macOS version also has goal archival view and goal-to-task associations shown. |
| **Functional gap** | Windows Goals is accessible via Tasks page toggle but not from main sidebar. Missing archived goals view, goal-to-task associations, full goal history. |
| **Proposed fix** | Add Goals as a sidebar item (or under Tasks as a prominent toggle — already implemented). Ensure archived/completed goals view is accessible. |
| **Priority** | P2 |

---

### 20. Focus Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/FocusPage.swift` |
| **Windows source** | None |
| **Status** | ❌ Missing |
| **Visual gap** | macOS has a Focus mode with timer, distraction detection alerts, session history, and streak tracking. Windows has no equivalent. |
| **Functional gap** | No Focus mode at all on Windows. |
| **Proposed fix** | Out of scope for a quick parity sprint — requires new backend features. Mark as known gap. |
| **Priority** | P2 |

---

### 21. Apps / Marketplace Page

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/AppsPage.swift` |
| **Windows source** | `src/renderer/src/pages/Apps.tsx` |
| **Status** | ✅ Works |
| **Visual gap** | Both show a grid of app cards with install/uninstall toggles. Windows has search, category filter, rating stars, install count — arguably more feature-rich than macOS. |
| **Functional gap** | None significant. |
| **Proposed fix** | None required. |
| **Priority** | — |

---

### 22. Memory Graph / Brain Visualization

| Field | Detail |
|-------|--------|
| **macOS source** | `Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift`, `Sources/MainWindow/Pages/MemoryGraph/ForceDirectedSimulation.swift` |
| **Windows source** | `src/renderer/src/components/BrainGraph.tsx` (Three.js + D3), `src/renderer/src/hooks/useMemoryGraph.ts` |
| **Status** | ✅ Works — interaction restored |
| **Visual gap** | macOS uses a 2D force-directed graph (SwiftUI Canvas). Windows uses a 3D WebGL sphere with Three.js — more visually impressive. |
| **Functional gap** | **Issue found:** Memories page was passing `interactive={false}`, which replaced `OrbitControls` with a `CameraRig` that locks the camera every frame. Graph rendered but drag/zoom/click were all dead. **Fix applied:** removed `interactive={false}` (defaults to `true`), added pointer/click handlers to `GraphNodeMesh` — hover shows pointer cursor (via `gl.domElement.style.cursor`), click selects a node with a visible glow boost (2.2× emissive, 1.35× halo). Non-interactive (onboarding) path is unchanged. |
| **Test status** | `npm run typecheck` ✅ · drag rotates ✅ · scroll zooms ✅ · node click selects/highlights ✅ · onboarding graph unchanged ✅ |
| **Priority** | — |

---

## Summary Score

| Surface | Status | Priority |
|---------|--------|----------|
| App Shell / Sidebar Nav | 🟡 Partial (improved) | P0 — IMPROVED |
| Onboarding | 🟡 Partial | P2 |
| Login / Auth | ✅ Works | — |
| Chat / AI Conversation | 🟡 Partial (improved) | P1 — IMPROVED |
| Floating Overlay | 🟡 Partial | P1 |
| Recording / Listening UI | 🟡 Partial (improved) | P1 — IMPROVED |
| Conversation History | 🟡 Partial (improved) | P1 — IMPROVED |
| Rewind / Timeline | 🟡 Partial (improved) | P0 — IMPROVED |
| Rewind Search | ✅ Works | P0 — DONE |
| Screen OCR / Context | 🟡 Partial | P2 |
| Settings | 🟡 Partial (improved) | P1 — IMPROVED (Support/About tab added, tabs reordered) |
| System Tray | ✅ Works | P0 — DONE |
| Notifications | 🟡 Partial | P2 |
| Integrations | 🟡 Partial | P1 |
| Dashboard Page | 🟡 Partial (improved) | P0 — IMPROVED |
| Memories Page (nav placement) | ✅ Works | P0 — DONE |
| Tasks Page | 🟡 Partial | P1 |
| Insights Page | ❌ Missing | P1 |
| Goals Page | 🟡 Partial | P2 |
| Focus Page | ❌ Missing | P2 |
| Apps / Marketplace | ✅ Works | — |
| Memory Graph | ✅ Works | — |

**Totals:** 6 ✅ Works · 13 🟡 Partial · 3 ❌ Missing  
**P0 gaps resolved:** Sidebar nav (7-item match) ✅ · Rewind search surfaced ✅ · System tray ✅ · Dashboard widgets ✅ · Memories in nav ✅ · Settings in nav ✅  
**Remaining P0 gaps:** None  
**Remaining P1 gaps:** Overlay (drag/resize/agent pills) · Conversations (folder, starred) · Tasks (date grouping) · Integrations (flag enabled) · Settings (Shortcuts/Notifications tabs)  
**Known permanent gaps:** Insights page · Focus mode · citation cards (backend) · onboarding flow style · Bluetooth device pairing

---

## Implementation Plan: Top 5 Highest-Impact Changes

### #1 — Add System Tray Icon  
**Impact:** P0 — Judge sees Omi living in the taskbar tray like macOS's menu bar. Without it the app feels incomplete as a background utility.  
**Files to edit:**  
- `src/main/index.ts` — create `Tray` instance, load icon, build context menu  
- `src/preload/index.ts` — expose `tray:setContextMenu` IPC if needed  
- Add a tray icon asset: `resources/tray-icon.ico` (16×16 or 32×32)  
**Risk:** Low. Electron `Tray` API is stable on Windows. Does not touch renderer.  
**Test:** After launch, a tray icon appears in the system tray. Right-click shows menu. "Open Omi" focuses the main window. Mic/Screen toggles affect recording state.

---

### #2 — Add Memories to Sidebar Navigation  
**Impact:** P0 — Memories is a primary nav destination in macOS. On Windows it's buried inside Settings.  
**Files to edit:**  
- `src/renderer/src/components/layout/Sidebar.tsx` — add a `NavItem` for `/memories` between Conversations and Tasks  
- `src/renderer/src/App.tsx` — ensure `/memories` route is already registered (it is)  
**Risk:** Very low. Just adding a nav item to an existing route.  
**Test:** Clicking Memories in sidebar navigates to the memories grid and brain graph. Active state highlights correctly.

---

### #3 — Enable Rewind Search  
**Impact:** P0 — The component and backend are already built. This is a one-line change to surface a major feature.  
**Files to edit:**  
- `src/renderer/src/pages/Rewind.tsx` — render `<RewindSearchBar>` (currently not included in JSX)  
- Verify `rewind:search` IPC is wired in `src/main/ipc/` (likely already is)  
**Risk:** Very low. Component already exists; just needs to be rendered.  
**Test:** Type a word in the Rewind search bar, filmstrip shows matching frames, clicking a result seeks to that time.

---

### #4 — Separate Dashboard from Home / Add Dashboard Widgets  
**Impact:** P0 — macOS has a rich dashboard as the first thing a judge sees. Windows collapses everything into a chat page.  
**Files to edit:**  
- `src/renderer/src/pages/Home.tsx` — split idle widget area into a dedicated layout, or create `src/renderer/src/pages/Dashboard.tsx`  
- `src/renderer/src/components/layout/Sidebar.tsx` — rename "Home" → "Dashboard" or add separate Dashboard route  
- Add `RecentConversationsWidget` component (fetch last 3 conversations, display as cards)  
**Risk:** Medium. Restructuring the Home page could affect the chat flow. Safest approach: keep Home as-is but rename it to "Dashboard" in the nav and expand the widget grid when idle.  
**Test:** Sidebar item says "Dashboard". Idle state shows task widget, goals widget, and recent conversations list. Chat still works when user starts typing.

---

### #5 — Add Insights Page  
**Impact:** P1 — macOS has a dedicated Insights feed. Windows only shows ephemeral insight toasts with no history.  
**Files to edit:**  
- Create `src/renderer/src/pages/Insights.tsx` — simple chronological list fetching from `/v1/insights` or the local insight store  
- `src/renderer/src/components/layout/Sidebar.tsx` — add Insights nav item  
- `src/renderer/src/App.tsx` — register `/insights` route  
- `src/main/insight/toastWindow.ts` — ensure insights are also persisted locally so the page has data  
**Risk:** Low for the page itself. Medium if insights need a new API endpoint. Check if `/v1/insights` or equivalent exists in the backend.  
**Test:** Navigate to Insights. Past insight cards are listed with category badge and headline. Clicking an insight shows detail or links to source conversation.

---

## Bonus Quick Wins (< 1 hour each)

| Change | File | Effort | Impact |
|--------|------|--------|--------|
| Add Shortcuts tab to Settings | `src/renderer/src/pages/Settings.tsx` + new tab component | 2h | P1 |
| Task grouping by date bucket | `src/renderer/src/pages/Tasks.tsx` | 2h | P1 |
| Add starred filter to Conversations | `src/renderer/src/pages/Conversations.tsx` | 1h | P1 |
| Show recording status bar in sidebar | `src/renderer/src/components/layout/Sidebar.tsx` | 2h | P1 |
| Enable Google integrations build flag | Build config / `.env` | 15m | P1 |
| Markdown rendering in chat messages | `src/renderer/src/components/chat/ChatMessages.tsx` | 1h | P1 |

---

## Build & Runtime Status

| Step | Status | Notes |
|------|--------|-------|
| `npm run typecheck` | ✅ Passes | Zero type errors across node + web tsconfigs |
| `npm run build:win` | ✅ Passes | Fixed: moved `three`/`@react-three/fiber`/`@react-three/drei` to devDependencies — they are Vite-bundled renderer packages and must not be in electron-builder's native module traversal |
| App launches after install | ✅ Fixed | Fixed: native Koffi module now included via `scripts/copy-koffi-native.mjs`. Root cause: pnpm `node-linker=hoisted` does not hoist optional scoped deps like `@koromix/koffi-win32-x64`; binary only lives in `.pnpm/` virtual store. Script copies `koffi.node` to `node_modules/koffi/build/koffi/win32_x64/` before packaging (already covered by `asarUnpack: node_modules/koffi/**`). |
| Installer produced | ✅ `dist/Omi for Windows-Setup-1.0.0.exe` | Signed, NSIS installer, per-user install |
| Branch | `feat/windows-track1-parity` | All changes on feature branch; not yet merged to `main` |

---

## What NOT to Change

- Do not rewrite the overlay window — it already has Acrylic/Mica and waveform, which macOS does not have natively in React.
- Do not change the 3D brain graph — it's a Windows-exclusive win over macOS's 2D canvas.
- Do not remove the Sticky Notes import — it's Windows-exclusive and shows platform depth.
- Do not restructure the Electron/React architecture — the framework split is correct and stable.
- Do not touch the OCR helper process — it works and is platform-appropriate.
