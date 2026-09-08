import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

// The row icons here were bare SF Symbols in `Ink.accent`, and both halves of that were wrong on
// this pane.
//
// *Bare* is a layout bug you can see: `rectangle.dashed.badge.record`, `mic.fill`, `bell.fill`,
// `speaker.wave.2.fill` and `textformat.size` have wildly different optical widths, so the column of
// titles beside them stepped left and right down the page instead of lining up. That is the exact
// failure `SettingsIconTile` exists to fix — a fixed 26 pt ground is what makes a column of symbols
// stop shimmering — and Notifications & Privacy already used it, so General and its neighbour were
// two different designs.
//
// *Accent* spends the one accent on decoration. `Ink.accent` is reserved for the thing that is
// actionable and is not already a control, which on this surface is the sidebar's selected row; with
// every icon on the pane in the same blue, the selection had nothing left to say. The tile's default
// tint is `Ink.primary`, which is what the rest of the pane is set in.
extension SettingsContentView {
  var generalSection: some View {
    VStack(spacing: OmiSpacing.sm) {
      // Screen Capture toggle
      settingsCard(settingId: "general.screencapture") {
        HStack(spacing: OmiSpacing.lg) {
          SettingsIconTile(symbol: "rectangle.dashed.badge.record")

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Screen Capture")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text(
              permissionError
                ?? screenCaptureHealth.statusText
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(
              permissionError != nil || screenCaptureHealth == .temporarilyUnavailable
                || screenCaptureHealth == .recovering
                ? SettingsInk.notice : Ink.secondary
            )
          }

          Spacer()

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

      // One recording policy; no independent enable switch or system-audio mode.
      settingsCard(settingId: "general.audiorecording") {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          HStack(spacing: OmiSpacing.lg) {
            SettingsIconTile(symbol: "mic.fill")

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Audio Recording")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(Ink.primary)

              Text(audioRecordingStatusText)
                .scaledFont(size: OmiType.body)
                .foregroundColor(audioRecordingNeedsAttention ? SettingsInk.notice : Ink.secondary)
            }

            Spacer()

            AudioRecordingModeSwitcher(selection: audioRecordingModeBinding)
          }

        }
      }

      // Notifications toggle
      settingsCard(settingId: "general.notifications") {
        VStack(spacing: OmiSpacing.xs) {
          HStack(spacing: OmiSpacing.lg) {
            SettingsIconTile(symbol: "bell.fill")

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Notifications")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(Ink.primary)

              Text(notificationStatusText)
                .scaledFont(size: OmiType.body)
                .foregroundColor(
                  appState.isNotificationBannerDisabled ? SettingsInk.notice : Ink.secondary
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
                      // Request the native prompt when possible; a prior denial opens
                      // System Settings immediately without restarting notification services.
                      AnalyticsManager.shared.notificationRepairTriggered(
                        reason: "settings_fix_button",
                        previousStatus: "not_authorized",
                        currentStatus: "not_authorized"
                      )
                      appState.requestNotificationPermission()
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
                .foregroundColor(SettingsInk.notice)

              Text(
                "Banners disabled - you won't see visual alerts. Set style to \"Banners\" in System Settings."
              )
              .scaledFont(size: OmiType.caption)
              .foregroundColor(SettingsInk.notice)

              Spacer()
            }
            .padding(OmiSpacing.sm)
            .background(
              RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                .fill(SettingsInk.notice.opacity(0.1))
            )
          }
        }
      }

      // Interface Sounds
      settingsCard(settingId: "general.interfacesounds") {
        InterfaceSoundsRow()
      }

      // Font Size
      settingsCard(settingId: "general.fontsize") {
        VStack(spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.lg) {
            SettingsIconTile(symbol: "textformat.size")

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Font Size")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(Ink.primary)

              Text("Scale: \(Int(fontScaleSettings.scale * 100))%")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }

            Spacer()

            if fontScaleSettings.scale != 1.0 {
              Button("Reset") {
                fontScaleSettings.resetToDefault()
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            }
          }

          HStack(spacing: OmiSpacing.md) {
            // The small/large "A" pair illustrates the scale range — keep the
            // original 12/18 ratio rather than the type registers.
            Text("A")
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(Ink.secondary)

            Slider(value: $fontScaleSettings.scale, in: 0.5...2.0, step: 0.05)
              .tint(Ink.accent)
              .onChange(of: fontScaleSettings.scale) { _, _ in
                performStepHaptic()
              }

            Text("A")
              .scaledFont(size: 18, weight: .medium)
              .foregroundColor(Ink.secondary)
          }

          Text("The quick brown fox jumps over the lazy dog")
            .scaledFont(size: 14)
            .foregroundColor(Ink.secondary)
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

  private var audioRecordingMode: AssistantSettings.AudioRecordingMode {
    AssistantSettings.AudioRecordingMode(rawValue: audioRecordingModeRaw) ?? .onlyMeetings
  }

  private var audioRecordingModeBinding: Binding<AssistantSettings.AudioRecordingMode> {
    Binding(
      get: { audioRecordingMode },
      set: { mode in
        let previousMode = audioRecordingMode
        audioRecordingModeRaw = mode.rawValue
        AnalyticsManager.shared.settingToggled(
          setting: "audio_recording_mode_\(mode.rawValue)", enabled: mode != .off)
        AssistantSettings.shared.audioRecordingMode = mode
        // The mode-change observer restores capture automatically, and automatic
        // starts never raise the TCC sheet. Enabling listening here IS an explicit
        // user action, so it owns the one-shot permission request itself (same
        // contract as the Listen control's `cycleListening`).
        if AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
          currentMode: previousMode,
          requestedMode: mode,
          permissionGranted: appState.hasMicrophonePermission)
        {
          appState.requestMicrophonePermission()
        }
      }
    )
  }

  private var audioRecordingNeedsAttention: Bool {
    audioRecordingMode != .off && !appState.hasMicrophonePermission
  }

  private var audioRecordingStatusText: String {
    if audioRecordingNeedsAttention { return "Microphone permission required" }
    switch audioRecordingMode {
    case .off:
      return "Off — no ambient audio is recorded"
    case .always:
      return appState.isTranscribing ? "Always on — recording audio" : "Always on — ready to record"
    case .onlyMeetings:
      if appState.isAwaitingMeeting { return "Only Meetings — waiting for a call" }
      return appState.isTranscribing ? "Only Meetings — recording a call" : "Only Meetings — ready"
    }
  }
}

/// The recording policy is a mode, so keep all three choices visible and one click away.
/// This intentionally uses the same raised-segment treatment as the chat mode switcher instead of
/// a menu: users should be able to compare the policies without opening another surface.
private struct AudioRecordingModeSwitcher: View {
  @Binding var selection: AssistantSettings.AudioRecordingMode

