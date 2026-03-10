---
name: mobile-e2e-verify
description: "Autonomously verify Omi Flutter mobile app UI changes using agent-flutter. Use after editing Dart UI code, when asked to test mobile changes, or when verifying a PR that touches app/lib/ Dart files. Captures screenshot evidence and generates video reports."
allowed-tools: Bash, Read, Glob, Grep
---

# Mobile E2E Verification

You are an autonomous agent verifying the Omi Flutter mobile app. You have full control of the app via `agent-flutter` — a CLI that taps widgets, reads the widget tree, and captures screenshots through the Marionette debug protocol. No human intervention needed.

## Prerequisites

1. Android emulator running: `adb devices` should show a device (default: `emulator-5554`)
2. Flutter app running in debug mode: `cd app && flutter run -d emulator-5554 --flavor dev`
3. agent-flutter installed: `npm install -g agent-flutter-cli`
4. `AGENT_FLUTTER_LOG` pointing to the flutter run stdout log file

Quick check:
```bash
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect
agent-flutter snapshot -i   # should show interactive widgets
```

## Core Workflow

### 1. Connect and Orient

```bash
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect
agent-flutter snapshot -i --json
```

The snapshot returns Flutter widgets with `ref`, `type`, `flutterType`, `bounds` (x, y, width, height), and optional `text`/`label` fields.

### 2. Explore and Verify

Use these commands to interact with the app. **Always re-snapshot after any mutation** — refs go stale after every press/fill/scroll.

| Command | When to use | Example |
|---------|-------------|---------|
| `press @ref` | Tap any widget | `agent-flutter press @e3` |
| `find type X press` | Find by widget type and tap | `agent-flutter find type button press` |
| `find type X --index N press` | Tap Nth match (0-indexed) | `agent-flutter find type switch --index 0 press` |
| `find text "X" press` | Find by text content and tap | `agent-flutter find text "Settings" press` |
| `fill @ref "text"` | Type into text field | `agent-flutter fill @e7 "search"` |
| `scroll down/up` | Scroll current view | `agent-flutter scroll down` |
| `back` | Android back button | `agent-flutter back` |
| `snapshot -i` | List interactive widgets | `agent-flutter snapshot -i` |
| `snapshot -i --json` | Structured widget data | `agent-flutter snapshot -i --json` |
| `screenshot PATH` | Capture screen | `agent-flutter screenshot /tmp/evidence.png` |

**Key rules:**
- `find type X` or `find text "label"` is more stable than hardcoded `@ref` numbers.
- `AGENT_FLUTTER_LOG` must point to the `flutter run` stdout log file (not logcat). This is how agent-flutter finds the correct VM Service URI.
- After hot restart, you must `disconnect` then `connect` again.
- Widget text labels may be null in snapshots — Marionette doesn't extract child text to parent widgets. Use `bounds` position to identify widgets when text isn't available.
- Bottom nav tabs are `InkWell` widgets with `bounds.y > 780`, sorted by `bounds.x` (left to right).

### 3. Recovery

If you get "No isolate with Marionette":
```bash
# Bring app to foreground
adb -s emulator-5554 shell am start -n com.friend.ios.dev/com.friend.ios.MainActivity

# Reconnect
agent-flutter disconnect
agent-flutter connect
```

If the widget tree is unhealthy (< 5 interactive elements), hot restart:
```bash
kill -SIGUSR2 $(pgrep -f "flutter_tools.*run" | head -1)
sleep 3
agent-flutter disconnect
agent-flutter connect
```

### 4. Capture Evidence

Take screenshots at each significant state change:
```bash
agent-flutter screenshot /tmp/e2e-step-01-before.png
# ... perform action ...
agent-flutter screenshot /tmp/e2e-step-02-after.png
```

Generate a video report from screenshots:
```bash
ffmpeg -framerate 1 -pattern_type glob -i '/tmp/e2e-step-*.png' \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1" \
  -c:v libx264 -pix_fmt yuv420p /tmp/e2e-report.mp4
```

### 5. Report Results

Summarize findings with pass/fail per check, include screenshot paths, and flag regressions.

## App Architecture Reference

### Home Screen (page.dart)
- Top bar: settings gear button (rightmost `button` widget)
- Main content: conversation list or empty state
- Bottom nav: 4 `InkWell` tabs at y > 780, sorted left-to-right (Home, Chat, Memories, Apps)

