# Omi Ambient Companion

Personal Android companion app for local-first ambient capture. The companion app owns Android permissions, foreground microphone capture, VAD, encrypted spool, accessibility/caption fallback, notification triggers, and sync to the Ambient Second Brain Controller plugin.

This is not an Omi plugin and does not modify the official Omi app. The plugin remains the controller/import bridge.

## What It Does

- Starts a visible microphone foreground service.
- Uses `AudioRecord` PCM16 mono 16 kHz.
- Runs lightweight RMS/VAD first with a RAM pre-roll buffer.
- Writes speech-triggered audio to encrypted app-private spool files.
- Uses AccessibilityService for foreground app and allowlisted caption/transcript fallback.
- Uses NotificationListenerService for meeting/call/Sound Notifications/Live Transcribe context triggers.
- Detects communication mode, mic silencing, low signal, network buffering, private mode, and storage limits.
- Registers with `plugins/ambient-second-brain-controller` and pins its policy key.
- Uploads telemetry, fallback segments, and decrypted length-prefixed PCM spools to the controller backend.
- The controller can forward companion PCM files into Omi's existing `/v1/sync-local-files` audio pipeline.
- Tracks capture sessions, storage status, and local delete pending/synced/all-audio controls.
- Runs best-effort Android on-device speech recognition over finalized spools on Android 13+ when supported by the device.
- Supports explicit, user-approved MediaProjection audio capture for apps/audio usages Android allows.
- Starts capture from context triggers such as meeting/call notifications, Live Transcribe/Sound Notifications, wired headset, Bluetooth audio, and SCO route changes.
- Shows a structured diagnostics snapshot in the app UI for field testing.

## Build

```powershell
Copy-Item app\android\local.properties companion\android\local.properties
app\android\gradlew.bat -p companion\android :app:assembleDebug --no-build-cache
```

APK:

```text
companion/android/app/build/outputs/apk/debug/omi-ambient-companion-debug-v0.1.0.apk
```

The standalone companion APK must identify as:

```text
package: com.omi.ambientcompanion
label: Omi Ambient Companion
```

It installs next to the official/published Omi app and does not replace or modify it.

## Personal Setup

1. Install the APK on the Pixel.
2. Open `Omi Ambient Companion`.
3. Enter the Ambient Second Brain Controller base URL and Omi user id.
4. Tap `Register`.
5. Tap `Permissions`, grant microphone and notifications.
6. Tap `Accessibility`, enable Omi Ambient Companion.
7. Tap `Notifications`, enable Omi Ambient Companion notification access.
8. Tap `Battery`, allow unrestricted/background operation.
9. Tap `Start`.

For the full field-test checklist, see `companion/TESTING.md`.

The app does not auto-record after reboot. Boot handling only resets stale recovery state.

## Safety

- Persistent notification is always visible while the mic service is running.
- Private Mode stops active capture/upload locally.
- The app does not use `VoiceInteractionService`, SoundTrigger HAL, hidden recording, arbitrary screen scraping, or silent media sessions.
- Call/meeting capture is degraded when Android blocks audio. Captions/transcripts are labeled as fallback sources.

## Known Limits

- Local STT uses Android's on-device recognizer when available. It is not a bundled Whisper/Vosk model and may be unavailable or limited by the system recognizer.
- MediaProjection captures only audio Android and the source app permit. It does not bypass protected meeting/call audio.
- Audio upload targets the plugin `/capture/audio-spool` endpoint. Final Omi conversation import depends on `OMI_API_BASE_URL` and `OMI_API_KEY`/`OMI_APP_SECRET` being configured for the controller deployment.
