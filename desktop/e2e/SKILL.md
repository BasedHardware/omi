---
name: desktop-app-flows
description: "Understand and explore the Omi desktop macOS app's UI flows, navigation patterns, and SwiftUI architecture. Use when developing features, fixing bugs, or verifying changes in desktop/ Swift files. Provides agent-swift commands to explore the live app, understand how screens connect, and verify your work."
allowed-tools: Bash, Read, Glob, Grep
---

# Omi Desktop App — Flows & Exploration

This skill teaches you the Omi desktop macOS app's navigation structure, screen architecture, and SwiftUI patterns. Use it when developing features (to understand how the app works), fixing bugs (to navigate to the affected screen), or verifying changes (to confirm your code works in the live app).

## How to Explore the App

You can interact with the running app via `agent-swift` — a CLI that clicks elements, reads the accessibility tree, and captures screenshots through the macOS Accessibility API. Works with any macOS app, no app-side instrumentation needed.

### Setup
```bash
# App must be running via ./run.sh from desktop/
agent-swift doctor                                   # check Accessibility permission
agent-swift connect --bundle-id com.omi.desktop-dev  # connect to Omi Dev
agent-swift snapshot -i --json                       # see what's on screen
```

### Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `snapshot -i --json` | See all interactive elements with refs, types, labels | `agent-swift snapshot -i --json` |
| `click @ref` | CGEvent click — SwiftUI elements (NavigationLink, gestures) | `agent-swift click @e3` |
| `press @ref` | AXPress — AppKit buttons, Settings sidebar items | `agent-swift press @e5` |
| `find role/text/key VALUE` | Find element and chain action | `agent-swift find text "Settings" click` |
| `fill @ref "text"` | Type into text field | `agent-swift fill @e7 "search"` |
| `scroll down/up` | Scroll current view | `agent-swift scroll down` |
| `wait text "X"` | Wait for element to appear | `agent-swift wait text "Loading" --timeout 5000` |
| `is exists @ref` | Assert element exists (exit 0/1) | `agent-swift is exists @e3` |
| `get PROP @ref` | Read property value | `agent-swift get value @e5 --json` |
| `screenshot PATH` | Capture app window | `agent-swift screenshot /tmp/screen.png` |

**Key rules:**
- `click` = CGEvent mouse click (SwiftUI). Use for main sidebar icons, NavigationLink.
- `press` = AXPress action (AppKit). Use for Settings sidebar sections.
- Refs go stale after any mutation — always re-snapshot before the next interaction.
- `find` with chained action is more stable than hardcoded `@ref` numbers.
- `--json` flag on any command gives structured output for parsing.

## App Navigation Architecture

### Screen Map
```
Main Window
├── Sidebar (SidebarView.swift) — use `click`
│   ├── Home (DesktopHomeView.swift)
│   ├── Conversation (ChatSessionsSidebar.swift)
│   ├── brain → Memories
│   ├── checklist → Action Items
│   ├── puzzlepiece.fill → Integrations
│   └── gearshape.fill → Settings
│
└── Settings (SettingsPage.swift) — use `press` for sidebar sections
    ├── General — app preferences
    ├── Rewind — screenshot/timeline settings
    ├── Transcription — Language Mode (Auto-Detect / Single Language)
    │   └── Language picker (popupbutton or button)
    ├── Notifications — alert preferences
    ├── Privacy — data settings
    ├── Account — user info
    ├── AI Chat — chat model settings
    ├── Advanced — developer options
    └── About — version info

System Tray Menu
├── openOmi — Open Omi
├── checkFor — Check for Updates
├── resetOnb — Reset Onboarding
├── reportIs — Report Issue
├── signOut — Sign Out
└── quitApp — Quit
```

### Interaction Patterns

**Main sidebar navigation:**
- Icons are `image` type elements with accessibility identifiers: `sidebar_dashboard`, `sidebar_chat`, `sidebar_memories`, `sidebar_tasks`, `sidebar_rewind`, `sidebar_apps`, `sidebar_settings`
- Use `find key sidebar_dashboard click` for reliable navigation (survives UI changes)
- Keyboard shortcuts: Cmd+1 (Dashboard), Cmd+2 (Chat), Cmd+3 (Memories), Cmd+4 (Tasks), Cmd+5 (Rewind), Cmd+6 (Apps), Cmd+, (Settings)
- Use `click` — these are SwiftUI views with onTapGesture

