import SwiftUI
import MarkdownUI

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

                        if isLoadingInitial && messages.isEmpty {
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
        if let lastMessage = messages.last {
            isProgrammaticScroll = true
            proxy.scrollTo(lastMessage.id, anchor: .bottom)
            // Reset after a short delay to allow the scroll to settle
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                isProgrammaticScroll = false
            }
        }
    }

    /// Throttled version of scrollToBottom — coalesces rapid calls (e.g. during
    /// streaming) so we scroll at most once per ~80ms instead of every token.
    /// This prevents the scroll → notify → state update → re-render → scroll
    /// feedback loop from saturating the main thread.
    private func throttledScrollToBottom(proxy: ScrollViewProxy) {
        // Cancel any pending scroll — we'll schedule a fresh one
        scrollThrottleWorkItem?.cancel()
        let workItem = DispatchWorkItem { [self] in
            scrollToBottom(proxy: proxy)
        }
        scrollThrottleWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08, execute: workItem)
    }
}
