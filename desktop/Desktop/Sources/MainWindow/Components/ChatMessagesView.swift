import SwiftUI

/// Detects user scroll-wheel / trackpad gestures on the enclosing NSScrollView
/// and fires a callback immediately — before the scroll position settles.
/// This wins the race against throttled programmatic scrolls during streaming.
private struct UserScrollDetector: NSViewRepresentable {
    let onUserScrollUp: () -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            context.coordinator.install(for: view)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onUserScrollUp: onUserScrollUp)
    }

    class Coordinator: NSObject {
        let onUserScrollUp: () -> Void
        private var monitor: Any?

        init(onUserScrollUp: @escaping () -> Void) {
            self.onUserScrollUp = onUserScrollUp
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

            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                guard let self = self, let targetScrollView = targetScrollView else { return event }
                // Only respond to events in our scroll view's window
                guard event.window == targetScrollView.window else { return event }
                // Check if the event location is inside our scroll view
                let locationInWindow = event.locationInWindow
                let locationInScrollView = targetScrollView.convert(locationInWindow, from: nil)
                guard targetScrollView.bounds.contains(locationInScrollView) else { return event }
                // deltaY > 0 means scrolling up (towards earlier content)
                if event.scrollingDeltaY > 0 {
                    self.onUserScrollUp()
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
    /// Tracks whether we should follow new content (survives the race between
    /// content growth and scroll position detection). Only set to false when
    /// the user actively scrolls up (not when content grows past the viewport).
    @State private var shouldFollowContent = true
    /// True while a programmatic scroll is in-flight, so we can distinguish
    /// user-initiated scrolls from our own.
    @State private var isProgrammaticScroll = false
    /// True for ~1s after the view appears, suppressing shouldFollowContent=false
    /// during the LazyVStack/Markdown layout settling period. Without this guard,
    /// content height changes from lazy rendering are misinterpreted as user scrolling.
    @State private var isSettlingAfterAppear = false
    /// Throttle token for scrollToBottom — prevents the streaming + scroll
    /// detection feedback loop from saturating the main thread.
    @State private var scrollThrottleWorkItem: DispatchWorkItem?
    /// True when the user is actively scrolling via scroll wheel/trackpad.
    /// Set immediately by the scroll wheel monitor to win the race against
    /// throttled programmatic scrolls during streaming.
    @State private var userIsScrolling = false
    @State private var userScrollEndWorkItem: DispatchWorkItem?

    var body: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .bottom) {
                ScrollView {
                    LazyVStack(spacing: 16) {
                        // Load more button at top
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

                        if isLoadingInitial && messages.isEmpty && sessionsLoadError == nil {
                            VStack(spacing: 12) {
                                Spacer()
                                ProgressView()
                                    .scaleEffect(0.8)
                                Text("Loading...")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textTertiary)
                                Spacer()
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if let error = sessionsLoadError, messages.isEmpty {
                            VStack(spacing: 16) {
                                Spacer()
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
                                            .background(
                                                RoundedRectangle(cornerRadius: 8)
                                                    .fill(OmiColors.purplePrimary)
                                            )
                                    }
                                    .buttonStyle(.plain)
                                }
                                Spacer()
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .padding(32)
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

                            // Invisible anchor for reliable scroll-to-bottom
                            Color.clear
                                .frame(height: 1)
                                .id("bottom-anchor")
                        }
                    }
                    .padding()
                    .textSelection(.enabled)
                    .background(
                        ScrollPositionDetector { atBottom in
                            isUserAtBottom = atBottom
                            if atBottom {
                                shouldFollowContent = true
                            } else if !isProgrammaticScroll && !isSettlingAfterAppear {
                                // Only stop following when the user actively scrolls up,
                                // not when content grows past the viewport, we're mid-scroll,
                                // or the view is still settling after (re-)appearing.
                                shouldFollowContent = false
                            }
                        }
                    )
                }
                .onChange(of: messages.count) { oldCount, newCount in
                    if newCount > oldCount || oldCount == 0 {
                        if shouldFollowContent || oldCount == 0 {
                            scrollToBottom(proxy: proxy)
                            // Extra scroll after layout settles for initial load
                            if oldCount == 0 {
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                    scrollToBottom(proxy: proxy)
                                }
                            }
                        }
                    }
                }
                .onChange(of: messages.last?.text) { _, _ in
                    if shouldFollowContent {
                        throttledScrollToBottom(proxy: proxy)
                    }
                }
                .onChange(of: messages.last?.contentBlocks.count) { _, _ in
                    if shouldFollowContent {
                        throttledScrollToBottom(proxy: proxy)
                    }
                }
                .onChange(of: isSending) { oldValue, newValue in
                    // When streaming starts, follow if we're at/near bottom
                    if newValue && !oldValue && isUserAtBottom {
                        shouldFollowContent = true
                    }
                }
                .background(
                    UserScrollDetector {
                        guard !isSettlingAfterAppear else { return }
                        // Immediately break out of follow mode — no delay
                        shouldFollowContent = false
                        userIsScrolling = true
                        // Cancel any pending programmatic scroll
                        scrollThrottleWorkItem?.cancel()
                        scrollThrottleWorkItem = nil
                        // Clear the scrolling flag after a short idle period
                        userScrollEndWorkItem?.cancel()
                        let endWork = DispatchWorkItem {
                            userIsScrolling = false
                        }
                        userScrollEndWorkItem = endWork
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: endWork)
                    }
                )
                .onAppear {
                    // Suppress scroll-detection false positives while content settles
                    isSettlingAfterAppear = true
                    // Scroll immediately, after initial layout, and after full settle
                    scrollToBottom(proxy: proxy)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        scrollToBottom(proxy: proxy)
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
                        scrollToBottom(proxy: proxy)
                    }
                    // Allow normal scroll detection after content has settled
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                        isSettlingAfterAppear = false
                    }
                }

                // Scroll to bottom button
                if !shouldFollowContent && !messages.isEmpty {
                    Button {
                        shouldFollowContent = true
                        scrollToBottom(proxy: proxy)
                    } label: {
                        Image(systemName: "arrow.down.circle.fill")
                            .scaledFont(size: 32)
                            .foregroundColor(OmiColors.purplePrimary)
                            .background(
                                Circle()
                                    .fill(OmiColors.backgroundPrimary)
                                    .frame(width: 28, height: 28)
                            )
                            .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, 16)
                    .transition(.scale.combined(with: .opacity))
                    .animation(.easeInOut(duration: 0.2), value: shouldFollowContent)
                }
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        // Don't fight the user — skip if they're actively scrolling up
        guard !userIsScrolling else { return }
        guard !messages.isEmpty else { return }
        isProgrammaticScroll = true
        proxy.scrollTo("bottom-anchor", anchor: .bottom)
        // Reset after a short delay to allow the scroll to settle
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            isProgrammaticScroll = false
        }
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
