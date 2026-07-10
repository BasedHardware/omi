# Omi Desktop App Feature Vector for Flow-Walker
## Updated 2026-07-09

### Purpose
Prioritized feature map to guide desktop E2E coverage. Uses the same two-dimensional priority model as the mobile feature vector, plus a **Bridge** score for the cursor-free automation lane (`omi-ctl` / typed YAML flows).

---

## Scoring Model

**Combined Priority** = `layer_weight × session_frequency`

| Dimension | Values |
|-----------|--------|
| **Core-to-mission** (layer weight) | capture=5, understand=4, memory=4, intelligence=3, retrieval-action=3 |
| **Session frequency** | daily=3, weekly=2, setup-only=1 |

**Bridge Score** (0-3) — `omi-ctl` / typed harness (`bridge.navigate`, `bridge.action`):
- 3 = hermetic mutation or deep snapshot action exists
- 2 = navigate + read-only snapshot
- 1 = seam exists but needs seed/setup (capture transcript, local auth)
- 0 = manual lane only (OAuth popup, TCC, external URL, destructive confirm)

**Walker Score** (0-3) — `agent-swift` (macOS Accessibility API):
- 3 = fully automatable (click/press-only, deterministic, AX identifiers present)
- 2 = partially automatable (needs scroll, conditional content, or timing waits)
- 1 = needs system setup first (microphone permission, account linking), then walker can verify
- 0 = unreachable (external OAuth popup, OS-level dialog, real payment)

> **Lane preference:** Prefer bridge (T2 hermetic) over walker (manual Live P2). Walker reports below are historical flow-walker runs; bless-tier confidence comes from `desktop-core-harness.sh --tier 2`.

---

## Feature Vector (sorted by priority)

### CORE DAILY (priority 9-15)

| # | Feature | Layer | Priority | Bridge | Walker | Coverage Status |
|---|---------|-------|----------|--------|--------|-----------------|
| 1 | Dashboard — conversations list, refresh | intelligence (3) | 9 | 2 | 2 | ✅ flow: `dashboard.yaml` (nav + `conversation_list_snapshot`) |
| 2 | Chat — send message, AI response | intelligence (3) | 9 | 2 | 2 | ✅ flow: `chat-hermetic.yaml` |
| 3 | Sidebar navigation — all sections | retrieval-action (3) | 9 | 2 | 3 | ✅ flow: `navigation.yaml` |
| 4 | Home stage (hub / chat / connect) | intelligence (3) | 9 | 2 | 2 | ✅ flow: `home-stage.yaml` |
| 5 | Capture lifecycle (hermetic transcript seam) | capture (5) | 15 | 2 | 1 | ✅ flow: `capture-lifecycle.yaml` |
| 6 | Screen capture (Rewind) | capture (5) | 15 | 0 | 2 | ⚠️ manual: `rewind.yaml`, `screen-recording-permission.yaml` (TCC) |
| 7 | Audio recording (desktop mic) | capture (5) | 15 | 0 | 1 | ⚠️ manual: `audio-recording.yaml` (mic permission) |
| 8 | Memory list & browse | memory (4) | 12 | 2 | 2 | ✅ flow: `memories.yaml` (nav + search step) |
| 9 | Memory search | memory (4) | 12 | 3 | 2 | ✅ flow: `memory-depth.yaml` + `memories.yaml` |
| 10 | Tasks — list, refresh | retrieval-action (3) | 9 | 3 | 2 | ✅ flow: `tasks-crud.yaml` + `tasks.yaml` |
| 11 | Quick Note (dashboard) | intelligence (3) | 9 | 2 | 2 | ✅ flow: `quick-note.yaml` |
| 12 | Floating bar / Ask Omi | intelligence (3) | 9 | 2 | 2 | ✅ flow: `floating-bar-functional.yaml` |

### SECONDARY SURFACES (priority 6-12) — first-class rows

