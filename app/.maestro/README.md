# Omi Maestro E2E Tests

Automated functional tests for the Omi Flutter mobile app using [Maestro](https://maestro.dev/).

## Quick Start

```bash
# 1. Install Maestro
curl -Ls "https://get.maestro.mobile.dev" | bash

# 2. Start your emulator or connect a device
adb devices  # Android
# or
xcrun simctl list | grep Booted  # iOS

# 3. Build and install the dev app
cd app && flutter build apk --flavor dev
adb install build/app/outputs/flutter-apk/app-dev-release.apk

# 4. Run all tests
cd app/.maestro && bash scripts/run_all.sh

# 5. Or run a single flow
maestro test flows/01_login.yaml
```

## What's Tested

| Flow | Description | Tags |
|------|-------------|------|
| 01_login | Sign-in screen, Google/Apple auth | smoke, auth |
| 02_onboarding | First-time user onboarding journey | smoke, onboarding |
| 03_conversations | Conversation list, viewing details | core, conversations |
| 04_memories | Creating, viewing, deleting memories | core, memories |
| 05_chat | Sending messages, receiving responses | core, chat |
| 06_apps_marketplace | Browsing plugins and integrations | core, apps |
| 07_settings | Profile, privacy, notifications | core, settings |
| 08_recording | Recording UI, phone mic fallback | device, recording |
| 09_logout | Sign-out flow | smoke, auth |
| 10_action_items | Action items from conversations | core, conversations |

## Running Specific Suites

```bash
# Only smoke tests (fast, no auth required)
bash scripts/run_all.sh --tags smoke

# Core tests (requires authentication)
bash scripts/run_all.sh --tags core

# Device-dependent tests (requires Omi hardware)
bash scripts/run_all.sh --tags device

# With HTML report
bash scripts/run_all.sh --report
```

## Test Suites

- **smoke** — Basic app launch, login/logout screens. Fast, CI-friendly.
- **core** — Full functional tests requiring authentication. Tests conversations, memories, chat, apps, settings.
- **device** — Tests requiring physical Omi hardware (recording, BLE). Run manually.

## Writing New Flows

Create a new YAML file in `flows/`:

```yaml
# Flow: Description of what this tests
# Tags: comma, separated, tags
# Prerequisites: What state the app needs to be in

appId: com.friend.ios.dev
tags:
  - core
  - your_tag

---
# Use shared setup
- runFlow: ../shared/launch_app.yaml

# Your test steps
- tapOn: "Button Text"
- assertVisible: "Expected Text"
- takeScreenshot: "evidence_name"
```

### Tips

- Use `extendedWaitUntil` for network-dependent steps (generous timeouts)
- Use `runFlow` with `when` for conditional steps (handling permission dialogs)
- Use `anyOf` for elements that might have different text across versions
- Take screenshots at key points for debugging failures
- Use `scrollUntilVisible` for off-screen elements

## CI Integration

See `.github/workflows/maestro-tests.yml` for automated testing on push.
The CI workflow:
1. Builds the Flutter app in dev flavor
2. Starts an Android emulator
3. Installs the app
4. Runs smoke + core test suites
5. Uploads screenshots as artifacts

## Environment Variables

Override in `config.yaml` or pass at runtime:

```bash
maestro test flows/05_chat.yaml --env TEST_CHAT_QUESTION="Tell me about AI"
```

| Variable | Default | Used By |
|----------|---------|---------|
| TEST_USER_NAME | "Test User" | 02_onboarding |
| TEST_MEMORY_TITLE | "Maestro Test Memory" | 04_memories |
| TEST_CHAT_QUESTION | "What did I talk about today?" | 05_chat |
| PLATFORM | "android" | scripts/run_all.sh |

## Troubleshooting

**"No devices found"** — Ensure emulator is running (`adb devices`) or simulator is booted.

**Tests fail on fresh install** — Some flows require authentication. Run `01_login` + `02_onboarding` first, or use a pre-authenticated APK.

**Timeouts on CI** — Increase `timeout` values in flow YAML. Emulators are slower than real devices.

**Permission dialogs** — On first run, Android shows permission popups. The flows handle common ones, but you may need to grant permissions manually once.
