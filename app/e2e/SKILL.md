---
name: mobile-app-flows
description: "Understand and explore the Omi Flutter mobile app's UI flows, navigation patterns, and widget architecture. Use when developing features, fixing bugs, or verifying changes in app/lib/ Dart files. Provides agent-flutter commands to explore the live app, understand how screens connect, and verify your work."
allowed-tools: Bash, Read, Glob, Grep
---

# Omi Mobile App — Flows & Exploration

This skill teaches you the Omi Flutter mobile app's navigation structure, screen architecture, and widget patterns. Use it when developing features (to understand how the app works), fixing bugs (to navigate to the affected screen), or verifying changes (to confirm your code works in the live app).

## How to Explore the App

You can interact with the running app via `agent-flutter` — a CLI that taps widgets, reads the widget tree, and captures screenshots through Flutter's Marionette debug protocol.

### Setup
```bash
# Emulator must be running (adb devices), app in debug mode
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect
agent-flutter snapshot -i --json    # see what's on screen
```

### Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `snapshot -i --json` | See all interactive widgets with refs, types, bounds | `agent-flutter snapshot -i --json` |
| `press @ref` | Tap a widget | `agent-flutter press @e3` |
| `find type X press` | Find widget by type and tap | `agent-flutter find type button press` |
| `find text "X" press` | Find by visible text and tap | `agent-flutter find text "Settings" press` |
| `find type X --index N press` | Tap Nth match (0-indexed) | `agent-flutter find type switch --index 0 press` |
| `fill @ref "text"` | Type into text field | `agent-flutter fill @e7 "search"` |
| `scroll down/up` | Scroll current view | `agent-flutter scroll down` |
| `back` | Android back button | `agent-flutter back` |
| `screenshot PATH` | Capture current screen | `agent-flutter screenshot /tmp/screen.png` |

**Key rules:**
- Refs go stale after any mutation — always re-snapshot before the next interaction.
- `find type X` is more stable than hardcoded `@ref` numbers.
- `AGENT_FLUTTER_LOG` must point to `flutter run` stdout (not logcat).
- After hot restart: `disconnect` → wait 3s → `connect`.
- Widget text labels are often null — use `type`, `flutterType`, or `bounds` to identify.

### Recovery
```bash
# "No isolate with Marionette" → bring app to foreground + reconnect
adb -s emulator-5554 shell am start -n com.friend.ios.dev/com.friend.ios.MainActivity
agent-flutter disconnect && agent-flutter connect

# Unhealthy widget tree → hot restart
kill -SIGUSR2 $(pgrep -f "flutter_tools.*run" | head -1)
sleep 3 && agent-flutter disconnect && agent-flutter connect
```

## App Navigation Architecture

### Screen Map
```
Home (page.dart)
├── [top-right button] → Settings (settings_drawer.dart)
│   ├── [1st row] → Profile (profile.dart)
│   │   ├── Name, Email
│   │   └── Language → Language Settings (language_settings_page.dart)
│   │       └── App Language → Bottom sheet picker (language_selection_dialog.dart)
│   ├── [scroll down] → Developer Settings (developer.dart)
│   │   └── Switch toggles for debug features
│   ├── Transcription Settings (transcription_settings_page.dart)
│   ├── Notification Settings (notifications_settings_page.dart)
│   ├── Privacy (privacy.dart)
│   ├── Device Settings (device_settings.dart)
│   └── About (about.dart)
├── [bottom nav tab 1] → Home / Conversations
├── [bottom nav tab 2] → Chat
├── [bottom nav tab 3] → Memories
└── [bottom nav tab 4] → Apps
```

### Widget Patterns

**Bottom navigation bar:**
- 4 `InkWell` widgets at `bounds.y > 780`, sorted left-to-right by `bounds.x`
- Detect with: `snapshot -i --json` → filter `flutterType == 'InkWell'` and `bounds.y > 780`
- Navigate home: press the leftmost one

**Settings gear:**
- Rightmost `button` widget in the top bar
- Detect with: sort buttons by `bounds.x` descending, take first

**Settings rows:**
- `gesture` widgets with `bounds.width > 300`
- Position-based: Profile is y=150-200, Developer Settings is y=400-520 after scrolling

**Switch toggles:**
- Type `switch` in snapshots
- Press to toggle ON/OFF (no separate ON/OFF actions)

**Bottom sheet pickers:**
- Open when you press a settings row
- Language items appear as `gesture` rows with `bounds.y > 380`
- Many items — use scroll if needed

### Changing Locale
```bash
DEVICE=emulator-5554; APP_PKG=com.friend.ios.dev

# Read current
adb -s $DEVICE shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" | grep app_locale

# Change to Spanish, hot restart to apply
adb -s $DEVICE shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" > /tmp/prefs.xml
sed -i 's|flutter.app_locale">[^<]*|flutter.app_locale">es|' /tmp/prefs.xml
adb -s $DEVICE push /tmp/prefs.xml /data/local/tmp/FlutterSharedPreferences.xml
adb -s $DEVICE shell "run-as $APP_PKG cp /data/local/tmp/FlutterSharedPreferences.xml shared_prefs/FlutterSharedPreferences.xml"
kill -SIGUSR2 $(pgrep -f "flutter_tools.*run" | head -1)
sleep 3 && agent-flutter disconnect && agent-flutter connect
```

## Known Flows

Reference flows in `app/e2e/flows/*.yaml` describe the app's key user journeys. Read these to understand navigation paths and expected UI state. Each flow lists `covers:` (source files) and `steps:` (actions + assertions).

| Flow | Covers | What it describes |
|------|--------|-------------------|
| `flows/home-navigation.yaml` | page.dart, settings_drawer.dart | Home → Settings → scroll → back |
| `flows/settings-toggle.yaml` | settings_drawer.dart, developer.dart | Home → Settings → Developer → switch toggle |
| `flows/tab-navigation.yaml` | page.dart | Bottom nav: switching between 4 tabs |
| `flows/language-change.yaml` | profile.dart, language_settings_page.dart | Settings → Profile → Language → picker → locale swap |

When you modify a Dart file, check if any flow's `covers:` includes it. If so, that flow describes the user journey your change affects — use it to understand context and verify your work.

## Verification & Evidence

After making changes, verify them in the live app:
1. Navigate to the affected screen using the commands above
2. Check that your changes appear (snapshot, screenshot)
3. Test interactions (press buttons, fill fields, scroll)
4. Capture evidence: `agent-flutter screenshot /tmp/evidence.png`
5. Generate video: `ffmpeg -framerate 1 -pattern_type glob -i '/tmp/e2e-*.png' -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1" -c:v libx264 -pix_fmt yuv420p /tmp/report.mp4`

## Decision Tree

| Problem | Solution |
|---------|----------|
| Widget not found | Re-snapshot, try scrolling, check if on wrong screen, match by bounds position |
| "No isolate with Marionette" | ADB foreground + disconnect + reconnect |
| Bottom nav tabs not detected | `back` until nav bar appears, filter InkWell y > 780 |
| Hot restart breaks connection | Wait 3s → disconnect → connect |
| Text labels null | Match by `type`, `flutterType`, or `bounds` — Marionette doesn't extract child text |

## Guard Conditions

**NEVER:**
- Use development env vars to bypass auth — test with real auth flows
- Set `hasCompletedOnboarding` to skip onboarding — test the real flow
- Modify source code to make tests pass — report the failure instead
- Commit screenshots to git — use GCS upload for PR evidence
