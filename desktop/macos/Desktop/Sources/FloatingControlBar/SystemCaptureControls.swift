import Foundation

/// What happened when a surface asked to change a capture toggle.
///
/// Returned rather than acted on so the caller can reflect the real end state — a request
/// to enable that was refused must leave the control showing OFF, not the value the user
/// clicked.
enum SystemCaptureOutcome: Equatable, Sendable {
  case enabled
  case disabled
  /// Trial expired or usage limit hit. The upgrade popup has been posted.
  case blockedPaywall
  /// Screen Recording permission is missing. Settings has been opened.
  case blockedPermission
  /// Capture accepted the request but the monitor failed to start; state was rolled back.
  case failedToStart

  /// The state the control should display after this outcome.
  var resultingIsOn: Bool { self == .enabled }
}

enum AudioRecordingPermissionTransitionPolicy {
  static func shouldRequestPermission(
    currentMode: AssistantSettings.AudioRecordingMode,
    requestedMode: AssistantSettings.AudioRecordingMode,
    permissionGranted: Bool
  ) -> Bool {
    currentMode == .off && requestedMode != .off && !permissionGranted
  }
}

/// Single owner of the screen-capture and audio-recording toggle transitions.
///
/// The menu-bar toggles and the notch control cluster are two surfaces over one piece of
/// state. The paywall gate, the permission gate, and the start/rollback sequence live here
/// once so a second surface cannot drift from the first — enabling capture from the notch
/// has to refuse for exactly the same reasons, in the same order, as enabling it from the
/// menu bar.
@MainActor
enum SystemCaptureControls {
  // MARK: - Current state

  static var isScreenCaptureOn: Bool {
    !AppState.isPaywalledEffective
      && AssistantSettings.shared.screenAnalysisEnabled
      && ProactiveAssistantsPlugin.shared.isMonitoring
  }

  static var isAudioRecordingOn: Bool {
    !AppState.isPaywalledEffective && AssistantSettings.shared.audioRecordingMode != .off
  }

  // MARK: - Transitions

  /// Ordering is load-bearing: paywall is checked before permission, so an expired trial
  /// surfaces the upgrade path rather than a permission prompt the user cannot act on.
  @discardableResult
  static func setScreenCapture(_ enabled: Bool, onStartResult: ((Bool) -> Void)? = nil) -> SystemCaptureOutcome {
    guard enabled else {
      AssistantSettings.shared.screenAnalysisEnabled = false
      ProactiveAssistantsPlugin.shared.stopMonitoring()
      return .disabled
    }

    if AppState.isPaywalledEffective {
      NotificationCenter.default.post(
        name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "trial_expired"])
      return .blockedPaywall
    }

    if !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
      ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      return .blockedPermission
    }

    AssistantSettings.shared.screenAnalysisEnabled = true
    ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
      DispatchQueue.main.async {
        if !success {
          log("SystemCaptureControls: screen capture failed to start: \(error ?? "unknown")")
          AssistantSettings.shared.screenAnalysisEnabled = false
        }
        onStartResult?(success)
      }
    }
    return .enabled
  }

  @discardableResult
  static func setAudioRecording(_ enabled: Bool) -> SystemCaptureOutcome {
    if enabled && AppState.isPaywalledEffective {
      NotificationCenter.default.post(
        name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "trial_expired"])
      return .blockedPaywall
    }

    let current = AssistantSettings.shared.audioRecordingMode
    let requested: AssistantSettings.AudioRecordingMode = enabled ? (current == .off ? .onlyMeetings : current) : .off
    let shouldRequestPermission = AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
      currentMode: current,
      requestedMode: requested,
      permissionGranted: AudioCaptureService.checkPermission())
    AssistantSettings.shared.audioRecordingMode = requested
    if shouldRequestPermission {
      AppState.current?.requestMicrophonePermission()
    }
    return enabled ? .enabled : .disabled
  }
}
