# Mobile own-voice enrollment

First-run onboarding keeps an explicit opportunity to teach Omi the user's own
voice. This does not govern tagging other people or desktop VoiceDemo.

## Product approach

- Explain the benefit and effort together: Omi needs to know which voice is
  yours; speak about anything for about five seconds. Do not require location,
  work, or goal answers to obtain a voiceprint.
- Keep enrollment in first run. Give speaking the visual priority and retain a
  legible, accessible Skip escape on entry, recording, and failure.
- Show progress from the sample rather than questionnaire completion. Today,
  onboarding uses the union of non-empty user transcript spans toward five
  seconds, excluding Omi prompts, gaps between segments, and overlaps. This is
  an STT estimate, not a voice-activity or speaker-purity measurement. Keep the
  existing pause/grace, recording cap, and backend five-second WAV floor.
- Keep success tied to the upload response. All Done/continued and skipped are
  navigation outcomes, not enrollment receipts. Never mark failed uploads as
  completed; local WAV creation failures must restore the error/escape path.
- Evaluate shipped cohorts, separated by OS and build: recording start,
  sufficient sample, upload success/failure, skip, and later identification
  quality. Confirm actual store/TestFlight distribution before attributing a
  funnel change to a merged PR. No conversion gain is claimed from this change.
- Longer term, use measured voiced audio and a server-authoritative enrollment
  receipt to separate capture quality from STT availability. Improve the sample
  progressively only with attributable user audio and measured identification
  quality; do not silently enroll another speaker or weaken quality thresholds.
- Offer recovery through Settings and consider a contextual reminder after a
  useful conversation. Avoid a recurring onboarding gate; validate reminder
  timing and longer samples against conversion and downstream recognition.

## Current boundary and verification

`SpeechProfileProvider.initialise(isOnboardingFlow: true)` selects duration
progress for first run; Settings redo retains its existing three-sentence target.
The backend question protocol is unchanged, but its topics and completion event
are not prerequisites for first-run enrollment. A transcript can still lag or
fail: this change does not turn a wall-clock countdown into proof of speech.

Run from `app/`:

```sh
flutter test test/providers/speech_profile_provider_test.dart test/widgets/speech_profile_onboarding_test.dart
```

These tests execute provider completion/error behavior and the real enrollment
widget with hardware/bootstrap boundaries faked. Live microphone, upload, and
identification quality still need a mobile dev device and dev backend.

## Follow-up observations from the path review

The existing availability/initialization work can outlive navigation; the
provider's final upload also lacks a session-generation check. Reconnection can
restart transcript timestamps. These deserve lifecycle/transport fault tests
before further changes to asynchronous ownership. Error dialogs currently offer
Skip but do not consistently offer an actual re-record action. The current change fixes
only the reproduced local WAV failure and the first-run sample/instruction
contract, leaving broader lifecycle and retry UX changes for separate work.