### Settings (settings_drawer.dart)
- Profile row (first wide `gesture` widget, y=150-200)
- Settings rows: scrollable list of `gesture` widgets
- Developer Settings: after scrolling, wide `gesture` in y=400-520 range

### Developer Settings (developer.dart)
- `switch` widgets for toggling features
- Toggle ON/OFF by pressing the switch ref

### Profile → Language (profile.dart, language_settings_page.dart)
- Language row: 3rd wide `gesture` in Profile (y=250-340)
- App Language picker: bottom sheet with many `gesture` rows for each language
- Locale change via ADB: modify `flutter.app_locale` in shared_prefs XML

### Changing Locale via ADB
```bash
DEVICE=emulator-5554
APP_PKG=com.friend.ios.dev

# Read current locale
adb -s $DEVICE shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" | grep app_locale

# Change to Spanish
adb -s $DEVICE shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" > /tmp/prefs.xml
sed -i 's|flutter.app_locale">[^<]*|flutter.app_locale">es|' /tmp/prefs.xml
adb -s $DEVICE push /tmp/prefs.xml /data/local/tmp/FlutterSharedPreferences.xml
adb -s $DEVICE shell "run-as $APP_PKG cp /data/local/tmp/FlutterSharedPreferences.xml shared_prefs/FlutterSharedPreferences.xml"

# Hot restart to apply
kill -SIGUSR2 $(pgrep -f "flutter_tools.*run" | head -1)
sleep 3 && agent-flutter disconnect && agent-flutter connect
```

## Known Verification Flows

Reference flows are defined in `app/e2e/flows/*.yaml`. Read these to understand what to verify for each area of the app. Each flow lists:
- `covers:` — which Dart source files it maps to
- `steps:` — the sequence of actions and assertions

When you modify a Dart UI file, check if any flow's `covers:` field includes your file. If so, execute that flow's verification steps.

| Flow | Covers | What it verifies |
|------|--------|-----------------|
| `flows/home-navigation.yaml` | page.dart, settings_drawer.dart | Home snapshot, settings gear, scroll, back |
| `flows/settings-toggle.yaml` | settings_drawer.dart, developer.dart | 3-level navigation, switch toggle ON/OFF |
| `flows/tab-navigation.yaml` | page.dart | Bottom nav bar detection, 4-tab switching, scroll |
| `flows/language-change.yaml` | settings_drawer.dart, profile.dart, language_settings_page.dart | Deep nav, picker, locale swap, hot restart |

### Adding a New Flow

Create `app/e2e/flows/<name>.yaml`:
```yaml
name: my-flow
description: What this flow verifies
covers:
  - app/lib/pages/path/to/your_file.dart
setup: normal
steps:
  - name: Step description
    press: { type: button, position: rightmost }
    screenshot: step-name
  - name: Verify result
    assert: { interactive_count: { min: 5 } }
```

## Decision Tree

### Widget not found
1. Re-snapshot: `agent-flutter snapshot -i --json`
2. Try scrolling: `agent-flutter scroll down`, then re-snapshot
3. Check if on the wrong screen — use `back` to navigate
4. Widget text labels are often null — match by `type`, `flutterType`, or `bounds` position
5. If genuinely missing → regression, report it

### "No isolate with Marionette"
1. Bring app to foreground via ADB: `adb shell am start -n com.friend.ios.dev/com.friend.ios.MainActivity`
2. Disconnect + reconnect: `agent-flutter disconnect && agent-flutter connect`
3. If still failing, hot restart: `kill -SIGUSR2 $(pgrep -f "flutter_tools.*run" | head -1)`

### Bottom nav tabs not detected
1. Tabs are `InkWell` widgets with `bounds.y > 780`
2. If not found, app may be on a detail page — press `back` until nav bar appears
3. Sort by `bounds.x` to get left-to-right order

### Hot restart breaks connection
1. After `kill -SIGUSR2`, wait 3 seconds
2. `agent-flutter disconnect`
3. `agent-flutter connect`
4. Verify with `agent-flutter snapshot -i`

## Guard Conditions

**STOP and report if:**
- No Android emulator detected (`adb devices` shows nothing)
- agent-flutter cannot connect after 3 retries
- Widget tree has < 5 interactive elements after recovery
- A non-optional assertion fails — this is a real bug

**NEVER:**
- Use development env vars to bypass auth
- Set `hasCompletedOnboarding` to skip onboarding
- Modify Dart source code to make tests pass — if it fails, report the failure
- Run against production builds
- Commit screenshots to the git repo (use GCS upload for PR evidence)
