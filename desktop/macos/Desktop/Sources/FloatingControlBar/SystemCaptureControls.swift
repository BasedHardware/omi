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

  // Reflects runtime truth (is monitoring actually running), not a paywall
  // gate: the paywall only ever blocks *starting* monitoring (see
  // setScreenCapture below, whose `enabled == false` branch is ungated), so
  // gating this display too made the switch lie about a still-running
  // monitor and get stuck: showing OFF while paywalled made the next click
  // request `enabled: true` (blocked, switch snaps back OFF) instead of the
  // `enabled: false` that would have actually stopped it.
  static var isScreenCaptureOn: Bool {
    AssistantSettings.shared.screenAnalysisEnabled
      && ProactiveAssistantsPlugin.shared.isMonitoring
  }

  static var isAudioRecordingOn: Bool {
    AppState.isTranscriptionExemptFromPaywall && AssistantSettings.shared.audioRecordingMode != .off
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

    // Posts its own "screen_capture" reason (not "trial_expired") so the
    // central `AppState.isUsageLimitExemptLocally` choke point can match this
    // gate's exemption exactly instead of relying on a shared, less precise
    // reason string.
    if !AppState.isScreenCaptureExemptFromPaywall {
      NotificationCenter.default.post(
        name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "screen_capture"])
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
    // Same general paywall check as everything else (see
    // AppState.isTranscriptionExemptFromPaywall): voice transcription always
    // runs through Omi's Deepgram proxy, so the Local provider earns no
    // exemption here. Posts its own "transcription" reason (not
    // "trial_expired") so the central
    // `AppState.isUsageLimitExemptLocally` choke point can tell this gate
    // apart from screen capture's and apply the right exemption to each.
    if enabled && !AppState.isTranscriptionExemptFromPaywall {
      NotificationCenter.default.post(
        name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "transcription"])
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
