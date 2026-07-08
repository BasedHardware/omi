import SwiftUI

/// Slim window top bar for the redesign: the `omi` wordmark on the left; on the
/// right, live Capture / Listening presence chips and a notification bell.
/// Capture toggles screen monitoring; Listening toggles transcription; the bell
/// opens Insights (where omi's proactive nudges live).
struct RedesignTopBar: View {
  @ObservedObject var appState: AppState
  @ObservedObject private var insightStorage = InsightStorage.shared
  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
  var onNotifications: () -> Void = {}

  var body: some View {
    HStack(spacing: 14) {
      Text("omi").inkWordmark(17)
      Spacer()
      PresenceChip(icon: "display", label: "Capture", on: screenAnalysisEnabled, toggle: toggleCapture)
      PresenceChip(icon: "mic", label: "Listening", on: appState.isTranscribing, toggle: toggleListening)
      NotificationBell(unread: insightStorage.unreadCount, action: onNotifications)
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

private struct NotificationBell: View {
  let unread: Int
  let action: () -> Void
  @State private var hovering = false

  var body: some View {
    Button(action: action) {
      ZStack(alignment: .topTrailing) {
        Image(systemName: "bell")
          .font(.system(size: 14))
          .foregroundColor(hovering ? Ink.ink : Ink.body)
          .frame(width: 28, height: 28)
          .background(Circle().fill(hovering ? Ink.surface2 : .clear))
        if unread > 0 {
          Circle().fill(Ink.warn).frame(width: 7, height: 7).offset(x: -4, y: 4)
        }
      }
      .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .onHover { hovering = $0 }
    .help(unread > 0 ? "\(unread) new — open notifications" : "Notifications")
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
      .background(Capsule().fill(hovering ? Ink.surface2 : .clear))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { hovering = $0 }
    .help(on ? "\(label) on — click to turn off" : "\(label) off — click to turn on")
  }
}
