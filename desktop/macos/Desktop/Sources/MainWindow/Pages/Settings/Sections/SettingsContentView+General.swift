import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var generalSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Screen Capture toggle
      settingsCard(settingId: "general.screencapture") {
        VStack(spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "rectangle.dashed.badge.record", title: "Screen Capture")
          settingRow(
            title: "Status",
            subtitle: permissionError ?? screenCaptureHealth.statusText
          ) {
            if isToggling {
              ProgressView()
                .scaleEffect(0.8)
                .frame(width: 36, height: 20)
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
              .frame(width: 36, height: 20)
            }
          }
        }
      }

      // Audio Recording toggle
      settingsCard(settingId: "general.audiorecording") {
        VStack(spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "mic.fill", title: "Audio Recording")
          settingRow(
            title: "Status",
            subtitle: transcriptionError
              ?? (isTranscribing
                ? (appState.isAwaitingMeeting
                  ? "Waiting for a meeting…" : "Recording and transcribing audio")
                : "Audio recording is paused")
          ) {
            if isTogglingTranscription {
              ProgressView()
                .scaleEffect(0.8)
                .frame(width: 36, height: 20)
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
              .frame(width: 36, height: 20)
            }
          }
        }
      }

      // Notifications toggle
      settingsCard(settingId: "general.notifications") {
        VStack(spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "bell.fill", title: "Notifications")
          settingRow(
            title: "Status",
            subtitle: notificationStatusText
          ) {
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
            .frame(width: 36, height: 20)
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
            settingsCardHeader(icon: "speaker.wave.2.fill", title: "System Audio")
            settingRow(
              title: "Capture Mode",
              subtitle: "Choose when Omi records audio from other apps (calls, videos, music)."
            ) {
              SettingsMenuPicker(
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
          settingsCardHeader(icon: "textformat.size", title: "Font Size")
          settingRow(
            title: "Scale",
            subtitle: "Current scale: \(Int(fontScaleSettings.scale * 100))%"
          ) {
            if fontScaleSettings.scale != 1.0 {
              Button("Reset") {
                fontScaleSettings.resetToDefault()
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            } else {
              EmptyView()
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
              .onChange(of: fontScaleSettings.scale) { _, _ in
                performStepHaptic()
              }

            Text("A")
              .scaledFont(size: 18, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
          }

          Text("The quick brown fox jumps over the lazy dog")
            .scaledFont(size: 14)
            .foregroundColor(OmiColors.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, OmiSpacing.xxs)

          HStack {
            Spacer()
            Button(action: {
              resetWindowToDefaultSize()
            }) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "arrow.uturn.backward")
                Text("Reset Window Size")
              }
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          }
        }
      }

    }
  }

}
