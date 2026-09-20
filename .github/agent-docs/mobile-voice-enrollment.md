# Mobile guided voice introduction

First-run onboarding offers four optional sentence starters: identity/everyday
context, a current activity, an interest, and a goal. A user explicitly starts the phone
microphone, finishes a sentence, and presses Next. Alternative prompts, skipping,
pause/resume, and an exit remain available. Settings > Profile also opens this
flow without resetting the account. The existing Settings speech-profile redo
continues to use SpeechProfileProvider.

## Ownership and truthfulness

`SpeechProfileWidget` renders `GuidedVoiceController`. `DeviceGuidedVoiceIO` owns
microphone capture, transcription, enrollment, and explicit memory/goal submission.
The controller has a fakeable I/O boundary for state-transition tests.

- Prompt progress advances only after Next or Skip. The separate audio-level
  indicator measures PCM energy, not transcription or enrollment quality.
- Recording does not auto-finish after five seconds. Each answer pauses at 45
  seconds; backgrounding and recorder stalls pause capture and preserve drafts.
- iOS uses its available on-device recognizer for preview and final transcription.
  Other configurations use the existing transcription-only voice-message API.
  No conversation socket is created, so unconfirmed statements are not
  automatically ingested as conversation memories.
- Review shows only transcribed user statements, never the sentence starters.
  Users can edit and uncheck statements before choosing Save and finish.
  Confirmed statements use the existing private canonical memory create API;
  successful writes are retained on partial failure and excluded from retry.
- Voice-profile saving has its own server receipt. Failed uploads retain the
  same PCM for retry; a short sample asks for additional speech without clearing
  answers. Only confirmed upload success sets hasSpeakerProfile.
- Temporary audio files are task-owned, deleted after their request, and cleaned
  when the screen closes. Drafts survive pauses within the session, not process
  termination. The production app's existing identity/auth boundary remains.
- This local evaluation adds English source copy through the localization tool.
  Translation review is required before distributing the new copy broadly.

## Verification

From `app/`:

```sh
flutter test test/providers/guided_voice_controller_test.dart test/widgets/speech_profile_onboarding_test.dart test/providers/speech_profile_provider_test.dart
```

Tests cover prompt progress, no five-second cutoff, skipped content, transcription
and upload retries, independent memory writes, interruption, stale completion,
and layout with large text on a small phone. Physical-device acceptance still
requires real speech, enrollment, and memory save/readback against a dev backend.

## Guided introduction follow-up

Next finalizes the current answer and starts recording the next prompt without a
second tap. A pause or background event while transcription is pending suppresses
automatic microphone restart. Skipping before the first Start never opens the mic.
The fourth prompt is "Right now my number one goal is to ___." Review labels it as
My goal; it writes through `POST /v1/goals/canonical` with a stable Idempotency-Key
and the account generation. It never also creates a memory or fabricates a numeric
tracker. A submitted goal stays fixed across uncertain retries; edit it later from
Goals after a successful save. Skipped and unchecked goals are not written.

Voice enrollment requires a real `HOSTED_SPEAKER_EMBEDDING_API_URL` service and
speech-profile storage. Missing service configuration returns 503 even if local
iOS transcription works. A 503 now displays service unavailability separately from
recording/transcription errors. Local device QA must check the embedding service
and `GET /v3/speech-profile/status`; transcription success alone is insufficient.

## Finish and goal cleanup

Review has one Save and finish action. It saves the voice profile and every
checked answer, then advances automatically once all requested saves succeed.
Failures retain per-item receipts: a voice failure does not block answers, and
one failed answer does not block the others. Retry only sends unfinished writes.
The user may continue with saved items after a partial failure. Busy saves block
back navigation and duplicate taps. A short-sample recovery starts capture in
one tap and preserves earlier answers.

Mobile currently has local speech recognition but no integrated local text
rewriter. `goal_text_cleanup.dart` therefore performs deterministic offline
cleanup before review: anchored English prompt/filler removal, whitespace and
sentence punctuation cleanup, with outcome details and negation preserved.
The cleaned goal remains editable; Use original wording restores the transcript.
Unfinished prompt-only speech does not create a goal. There is no model download
or network request for cleanup.

Review cards are compact. The final recording action is Review answers. Scrolling
resets for each prompt and reveals save errors after a failed attempt; dragging
the review dismisses the keyboard. Tests include partial saves, duplicate taps,
cleanup meaning preservation, restore-original, and a small screen with large
text and the keyboard open.
