# Pendant tutorial question lifecycle

The question step uses the existing pipeline:

`admitted button → CaptureController → CaptureExternalActions → MessageProvider → VoiceQuestionResult → owning DeviceOnboardingProvider → SinglePressStep`

The main chat list is a presentation projection, not question-completion authority. Pendant replies belong to main Omi chat even when a persona, past or fresh chat is selected. The tutorial displays its own returned question and answer without appending them to the wrong chat. Unrelated messages cannot complete the step.

Capture owns Listening and Processing transitions. A raw press ignored by the auto-submit grace or while awaiting a reply does not toggle tutorial state. Manual submission and the existing 15-second auto-submit follow the same completion path. Completion is scoped to the provider instance and question attempt, and invalidated on step changes, exit and restart. Codec acquisition is bounded to ten seconds; audio save and the entire response stream each have the existing configurable 60-second voice-reply budget. Think/data heartbeats do not extend the stream deadline. No-speech completion never waits for its best-effort Bluetooth failure vibration. Failure returns to the pendant press prompt with localized no-speech, limit or connection guidance. No recording or preference reset is involved; this is client-side handling of the existing voice endpoint.

## Implementation and acceptance checklist

- [x] Typed success/failure returned by MessageProvider and the production adapter.
- [x] Tutorial receives only its attempt's result; SinglePressStep observes tutorial state directly.
- [x] Capture reports empty frames, missing device and codec failures, and handles send exceptions.
- [x] Busy, quota, file-save, no-speech, network, timeout and incomplete streams terminalize the request.
- [x] Press admission and overlapping request guards preserve capture state.
- [ ] Record exact-head unit/widget, simulator, analyzer, journey and preflight results in the PR.
- [ ] Post-release customer/pendant check: first-step transcription, press/speak/press, visible answer/Continue, auto-submit, disconnect/reconnect and retry, tutorial exit and ordinary recording afterward.
- [ ] Merge, signed mobile release and customer retest; no backend deployment required by this change.

Reproducible software scenarios: `flutter test test/widgets/pendant_tutorial_question_flow_test.dart`; running iOS scenarios: `flutter test --flavor dev -d <simulator-id> integration_test/pendant_tutorial_question_test.dart`. The latter supplies synthetic BLE/audio/codec and response I/O, not a physical pendant or production backend. This changes application outcome/admission state, not native BLE delivery, microphone custody or firmware. Simulator/local integration plus required CI are the pre-merge gates for that boundary. Keep the PR draft until those gates pass; a real pendant/customer retest separately establishes Andrea's specific outcome.
