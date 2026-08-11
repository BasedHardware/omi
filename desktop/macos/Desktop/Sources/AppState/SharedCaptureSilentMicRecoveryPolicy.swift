import CoreAudio

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

/// Which input device a rebuilt capture stack must use.
///
/// The alert loop this exists to prevent: a silent Bluetooth mic triggers a fallback onto
/// the built-in device, then the next watchdog trip rebuilds the CoreAudio stack from the
/// *system default* — still the silent device — and the two fight until the recovery cap is
/// hit and the user gets a modal. A heal that a rebuild can undo is not a heal.
enum SilentMicRoutePolicy {
  /// `healed` wins for the rest of the session; `nil` means follow the system default.
  static func captureDeviceID(
    healed: AudioDeviceID?,
    systemDefault: AudioDeviceID?
  ) -> AudioDeviceID? {
    healed ?? systemDefault
  }
}
