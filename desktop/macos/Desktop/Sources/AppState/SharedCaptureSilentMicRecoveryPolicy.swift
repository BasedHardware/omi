import AVFoundation
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

/// Authorization gate for arming microphone capture.
///
/// CoreAudio HAL capture never triggers the system microphone prompt on its own: with a
/// notDetermined or revoked TCC entry it "succeeds" and delivers zero samples forever,
/// which the silent-mic watchdog reads as dead hardware. Every decision the gate makes
/// lives here so the denied/revoked path is testable without a TCC database.
enum MicrophoneCaptureAuthorizationPolicy {
  enum Action: Equatable {
    /// Authorization is settled in the app's favor — arm capture.
    case proceed
    /// First run: ask macOS, then re-decide with `action(afterRequestGranted:)`.
    case requestPermission
    /// The user (or MDM) said no — tell them the real problem instead of arming a
    /// zero-sample stream that ends in a hardware alert.
    case surfacePermissionAlert
    /// This start was automatic (launch, reactivation, key load, settings sync, wake,
    /// post-onboarding) and authorization is not settled in the app's favor. Automatic
    /// paths never show a TCC sheet or an alert; they abandon the start and let the
    /// persisted intent wait for an explicit Listen/Grant action.
    case abandonAutomaticStart
  }

  static func action(for status: AVAuthorizationStatus) -> Action {
    switch status {
    case .authorized:
      return .proceed
    case .notDetermined:
      return .requestPermission
    case .denied, .restricted:
      return .surfacePermissionAlert
    @unknown default:
      return .proceed
    }
  }

  /// The single rule behind "skipped or denied permissions must not auto-reprompt":
  /// only an explicit user action may raise the system sheet (or surface the denied
  /// alert). Everything automatic abandons the start instead.
  static func action(for status: AVAuthorizationStatus, userInitiated: Bool) -> Action {
    let resolved = action(for: status)
    if resolved == .proceed { return .proceed }
    return userInitiated ? resolved : .abandonAutomaticStart
  }

  static func action(afterRequestGranted granted: Bool) -> Action {
    granted ? .proceed : .surfacePermissionAlert
  }

  /// Which terminal alert the exhausted silent-mic watchdog shows. An unauthorized app
  /// receives exactly the zero-sample symptom, so permission is checked before blaming
  /// the hardware and sending the user to swap microphones.
  enum TerminalAlert: Equatable {
    case permission
    case hardware
  }

  static func terminalAlert(for status: AVAuthorizationStatus) -> TerminalAlert {
    status == .authorized ? .hardware : .permission
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