  var body: some View {
    HStack(spacing: 2) {
      segment(.off, label: "Off")
      segment(.always, label: "Always")
      segment(.onlyMeetings, label: "Meetings")
    }
    .padding(3)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .fill(Ink.rowFill)
    )
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .strokeBorder(Ink.hairline, lineWidth: 1)
    )
    .frame(width: 230)
    .accessibilityElement(children: .contain)
    .accessibilityLabel("Audio Recording")
  }

  private func segment(
    _ mode: AssistantSettings.AudioRecordingMode,
    label: String
  ) -> some View {
    let isSelected = selection == mode
    return Button {
      guard !isSelected else { return }
      OmiMotion.withGated(.easeOut(duration: InkMotion.checkbox)) {
        selection = mode
      }
    } label: {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
        .lineLimit(1)
        .frame(maxWidth: .infinity)
        .padding(.horizontal, OmiSpacing.xs)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
            .fill(isSelected ? Ink.surface : Color.clear)
        )
        .contentShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(isSelected ? .isSelected : [])
    .accessibilityLabel(label)
  }
}

/// The app's mute for its own interface sounds.
///
/// Its own view, and not another `@State` on `SettingsContentView`, because the value it edits does
/// not live in this pane: `OmiUISound.isEnabled` is persisted by the sound controller, so the row
/// only needs somewhere local to hold the last read for SwiftUI to diff against.
///
/// Deliberately separate from macOS's "Play user interface sound effects": that switch governs the
/// swooshes, and this one governs everything Omi plays, including the completion chimes the system
/// switch has no say over.
private struct InterfaceSoundsRow: View {
  @State private var isEnabled = OmiUISound.isEnabled

  var body: some View {
    HStack(spacing: OmiSpacing.lg) {
      SettingsIconTile(symbol: "speaker.wave.2")

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Interface Sounds")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text("Sounds for important arrivals and completions.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
      }

      Spacer()

      Toggle(
        "",
        isOn: Binding(
          get: { isEnabled },
          set: { newValue in
            isEnabled = newValue
            OmiUISound.isEnabled = newValue
          }
        )
      )
      .toggleStyle(OmiToggleStyle())
      .labelsHidden()
      .frame(width: 36, height: 20)
    }
  }

}
