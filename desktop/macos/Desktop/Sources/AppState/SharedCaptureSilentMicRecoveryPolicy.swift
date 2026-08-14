/// Terminal policy for the shared microphone capture path used by listening,
/// manual recording, and Quick Note. `AudioCaptureService` is deliberately
/// recreated during recovery, so the cross-rebuild cap belongs here.
enum SharedCaptureSilentMicRecoveryPolicy {
  enum Action: Equatable {
    case rebuild
    case stopAndSurfaceError
  }

  static let maximumRecoveryAttempts = 3

  /// Shared capture must treat a zero-sample CoreAudio stream as a failure for
  /// every input transport, not only Bluetooth. This configuration is intentionally
  /// testable without a physical audio route.
  static func configure(_ capture: AudioCaptureService) {
    capture.detectSilentMicOnAnyTransport = true
  }

  static func action(for recoveryAttempt: Int) -> Action {
    recoveryAttempt >= maximumRecoveryAttempts ? .stopAndSurfaceError : .rebuild
  }
}
