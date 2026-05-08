import SwiftUI

/// Main floating control bar SwiftUI view composing all sub-views.
struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @ObservedObject private var shortcutSettings = ShortcutSettings.shared
    weak var window: NSWindow?
    var onPlayPause: () -> Void
    var onAskAI: () -> Void
    var onHide: () -> Void
    var onSendQuery: (String) -> Void
    var onCloseAI: () -> Void
    var onEscape: () -> Void
    var onClearVisibleConversation: () -> Void
    var onRate: ((String, Int?) -> Void)?
    var onShareLink: (() async -> String?)?

    @State private var isHovering = false
    private let conversationTransition = Animation.spring(response: 0.32, dampingFraction: 0.86)

    var body: some View {
        VStack(spacing: state.isShowingNotification && !state.showingAIConversation ? 8 : 0) {
            barChrome

            if let notification = state.currentNotification, !state.showingAIConversation {
                notificationView(notification)
                    .padding(.horizontal, 8)
                    .padding(.bottom, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .animation(.spring(response: 0.35, dampingFraction: 0.82), value: state.currentNotification?.id)
    }

    /// Whether the bar chrome should stretch to fill the window width
    private var barNeedsFullWidth: Bool {
        isHovering || state.showingAIConversation || state.isVoiceListening
    }

    private var barChrome: some View {
        VStack(spacing: 0) {
            // Main control bar - always visible
            controlBarView

            // AI conversation view - conditionally visible
            if state.showingAIConversation {
                conversationView
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(Color.black.opacity(0.5), lineWidth: 1)
                )
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .frame(maxWidth: barNeedsFullWidth ? .infinity : nil, alignment: .top)
        .animation(.spring(response: 0.3, dampingFraction: 0.85), value: state.showingAIConversation)
        .animation(conversationTransition, value: state.showingAIResponse)
        .overlay(alignment: .topLeading) {
            if state.showingAIConversation {
                Button {
                    onCloseAI()
                } label: {
                    ZStack {
                        Circle()
                            .strokeBorder(Color.white.opacity(0.2), lineWidth: 0.5)
                            .frame(width: 16, height: 16)

                        Image(systemName: "xmark")
                            .font(.system(size: 8))
                            .foregroundColor(.secondary)
                    }
                    .frame(width: 20, height: 20)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
                .padding(2)
                .transition(.opacity)
            }
        }
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
        .overlay(alignment: .bottomTrailing) {
            if state.showingAIConversation {
                ZStack {
                    ResizeHandleView(targetWindow: window)
                        .frame(width: 20, height: 20)
                    ResizeGripShape()
                        .foregroundStyle(.white.opacity(0.3))
                        .frame(width: 14, height: 14)
                        .allowsHitTesting(false)
                }
                .padding(4)
            }
        }
        .clipped()
        .background(DraggableAreaView(targetWindow: window))
        .floatingBackground(cornerRadius: barNeedsFullWidth ? 20 : 5)
        .contextMenu {
            barContextMenu
        }
        .onHover(perform: handleBarHover)
    }

    @ViewBuilder
    private var barContextMenu: some View {
        Button("Disable for 2 hours") {
            FloatingControlBarManager.shared.snooze(
                for: FloatingControlBarManager.snoozeTwoHoursDuration
            )
        }
    }

    private var conversationView: some View {
        ZStack(alignment: .top) {
            if state.showingAIResponse {
                aiResponseView
                    .id("response")
                    .zIndex(1)
            } else {
                aiInputView
                    .id("input")
                    .zIndex(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private func handleBarHover(_ hovering: Bool) {
        if !hovering {
            state.requiresHoverReset = false
        }

        let effectiveHover = hovering && !state.requiresHoverReset
        state.isHoveringBar = effectiveHover
        // Resize window BEFORE updating SwiftUI state on expand so the expanded
        // content never renders in a too-small window (which causes overflow).
        if effectiveHover {
            (window as? FloatingControlBarWindow)?.resizeForHover(expanded: true)
        }
        withAnimation(.easeInOut(duration: 0.2)) {
            isHovering = effectiveHover
        }
        if !effectiveHover {
            (window as? FloatingControlBarWindow)?.resizeForHover(expanded: false)
        }
    }

    private func notificationView(_ notification: FloatingBarNotification) -> some View {
        // The entire card opens the chat. A SwiftUI Button only hit-tests its
        // visible content, so the previous layout left the padding and spacer
        // as dead zones — users reported clicks landing "on the box" doing
        // nothing. Wrapping the whole card in a single Button with
        // contentShape(Rectangle()) makes every pixel clickable. The dismiss
        // (X) button sits in an overlay on top so it keeps its own hit region.
        Button {
            FloatingControlBarManager.shared.openNotificationAsChat(notification)
        } label: {
            HStack(alignment: .top, spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.white.opacity(0.08))
                        .frame(width: 34, height: 34)

                    Image(systemName: "bell.badge.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(notification.title)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundColor(.white)
                        .lineLimit(1)

                    Text(notification.message)
                        .scaledFont(size: 12)
                        .foregroundColor(.white.opacity(0.72))
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                // Reserve space so text never runs under the overlaid action buttons.
                Color.clear.frame(width: 90, height: 18)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .topTrailing) {
            HStack(spacing: 6) {
                // Spawn an agent pill that handles whatever the notification is
                // about — reuses the same parallel-pill bridge flow.
                Button {
                    let model = ShortcutSettings.shared.selectedModel.isEmpty
                        ? "claude-sonnet-4-6"
                        : ShortcutSettings.shared.selectedModel
                    let query = "Handle this notification: \(notification.title). \(notification.message)"
                    AgentPillsManager.shared.spawn(query: query, model: model)
                    FloatingControlBarManager.shared.dismissCurrentNotification()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 9, weight: .bold))
                        Text("Execute")
                            .scaledFont(size: 10, weight: .semibold)
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.18))
                    .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                .help("Spawn an agent to handle this")

                Button {
                    FloatingControlBarManager.shared.dismissCurrentNotification()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.white.opacity(0.62))
                        .frame(width: 18, height: 18)
                        .background(Color.white.opacity(0.08))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
        }
        .floatingBackground(cornerRadius: 18)
    }

    private func openFloatingBarSettings() {
        // Bring main window to front and navigate to floating bar settings
        NSApp.activate()
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
                    compactButton(title: "Ask omi / Collapse", keys: shortcutSettings.askOmiShortcut.displayTokens) {
                        onAskAI()
                    }

                    HStack(spacing: 6) {
                        compactLabel("Push to talk", keys: shortcutSettings.pttShortcut.displayTokens)
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
        RoundedRectangle(cornerRadius: 3)
            .fill(Color.white.opacity(0.5))
            .frame(width: 28, height: 6)
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
                    .padding(.horizontal, key.count > 1 ? 4 : 0)
                    .frame(minWidth: 15, minHeight: 15)
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
                Text(
                    state.isVoiceLocked
                        ? "Tap \(shortcutSettings.pttShortcut.displayLabel) to send"
                        : "Release \(shortcutSettings.pttShortcut.displayLabel) to send"
                )
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
            canClearVisibleConversation: state.hasVisibleConversation,
            onSend: { message in
                state.displayedQuery = message
                state.markConversationActivity()
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.showingAIResponse = true
                    state.isAILoading = true
                    state.currentAIMessage = nil
                }
                onSendQuery(message)
            },
            onClearVisibleConversation: onClearVisibleConversation,
            onEscape: onEscape,
            onHeightChange: { [weak state] height in
                guard let state = state else { return }
                let totalHeight = 50 + height + 24
                state.inputViewHeight = totalHeight
            }
        )
        .transition(
            .asymmetric(
                insertion: .move(edge: .top).combined(with: .opacity),
                removal: .move(edge: .top).combined(with: .opacity)
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
            canClearVisibleConversation: state.hasVisibleConversation,
            onClearVisibleConversation: onClearVisibleConversation,
            onEscape: onEscape,
            onSendFollowUp: { message in
                archiveCurrentExchange()

                state.displayedQuery = message
                state.currentQuestionMessageId = nil
                state.markConversationActivity()
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.isAILoading = true
                    state.currentAIMessage = nil
                }
                onSendQuery(message)
            },
            onRate: onRate,
            onShareLink: onShareLink
        )
        .transition(
            .asymmetric(
                insertion: .move(edge: .bottom).combined(with: .opacity),
                removal: .move(edge: .bottom).combined(with: .opacity)
            ))
    }

    private func archiveCurrentExchange() {
        guard let currentMessage = state.currentAIMessage else { return }
        guard !currentMessage.text.isEmpty || !currentMessage.contentBlocks.isEmpty else { return }

        let currentQuery = state.displayedQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        state.chatHistory.append(
            FloatingChatExchange(
                question: currentQuery.isEmpty ? nil : currentQuery,
                questionMessageId: state.currentQuestionMessageId,
                aiMessage: currentMessage
            )
        )
    }

}
