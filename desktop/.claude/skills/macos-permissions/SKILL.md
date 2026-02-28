---
name: macos-permissions
description: "Debug macOS TCC permission issues (Accessibility, Screen Recording, Automation, Microphone, System Audio). Use when user reports permission problems, 'permission not working', 'can't grant permission', 'accessibility not granted', AXIsProcessTrusted issues, or TCC errors in logs."
allowed-tools: Bash, Read, Grep
---

# macOS TCC Permission Debugging

Debug Transparency, Consent, and Control (TCC) permission issues for the OMI Desktop app. The app requires multiple system permissions that are a frequent source of bugs.

## Permission Types Used by OMI Desktop

| Permission | API | TCC Service |
|-----------|-----|-------------|
| Accessibility | `AXIsProcessTrusted()` | kTCCServiceAccessibility |
| Screen Recording | ScreenCaptureKit | kTCCServiceScreenCapture |
| Microphone | AVCaptureDevice | kTCCServiceMicrophone |
| System Audio | ScreenCaptureKit (audio) | kTCCServiceScreenCapture |
| Automation | NSAppleScript/AppleEvents | kTCCServiceAppleEvents |

## Known Gotchas

1. **`AXIsProcessTrusted()` caches per-process on macOS 26 (Tahoe)**: When a user grants accessibility in System Settings, the running process keeps seeing `false`. Fix: restart the app, or use a polling approach with `AXIsProcessTrustedWithOptions`.
2. **App not appearing in System Settings**: The app must be code-signed with the correct identity. Debug builds vs release builds may have different identities.
3. **TCC database staleness**: `tccutil reset <service>` can help, but requires the bundle identifier.
4. **Screen Recording prompt**: Only triggered when actually capturing — not on permission request.
5. **Multiple permission prompts**: macOS may not show a prompt if one was recently dismissed.

## Diagnostic Commands

```bash
# Check TCC database (requires SIP partially disabled)
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service, client, auth_value FROM access WHERE client LIKE '%omi%'"

# Reset a specific permission
tccutil reset Accessibility com.omi.computer

# Check code signing identity
codesign -dvv /path/to/OMI.app

# Check if app is trusted (in Swift)
# AXIsProcessTrusted()
```

## Debugging Workflow

1. Check `/private/tmp/omi.log` for permission-related log entries.
2. Check Sentry for TCC-related errors (use the `sentry-release` skill).
3. Verify the bundle identifier matches what's in the TCC database.
4. Check if the issue is macOS version-specific (especially macOS 26 Tahoe).
5. Check code signing identity: `codesign -dvv /path/to/OMI.app`.
6. If permission was granted but not detected, advise user to restart the app (see gotcha #1).
7. If the app doesn't appear in System Settings, check code signing and bundle ID.
