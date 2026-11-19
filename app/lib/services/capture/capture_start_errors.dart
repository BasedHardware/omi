/// The phone recording did not start because the microphone permission is denied. The record
/// button says so and offers Open Settings instead of a generic error (ux-contract §15, §17.8).
class MicPermissionDenied implements Exception {
  const MicPermissionDenied();
}
