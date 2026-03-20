# Omi Desktop App Feature Vector for Flow-Walker
## Updated 2026-03-20

### Purpose
Prioritized feature map to guide flow-walker E2E coverage of core Omi desktop macOS app flows. Uses the same two-dimensional scoring model as the mobile feature vector.

---

## Scoring Model

**Combined Priority** = `layer_weight × session_frequency`

| Dimension | Values |
|-----------|--------|
| **Core-to-mission** (layer weight) | capture=5, understand=4, memory=4, intelligence=3, retrieval-action=3 |
| **Session frequency** | daily=3, weekly=2, setup-only=1 |

**Walker Score** (0-3) — desktop-specific (agent-swift via macOS Accessibility API):
- 3 = fully automatable (click/press-only, deterministic, AX identifiers present)
- 2 = partially automatable (needs scroll, conditional content, or timing waits)
- 1 = needs system setup first (microphone permission, account linking), then walker can verify
- 0 = unreachable (external OAuth popup, OS-level dialog, real payment)

> **Note:** Desktop walker uses `agent-swift` (CGEvent click + AXPress) instead of mobile's `agent-flutter` (Marionette). All sidebar items have AX identifiers (`sidebar_dashboard`, `sidebar_chat`, etc.), making navigation highly automatable.

---

## Feature Vector (sorted by priority × walker_score)

### CORE DAILY (priority 9-15, walker_score 2-3)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 1 | Dashboard — goals widget, tasks, conversations | intelligence (3) | 9 | 3 | ✅ flow: dashboard.yaml (6 steps) |
| 2 | Chat — send message, AI response, actions | intelligence (3) | 9 | 2 | ✅ flow: chat.yaml (5 steps) |
| 3 | Sidebar navigation — all 7 sections | retrieval-action (3) | 9 | 3 | ✅ flow: navigation.yaml |
| 4 | Conversation list & browse (dashboard embedded) | capture (5) | 15 | 2 | ✅ flow: dashboard.yaml |
| 5 | Screen capture (Rewind) | capture (5) | 15 | 2 | ❌ needs flow |
| 6 | Audio recording (desktop mic) | capture (5) | 15 | 1 | ❌ needs flow |
| 7 | Memory list & browse | memory (4) | 12 | 2 | ✅ flow: memories.yaml (6 steps) |
| 8 | Memory search | memory (4) | 12 | 2 | ✅ flow: memories.yaml |
| 9 | Tasks — categories, filters, create, toggle | retrieval-action (3) | 9 | 2 | ✅ flow: tasks.yaml (5 steps) |
| 10 | Quick Note (dashboard) | intelligence (3) | 9 | 2 | ⚠️ partial (in dashboard.yaml) |

### CORE WEEKLY (priority 6-12, walker_score 1-2)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 11 | Memory visibility toggle | memory (4) | 8 | 2 | ✅ flow: memories.yaml |
| 12 | Memory graph visualization | memory (4) | 8 | 2 | ✅ flow: memories.yaml |
| 13 | Memory tag filtering | memory (4) | 8 | 2 | ✅ flow: memories.yaml |
| 14 | Transcription language settings | understand (4) | 8 | 3 | ✅ flow: language.yaml |
| 15 | Language mode toggle (Auto/Single) | understand (4) | 8 | 3 | ✅ flow: language.yaml |
| 16 | Goals CRUD (create, update, delete) | intelligence (3) | 6 | 2 | ✅ flow: dashboard.yaml |
| 17 | Apps/Integrations marketplace | retrieval-action (3) | 6 | 2 | ❌ needs flow |
| 18 | Refer a Friend | retrieval-action (3) | 6 | 2 | ❌ needs flow |