| # | Feature | Layer | Priority | Bridge | Walker | Coverage Status |
|---|---------|-------|----------|--------|--------|-----------------|
| 13 | Conversation detail (transcript drawer, segments) | capture (5) | 15 | 3 | 2 | ✅ flow: `conversation-detail.yaml` |
| 14 | Conversation sharing / export | retrieval-action (3) | 6 | 2 | 2 | ⚠️ partial: `conversation-sharing.yaml` (share link probe; clipboard/native share manual) |
| 15 | Conversation folders & starring | retrieval-action (3) | 6 | 3 | 2 | ✅ flow: `conversation-folders.yaml` |
| 16 | Speaker naming (People) | understand (4) | 8 | 3 | 1 | ✅ flow: `speaker-naming.yaml` (multi-speaker inject + assign) |
| 17 | Memory CRUD (create / edit / delete) | memory (4) | 8 | 3 | 2 | ✅ flow: `memory-crud.yaml` |
| 18 | Memory visibility toggle | memory (4) | 8 | 3 | 2 | ✅ flow: `memory-depth.yaml` |
| 19 | Memory graph visualization | memory (4) | 8 | 2 | 2 | ✅ flow: `memory-graph.yaml` (API counts; no SceneKit) |
| 20 | Memory tag filtering | memory (4) | 8 | 3 | 2 | ✅ flow: `memory-depth.yaml` |
| 21 | Custom vocabulary | understand (4) | 8 | 3 | 2 | ✅ flow: `vocabulary.yaml` |
| 22 | Goals tracking (dashboard widget) | intelligence (3) | 6 | 3 | 2 | ✅ flow: `goals-dashboard.yaml` |
| 23 | Transcription language settings | understand (4) | 8 | 3 | 3 | ✅ flow: `language.yaml` (set + snapshot) |
| 24 | Privacy toggles (store recordings, tracking) | — | 5 | 2 | 2 | ✅ flow: `privacy-settings.yaml` (toggle snapshot) |
| 25 | Plan / usage (billing) | — | 5 | 2 | 1 | ✅ flow: `plan-usage.yaml` (subscription snapshot) |
| 26 | Apps / integrations catalog | retrieval-action (3) | 6 | 2 | 2 | ✅ flow: `apps-marketplace.yaml` + ⚠️ manual: `apps.yaml` |
| 27 | Connector import (progress persistence) | retrieval-action (3) | 6 | 3 | 2 | ✅ flow: `connector-import.yaml` + ⚠️ manual: `connector-import-progress.yaml` |
| 28 | Refer a Friend (external affiliate URL) | retrieval-action (3) | 6 | 0 | 2 | ⚠️ manual: `refer-external.yaml` (profile menu → browser) |
| 29 | Delete account (confirmation only) | — | 5 | 0 | 2 | ⚠️ manual: `delete-account.yaml` (never confirms) |
| 30 | Logout (local auth / emulator) | — | 5 | 1 | 2 | ⚠️ manual: `logout.yaml` (`sign_out` bridge; not prod OAuth) |
| 31 | Onboarding (first launch / reset) | — | 5 | 1 | 1 | ⚠️ manual: `onboarding-smoke.yaml` — reset fix landed; keep manual until 2× local green |

### SETTINGS & SYSTEM (priority 3-5)

