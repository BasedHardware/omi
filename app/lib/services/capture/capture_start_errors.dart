/// The phone recording did not start because the microphone permission is denied. The record
/// button says so and offers Open Settings instead of a generic error (ux-contract §15, §17.8).
/// It stays a [StateError] so callers that catch the refused start keep working.
class MicPermissionDenied extends StateError {
  MicPermissionDenied() : super('phone recording start refused: microphone permission denied');
}
