# Mac→Windows Parity Audit — App Shell, Pages & System Integration

> **Re-audit date: 2026-08-22.** This is a full re-verification against current source, not a diff of the 2026-08-20 version — every claim below was re-checked against the files cited, and every citation was re-read (not trusted because a line number existed). See "Changed since the 2026-08-20 audit" for what moved.
>
> Scope: app shell/navigation, dashboard/home, Apps marketplace, Conversations + LiveNotes + speaker ID, Permissions/Help pages, Settings section inventory, Spatial overlay, OS-level integration (diagnostics/telemetry/startup). Deep subsystems (tasks engine, memory extraction, rewind depth, chat/agents, bar, realtime voice, bluetooth, onboarding, file-index/KG) are owned by other agents — noted only as one-line cross-refs.
>
> Windows baseline checked: `src/renderer/src/pages/{Home,LegacyHome,Apps,Conversations,ConversationDetail,LiveConversation,Rewind,Tasks,Goals,Memories,Insights,Settings,Login,Onboarding,KnowledgeGraph}.tsx`, `components/layout/{Sidebar,MainViews,PageHeader,AppChrome}.tsx`, `components/home/hub/*` (HomeHub, connections/*), `components/settings/tabs/{GeneralTab,AgentsTab,TranscriptionTab,RewindTab,NotificationsTab,PrivacyTab,AccountTab,PlanUsageTab,ShortcutsTab,AdvancedTab,AboutTab,IntegrationsTab}.tsx`, `components/settings/{SettingsTabRail,SettingsTabPanel,SettingsSearchProvider,SettingRow}.tsx`, `components/conversations/NameSpeakerModal.tsx`, `lib/liveNotes/*`, `lib/chatQuotaGate.ts`, `lib/billing.ts`, `routes/manifest.ts`, `App.tsx`, `src/main/{sentry.ts,crashSentinel.ts,updater.ts,lifecycle.ts,soak.ts,startupScheduler.ts,billing/checkoutWindow.ts}`.

## Changed since the 2026-08-20 audit

The single biggest lesson from this pass: most of what the old audit called "Absent" wasn't a wave-14-onward gap that shipped *after* the audit — it was already sitting in the tree, in several cases weeks before the audit's own commit (`66e150275c`, 2026-07-13). The audit's "Windows status" column was wrong at the time it was written for at least seven of its ~16 rows, not merely stale. Concretely:

1. **Home is no longer chat-only — the redesigned "Hub" is the shipped default.** `pages/Home.tsx` is now a two-line switch: `useLegacyHomeDesign` picks between the old chat-first screen (renamed `LegacyHome.tsx`, unchanged in spirit — this is what the old audit actually reviewed and called the *only* Windows Home) and `HomeHub`/`HomeHub.tsx`, the DashboardPage port, which is now the default (`Home.tsx:15`, `getPreferences().useLegacyHomeDesign ?? false`). Shipped 2026-07-14 (`b93db2c7ef`). This directly overturns the "Redesigned Home: Absent" row.
2. **The Imports hub and the Exports/MCP hub both exist now**, as the Hub's "Connect" stage (`components/home/hub/connections/ConnectionsPanel.tsx`): Calendar, Gmail, Sticky Notes (Windows' Apple-Notes equivalent), X/Twitter, and ChatGPT/Claude memory-log paste on the import side; real MCP config connectors + cloud OAuth connectors for Claude/Claude Code, ChatGPT/Codex, OpenClaw, and Hermes on the export side (`McpExportDetail.tsx`, `McpConfigConnectorRow.tsx`, `McpCloudConnectorCard.tsx`), plus Windows-exclusive one-shot Obsidian/Markdown/Notion memory export (`ExportsConnector.tsx`) that has no Mac equivalent at all. This overturns both the "Imports: Partial" and "Exports: Absent" rows — the H/M gaps the old audit flagged as the biggest Apps-marketplace issue are gone.
3. **LiveNotes is fully ported** (`lib/liveNotes/liveNotesAccumulator.ts`, word-threshold-50 policy exactly matching Mac's constants; `components/recording/LiveNotesPanel.tsx`; SQLite-backed via `main/ipc/liveNotesStore.ts`), shipped 2026-07-14 (`9956fa419b`, `59dea77c18`). Overturns "LiveNotes: Absent, H."
4. **Post-hoc speaker naming is fully ported** (`components/conversations/NameSpeakerModal.tsx`, a line-for-line-faithful port of `NameSpeakerSheet.swift` down to the 120-char preview truncation and the default-on "tag N others" toggle), shipped 2026-07-14 (`dfad6500f3`, `ada17b00cc`). **Live speaker naming (during an active recording) remains genuinely absent** — this half of the old "H" row is still a real gap.
5. **Trial/paywall gating is fully built and wired**, not "types generated but unused" as the old audit found: `components/settings/tabs/PlanUsageTab.tsx` (subscription/trial/overage/checkout), `main/billing/checkoutWindow.ts` (real Stripe checkout window), `components/settings/billing/UsageLimitPopup.tsx` (a faithful port of `UsageLimitPopupView`, three reasons: transcription/chat/trial_expired, Upgrade + BYOK actions), and `lib/chatQuotaGate.ts` (a client-side pre-send gate matching Mac's `FloatingBarUsageLimiter`, fail-open on network errors exactly like Mac). Shipped 2026-07-13 (`9d0edb5fbf`). This overturns "Trial/paywall: Absent" entirely — it was never a product-decision question, it just hadn't been checked closely enough.
6. **Settings grew from 6 tabs to 12**, adding Notifications, Transcription, Plan & Usage, Shortcuts, About, and **Agents** (a tab the old audit never mentioned at all, and which predates the audit's own commit by five weeks — `3ef708cdb7`, 2026-07-08). The "largest single gap by count" framing from the old audit no longer holds; see the Settings section below for what's actually still missing.
7. **Settings search is now a real cross-section search**, not "per-tab keyword search only": every tab's rows stay mounted and registered in one shared registry (`SettingsSearchProvider.tsx`), and a query shows every matching row across every tab simultaneously with the tab label as a group header (`SettingsTabPanel.tsx`). It still doesn't scroll-to/glow a specific control the way Mac's `highlightedSettingId` does, so it's not full parity — but it's no longer accurately described as tab-scoped.
8. **Startup warmup staggering exists and is substantial** (`main/startupScheduler.ts`, `scheduleStartupSteps` in `main/index.ts:1150`) — 17 named steps deferred to `ready-to-show`, plus three more `setTimeout`-deferred warmups. The old audit correctly declined to guess here ("not independently verified"); it is Present.
9. **A new, unrelated crash-detection mechanism exists**: `main/crashSentinel.ts`, a clean-shutdown sentinel that reports a Sentry *message* (not exception) when the previous session never reached its quit path — this is functionally close to Mac's `AnalyticsManager.detectAndReportCrash`, which the old audit didn't mention at all (it only checked for the separate heartbeat-breadcrumb feature). The heartbeat breadcrumb itself is still absent; this is a different, also-real, feature that happens to close some of the same telemetry gap.
10. **New, unaudited page: a persistent Insights history page** (`pages/Insights.tsx`, 306 lines, category filters + search + expandable rows, shipped 2026-07-16) now has its own sidebar-adjacent nav slot in `routes/manifest.ts` (6th nav item). No Mac equivalent page was found this pass — Mac's insight history (`InsightStorage.insightHistory`) is read inline by `DashboardPage.swift`, not as a standalone page — so this may be a Windows-side addition rather than a gap; flagged for confirmation, not scored.
11. **New Mac-side feature the old Mac citations didn't have to account for**: Mac shipped a referral/signup-first-redemption settings section on 2026-08-20/08-21 (`a67b0a6a99`, `640830e94f`) and folded Permissions into the Settings sidebar itself (`.permissions` is now also a `visibleSections` entry, not only a standalone `SidebarNavItem`) on 2026-08-14. Windows has no referral UI at all (grep for "referral" outside generated API types/analytics turns up nothing). Adding as a new low-value gap row.

Net: of the ~16 rows in the old table, **9 changed status** in this pass (6 flipped from a real gap to Present, 1 split into "half fixed, half still a gap" (speaker naming), 1 gained new nuance without changing verdict (Sentry), and 1 is a wholly new row (referral)). The single most significant correction is #5 (Trial/paywall) combined with #2 (Imports/Exports hub): the old audit treated both as open questions for product to weigh in on, when in fact the code was already fully built, wired, and shipped weeks before the audit was written.

## Summary table

| Feature/surface | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Apps marketplace core (browse/search/install/detail/reviews) | `MainWindow/Pages/AppsPage.swift` | Present (`pages/Apps.tsx`, 939 lines — detail sheet + reviews added 2026-07-16; real paid-app purchase flow added, which exceeds Mac) | — |
| Home Hub — Imports (Gmail, Calendar, Sticky Notes, X, ChatGPT/Claude memory-log paste) | `AppsPage.swift`/`DashboardPage.swift` `ImportConnector.all` | **Present** (`components/home/hub/connections/ConnectionsPanel.tsx`, "imports" view) — Gmail via session-cookie lane ships on by default (2026-07-17); Gmail via loopback-OAuth lane and the Settings→Integrations "Google" row stay build-flag-gated; Calendar (backend OAuth) and Sticky Notes are ungated | — (was H) |
| Home Hub — Exports/MCP destinations (Claude, ChatGPT/Codex, OpenClaw, Hermes) + Obsidian/MD/Notion one-shot export | `AppsPage.swift` `ExportsSection` | **Present** (`connections/McpExportDetail.tsx`, `ExportsConnector.tsx`) — real MCP config + cloud connectors; Obsidian/Notion export has no Mac equivalent | — (was M) |
| Redesigned Home (Hub: stat ribbon, ask bar, Connect-data tray) | `Pages/DashboardPage.swift` `redesignedHome` | **Present and default** (`pages/Home.tsx` → `HomeHub`); `useLegacyHomeDesign` flag brings back the old chat-first screen, mirroring Mac's own flag | — (was M) |
| Daily/Weekly Score gauge widget | `MainWindow/Components/DailyScoreWidget.swift` | Absent (still) | L |
| Recent Conversations widget on Home | `MainWindow/Components/RecentConversationsWidget.swift` | Absent (still) | L |
| LiveNotes — AI auto-generated notes during recording | `Sources/LiveNotes/*`, `Components/LiveNotesView.swift` | **Present** (`lib/liveNotes/*`, `components/recording/LiveNotesPanel.tsx`) — word-threshold-50 policy matches Mac's constants exactly | — (was H) |
| Speaker naming — post-hoc (transcript detail) | `Components/NameSpeakerSheet.swift` | **Present** (`components/conversations/NameSpeakerModal.tsx`) — faithful port | — (was H) |
| Speaker naming — live (during active recording) | `Components/LiveNameSpeakerSheet.swift` | Absent (still) — `LiveConversation.tsx` renders the speaker label as static text, no tap handler | H |
| Permissions management page | `Pages/PermissionsPage.swift` (now also a Settings-sidebar section, since 2026-08-14) | Absent (still) — sidebar footer has on/off toggles only, no repair flow for denied/broken/stale states | M |
| Help / Crisp support chat | `MainWindow/HelpPage.swift`, `CrispManager.swift` | Absent (still — grep confirms zero hits) | M |
| Spatial overlay (screen-anchored coach-mark) | `Sources/SpatialOverlay/*` | Absent (still) | L |
| Trial / paywall gating UI | `AppState+TrialPaywall.swift`, `UsageLimitPopupView` | **Present** (`PlanUsageTab.tsx`, `UsageLimitPopup.tsx`, `chatQuotaGate.ts`, `main/billing/checkoutWindow.ts`) — full Stripe checkout, quota gate, upgrade/BYOK popup | — (was M, treated as open) |
| Sentry heartbeat breadcrumb | `Telemetry/SentryHeartbeatTelemetry.swift` | Absent (still, as a periodic breadcrumb) — but a related boot-time crash-detection sentinel now exists (`main/crashSentinel.ts`), closer to Mac's separate `detectAndReportCrash` | L |
| Crash reporting (Sentry) | Sentry Cocoa SDK, app-wide | Present, thicker than before — `captureError`/`captureMessage` helpers + PII scrub (`sentry.ts`, 71 lines, up from 41) | — |
| Stress/diagnostics harness with release-gate taxonomy | `Diagnostics/DesktopStressDiagnostics.swift` | Partial (unchanged) — `soak.ts` (41 lines) is still a dev-only, `OMI_SOAK=1`-gated metrics sampler, no terminal-reason taxonomy/gate | L |
| DMG/translocation self-install gate | `Startup/AppInstaller.swift` | N/A (unchanged — platform difference, not a gap) | — |
| Startup warmup staggering | `Startup/StartupWarmupPolicy.swift` | **Present** (`main/startupScheduler.ts`, 17 staggered steps + 3 deferred timeouts in `main/index.ts:1150-1266`) | — (was "unverified") |
| Settings sections | 11 visible sections (General, Account, Transcription, Rewind, Floating Bar, Notifications, Permissions, Shortcuts, Advanced, Referral, About — Plan&Usage/Privacy absorbed into Account/Notifications; AI Chat hidden) | 12 tabs (General, Memories, Agents, Transcription, Rewind, Notifications, Privacy, Account, Plan & Usage, Shortcuts, Advanced, About) | M (was H) |
| Settings search | `SettingsSidebar.swift` `SettingsSearchItem` — global fuzzy search, jumps to and highlights the matched control | **Improved**: genuinely cross-tab now (`SettingsSearchProvider.tsx` registry spans all tabs, shows every matching row with its tab as a group header) — but still no scroll-to/highlight of the specific control | L (was M) |
| Sidebar tier-gating / progressive unlock | `SidebarView.swift` `SidebarNavItem.requiredTier` | Absent (still) — no tier field anywhere in `routes/manifest.ts` | L |
| Insights history page (new, unaudited) | No dedicated page found (`InsightStorage.insightHistory` read inline by `DashboardPage.swift`) | Present (`pages/Insights.tsx`) — own nav slot, category filters, search | — (informational, not scored) |
| Referral program / signup-first redemption (new) | `SettingsSidebar.swift` `.referral` (added 2026-08-20/21) | Absent | L |

## App shell & navigation

**What it is:** The window chrome, sidebar, and top-level page router.

**Where (Mac):** `MainWindow/DesktopHomeView.swift`, `MainWindow/SidebarView.swift`, `MainWindow/SettingsSidebar.swift`.

**How it works (Mac, re-confirmed):** A `SidebarNavItem` enum drives the nav rail; the sidebar shows live status and inline permission-repair rows with Grant/Reset/Fix actions. `currentTierLevel` progressively unlocks nav items. Settings is a sidebar *replacement* with `highlightedSettingId` deep-link highlighting. One correction to the Mac citation itself: `SettingsSidebar.swift`'s `visibleSections` has changed shape since the old audit — `.account` now also renders `.planUsage` content and `.notifications` now also renders `.privacy` content (both absorbed, still routable for deep links), and `.permissions` is now itself a visible Settings section in addition to remaining a top-level `SidebarNavItem` (`SettingsSidebar.swift:390-401`, changed 2026-08-14 in `2d6b4ecd26`, "calm the Permissions settings page"). `PermissionsPage.swift` itself grew from ~1,140 to 1,495 lines over the same period — the old audit's line count is stale.

**Windows status:** Present, still structurally simpler than Mac, but with real changes since the old audit:
- The nav rail is now driven by a single route manifest (`routes/manifest.ts`) rather than hardcoded JSX — a refactor, not a feature change, but it means "5 nav items" is now wrong: there are **6** (Home, Conversations, Tasks, Rewind, Apps, **Insights**), with Memories/Goals/Settings still reachable but rail-less (`routeManifest`, `navRoutes()`).
- Sidebar footer (`components/layout/Sidebar.tsx:236-239`) still has exactly two on/off toggles (Screen recording, Microphone) — no repair flow for denied/broken/stale permission states, and `main/ipc/micPermission.ts` (real registry-backed mic-permission detection, added for onboarding) is read-only detection with no in-sidebar fix action wired to it.
- No tier-gating system anywhere in the manifest (`RouteNav`/`RouteEntry` types have no tier field).

**Value / notes:** M — unchanged from the old audit's reasoning: the missing piece is still the lack of any in-line permission-repair affordance. This is now compounded by the fact that Mac's own Permissions surface got *more* prominent (folded into Settings too) while Windows' equivalent didn't move at all.

## Dashboard / Home

**What it is:** The default landing page.

**Where (Mac):** `Pages/DashboardPage.swift`. Unchanged structurally since the old audit (last touched 2026-08-17, unrelated nudge-throttling fix) — the `useLegacyHomeDesign` / redesigned-Home duality the old audit described is still accurate on the Mac side.

**Windows status — corrected from "Absent/Partial" to Present-and-default:** `pages/Home.tsx` is now a 19-line switch (`getPreferences().useLegacyHomeDesign ?? false ? <LegacyHome/> : <HomeHub/>`), landed 2026-07-14 (`b93db2c7ef`, "the Hub — Mac-parity Home"). `HomeHub.tsx` (333 lines) implements the same three-mode stage Mac has — resting `hub` (wordmark + `HubStatRibbon.tsx` + ask bar), `chat` (`HubChatPanel.tsx`), and `connect` (`HubConnectPanel.tsx` → `ConnectionsPanel.tsx`) — with layout constants explicitly ported from Mac's pixel values (`HomeHub.tsx:24-58` cites `DashboardPage.swift` line numbers for each constant, including two documented deliberate deviations). `LegacyHome.tsx` (565 lines) is what the old audit reviewed and called "the only Windows Home" — it still exists, just demoted to an opt-out.

What's still genuinely missing from the redesigned Home: the `DailyScoreWidget` semicircle gauge and the `RecentConversationsWidget` — grep for both concepts across `components/home/**` finds nothing. The resting-hub widget slot (`hubHomeWidgetsSlot.ts`) currently holds only `HomeGoalsChips`, a focused-goals chip row — not a score gauge or a conversations list.

**Value / notes:** L for the two still-missing widgets (cosmetic, matches old audit's reasoning) — but the far larger M-value item the old audit flagged (the Connect-data hub as a discoverability problem) is resolved: it's now the default landing surface's own "connect" mode, not something a user has to already know to seek out in Settings.

## Apps marketplace, and the Home Hub's Connect tray

**What it is:** Browse/install/manage third-party "Omi apps," plus the Imports (pull external data in) and Exports (push Omi memory out via MCP) surfaces — which on Windows now live in the Home Hub rather than the Apps page, unlike Mac where both live inside `AppsPage.swift` (as well as inside `DashboardPage.swift`'s redesigned Home, which is where Windows' equivalent actually sits).

**Where (Mac):** `MainWindow/Pages/AppsPage.swift` (`ImportsSection`/`ExportsSection`, still present, last touched 2026-08-17) plus `DashboardPage.swift`'s `redesignedHome` (which also renders an import/export tray — the same duality Windows now mirrors).

**Windows status:**
- Core marketplace grid: **Present**, and grown since the old audit — `pages/Apps.tsx` (939 lines) added an app-detail sheet + reviews (2026-07-16, `e201748e47`) and real paid-app purchase handling that Mac doesn't have (`705331cb55`, "beyond macOS").
- Imports: **Present**, via `components/home/hub/connections/ConnectionsPanel.tsx`'s "imports" view — `CalendarConnector.tsx` (backend-mediated OAuth, ungated), `GmailConnector.tsx` (client-side loopback-OAuth lane, still gated by `VITE_ENABLE_GOOGLE_INTEGRATION` — "Requires setup" fallback when unset), `StickyNotesConnector.tsx` (Windows' Apple-Notes equivalent, ungated), `XConnector.tsx` (a real running main-process connector with streamed progress, `main/integrations/xConnector.ts` — not the "Absent" the old audit found), and `PasteImportConnector.tsx` for both `source="chatgpt"` and `source="claude"`. Separately, `components/settings/tabs/IntegrationsTab.tsx` ships a *second*, default-on Gmail lane — "Gmail (session)," a cookie-replay connector shipped 2026-07-17 (`c0240f4839`) specifically because the loopback-OAuth lane needs a compiled-in client id most builds don't have. Net effect: Gmail import works out of the box on a shipped build via the session lane in Settings, even though the Hub's own Gmail card still shows "Requires setup" unless the OAuth flag is set — a real seam between the two surfaces worth closing, but not the blanket "off by default" the old audit found.
- Exports/MCP destinations: **Present** — `McpExportDetail.tsx` renders, per destination, the real config-writing connector (`McpConfigConnectorRow.tsx`, backed by `shared/mcpExports.ts`'s `MCP_CONFIG_CONNECTORS`) and, for Claude/ChatGPT, an additional cloud OAuth connector (`McpCloudConnectorCard.tsx`) plus a memory-pack row (`MemoryPackRow.tsx`). `ExportsConnector.tsx` additionally ships one-shot Obsidian/plain-Markdown/Notion memory exports (`main/memoryExport/{obsidian,plainFile,notion}.ts`) that have no Mac equivalent — a Windows-exclusive addition, not a gap.

**Value / notes:** These were H (Imports) and M (Exports) gaps in the old audit; both are now built and shipped (Exports since at least 2026-06-11 per `memoryExport/format.ts`'s original commit, Imports' Hub surface since 2026-07-14+). The one real remaining seam is the Gmail loopback-vs-session lane split noted above — worth a follow-up ticket, not a parity gap.

## Conversations, LiveNotes & speaker identification

**What it is:** The conversation list/detail experience, live auto-note-taking during an active recording, and naming/correcting diarized speakers.

**Where (Mac):** `Pages/ConversationsPage.swift`, `Pages/ConversationDetailView.swift`; `Sources/LiveNotes/*`; `Components/{NameSpeakerSheet,LiveNameSpeakerSheet,SpeakerBubbleView}.swift`. No changes found to these Mac files since the old audit beyond routine touches — the old Mac citations hold up.

**Windows status:**
- Conversation list/detail: Present, unchanged assessment (still primarily wal-sync's area for sync semantics).
- LiveNotes: **Present**, corrected from "Absent" — `lib/liveNotes/liveNotesAccumulator.ts` (146 lines) is a pure, directly-unit-tested port of `LiveNotesAccumulator.swift`: word-count-triggered (not time-triggered) generation, `DEFAULT_WORD_THRESHOLD = 50` matching Mac's constant exactly (cited from `LiveNotesAccumulator.swift:23-25`), a 500-word max buffer, 20-note max context. `components/recording/LiveNotesPanel.tsx` (189 lines) and `LiveNotesHost.tsx` render it live inside `LiveConversation.tsx` in a two-column split (transcript left, notes right) mirroring Mac's expanded-transcript view. Persistence is via `main/ipc/liveNotesStore.ts`, SQLite-backed like Mac's `NoteStorage`. Shipped 2026-07-14 (`9956fa419b`, `59dea77c18`).
- Speaker naming (post-hoc): **Present**, corrected from "Absent" — `components/conversations/NameSpeakerModal.tsx` (242 lines) is an explicit, line-cited port of `NameSpeakerSheet.swift`: same 120-char preview truncation, same chip-grid ("You" + known `Person`s + "+ Add Person" with inline create), same default-on "also tag N other segments from this speaker" toggle, same person-scope semantics (account-wide, not conversation-scoped). It also adds an honest failure mode Mac doesn't need to handle — an "unaddressable" state when a conversation is still syncing and segment ids aren't real yet. Wired from `ConversationDetail.tsx:795,803`. Shipped 2026-07-14 (`dfad6500f3`, `ada17b00cc`).
- Speaker naming (live, during active recording): **Still Absent.** `pages/LiveConversation.tsx` renders each segment's speaker as a static badge (`{s.speaker || 'speaker'}`, line 105) with no click handler, no modal, and no wiring to `NameSpeakerModal` or any live equivalent of `LiveNameSpeakerSheet.swift`. This half of the old "H" gap is real and unaddressed.

**Value / notes:** The old audit's H rating was earned by two features that turned out to already be shipped (LiveNotes, post-hoc naming) and one that's still missing (live naming). Net H value remaining is now solely "you can't name a speaker while they're still talking" — real, but a narrower gap than the old audit described.

## Insights history page (new, not in the old audit)

**What it is:** A dedicated, searchable, category-filterable history of proactive "Insight" notifications (productivity/communication/learning/health/other), reachable from its own sidebar-adjacent nav entry.

**Where (Windows):** `pages/Insights.tsx` (306 lines), registered in `routes/manifest.ts` with `nav: { label: 'Insights', Icon: Lightbulb, order: 5 }` — a genuine sixth item in the primary nav rail. Backed by `main/insight/{toastWindow,notification,state}.ts` for the underlying toast/notification engine (that engine's internals are a proactive-assistants concern, out of scope here — this section only covers the history *page*). Shipped 2026-07-16 (`3a96af7967`), perf-tuned 2026-07-19 (`d04e9008ca`).

**Mac comparison:** No dedicated Mac page was found. Mac's insight history (`InsightStorage.insightHistory`) is read directly by `DashboardPage.swift:940`, i.e. surfaced inline in the dashboard rather than as its own page/route. This may mean Windows has built something with no direct Mac counterpart (a value-add, not a gap) — or that Mac's inline presentation is the intended parity target and Windows over-built a standalone page. Flagging for confirmation with whichever agent owns the Insight/proactive-assistants area; not scored in the summary table.

## Permissions & Help pages

**What it is:** A dedicated in-app permissions-repair surface, and a dedicated in-app support-chat page.

**Where (Mac):** `Pages/PermissionsPage.swift` (now 1,495 lines, up from ~1,140 — last substantive change 2026-08-14, "calm the Permissions settings page"), `MainWindow/HelpPage.swift` + `CrispManager.swift`. New since the old audit: Permissions is now *also* one of the visible Settings sections (`SettingsSidebar.swift`'s `visibleSections`), not only a standalone `SidebarNavItem` — Mac made this surface more prominent, not less, while the old audit's Windows-side finding stayed frozen.

**Windows status:** Absent, unchanged. No `pages/Permissions.tsx` or equivalent exists; `main/ipc/micPermission.ts` (real Windows registry-backed mic-permission detection, used by onboarding) is read-only and has no repair-flow UI wired to it anywhere. Grep for "crisp"/"Help from Founder" across the renderer and main process: zero hits, confirming Help/Crisp is still entirely absent.

**Value / notes:** M, unchanged — if anything, the gap is now slightly wider in relative terms since Mac invested more in this surface (folding it into Settings) in the interim. Help/Crisp absence may still be an intentional scope decision (vendor choice) rather than a build gap.

## Spatial overlay

**What it is:** A screen-anchored coach-mark system pointing at a button in another app's window.

**Where (Mac):** `Sources/SpatialOverlay/*`, consumed by `CloudConnectorGuidanceOverlay.swift`. No changes found since the old audit.

**Windows status:** Absent, unchanged — grep across the renderer and main process for spatial/overlay-guidance/coach-mark concepts finds nothing beyond unrelated orb-shader code (the word "crisp" appears only in shader comments and CSS-rendering comments, not a Crisp-support or coach-mark hit).

**Value / notes:** L, unchanged. Now doubly moot in one sense — the Exports/MCP hub this overlay was meant to eventually support on Windows (per the old audit's framing) is itself already built and shipped without any coach-mark equivalent, so if a "point at the exact button in Claude Desktop" flow is ever wanted, it would be additive polish, not a blocking dependency.

## Trial / paywall

**What it is:** Client-side usage-limit gating with an upgrade modal.

**Where (Mac):** `AppState+TrialPaywall.swift`, `UsageLimitPopupView`. No changes found since the old audit.

**Windows status — corrected from "Absent as a gating mechanism" to Present:**
- `components/settings/tabs/PlanUsageTab.tsx`: subscription/quota/trial/overage cards, plan grid, Stripe checkout (`startCheckout`/`createCheckoutSession` from `lib/billing.ts`), customer-portal deep link. Registered for cross-tab settings search under keywords "plan usage billing subscription upgrade quota trial overage payment neo operator architect."
- `main/billing/checkoutWindow.ts` (118 lines): a real, separate BrowserWindow hosting Stripe Checkout, with its own menu/spell-check/Delete handling (polished 2026-07-14, `d457a19fbb`).
- `components/settings/billing/UsageLimitPopup.tsx` (82 lines): an explicit port of `UsageLimitPopupView` — same three trigger reasons (`transcription`/`chat`/`trial_expired`), same headline copy, Upgrade (deep-links to the Plan & Usage tab) + "Bring your own keys" (deep-links to Advanced's BYOK section) actions. One documented, deliberate visual deviation: Mac's purple Upgrade button becomes Windows' neutral white primary per an explicit UI invariant (no purple), not an omission.
- `lib/chatQuotaGate.ts` (177 lines): the bar's pre-send quota gate, an explicit port of Mac's `FloatingBarUsageLimiter` — same fail-open-on-network-error philosophy, same optimistic local delta tracking between server syncs, same BYOK fast-path (trusts the server's `allowed:true`/`limit:null` for BYOK users rather than re-implementing Mac's client-side APIKeyService check).

Shipped as a unit 2026-07-13 (`9d0edb5fbf`, "Plan & Usage settings tab, Stripe checkout flow, usage-limit popup") — before the old audit's own commit date.

**Value / notes:** The old audit correctly hedged that this might be "an intentional product decision," which turned out to be the wrong hedge — it's not a decision, it's already-shipped functionality the previous pass simply didn't find. No further product confirmation needed here.

## Diagnostics / telemetry / startup

**What it is:** Crash reporting, heartbeats, a stress-test harness, and startup sequencing.

**Where (Mac):** `Telemetry/SentryHeartbeatTelemetry.swift`, `Diagnostics/DesktopStressDiagnostics.swift`, `Startup/AppInstaller.swift`, `Startup/StartupWarmupPolicy.swift`. No changes found to these Mac files since the old audit.

**Windows status:**
- Crash reporting: Present, and thicker than the old audit found — `src/main/sentry.ts` grew from 41 to 71 lines, adding `captureError`/`captureMessage` helper functions used elsewhere in the codebase (e.g. reporting a detected previous-session crash, or a renderer going unresponsive — `main/index.ts:348`), on top of the DSN-gated init and Authorization/Cookie/email PII scrubbing the old audit already found.
- Heartbeat telemetry: Absent, unchanged, as a *periodic breadcrumb* specifically — grep for "heartbeat" still finds no hits in app code (only in unrelated agent-kernel/goals-scheduler/voice-supervisor naming). However, a related but distinct mechanism now exists: `main/crashSentinel.ts` (114 lines), a clean-shutdown sentinel that writes a dirty flag on boot and a clean flag on the real quit path, reporting a Sentry *message* ("App crash detected," not an exception, no user banner) when the previous session's flag was left dirty. This is structurally closer to Mac's separate `AnalyticsManager.detectAndReportCrash` mechanism than to the heartbeat the old audit was checking for — worth noting so a future pass doesn't double-count it as closing the heartbeat gap.
- Stress/diagnostics harness: Partial, unchanged — `main/soak.ts` is still exactly 41 lines, still `OMI_SOAK=1`-gated, still a plain metrics-to-JSONL sampler with no scenario/terminal-reason taxonomy or `passedReleaseGate` computation.
- DMG/translocation gate: N/A, unchanged — still a platform difference, not a gap.
- Startup warmup staggering: **Present**, resolved from "unverified" — `main/startupScheduler.ts`'s `scheduleStartupSteps` runs 17 named steps (capture window, foreground monitor, Rewind capture/OCR/embedding/retention, orphan sweep, insight toast window, glow window, meeting monitor, AI-profile/Focus/Insight/Memory/Task assistants, task promotion, goal generation) staggered across the first tick after `ready-to-show` (`main/index.ts:1138-1266`), plus three additional `setTimeout`-deferred warmups (screen-source-id cache, audio-mute helper, post-update changelog toast) — directly comparable in purpose to Mac's `StartupWarmupPolicy.swift`.

**Value / notes:** L for all of the above — still internal-facing, no direct user-visible impact, matching the old audit's reasoning. The crash-sentinel addition (#9 above) is worth a one-line mention to whoever owns Mac-parity telemetry tracking so it isn't mistaken for heartbeat parity.

## Settings section inventory

**Mac** (`SettingsSidebar.swift` `SettingsSidebarRoutes.visibleSections`, re-read fresh this pass — **this list has changed since the old audit**, not just Windows): General, Account (now also renders Plan & Usage content), Transcription, Rewind, Floating Bar, Notifications (now also renders Privacy content), **Permissions** (newly promoted into the Settings sidebar, 2026-08-14), Shortcuts, Advanced, **Referral** (new, 2026-08-20/21), About — 11 visible entries. AI Chat remains in the enum but stays hidden (`EmptyView()`), matching the old audit.

**Windows** (`components/settings/tabs.ts` `SETTINGS_TABS`, `Settings.tsx`): General, Memories, **Agents**, Transcription, Rewind, Notifications, Privacy, Account, Plan & Usage, Shortcuts, Advanced, About — 12 tabs. Six of these (Notifications, Transcription, Plan & Usage, Shortcuts, About, Agents) did not exist when the old audit's "6 tabs" count was written, and — critically — **Agents shipped 2026-07-08**, five weeks before either the audit's stated write date or its actual commit date, meaning the old audit's "6 tabs (General, Account, Privacy, Rewind, Integrations, Advanced)" list was simply wrong when written, not stale.

What's still actually missing on Windows relative to Mac's current list: a dedicated **Floating Bar** settings section (bar-related settings are folded into General/Shortcuts, as the old audit found — unchanged), a dedicated **Permissions** settings section (unchanged — see Permissions & Help above), and the brand-new **Referral** section (Windows has no referral UI at all — new gap, see table). Conversely, Windows now has two sections Mac's *visible* list doesn't carry as separate items: **Agents** (Mac's coding-agent connection settings, if any, weren't found under a dedicated section this pass — flagging as a possible reverse-gap worth Mac-side confirmation rather than asserting it doesn't exist) and a full **Memories** tab-as-page (Mac's Memories brain-map is a top-level `SidebarNavItem`, not a Settings section, so this is an architectural difference rather than a gap either direction).

**Value / notes:** M, downgraded from the old audit's H. This is no longer "the largest single gap by count" — Windows and Mac are now within one section of each other (12 vs 11), and the specific sections the old audit worried about most (Notifications, Shortcuts, Plan & Usage/billing, About) are all now present. The two real remaining gaps (Floating Bar, Permissions-as-a-section) plus the brand-new Referral gap are real but narrower in scope than the old framing suggested.

## Settings search

**Mac:** `SettingsSearchItem.allSearchableItems` — a global fuzzy search across every section that jumps to and highlights (`highlightedSettingId`) the matched control. No changes found since the old audit.

**Windows — corrected from "per-tab keyword search only" to "genuinely cross-tab":** `SettingsSearchProvider.tsx` maintains one shared registry (`Map<id, {text, tab}>`) that every `SettingRow` across every tab registers into on mount (`SettingRow.tsx`'s `useSearchableRow`). `SettingsTabPanel.tsx` shows a tab's panel either when it's the active tab, or — while a search query is active — whenever *any* of its registered rows match, with the tab's label rendered as a group header. This means a query like "notification" now surfaces matching rows from Notifications *and* any other tab with a matching keyword, simultaneously, exactly like a cross-section search should — the old audit's claim that it was scoped to the currently-open tab is incorrect for the current implementation (it may have been briefly true at an earlier revision, but the registry-based design checked here spans all tabs by construction).

What's still missing relative to Mac: there's no scroll-to-and-glow of the specific matched control — the whole matching tab's panel is shown, not a highlighted single row, so on a tab with many matches the user still has to visually scan for the right one.

**Value / notes:** L, downgraded from M. The functional gap (no highlight-and-jump) is real but minor now that the underlying search is already cross-tab; this is closer to "missing polish" than "missing capability."

## Sidebar tier-gating

**Mac:** `SidebarNavItem.requiredTier` progressively unlocks nav items with a lock icon + tooltip. No changes found since the old audit.

**Windows status:** Absent, unchanged — `routes/manifest.ts`'s `RouteEntry`/`RouteNav` types carry no tier field, and `Sidebar.tsx` renders every entry from `navRoutes()` unconditionally.

**Value / notes:** L, unchanged.

## Spotted outside my scope

- Chat/agent behavior on Home (`HubChatPanel`, `ChatBridgeHost`) — chat-agent's area.
- The Insight/proactive-notification *engine* itself (`main/insight/{toastWindow,notification,state}.ts`) — only the new Insights history *page* was reviewed here; the engine is a proactive-assistants concern.
- File indexing / knowledge graph, including the new full-screen `pages/KnowledgeGraph.tsx` route (reached from Memories' brain-map expand affordance, shipped 2026-07-15) — fileindex-kg's area.
- Floating top-edge bar (`components/bar/BarApp`, `main/bar/*`) and Orb component — floating-bar's area.
- Realtime voice session internals (`lib/voice/*`) — realtime-voice's area.
- Rewind depth (capture cadence, retention, excluded apps) — rewind's area.
- Tasks/Goals engine internals — tasks-goals's area.
- Onboarding flow internals, including the real registry-backed mic-permission detection now feeding it (`main/ipc/micPermission.ts`) — onboarding's area.
- Bluetooth/device pairing — bluetooth's area.
- Conversation sync/merge/outbox correctness (`lib/sync/*`) — wal-sync's area; only the UI shell plus LiveNotes/speaker-naming were reviewed here.
- The underlying Google/X/memory-import connector *logic* (`main/integrations/*`, `main/memoryImport/*`, `main/memoryExport/*`) — reviewed only as far as confirming the UI surfaces exist and are wired; correctness of the sync/parsing itself is out of scope for this app-shell pass.