| # | Feature | Layer | Priority | Bridge | Walker | Coverage Status |
|---|---------|-------|----------|--------|--------|-----------------|
| 32 | Settings — section navigation | — | 5 | 2 | 3 | ✅ flow: `settings-basic.yaml` (General, Transcription, Privacy, Rewind, Notifications, About, Shortcuts, Advanced) |
| 33 | Rewind settings | capture (5) | 5 | 2 | 2 | ✅ flow: `rewind-settings.yaml` |
| 34 | Account info | — | 5 | 2 | 2 | ✅ flow: `plan-usage.yaml` (Account section + subscription snapshot) |
| 35 | AI Chat model settings | intelligence (3) | 3 | 2 | 2 | ✅ flow: `ai-chat-settings.yaml` (non-prod section; prod still redirects to Advanced) |
| 36 | Advanced / Developer options | — | 3 | 2 | 2 | ✅ flow: `settings-basic.yaml` (`advanced_settings_snapshot`) |
| 37 | System tray menu | — | 5 | 0 | 3 | ⚠️ partial: covered indirectly by manual logout/onboarding |
| 38 | Keyboard shortcuts (Cmd+1..6, Cmd+,) | — | 5 | 2 | 3 | ✅ flow: `keyboard-shortcuts.yaml` |
| 39 | Notifications settings | — | 3 | 2 | 2 | ✅ flow: `notifications-settings.yaml` |
| 40 | About page (version info) | — | 3 | 2 | 3 | ✅ flow: `about-settings.yaml` |
| 41 | Auth (Sign In — Google/Apple) | — | 5 | 0 | 0 | blocked: external OAuth |
| 42 | Connector import (hermetic probe) | retrieval-action (3) | 6 | 3 | 0 | ✅ flow: `connector-import.yaml` (same surface as #27; progress UI stays manual) |

---

## Live P2 Manual Lane

Agent-local flows with `tier: manual` — **not** bless-tier (T2). Run individually with flow-walker / `agent-swift` on a signed-in named bundle.

| Flow | Why manual | Destructive? |
|------|------------|--------------|
| `refer-external.yaml` | Opens `https://affiliate.omi.me` in the default browser | No |
| `delete-account.yaml` | Exercises confirmation sheet only; **never** taps Delete Permanently | Yes (gated) |
| `logout.yaml` | Sign out via Settings; requires **local Auth emulator** (`make desktop-run-local`), not prod OAuth | No |
| `onboarding-smoke.yaml` | `reset_onboarding` restarts app; Wave 7 fix landed — manual until 2× local green | Yes (local reset) |
| `audio-recording.yaml` | Microphone TCC | No |
| `rewind.yaml` | Rewind page + permission state | No |
| `screen-recording-permission.yaml` | Screen Recording TCC + System Settings | No |
| `apps.yaml` | Marketplace browse/filter (walker) | No |
| `connector-import-progress.yaml` | Live import progress UI | No |

Do **not** promote destructive flows (`delete-account`, `onboarding-smoke`) to T2 bless tier.

---

## Remaining Gaps

| Rank | Feature | Priority | Blocker | Notes |
|------|---------|----------|---------|-------|
| 1 | Onboarding reset smoke | 5 | App restart harness | `onboarding-smoke.yaml` stays manual until 2× local green after Wave 7 fix |
| 2 | Prod OAuth sign-in | 5 | External browser | Use local Auth emulator for logout manual lane |
| 3 | Native share / clipboard | 6 | OS share sheet | `conversation-sharing.yaml` probes share link only |
| 4 | TCC live lanes | 15 | Mic / screen recording | `audio-recording.yaml`, `rewind.yaml`, `screen-recording-permission.yaml` |
| 5 | System tray depth | 5 | Low ROI | Partial via manual logout/onboarding only |

---

## Published Flow-Walker Reports (historical walker lane)

| Flow | Steps | Result | Report URL |
|------|-------|--------|------------|
| navigation | 6/6 | PASS | flow-walker.beastoin.workers.dev/runs/RVS7NChPvj.html |
| dashboard | 3/6 | PASS (3 skipped) | flow-walker.beastoin.workers.dev/runs/ghCdGIUAA2.html |
| chat-hermetic | 5/5 | PASS | flow-walker.beastoin.workers.dev/runs/z62Nll0IzR.html |
| memories | 5/6 | PASS (1 skipped) | flow-walker.beastoin.workers.dev/runs/Mkp6ahc12I.html |
| tasks | 4/5 | PASS (1 skipped) | flow-walker.beastoin.workers.dev/runs/ealB_-UdqS.html |
| settings-basic | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/RoTW8GeljN.html |
| rewind | 4/4 | PASS | flow-walker.beastoin.workers.dev/runs/1HE5OsPOOy.html |
| apps | 6/6 | PASS | flow-walker.beastoin.workers.dev/runs/VDGw-wbHqa.html |
| refer-external | — | — | superseded old `refer.yaml` (profile menu, not sidebar page) |
| screen-recording-permission | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/3WoXUG6xkT.html |
| audio-recording | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/UdkzB-dYG_.html |

---

## What Changed (2026-07-09)

Wave 1/2 T2 hermetic flows landed for secondary surfaces:

- `conversation-detail.yaml`, `memory-crud.yaml`, `vocabulary.yaml`, `goals-dashboard.yaml`, `plan-usage.yaml`, `privacy-settings.yaml`, `apps-marketplace.yaml`, `connector-import.yaml`, `conversation-folders.yaml`, `conversation-sharing.yaml`
- Bridge actions power mutations and deep snapshots; Live P2 manual lane unchanged for prod auth, delete-account, logout, and refer-external.

Waves 4–7 (code landed; Wave 8 live bless complete):

- Wave 4: `tasks-crud.yaml`, `memory-depth.yaml`, language save, memory search/filter/visibility actions
- Wave 5: `quick-note.yaml`, `about-settings.yaml`, `notifications-settings.yaml`, `rewind-settings.yaml`, `keyboard-shortcuts.yaml`, extended `settings-basic.yaml`
- Wave 6: multi-speaker `inject_multi`, `speaker-naming.yaml` T2, `memory-graph.yaml`
- Wave 7: `reset_onboarding` corruption fix, non-prod AI Chat section + `ai-chat-settings.yaml`; `onboarding-smoke.yaml` stays manual
- Wave 8: 32/32 T2 flows green (manual bless via `omi-harness`; harness `dev-up` blocked on port 8085 conflict — see CORE_E2E Failure playbook)

---

## Coverage Summary (honest — 2026-07-09, post Wave 8 bless)

| Category | Total | ✅ deep flow | ⚠️ nav-only / manual / partial | ❌ / blocked |
|----------|-------|-------------|--------------------------------|-------------|
| Core Daily | 12 | 10 | 2 | 0 |
| Secondary Surfaces | 19 | 14 | 5 | 0 |
| Settings & System | 11 | 9 | 1 | 1 |
| **Total** | **42** | **33** | **8** | **1** |

T2 bless matrix: **32/32 flows green** (2026-07-09 manual bless via `omi-harness` bridge lane; full `desktop-core-harness.sh --tier 2` blocked on foreign Firestore port — see CORE_E2E Failure playbook). Manual Live P2 remains for TCC, OAuth, destructive gates, and partial sharing.

---

## Desktop-Specific Notes

- **Bridge first:** `scripts/omi-ctl` + `e2e/flows/*.yaml` with `bridge.navigate` / `bridge.action`.
- **Walker second:** `agent-swift` for manual Live P2 lane and TCC-dependent flows.
- Sidebar AX identifiers: `sidebar_dashboard`, `sidebar_chat`, `sidebar_memories`, `sidebar_tasks`, `sidebar_rewind`, `sidebar_apps`, `sidebar_settings`. Refer a Friend lives in the **profile menu popover**, not a sidebar item.
- System tray menu items: `openOmiFromMenu`, `checkForUpdates`, `resetOnboarding`, `reportIssue`, `signOut`, `quitApp`
- Keyboard shortcuts via View menu: Cmd+1 (Dashboard), Cmd+2 (Conversations), Cmd+3 (Memories), Cmd+4 (Tasks), Cmd+5 (Rewind), Cmd+6 (Apps), Cmd+, (Settings)
- Beta app bundle ID: `com.omi.computer-macos` (flow-walker default)
- Dev / hermetic bundle: `com.omi.omi-core-e2e` with `make desktop-run-local` (Auth emulator)
