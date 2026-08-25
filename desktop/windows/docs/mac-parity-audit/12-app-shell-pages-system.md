# Mac→Windows Parity Audit — App Shell, Pages & System Integration

> Scope: app shell/navigation, dashboard/home, Apps marketplace, Conversations + LiveNotes + speaker ID, Permissions/Help pages, Settings section inventory, Spatial overlay, OS-level integration (diagnostics/telemetry/startup). Deep subsystems (tasks engine, memory extraction, rewind depth, chat/agents, bar, realtime voice, bluetooth, onboarding, file-index/KG) are owned by other agents — noted only as one-line cross-refs.
>
> Windows baseline checked: `src/renderer/src/pages/{Home,Apps,Conversations,ConversationDetail,LiveConversation,Rewind,Tasks,Goals,Memories,Settings,Login,Onboarding}.tsx`, `components/layout/{Sidebar,MainViews,PageHeader}.tsx`, `components/settings/tabs/{GeneralTab,AccountTab,PrivacyTab,RewindTab,IntegrationsTab,AdvancedTab}.tsx`, `App.tsx`, `src/main/{sentry.ts,updater.ts,lifecycle.ts,soak.ts}`.

## Summary table

| Feature/surface | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Apps marketplace core (browse/search/install) | `MainWindow/Pages/AppsPage.swift` | Present | — |
| Apps marketplace — Imports hub (Gmail, Calendar, Local Files, Apple Notes, X, ChatGPT/Claude memory-log paste) | `AppsPage.swift` `ImportsSection`/`ImportConnector.all` | Partial (`IntegrationsTab.tsx`: Sticky Notes + feature-flagged Google only) | H |
| Apps marketplace — Exports/MCP destinations hub (Claude, ChatGPT/Codex, OpenClaw, Hermes) | `AppsPage.swift` `ExportsSection` | Absent | M |
| Redesigned Home (data hub: stat ribbon, Connect-data panel, apps popup, capture/listening status buttons) | `Pages/DashboardPage.swift` `redesignedHome` | Absent (Windows Home is chat-only + 2 widgets) | M |
| Daily/Weekly Score gauge widget | `MainWindow/Components/DailyScoreWidget.swift` | Absent | L |
| Recent Conversations widget on Home | `MainWindow/Components/RecentConversationsWidget.swift` | Absent | L |
| LiveNotes — AI auto-generated notes during recording | `Sources/LiveNotes/*`, `Components/LiveNotesView.swift` | Absent | H |
| Speaker naming — post-hoc (transcript detail) | `Components/NameSpeakerSheet.swift` | Absent | H |
| Speaker naming — live (during active recording) | `Components/LiveNameSpeakerSheet.swift` | Absent | H |
| Permissions management page | `Pages/PermissionsPage.swift` | Absent (no dedicated page; permission prompts likely ad hoc) | M |
| Help / Crisp support chat | `MainWindow/HelpPage.swift`, `CrispManager.swift` | Absent | M |
| Spatial overlay (screen-anchored coach-mark for cloud connector setup) | `Sources/SpatialOverlay/*`, `CloudConnectorGuidanceOverlay.swift` | Absent | L |
| Trial / paywall gating UI | `AppState+TrialPaywall.swift`, `UsageLimitPopupView` | Absent (API types generated but unused; no gating) | M |
| Sentry heartbeat breadcrumb | `Telemetry/SentryHeartbeatTelemetry.swift` | Absent | L |
| Crash reporting (Sentry) | Sentry Cocoa SDK, app-wide | Present but thinner | — |
| Stress/diagnostics harness with release-gate taxonomy | `Diagnostics/DesktopStressDiagnostics.swift` | Partial (`soak.ts` — dev-only soak harness, no terminal-reason taxonomy/gate) | L |
| DMG/translocation self-install gate | `Startup/AppInstaller.swift` | N/A (Windows installer model differs — not a gap) | — |
| Settings sections | 11 sections (General, Rewind, Transcription, Notifications, Privacy, Account, Plan&Usage, AI Chat, Floating Bar, Shortcuts, Advanced, About) | 6 tabs (General, Account, Privacy, Rewind, Integrations, Advanced) | H |
| Settings search | `SettingsSidebar.swift` `SettingsSearchItem` (global fuzzy search across all settings) | Partial (`SettingsSearchProvider.tsx` exists — per-tab keyword search only, not a global omnibox) | M |
| Sidebar tier-gating / progressive unlock | `SidebarView.swift` `SidebarNavItem.requiredTier` | Absent (all nav items always visible) | L |