**Settings sidebar navigation:**
- Sections are `button` type elements with section name labels
- Use `press` — these are SwiftUI Button views that respond to AXPress

**Transcription language mode:**
- Two radio-button-style options: "Auto-Detect Multi-Language" and "Single Language Better Accuracy"
- `click` on the text to switch modes
- Single Language mode shows a language picker (`popupbutton`)
- Click popupbutton → menu items appear as `menuitem` elements

**System tray menu:**
- Menu items have `identifier` prefixes for detection
- Access via `snapshot --json` (includes menu bar items)

## Known Flows

Reference flows in `desktop/e2e/flows/*.yaml` describe the app's key user journeys. Read these to understand navigation paths, expected elements, and UI state at each step.

| Flow | Covers | Steps | Report |
|------|--------|-------|--------|
| `flows/navigation.yaml` | SidebarView, DesktopHomeView | 6/6 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/RVS7NChPvj.html) |
| `flows/dashboard.yaml` | DashboardPage, GoalsWidget, TasksWidget | 3/6 (3 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/ghCdGIUAA2.html) |
| `flows/chat.yaml` | ChatPage, ChatProvider | 5/5 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/z62Nll0IzR.html) |
| `flows/memories.yaml` | MemoriesPage, MemoryGraphPage | 5/6 (1 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/Mkp6ahc12I.html) |
| `flows/tasks.yaml` | TasksPage, TasksStore | 4/5 (1 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/ealB_-UdqS.html) |
| `flows/settings.yaml` | SettingsPage, SettingsSidebar | 9/9 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/RoTW8GeljN.html) |
| `flows/language.yaml` | SettingsPage, SettingsSidebar | 5 steps | — |
| `flows/rewind.yaml` | RewindPage | 4/4 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/1HE5OsPOOy.html) |
| `flows/apps.yaml` | IntegrationsPage | 6/6 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/VDGw-wbHqa.html) |
| `flows/refer.yaml` | ReferPage | 3/3 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/Jz8ymviOy1.html) |

When you modify a Swift file, check if any flow's `covers:` includes it. That flow describes the user journey your change affects.

### Adding a New Flow
Create `desktop/e2e/flows/<name>.yaml` in v2 format:
```yaml
version: 2
name: my-flow
description: What this flow covers
app: com.omi.computer-macos
covers:
  - desktop/Desktop/Sources/path/to/YourView.swift
preconditions:
  - auth_ready
steps:
  - id: S1
    name: Step description
    do: "Click the element (identifier: my_element). Verify the page loads."
    expect:
      interactive_count: { min: 5 }
      text_visible:
        - Expected Text
```
**Important:** Always use quoted strings for `do:` fields (not YAML `>` or `|`).

## Verification & Evidence

After making changes, verify them in the live app:
1. Navigate to the affected screen using the commands above
2. Check that your changes appear (snapshot, screenshot)
3. Test interactions (click buttons, fill fields, scroll)
4. Capture evidence: `agent-swift screenshot /tmp/evidence.png`
5. Generate video: `ffmpeg -framerate 1 -pattern_type glob -i '/tmp/e2e-*.png' -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1" -c:v libx264 -pix_fmt yuv420p /tmp/report.mp4`

## Decision Tree

| Problem | Solution |
|---------|----------|
| Element not found | Re-snapshot, try scrolling, check if on wrong screen |
| Click doesn't navigate | Try `press` instead (Settings sidebar = `press`, main sidebar = `click`) |
| Picker not responding | SwiftUI Picker `.menu` style may not expose as `popupbutton` — look for `button` with value label |
| App seems frozen | Check `agent-swift status --json`, re-connect, check `/private/tmp/omi-dev.log` |

## Guard Conditions

**NEVER:**
- Kill or restart the production Omi app
- Use development env vars to bypass auth — test real auth flows
- Set `hasCompletedOnboarding` to skip onboarding — test the real flow
- Modify source code to make tests pass — report the failure instead

**NOTE:** The beta app (`com.omi.computer-macos`) is the standard target for flow-walker E2E testing. The dev app (`com.omi.desktop-dev`) is for local development only.
