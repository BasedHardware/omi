import SwiftUI

/// Slim window top bar for the redesign: the `omi` wordmark on the left and the
/// live, clickable Capture / Listening presence chips on the right (mockup titlebar).
/// Capture toggles screen monitoring; Listening toggles transcription.
struct RedesignTopBar: View {
  @ObservedObject var appState: AppState
  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true

  var body: some View {
    HStack {
      Text("omi").inkWordmark(17)
      Spacer()
      PresenceChip(icon: "display", label: "Capture", on: screenAnalysisEnabled, toggle: toggleCapture)
      PresenceChip(icon: "mic", label: "Listening", on: appState.isTranscribing, toggle: toggleListening)
    }
    .padding(.horizontal, 18)
    .frame(height: 40)
    .background(Ink.soft)
    .overlay(Rectangle().fill(Ink.hair).frame(height: 1), alignment: .bottom)
  }

  private func toggleCapture() {
    let newValue = !screenAnalysisEnabled
    screenAnalysisEnabled = newValue
    AssistantSettings.shared.screenAnalysisEnabled = newValue
    AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: newValue)
    if newValue {
      ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
      if ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
        ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
      } else {
        ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
      }
    } else {
      ProactiveAssistantsPlugin.shared.stopMonitoring()
    }
  }

  private func toggleListening() {
    let newValue = !appState.isTranscribing
    if newValue && !appState.hasMicrophonePermission {
      appState.requestMicrophonePermission()
      return
    }
    AssistantSettings.shared.transcriptionEnabled = newValue
    AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: newValue)
    if newValue { appState.startTranscription() } else { appState.stopTranscription() }
  }
}

private struct PresenceChip: View {
  let icon: String
  let label: String
  let on: Bool
  let toggle: () -> Void

  @State private var hovering = false

  var body: some View {
    Button(action: toggle) {
      HStack(spacing: 5) {
        Image(systemName: icon).font(.system(size: 11)).foregroundColor(on ? Ink.body : Ink.faint)
        if on {
          LiveDot(size: 6)
        } else {
          Circle().fill(Ink.faint.opacity(0.5)).frame(width: 6, height: 6)
        }
        Text(label).font(InkFont.sans(11.5, .medium)).foregroundColor(on ? Ink.ink : Ink.muted)
      }
      .padding(.horizontal, 8)
      .frame(height: 26)
      .background(
        Capsule().fill(hovering ? Ink.surface2 : .clear))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { hovering = $0 }
    .help(on ? "\(label) on — click to turn off" : "\(label) off — click to turn on")
  }
}
