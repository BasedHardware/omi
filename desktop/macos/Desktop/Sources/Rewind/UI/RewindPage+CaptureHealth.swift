import OmiTheme
import SwiftUI

extension RewindPage {
  var rewindToggle: some View {
    ZStack {
      Capsule()
        .fill(
          screenCaptureHealth == .active
            ? OmiColors.accent
            : (screenCaptureHealth == .stopped ? Color.red : OmiColors.warning)
        )
        .frame(width: 36, height: 20)

      Circle()
        .fill(isMonitoring ? OmiColors.backgroundPrimary : Color.white)
        .frame(width: 16, height: 16)
        .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
        .offset(x: isMonitoring ? 8 : -8)
        .omiAnimation(.easeInOut(duration: 0.15), value: isMonitoring)
    }
    .opacity(isTogglingMonitoring ? 0.5 : 1.0)
    .overlay {
      if isTogglingMonitoring {
        ProgressView()
          .scaleEffect(0.5)
      }
    }
    .onTapGesture {
      if !isTogglingMonitoring {
        toggleMonitoring(enabled: !isMonitoring)
      }
    }
    .help(screenCaptureHealth.rewindToggleHelp)
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
