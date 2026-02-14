import SwiftUI

/// Recording header showing status, timer, and audio levels
struct RecordingHeaderView: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var audioLevels = AudioLevelMonitor.shared
    @ObservedObject private var recordingTimer = RecordingTimer.shared

    /// Pulsing animation state
    @State private var isPulsing = false

    /// Finish button state
    @State private var isFinishing = false
    @State private var showSavedSuccess = false
    @State private var showDiscarded = false
    @State private var showError = false

    /// Which action the user prefers (persisted)
    @AppStorage("recordingButtonMode") private var buttonMode: String = "finish"

    /// Format duration as HH:MM:SS
    private var formattedDuration: String {
        recordingTimer.formattedDuration
    }

    private var isFinishMode: Bool { buttonMode == "finish" }

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
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Text(formattedDuration)
                    .scaledFont(size: 14, weight: .medium, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)

                // Split button: main action + dropdown chevron
                HStack(spacing: 0) {
                    // Main action button
                    Button(action: {
                        if isFinishMode {
                            handleFinish()
                        } else {
                            appState.stopTranscription()
                        }
                    }) {
                        HStack(spacing: 6) {
                            if isFinishing {
                                ProgressView()
                                    .scaleEffect(0.5)
                                    .frame(width: 12, height: 12)
                            } else if showSavedSuccess {
                                Image(systemName: "checkmark")
                                    .scaledFont(size: 12, weight: .bold)
                            } else if showDiscarded {
                                Image(systemName: "xmark")
                                    .scaledFont(size: 12, weight: .bold)
                            } else if showError {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .scaledFont(size: 12)
                            } else {
                                Image(systemName: isFinishMode ? "checkmark.circle.fill" : "stop.circle.fill")
                                    .scaledFont(size: 12)
                            }
                            Text(finishButtonText)
                                .scaledFont(size: 13, weight: .medium)
                        }
                        .foregroundColor(.white)
                        .padding(.leading, 14)
                        .padding(.trailing, 8)
                        .padding(.vertical, 8)
                    }
                    .buttonStyle(.plain)
                    .disabled(isFinishing || showSavedSuccess || showDiscarded || showError)

                    // Divider line
                    Rectangle()
                        .fill(Color.white.opacity(0.3))
                        .frame(width: 1, height: 20)

                    // Dropdown chevron
                    Menu {
                        Button(action: {
                            buttonMode = "finish"
                        }) {
                            HStack {
                                Text("Finish")
                                if buttonMode == "finish" {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                        Button(action: {
                            buttonMode = "stop"
                        }) {
                            HStack {
                                Text("Stop Recording")
                                if buttonMode == "stop" {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    } label: {
                        Image(systemName: "chevron.down")
                            .scaledFont(size: 9, weight: .bold)
                            .foregroundColor(.white)
                            .padding(.leading, 8)
                            .padding(.trailing, 10)
                            .padding(.vertical, 8)
                    }
                    .menuStyle(.borderlessButton)
                    .fixedSize()
                }
                .background(
                    Capsule()
                        .fill(finishButtonColor)
                )
            }

            // Audio level meters
            HStack(spacing: 32) {
                // Microphone level
                HStack(spacing: 8) {
                    Image(systemName: "mic.fill")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)

                    AudioLevelWaveformView(
                        level: audioLevels.microphoneLevel,
                        isActive: appState.isTranscribing
                    )

                    Text("Mic")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }

                // System audio level
                HStack(spacing: 8) {
                    Image(systemName: "speaker.wave.2.fill")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)

                    AudioLevelWaveformView(
                        level: audioLevels.systemLevel,
                        isActive: appState.isTranscribing
                    )

                    Text("System Audio")
                        .scaledFont(size: 12)
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

    // MARK: - Finish Button

    private var finishButtonText: String {
        if isFinishing { return "Saving..." }
        if showSavedSuccess { return "Saved!" }
        if showDiscarded { return "Too Short" }
        if showError { return "Failed" }
        return isFinishMode ? "Finish" : "Stop Recording"
    }

    private var finishButtonColor: Color {
        if isFinishing { return OmiColors.textTertiary }
        if showSavedSuccess { return OmiColors.success }
        if showDiscarded { return OmiColors.warning }
        if showError { return OmiColors.error }
        return OmiColors.purplePrimary
    }

    private func handleFinish() {
        guard !isFinishing else { return }
        isFinishing = true
        Task {
            let result = await appState.finishConversation()
            isFinishing = false
            switch result {
            case .saved:
                withAnimation(.easeInOut(duration: 0.3)) {
                    showSavedSuccess = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
                    showSavedSuccess = false
                }
            case .discarded:
                withAnimation(.easeInOut(duration: 0.3)) {
                    showDiscarded = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
                    showDiscarded = false
                }
            case .error:
                withAnimation(.easeInOut(duration: 0.3)) {
                    showError = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
                    showError = false
                }
            }
        }
    }
}

#Preview {
    RecordingHeaderView(appState: AppState())
        .padding()
        .background(OmiColors.backgroundPrimary)
}
