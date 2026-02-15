import SwiftUI

/// Main floating control bar SwiftUI view composing all sub-views.
struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState
    weak var window: NSWindow?
    var onPlayPause: () -> Void
    var onAskAI: () -> Void
    var onHide: () -> Void
    var onSendQuery: (String, URL?) -> Void
    var onCloseAI: () -> Void
    var onAskFollowUp: () -> Void
    var onCaptureScreenshot: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Main control bar - always visible
            controlBarView

            // AI conversation view - conditionally visible
            if state.showingAIConversation {
                Group {
                    if state.showingAIResponse {
                        aiResponseView
                    } else {
                        aiInputView
                    }
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(Color.white.opacity(0.2), lineWidth: 1)
                )
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DraggableAreaView(targetWindow: window))
        .floatingBackground()
    }

    private var controlBarView: some View {
        VStack(spacing: 1) {
            if state.isVoiceListening {
                voiceListeningView
            } else {
                compactButton(title: "Ask omi", keys: ["\u{2318}", "\u{21A9}\u{FE0E}"]) {
                    onAskAI()
                }
            }

            HStack(spacing: 6) {
                compactLabel("Hide", keys: ["\u{2318}", "\\"])
                compactLabel("Push to talk", keys: ["\u{2325}"])
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .frame(height: 50)
    }

    private func compactButton(title: String, keys: [String], action: @escaping () -> Void) -> some View {
        Button(action: action) {
            compactLabel(title, keys: keys)
        }
        .buttonStyle(.plain)
    }

    private func compactLabel(_ title: String, keys: [String]) -> some View {
        HStack(spacing: 3) {
            Text(title)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(.white)
            ForEach(keys, id: \.self) { key in
                Text(key)
                    .scaledFont(size: 9)
                    .foregroundColor(.white)
                    .frame(width: 15, height: 15)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(3)
            }
        }
    }

    private var voiceListeningView: some View {
        HStack(spacing: 8) {
            // Pulsing mic icon
            Circle()
                .fill(Color.red)
                .frame(width: 10, height: 10)
                .scaleEffect(state.isVoiceListening ? 1.2 : 1.0)
                .animation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true), value: state.isVoiceListening)

            Image(systemName: "mic.fill")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(.white)

            if state.isVoiceLocked {
                Text("LOCKED")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundColor(.orange)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.orange.opacity(0.2))
                    .cornerRadius(4)
            }

            if !state.voiceTranscript.isEmpty {
                Text(state.voiceTranscript)
                    .scaledFont(size: 13)
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(1)
                    .truncationMode(.tail)
            } else {
                Text(state.isVoiceLocked ? "Tap \u{2325} to send" : "Release \u{2325} to send")
                    .scaledFont(size: 13)
                    .foregroundColor(.white.opacity(0.5))
            }
        }
    }

    private var aiInputView: some View {
        AskAIInputView(
            userInput: Binding(
                get: { state.aiInputText },
                set: { state.aiInputText = $0 }
            ),
            screenshotURL: Binding(
                get: { state.screenshotURL },
                set: { state.screenshotURL = $0 }
            ),
            onSend: { message in
                state.displayedQuery = message
                let screenshot = state.screenshotURL
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.showingAIResponse = true
                    state.isAILoading = true
                    state.aiResponseText = ""
                }
                onSendQuery(message, screenshot)
            },
            onCancel: onCloseAI,
            onHeightChange: { [weak state] height in
                guard let state = state else { return }
                let totalHeight = 50 + height + 24
                state.inputViewHeight = totalHeight
            },
            onCaptureScreenshot: onCaptureScreenshot
        )
        .transition(
            .asymmetric(
                insertion: .scale(scale: 0.95).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
    }

    private var aiResponseView: some View {
        AIResponseView(
            isLoading: Binding(
                get: { state.isAILoading },
                set: { state.isAILoading = $0 }
            ),
            responseText: Binding(
                get: { state.aiResponseText },
                set: { state.aiResponseText = $0 }
            ),
            userInput: state.displayedQuery,
            onClose: onCloseAI,
            onAskFollowUp: onAskFollowUp
        )
        .transition(
            .asymmetric(
                insertion: .scale(scale: 0.95).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
    }


}
