# Omi Functional Test Suite (Maestro E2E)

Automated functional tests for the Omi Flutter mobile app using [Maestro](https://maestro.mobile.dev/).

## Prerequisites

1. **Install Maestro CLI:**
   ```bash
   # macOS
   brew install maestro

   # Linux
   curl -Ls "https://get.maestro.mobile.dev" | bash
   ```

2. **Install the Omi app** on your device/emulator (dev flavor):
   ```bash
   cd app && flutter build apk --flavor dev
   adb install build/app/outputs/flutter-apk/app-dev-release.apk
   ```

3. **For device-required tests:** Power on Omi hardware and keep it within BLE range.

## Quick Start

```bash
# Run core tests (simulator-safe)
bash app/.maestro/scripts/run_all.sh --tags core

# Run all tests (including device-required)
bash app/.maestro/scripts/run_all.sh --tags all

# Target a specific device
bash app/.maestro/scripts/run_all.sh --device-id emulator-5554 --tags core

# Custom output directory
bash app/.maestro/scripts/run_all.sh --output ./my-reports --tags core
```

## Test Flows

| # | Flow | Tags | Description |
|---|------|------|-------------|
| 01 | Login | `core`, `auth` | Sign in with Google through consent flow |
| 02 | Onboarding | `core`, `onboarding` | First-time user setup: name, permissions, device skip |
| 03 | Conversations | `core`, `conversations` | List, detail, tabs (Summary/Transcript/Action Items), folder filter |
| 04 | Memories | `core`, `memories` | View, create, edit, delete memories |
| 05 | Chat | `core`, `chat` | Send message, receive AI response |
| 06 | Apps/Plugins | `core`, `apps` | Browse marketplace, view app detail |
| 07 | Settings | `core`, `settings` | Navigate settings pages |
| 08 | Device Connection | `device_required`, `connection` | BLE scan and pair Omi hardware |
| 09 | Recording | `device_required`, `recording` | Start recording, verify transcription |
| 10 | Logout | `core`, `auth` | Sign out and verify auth screen |

## Tag System

- **`core`** — Runs on simulator/emulator, no physical Omi device needed
- **`device_required`** — Requires physical Omi hardware nearby
- **`auth`** — Authentication flows (login/logout)
- **`conversations`** — Conversation CRUD operations
- **`memories`** — Memory management
- **`chat`** — Chat interactions
- **`apps`** — App/plugin marketplace
- **`settings`** — Settings navigation
- **`connection`** — Device BLE pairing
- **`recording`** — Audio capture and transcription

## Reports

After a run, find the report at `.maestro/reports/report.md` with:
- Summary table (total/passed/failed/skipped)
- Per-flow duration and status
- Console output for debugging failures
- Screenshots in each flow's output directory

## Typical Workflow

```bash
# 1. Turn on Omi device, keep near phone
# 2. Connect phone via USB, verify: adb devices
# 3. Run the full suite:
bash app/.maestro/scripts/run_all.sh --tags all

# 4. After ~1 hour, check the report:
cat app/.maestro/reports/report.md
```

## Adding New Flows

1. Create `app/.maestro/flows/NN_flow_name.yaml`
2. Add appropriate `tags:` section
3. Follow existing flow patterns for consistency
4. Run `bash app/.maestro/scripts/run_all.sh --tags your_tag` to test