## App shell & navigation

**What it is:** The window chrome, sidebar, and top-level page router.

**Where (Mac):** `MainWindow/DesktopHomeView.swift` (root state machine: auth → onboarding → main), `MainWindow/SidebarView.swift` (nav rail), `MainWindow/SettingsSidebar.swift` (settings-mode sidebar swap).

**How it works:** A single `SidebarNavItem` enum drives 12 destinations (Home, Conversations, Chat, Memories, Tasks, Focus, Insight, Rewind, Apps, Settings, Permissions, Help). The sidebar is collapsible (drag handle + button), shows live status (audio-level bars on Conversations icon, pulsing record dot on Rewind icon), and has inline permission-repair rows (Screen Recording / Microphone / Accessibility) with Grant/Reset/Fix buttons directly in the sidebar footer — so permission problems surface without navigating anywhere. A `currentTierLevel` mechanism progressively unlocks nav items (used for staged onboarding rollouts) with a lock icon + "Unlocks at Tier N" tooltip. Settings is a full sidebar *replacement* (not a page push) with its own back button and a live element-highlight system (`highlightedSettingId`) driven by deep-links from other parts of the app.

**Windows status:** Present but structurally simpler. `Sidebar.tsx` has 5 nav items (Home, Conversations, Tasks, Rewind, Apps — Memories/Goals/Settings are reachable but not in the primary rail), collapsible, with inline Screen Recording / Microphone quick-toggles in the footer (no inline *repair* flow — just on/off). No tier-gating system. No in-sidebar permission-denied/broken/stale states with Grant/Reset/Fix actions — Mac's sidebar surfaces 3 distinct permission failure modes (denied, broken-but-granted, stale-after-update) each with a different action button; Windows shows on/off only.

**Value / notes:** M — the missing piece with real user impact is the lack of any in-line permission-repair affordance; a Windows user whose mic/screen-capture permission breaks has no equivalent quick-fix surface at all (see Permissions page below, which is fully absent).

## Dashboard / Home

**What it is:** The default landing page.

**Where (Mac):** `Pages/DashboardPage.swift` (~4,300 lines). Two coexisting designs behind an `@AppStorage("useLegacyHomeDesign")` flag: **legacy** (dashboard widgets + full chat thread, closer to what Windows has) and **redesigned** (current default) — a "hub/chat/connect" stage: a centered wordmark + stat ribbon (Conversations/Tasks/Memories/Screenshots counts, each a live nav shortcut) + an ask bar, which morphs in place into either an inline chat panel or a "Connect data" tray (two columns: import *sources* — Gmail/Calendar/Files/Notes/Omi Device — feeding an export *destinations* column — Ask Omi/Claude/ChatGPT/OpenClaw/Hermes). Also renders `DailyScoreWidget` (semicircle gauge, weekly task-completion %) and `RecentConversationsWidget` in the legacy layout.

