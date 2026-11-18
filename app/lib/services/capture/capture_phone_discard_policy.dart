part of 'capture_coordinator.dart';

/// Undo on Home's recording bar: end the phone's live recording and keep nothing of it. Ownership
/// moves exactly as for a user stop (a pendant the phone took over from resumes, the capture policy
/// returns to its value at start); only the teardown differs ([DiscardPhoneLiveStage]). Ignored
/// unless the phone owns a live (not Transcribe Later) recording.
class PhoneDiscardRequested extends CaptureEvent {
  const PhoneDiscardRequested();
}

/// Live phone teardown that keeps nothing: the buffered tail is not flushed, and the recording's
/// WAL audio and in-memory transcript are dropped ([PhoneDiscardRequested]).
class DiscardPhoneLiveStage extends CaptureStage {
  const DiscardPhoneLiveStage();
}

/// A discard is a user stop whose live teardown keeps nothing. Batch recordings (Transcribe Later)
/// and captures the phone does not own are left alone.
CaptureTransition _reducePhoneDiscard(CaptureCoordinatorState state) {
  final live = state.phase == CapturePhase.phoneLive ||
      state.phase == CapturePhase.phonePaused ||
      state.phase == CapturePhase.audioInterrupted;
  if (!live) return CaptureTransition(state, const []);
  final stop = _reducePhoneStop(state, const PhoneStopRequested(reason: 'user_discarded', userStop: true));
  return CaptureTransition(stop.state, [
    for (final effect in stop.effects)
      if (effect is RunStage && effect.stage is StopPhoneLiveStage) const RunStage(DiscardPhoneLiveStage()) else effect,
  ]);
}
