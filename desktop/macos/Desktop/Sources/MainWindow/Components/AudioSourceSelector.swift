import OmiTheme
import SwiftUI

/// Audio source selector for the macOS capture path.
struct AudioSourceSelector: View {
  @ObservedObject var appState: AppState

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      audioSourceButton(
        source: .microphone,
        isSelected: true,
        isAvailable: true
      )
    }
    .onAppear {
      guard appState.audioSource != .microphone else { return }
      appState.audioSource = .microphone
    }
  }

  private func audioSourceButton(
    source: AudioSource,
    isSelected: Bool,
    isAvailable: Bool
  ) -> some View {
    Button(action: {
      guard isAvailable && !appState.isTranscribing else { return }
      appState.audioSource = source
    }) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: source.iconName)
          .scaledFont(size: OmiType.body)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(source.displayName)
            .scaledFont(size: OmiType.body, weight: .medium)

          Text(AudioCaptureService.getCurrentMicrophoneName() ?? "Default")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
        }

        Spacer()

        if isSelected {
          Image(systemName: "checkmark.circle.fill")
            .foregroundColor(OmiColors.accent)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isSelected ? OmiColors.accent.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.5))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(isSelected ? OmiColors.accent : Color.clear, lineWidth: 1.5)
          )
      )
      .foregroundColor(isAvailable ? OmiColors.textPrimary : OmiColors.textTertiary)
      .opacity(isAvailable ? 1.0 : 0.5)
    }
    .buttonStyle(.plain)
    .disabled(!isAvailable || appState.isTranscribing)
  }
}

/// Compact audio source indicator for display in headers
struct AudioSourceIndicator: View {
  @ObservedObject var appState: AppState

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: AudioSource.microphone.iconName)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.accent)

      Text("Mic")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xxs)
    .background(
      Capsule()
        .fill(OmiColors.backgroundTertiary.opacity(0.5))
    )
  }
}

// MARK: - Preview

#if canImport(PreviewsMacros)
  #Preview("Audio Source Selector") {
    VStack(spacing: OmiSpacing.xl) {
      AudioSourceSelector(appState: AppState())
      AudioSourceIndicator(appState: AppState())
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
  }
#endif
