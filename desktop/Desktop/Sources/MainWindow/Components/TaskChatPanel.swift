import SwiftUI

/// Compact chat panel for the task sidebar.
/// Displays task-scoped chat using the shared ChatProvider via TaskChatCoordinator.
struct TaskChatPanel: View {
    @ObservedObject var chatProvider: ChatProvider
    @ObservedObject var coordinator: TaskChatCoordinator
    let task: TaskActionItem?
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Compact header
            panelHeader

            Divider()
                .background(OmiColors.backgroundTertiary)

            if coordinator.isOpening {
                // Loading state while session is being created
                VStack(spacing: 12) {
                    Spacer()
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Setting up chat...")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Messages area
                ChatMessagesView(
                    messages: chatProvider.messages,
                    isSending: chatProvider.isSending,
                    hasMoreMessages: chatProvider.hasMoreMessages,
                    isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
                    isLoadingInitial: chatProvider.isLoading,
                    app: nil,
                    onLoadMore: { await chatProvider.loadMoreMessages() },
                    onRate: { messageId, rating in
                        Task { await chatProvider.rateMessage(messageId, rating: rating) }
                    },
                    welcomeContent: { taskWelcome }
                )

                // Input area
                ChatInputView(
                    onSend: { text in
                        Task { await chatProvider.sendMessage(text) }
                    },
                    onFollowUp: { text in
                        Task { await chatProvider.sendFollowUp(text) }
                    },
                    onStop: {
                        chatProvider.stopAgent()
                    },
                    isSending: chatProvider.isSending,
                    placeholder: "Ask about this task...",
                    mode: $chatProvider.chatMode
                )
                .padding(12)
            }
        }
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Header

    /// Abbreviate a path for display: ~/Projects/my-app
    private var displayPath: String {
        let path = coordinator.workspacePath
        let home = NSHomeDirectory()
        if path.hasPrefix(home) {
            return "~" + path.dropFirst(home.count)
        }
        return path
    }

    private var panelHeader: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Task Chat")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                if let task = task {
                    Text(task.description)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }

                Spacer()

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("Close chat panel")
            }

            // Workspace path indicator
            HStack(spacing: 4) {
                Image(systemName: "folder")
                    .scaledFont(size: 9)
                Text(displayPath)
                    .scaledFont(size: 10)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
            }
            .foregroundColor(OmiColors.textTertiary.opacity(0.7))
            .padding(.top, 4)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
    }

    // MARK: - Welcome

    private var taskWelcome: some View {
        VStack(spacing: 12) {
            Image(systemName: "bubble.left.and.bubble.right")
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.textTertiary.opacity(0.5))

            Text("Chat about this task")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text("Ask questions, get suggestions, or discuss implementation details.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
