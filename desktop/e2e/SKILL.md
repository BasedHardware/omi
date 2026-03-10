---
name: desktop-e2e-verify
description: "Autonomously verify Omi desktop macOS app UI changes using agent-swift. Use after editing SwiftUI code, when asked to test desktop changes, or when verifying a PR that touches desktop/ Swift files. Captures screenshot evidence and generates video reports."
allowed-tools: Bash, Read, Glob, Grep
---

# Desktop E2E Verification

You are an autonomous agent verifying the Omi desktop macOS app. You have full control of the app via `agent-swift` — a CLI that sends clicks, reads elements, and captures screenshots through the macOS Accessibility API. No human intervention needed.

## Prerequisites

1. App must be running: `./run.sh` from `desktop/` (see `test-local` skill)
2. agent-swift installed: `brew install beastoin/tap/agent-swift`
3. Accessibility permission granted for Terminal.app

Quick check:
```bash
agent-swift doctor
agent-swift connect --bundle-id com.omi.desktop-dev
agent-swift snapshot -i   # should show interactive elements
```

## Core Workflow

### 1. Connect and Orient

```bash
agent-swift connect --bundle-id com.omi.desktop-dev
agent-swift snapshot -i --json
```

Parse the JSON to understand current app state. The snapshot returns elements with `ref`, `type`, `label`, `value`, and `identifier` fields.

### 2. Explore and Verify

Use these commands to interact with the app. **Always re-snapshot after any mutation** — refs go stale after every click/press/fill/scroll.

| Command | When to use | Example |
|---------|-------------|---------|
| `click @ref` | SwiftUI elements (NavigationLink, onTapGesture) | `agent-swift click @e3` |
| `press @ref` | AppKit buttons, Settings sidebar items | `agent-swift press @e5` |
| `fill @ref "text"` | Text fields | `agent-swift fill @e7 "search query"` |
| `scroll down/up` | Scroll current view | `agent-swift scroll down` |
| `find role/text/key VALUE` | Find element without knowing ref | `agent-swift find text "Settings" click` |
| `wait text "X"` | Wait for element to appear | `agent-swift wait text "Loading" --timeout 5000` |
| `is exists @ref` | Assert element exists (exit 0/1) | `agent-swift is exists @e3` |
| `get PROP @ref` | Read property value | `agent-swift get value @e5 --json` |
| `screenshot PATH` | Capture app window | `agent-swift screenshot /tmp/evidence.png` |

**Key rules:**
- `click` = CGEvent mouse click (works with SwiftUI). Use for main sidebar icons, navigation links.
- `press` = AXPress accessibility action (works with AppKit). Use for Settings sidebar sections.
- `find` with chained action is more stable than hardcoded `@ref` numbers.
- `--json` flag on any command gives structured output for parsing.

### 3. Capture Evidence

Take screenshots at each significant state change:
```bash
agent-swift screenshot /tmp/e2e-step-01-before.png
# ... perform action ...
agent-swift screenshot /tmp/e2e-step-02-after.png
```

Generate a video report from screenshots:
```bash
ffmpeg -framerate 1 -pattern_type glob -i '/tmp/e2e-step-*.png' \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1" \
  -c:v libx264 -pix_fmt yuv420p /tmp/e2e-report.mp4
```

### 4. Report Results

Summarize findings with pass/fail per check, include screenshot paths, and flag any regressions.

## App Architecture Reference

### Sidebar Navigation (SidebarView.swift)
Main sidebar icons — use `click`:

| Label | Section |
|-------|---------|
| `Home` | Home/Dashboard |
| `Conversation` | Conversations list |
| `brain` | Memories |
| `checklist` | Action items |
| `puzzlepiece.fill` | Integrations |
| `gearshape.fill` | Settings |

### Settings Sidebar (SettingsSidebar.swift)
Settings sections — use `press` (these are SwiftUI Button views):

| Section | Key UI elements |
|---------|----------------|
| General | App preferences |
| Rewind | Screenshot/timeline settings |
| Transcription | Language Mode (Auto-Detect / Single Language), language picker |
| Notifications | Alert preferences |
| Privacy | Data settings |
| Account | User info |
| AI Chat | Chat model settings |
| Advanced | Developer options |
| About | Version info |

### System Tray Menu
Menu bar items with identifiers: `openOmi`, `checkFor`, `resetOnb`, `reportIs`, `signOut`, `quitApp`.

## Known Verification Flows

Reference flows are defined in `desktop/e2e/flows/*.yaml`. Read these to understand what to verify for each area of the app. Each flow lists:
- `covers:` — which Swift source files it maps to
- `steps:` — the sequence of actions and assertions

When you modify a SwiftUI view, check if any flow's `covers:` field includes your file. If so, execute that flow's steps using the commands above.

| Flow | Covers | What it verifies |
|------|--------|-----------------|
| `flows/navigation.yaml` | SidebarView, DesktopHomeView, OmiApp | Sidebar icons exist, section switching works, text input, scroll, tray menu |
| `flows/language.yaml` | SettingsPage, SettingsSidebar, SidebarView | Settings nav, Transcription section, language mode radio buttons, picker |

### Adding a New Flow

Create `desktop/e2e/flows/<name>.yaml`:
```yaml
name: my-flow
description: What this flow verifies
covers:
  - Desktop/Sources/path/to/YourView.swift
setup: normal   # normal | fresh_auth | signed_out
steps:
  - name: Step description
    click: { type: image, label: "gearshape.fill" }
    screenshot: step-name
  - name: Verify result
    assert: { text: "Expected Text" }
```

## Decision Tree

### Element not found
1. Re-snapshot: `agent-swift snapshot -i --json`
2. Check if element requires scrolling: `agent-swift scroll down`, then re-snapshot
3. Check if element is behind a navigation action (wrong screen)
4. Check if label/type changed in the source code
5. If element genuinely doesn't exist → this is a regression, report it

### Click doesn't trigger navigation
1. Try `press` instead of `click` (or vice versa)
2. Rule of thumb: main sidebar = `click`, settings sidebar = `press`
3. Check if the element is an image vs button — images with onTapGesture need `click`
4. Try `find text "Label" click` instead of clicking by ref

### Picker/dropdown not responding
1. SwiftUI Picker with `.menu` style may not expose as `popupbutton` in accessibility
2. Look for a `button` element with the current value as its label
3. After clicking, menu items appear as `menuitem` type elements

### App seems frozen
1. Check `agent-swift status --json` for connection
2. Re-connect: `agent-swift connect --bundle-id com.omi.desktop-dev`
3. Check app logs: `tail -20 /private/tmp/omi-dev.log`

## Guard Conditions

**STOP and report if:**
- `agent-swift doctor` fails (Accessibility permission not granted)
- App is not running (no `Omi Dev` process found)
- Connection fails after 3 retries
- A non-optional assertion fails — this is a real bug, don't retry

**NEVER:**
- Automate the production app (`com.omi.computer-macos`)
- Kill or restart the production Omi app
- Use development env vars to bypass auth
- Set `hasCompletedOnboarding` to skip onboarding
- Modify app source code to make tests pass — if it fails, report the failure
