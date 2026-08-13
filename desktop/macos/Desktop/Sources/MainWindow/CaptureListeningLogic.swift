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

  // MARK: Actions

  static func toggleListening(
    appState: AppState, audioRecordingModeRaw: Binding<String>, isTogglingListening: Binding<Bool>
  ) {
    let currentMode = audioRecordingMode(raw: audioRecordingModeRaw.wrappedValue)
    let nextMode: AssistantSettings.AudioRecordingMode = currentMode == .off ? .onlyMeetings : .off
    let enabled = nextMode != .off
    if enabled && !appState.hasMicrophonePermission {
      appState.requestMicrophonePermission()
      return
    }

    isTogglingListening.wrappedValue = true
    audioRecordingModeRaw.wrappedValue = nextMode.rawValue
    AssistantSettings.shared.audioRecordingMode = nextMode
    AnalyticsManager.shared.settingToggled(setting: "audio_recording_mode_\(nextMode.rawValue)", enabled: enabled)
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
      isTogglingListening.wrappedValue = false
    }
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
