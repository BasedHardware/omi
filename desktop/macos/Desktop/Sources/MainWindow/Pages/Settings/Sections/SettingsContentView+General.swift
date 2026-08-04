import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  /// Listening controls only — capture toggles live here so Rewind/Transcription
  /// stay focused on history and speech quality rather than on/off power switches.
  var generalSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      Text(
        "Control what Omi captures while you work. Fine-tune screen history in Rewind and speech quality in Transcription."
      )
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textTertiary)
      .frame(maxWidth: .infinity, alignment: .leading)
      .fixedSize(horizontal: false, vertical: true)

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
    }
  }

}
