import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var generalSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Screen Capture toggle
      settingsCard(settingId: "general.screencapture") {
        HStack(spacing: OmiSpacing.lg) {
          Circle()
            .fill(isMonitoring ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
            .frame(width: 12, height: 12)
            .shadow(color: isMonitoring ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

          Image(systemName: "rectangle.dashed.badge.record")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.info)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Screen Capture")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              permissionError
                ?? (isMonitoring ? "Capturing screen content" : "Screen capture is paused")
            )
            .scaledFont(size: OmiType.body)
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
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
          }
        }
      }

      // Audio Recording toggle
      settingsCard(settingId: "general.audiorecording") {
        HStack(spacing: OmiSpacing.lg) {
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
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.info)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Audio Recording")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              transcriptionError
                ?? (isTranscribing
                  ? (appState.isAwaitingMeeting
                    ? "Waiting for a meeting…" : "Recording and transcribing audio")
                  : "Audio recording is paused")
            )
            .scaledFont(size: OmiType.body)
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
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
          }
        }
      }

      // Notifications toggle
      settingsCard(settingId: "general.notifications") {
        VStack(spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
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

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Notifications")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(notificationStatusText)
                .scaledFont(size: OmiType.body)
                .foregroundColor(
                  appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.textTertiary
                )
            }

            Spacer()

            // Toggle mirrors the effective notification state. macOS ownership
            // caveat: the app can request/repair permission but cannot revoke
            // it, so flipping OFF (or fixing disabled banners) deep-links to
            // System Settings; the toggle re-syncs from the real permission.
            Toggle(
              "",
              isOn: Binding(
                get: {
                  appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                },
                set: { newValue in
                  if newValue {
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
                  } else {
                    appState.openNotificationPreferences()
                  }
                }
              )
            )
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
          }

          // Warning when banners are disabled
          if appState.isNotificationBannerDisabled {
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "exclamationmark.triangle.fill")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.warning)

              Text(
                "Banners disabled - you won't see visual alerts. Set style to \"Banners\" in System Settings."
              )
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.warning)

              Spacer()
            }
            .padding(OmiSpacing.sm)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .fill(OmiColors.warning.opacity(0.1))
            )
          }
        }
      }

      // System Audio capture mode (macOS 14.4+ — system audio capture requires Core Audio taps)
      if #available(macOS 14.4, *) {
        settingsCard(settingId: "general.systemaudio") {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            HStack(spacing: OmiSpacing.lg) {
              Image(systemName: "speaker.wave.2.fill")
                .scaledFont(size: OmiType.subheading)
                .foregroundColor(OmiColors.info)

              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("System Audio")
                  .scaledFont(size: OmiType.subheading, weight: .semibold)
                  .foregroundColor(OmiColors.textPrimary)

                Text("Choose when Omi records audio from other apps (calls, videos, music).")
                  .scaledFont(size: OmiType.body)
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
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }

      // Font Size
      settingsCard(settingId: "general.fontsize") {
        VStack(spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
            Image(systemName: "textformat.size")
              .scaledFont(size: 16, weight: .medium)
              .foregroundColor(OmiColors.info)
              .frame(width: 12)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Font Size")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text("Scale: \(Int(fontScaleSettings.scale * 100))%")
                .scaledFont(size: OmiType.body)
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

          HStack(spacing: OmiSpacing.md) {
            // The small/large "A" pair illustrates the scale range — keep the
            // original 12/18 ratio rather than the type registers.
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
            .padding(.top, OmiSpacing.xxs)

          // Keyboard shortcuts for font size
          VStack(spacing: OmiSpacing.xs) {
            fontShortcutRow(label: "Increase font size", keys: "\u{2318}+")
            fontShortcutRow(label: "Decrease font size", keys: "\u{2318}\u{2212}")
            fontShortcutRow(label: "Reset font size", keys: "\u{2318}0")
          }
          .padding(.top, OmiSpacing.xxs)

          HStack {
            Spacer()
            Button(action: {
              resetWindowToDefaultSize()
            }) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "arrow.uturn.backward")
                  .scaledFont(size: OmiType.caption)
                Text("Reset Window Size")
                  .scaledFont(size: OmiType.caption, weight: .medium)
              }
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, OmiSpacing.sm)
              .padding(.vertical, OmiSpacing.xxs)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
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
