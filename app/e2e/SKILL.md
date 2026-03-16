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
# 1. Emulator must be running
adb devices                          # should show emulator-5554
# If not: sg kvm -c "$ANDROID_HOME/emulator/emulator -avd omi-dev -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim &"

# 2. Set system language to English (REQUIRED — non-English IME breaks text input)
adb shell "settings put system system_locales en-US"
adb shell "setprop persist.sys.locale en-US"

# 3. App must be running in debug mode with flutter run stdout captured
cd app && flutter run -d emulator-5554 --flavor dev > /tmp/omi-flutter.log 2>&1 &
# Wait for "VM Service" line to appear in the log

# 4. Connect agent-flutter (AGENT_FLUTTER_LOG must point to flutter run stdout, NOT logcat)
AGENT_FLUTTER_LOG=/tmp/omi-flutter.log agent-flutter connect
agent-flutter snapshot -i --json    # see what's on screen
```

**Prerequisites:**
- AVD name: `omi-dev` (check: `$ANDROID_HOME/emulator/emulator -list-avds`)
- KVM access required: user must be in `kvm` group (`sg kvm -c "..."` if not in current session)
- App package: `com.friend.ios.dev` (dev flavor)
- **System language must be English** — non-English IME breaks `fill` commands
- **App must be authenticated and connected to the correct backend** (local, dev, or prod — depends on the task)
- Marionette already integrated: `marionette_flutter: ^0.3.0` in pubspec.yaml

### Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `snapshot -i --json` | See all interactive widgets with refs, types, bounds | `agent-flutter snapshot -i --json` |
| `press @ref` | Tap a widget by ref | `agent-flutter press @e3` |
| `press x y` | Tap by coordinates (ADB input tap) | `agent-flutter press 540 1200` |
| `press @ref --adb` | Tap by ref using ADB (for stale refs) | `agent-flutter press @e3 --adb` |
| `dismiss` | Dismiss system dialogs (location, permissions) | `agent-flutter dismiss` |
| `find type X press` | Find widget by type and tap | `agent-flutter find type button press` |
| `find text "X" press` | Find by visible text and tap | `agent-flutter find text "Settings" press` |
| `find type X --index N press` | Tap Nth match (0-indexed) | `agent-flutter find type switch --index 0 press` |
| `fill @ref "text"` | Type into text field | `agent-flutter fill @e7 "search"` |
| `scroll down/up` | Scroll current view | `agent-flutter scroll down` |
| `back` | Android back button | `agent-flutter back` |
| `screenshot PATH` | Capture current screen | `agent-flutter screenshot /tmp/screen.png` |

**Key rules:**
- Refs go stale frequently (Flutter rebuilds widget tree aggressively) — always re-snapshot before every interaction, not just after mutations.
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
Onboarding (wrapper.dart) — 11-step wizard
├── 0: Auth (auth.dart) — Google/Apple sign-in
├── 1: Name (name_widget.dart)
├── 2: Primary Language (primary_language_widget.dart)
├── 3: Found Omi (found_omi_widget.dart)
├── 4: Permissions (permissions_widget.dart)
├── 5: User Review (user_review_page.dart)
├── 6-7: Welcome / Find Devices (placeholders)
├── 8: Speech Profile (speech_profile_widget.dart)
├── 9: Knowledge Graph (knowledge_graph_step.dart)
└── 10: Complete (complete_screen.dart)

Home (page.dart) — main app after auth
├── [top bar] Connect Device | Search | History | Settings gear
├── [center] Daily Score card → Add Goal
├── [Ask Omi button] → Chat (chat/page.dart)
│   └── Text input, voice recorder, AI responses, message actions
├── [record button] → Conversation Capturing (conversation_capturing/page.dart)
│   └── Live transcript, waveform, stop button
│
├── [tab 0] Conversations (conversations_page.dart)
│   ├── Folder tabs (All, Starred, custom folders)
│   ├── Daily summaries toggle
│   ├── Today's tasks widget
│   └── Conversation item → Detail (conversation_detail/page.dart)
│       └── Transcript, Summary, Action Items tabs, share, audio
│
├── [tab 1] Action Items (action_items_page.dart)
│   ├── Categories: Today, Tomorrow, Later, No Deadline, Overdue
│   ├── FAB → Create task sheet (action_item_form_sheet.dart)
│   ├── Task checkboxes, drag-drop reorder
│   └── Task → Goal linking
│
├── [tab 2] Memories (memories/page.dart)
│   ├── Search bar, graph button, management button
│   ├── FAB → Add memory dialog
│   ├── Category chips filter
│   ├── Memory item → Quick edit sheet (memory_edit_sheet.dart)
│   ├── Graph → Memory Graph (memory_graph_page.dart)
│   └── Management → Category management sheet
│
├── [tab 3] Apps (apps/page.dart)
│   ├── Search, filter, create buttons
│   ├── Popular apps (horizontal scroll)
│   ├── Category sections → Category apps page
│   ├── App item → App Detail (app_detail/app_detail.dart)
│   │   └── Reviews, capabilities, install/enable
│   └── Create → Custom app or MCP server
│
└── [settings gear] → Settings Drawer (settings_drawer.dart)
    ├── Profile (profile.dart)
    │   ├── Name → Change name dialog
    │   ├── Email (read-only)
    │   ├── Language → Language Settings (language_settings_page.dart)
    │   ├── Custom Vocabulary (custom_vocabulary_page.dart)
    │   ├── Speech Profile (speech_profile/page.dart)
    │   ├── Identifying Others (people.dart)
    │   ├── Payment Methods (payments/payments_page.dart)
    │   ├── Conversation Display (conversation_display_settings.dart)
    │   ├── Data Privacy (data_privacy_page.dart)
    │   └── Delete Account (delete_account.dart)
    ├── Notifications (notifications_settings_page.dart)
    │   ├── Frequency slider (0-5)
    │   ├── Daily Summary toggle + time picker
    │   └── Daily Reflection toggle
    ├── Plan & Usage (usage_page.dart)
    ├── Offline Sync (sync_page.dart)
    │   ├── Local storage, recordings list
    │   ├── Fast transfer settings
    │   └── Private cloud sync
    ├── Device Settings (device_settings.dart) — requires BLE device
    │   ├── Device info (name, ID, firmware, SD card)
    │   ├── LED brightness slider, mic gain slider
    │   └── Double tap action picker
    ├── Integrations (integrations_page.dart) — BETA
    │   └── Google Calendar, Gmail, Apple Health
    ├── Phone Calls (phone_call_settings_page.dart)
    │   └── Verified numbers list, delete button
    ├── Transcription Settings (transcription_settings_page.dart)
    │   ├── Source toggle: Omi Cloud vs Custom STT
    │   ├── Provider selector, API key, model config
    │   └── Advanced JSON editors, logs viewer
    ├── Developer Settings (developer.dart)
    │   ├── Custom STT provider config
    │   ├── API key management
    │   └── MCP API keys
    ├── What's New → Changelog sheet
    ├── Referral Program (referral_page.dart) — NEW
    └── Sign Out → Confirmation dialog

Persona Profile (persona_profile.dart) — AI clone management
├── Avatar (100x100), name with verified badge
├── Share Public Link button
├── Make Public toggle
└── 10 social link rows (omi, Twitter active; others Coming Soon)
    └── Twitter → Social Handle Entry → Verify Identity → Clone Success

Connected Device (home/device.dart) — requires BLE
├── Device name, connection status, battery
├── Actions: Firmware Update, SD Card Sync, Disconnect, Unpair
└── Device info: Product, Model, Manufacturer, Firmware, ID, Serial

Speech Profile (speech_profile/page.dart)
├── Device animation, intro text
├── Get Started / Do It Again button
├── Question flow: text, progress bar, skip
└── Listen to Speech Profile (if samples exist)
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

## Prerequisites Reference

Every flow lists `prerequisites:` — conditions that MUST be true before running. These describe the **real user state** — no bypasses, no shortcuts. Test the app the way users experience it.

| Prerequisite | What it means | How to achieve (Android) | How to achieve (iOS) |
|-------------|---------------|--------------------------|----------------------|
| `auth_ready` | User completed sign-in (Google or Apple), app shows home screen | Run `bash setup.sh android` → launch app → complete Google Sign-In flow → complete onboarding | Run `bash setup.sh ios` → launch on simulator or device → complete Google/Apple Sign-In → complete onboarding |
| `signed_out` | Fresh app, user NOT signed in, shows Get Started screen | Uninstall + reinstall, or clear app data via Settings → Apps → Omi → Clear Data | Delete app from simulator/device and reinstall |
| `microphone_permission` | App has mic permission granted | When app requests mic permission during use, tap "Allow". Or pre-grant: `adb shell pm grant com.friend.ios.dev android.permission.RECORD_AUDIO` | When app requests mic permission, tap "Allow" in the iOS permission dialog |
| `ble_on` | Bluetooth enabled on device | Enable Bluetooth in device Settings → Connected Devices. **Emulators/simulators do not support BLE** — requires physical device | Enable Bluetooth in device Settings. **iOS Simulator has no BLE** — requires physical iPhone |
| `omi_device_connected` | Omi hardware paired and connected via BLE | Power on Omi device within BLE range → app auto-discovers on home screen → tap Connect. **Physical device only** | Same — power on Omi, app discovers it. **Physical iPhone only** |
| `phone_number_verified` | Phone number added and verified in settings | Settings → Phone Calls → add phone number → receive SMS → enter code. Requires real phone number | Same flow — requires real phone number that receives SMS |
| `developer_settings_enabled` | Developer Settings screen is open | Settings drawer → scroll down → tap "Developer Settings" (visible to all users) | Same navigation path |
| `adb_access` | Shell access for locale/prefs manipulation (Android only) | Debug build + `adb` in PATH. Verify: `adb shell run-as com.friend.ios.dev ls shared_prefs/` | Not applicable — iOS equivalent uses `xcrun simctl` for simulator or Xcode for device |

### Prerequisite dependency chain
```
signed_out ─── (fresh install, no prior state)

