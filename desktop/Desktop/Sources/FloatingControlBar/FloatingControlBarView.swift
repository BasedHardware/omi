import SwiftUI

/// Main floating control bar SwiftUI view composing all sub-views.
struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @ObservedObject private var shortcutSettings = ShortcutSettings.shared
    weak var window: NSWindow?
    var onPlayPause: () -> Void
    var onAskAI: () -> Void
    var onHide: () -> Void
    var onSendQuery: (String, URL?) -> Void
    var onCloseAI: () -> Void

    @State private var isHovering = false

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
        .overlay(alignment: .topTrailing) {
            if isHovering && !state.isVoiceListening {
                Button {
                    openFloatingBarSettings()
                } label: {
                    Image(systemName: "gearshape.fill")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.7))
                        .frame(width: 22, height: 22)
                        .background(Color.white.opacity(0.12))
                        .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .padding(6)
                .transition(.opacity)
            }
        }
        .onHover { hovering in
            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                isHovering = hovering
            }
            // Drive window resize via state (only when bar is in compact mode)
            if !state.showingAIConversation && !state.isVoiceListening {
                state.isHoveringBar = hovering
            }
        }
        .background(DraggableAreaView(targetWindow: window))
        .floatingBackground(cornerRadius: isHovering || state.showingAIConversation || state.isVoiceListening ? 20 : 14)
    }

    private func openFloatingBarSettings() {
        // Bring main window to front and navigate to floating bar settings
        NSApp.activate(ignoringOtherApps: true)
        NotificationCenter.default.post(name: .navigateToFloatingBarSettings, object: nil)
    }

    private var controlBarView: some View {
        Group {
            if state.isVoiceListening && !state.isVoiceFollowUp {
                voiceListeningView
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .frame(height: 50)
                    .transition(.opacity)
            } else if isHovering || state.showingAIConversation {
                VStack(spacing: 1) {
                    compactButton(title: "Ask omi", keys: shortcutSettings.askOmiKey.hintKeys) {
                        onAskAI()
                    }

                    HStack(spacing: 6) {
                        compactLabel("Hide", keys: ["\u{2318}", "\\"])
                        compactLabel("Push to talk", keys: [shortcutSettings.pttKey.symbol])
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .frame(height: 50)
                .transition(.opacity)
            } else {
                compactCircleView
                    .transition(.opacity)
            }
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: isHovering)
    }

    /// Minimal circle shown when not hovering
    private var compactCircleView: some View {
        Image(systemName: "waveform")
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(.white.opacity(0.6))
            .frame(width: 28, height: 28)
    }

    private func compactToggle(_ title: String, isOn: Binding<Bool>) -> some View {
        Button(action: { isOn.wrappedValue.toggle() }) {
            HStack(spacing: 3) {
                Text(title)
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(.white)
                RoundedRectangle(cornerRadius: 6)
                    .fill(isOn.wrappedValue ? Color.white.opacity(0.3) : Color.white.opacity(0.1))
                    .frame(width: 26, height: 15)
                    .overlay(alignment: isOn.wrappedValue ? .trailing : .leading) {
                        Circle()
                            .fill(.white)
                            .frame(width: 11, height: 11)
                            .padding(2)
                    }
                    .animation(.easeInOut(duration: 0.15), value: isOn.wrappedValue)
            }
        }
        .buttonStyle(.plain)
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
                    .truncationMode(.head)
            } else {
                Text(state.isVoiceLocked ? "Tap \(shortcutSettings.pttKey.symbol) to send" : "Release \(shortcutSettings.pttKey.symbol) to send")
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
            }
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
            chatHistory: state.chatHistory,
            isVoiceFollowUp: Binding(
                get: { state.isVoiceFollowUp },
                set: { state.isVoiceFollowUp = $0 }
            ),
            voiceFollowUpTranscript: Binding(
                get: { state.voiceFollowUpTranscript },
                set: { state.voiceFollowUpTranscript = $0 }
            ),
            onClose: onCloseAI,
            onSendFollowUp: { message in
                // Archive current exchange to chat history
                let currentQuery = state.displayedQuery
                let currentResponse = state.aiResponseText
                if !currentQuery.isEmpty && !currentResponse.isEmpty {
                    state.chatHistory.append(ChatExchange(question: currentQuery, response: currentResponse))
                }

                state.displayedQuery = message
                let screenshot = state.screenshotURL
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.isAILoading = true
                    state.aiResponseText = ""
                }
                onSendQuery(message, screenshot)
            }
        )
        .transition(
            .asymmetric(
                insertion: .scale(scale: 0.95).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
    }


}
