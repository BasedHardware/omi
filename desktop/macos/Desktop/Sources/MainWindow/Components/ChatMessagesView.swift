import SwiftUI

/// Detects user scroll-wheel / trackpad gestures, mouse interactions, and
/// keyboard scroll-navigation on the enclosing NSScrollView and fires a
/// callback immediately — before the scroll position settles.
/// This wins the race against throttled programmatic scrolls during streaming.
private struct UserScrollDetector: NSViewRepresentable {
    let onUserScroll: () -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            context.coordinator.install(for: view)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onUserScroll: onUserScroll)
    }

    class Coordinator: NSObject {
        let onUserScroll: () -> Void
        private var monitor: Any?

        /// Key codes that navigate within a scroll view when it has keyboard
        /// focus. These are unambiguous reader-intent scroll signals.
        private static let scrollNavigationKeyCodes: Set<UInt16> = [
            125,  // Down arrow
            126,  // Up arrow
            116,  // Page Up
            121,  // Page Down
            115,  // Home
            119,  // End
        ]

        init(onUserScroll: @escaping () -> Void) {
            self.onUserScroll = onUserScroll
        }

        func install(for view: NSView) {
            // Find the enclosing NSScrollView so we can scope the monitor
            var scrollView: NSScrollView?
            var current: NSView? = view
            while let v = current {
                if let sv = v as? NSScrollView {
                    scrollView = sv
                    break
                }
                current = v.superview
            }
            let targetScrollView = scrollView

            monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .leftMouseDown, .leftMouseDragged, .keyDown]) { [weak self] event in
                guard let self = self, let targetScrollView = targetScrollView else { return event }
                // Only respond to events in our scroll view's window
                guard event.window == targetScrollView.window else { return event }

                if event.type == .keyDown {
                    // Keyboard scroll-navigation (Page Up/Down, arrows, Home/End)
                    // is reader intent — but only when a text-editing control
                    // does NOT have keyboard focus. Otherwise arrow keys and
                    // Page Up/Down go to the chat input or a selected text view,
                    // not the scroll view.
                    guard Self.scrollNavigationKeyCodes.contains(event.keyCode) else { return event }
                    if Self.isFirstResponderEditingText(in: event.window) { return event }
                    self.onUserScroll()
                } else {
                    // Mouse/wheel events: check if inside the scroll view
                    let locationInWindow = event.locationInWindow
                    let locationInScrollView = targetScrollView.convert(locationInWindow, from: nil)
                    guard targetScrollView.bounds.contains(locationInScrollView) else { return event }
                    if event.type == .scrollWheel {
                        // Any physical wheel/trackpad scroll inside the transcript is reader intent.
                        if event.scrollingDeltaY != 0 || event.scrollingDeltaX != 0 {
                            self.onUserScroll()
                        }
                    } else {
                        // Mouse click/drag inside the transcript is reader intent: it may be
                        // a scrollbar drag, text selection, or another reading interaction.
                        self.onUserScroll()
                    }
                }
                return event
            }
        }

        /// Returns true if the window's first responder is a text-editing
        /// control (NSTextView backs both NSTextField via field editor and
        /// SwiftUI text inputs). Used to distinguish typing in the chat input
        /// from keyboard-driven scroll navigation.
        private static func isFirstResponderEditingText(in window: NSWindow?) -> Bool {
            guard let window = window else { return false }
            let fr = window.firstResponder
            return fr is NSTextView
        }

        deinit {
            if let monitor = monitor {
                NSEvent.removeMonitor(monitor)
            }
        }
    }
}

/// Explicit scroll intent model for streaming follow behavior.
/// `followingBottom` = the reader is at the live edge; streamed chunks may auto-scroll.
/// `freeScrolling`  = the reader intentionally scrolled away; viewport must not move.
/// `anchoringTurn`  = the viewport is intentionally anchored to the latest local
///                     user turn; assistant streaming below must not yank to bottom.
private enum ChatScrollMode: Equatable {
    case followingBottom
    case freeScrolling
    case anchoringTurn
}

/// A token that callers pass when the local user sends a message.
/// This allows ChatMessagesView to distinguish genuine user sends from
/// messages arriving via polling, sync, or other sources — without
/// inferring solely from messages.count changes.
struct LocalSendToken: Equatable {
    /// Monotonic counter that increments on every local send.
    /// ChatMessagesView tracks the last seen value and reacts to increments.
    let generation: Int
}

