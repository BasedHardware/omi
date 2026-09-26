import SwiftUI

/// Shared Capture/Listening control logic used by both the top bar's wordless status cluster
/// (`ShellStatusIcons`) and the legacy Home's column-aligned header
/// (`DashboardPage.homeHeader`). The two surfaces render different layouts but
/// drive identical behavior, so the toggle actions and status derivations live
/// here once. Each view keeps its own `@State`/`@AppStorage` (preserving SwiftUI
/// ownership + reactivity) and passes them in as values/bindings.
@MainActor
enum CaptureListeningLogic {
  // MARK: Status derivations

  static func captureStatus(appState: AppState, isCaptureMonitoring: Bool) -> HomeStatusState {
    if appState.isScreenCaptureKitBroken || appState.isScreenRecordingStale || !appState.hasScreenRecordingPermission {
      return .blocked
    }
    return isCaptureLive(isCaptureMonitoring: isCaptureMonitoring) ? .active : .inactive
  }

  static func isCaptureLive(isCaptureMonitoring: Bool) -> Bool {
    isCaptureMonitoring || ProactiveAssistantsPlugin.shared.isMonitoring
  }

  /// The top-bar listening readout. An Only Meetings session that is only *armed* (no call yet) is
  /// `.armed`, not `.active`: it is switched on, so it wears no off-slash, but nothing is recorded
  /// yet, and green is reserved for recording now. Whether audio is reaching STT is
  /// `isLiveCapturing`, which the live-transcript surfaces read directly.
  static func listeningStatus(appState: AppState) -> HomeStatusState {
    if appState.transcriptionServiceError != nil { return .blocked }
    if appState.isLiveCapturing { return .active }
    return appState.isAwaitingMeeting ? .armed : .inactive
  }

  static func audioRecordingMode(raw: String) -> AssistantSettings.AudioRecordingMode {
    AssistantSettings.AudioRecordingMode(rawValue: raw) ?? .onlyMeetings
  }

  static func listeningModeTitle(appState: AppState, raw: String) -> String {
    // Surface the explicitly-chosen mic as the visible capture source. Meta
    // glasses advertise a Bluetooth codename (e.g. "EL AI 000F"), so product-
    // name matching alone can't identify them — an explicit user selection is
    // the reliable signal, and showing its real name stays honest either way.
    // While "Only during meetings" is armed but no meeting is live, no mic is
    // actually open — keep the mode title instead of implying live capture.
    if appState.isTranscribing, !appState.isAwaitingMeeting,
      let name = appState.recordingInputDeviceName
    {
      if AudioCaptureService.isMetaGlassesName(name) {
        return name.localizedCaseInsensitiveContains("oakley") ? name : "Ray-Ban Meta"
      }
      let preferredUID =
        UserDefaults.standard.string(
          forKey: AudioCaptureService.preferredInputUIDDefaultsKey) ?? ""
      if !preferredUID.isEmpty {
        return name
      }
    }
    switch audioRecordingMode(raw: raw) {
    case .off:
      return "Off"
    case .always:
      return "Always On"
    case .onlyMeetings:
      return appState.isAwaitingMeeting ? "Only Meetings" : "In Meeting"
    }
  }

  /// The name of a *mode*, for naming a state the session is not in yet.
  ///
  /// Distinct from `listeningModeTitle`, which describes the **running** session and may answer
  /// with the live microphone's own name ("Ray-Ban Meta") or with "In Meeting". That is the right
  /// answer for "what is happening now" and the wrong one for "what does this choice select".
  nonisolated static func audioRecordingModeTitle(_ mode: AssistantSettings.AudioRecordingMode) -> String {
    switch mode {
    case .off: return "Off"
    case .always: return "Always On"
    case .onlyMeetings: return "Only Meetings"
    }
  }

  // MARK: Actions

  /// What choosing `requested` from the mode menu does, decided without touching anything.
  enum ListeningModeSelection: Equatable {
    /// The mode is already selected and can record; nothing moves.
    case unchanged
    /// The mode needs the microphone and Omi has no grant: the choice is spent on the permission
    /// request and the mode stays where it was.
    case needsMicrophonePermission
    /// The mode is applied.
    case apply(AssistantSettings.AudioRecordingMode)
  }

