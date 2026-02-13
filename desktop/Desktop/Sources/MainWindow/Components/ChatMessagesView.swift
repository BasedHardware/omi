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

    @State private var isUserAtBottom = true

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
                                    .font(.system(size: 13))
                                    .foregroundColor(OmiColors.textTertiary)
                                Spacer()
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if messages.isEmpty {
                            welcomeContent()
                        } else {
                            ForEach(messages) { message in
                                ChatBubble(
                                    message: message,
                                    app: app,
                                    onRate: { rating in
                                        onRate(message.id, rating)
                                    },
                                    onCitationTap: { citation in
                                        onCitationTap?(citation)
                                    }
                                )
                                .id(message.id)
                            }
                        }
                    }
                    .padding()
                    .background(
                        ScrollPositionDetector { atBottom in
                            if isUserAtBottom != atBottom {
                                isUserAtBottom = atBottom
                            }
                        }
                    )
                }
                .onChange(of: messages.count) { oldCount, newCount in
                    if newCount > oldCount || oldCount == 0 {
                        if isUserAtBottom || oldCount == 0 {
                            scrollToBottom(proxy: proxy)
                        }
                    }
                }
                .onChange(of: messages.last?.text) { _, _ in
                    if isUserAtBottom {
                        scrollToBottom(proxy: proxy)
                    }
                }
                .onAppear {
                    scrollToBottom(proxy: proxy)
                }

                // Scroll to bottom button
                if !isUserAtBottom && !messages.isEmpty {
                    Button {
                        isUserAtBottom = true
                        scrollToBottom(proxy: proxy)
                    } label: {
                        Image(systemName: "arrow.down.circle.fill")
                            .font(.system(size: 32))
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
                    .animation(.easeInOut(duration: 0.2), value: isUserAtBottom)
                }
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if let lastMessage = messages.last {
            withAnimation(.easeOut(duration: 0.1)) {
                proxy.scrollTo(lastMessage.id, anchor: .bottom)
            }
        }
    }
}
