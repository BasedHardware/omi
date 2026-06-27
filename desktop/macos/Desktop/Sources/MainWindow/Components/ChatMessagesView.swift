import SwiftUI

/// Detects user scroll-wheel / trackpad gestures on the enclosing NSScrollView
/// and fires a callback immediately — before the scroll position settles.
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

            monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .leftMouseDown, .leftMouseDragged]) { [weak self] event in
                guard let self = self, let targetScrollView = targetScrollView else { return event }
                // Only respond to events in our scroll view's window
                guard event.window == targetScrollView.window else { return event }
                // Check if the event location is inside our scroll view
                let locationInWindow = event.locationInWindow
                let locationInScrollView = targetScrollView.convert(locationInWindow, from: nil)
                guard targetScrollView.bounds.contains(locationInScrollView) else { return event }
                // Any physical wheel/trackpad scroll or mouse drag/click inside the transcript is reader intent.
                if event.type == .scrollWheel {
                    if event.scrollingDeltaY != 0 || event.scrollingDeltaX != 0 {
                        self.onUserScroll()
                    }
                } else {
                    self.onUserScroll()
                }
                return event
            }
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
private enum ChatScrollMode: Equatable {
    case followingBottom
    case freeScrolling
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

    @State private var isUserAtBottom = true
    /// Source of truth for scroll intent. Geometry/layout changes alone must NOT
    /// switch this to `.freeScrolling` — only physical wheel/trackpad user scroll.
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
        .onChange(of: messages.count) { oldCount, newCount in
            if newCount > oldCount || oldCount == 0 {
                if scrollMode == .followingBottom || oldCount == 0 {
                    scrollToBottom(proxy: proxy)
                    if oldCount == 0 {
                        scheduleInitialScroll(proxy: proxy, delay: 0.3)
                    }
                }
            }
        }
        .onChange(of: messages.last?.text) { _, _ in
            if scrollMode == .followingBottom {
                throttledScrollToBottom(proxy: proxy)
            }
        }
        .onChange(of: messages.last?.contentBlocks.count) { _, _ in
            if scrollMode == .followingBottom {
                throttledScrollToBottom(proxy: proxy)
            }
        }
        .onChange(of: isSending) { oldValue, newValue in
            if newValue && !oldValue {
                cancelAllPendingScrolls()
                userIsScrolling = false
                scrollMode = .followingBottom
                scrollToBottom(proxy: proxy)
            }
        }
        .onAppear {
            if scrollMode == .followingBottom {
                scrollToBottom(proxy: proxy)
                scheduleInitialScroll(proxy: proxy, delay: 0.3)
                scheduleInitialScroll(proxy: proxy, delay: 0.7)
            }
        }
        .onDisappear {
            cancelAllPendingScrolls()
        }
    }

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

    @ViewBuilder
    private var loadMoreButton: some View {
        if hasMoreMessages {
            Button {
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
                // atBottom == false alone must NOT switch to freeScrolling.
                // Geometry/layout changes (content growth, markdown layout,
                // LazyVStack realization, citations, window resize) can make
                // the viewport not-at-bottom without user intent.
                // Only atBottom == true updates isUserAtBottom tracking.
            }
            UserScrollDetector {
                scrollMode = .freeScrolling
                userIsScrolling = true
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
        if scrollMode == .freeScrolling && !messages.isEmpty {
            Button {
                cancelAllPendingScrolls()
                userIsScrolling = false
                scrollMode = .followingBottom
                scrollToBottom(proxy: proxy)
            } label: {
                Image(systemName: "arrow.down.circle.fill")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textSecondary)
                    .background(
                        Circle()
                            .fill(OmiColors.backgroundPrimary)
                            .frame(width: 28, height: 28)
                    )
                    .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Jump to latest message")
            .padding(.bottom, 16)
            .transition(.scale.combined(with: .opacity))
            .animation(.easeInOut(duration: 0.2), value: scrollMode)
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
