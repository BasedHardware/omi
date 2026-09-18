import OmiTheme
import SwiftUI

extension RewindPage {
  var rewindToggle: some View {
    Button {
      toggleMonitoring(enabled: !isMonitoring)
    } label: {
      ZStack {
        Capsule()
          // The adjacent text supplies the state; colour is a redundant signal.
          .fill(
            screenCaptureHealth == .active
              ? Ink.listeningGreen
              : (screenCaptureHealth == .stopped ? Ink.errorRed : PageGlass.warning)
          )
          .frame(width: 36, height: 20)

        Circle()
          .fill(Ink.surface)
          .frame(width: 16, height: 16)
          .shadow(color: .black.opacity(0.08), radius: 1, x: 0, y: 1)
          .offset(x: isMonitoring ? 8 : -8)
          .omiAnimation(.easeInOut(duration: 0.15), value: isMonitoring)

        if isTogglingMonitoring {
          ProgressView()
            .scaleEffect(0.5)
        }
      }
    }
    .buttonStyle(.plain)
    .disabled(isTogglingMonitoring)
    .opacity(isTogglingMonitoring ? 0.5 : 1.0)
    .help(screenCaptureHealth.rewindToggleHelp)
    .accessibilityLabel("Screen capture")
    .accessibilityValue(screenCaptureHealth.statusText)
    .accessibilityHint(isMonitoring ? "Turn screen capture off" : "Turn screen capture on")
  }

  private func toggleMonitoring(enabled: Bool) {
    if enabled {
      // Refresh permission cache before checking (may be stale after user granted access)
      ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
    }

    if enabled && !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
      isMonitoring = false
      ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      return
    }

    isTogglingMonitoring = true
    isMonitoring = enabled
    screenCaptureHealth = enabled ? .active : .stopped

    AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

    screenAnalysisEnabled = enabled
    AssistantSettings.shared.screenAnalysisEnabled = enabled

    if enabled {
      ProactiveAssistantsPlugin.shared.startMonitoring { success, _ in
        DispatchQueue.main.async {
          isTogglingMonitoring = false
          if !success {
            isMonitoring = false
            screenCaptureHealth = .stopped
            // Revert persistent setting so UI and auto-start stay in sync
            screenAnalysisEnabled = false
            AssistantSettings.shared.screenAnalysisEnabled = false
          }
        }
      }
    } else {
      ProactiveAssistantsPlugin.shared.stopMonitoring()
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
        isTogglingMonitoring = false
      }
    }
  }
}
