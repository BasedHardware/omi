# E2E Tests (agent-flutter)

Automated end-to-end tests using [agent-flutter](https://github.com/beastoin/agent-flutter) to control the running Omi app via Dart VM Service + Marionette.

## Prerequisites

- Android emulator running (`adb devices` shows `emulator-5554`)
- Omi app running in debug mode (`flutter run -d emulator-5554 --flavor dev`)
- agent-flutter installed: `npm install -g beastoin/agent-flutter`

## Quick Start

```bash
# 1. Start the app (in background, log to file)
cd app && flutter run -d emulator-5554 --flavor dev 2>&1 | tee /tmp/flutter-run.log &

# 2. Wait for "Dart VM Service" to appear in the log
grep -m1 "Dart VM Service" <(tail -f /tmp/flutter-run.log)

# 3. Run all flows
AGENT_FLUTTER_LOG=/tmp/flutter-run.log app/e2e/run-all.sh

# 4. Run a single flow
AGENT_FLUTTER_LOG=/tmp/flutter-run.log app/e2e/flow1-home-navigation.sh
```

## Flows

| Flow | What it tests |
|------|--------------|
| `flow1-home-navigation.sh` | Home screen elements, top-bar buttons, screen transitions |
| `flow2-settings-toggle.sh` | Settings navigation, sub-page entry, switch toggle, state verification |
| `flow3-tab-navigation.sh` | Bottom nav tabs, list rendering, scroll, back navigation |
| `run-all.sh` | Runs all flows sequentially, reports pass/fail summary |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_FLUTTER_LOG` | Yes | Path to flutter run log file (for auto-detect) |
| `AGENT_FLUTTER_DEVICE` | No | Device ID (default: `emulator-5554`) |
| `E2E_SCREENSHOT_DIR` | No | Screenshot output dir (default: `/tmp/omi-e2e`) |

## Writing New Flows

Use the helper functions from `e2e-helpers.sh`:

```bash
source "$(dirname "$0")/e2e-helpers.sh"
e2e_setup "my-flow-name"

e2e_step "Navigate to screen"
af snapshot -i
af press @e3
af_wait

e2e_step "Verify element exists"
af_find_type "button" || e2e_fail "No button found"
af screenshot "$SCREENSHOT_DIR/my-screenshot.png"

e2e_teardown
```
