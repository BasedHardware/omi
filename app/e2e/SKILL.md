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
    ├── Phone Calls (phone_calls_page.dart)
    ├── Developer Settings (developer.dart)
    │   ├── Custom STT provider config
    │   ├── API key management
    │   └── MCP API keys
    ├── What's New → Changelog sheet
    ├── Referral Program (referral_page.dart) — NEW
    ├── About (about.dart)
    │   └── Privacy Policy, Website, Discord, Help
    └── Sign Out → Confirmation dialog
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

| Flow | What it describes |
|------|-------------------|
| **Core Navigation** | |
| `flows/tab-navigation.yaml` | Bottom nav: switching between 4 tabs, scroll, return home |
| `flows/home-navigation.yaml` | Home → Settings → scroll → back |
| `flows/search.yaml` | Search icon → query → results → clear |
| `flows/onboarding.yaml` | Full 11-step onboarding: auth → name → language → permissions → complete |
| **Main Tabs** | |
| `flows/conversations.yaml` | Conversations list, folder tabs, starred filter, daily score, detail view |
| `flows/action-items.yaml` | Task creation, categories, checkbox toggle, goal linking |
| `flows/memories.yaml` | Memory search, graph view, category filter, add/edit memory |
| `flows/apps.yaml` | App explore, search, categories, detail view, create custom app |
| `flows/chat.yaml` | Ask Omi → text/voice input → AI response |
| `flows/record-conversation.yaml` | Phone mic capture → live transcript → stop |
| **Settings** | |
| `flows/settings-profile.yaml` | Profile: name, language, vocabulary, speech profile, privacy |
| `flows/settings-notifications.yaml` | Frequency slider, daily summary toggle, time picker |
| `flows/settings-developer.yaml` | STT provider, API keys, MCP keys |
| `flows/settings-integrations.yaml` | Google Calendar, Gmail, Apple Health connect/disconnect |
| `flows/settings-device.yaml` | Device info, LED brightness, mic gain, double tap (requires BLE) |
| `flows/settings-sync.yaml` | Offline sync, local storage, recordings, fast transfer |
| `flows/settings-plan-usage.yaml` | Current plan, usage stats, upgrade options |
| `flows/settings-about.yaml` | About page, external links |
| `flows/settings-toggle.yaml` | Developer Settings switch toggle (legacy) |
| `flows/language-change.yaml` | Profile → Language → picker → locale swap via shared_prefs |

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
