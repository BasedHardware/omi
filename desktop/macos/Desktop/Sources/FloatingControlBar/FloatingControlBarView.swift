import AppKit
import Combine
import MarkdownUI
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
    @State private var agentSwitcherHovering = false
    @State private var agentSwitcherPinned = false
    @State private var agentSwitcherCollapseWorkItem: DispatchWorkItem?
    private let conversationTransition = Animation.spring(response: 0.32, dampingFraction: 0.86)
    private var notchHiddenCenterWidth: CGFloat {
        FloatingControlBarWindow.notchHiddenCenterWidth(for: window?.screen ?? NSScreen.main)
    }
    private var notchSideWidth: CGFloat {
        if state.showingAIConversation {
            return agentPills.pills.isEmpty
                ? FloatingControlBarWindow.notchCompactSideWidth
                : FloatingControlBarWindow.notchActiveSideWidth
        }
        if agentPills.pills.isEmpty && !state.isVoiceListening {
            return FloatingControlBarWindow.notchCompactSideWidth
        }
        return FloatingControlBarWindow.notchActiveSideWidth
    }
    private var notchChromeWidth: CGFloat {
        notchHiddenCenterWidth + notchSideWidth * 2
    }
    private var notchChromeLayoutWidth: CGFloat {
        state.showingAIConversation || shouldShowAgentSwitcher
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

    private var shouldShowAgentSwitcher: Bool {
        !agentPills.pills.isEmpty && (state.showingAIConversation || agentSwitcherPinned || agentSwitcherHovering)
    }

    private var notchModeBody: some View {
        VStack(spacing: 0) {
            notchChrome

            if shouldShowAgentSwitcher {
                NotchAgentFanoutRow(
                    manager: agentPills,
                    activePillID: state.activeAgentChatPillID,
                    onSelect: openAgentInChat
                )
                .frame(width: notchChromeLayoutWidth, height: FloatingControlBarWindow.notchAgentFanoutRowHeight)
                .onHover { setAgentSwitcherHovering($0) }
                .transition(.move(edge: .top).combined(with: .opacity))
                .zIndex(10)
            }

            if state.showingAIConversation {
                conversationView
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

                if state.showingAIConversation || state.currentNotification != nil || shouldShowAgentSwitcher {
                    NotchDockShape(bottomRadius: state.showingAIConversation || state.currentNotification != nil ? 22 : 18)
                        .fill(Color.black)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    NotchDockShape(bottomRadius: 18)
                        .fill(Color.black)
                        .frame(width: notchChromeWidth, height: notchChromeHeight)
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
        .animation(.spring(response: 0.24, dampingFraction: 0.88), value: shouldShowAgentSwitcher)
        .onChange(of: shouldShowAgentSwitcher) { _, visible in
            (window as? FloatingControlBarWindow)?.resizeForAgentSwitcher(visible: visible)
        }
        .onChange(of: agentPills.pills.isEmpty) { _, isEmpty in
            if isEmpty {
                agentSwitcherPinned = false
                agentSwitcherHovering = false
            }
        }
    }

    private var notchChrome: some View {
        ZStack {
            HStack(spacing: 0) {
                notchAgentLobe
                    .frame(width: notchSideWidth, height: notchChromeHeight)

                Spacer(minLength: notchHiddenCenterWidth)

                notchControlLobe
                    .frame(width: notchSideWidth, height: notchChromeHeight)
            }

            Color.clear
                .frame(width: notchHiddenCenterWidth, height: notchChromeHeight)
                .allowsHitTesting(false)
        }
        .frame(width: notchChromeLayoutWidth, height: notchChromeHeight)
    }

    private var notchAgentLobe: some View {
        HStack(spacing: 0) {
            if state.isVoiceListening && !state.isVoiceFollowUp && !state.showingAIConversation {
                HStack(spacing: 4) {
                    VoiceWaveformBars(isActive: true)
                        .scaleEffect(0.76)
                        .frame(width: 26, height: 15)
                    Image(systemName: "mic.fill")
                        .scaledFont(size: 10, weight: .semibold)
                        .foregroundColor(.white)
                }
                .frame(width: 58, height: 27)
            } else {
                NotchAgentPillsRowView(manager: agentPills, barWindow: window)
                    .opacity(shouldShowAgentSwitcher ? 0 : 1)
                    .scaleEffect(shouldShowAgentSwitcher ? 0.72 : 1, anchor: .center)
                    .frame(width: notchSideWidth - 6, height: notchChromeHeight, alignment: .trailing)
                    .padding(.trailing, 4)
                    .onHover { setAgentSwitcherHovering($0) }
                    .simultaneousGesture(
                        TapGesture().onEnded {
                            toggleAgentSwitcherPinned()
                        }
                    )
                    .onTapGesture {
                        if agentPills.pills.isEmpty {
                            onAskAI()
                        }
                    }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
    }

    private var notchControlLobe: some View {
        HStack(spacing: 10) {
            Button {
                openFloatingBarSettings()
            } label: {
                Image(systemName: "gearshape.fill")
                    .scaledFont(size: 15, weight: .semibold)
                    .foregroundColor(.white.opacity(0.86))
                    .frame(width: 40, height: 27)
            }
            .buttonStyle(.plain)
            .help("Floating Bar Settings")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .padding(.leading, 4)
    }

    private var notchChromeHeight: CGFloat {
        FloatingControlBarWindow.notchChromeHeight
    }

    private var barChrome: some View {
        VStack(spacing: 0) {
            // Main control bar - always visible
            controlBarView

            // AI conversation view - conditionally visible
            if state.showingAIConversation {
                conversationView
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
            if let activeAgentChatPill {
                AgentMainChatView(
                    pill: activeAgentChatPill,
                    manager: agentPills,
                    onBackToOmi: {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                            state.activeAgentChatPillID = nil
                            if state.chatHistory.isEmpty && state.currentAIMessage == nil && state.displayedQuery.isEmpty {
                                state.showingAIResponse = false
                            }
                        }
                    },
                    onEscape: onEscape
                )
                .id(activeAgentChatPill.id)
                .zIndex(1)
            } else if state.showingAIResponse {
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

    private var activeAgentChatPill: AgentPill? {
        guard let id = state.activeAgentChatPillID else { return nil }
        return agentPills.pills.first { $0.id == id }
    }

    private func setAgentSwitcherHovering(_ hovering: Bool) {
        agentSwitcherCollapseWorkItem?.cancel()
        agentSwitcherCollapseWorkItem = nil

        if hovering {
            agentSwitcherHovering = true
            return
        }

        guard !agentSwitcherPinned, !state.showingAIConversation else {
            agentSwitcherHovering = false
            return
        }

        let workItem = DispatchWorkItem {
            agentSwitcherHovering = false
        }
        agentSwitcherCollapseWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.14, execute: workItem)
    }

    private func toggleAgentSwitcherPinned() {
        guard !agentPills.pills.isEmpty else { return }
        agentSwitcherCollapseWorkItem?.cancel()
        agentSwitcherCollapseWorkItem = nil
        agentSwitcherPinned.toggle()
        agentSwitcherHovering = agentSwitcherPinned
    }

    private func openAgentInChat(_ pill: AgentPill) {
        guard agentPills.pills.contains(where: { $0.id == pill.id }) else { return }
        agentPills.markViewed(pillID: pill.id)
        (window as? FloatingControlBarWindow)?.makeKeyAndOrderFront(nil)
        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
            state.activeAgentChatPillID = pill.id
            state.showingAIConversation = true
            state.showingAIResponse = true
            state.isAILoading = false
            state.aiInputText = ""
        }
        state.markConversationActivity()
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
    var dotColors: [Color] = []

    private static let dotCount = 8
    private static let dotDiameterRatio: CGFloat = 0.18
    private static let ringRadiusRatio: CGFloat = 0.33

    var body: some View {
        GeometryReader { geometry in
            let size = min(geometry.size.width, geometry.size.height)
            let center = CGPoint(
                x: geometry.size.width / 2,
                y: geometry.size.height / 2
            )
            let dotDiameter = size * Self.dotDiameterRatio
            let ringRadius = size * Self.ringRadiusRatio

            ZStack {
                ForEach(0..<Self.dotCount, id: \.self) { index in
                    let angle = Double(index) / Double(Self.dotCount) * Double.pi * 2 - Double.pi
                    Circle()
                        .fill(dotColors.indices.contains(index) ? dotColors[index] : Color.white.opacity(0.96))
                        .frame(width: dotDiameter, height: dotDiameter)
                        .position(
                            x: center.x + CGFloat(cos(angle)) * ringRadius,
                            y: center.y + CGFloat(sin(angle)) * ringRadius
                        )
                }
            }
        }
        .drawingGroup(opaque: false, colorMode: .linear)
        .accessibilityHidden(true)
    }
}

private struct SubagentChatPointer: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

private struct AgentMainChatView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @ObservedObject var pill: AgentPill
    @ObservedObject var manager: AgentPillsManager
    let onBackToOmi: () -> Void
    let onEscape: () -> Void

    @State private var followUpText = ""
    @FocusState private var isFollowUpFocused: Bool

    private var isRecording: Bool {
        manager.recordingPillID == pill.id
    }

    private var isRunning: Bool {
        switch pill.status {
        case .queued, .starting, .running:
            return true
        case .done, .failed:
            return false
        }
    }

    private var outputText: String {
        if let message = pill.aiMessage {
            let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                return text
            }
        }
        return pill.latestActivity.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        questionBubble

                        responseContent

                        if isRecording {
                            voiceFollowUpView
                                .id("agentVoiceFollowUp")
                        }

                        Color.clear.frame(height: 1).id("agentBottom")
                    }
                    .background(
                        GeometryReader { geometry -> Color in
                            let height = geometry.size.height
                            DispatchQueue.main.async {
                                state.responseContentHeight = height
                            }
                            return Color.clear
                        }
                    )
                }
                .onChange(of: pill.latestActivity) {
                    scrollToBottom(proxy)
                }
                .onChange(of: pill.aiMessage?.text) {
                    scrollToBottom(proxy)
                }
                .onChange(of: isRecording) {
                    scrollToBottom(proxy)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            followUpInput
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            manager.markViewed(pillID: pill.id)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
                isFollowUpFocused = true
            }
        }
        .onExitCommand {
            onEscape()
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Button(action: onBackToOmi) {
                Image(systemName: "chevron.left")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(.white.opacity(0.82))
                    .frame(width: 36, height: 36)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Back to Omi chat")

            Text(pill.title)
                .scaledFont(size: 13, weight: .bold)
                .foregroundColor(.white)
                .lineLimit(1)

            Spacer(minLength: 8)

            statusBadge
        }
    }

    private var statusBadge: some View {
        Group {
            if pill.status == .done {
                Button {
                    manager.dismiss(pillID: pill.id)
                    onBackToOmi()
                } label: {
                    statusBadgeLabel
                }
                .buttonStyle(.plain)
                .help("Dismiss completed agent")
            } else {
                statusBadgeLabel
            }
        }
    }

    private var statusBadgeLabel: some View {
        Text(pill.status.displayLabel)
            .scaledFont(size: 9, weight: .bold)
            .foregroundColor(statusForeground)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(pill.status.tintColor.opacity(statusBackgroundOpacity))
            .clipShape(Capsule())
    }

    private var statusForeground: Color {
        switch pill.status {
        case .queued, .starting, .running, .done:
            return .black.opacity(0.86)
        case .failed:
            return .white
        }
    }

    private var statusBackgroundOpacity: Double {
        switch pill.status {
        case .queued, .starting, .running, .done:
            return 1
        case .failed:
            return 0.75
        }
    }

    private var questionBubble: some View {
        Text(pill.query)
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(.white)
            .textSelection(.enabled)
            .lineLimit(4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(Color.white.opacity(0.10))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            .contextMenu {
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(pill.query, forType: .string)
                }
            }
    }

    @ViewBuilder
    private var responseContent: some View {
        if isRunning && outputText.isEmpty {
            TypingIndicator()
                .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                if isRunning {
                    HStack(spacing: 7) {
                        ProgressView()
                            .scaleEffect(0.55)
                            .frame(width: 14, height: 14)
                        Text("working")
                            .scaledFont(size: 11, weight: .medium)
                            .foregroundColor(.white.opacity(0.48))
                    }
                }

                Markdown(outputText.isEmpty ? "Working..." : outputText)
                    .markdownTheme(.aiMessage(scale: 0.88))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 4)
            .contextMenu {
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(outputText, forType: .string)
                }
            }
        }
    }

    private var voiceFollowUpView: some View {
        HStack(spacing: 8) {
            VoiceWaveformBars(isActive: true)
            Image(systemName: "mic.fill")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(.white)
            Text("Listening...")
                .scaledFont(size: 13)
                .foregroundColor(.white.opacity(0.62))
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(OmiColors.purplePrimary.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var followUpInput: some View {
        HStack(spacing: 6) {
            Button {
                manager.toggleFollowUpVoice(for: pill)
            } label: {
                Image(systemName: isRecording ? "stop.circle.fill" : "mic.fill")
                    .scaledFont(size: 17, weight: .semibold)
                    .foregroundColor(isRecording ? OmiColors.purpleAccent : .secondary)
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .help(isRecording ? "Stop voice follow-up" : "Voice follow-up")

            TextField("Ask this agent...", text: $followUpText)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color.white.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .focused($isFollowUpFocused)
                .onSubmit {
                    sendFollowUp()
                }

            Button(action: sendFollowUp) {
                Image(systemName: "arrow.up.circle.fill")
                    .scaledFont(size: 20)
                    .foregroundColor(canSend ? .white : .secondary)
            }
            .disabled(!canSend)
            .buttonStyle(.plain)
        }
    }

    private var canSend: Bool {
        !followUpText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func sendFollowUp() {
        let trimmed = followUpText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        followUpText = ""
        if let handoff = AgentPillsManager.floatingAgentHandoff(for: trimmed) {
            let sibling = manager.spawnFromHandoff(handoff, model: pill.model)
            state.activeAgentChatPillID = sibling.id
            return
        }
        manager.continueAgent(from: pill, text: trimmed)
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.15)) {
            proxy.scrollTo("agentBottom", anchor: .bottom)
        }
    }
}

private struct NotchAgentPillsRowView: View {
    @ObservedObject var manager: AgentPillsManager
    weak var barWindow: NSWindow?
    @State private var pillStatusCancellables: [UUID: AnyCancellable] = [:]
    @State private var pillStatusChangeToken = 0

    private var stackedPills: [AgentPill] {
        NotchAgentStackMetrics.sortedPills(manager.pills)
    }

    var body: some View {
        let _ = pillStatusChangeToken
        NotchAgentOmiIndicatorView(pills: stackedPills)
            .frame(width: 21, height: 21)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
            .accessibilityLabel("Subagent status")
            .accessibilityHint("Hover to fan out subagents, click to keep them open")
            .onAppear { syncPillStatusObservers() }
            .onChange(of: manager.pills.map(\.id)) { _, _ in
                syncPillStatusObservers()
            }
    }

    private func syncPillStatusObservers() {
        let currentIDs = Set(manager.pills.map(\.id))
        pillStatusCancellables = pillStatusCancellables.filter { currentIDs.contains($0.key) }
        for pill in manager.pills where pillStatusCancellables[pill.id] == nil {
            pillStatusCancellables[pill.id] = pill.objectWillChange
                .receive(on: DispatchQueue.main)
                .sink { _ in
                    pillStatusChangeToken &+= 1
                }
        }
    }
}

@MainActor
private enum NotchAgentStackMetrics {
    static let maxAgents = 8
    static let fanoutOrbSize: CGFloat = 11
    static let fanoutSpacing: CGFloat = 0
    static let fanoutHorizontalInset: CGFloat = 42
    static let fanoutOriginYOffset: CGFloat = -31

    static func sortedPills(_ pills: [AgentPill]) -> [AgentPill] {
        let newestIndex = Dictionary(uniqueKeysWithValues: pills.reversed().enumerated().map { ($0.element.id, $0.offset) })
        return pills.sorted { lhs, rhs in
            let lhsGroup = NotchAgentStatusGroup(status: lhs.status)
            let rhsGroup = NotchAgentStatusGroup(status: rhs.status)
            if lhsGroup.sortRank != rhsGroup.sortRank {
                return lhsGroup.sortRank < rhsGroup.sortRank
            }
            return (newestIndex[lhs.id] ?? 0) < (newestIndex[rhs.id] ?? 0)
        }
    }

    static func fanoutX(for index: Int, width: CGFloat) -> CGFloat {
        guard maxAgents > 1 else { return width / 2 }
        let usableWidth = max(0, width - fanoutHorizontalInset * 2)
        return fanoutHorizontalInset + usableWidth * CGFloat(index) / CGFloat(maxAgents - 1)
    }
}

private struct NotchAgentOmiIndicatorView: View {
    let pills: [AgentPill]

    private var visiblePills: [AgentPill] {
        Array(pills.prefix(NotchAgentStackMetrics.maxAgents))
    }

    var body: some View {
        NotchOmiMark(dotColors: visiblePills.map { NotchAgentStatusGroup(status: $0.status).color })
            .shadow(color: visiblePills.first.map { NotchAgentStatusGroup(status: $0.status).color.opacity(0.55) } ?? .clear, radius: 8)
            .contentShape(Rectangle())
    }
}

private struct NotchAgentFanoutRow: View {
    @ObservedObject var manager: AgentPillsManager
    let activePillID: UUID?
    let onSelect: (AgentPill) -> Void
    @State private var pillStatusCancellables: [UUID: AnyCancellable] = [:]
    @State private var pillStatusChangeToken = 0
    @State private var didFanOut = false

    private var sortedPills: [AgentPill] {
        let _ = pillStatusChangeToken
        return Array(NotchAgentStackMetrics.sortedPills(manager.pills).prefix(NotchAgentStackMetrics.maxAgents))
    }

    var body: some View {
        GeometryReader { geometry in
            let rowWidth = geometry.size.width
            let rowHeight = max(geometry.size.height, FloatingControlBarWindow.notchAgentFanoutRowHeight)
            let originX = NotchAgentStackMetrics.fanoutX(for: 0, width: rowWidth)

            ZStack {
                ForEach(0..<NotchAgentStackMetrics.maxAgents, id: \.self) { index in
                    let targetX = NotchAgentStackMetrics.fanoutX(for: index, width: rowWidth)
                    if sortedPills.indices.contains(index) {
                        let pill = sortedPills[index]
                        Button {
                            onSelect(pill)
                        } label: {
                            NotchAgentFanoutDot(
                                group: NotchAgentStatusGroup(status: pill.status),
                                isActive: pill.id == activePillID,
                                isOccupied: true
                            )
                            .fanoutSlotAnimation(
                                index: index,
                                didFanOut: didFanOut,
                                initialXOffset: originX - targetX
                            )
                        }
                        .buttonStyle(.plain)
                        .help(pill.title)
                        .position(x: targetX, y: rowHeight / 2)
                    } else {
                        NotchAgentFanoutDot(
                            group: nil,
                            isActive: false,
                            isOccupied: false
                        )
                        .fanoutSlotAnimation(
                            index: index,
                            didFanOut: didFanOut,
                            initialXOffset: originX - targetX
                        )
                        .allowsHitTesting(false)
                        .position(x: targetX, y: rowHeight / 2)
                    }
                }
            }
            .frame(width: rowWidth, height: rowHeight)
        }
        .frame(maxWidth: .infinity, minHeight: FloatingControlBarWindow.notchAgentFanoutRowHeight)
        .background(Color.black)
        .onAppear {
            syncPillStatusObservers()
            didFanOut = false
            DispatchQueue.main.async {
                withAnimation(.spring(response: 0.22, dampingFraction: 0.74)) {
                    didFanOut = true
                }
            }
        }
        .onDisappear {
            didFanOut = false
        }
        .onChange(of: manager.pills.map(\.id)) { _, _ in
            syncPillStatusObservers()
        }
    }

    private func syncPillStatusObservers() {
        let currentIDs = Set(manager.pills.map(\.id))
        pillStatusCancellables = pillStatusCancellables.filter { currentIDs.contains($0.key) }
        for pill in manager.pills where pillStatusCancellables[pill.id] == nil {
            pillStatusCancellables[pill.id] = pill.objectWillChange
                .receive(on: DispatchQueue.main)
                .sink { _ in
                    pillStatusChangeToken &+= 1
                }
        }
    }
}

private extension View {
    func fanoutSlotAnimation(index: Int, didFanOut: Bool, initialXOffset: CGFloat) -> some View {
        self
            .offset(
                x: didFanOut ? 0 : initialXOffset,
                y: didFanOut ? 0 : NotchAgentStackMetrics.fanoutOriginYOffset
            )
            .scaleEffect(didFanOut ? 1 : 0.72)
            .opacity(didFanOut ? 1 : 0.2)
            .animation(
                .spring(response: 0.18, dampingFraction: 0.74)
                    .delay(Double(index) * 0.018),
                value: didFanOut
            )
    }
}

private struct NotchAgentFanoutDot: View {
    let group: NotchAgentStatusGroup?
    let isActive: Bool
    let isOccupied: Bool

    var body: some View {
        Circle()
            .fill(group?.color ?? Color.white.opacity(0.94))
            .frame(width: NotchAgentStackMetrics.fanoutOrbSize, height: NotchAgentStackMetrics.fanoutOrbSize)
            .overlay(
                Circle()
                    .strokeBorder(Color.white.opacity(isOccupied ? 0.42 : 0.82), lineWidth: isOccupied ? 0.7 : 0.9)
            )
            .shadow(color: (group?.color ?? .clear).opacity(isOccupied ? 0.72 : 0), radius: isActive ? 9 : 5)
            .frame(width: 18, height: 22)
            .contentShape(Circle())
    }
}

private enum NotchAgentStatusGroup: String, Identifiable {
    case running
    case queued
    case failed
    case done

    var id: String { rawValue }

    init(status: AgentPill.Status) {
        switch status {
        case .starting, .running:
            self = .running
        case .queued:
            self = .queued
        case .failed:
            self = .failed
        case .done:
            self = .done
        }
    }

    var title: String {
        switch self {
        case .running: return "Running"
        case .queued: return "Queued"
        case .failed: return "Failed"
        case .done: return "Done"
        }
    }

    var color: Color {
        switch self {
        case .running: return Color(red: 0.74, green: 0.32, blue: 1.0)
        case .queued: return Color(red: 0.20, green: 0.86, blue: 1.0)
        case .failed: return Color(red: 1.0, green: 0.42, blue: 0.42)
        case .done: return Color(red: 0.27, green: 0.92, blue: 0.46)
        }
    }

    var highlightColor: Color {
        switch self {
        case .running: return Color(red: 1.0, green: 0.20, blue: 0.86)
        case .queued: return Color(red: 0.08, green: 0.52, blue: 1.0)
        case .failed: return Color(red: 1.0, green: 0.46, blue: 0.12)
        case .done: return Color(red: 0.08, green: 0.78, blue: 0.62)
        }
    }

    var shadowColor: Color {
        switch self {
        case .running: return Color(red: 0.36, green: 0.06, blue: 0.86)
        case .queued: return Color(red: 0.00, green: 0.44, blue: 0.95)
        case .failed: return Color(red: 0.78, green: 0.08, blue: 0.18)
        case .done: return Color(red: 0.02, green: 0.50, blue: 0.24)
        }
    }

    var sortRank: Int {
        switch self {
        case .running: return 0
        case .queued: return 1
        case .failed: return 2
        case .done: return 3
        }
    }

    var swirlDuration: TimeInterval {
        switch self {
        case .running: return 0.9
        case .queued: return 3.8
        case .failed: return 4.6
        case .done: return 5.2
        }
    }
}

private struct NotchAgentStatusOrb: View {
    let group: NotchAgentStatusGroup
    let isActive: Bool
    var size: CGFloat = 16

    var body: some View {
        TimelineView(.animation) { timeline in
            let duration = group.swirlDuration
            let phase = CGFloat(timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: duration) / duration)
            NotchAgentSwirlSphere(group: group, isActive: isActive, phase: phase, size: size)
        }
        .frame(width: size + 6, height: size + 6)
    }
}

private struct NotchAgentSwirlSphere: View {
    let group: NotchAgentStatusGroup
    let isActive: Bool
    let phase: CGFloat
    let size: CGFloat

    var body: some View {
        Canvas { context, size in
            drawSwirl(context: &context, size: size)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .shadow(color: group.color.opacity(isActive ? 0.94 : 0.74), radius: isActive ? size * 0.50 : size * 0.38)
        .shadow(color: group.highlightColor.opacity(isActive ? 0.68 : 0.46), radius: isActive ? size * 0.88 : size * 0.62)
    }

    private func drawSwirl(context: inout GraphicsContext, size: CGSize) {
        let rect = CGRect(origin: .zero, size: size)
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let radius = min(size.width, size.height) / 2
        let circle = Path(ellipseIn: rect)
        context.clip(to: circle)
        context.fill(circle, with: .color(group.shadowColor.opacity(0.94)))

        for index in 0..<3 {
            drawBand(index: index, rect: rect, center: center, radius: radius, context: &context)
        }

        drawColorLift(size: size, context: &context)
    }

    private func drawBand(
        index: Int,
        rect: CGRect,
        center: CGPoint,
        radius: CGFloat,
        context: inout GraphicsContext
    ) {
        let turn = phase * .pi * 2 + CGFloat(index) * (.pi * 2 / 3)
        let sweepCenter = CGPoint(
            x: center.x + cos(turn) * radius * 0.28,
            y: center.y + sin(turn * 0.86) * radius * 0.24
        )
        let start = CGPoint(
            x: sweepCenter.x - cos(turn) * radius * 1.35,
            y: sweepCenter.y - sin(turn) * radius * 1.35
        )
        let end = CGPoint(
            x: sweepCenter.x + cos(turn) * radius * 1.35,
            y: sweepCenter.y + sin(turn) * radius * 1.35
        )
        let stops = [
            Gradient.Stop(color: group.color.opacity(index == 1 ? 1.0 : 0.78), location: 0),
            Gradient.Stop(color: group.highlightColor.opacity(index == 0 ? 1.0 : 0.90), location: 0.52),
            Gradient.Stop(color: group.color.opacity(index == 2 ? 1.0 : 0.78), location: 1),
        ]
        let gradient = Gradient(stops: stops)
        let bandRect = rect
            .insetBy(dx: -radius * 0.35, dy: radius * (0.06 + CGFloat(index) * 0.04))
            .offsetBy(dx: cos(turn) * radius * 0.20, dy: sin(turn) * radius * 0.18)
        context.fill(Path(ellipseIn: bandRect), with: .linearGradient(gradient, startPoint: start, endPoint: end))
    }

    private func drawColorLift(size: CGSize, context: inout GraphicsContext) {
        let liftRect = CGRect(
            x: size.width * (0.18 + 0.08 * cos(phase * .pi * 2)),
            y: size.height * 0.14,
            width: size.width * 0.42,
            height: size.height * 0.34
        )
        let gradient = Gradient(colors: [
            group.highlightColor.opacity(0.48),
            group.color.opacity(0.20),
            .clear,
        ])
        context.fill(
            Path(ellipseIn: liftRect),
            with: .radialGradient(
                gradient,
                center: CGPoint(x: liftRect.midX, y: liftRect.midY),
                startRadius: 0,
                endRadius: liftRect.width * 0.72
            )
        )
    }
}