auth_ready ─── launch app → sign in with Google/Apple → complete onboarding
  │             (this is the REAL user flow — no bypasses)
  ├── microphone_permission  (grant when prompted, or pre-grant via platform tools)
  ├── developer_settings_enabled  (navigate in-app to Settings → Developer Settings)
  ├── phone_number_verified  (in-app SMS verification — manual step)
  ├── ble_on + omi_device_connected  (physical device + physical Omi hardware)
  └── adb_access  (Android debug builds only — for locale manipulation)
```

### Platform setup
```bash
# Android: setup + build + launch
cd app && bash setup.sh android
# → completes: keystore, Firebase config, .dev.env, flutter run --flavor dev
# → sign in with Google when app launches, complete onboarding

# iOS: setup + build + launch
cd app && bash setup.sh ios
# → completes: Firebase config, .dev.env, flutter run --flavor dev
# → sign in with Google/Apple when app launches, complete onboarding
```

**Important:** Both platforms require completing the real sign-in and onboarding flows. Never bypass auth or onboarding — these are user-facing flows that must work correctly.

## YAML Flow Schema (v2)

Each flow file uses schema v2:
```yaml
version: 2
name: string          # Flow identifier
description: string   # What this flow covers
app: com.friend.ios.dev
evidence:
  video: true
