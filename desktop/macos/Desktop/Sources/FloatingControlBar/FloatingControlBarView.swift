import AppKit
import SwiftUI

/// Main floating control bar SwiftUI view composing all sub-views.
struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @ObservedObject private var shortcutSettings = ShortcutSettings.shared
    @ObservedObject private var agentPills = AgentPillsManager.shared
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
    @State private var notchSettingsHoverReady = false
    @State private var notchHoverGeneration = 0
    private let conversationTransition = Animation.spring(response: 0.32, dampingFraction: 0.86)
    private var notchSideWidth: CGFloat {
        if agentPills.pills.isEmpty && !state.isVoiceListening {
            return FloatingControlBarWindow.notchCompactSideWidth
        }
        return FloatingControlBarWindow.notchActiveSideWidth
    }
    private var notchChromeWidth: CGFloat {
        FloatingControlBarWindow.notchHiddenCenterWidth + notchSideWidth * 2
    }
    private var notchChromeLayoutWidth: CGFloat {
        state.showingAIConversation
            ? max(notchChromeWidth, FloatingControlBarWindow.notchExpandedWidth)
            : notchChromeWidth
    }

    var body: some View {
        Group {
            if state.usesNotchIsland {
                notchModeBody
            } else {
                VStack(spacing: state.isShowingNotification && !state.showingAIConversation ? 8 : 0) {
                    barChrome

                    if let notification = state.currentNotification, !state.showingAIConversation {
                        notificationView(notification)
                            .padding(.horizontal, 8)
                            .padding(.bottom, 8)
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: state.usesNotchIsland ? .top : .center)
        .background(Color.clear)
        .animation(.spring(response: 0.35, dampingFraction: 0.82), value: state.currentNotification?.id)
    }

    /// Whether the bar chrome should stretch to fill the window width
    private var barNeedsFullWidth: Bool {
        isHovering || state.showingAIConversation || state.isVoiceListening
    }

    private var notchModeBody: some View {
        VStack(spacing: 0) {
            notchChrome

            if state.showingAIConversation {
                conversationView
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.10), lineWidth: 0.8)
                    )
                    .background(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(Color.white.opacity(0.025))
                    )
                    .padding(.horizontal, 12)
                    .padding(.top, 4)
                    .padding(.bottom, 9)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }

            if let notification = state.currentNotification, !state.showingAIConversation {
                notificationView(notification)
                    .padding(.horizontal, 10)
                    .padding(.bottom, 10)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .background(alignment: .top) {
            ZStack(alignment: .top) {
                if state.isVoiceResponseActive {
                    NotchResponseGlowView(
                        bottomRadius: state.showingAIConversation || state.currentNotification != nil ? 22 : 18
                    )
                }

                if state.showingAIConversation || state.currentNotification != nil {
                    NotchDockShape(bottomRadius: 22)
                        .fill(Color.black)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    NotchDockShape(bottomRadius: 18)
                        .fill(Color.black)
                        .frame(height: notchChromeHeight)
                }
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
        .scaleEffect(
            x: max(0.001, state.notchRevealProgress),
            y: max(0.001, state.notchRevealProgress),
            anchor: .top
        )
        .opacity(min(1, max(0, state.notchRevealProgress * 1.4)))
        .contextMenu { barContextMenu }
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: state.showingAIConversation)
    }

    private var notchChrome: some View {
        ZStack {
            HStack(spacing: 0) {
                notchAgentLobe
                    .frame(width: notchSideWidth, height: notchChromeHeight)

                Spacer(minLength: FloatingControlBarWindow.notchHiddenCenterWidth)

                notchControlLobe
                    .frame(width: notchSideWidth, height: notchChromeHeight)
            }

            Color.clear
                .frame(width: FloatingControlBarWindow.notchHiddenCenterWidth, height: notchChromeHeight)
                .allowsHitTesting(false)
        }
        .frame(width: notchChromeLayoutWidth, height: notchChromeHeight)
    }

    private var notchAgentLobe: some View {
        HStack(spacing: 0) {
            if agentPills.pills.isEmpty {
                Color.clear
                    .allowsHitTesting(false)
            } else {
                NotchAgentPillsRowView(manager: agentPills, barWindow: window)
                    .frame(width: notchSideWidth - 12, height: notchChromeHeight, alignment: .trailing)
                    .padding(.leading, 6)
                    .padding(.trailing, 6)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
    }

    private var notchControlLobe: some View {
        HStack(spacing: 10) {
            Button {
                if notchSettingsHoverReady && !state.isVoiceListening {
                    openFloatingBarSettings()
                } else {
                    onAskAI()
                }
            } label: {
                ZStack {
                    if state.isVoiceListening && !state.isVoiceFollowUp {
                        HStack(spacing: 4) {
                            VoiceWaveformBars(isActive: true)
                                .scaleEffect(0.76)
                                .frame(width: 26, height: 15)
                            Image(systemName: "mic.fill")
                                .scaledFont(size: 10, weight: .semibold)
                                .foregroundColor(.white)
                        }
                    } else {
                        ZStack {
                            notchOmiLogo
                                .opacity(notchSettingsHoverReady ? 0 : 1)
                                .scaleEffect(notchSettingsHoverReady ? 0.78 : 1)
                                .rotationEffect(.degrees(notchSettingsHoverReady ? -35 : 0))

                            Image(systemName: "gearshape.fill")
                                .scaledFont(size: 15, weight: .semibold)
                                .foregroundColor(.white.opacity(0.86))
                                .opacity(notchSettingsHoverReady ? 1 : 0)
                                .scaleEffect(notchSettingsHoverReady ? 1 : 0.55)
                                .rotationEffect(.degrees(notchSettingsHoverReady ? 0 : 70))
                        }
                        .frame(width: 22, height: 22)
                        .shadow(
                            color: state.isVoiceResponseActive ? OmiColors.purpleAccent.opacity(0.85) : .clear,
                            radius: 10
                        )
                    }
                }
                .frame(width: state.isVoiceListening ? 58 : 40, height: 27)
            }
            .buttonStyle(.plain)
            .help(state.isVoiceListening ? "Listening" : (notchSettingsHoverReady ? "Floating Bar Settings" : "Ask Omi"))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
        .padding(.trailing, 6)
        .onHover { hovering in
            notchHoverGeneration += 1
            let generation = notchHoverGeneration
            withAnimation(.easeInOut(duration: 0.16)) {
                isHovering = hovering
                if !hovering {
                    notchSettingsHoverReady = false
                }
            }
            if hovering {
                scheduleNotchSettingsHoverReady(generation: generation)
            }
        }
        .onChange(of: state.isVoiceListening) { _, isListening in
            guard !isListening, isHovering else { return }
            notchHoverGeneration += 1
            scheduleNotchSettingsHoverReady(generation: notchHoverGeneration)
        }
    }

    private func scheduleNotchSettingsHoverReady(generation: Int) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.22) {
            guard generation == notchHoverGeneration,
                  isHovering,
                  !state.isVoiceListening
            else {
                return
            }
            withAnimation(.easeInOut(duration: 0.16)) {
                notchSettingsHoverReady = true
            }
        }
    }

    private var notchChromeHeight: CGFloat {
        FloatingControlBarWindow.notchChromeHeight
    }

    private var notchOmiLogo: some View {
        NotchOmiMark()
            .frame(width: 18.5, height: 18.5)
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
                // Wider for actionable (task) notifications that also show Execute.
                Color.clear
                    .frame(width: notification.assistantId == "task" ? 90 : 36, height: 18)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .topTrailing) {
            HStack(spacing: 6) {
                // Execute is only meaningful for actionable notifications (tasks).
                // Focus / Insight (tips) / other passive notifications are
                // informational — spawning an agent there made no sense.
                if notification.assistantId == "task" {
                    Button {
                        let model = ShortcutSettings.shared.selectedModel.isEmpty
                            ? ModelQoS.Claude.defaultSelection
                            : ShortcutSettings.shared.selectedModel
                        let query = ProactiveTaskExecute.buildQuery(
                            title: notification.title,
                            message: notification.message
                        )
                        _ = AgentPillsManager.shared.spawn(
                            query: query,
                            model: model,
                            systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix
                        )
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
                }

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
        activateMainAppWindow()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
            NotificationCenter.default.post(name: .navigateToFloatingBarSettings, object: nil)
        }
    }

    private func activateMainAppWindow() {
        NSApp.activate()

        if !revealMainAppWindow() {
            AppDelegate.openMainWindow?()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                NSApp.activate()
                _ = revealMainAppWindow()
            }
        }
    }

    @discardableResult
    private func revealMainAppWindow() -> Bool {
        guard let window = NSApp.windows.first(where: { window in
            let isRealAppWindow = !(window is NSPanel)
                && window.frame.width > 300
                && window.frame.height > 200
            let isMenuBarPopover = window.title.hasPrefix("Item-")
            return isRealAppWindow && !isMenuBarPopover && !window.isMiniaturized
        }) ?? NSApp.windows.first(where: { window in
            let isRealAppWindow = !(window is NSPanel)
                && window.frame.width > 300
                && window.frame.height > 200
            let isMenuBarPopover = window.title.hasPrefix("Item-")
            return isRealAppWindow && !isMenuBarPopover
        }) else {
            return false
        }

        window.deminiaturize(nil)
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        return true
    }

    private var controlBarView: some View {
        let allowsHoverExpansion = isHovering && !state.isVoiceResponseActive
        return Group {
            if state.isVoiceListening && !state.isVoiceFollowUp {
                voiceListeningView
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .frame(height: 42)
                    .transition(.opacity)
            } else if allowsHoverExpansion || state.showingAIConversation {
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
            .fill(compactPillFill)
            .frame(width: 28, height: 6)
            .shadow(
                color: state.isVoiceResponseActive ? OmiColors.purpleAccent.opacity(0.95) : .clear,
                radius: state.isVoiceResponseActive ? 16 : 0,
                x: 0,
                y: 0
            )
            .shadow(
                color: state.isVoiceResponseActive ? OmiColors.purplePrimary.opacity(0.72) : .clear,
                radius: state.isVoiceResponseActive ? 28 : 0,
                x: 0,
                y: 0
            )
            .overlay {
                if state.isVoiceResponseActive {
                    RoundedRectangle(cornerRadius: 3)
                        .stroke(
                            LinearGradient(
                                colors: [
                                    OmiColors.purpleAccent,
                                    Color(red: 0.25, green: 0.75, blue: 1.0),
                                    OmiColors.purplePrimary
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            ),
                            lineWidth: 1.4
                        )
                        .padding(-2.2)
                        .blur(radius: 0.25)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: state.isVoiceResponseActive)
    }

    private var compactPillFill: LinearGradient {
        if state.isVoiceResponseActive {
            return LinearGradient(
                colors: [
                    OmiColors.purpleAccent,
                    Color(red: 0.50, green: 0.33, blue: 1.0),
                    OmiColors.purplePrimary
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
        }
        return LinearGradient(
            colors: [Color.white.opacity(0.5), Color.white.opacity(0.5)],
            startPoint: .leading,
            endPoint: .trailing
        )
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
        HStack(spacing: 7) {
            // Playful realtime mic waveform (replaces the old pulsing red dot)
            VoiceWaveformBars(isActive: state.isVoiceListening)

            Image(systemName: "mic.fill")
                .scaledFont(size: 12, weight: .semibold)
                .foregroundColor(.white)

            if state.isVoiceLocked {
                Image(systemName: "lock.fill")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundColor(.orange)
                    .frame(width: 18, height: 18)
                    .background(Color.orange.opacity(0.2))
                    .cornerRadius(4)
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
                let totalHeight = state.usesNotchIsland
                    ? notchChromeHeight + height + FloatingControlBarWindow.notchInputPanelVerticalPadding
                    : 50 + height + 24
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

private struct NotchDockShape: Shape {
    let bottomRadius: CGFloat

    func path(in rect: CGRect) -> Path {
        let radius = min(bottomRadius, rect.height / 2)
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - radius))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX - radius, y: rect.maxY),
            control: CGPoint(x: rect.maxX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.minX + radius, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.minX, y: rect.maxY - radius),
            control: CGPoint(x: rect.minX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        path.closeSubpath()
        return path
    }
}

private struct NotchLowerEdgeShape: Shape {
    let bottomRadius: CGFloat

    func path(in rect: CGRect) -> Path {
        let radius = min(bottomRadius, rect.height / 2)
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY + 1))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY - radius))
        path.addQuadCurve(
            to: CGPoint(x: rect.minX + radius, y: rect.maxY),
            control: CGPoint(x: rect.minX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.maxX - radius, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: rect.maxY - radius),
            control: CGPoint(x: rect.maxX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + 1))
        return path
    }
}

private struct NotchResponseGlowView: View {
    let bottomRadius: CGFloat

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            let phase = time.truncatingRemainder(dividingBy: 2.4) / 2.4
            let sweepStart = UnitPoint(x: -0.35 + phase * 1.7, y: 0.0)
            let sweepEnd = UnitPoint(x: 0.35 + phase * 1.7, y: 1.0)
            let edge = NotchLowerEdgeShape(bottomRadius: bottomRadius)

            ZStack {
                edge
                    .stroke(
                        LinearGradient(
                            colors: [
                                Color(red: 0.45, green: 0.18, blue: 1.0).opacity(1.0),
                                Color(red: 0.88, green: 0.22, blue: 1.0).opacity(1.0),
                                Color(red: 0.22, green: 0.72, blue: 1.0).opacity(1.0),
                                Color(red: 0.72, green: 0.16, blue: 1.0).opacity(1.0)
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        ),
                        style: StrokeStyle(lineWidth: 3.2, lineCap: .round, lineJoin: .round)
                    )

                edge
                    .stroke(
                        LinearGradient(
                            stops: [
                                .init(color: .clear, location: 0.0),
                                .init(color: OmiColors.purpleAccent.opacity(0.55), location: 0.28),
                                .init(color: Color(red: 0.22, green: 0.88, blue: 1.0).opacity(1.0), location: 0.45),
                                .init(color: .white.opacity(1.0), location: 0.53),
                                .init(color: Color(red: 1.0, green: 0.34, blue: 0.95).opacity(0.95), location: 0.70),
                                .init(color: .clear, location: 1.0)
                            ],
                            startPoint: sweepStart,
                            endPoint: sweepEnd
                        ),
                        style: StrokeStyle(lineWidth: 4.8, lineCap: .round, lineJoin: .round)
                    )
            }
            .animation(.linear(duration: 0.12), value: phase)
        }
        .allowsHitTesting(false)
    }
}

private struct NotchOmiMark: View {
    private struct Dot: Identifiable {
        let id: Int
        let x: CGFloat
        let y: CGFloat
        let radius: CGFloat
    }

    private static let viewBox = CGRect(x: 237.360, y: 237.338, width: 549.318, height: 549.322)
    private static let dots: [Dot] = [
        Dot(id: 0, x: 282.523, y: 511.982, radius: 45.163),
        Dot(id: 1, x: 339.909, y: 339.890, radius: 45.107),
        Dot(id: 2, x: 512.014, y: 282.495, radius: 45.156),
        Dot(id: 3, x: 684.096, y: 339.880, radius: 45.103),
        Dot(id: 4, x: 741.511, y: 512.003, radius: 45.167),
        Dot(id: 5, x: 684.096, y: 684.094, radius: 45.103),
        Dot(id: 6, x: 511.981, y: 741.500, radius: 45.160),
        Dot(id: 7, x: 339.902, y: 684.107, radius: 45.103)
    ]

    var body: some View {
        GeometryReader { geometry in
            let size = min(geometry.size.width, geometry.size.height)
            let origin = CGPoint(
                x: (geometry.size.width - size) / 2,
                y: (geometry.size.height - size) / 2
            )

            ZStack {
                ForEach(Self.dots) { dot in
                    let x = origin.x + ((dot.x - Self.viewBox.minX) / Self.viewBox.width) * size
                    let y = origin.y + ((dot.y - Self.viewBox.minY) / Self.viewBox.height) * size
                    let radius = (dot.radius / Self.viewBox.width) * size
                    Circle()
                        .fill(Color.white.opacity(0.96))
                        .frame(width: radius * 2, height: radius * 2)
                        .position(x: x, y: y)
                }
            }
        }
        .drawingGroup(opaque: false, colorMode: .linear)
        .accessibilityHidden(true)
    }
}

private struct NotchAgentPillsRowView: View {
    @ObservedObject var manager: AgentPillsManager
    weak var barWindow: NSWindow?

    private var pillsNewestFirst: [AgentPill] {
        Array(manager.pills.reversed())
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(pillsNewestFirst) { pill in
                    NotchAgentPillIcon(pill: pill, manager: manager, barWindow: barWindow)
                }
            }
            .frame(maxHeight: .infinity, alignment: .center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
        .accessibilityLabel("Agent pills")
        .accessibilityHint("Scroll horizontally to reach older agents")
    }
}

private struct NotchAgentPillIcon: View {
    @ObservedObject var pill: AgentPill
    @ObservedObject var manager: AgentPillsManager
    weak var barWindow: NSWindow?

    var body: some View {
        Button {
            if manager.hoveredPillID == pill.id {
                manager.hoveredPillID = nil
            } else {
                manager.hoveredPillID = pill.id
            }
        } label: {
            ZStack(alignment: .topTrailing) {
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(Color.white.opacity(0.10))
                    .overlay(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.18), lineWidth: 0.6)
                    )
                    .overlay(
                        NotchOmiMark()
                            .frame(width: 11, height: 11)
                    )

                Circle()
                    .fill(pill.status.tintColor)
                    .frame(width: 4, height: 4)
                    .offset(x: 1.5, y: -1.5)
            }
        }
        .buttonStyle(.plain)
        .frame(width: 18, height: 18)
        .accessibilityLabel("\(pill.title) - \(pill.status.displayLabel)")
        .popover(isPresented: popoverBinding, arrowEdge: .bottom) {
            AgentPillPopover(
                pill: pill,
                isRecording: manager.recordingPillID == pill.id,
                onDismiss: { manager.dismiss(pillID: pill.id) },
                onOpenInChat: { openPillInChat() },
                onSendFollowUp: { text in manager.continueAgent(from: pill, text: text) },
                onToggleVoice: { manager.toggleFollowUpVoice(for: pill) }
            )
        }
    }

    private var popoverBinding: Binding<Bool> {
        Binding(
            get: { manager.hoveredPillID == pill.id },
            set: { isPresented in
                manager.hoveredPillID = isPresented ? pill.id : nil
            }
        )
    }

    private func openPillInChat() {
        manager.hoveredPillID = nil
        barWindow?.makeKeyAndOrderFront(nil)
        NotificationCenter.default.post(
            name: .agentPillRequestedChat,
            object: nil,
            userInfo: ["query": pill.query]
        )
    }
}
