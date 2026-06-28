import SwiftUI

/// Audio source selector for the macOS capture path.
struct AudioSourceSelector: View {
    @ObservedObject var appState: AppState

    var body: some View {
        HStack(spacing: 12) {
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
            HStack(spacing: 8) {
                Image(systemName: source.iconName)
                    .scaledFont(size: 14)

                VStack(alignment: .leading, spacing: 2) {
                    Text(source.displayName)
                        .scaledFont(size: 13, weight: .medium)

                    Text(AudioCaptureService.getCurrentMicrophoneName() ?? "Default")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
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
        HStack(spacing: 6) {
            Image(systemName: AudioSource.microphone.iconName)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Mic")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }
}

// MARK: - Preview

#Preview("Audio Source Selector") {
    VStack(spacing: 20) {
        AudioSourceSelector(appState: AppState())
        AudioSourceIndicator(appState: AppState())
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
