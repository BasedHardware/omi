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
                        .strokeBorder(Color.black.opacity(0.5), lineWidth: 1)
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
        .clipped()
        .onHover { hovering in
            // Resize window BEFORE updating SwiftUI state on expand so the expanded
            // content never renders in a too-small window (which causes overflow).
            if hovering {
                (window as? FloatingControlBarWindow)?.resizeForHover(expanded: true)
            }
            withAnimation(.easeInOut(duration: 0.2)) {
                isHovering = hovering
            }
            if !hovering {
                (window as? FloatingControlBarWindow)?.resizeForHover(expanded: false)
            }
        }
        .background(DraggableAreaView(targetWindow: window))
        .floatingBackground(cornerRadius: isHovering || state.showingAIConversation || state.isVoiceListening ? 20 : 5)
    }

    private func openFloatingBarSettings() {
        // Bring main window to front and navigate to floating bar settings
        NSApp.activate(ignoringOtherApps: true)
        for window in NSApp.windows where window.title.hasPrefix("Omi") {
            window.makeKeyAndOrderFront(nil)
            break
        }
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
    }

    /// Minimal thin bar shown when not hovering
    private var compactCircleView: some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(Color.white.opacity(0.5))
            .frame(width: 28, height: 4)
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
                    state.currentAIMessage = nil
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
            currentMessage: state.currentAIMessage,
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
                if let currentMessage = state.currentAIMessage, !currentQuery.isEmpty, !currentMessage.text.isEmpty {
                    state.chatHistory.append(FloatingChatExchange(question: currentQuery, aiMessage: currentMessage))
                }

                state.displayedQuery = message
                let screenshot = state.screenshotURL
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.isAILoading = true
                    state.currentAIMessage = nil
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
