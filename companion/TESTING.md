# Omi Ambient Companion Test Guide

This guide is for personal Pixel testing of the standalone `Omi Ambient Companion` app.

## Build Or Download

Local debug APK:

```powershell
Copy-Item app\android\local.properties companion\android\local.properties
app\android\gradlew.bat -p companion\android :app:assembleDebug --no-build-cache
```

APK path:

```text
companion/android/app/build/outputs/apk/debug/omi-ambient-companion-debug-v0.1.0.apk
```

GitHub Actions also uploads the debug APK from the `Ambient Companion Android` workflow. Download the artifact named
`omi-ambient-companion-standalone-debug-apk`, not the regular Omi app APK.

Before installing, verify the standalone identity:

```powershell
& C:\Android\Sdk\build-tools\36.0.0\aapt.exe dump badging companion\android\app\build\outputs\apk\debug\omi-ambient-companion-debug-v0.1.0.apk | findstr "package application-label"
```

Expected:

```text
package: name='com.omi.ambientcompanion'
application-label:'Omi Ambient Companion'
```

## Controller Setup

The companion expects the `Ambient Second Brain Controller` plugin backend to be reachable from the phone.

Local controller:

```powershell
cd plugins\ambient-second-brain-controller
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn python-dotenv requests cryptography pytest
Copy-Item .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000
```

Expose it to the phone with your preferred tunnel. Set `WEBHOOK_BASE_URL` in the controller environment to the same public base URL.

For Omi import, also set:

```text
OMI_API_BASE_URL=<your Omi API base URL>
OMI_API_KEY=<developer/Omi token if available>
```

Without those, the controller still stores audio/fallback segments locally, but it cannot forward audio into Omi conversations.

## First Install

1. Install `app-debug.apk`.
2. Open `Omi Ambient Companion`.
3. Enter the public controller base URL.
4. Enter your Omi user id.
5. Tap `Register`.
6. Tap `Permissions` and grant microphone, notifications, and Bluetooth route permission if prompted.
7. Tap `Accessibility` and enable `Omi Ambient Companion`.
8. Tap `Notifications` and enable notification listener access for `Omi Ambient Companion`.
9. Tap `Battery` and allow unrestricted or exempt background operation.
10. Return to the app and tap `Refresh Preflight`.

The `Preflight` section should show `OK` for plugin URL, user id, device token, pinned key, microphone, notifications, accessibility, notification listener, and battery.

## Smoke Tests

### Manual Mic Capture

1. Tap `Start`.
2. Confirm a persistent `Omi Ambient Companion` microphone notification appears.
3. Speak for 30-60 seconds.
4. Stop speaking and wait for the silence timeout.
5. Tap `Refresh Diagnostics`.
6. Confirm storage pending count or audit entries show a spool session and upload/local STT attempts.

### Offline Buffering

1. Tap `Start`.
2. Disable network.
3. Speak for 1-2 minutes.
4. Re-enable network.
5. Tap `Sync`.
6. Confirm audit log shows `spool_audio_uploaded` or sync backoff if the controller is unreachable.

### Accessibility Caption Fallback

1. Enable Live Transcribe or open a meeting app with captions.
2. Confirm the notification/accessibility triggers show in the audit log.
3. Confirm fallback entries use `accessibility_caption` or `live_caption`.

### Communication Awareness

1. Start a phone call or meeting call.
2. Confirm diagnostics show communication/degraded mode rather than normal audio confidence.
3. Confirm the app does not claim protected call recording.

### Screen Audio

1. Tap `Screen Audio`.
2. Approve Android's screen/audio capture prompt.
3. Play permitted media or a meeting source that allows playback capture.
4. Tap `Stop Screen Audio`.
5. Confirm a spool session is created.

## What To Send Back When Something Fails

Please send:

- Phone model and Android version.
- Whether the APK installed cleanly.
- The controller base URL shape you used, without secrets.
- A screenshot or copied text from `Preflight`.
- The text from `Share Diagnostics`.
- The last 30-50 audit log lines.
- Whether the persistent mic notification was visible.
- Whether Omi conversations appeared, or only controller/plugin storage updated.

Useful optional adb commands:

```powershell
adb shell dumpsys package com.omi.ambientcompanion | findstr granted
adb shell dumpsys notification --noredact | findstr ambientcompanion
adb logcat -d -s OmiAmbient AndroidRuntime ActivityTaskManager
```

## Expected Limitations

- Local STT depends on Android's on-device recognizer and may not accept injected PCM on every build.
- MediaProjection captures only audio Android and the source app allow.
- Accessibility fallback is restricted to allowlisted meeting/caption surfaces.
- The app never auto-starts recording after reboot.
