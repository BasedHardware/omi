# Mobile QA checklists (app contributors)

Internal testing guidance for app contributors — moved out of the public docs
(docs.omi.me) because it churns with the app. Verify against the current code
before relying on it; the owning tests are the source of truth.

## Testing mobile voice enrollment

First-run speech-profile enrollment asks for a short sample about any topic.
Its progress uses approximately five seconds of user transcript spans; the
server still validates the uploaded WAV. Settings redo uses its existing
sentence target. Run the provider and onboarding widget regressions from `app/`:

```bash
flutter test test/providers/speech_profile_provider_test.dart test/widgets/speech_profile_onboarding_test.dart
```

For device verification, use the dev flavor and dev backend. Check speaking,
Skip, and upload failure on the actual onboarding step. Advancing through All
Done is a navigation event; verify the upload result separately.

## Fleet telemetry for app contributors

The backend accepts aggregated operational summaries at `POST /v1/telemetry/fleet`
with the app's Firebase ID token. Client integrations should follow the checked-in
[fleet schema](../../backend/telemetry/fleet_schema.json)
and [transport contract](../../backend/telemetry/README.md).
Aggregate locally, normally over 15 minutes, and coalesce background flushes within
the per-account budget. Use only registered events, outcomes and histogram edges;
do not include recording content, user/device identifiers, or free-text errors.

## Testing transcription settings and connectivity

From `app/`, run the hermetic connection, credential and retention regressions:

```bash
flutter test test/unit/connectivity_service_test.dart test/unit/stt_request_credentials_test.dart test/widgets/transcription_settings_recovery_test.dart test/services/capture/transcription_settings_retention_test.dart
```

These exercise network handovers and settings saves without a live provider.
Physical CV1 testing must separately verify Wi-Fi/cellular transcription and
Offline Sync. Preserve local recordings while investigating; do not clear app
data or reset a device to change transcription providers.