/// Reusable chat messages scroll view extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
struct ChatMessagesView<WelcomeContent: View>: View {
    let messages: [ChatMessage]
    let isSending: Bool
    let hasMoreMessages: Bool
    let isLoadingMoreMessages: Bool
    let isLoadingInitial: Bool
    let app: OmiApp?
    let onLoadMore: () async -> Void
    let onRate: (String, Int?) -> Void
    var onCitationTap: ((Citation) -> Void)? = nil
    var sessionsLoadError: String? = nil
    var onRetry: (() -> Void)? = nil
    /// Token that increments each time the local user sends a message.
    /// ChatMessagesView uses this to anchor the new user message near the
    /// top of the viewport (one-shot) before the assistant streams below.
    /// Pass nil when the caller cannot distinguish local sends (e.g. TaskChatPanel
    /// with its own send path).
    var localSendToken: LocalSendToken? = nil
    @ViewBuilder var welcomeContent: () -> WelcomeContent

    /// IDs of messages that are near-duplicates of an earlier message in the same session.
    /// Computed once per messages change to avoid O(n^2) per render.
    private var duplicateMessageIds: Set<String> {
        var seen: [String: String] = [:]  // truncated text → first message ID
        var dupes = Set<String>()
        for msg in messages {
            guard msg.text.count > 200 else { continue }  // only dedup long messages
            // Use first 200 chars as fingerprint (handles minor trailing diffs)
            let fingerprint = String(msg.text.prefix(200))
            if let _ = seen[fingerprint] {
                dupes.insert(msg.id)
            } else {
                seen[fingerprint] = msg.id
            }
        }
        return dupes
    }

    // MARK: - Scroll State

    @State private var isUserAtBottom = true
    /// Source of truth for scroll intent. Geometry/layout changes alone must NOT
    /// switch this to `.freeScrolling` — only physical user input (wheel/trackpad,
    /// mouse, or keyboard scroll-navigation).
    @State private var scrollMode: ChatScrollMode = .followingBottom
    /// Throttle token for scrollToBottom — prevents the streaming + scroll
    /// detection feedback loop from saturating the main thread.
    @State private var scrollThrottleWorkItem: DispatchWorkItem?
    /// True when the user is actively scrolling via scroll wheel/trackpad.
    /// Set immediately by the scroll wheel monitor to win the race against
    /// throttled programmatic scrolls during streaming.
    @State private var userIsScrolling = false
    @State private var userScrollEndWorkItem: DispatchWorkItem?
    /// Tracks work items for delayed initial bottom scrolls so they can be
    /// canceled on user scroll or disappear.
    @State private var initialScrollWorkItems: [DispatchWorkItem] = []

    // MARK: - Local Send Anchoring

    /// Last observed local send token generation. When it increments, we know
    /// a local user send just happened and can anchor the viewport.
    @State private var lastSeenSendGeneration: Int = 0

    // MARK: - Saved Restore

    /// Whether the initial history load for this conversation has been handled.
    /// Prevents re-anchoring on subsequent messages.count changes after restore.
    @State private var initialRestoreHandled = false

    // MARK: - Prepend Preservation (Load Earlier Messages)

    /// The ID of the first visible message before a "Load earlier" operation.
    /// After load completes, we scroll to reposition this message at the top
    /// of the viewport, preserving the user's reading position.
    @State private var prependAnchorId: String?

    // MARK: - Activity Below Indicator

    /// True when new content arrived while the user is scrolled away, so the
    /// jump-to-bottom affordance should be shown.
    @State private var hasActivityBelow = false