### SETTINGS & SYSTEM (priority 3-5, walker_score 1-3)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 19 | Settings — all 9 sections | — | 5 | 3 | ✅ flow: settings.yaml (9 steps) |
| 20 | General preferences | — | 5 | 3 | ✅ flow: settings.yaml |
| 21 | Rewind settings | capture (5) | 5 | 2 | ✅ flow: settings.yaml |
| 22 | Privacy settings | — | 5 | 2 | ✅ flow: settings.yaml |
| 23 | Account info | — | 5 | 2 | ✅ flow: settings.yaml |
| 24 | AI Chat model settings | intelligence (3) | 3 | 2 | ✅ flow: settings.yaml |
| 25 | Advanced / Developer options | — | 3 | 2 | ✅ flow: settings.yaml |
| 26 | System tray menu | — | 5 | 3 | ✅ flow: navigation.yaml |
| 27 | Keyboard shortcuts (Cmd+1..6, Cmd+,) | — | 5 | 3 | ✅ flow: navigation.yaml |
| 28 | Onboarding (first launch) | — | 5 | 1 | ❌ needs fresh state |
| 29 | Auth (Sign In / Sign Out) | — | 5 | 0 | ❌ external OAuth |
| 30 | Notifications settings | — | 3 | 2 | ✅ flow: settings.yaml |
| 31 | About page (version info) | — | 3 | 3 | ✅ flow: settings.yaml |

---

## Remaining Gaps

| Rank | Feature | Priority | Blocker | Notes |
|------|---------|----------|---------|-------|
| 1 | Screen capture (Rewind) | 15 | Needs screen recording permission | Rewind page exists, AX identifiers unknown — needs exploration |
| 2 | Audio recording (desktop mic) | 15 | Needs microphone permission grant | Start Recording button visible on dashboard but mic requires OS dialog |
| 3 | Apps/Integrations | 6 | No flow written | Apps page accessible via sidebar_apps — should be straightforward |
| 4 | Onboarding | 5 | Needs fresh/reset state | Reset Onboarding available in tray menu but causes state corruption (known issue) |
| 5 | Auth | 5 | External OAuth | Google/Apple Sign-In opens browser — not automatable |

---

## Published Flow-Walker Reports

| Flow | Steps | Result | Report URL |
|------|-------|--------|------------|
| navigation | 6/6 | PASS | flow-walker.beastoin.workers.dev/runs/RVS7NChPvj.html |
| dashboard | 3/6 | PASS (3 skipped) | flow-walker.beastoin.workers.dev/runs/ghCdGIUAA2.html |
| chat | 5/5 | PASS | flow-walker.beastoin.workers.dev/runs/z62Nll0IzR.html |
| memories | 5/6 | PASS (1 skipped) | flow-walker.beastoin.workers.dev/runs/Mkp6ahc12I.html |
| tasks | 4/5 | PASS (1 skipped) | flow-walker.beastoin.workers.dev/runs/ealB_-UdqS.html |
| settings | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/RoTW8GeljN.html |

---

## Coverage Summary

| Category | Total Features | Covered | Gaps |
|----------|---------------|---------|------|
| Core Daily (capture, intelligence) | 10 | 7 | 3 (screen capture, audio recording, quick note partial) |
| Core Weekly (memory, understand, retrieval) | 8 | 6 | 2 (apps, refer) |
| Settings & System | 13 | 11 | 2 (onboarding, auth) |
| **Total** | **31** | **24** | **7** |

---

## Desktop-Specific Notes

- **agent-swift** is the automation tool (not agent-flutter). Uses macOS Accessibility API.
- **click** for SwiftUI elements (sidebar icons, NavigationLink). **press** for AppKit buttons (Settings sidebar sections).
- Sidebar AX identifiers: `sidebar_dashboard`, `sidebar_chat`, `sidebar_memories`, `sidebar_tasks`, `sidebar_rewind`, `sidebar_apps`, `sidebar_settings`, `sidebar_refer_a_friend`, `sidebar_discord`
- System tray menu items: `openOmiFromMenu`, `checkForUpdates`, `resetOnboarding`, `reportIssue`, `signOut`, `quitApp`
- Keyboard shortcuts via View menu: Cmd+1 (Dashboard), Cmd+2 (Chat), Cmd+3 (Memories), Cmd+4 (Tasks), Cmd+5 (Rewind), Cmd+6 (Apps), Cmd+, (Settings)
- Beta app bundle ID: `com.omi.computer-macos` (use for flow-walker runs)
- Dev app bundle ID: `com.omi.desktop-dev` (skip unless dev-specific testing)
- GUI user prefix required on SSH: `sudo launchctl asuser 501 sudo -u beastoinagents <cmd>`
