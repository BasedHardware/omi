# agent-flutter E2E Reference Flows

Reference implementations showing how AI agents use agent-flutter to interact with the Omi Flutter app. These serve two purposes:

1. **Examples** — agents can read these to learn the agent-flutter workflow patterns
2. **Validation** — run them to verify the app's core interactions still work

## Prerequisites

- Android emulator running (`adb devices`)
- Node.js 18+ with agent-flutter: `npm install -g agent-flutter-cli`
- Omi app in debug mode (Marionette is auto-enabled in debug builds)

## Quick Start

```bash
# Fully automated: boots flutter, connects, runs all flows, reports results
app/e2e/run-all.sh

# With an existing flutter run session
AGENT_FLUTTER_LOG=/tmp/flutter-run.log app/e2e/run-all.sh
```

## Flows

| Flow | Steps | What it demonstrates |
|------|-------|---------------------|
| flow1-home-navigation | 4 | Snapshot, find rightmost button, screen transitions, back |
| flow2-settings-toggle | 7 | Deep navigation (3 levels), find switch widget, toggle ON/OFF |
| flow3-tab-navigation | 6 | Bottom nav InkWell detection, 4-tab switching, scroll |
| flow4-language-change | 8 | 4-level deep nav, bottom sheet picker, shared_prefs locale swap |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_FLUTTER_LOG` | (auto) | Flutter run log file — how agent-flutter finds the VM Service URI |
| `AGENT_FLUTTER_DEVICE` | `emulator-5554` | ADB device ID |
| `E2E_FAST` | `1` | Skip screenshots for speed |
| `E2E_WAIT` | `0.2` | Seconds between actions |
| `E2E_SCREENSHOT_DIR` | `/tmp/omi-e2e` | Screenshot output directory |

## Key Patterns in the Helpers (`e2e-helpers.sh`)

- **`af()`** — Wrapper around `agent-flutter` that auto-reconnects on "No isolate with Marionette" errors
- **`_go_home()`** — Navigates to home tab by finding leftmost InkWell at y > 780
- **`_is_healthy()`** — Verifies widget tree has >= 5 interactive elements
- **`af_find_type`** — Finds widget by type and returns its ref (more stable than hardcoded refs)
- **`e2e_setup/teardown`** — Brings app to foreground, connects, navigates home, reports pass/fail counts

## Writing New Flows

```bash
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "my-flow-name"

e2e_step "Do something"
af_find_press "button"    # find first button and press it
af_wait                    # wait for UI to settle
e2e_pass "Did the thing"

e2e_teardown
```
