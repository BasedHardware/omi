import SwiftUI

/// Recording header showing status, timer, and audio levels
struct RecordingHeaderView: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var audioLevels = AudioLevelMonitor.shared
    @ObservedObject private var recordingTimer = RecordingTimer.shared

    /// Pulsing animation state
    @State private var isPulsing = false

    /// Format duration as HH:MM:SS
    private var formattedDuration: String {
        recordingTimer.formattedDuration
    }

    var body: some View {
        VStack(spacing: 16) {
            // Recording status and timer
            HStack {
                // Pulsing listening indicator with glow
                ZStack {
                    // Glow effect
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.3))
                        .frame(width: 24, height: 24)
                        .scaleEffect(isPulsing ? 1.8 : 1.0)
                        .opacity(isPulsing ? 0.0 : 0.6)

                    // Main dot
                    Circle()
                        .fill(OmiColors.purplePrimary)
                        .frame(width: 12, height: 12)
                        .scaleEffect(isPulsing ? 1.3 : 1.0)
                }
                .animation(
                    .easeInOut(duration: 1.0)
                    .repeatForever(autoreverses: true),
                    value: isPulsing
                )

                Text("Listening")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Text(formattedDuration)
                    .font(.system(size: 14, weight: .medium, design: .monospaced))
                    .foregroundColor(OmiColors.textSecondary)

                // Stop recording button
                Button(action: {
                    appState.stopTranscription()
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: "stop.circle.fill")
                            .font(.system(size: 12))
                        Text("Stop Recording")
                            .font(.system(size: 13, weight: .medium))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(
                        Capsule()
                            .fill(OmiColors.purplePrimary)
                    )
                }
                .buttonStyle(.plain)
            }

            // Audio level meters
            HStack(spacing: 32) {
                // Microphone level
                HStack(spacing: 8) {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textTertiary)

                    AudioLevelWaveformView(
                        level: audioLevels.microphoneLevel,
                        isActive: appState.isTranscribing
                    )

                    Text("Mic")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)
                }

                // System audio level
                HStack(spacing: 8) {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textTertiary)

                    AudioLevelWaveformView(
                        level: audioLevels.systemLevel,
                        isActive: appState.isTranscribing
                    )

                    Text("System Audio")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary)
        )
        .onAppear {
            isPulsing = true
        }
    }
}

#Preview {
    RecordingHeaderView(appState: AppState())
        .padding()
        .background(OmiColors.backgroundPrimary)
}
