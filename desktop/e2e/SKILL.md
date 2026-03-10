# Desktop E2E Test Flows

Declarative YAML-based E2E testing for the Omi desktop macOS app, powered by [agent-swift](https://github.com/beastoin/agent-swift).

## Flow-to-View Map

| Flow | YAML | Swift Files Covered |
|------|------|---------------------|
| navigation | `flows/navigation.yaml` | SidebarView.swift, DesktopHomeView.swift, OmiApp.swift |
| language | `flows/language.yaml` | SettingsPage.swift, SettingsSidebar.swift, SidebarView.swift |

## When to Update Flows

- Modified a SwiftUI view? Check `covers:` in each YAML for your file.
- Changed sidebar icons/labels? Update `navigation.yaml` step "Verify sidebar navigation icons".
- Changed settings sections? Update `language.yaml` or add a new flow.
- Added a new view? Consider adding a flow for it.

## Running Flows

```bash
# Single flow
python3 desktop/e2e/runner.py navigation

# All flows
python3 desktop/e2e/runner.py --all

# List available flows
python3 desktop/e2e/runner.py --list

# With video output
python3 desktop/e2e/runner.py --all --video

# Via SSH to Mac Mini
E2E_SSH_HOST=100.126.187.125 python3 desktop/e2e/runner.py --all

# Skip screenshots (fast mode)
E2E_FAST=1 python3 desktop/e2e/runner.py navigation
```

## Adding a New Flow

1. Create `desktop/e2e/flows/<name>.yaml`
2. Set required fields: `name`, `description`, `covers`, `setup`, `steps`
3. Update the Flow-to-View Map table above
4. Run: `python3 desktop/e2e/runner.py <name>`

## YAML Schema

```yaml
name: my-flow                    # Flow identifier
description: What this tests     # Human-readable description
covers:                          # Swift files this flow tests
  - Desktop/Sources/path/to/View.swift
setup: normal                    # normal | fresh_auth | signed_out
bundle_id: com.omi.desktop-dev   # Override target app (optional)

steps:
  - name: Step description       # Required
    click: { ... }               # Action (see below)
    assert: { ... }              # Assertion (see below)
    screenshot: name             # Screenshot after step (optional)
    optional: true               # Don't fail flow if step fails (optional)
    save_ref: var_name           # Save found ref to variable (optional)
    save_as: var_name            # Save get result to variable (optional)
```

## Step Actions

| Action | Description | Example |
|--------|-------------|---------|
| `click` | CGEvent click (SwiftUI) | `click: { type: image, label: "gearshape.fill" }` |
| `press` | AXPress (AppKit/Settings sidebar) | `press: { text: "Transcription" }` |
| `fill` | Type into text field | `fill: { type: textfield, value: "test" }` |
| `scroll` | Scroll direction(s) | `scroll: down` or `scroll: [down, up]` |
| `wait` | Wait for condition | `wait: { text: "Settings", timeout: 5000 }` |
| `assert` | Verify element exists | `assert: { text: "Home" }` |
| `assert_each` | Check multiple labels | `assert_each: { type: image, labels: [...], min_found: 4 }` |
| `find` | Find element, save ref | `find: { role: button }` + `save_ref: btn` |
| `get` | Read element property | `get: { property: value, type: popupbutton }` |
| `dismiss` | Non-fatal press | `dismiss: { text: "OK" }` |
| `navigate_sidebar` | Click through sidebar items | see navigation.yaml |
| `click_menu_item` | Try clicking menu items | `click_menu_item: { try_labels: ["Spanish", "French"] }` |
| `screenshot` | Capture app window | `screenshot: step-name` |

## Element Matching

Steps that find elements support these criteria:

| Key | Matches |
|-----|---------|
| `type` | Element type (`button`, `image`, `statictext`, `popupbutton`, etc.) |
| `label` | Exact label match |
| `value` | Exact value match |
| `text` | Match in either value or label |
| `text_contains` | Substring match in value or label |
| `value_contains` | Substring match in value |
| `role` | Element role |
| `fallback_label` | Try this label if primary match fails |

## Variables

Steps can save element refs or property values for later steps:
- `save_ref: var_name` — saves found element ref (from `find`)
- `save_as: var_name` — saves property value (from `get`)
- Reference with `$var_name` in later steps: `assert: { exists: "$btn_ref" }`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SWIFT` | auto-detect | Path to agent-swift binary |
| `E2E_SSH_HOST` | (local) | SSH host for remote execution |
| `E2E_SSH_USER` | `sudo launchctl asuser 501 sudo -u beastoinagents` | SSH GUI user prefix |
| `E2E_SCREENSHOT_DIR` | `/tmp/omi-desktop-e2e` | Screenshot output directory |
| `E2E_WAIT` | `0.5` | Settle time (seconds) between actions |
| `E2E_FAST` | (off) | Set to `1` to skip screenshots |
| `E2E_BUNDLE_ID` | from YAML | Override target bundle ID |
