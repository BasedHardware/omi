import OmiTheme
import SwiftUI

struct AssistantVoicePicker: View {
  @ObservedObject var store: AssistantVoiceStore

  var onPreview: (String) async throws -> Void = { voiceID in
    try await FloatingBarVoicePlaybackService.shared.playVoiceSample(voiceID: voiceID)
  }
  var onStopPreview: () -> Void = { FloatingBarVoicePlaybackService.shared.stopVoiceSample() }

  private var voices: [AssistantVoiceEntry] {
    store.catalog.isEmpty
      ? [AssistantVoiceEntry(id: AssistantVoiceStore.defaultVoiceID, name: AssistantVoiceStore.defaultVoiceID)]
      : store.catalog
  }

  @State private var previewBusy = false
  @State private var previewFailed = false

  private var selection: Binding<String> {
    Binding(
      get: { store.selectedVoiceID },
      set: { voiceID in
        guard voiceID != store.selectedVoiceID, !store.isSaving else { return }
        Task { await store.save(voiceID: voiceID) }
      })
  }

  private var selectedVoiceName: String {
    voices.first(where: { $0.id == store.selectedVoiceID })?.name ?? store.selectedVoiceID
  }

  private func runPreview() {
    guard !previewBusy else { return }
    previewBusy = true
    previewFailed = false
    let voiceID = store.selectedVoiceID
    Task {
      do {
        try await onPreview(voiceID)
      } catch {
        previewFailed = true
      }
      previewBusy = false
    }
  }

  var body: some View {
    HStack(spacing: OmiSpacing.lg) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Voice")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(
          store.lastError != nil
            ? "Couldn't reach the voice service — your previous choice stays active."
            : previewFailed
              ? "Couldn't play the preview — try again."
              : "Your voice choice is shared across desktop and mobile."
        )
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
      }
      Spacer()
      if store.isLoading || store.isSaving || previewBusy {
        ProgressView()
          .controlSize(.small)
      }
      if store.lastError != nil || previewFailed {
        Button("Try Again") {
          if previewFailed {
            runPreview()
          } else {
            Task { await store.refresh() }
          }
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      }
      OmiIconButton("play.fill", help: "Preview \(selectedVoiceName)", size: .compact) {
        runPreview()
      }
      .disabled(previewBusy || store.isSaving || VoiceTurnCoordinator.shared.activeTurnID != nil)
      SettingsMenuPicker(selection: selection) {
        ForEach(voices, id: \.id) { voice in
          Text(voice.name).tag(voice.id)
        }
      }
      .disabled(store.isSaving || store.isLoading)
    }
    .onAppear {
      Task { await store.refresh() }
    }
    .onDisappear {
      onStopPreview()
    }
  }
}

extension SettingsContentView {
  func assistantVoicePicker(settingId: String) -> some View {
    settingsCard(settingId: settingId) {
      AssistantVoicePicker(store: .shared)
    }
  }
}