    var body: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .bottom) {
                scrollContent(proxy: proxy)
                scrollToBottomButton(proxy: proxy)
            }
        }
    }

    @ViewBuilder
    private func scrollContent(proxy: ScrollViewProxy) -> some View {
        ScrollView {
            LazyVStack(spacing: 18) {
                loadMoreButton
                messageContent
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 22)
            .textSelection(.enabled)
            .background(scrollDetectors)

            // Invisible anchor lives OUTSIDE the LazyVStack so it is always
            // eagerly rendered. Inside LazyVStack it may not exist in the view
            // hierarchy when scrollTo is first called (lazy evaluation), causing
            // the scroll to jump to an estimated — often empty — position.
            if !messages.isEmpty {
                Color.clear
                    .frame(height: 1)
                    .id("bottom-anchor")
            }
        }
        // MARK: - React to message count changes
        .onChange(of: messages.count) { oldCount, newCount in
            handleMessagesCountChange(oldCount: oldCount, newCount: newCount, proxy: proxy)
        }
        // MARK: - React to streaming text changes
        .onChange(of: messages.last?.text) { _, _ in
            handleLiveContentChange(proxy: proxy)
        }
        // MARK: - React to content block changes (tool calls, etc.)
        .onChange(of: messages.last?.contentBlocks.count) { _, _ in
            handleLiveContentChange(proxy: proxy)
        }
        // MARK: - React to local send token (turn anchoring)
        .onChange(of: localSendToken?.generation) { oldGen, newGen in
            guard let newGen = newGen else { return }
            if newGen > lastSeenSendGeneration {
                lastSeenSendGeneration = newGen
                handleLocalSend(proxy: proxy)
            }
        }
        // MARK: - React to isSending (send started)
        .onChange(of: isSending) { oldValue, newValue in
            if newValue && !oldValue && localSendToken == nil {
                cancelAllPendingScrolls()
                userIsScrolling = false
                scrollMode = .followingBottom
                hasActivityBelow = false
                scrollToBottom(proxy: proxy)
            }
        }
        // MARK: - React to isLoadingMoreMessages (prepend preservation)
        .onChange(of: isLoadingMoreMessages) { _, isLoading in
            if isLoading {
                // Capture the first message ID before the load begins
                prependAnchorId = messages.first?.id
            } else {
                // Load finished — restore prepend anchor if user hasn't scrolled
                restorePrependAnchor(proxy: proxy)
            }
        }
        .onAppear {
            if !messages.isEmpty {
                handleInitialRestore(proxy: proxy)
            }
        }
        .onDisappear {
            cancelAllPendingScrolls()
        }
    }

    // MARK: - Message Count Change Handler

    /// Central handler for messages.count changes. Handles:
    /// - Initial restore (scroll to last user message on first load)
    /// - New messages arriving while following
    /// - New messages arriving while scrolled away (activity indicator)
    /// - Prepend detection (load earlier)
    private func handleMessagesCountChange(oldCount: Int, newCount: Int, proxy: ScrollViewProxy) {
        if newCount > oldCount {
            // --- Initial restore: messages went from 0→N ---
            if oldCount == 0 && newCount > 0 {
                handleInitialRestore(proxy: proxy)
                return
            }

            // --- Prepend: new older messages inserted ---
            // If prependAnchorId is set and the count increase corresponds to
            // older messages, the onChange(of: isLoadingMoreMessages) handler
            // takes care of repositioning.

            // --- New live messages arriving ---
            if scrollMode == .followingBottom {
                scrollToBottom(proxy: proxy)
            } else if scrollMode == .anchoringTurn {
                // While anchored to the new turn, keep the prompt stable and
                // surface that live activity is arriving below.
                hasActivityBelow = true
            } else {
                // freeScrolling — new content arrived below
                hasActivityBelow = true
            }
        }
    }

    private func handleLiveContentChange(proxy: ScrollViewProxy) {
        switch scrollMode {
        case .followingBottom:
            throttledScrollToBottom(proxy: proxy)
        case .freeScrolling, .anchoringTurn:
            hasActivityBelow = true
        }
    }

    // MARK: - Initial Restore

    /// On the first load of a saved conversation, scroll to the last user
    /// message rather than absolute bottom. This lets the user see their
    /// last question and the beginning of the AI response, with more context
    /// above. Fallback: for chats with no user messages or only one turn,
    /// just go to bottom.
    private func handleInitialRestore(proxy: ScrollViewProxy) {
        guard !initialRestoreHandled else { return }
        initialRestoreHandled = true

        // Find the last user message
        let lastUserMsg = messages.last { $0.sender == .user }

        if let anchorMsg = lastUserMsg, messages.count > 2 {
            scrollMode = .anchoringTurn
            hasActivityBelow = true
            // Scroll so the last user message appears near the top of the
            // viewport. We use a small delay to let the LazyVStack render.
            let anchorId = anchorMsg.id
            let work = DispatchWorkItem { [self] in
                guard scrollMode == .followingBottom || scrollMode == .anchoringTurn else { return }
                proxy.scrollTo(anchorId, anchor: .top)
            }
            initialScrollWorkItems.append(work)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
        } else {
            // Fallback: no user messages, or very short chat — scroll to bottom
            scrollMode = .followingBottom
            hasActivityBelow = false
            scrollToBottom(proxy: proxy)
        }
    }

    // MARK: - Local Send / Turn Anchoring

    /// Called when the local send token increments. Anchors the newest user
    /// message near the top of the viewport so the assistant response streams
    /// below it, giving the user a stable reading frame.
    private func handleLocalSend(proxy: ScrollViewProxy) {
        guard !messages.isEmpty else { return }

        // Find the most recently added user message
        let lastUserMsg = messages.last { $0.sender == .user }
        guard let anchorMsg = lastUserMsg else {
            // No user message found (shouldn't happen on a local send, but be safe)
            scrollMode = .followingBottom
            scrollToBottom(proxy: proxy)
            return
        }

        cancelAllPendingScrolls()
        scrollMode = .anchoringTurn

        let anchorId = anchorMsg.id
        // Small delay to let SwiftUI commit the new message into the LazyVStack
        let work = DispatchWorkItem { [self] in
            guard scrollMode == .anchoringTurn else { return }
            proxy.scrollTo(anchorId, anchor: .top)
        }
        initialScrollWorkItems.append(work)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1, execute: work)
    }

    // MARK: - Prepend Preservation

    /// After "Load earlier messages" completes, scroll to restore the message
    /// that was at the top before the load. Skipped if the user scrolled during
    /// the load or if the anchor message is no longer present.
    private func restorePrependAnchor(proxy: ScrollViewProxy) {
        guard let anchorId = prependAnchorId else { return }
        prependAnchorId = nil

        // If the user scrolled during the load, don't override their position
        guard scrollMode != .freeScrolling else { return }

        // Verify the anchor message is still in the list
        let stillExists = messages.contains { $0.id == anchorId }
        guard stillExists else { return }

        // Scroll anchor to top without animation
        let work = DispatchWorkItem { [self] in
            guard self.scrollMode != .freeScrolling else { return }
            proxy.scrollTo(anchorId, anchor: .top)
        }
        initialScrollWorkItems.append(work)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: work)
    }

    // MARK: - Scheduled Scrolls

    /// Schedules a delayed bottom scroll that is mode-aware and cancelable.
    private func scheduleInitialScroll(proxy: ScrollViewProxy, delay: TimeInterval) {
        var workItem: DispatchWorkItem?
        workItem = DispatchWorkItem { [self] in
            // Only fire if still following — user may have scrolled during settling
            if scrollMode == .followingBottom {
                scrollToBottom(proxy: proxy)
            }
            if let workItem {
                initialScrollWorkItems.removeAll { $0 === workItem }
            }
        }
        if let workItem {
            initialScrollWorkItems.append(workItem)
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
        }
    }

    /// Cancels all pending scheduled scrolls (throttle, initial, user-scroll-end).
    private func cancelAllPendingScrolls() {
        scrollThrottleWorkItem?.cancel()
        scrollThrottleWorkItem = nil
        userScrollEndWorkItem?.cancel()
        userScrollEndWorkItem = nil
        for item in initialScrollWorkItems {
            item.cancel()
        }
        initialScrollWorkItems.removeAll()
    }

    // MARK: - Subviews

    @ViewBuilder
    private var loadMoreButton: some View {
        if hasMoreMessages {
            Button {
                prependAnchorId = messages.first?.id
                Task {
                    await onLoadMore()
                }
            } label: {
                if isLoadingMoreMessages {
                    ProgressView()
                        .scaleEffect(0.8)
                } else {
                    Text("Load earlier messages")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
        }
    }

    @ViewBuilder
    private var messageContent: some View {
        if isLoadingInitial && messages.isEmpty && sessionsLoadError == nil {
            VStack(spacing: 12) {
                ProgressView()
                    .scaleEffect(0.8)
                Text("Loading...")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 80)
        } else if let error = sessionsLoadError, messages.isEmpty {
            errorContent(error: error)
        } else if messages.isEmpty {
            welcomeContent()
        } else {
            let dupeIds = duplicateMessageIds
            ForEach(messages) { message in
                ChatBubble(
                    message: message,
                    app: app,
                    onRate: { rating in
                        onRate(message.id, rating)
                    },
                    onCitationTap: { citation in
                        onCitationTap?(citation)
                    },
                    isDuplicate: dupeIds.contains(message.id)
                )
                .id(message.id)
            }
        }
    }

    @ViewBuilder
    private func errorContent(error: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .scaledFont(size: 40)
                .foregroundColor(OmiColors.warning)

            Text("Failed to load chats")
                .scaledFont(size: 16, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

            Text(error)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)

            if let onRetry {
                Button(action: onRetry) {
                    Text("Try Again")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .omiControlSurface(fill: OmiColors.userBubble, radius: OmiChrome.chipRadius)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(32)
        .padding(.vertical, 48)
    }

    // Both detectors share the same .background so their NSViews land
    // inside NSScrollView.documentView — the superview walk in each
    // coordinator then correctly finds the enclosing NSScrollView.
    private var scrollDetectors: some View {
        ZStack {
            ScrollPositionDetector { atBottom in
                isUserAtBottom = atBottom
                // Resume live following when the reader scrolls back to the
                // live edge. atBottom == true is unambiguous intent to follow
                // again; only atBottom == false is ambiguous (it can be a
                // geometry/layout change, not user intent) and must NOT switch
                // to .freeScrolling on its own.
                if atBottom && scrollMode == .freeScrolling {
                    cancelAllPendingScrolls()
                    userIsScrolling = false
                    scrollMode = .followingBottom
                    hasActivityBelow = false
                }
            }
            UserScrollDetector {
                if scrollMode == .anchoringTurn {
                    // If user scrolls during turn anchoring, cancel the anchor
                    // and go to free-scrolling immediately.
                    scrollMode = .freeScrolling
                    cancelAllPendingScrolls()
                } else {
                    scrollMode = .freeScrolling
                }
                userIsScrolling = true
                hasActivityBelow = false
                cancelAllPendingScrolls()
                let endWork = DispatchWorkItem {
                    userIsScrolling = false
                }
                userScrollEndWorkItem = endWork
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: endWork)
            }
        }
    }

    @ViewBuilder
    private func scrollToBottomButton(proxy: ScrollViewProxy) -> some View {
        // Show when: free-scrolled, OR anchoring turn (give user escape hatch),
        // AND there are messages, AND either there's activity below or we're
        // in a non-following mode.
        if (scrollMode == .freeScrolling || scrollMode == .anchoringTurn) && !messages.isEmpty {
            Button {
                cancelAllPendingScrolls()
                userIsScrolling = false
                scrollMode = .followingBottom
                hasActivityBelow = false
                scrollToBottom(proxy: proxy)
            } label: {
                ZStack(alignment: .center) {
                    Circle()
                        .fill(OmiColors.backgroundPrimary)
                        .frame(width: 36, height: 36)
                        .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
                    Image(systemName: "arrow.down.circle.fill")
                        .scaledFont(size: 28)
                        .foregroundColor(OmiColors.textSecondary)
                }
                // Activity pulse: subtle white glow when new content arrived below
                .overlay(
                    Circle()
                        .stroke(OmiColors.textSecondary.opacity(hasActivityBelow ? 0.6 : 0), lineWidth: 1.5)
                )
                .opacity(hasActivityBelow ? 1.0 : 0.85)
                .scaleEffect(hasActivityBelow ? 1.08 : 1.0)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Jump to latest message")
            .padding(.bottom, 16)
            .transition(.scale.combined(with: .opacity))
            .animation(.easeInOut(duration: 0.2), value: scrollMode)
            .animation(.easeInOut(duration: 0.3), value: hasActivityBelow)
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        guard scrollMode == .followingBottom else { return }
        // Don't fight the user — skip if they're actively wheel/trackpad scrolling
        guard !userIsScrolling else { return }
        guard !messages.isEmpty else { return }
        proxy.scrollTo("bottom-anchor", anchor: .bottom)
    }

    /// Throttled version of scrollToBottom — coalesces rapid calls (e.g. during
    /// streaming) so we scroll at most once per ~80ms instead of every token.
    /// This prevents the scroll → notify → state update → re-render → scroll
    /// feedback loop from saturating the main thread.
    private func throttledScrollToBottom(proxy: ScrollViewProxy) {
        guard !userIsScrolling else { return }
        // Cancel any pending scroll — we'll schedule a fresh one
        scrollThrottleWorkItem?.cancel()
        let workItem = DispatchWorkItem { [self] in
            scrollToBottom(proxy: proxy)
        }
        scrollThrottleWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08, execute: workItem)
    }
}
