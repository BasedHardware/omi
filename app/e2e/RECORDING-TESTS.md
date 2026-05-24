# Recording & Transcription Behavior Test Skill

Comprehensive behavior tests for Omi's core recording, transcription, and conversation processing features. Every flow is designed for automated execution via `flow-walker` or manual execution via `agent-flutter`.

## Quick Start

```bash
# 1. Start emulator + app
sg kvm -c "$ANDROID_HOME/emulator/emulator -avd omi-dev -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim &"
cd app && flutter run -d emulator-5554 --flavor dev > /tmp/omi-flutter.log 2>&1 &

# 2. Connect agent-flutter
AGENT_FLUTTER_LOG=/tmp/omi-flutter.log agent-flutter connect

# 3. Run a specific flow
flow-walker run app/e2e/flows/phone-capture.yaml

# 4. Run all recording flows
flow-walker run app/e2e/flows/phone-capture.yaml \
  app/e2e/flows/recording-controls.yaml \
  app/e2e/flows/conversation-processing.yaml \
  app/e2e/flows/conversation-detail.yaml
```

## Flow Inventory

### Core Recording Flows (must-pass for every release)

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `phone-capture.yaml` | 9 | auth, mic, no device | Phone mic record → live transcript → process → conversation created | Emulator |
| `device-capture.yaml` | 10 | auth, BLE device | Omi device auto-record → live transcript → mute/unmute → process | Physical device |
| `recording-controls.yaml` | 9 | auth, mic, no device | Mute/unmute toggle, summary tab, process now confirmation dialog | Emulator |
| `conversation-processing.yaml` | 9 | auth, mic | Full lifecycle: record → processing skeleton → summary + action items | Emulator |

### Conversation Review Flows

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `conversation-detail.yaml` | 9 | auth, has conversations | Transcript/summary/action items tabs, search, star, share, menu actions | Emulator |
| `conversation-capturing.yaml` | 6 | auth, mic | Basic capturing page layout (v1 format, legacy) | Emulator |

### Voice & Speaker Flows

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `speech-profile.yaml` | 8 | auth, mic | Voice training: questions, skip, complete, upload profile | Emulator |
| `speaker-identification.yaml` | 9 | auth, has conversations | Add people, name speakers in transcript, bulk assignment | Emulator |

### Settings Flows

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `transcription-settings.yaml` | 9 | auth | Language picker, auto-translate toggle, custom STT provider config | Emulator |
| `custom-vocabulary.yaml` | 7 | auth | Add/delete vocabulary words, chip display, API sync | Emulator |

### Resilience Flows

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `wal-offline-recovery.yaml` | 8 | auth, mic | WAL indicator, airplane mode, offline recording, reconnect, WAL sync | Emulator |
| `freemium-threshold.yaml` | 4 | auth, mic, free tier | Usage limit warning, WebSocket close 4002, on-device STT prompt | Emulator |

### Device-Specific Flows

| Flow | Steps | Prerequisites | What it tests | Hardware |
|------|-------|--------------|---------------|----------|
| `device-photo-capture.yaml` | 7 | auth, BLE device w/ camera | Photo capture, timeline mixing, photo viewer, photos in summary | Physical device |

## Coverage Map

Maps each flow to the source files it exercises. Use this to determine which flows to run when modifying a file.

```
providers/capture_provider.dart
  ├── phone-capture.yaml (recording start/stop, WebSocket lifecycle)
  ├── device-capture.yaml (BLE audio streaming, pause/resume)
  ├── recording-controls.yaml (mute/unmute, process now)
  ├── conversation-processing.yaml (processing lifecycle)
  ├── wal-offline-recovery.yaml (WAL management, keep-alive)
  ├── freemium-threshold.yaml (freemium state handling)
  └── device-photo-capture.yaml (photo streaming)

pages/conversation_capturing/page.dart
  ├── phone-capture.yaml
  ├── device-capture.yaml
  ├── recording-controls.yaml
  ├── conversation-processing.yaml
  ├── wal-offline-recovery.yaml
  └── device-photo-capture.yaml

pages/conversation_detail/page.dart
  ├── conversation-detail.yaml
  └── conversation-processing.yaml

services/wals/*
  └── wal-offline-recovery.yaml

services/sockets/transcription_service.dart
  ├── phone-capture.yaml
  ├── device-capture.yaml
  └── speech-profile.yaml

providers/speech_profile_provider.dart
  └── speech-profile.yaml

pages/speech_profile/page.dart
  └── speech-profile.yaml

pages/settings/transcription_settings_page.dart
  └── transcription-settings.yaml

pages/settings/language_settings_page.dart
  └── transcription-settings.yaml

pages/settings/custom_vocabulary_page.dart
  └── custom-vocabulary.yaml

pages/settings/people.dart
  └── speaker-identification.yaml

services/freemium_transcription_service.dart
  └── freemium-threshold.yaml

pages/conversations/widgets/processing_capture.dart
  ├── conversation-processing.yaml
  ├── phone-capture.yaml
  └── device-capture.yaml
```

## State Machine Reference

