# local-calls

Incoming call detection and answering, for the RN app. Android only.

## What it can see, precisely

| | needs | this module |
|---|---|---|
| Outbound VoIP call state (omi's own calls) | nothing | not this — the Flutter `PhoneCallsPlugin` already covers it via `TelecomManager` |
| Incoming **cellular** call ringing | `READ_PHONE_STATE` | yes, via `TelephonyCallback.CallStateListener` |
| Answer / hang up | `ANSWER_PHONE_CALLS` | yes, via `TelecomManager` |
| **Who** is calling | `READ_CALL_LOG` | **no** — deliberately not requested |

The caller is always `null`. Identifying a caller needs `READ_CALL_LOG`, which grants
the entire call history; that is a product decision, not a technical one, so it is
not taken here.

`PhoneStateListener` is deprecated and does not deliver an incoming ring on API 31+.
The module uses `TelephonyCallback` there and keeps `PhoneStateListener` only for
the pre-31 branch, which is why the file carries a file-level deprecation
suppression with that rationale.

## Setup

`expo prebuild` first — this project is on the managed workflow, so no `android/`
directory exists until then. Then add to `app.json`:

```json
{
  "expo": {
    "android": {
      "permissions": [
        "android.permission.RECORD_AUDIO",
        "android.permission.READ_PHONE_STATE",
        "android.permission.ANSWER_PHONE_CALLS"
      ]
    }
  }
}
```

`READ_PHONE_STATE` and `ANSWER_PHONE_CALLS` are runtime permissions; the manifest
declaration is required and `requestCallPermissions()` triggers the prompt.

## What answering does not enable

Playing audio into an active carrier call is not possible from a third-party app.
The call takes exclusive audio and Android exposes no API for adding a stream.
Voice on a call is only reachable on a call path this app controls (omi's own
Twilio calls), not on a carrier call.

## Files

| | |
|---|---|
| `android/.../CallStateDetector.kt` | all logic; no Expo or React types, compiles standalone |
| `android/.../LocalCallsModule.kt` | thin Expo adapter |
| `index.ts` | `startCallDetection`, `answerCall`, `hangUp`, permission helpers |

## Verification

`CallStateDetector.kt` compiles clean against `android.jar` (API 35) with zero
diagnostics. `LocalCallsModule.kt` is **not compile-verified** — it needs
`expo-modules-core`, which does not exist without a Gradle build. Nothing here has
run on a device.