covers: [string]      # Source files this flow exercises
preconditions: [string]  # Conditions required — see Prerequisites Reference above
steps: [Step]         # Ordered list of actions
```

Each step has these fields:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Step ID (S1, S2, ...) |
| `name` | yes | Short description |
| `do` | yes | Instructions for executing |
| `verify` | no | `true` = must be verified even during snapshot replay |
| `expect` | no | Assertions (text_visible, interactive_count) |
| `evidence` | no | Screenshot filename (`.webp` preferred) |
| `note` | no | Edge case notes |

Supported `expect` kinds:

| Kind | Fields | Example |
|------|--------|---------|
| `text_visible` | `values: [string]` | Verify specific text appears |
| `interactive_count` | `min: number` | Verify minimum interactive widgets |

## Navigation Graph (flow-walker verified)

Real navigation edges verified by flow-walker run11 on Pixel 7a (26 screens, 44 edges, depth 3). Screen names mapped from fingerprint IDs to semantic names.

```
Home (24 elements: 17 gesture, 3 icon, 4 inkwell)
├── [tab 0] Conversations (17 el: 1 FAB, 9 gesture, 3 icon, 4 inkwell)
│   ├── Conversation Detail (27 el: 18 gesture, 4 icon, 4 inkwell, 1 textformfield)
│   │   └── Notifications Settings (14 el: 10 gesture, 1 icon, 1 inkwell, 1 switch, 1 textbutton)
│   ├── Settings Drawer (13 el: 13 gesture)
│   │   ├── Language Settings (13 el: 10 gesture, 1 icon, 1 switch, 1 textbutton)
│   │   │   ├── Sub-detail (5 el: 4 gesture, 1 icon)
│   │   │   ├── Sub-settings (7 el: 1 elevated, 5 gesture, 1 icon)
│   │   │   │   ├── Settings Confirmation (3 el: 1 gesture, 2 textbutton)
│   │   │   │   └── Settings Form (16 el: 1 elevated, 9 gesture, 3 icon, 1 inkwell, 2 textfield)
│   │   │   └── Filter Sheet (13 el: 6 gesture, 5 inkwell, 2 textbutton)
│   │   └── Back → Home
│   ├── Sub-detail (2 el: gesture, icon)
│   ├── Sub-page (3 el: 2 gesture, 1 icon)
│   └── Back → Home
├── [tab 1] Action Items (17 el: 1 FAB, 9 gesture, 3 icon, 4 inkwell)
│   └── Notifications Settings (same as above)
├── [tab 2] Memories (25 el: 15 gesture, 4 icon, 5 inkwell, 1 textfield)
│   ├── Notifications Settings
│   ├── Memory Detail (9 el: 5 gesture, 2 icon, 2 inkwell)
│   ├── Category Page (7 el: 4 gesture, 3 inkwell)
│   └── Memory Search (18 el: 12 gesture, 4 icon, 1 inkwell, 1 textfield)
├── [tab 3] Apps (19 el: 2 elevated, 1 FAB, 9 gesture, 1 icon, 5 inkwell, 1 textfield)
│   ├── Notifications Settings
│   ├── Confirmation Dialog (4 el: 1 elevated, 1 gesture, 2 icon)
│   ├── Apps Sub-page (14 el: 3 elevated, 6 gesture, 1 icon, 4 inkwell)
│   ├── App Form (5 el: 1 elevated, 2 gesture, 1 icon, 1 textfield)
│   └── Back → Home
├── [Ask Omi] Chat (22 el: 19 gesture, 1 textbutton, 2 textfield)
│   ├── Delete Account (6 el: 1 checkbox, 4 gesture, 1 textfield)
│   └── Back → Home
├── [record] Capturing (19 el: 2 elevated, 1 FAB, 9 gesture, 1 icon, 5 inkwell, 1 textfield)
├── [settings] Settings Drawer (13 el: 13 gesture)
├── [gesture] Sign Up (5 el: 1 elevated, 1 gesture, 3 textfield)
├── [gesture] Confirmation (2 el: gesture, textbutton)
└── [gesture] Conversations Alt (17 el: 10 gesture, 2 icon, 4 inkwell, 1 textfield)
```

### Screen Fingerprint Mapping

For flow-walker compatibility — maps auto-generated fingerprint names to semantic flow names.

| Fingerprint ID | Element Count | Semantic Name | Flow File |
|----------------|---------------|---------------|-----------|
| `92a58e321064` | 24 | Home | home-navigation, tab-navigation |
| `113cc0d4f097` | 17 | Conversations (FAB) | conversations |
| `59c8c3dba1aa` | 17 | Conversations Alt | conversations |
| `2108e83364c2` | 19 | Apps | apps |
| `2b9f6e0d087b` | 25 | Memories | memories |
| `13f37b3018c5` | 22 | Chat | chat |
| `49f053d00b0f` | 27 | Conversation Detail | conversation-detail |
| `011f78c61152` | 14 | Notifications Settings | settings-notifications |
| `1b40a175a5fd` | 13 | Language Settings | language-change |
| `4b666d4ec8e3` | 13 | Settings Drawer | home-navigation |
| `0f852433acc6` | 6 | Delete Account | delete-account |
| `a74411638a9c` | 5 | Sign Up Form | onboarding |
| `0ba3aef7f00f` | 2 | Confirmation Dialog | — |
| `8407c23c9698` | 2 | Sub-detail | — |
| `9580b20fb6e0` | 3 | Sub-page | — |
| `dacfbda46c10` | 5 | Sub-detail (settings) | — |
| `e8ea54a72f46` | 7 | Sub-settings | — |
| `0766ec584fb4` | 13 | Filter Sheet | apps |
| `f94e0140ed7e` | 4 | Confirmation Dialog | — |
| `88992c72a759` | 14 | Apps Sub-page | app-detail |
| `f757010c13b3` | 5 | App Form | apps |
| `485a8ce57ebc` | 9 | Memory Detail | memories |
| `a6983264d893` | 7 | Category Page | memories |
| `4450e0d3044e` | 18 | Memory Search | memories |
| `35c0d8ed0daa` | 3 | Settings Confirmation | settings-profile |
| `a864d8b70edf` | 16 | Settings Form | settings-profile |

## Verified Flows (v2 flow-walker)

Only flows that have been executed, verified, and pushed through the v2 flow-walker pipeline are listed here. Each has a `.snapshot.json` for fast replay.

| Flow | Steps | Prerequisites | What it tests | Reports |
|------|-------|--------------|---------------|---------|
| `flows/login.yaml` | 5 | signed_out | Auth screen → Google Sign-In → consent → OAuth → home | [normal](https://flow-walker.beastoin.workers.dev/runs/hao5vbBsBI.html), [replay](https://flow-walker.beastoin.workers.dev/runs/-aeMGlV88w.html) |
| `flows/onboarding.yaml` | 9 | signed_out + auth | Name → Language → Found Omi → Permissions → Review → Speech → Knowledge → Complete → Home | [normal](https://flow-walker.beastoin.workers.dev/runs/UHqa8Fysj2.html), [replay](https://flow-walker.beastoin.workers.dev/runs/B9Py6uoJaO.html) |
| `flows/logout.yaml` | 5 | auth_ready | Home → Settings → Sign Out → Confirm → Auth screen | [normal](https://flow-walker.beastoin.workers.dev/runs/SH4MXH9gkv.html), [replay](https://flow-walker.beastoin.workers.dev/runs/NcZlCUW0W7.html) |

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
| Ref expired between commands | Use `press x y` with coordinates from last snapshot bounds, or `press @ref --adb` |
| System dialog blocking (location, permissions) | `agent-flutter dismiss` — detects and dismisses via ADB |
| "No isolate with Marionette" | ADB foreground + disconnect + reconnect |
| Snapshot returns 0 interactive elements | Marionette lost widget tree — `disconnect` then `connect` to re-attach |
| Bottom nav tabs not detected | `back` until nav bar appears, filter InkWell y > 780 |
| Hot restart breaks connection | Wait 3s → disconnect → connect |
| Text labels null | Match by `type`, `flutterType`, or `bounds` — Marionette doesn't extract child text |
| Non-English IME breaks text input | Set system locale to English: `adb shell "settings put system system_locales en-US"` |

## Guard Conditions

**NEVER:**
- Use development env vars to bypass auth — test with real auth flows
- Set `hasCompletedOnboarding` to skip onboarding — test the real flow
- Modify source code to make tests pass — report the failure instead
- Commit screenshots to git — use GCS upload for PR evidence