### RecordingState Transitions
```
                    ┌─────────────────┐
                    │   initialising  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌────────┐   ┌────────────┐  ┌──────────────────┐
         │ record │   │deviceRecord│  │systemAudioRecord │
         │(phone) │   │  (BLE)     │  │  (phone calls)   │
         └───┬────┘   └──┬───┬────┘  └──────────────────┘
             │           │   │
             │           │   ▼
             │           │ ┌───────┐
             │           │ │ pause │ (device mute)
             │           │ └───┬───┘
             │           │     │ (unmute)
             │           ◄─────┘
             │           │
             ▼           ▼
         ┌────────────────────┐
         │       stop         │
         └────────┬───────────┘
                  │
                  ▼
         ┌────────────────────┐
         │    processing      │
         └────────┬───────────┘
                  │
                  ▼
         ┌────────────────────┐
         │    completed       │
         └────────────────────┘
```

### WebSocket Lifecycle
```
disconnected ──► connected ──► receiving segments
     ▲                              │
     │         onClosed/onError     │
     └──────────────────────────────┘
              keep-alive (15s)
              auto-reconnect
```

### Conversation Processing Pipeline
```
Audio Recording
  │
  ├──► WAL Frames (local storage)
  │
  ├──► WebSocket (real-time transcription)
  │         │
  │         ├── TranscriptSegmentEvent (segments)
  │         ├── SpeakerLabelSuggestionEvent (speaker hints)
  │         ├── TranslationEvent (auto-translate)
  │         ├── PhotoProcessingEvent (photo status)
  │         ├── PhotoDescribedEvent (photo descriptions)
  │         └── FreemiumThresholdReachedEvent (usage limit)
  │
  └──► Process Now (manual) or Silence Timeout (auto)
            │
            ├── ConversationProcessingStartedEvent
            │     (processing skeleton in list)
            │
            ├── WAL sync (upload offline audio)
            │
            └── ConversationEvent
                  (completed conversation with summary)
```

## Prerequisites Reference

| Prerequisite | Description | Setup |
|-------------|-------------|-------|
| `auth_ready` | Signed in, onboarding complete | Complete Google Sign-In + onboarding flow |
| `microphone_permission` | Mic permission granted | `adb shell pm grant com.friend.ios.dev android.permission.RECORD_AUDIO` |
| `no_omi_device` | No BLE device connected | Disconnect device in settings, or use emulator |
| `omi_device_connected` | Omi BLE device paired | Physical device only, power on Omi in BLE range |
| `has_conversations` | At least 1 conversation exists | Run phone-capture or device-capture flow first |
| `free_tier_account` | User on free plan | Use account without premium subscription |

## Suggested Test Sequences

### Minimum Viable Test (emulator, ~10 min)
```
1. phone-capture.yaml          — core recording path
2. recording-controls.yaml     — mute/unmute and process now
3. conversation-detail.yaml    — review recorded conversation
```

### Full Emulator Suite (~30 min)
```
1. phone-capture.yaml          — phone mic recording
2. recording-controls.yaml     — all controls
3. conversation-processing.yaml — full processing lifecycle
4. conversation-detail.yaml    — conversation review
5. speech-profile.yaml         — voice training
6. speaker-identification.yaml — people + speaker naming
7. transcription-settings.yaml — language + custom STT
8. custom-vocabulary.yaml      — vocabulary management
9. wal-offline-recovery.yaml   — offline resilience
```

### Full Device Suite (physical Omi, ~30 min)
```
1. device-capture.yaml         — BLE device recording
2. recording-controls.yaml     — mute/unmute device
3. device-photo-capture.yaml   — camera + transcript timeline
4. conversation-detail.yaml    — review device conversation
5. speaker-identification.yaml — speaker naming
```

### Pre-Release Regression (~45 min)
Run both emulator and device suites. Add:
```
10. freemium-threshold.yaml    — usage limit (needs free-tier account)
```

## Evidence Collection

```bash
# Screenshots during flow execution
agent-flutter screenshot /tmp/step-S1.webp

# PR evidence with GCS upload
beast omi dev evidence emulator --pr <NUM> --upload

# Video compilation from step screenshots
ffmpeg -framerate 1 -pattern_type glob -i '/tmp/step-*.webp' \
  -vf "scale=540:1200:force_original_aspect_ratio=decrease,pad=540:1200:-1:-1" \
  -c:v libx264 -pix_fmt yuv420p /tmp/recording-test-report.mp4
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Mic button not visible | BLE device is connected — disconnect or use device-capture flow |
| No transcripts appear | Check WebSocket connection — network/firewall may block wss:// |
| WAL indicator missing | Speak first — indicator only shows when segments/photos exist |
| Processing skeleton stays forever | Backend may be down — check API connectivity |
| Speech profile errors | Speak louder/clearer, avoid multiple speakers, check mic permission |
| Custom STT validation fails | Verify API key, check URL format (wss:// for live, https:// for batch) |
| Airplane mode no effect | Emulator networking may not fully disconnect — try `adb shell svc wifi disable && adb shell svc data disable` |