  nonisolated static func listeningModeSelection(
    current: AssistantSettings.AudioRecordingMode, requested: AssistantSettings.AudioRecordingMode,
    hasMicrophonePermission: Bool
  ) -> ListeningModeSelection {
    // Permission first: choosing a mode that is already selected but cannot record (the grant was
    // revoked) is a request to make it work, so it asks rather than doing nothing.
    if requested != .off && !hasMicrophonePermission { return .needsMicrophonePermission }
    return requested == current ? .unchanged : .apply(requested)
  }

  /// The side effects of a selection, injectable so a test can run the production path without
  /// raising the TCC prompt or rewriting the user's recording mode.
  struct ListeningModeEffects {
    var requestMicrophonePermission: @MainActor (AppState) -> Void
    var persist: @MainActor (AssistantSettings.AudioRecordingMode) -> Void
    var track: @MainActor (AssistantSettings.AudioRecordingMode) -> Void

    static var live: ListeningModeEffects {
      ListeningModeEffects(
        requestMicrophonePermission: { $0.requestMicrophonePermission() },
        persist: { AssistantSettings.shared.audioRecordingMode = $0 },
        track: {
          AnalyticsManager.shared.settingToggled(
            setting: "audio_recording_mode_\($0.rawValue)", enabled: $0 != .off)
        })
    }
  }

  /// Apply a mode chosen from the listening control's menu. Returns what happened, so the caller
  /// can tell an applied choice from one spent on the microphone prompt.
  @discardableResult
  static func selectListeningMode(
    _ requested: AssistantSettings.AudioRecordingMode, appState: AppState,
    audioRecordingModeRaw: Binding<String>, isTogglingListening: Binding<Bool>,
    effects: ListeningModeEffects = .live
  ) -> ListeningModeSelection {
    let outcome = listeningModeSelection(
      current: audioRecordingMode(raw: audioRecordingModeRaw.wrappedValue), requested: requested,
      hasMicrophonePermission: appState.hasMicrophonePermission)
    switch outcome {
    case .unchanged:
      break
    case .needsMicrophonePermission:
      effects.requestMicrophonePermission(appState)
    case .apply(let mode):
      isTogglingListening.wrappedValue = true
      audioRecordingModeRaw.wrappedValue = mode.rawValue
      effects.persist(mode)
      effects.track(mode)
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
        isTogglingListening.wrappedValue = false
      }
    }
    return outcome
  }

  static func toggleCapture(
    appState: AppState, screenAnalysisEnabled: Binding<Bool>, isCaptureMonitoring: Binding<Bool>,
    isTogglingCapture: Binding<Bool>
  ) {
    syncCaptureState(screenAnalysisEnabled: screenAnalysisEnabled, isCaptureMonitoring: isCaptureMonitoring)
    let enabled = !isCaptureLive(isCaptureMonitoring: isCaptureMonitoring.wrappedValue)
    isTogglingCapture.wrappedValue = true

    if enabled {
      ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
      guard ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission else {
        screenAnalysisEnabled.wrappedValue = false
        isCaptureMonitoring.wrappedValue = false
        isTogglingCapture.wrappedValue = false
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        return
      }
    }

    screenAnalysisEnabled.wrappedValue = enabled
    AssistantSettings.shared.screenAnalysisEnabled = enabled
    AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

    if enabled {
      ProactiveAssistantsPlugin.shared.startMonitoring { success, _ in
        DispatchQueue.main.async {
          isTogglingCapture.wrappedValue = false
          isCaptureMonitoring.wrappedValue = ProactiveAssistantsPlugin.shared.isMonitoring
          if !success {
            screenAnalysisEnabled.wrappedValue = false
            AssistantSettings.shared.screenAnalysisEnabled = false
            isCaptureMonitoring.wrappedValue = false
          }
        }
      }
    } else {
      ProactiveAssistantsPlugin.shared.stopMonitoring()
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
        isTogglingCapture.wrappedValue = false
        isCaptureMonitoring.wrappedValue = false
      }
    }
  }

  static func syncCaptureState(screenAnalysisEnabled: Binding<Bool>, isCaptureMonitoring: Binding<Bool>) {
    ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
    screenAnalysisEnabled.wrappedValue = AssistantSettings.shared.screenAnalysisEnabled
    isCaptureMonitoring.wrappedValue = ProactiveAssistantsPlugin.shared.isMonitoring
  }
}
