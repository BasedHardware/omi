import SwiftUI

/// Compact chat panel for the task sidebar.
/// Displays task-scoped chat using an independent TaskChatState per task.
struct TaskChatPanel: View {
    @ObservedObject var taskState: TaskChatState
    @ObservedObject var coordinator: TaskChatCoordinator
    let task: TaskActionItem?
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Compact header
            panelHeader

            Divider()
                .background(OmiColors.backgroundTertiary)

            if coordinator.activeTaskId == nil {
                // No task selected — prompt user to pick one
                noTaskSelectedView
            } else if coordinator.isOpening {
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
                    messages: taskState.messages,
                    isSending: taskState.isSending,
                    hasMoreMessages: false,
                    isLoadingMoreMessages: false,
                    isLoadingInitial: false,
                    app: nil,
                    onLoadMore: { },
                    onRate: { _, _ in },
                    welcomeContent: { taskWelcome }
                )

                // Error banner
                if let error = taskState.errorMessage {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(OmiColors.warning)
                            .scaledFont(size: 14)
                        Text(error)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textSecondary)
                        Spacer()
                        Button {
                            taskState.errorMessage = nil
                        } label: {
                            Image(systemName: "xmark")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(OmiColors.backgroundSecondary)
                }

                // Input area
                ChatInputView(
                    onSend: { text in
                        AnalyticsManager.shared.chatMessageSent(messageLength: text.count, source: "task_chat")
                        Task { await taskState.sendMessage(text) }
                    },
                    onFollowUp: { text in
                        Task { await taskState.sendFollowUp(text) }
                    },
                    onStop: {
                        taskState.stopAgent()
                    },
                    isSending: taskState.isSending,
                    isStopping: taskState.isStopping,
                    placeholder: "Ask about this task...",
                    mode: $taskState.chatMode,
                    pendingText: $coordinator.pendingInputText,
                    inputText: $taskState.draftText
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

                Text(task?.description ?? "Task Chat")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.tail)

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

            // Workspace path indicator (only when a task is active)
            if coordinator.activeTaskId != nil {
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
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
    }

    // MARK: - Empty State

    private var noTaskSelectedView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "text.bubble")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.textTertiary.opacity(0.4))

            Text("Select a task to chat")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text("Click on any task in the list to start a conversation about it.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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

/// Placeholder shown when the chat panel is open but no task is selected.
struct TaskChatPanelPlaceholder: View {
    @ObservedObject var coordinator: TaskChatCoordinator
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)
                Text("Task Chat")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
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
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary.opacity(0.5))

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Empty state
            VStack(spacing: 16) {
                Spacer()
                Image(systemName: "text.bubble")
                    .scaledFont(size: 36)
                    .foregroundColor(OmiColors.textTertiary.opacity(0.4))
                Text("Select a task to chat")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                Text("Click on any task in the list to start a conversation about it.")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(OmiColors.backgroundPrimary)
    }
}
