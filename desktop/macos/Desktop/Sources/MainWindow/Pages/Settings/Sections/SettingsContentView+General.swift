import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var generalSection: some View {
    VStack(spacing: 20) {
      // Screen Capture toggle
      settingsCard(settingId: "general.screencapture") {
        HStack(spacing: 16) {
          Circle()
            .fill(isMonitoring ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
            .frame(width: 12, height: 12)
            .shadow(color: isMonitoring ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

          Image(systemName: "rectangle.dashed.badge.record")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.info)

          VStack(alignment: .leading, spacing: 4) {
            Text("Screen Capture")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              permissionError
                ?? (isMonitoring ? "Capturing screen content" : "Screen capture is paused")
            )
            .scaledFont(size: 13)
            .foregroundColor(permissionError != nil ? OmiColors.warning : OmiColors.textTertiary)
          }

          Spacer()

          if isToggling {
            ProgressView()
              .scaleEffect(0.8)
          } else {
            Toggle(
              "",
              isOn: Binding(
                get: { isMonitoring },
                set: { newValue in
                  isMonitoring = newValue
                  toggleMonitoring(enabled: newValue)
                }
              )
            )
            .toggleStyle(.switch)
            .labelsHidden()
          }
        }
      }

      // Audio Recording toggle
      settingsCard(settingId: "general.audiorecording") {
        HStack(spacing: 16) {
          Circle()
            .fill(
              isTranscribing
                ? (appState.isAwaitingMeeting ? OmiColors.warning : OmiColors.success)
                : OmiColors.textTertiary.opacity(0.3)
            )
            .frame(width: 12, height: 12)
            .shadow(
              color: isTranscribing
                ? (appState.isAwaitingMeeting ? OmiColors.warning : OmiColors.success).opacity(0.5)
                : .clear, radius: 6)

          Image(systemName: "mic.fill")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.info)

          VStack(alignment: .leading, spacing: 4) {
            Text("Audio Recording")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              transcriptionError
                ?? (isTranscribing
                  ? (appState.isAwaitingMeeting
                    ? "Waiting for a meeting…" : "Recording and transcribing audio")
                  : "Audio recording is paused")
            )
            .scaledFont(size: 13)
            .foregroundColor(transcriptionError != nil ? OmiColors.warning : OmiColors.textTertiary)
          }

          Spacer()

          if isTogglingTranscription {
            ProgressView()
              .scaleEffect(0.8)
          } else {
            Toggle(
              "",
              isOn: Binding(
                get: { isTranscribing },
                set: { newValue in
                  isTranscribing = newValue
                  toggleTranscription(enabled: newValue)
                }
              )
            )
            .toggleStyle(.switch)
            .labelsHidden()
          }
        }
      }

      // System Audio capture mode (macOS 14.4+ — system audio capture requires Core Audio taps)
      if #available(macOS 14.4, *) {
        settingsCard(settingId: "general.systemaudio") {
          VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 16) {
              Image(systemName: "speaker.wave.2.fill")
                .scaledFont(size: 16)
                .foregroundColor(OmiColors.info)

              VStack(alignment: .leading, spacing: 4) {
                Text("System Audio")
                  .scaledFont(size: 16, weight: .semibold)
                  .foregroundColor(OmiColors.textPrimary)

                Text("Choose when Omi records audio from other apps (calls, videos, music).")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              }

              Spacer()

              Picker(
                "",
                selection: Binding(
                  get: { systemAudioCaptureMode },
                  set: { newValue in
                    systemAudioCaptureMode = newValue
                    setSystemAudioCaptureMode(newValue)
                  }
                )
              ) {
                Text("Always").tag(AssistantSettings.SystemAudioCaptureMode.always)
                Text("Only during meetings").tag(
                  AssistantSettings.SystemAudioCaptureMode.onlyDuringMeetings)
                Text("Never").tag(AssistantSettings.SystemAudioCaptureMode.never)
              }
              .pickerStyle(.menu)
              .labelsHidden()
              .frame(width: 200)
            }

            if systemAudioCaptureMode == .onlyDuringMeetings {
              Text(
                "Omi captures other apps' audio only while you're in a call (e.g. Zoom, Teams, FaceTime). Detecting browser-based calls like Google Meet requires Screen Recording permission."
              )
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }

      // Notifications toggle
      settingsCard(settingId: "general.notifications") {
        VStack(spacing: 12) {
          HStack(spacing: 16) {
            Circle()
              .fill(
                appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                  ? OmiColors.success
                  : (appState.isNotificationBannerDisabled
                    ? OmiColors.warning : OmiColors.textTertiary.opacity(0.3))
              )
              .frame(width: 12, height: 12)
              .shadow(
                color: appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                  ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

            VStack(alignment: .leading, spacing: 4) {
              Text("Notifications")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(notificationStatusText)
                .scaledFont(size: 13)
                .foregroundColor(
                  appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.textTertiary
                )
            }

            Spacer()

            if appState.hasNotificationPermission && !appState.isNotificationBannerDisabled {
              // Show enabled badge
              Text("Enabled")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(.green)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                  Capsule()
                    .fill(Color.green.opacity(0.15))
                )
            } else {
              // Show button to enable or fix
              Button(action: {
                if appState.isNotificationBannerDisabled {
                  // Banners off — user needs to change style in System Settings
                  appState.openNotificationPreferences()
                } else {
                  // Auth not granted — try lsregister repair first
                  AnalyticsManager.shared.notificationRepairTriggered(
                    reason: "settings_fix_button",
                    previousStatus: "not_authorized",
                    currentStatus: "not_authorized"
                  )
                  appState.repairNotificationAndFallback()
                }
              }) {
                Text(appState.isNotificationBannerDisabled ? "Fix" : "Enable")
                  .scaledFont(size: 12, weight: .semibold)
                  .foregroundColor(.white)
                  .padding(.horizontal, 12)
                  .padding(.vertical, 6)
                  .background(
                    RoundedRectangle(cornerRadius: 6)
                      .fill(
                        appState.isNotificationBannerDisabled
                          ? OmiColors.warning : OmiColors.info)
                  )
              }
              .buttonStyle(.plain)
            }
          }

          // Warning when banners are disabled
          if appState.isNotificationBannerDisabled {
            HStack(spacing: 8) {
              Image(systemName: "exclamationmark.triangle.fill")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.warning)

              Text(
                "Banners disabled - you won't see visual alerts. Set style to \"Banners\" in System Settings."
              )
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)

              Spacer()
            }
            .padding(10)
            .background(
              RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.warning.opacity(0.1))
            )
          }
        }
      }

      // Font Size
      settingsCard(settingId: "general.fontsize") {
        VStack(spacing: 12) {
          HStack(spacing: 16) {
            Image(systemName: "textformat.size")
              .scaledFont(size: 16, weight: .medium)
              .foregroundColor(OmiColors.info)
              .frame(width: 12)

            VStack(alignment: .leading, spacing: 4) {
              Text("Font Size")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text("Scale: \(Int(fontScaleSettings.scale * 100))%")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if fontScaleSettings.scale != 1.0 {
              Button("Reset") {
                fontScaleSettings.resetToDefault()
              }
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(OmiColors.info)
              .buttonStyle(.plain)
            }
          }

          HStack(spacing: 12) {
            Text("A")
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)

            Slider(value: $fontScaleSettings.scale, in: 0.5...2.0, step: 0.05)
              .tint(OmiColors.info)

            Text("A")
              .scaledFont(size: 18, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
          }

          Text("The quick brown fox jumps over the lazy dog")
            .scaledFont(size: 14)
            .foregroundColor(OmiColors.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)

          // Keyboard shortcuts for font size
          VStack(spacing: 6) {
            fontShortcutRow(label: "Increase font size", keys: "\u{2318}+")
            fontShortcutRow(label: "Decrease font size", keys: "\u{2318}\u{2212}")
            fontShortcutRow(label: "Reset font size", keys: "\u{2318}0")
          }
          .padding(.top, 4)

          HStack {
            Spacer()
            Button(action: {
              resetWindowToDefaultSize()
            }) {
              HStack(spacing: 6) {
                Image(systemName: "arrow.uturn.backward")
                  .scaledFont(size: 11)
                Text("Reset Window Size")
                  .scaledFont(size: 12, weight: .medium)
              }
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 10)
              .padding(.vertical, 5)
              .background(
                RoundedRectangle(cornerRadius: 6)
                  .fill(OmiColors.backgroundTertiary)
              )
            }
            .buttonStyle(.plain)
          }
        }
      }

    }
  }

}