**Windows status:** Absent/Partial. `pages/Home.tsx` is chat-first only: a greeting, an animated chat thread (Mac's legacy-mode shape, not the redesigned hub), a `ChatBar` with voice toggle, and two small widgets (`QuickTaskWidget`, `QuickGoalsWidget`). No stat ribbon/knowledge counts, no score gauge, no Recent Conversations widget, no in-place Connect-data tray, no Apps-popup-from-Home. Cross-ref: chat/agent behavior itself is chat-agent's area.

**Value / notes:** M — the widgets are cosmetic, but the "Connect data" hub (single place to wire up Gmail/Calendar/Notes → Omi, and Omi → Claude/ChatGPT) is a real discoverability gap; on Windows a user has to already know to visit Settings → Integrations or the Apps page.

## Apps marketplace

**What it is:** Browse/install/manage third-party "Omi apps" (chat personas, notification plugins, summary formatters) plus two special first-class sections: **Imports** (pull external data sources into Omi's memory) and **Exports** (push Omi's memory into other AI tools via MCP).

**Where (Mac):** `MainWindow/Pages/AppsPage.swift` (~3,400 lines).

**How it works:** Search + category filter + "Installed only" toggle, popularity-sorted grid sections (Featured/Other, Integrations, Realtime Notifications) each with a "See more" expansion, backed by `AppProvider`. Above the marketplace grid sit two fixed rows that are *not* part of the app catalog API:
- **Imports** (`ImportConnector.all`): Calendar, Email(Gmail), Local Files, Apple Notes, X(Twitter), ChatGPT-memory-paste, Claude-memory-paste. Each row shows live status (source count, memory count, last-synced-relative-time, delta since last sync) persisted via `ImportConnectorStatusStore` (UserDefaults-backed, with on-device probes for Local Files/Apple Notes). Runs survive the sheet closing (`ConnectorImportRunner` is a standalone actor).
- **Exports**: Claude/Claude Code, ChatGPT/Codex, OpenClaw, Hermes — each an MCP connection sheet with copy-paste config fields.

**Windows status:**
- Core marketplace grid (search, category filter multi-select, Marketplace/Installed tabs, install/uninstall toggle): **Present** — `pages/Apps.tsx` is a solid, comparable implementation (category chips, debounced search, optimistic install toggle).
- Imports hub: **Partial** — `IntegrationsTab.tsx` (in Settings, not Apps) has only Windows Sticky Notes (local, Windows-only equivalent of a note import) and Google (Gmail+Calendar combined) which is gated behind `VITE_ENABLE_GOOGLE_INTEGRATION` / a dev localStorage flag — i.e. off by default in shipped builds. No Local Files import row here (file indexing lives in Advanced tab / fileindex-kg's area — cross-ref only), no Apple Notes (N/A, no Windows equivalent exists), no X/Twitter import, no ChatGPT/Claude memory-log paste import.
- Exports/MCP destinations hub (Claude, ChatGPT/Codex, OpenClaw, Hermes): **Absent** — no UI anywhere lets a Windows user connect Omi's memory outward to another AI tool via MCP.

**Value / notes:** H for Imports (Gmail/Calendar/memory-log-paste are meaningful onboarding data sources entirely missing or dark-flagged) and M for Exports (a smaller but real gap — MCP export is how power users pipe Omi context into Claude Desktop/ChatGPT desktop).

## Conversations, LiveNotes & speaker identification

**What it is:** The conversation list/detail experience, live auto-note-taking during an active recording, and the ability to name/correct diarized speakers.

**Where (Mac):**
- List/detail: `Pages/ConversationsPage.swift`, `Pages/ConversationDetailView.swift`, `Components/{ConversationListView,ConversationRowView,LiveTranscriptView,TranscriptDetailView}.swift`.
- LiveNotes: `Sources/LiveNotes/{LiveNoteModels,LiveNotesAccumulator,LiveNotesMonitor,NoteStorage}.swift` + `Components/LiveNotesView.swift`.
- Speaker naming: `Components/SpeakerBubbleView.swift` (chat-bubble-style transcript render, clickable speaker label), `Components/NameSpeakerSheet.swift` (post-hoc, from a saved conversation's transcript), `Components/LiveNameSpeakerSheet.swift` (during active recording).

**How it works:**
- *LiveNotes* is a background pipeline independent of the raw transcript: a `LiveNotesAccumulator` buffers new transcript words (word-diffed per segment) and fires an AI note-generation request every 50 words (Gemini Flash, "3-10 word concise note" system prompt), which then feeds back into its own context so later notes don't repeat earlier ones. Notes are SQLite-persisted (`live_notes` table via `NoteStorage`, crash-recoverable), can be manually added/edited/deleted, and are rendered in a live-scrolling side panel (`LiveNotesView`) with an AI on/off toggle and a generating spinner. This is a genuinely distinct feature from the raw transcript — it's a running "meeting minutes" summary, not a copy of what was said.
- *Speaker naming* — both sheets present the tapped speaker's sample text, a chip-grid of known `Person`s ("You" + existing people + "+ Add Person" inline create with duplicate-name validation), and an option to retroactively tag *all* other segments from the same speaker in one action. The live variant explicitly notes the name "will be saved when the conversation ends." `SpeakerBubbleView` renders transcript segments as chat bubbles color-keyed per speaker ID, with the speaker label itself clickable (pencil icon affordance) to open the naming sheet.

**Windows status:**
- Conversation list/detail: **Present**, comparable structure (`pages/Conversations.tsx` is owned by wal-sync/other agents for sync semantics — not re-audited here; only the UI shell was checked).
- LiveNotes: **Absent** — grep across `LiveConversation.tsx` and `ConversationDetail.tsx` found zero references to any note-generation concept; only raw transcript segments exist (`pages/LiveConversation.tsx`, `components/TranscriptPopup.tsx`).
- Speaker naming (both live and post-hoc): **Absent** — `ConversationDetail.tsx` renders segments with a `speaker` string (`SPEAKER_00` etc.) as a colored uppercase badge (`speakerColor()` hash-based coloring) but there is no tap/click handler, no naming sheet, no `Person` chip picker, and no API call wiring to assign a name to a speaker anywhere in the renderer. Diarization labels are permanently opaque IDs on Windows.

**Value / notes:** H for both — LiveNotes is a distinctive, marketed differentiator (auto meeting-minutes) entirely missing from Windows, and speaker naming is core usability for any multi-person conversation (without it, transcripts stay "SPEAKER_00 / SPEAKER_01" forever with no way to fix misattributions or add names).

## Permissions & Help pages

**What it is:** A dedicated in-app permissions-repair page, and a dedicated in-app support-chat page.

**Where (Mac):** `Pages/PermissionsPage.swift` (~1,140 lines), `MainWindow/HelpPage.swift` + `MainWindow/CrispManager.swift`.

**How it works:**
- *Permissions*: one expandable card per permission (Microphone, Screen Recording, System Audio [macOS 14.4+ Core Audio tap test], Notifications), each showing granted/denied/not-determined/stale/broken state with tailored recovery flows — e.g. Microphone-denied shows three parallel recovery options (quick programmatic reset+restart, a "open Terminal" tmux-style manual reset command, or manual System Settings instructions with an annotated screenshot); Screen-Recording-stale (post-update TCC breakage) walks through remove-and-re-grant with numbered steps and inline action buttons at each step.
- *Help*: a full-page embedded Crisp live-chat widget (`WKWebView`, pre-filled with the user's email/name). `CrispManager` separately polls for unread operator replies on app-activation/Cmd+R (no timer), fires a macOS notification "Help from Founder" per new message, and badges the sidebar Help icon with an unread count.

**Windows status:** Absent — no dedicated Permissions page exists (sidebar has raw on/off toggles only, no repair flows for denied/stale states), and no Help/Crisp support-chat surface exists anywhere in the app (confirmed via grep for "crisp"/"Help from Founder" — zero hits).

**Value / notes:** M — Permissions-page absence compounds the sidebar gap above (no path at all to recover from a stuck/denied permission beyond OS Settings knowledge the user must already have). Help/Crisp absence means Windows users have no in-app support channel; this may be an intentional scope decision (Crisp is a specific vendor choice) rather than a build gap — worth confirming with product before treating as a build task.

## Spatial overlay

**What it is:** A screen-anchored coach-mark/arrow-callout system that visually points at a specific button in *another app's window* (not Omi's own UI) to guide the user through a manual setup step it can't do for them.

**Where (Mac):** `Sources/SpatialOverlay/{SpatialOverlayCore,SpatialOverlayGeometry,SpatialOverlayRenderGeometry,SpatialOverlayResolver,SpatialOverlayDogfood}.swift`, consumed by `CloudConnectorGuidanceOverlay.swift`.

**How it works:** A geometry/placement solver (`SpatialOverlayPlacementSolver`) takes a target rect (found via Accessibility API, OCR, `CGWindowList`, or layout heuristics, each tagged with a confidence score) plus a set of screen exclusion zones (menu bar, dock, notch, Omi's own floating bar/agent pills) and computes where to draw a callout panel + arrow so the arrow tip lands exactly on the target without covering it or a hard-excluded zone, picking the best-scoring edge (above/below/leading/trailing) after clamping to the visible screen area. `SpatialOverlayDogfood` is a self-test oracle that validates arrow-to-target distance and panel/target overlap for known fixtures (e.g. pointing at Claude Desktop's "Add" or "Connect" MCP-server buttons during the assisted cloud-connector flow — see `CloudConnectorFormAutomation.swift`). In practice this is the mechanism behind "point at the exact button in Claude Desktop you need to click" during MCP setup guidance.

**Windows status:** Absent — no equivalent concept anywhere in the renderer or main process (grep for spatial/overlay-guidance/coach-mark: no hits beyond unrelated orb-shader code).

**Value / notes:** L for general product parity (niche, used only in one guided-setup flow) — but it is the visual mechanism *behind* the Exports/MCP-connector setup gap noted above, so if Windows ever adds MCP export destinations, this (or a simpler substitute like a static screenshot) would need to be designed alongside it.

## Trial / paywall

**What it is:** Client-side usage-limit gating with an upgrade modal.

**Where (Mac):** `AppState+TrialPaywall.swift` (`isPaywalledEffective`, `blockIfPaywalled(reason:)` gate called at the entry point of every $-cost toggle — transcription, screen analysis, proactive monitoring), `UsageLimitPopupView` (shown via `.showUsageLimitPopup` notification, offers Upgrade / BYOK / Dismiss).

**Windows status:** Absent as a gating mechanism. The generated API client (`omiApi.generated.ts`) includes the `PaywallStatusResponse`/`TrialMetadata` types and the `/v1/users/me/paywall` and `/v1/users/me/trial` endpoint bindings (auto-generated from the shared OpenAPI schema), but grep found zero call sites or UI consuming them — no popup, no feature blocking, no BYOK-exemption check.

**Value / notes:** M — this may be an intentional product decision (Windows could be unmetered/BYOK-only, or trial enforcement may be server-side only for this platform) rather than a build gap; flag for product confirmation rather than assuming it needs building.

## Diagnostics / telemetry / startup

**What it is:** Crash reporting, low-noise session heartbeats, and a structured stress-test harness with a release-gate taxonomy.

**Where (Mac):** `Telemetry/SentryHeartbeatTelemetry.swift` (a breadcrumb-only heartbeat — explicitly must never call `SentrySDK.capture(message:)`, see code comment referencing issue #9191), `Diagnostics/DesktopStressDiagnostics.swift` (defines `DesktopStressScenario`/`DesktopStressTerminalReason` enums distinguishing expected outcomes like `pttVoicedSuccess` from `isReleaseGateFailure` outcomes like `audioFramesMissing`/`bridgeLaunchFailure`; `DesktopStressRunSummary` computes `passedReleaseGate` from a batch of events — this is a shipped/CI-facing gate, not just a dev tool), `Startup/AppInstaller.swift` (DMG/App-Translocation self-relocate-to-`/Applications` + relaunch, fixing TCC permission grants that don't stick under translocation), `Startup/StartupWarmupPolicy.swift` (staggered delay policy for service/database/dashboard/chat-context/MCP-key warmups so nothing contends with app launch).

**Windows status:**
- Crash reporting: **Present but thinner** — `src/main/sentry.ts` (41 lines) does DSN-gated init, packaged-only enablement, and PII scrubbing (Authorization/Cookie headers, email) comparable in spirit to Mac's scrubbing but without a renderer-side heartbeat breadcrumb equivalent.
- Heartbeat telemetry: **Absent** (grep for "heartbeat": no hits).
- Stress/diagnostics harness: **Partial** — `src/main/soak.ts` (41 lines) exists and is actively used per project notes (an untracked `soak-report.json` was present at session start, and CLAUDE.local.md references an "8h idle soak" for Phase 2 testing), but it reads as a dev-only soak-testing utility, not a shipped scenario/terminal-reason taxonomy with a `passedReleaseGate` computation like Mac's `DesktopStressDiagnostics`.
- DMG/translocation self-install gate: **N/A** — Windows has no DMG-equivalent installer-mount problem (NSIS/MSI install model is fundamentally different), so this is not a real gap, just a platform difference.
- Startup warmup staggering: not independently verified this pass (would need `lifecycle.ts`/`index.ts` deep-read) — noting as unverified rather than claiming absent.

**Value / notes:** L — these are internal-facing systems with no direct user-visible impact; only worth prioritizing if Windows release quality bars start requiring the same automated release-gate evidence Mac's CI produces.

## Settings section inventory

**Mac** (`SettingsSidebar.swift` `visibleSections`, 11 total): General, Rewind, Transcription, Notifications, Privacy, Account, Plan and Usage, Floating Bar, Shortcuts, Advanced, About. (AI Chat section exists in the enum but is explicitly hidden — `EmptyView()` — so not counted as user-visible.) Plus a **global fuzzy settings search** (`SettingsSearchItem.allSearchableItems`, ~50+ indexed items across every section, searches name+subtitle+keywords) that jumps straight to and highlights the matched control.

**Windows** (`components/settings/tabs/`, 6 total): General, Account, Privacy, Rewind, Integrations, Advanced. No dedicated Transcription section (language/vocabulary controls, if present, are folded elsewhere or absent — not verified this pass, cross-ref transcription/voice work to realtime-voice's area), no dedicated Notifications section, no Plan & Usage/billing section, no dedicated Floating Bar section, no dedicated Shortcuts section (a single "Record hotkey" row lives in General instead), no About section (version/update-channel info folds into General's "Update ready" row instead of a dedicated page). Settings search exists (`SettingsSearchProvider.tsx`) but scoped to keyword-matching within visible rows, not a global omnibox with deep-link highlighting across all sections.

**Value / notes:** H — this is the largest single gap by count. Missing sections that likely matter most: **Notifications** (no user control over notification frequency/categories at all), **Shortcuts** (only one hotkey is configurable vs. Mac's PTT/Ask-Omi/double-tap-lock/sound-feedback cluster), and **About/versioning** (no dedicated update-channel or version-info surface). Plan & Usage absence is consistent with the Trial/Paywall absence noted above (likely the same product decision, not two separate gaps).

## Spotted outside my scope

- Chat/agent behavior on Home (`ChatBar`, `VoiceSessionSurface`) — chat-agent's area.
- File indexing / knowledge graph (`fileIndex/`, `kgSynthesis`, Memories page's brain-map) — fileindex-kg's area.
- Floating top-edge bar (`components/layout` bar route, `BarApp`) and Orb component — floating-bar's area.
- Realtime voice session internals (`lib/voice/*`) — realtime-voice's area.
- Rewind depth (capture cadence, retention, excluded apps beyond the settings-row inventory above) — rewind's area.
- Tasks/Goals engine internals — tasks-goals's area.
- Onboarding flow internals — onboarding's area.
- Bluetooth/device pairing — bluetooth's area.
- Conversation sync/merge/outbox correctness (`lib/sync/*`) — wal-sync's area; only the UI shell of Conversations/ConversationDetail was reviewed here.
