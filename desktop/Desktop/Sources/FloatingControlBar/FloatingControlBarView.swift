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
        .floatingBackground()
    }

    private var controlBarView: some View {
        HStack(spacing: 12) {
            Spacer()

            recordingStatusView

            Spacer().frame(width: 4)

            commandButton(title: "Ask omi", keys: ["\u{2318}", "\u{21A9}\u{FE0E}"]) {
                onAskAI()
            }

            Spacer().frame(width: 4)

            commandButton(title: "Show/Hide", keys: ["\u{2318}", "\\"]) {
                onHide()
            }

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(height: 60)
        .background(DraggableAreaView(targetWindow: window))
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
                let totalHeight = 60 + height + 24 + (state.screenshotURL != nil ? 60 : 0)
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

    private var recordingStatusView: some View {
        HStack(spacing: 8) {
            Button(action: onPlayPause) {
                if state.isInitialising {
                    FloatingLoadingSpinner()
                        .frame(width: 24, height: 24)
                        .frame(width: 28, height: 28)
                        .background(Color.white)
                        .clipShape(Circle())
                } else {
                    Image(systemName: state.isRecording ? "pause.fill" : "play.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.black)
                        .frame(width: 28, height: 28)
                        .background(Color.white)
                        .clipShape(Circle())
                        .scaleEffect(state.isRecording ? 1.0 : 0.9)
                        .animation(
                            .spring(response: 0.3, dampingFraction: 0.6), value: state.isRecording
                        )
                }
            }
            .buttonStyle(.plain)

            if state.isRecording {
                Text(formattedDuration)
                    .font(.system(size: 14).monospacedDigit())
                    .foregroundColor(.white)
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
                    .animation(.spring(response: 0.3, dampingFraction: 0.7), value: state.duration)
            }
        }
    }

    private func commandButton(title: String, keys: [String], action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.white)
                ForEach(keys, id: \.self) { key in
                    Text(key)
                        .font(.system(size: 11))
                        .foregroundColor(.white)
                        .frame(width: 20, height: 20)
                        .background(Color.white.opacity(0.1))
                        .cornerRadius(4)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var formattedDuration: String {
        String(format: "%02d:%02d", state.duration / 60, state.duration % 60)
    }
}
