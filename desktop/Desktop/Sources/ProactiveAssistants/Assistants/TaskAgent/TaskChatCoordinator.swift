import SwiftUI
import Combine

/// Manages task-scoped chat sessions using independent TaskChatState per task.
/// Each task gets its own bridge process, messages, and sending state.
/// The sidebar ChatProvider is completely untouched.
@MainActor
class TaskChatCoordinator: ObservableObject {
    @Published var activeTaskId: String?
    @Published var isPanelOpen = false
    @Published var isOpening = false

    /// Text to pre-fill in the chat input field (consumed by the UI).
    @Published var pendingInputText: String = ""

    /// The workspace path used for file-system tools in task chat
    @Published var workspacePath: String = TaskAgentSettings.shared.workingDirectory

    // MARK: - Chat Status Tracking

    /// Tasks that currently have an active AI stream (supports parallel agents)
    @Published var streamingTaskIds: Set<String> = []
    /// Tasks with unseen AI responses (finished while user wasn't viewing)
    @Published var unreadTaskIds: Set<String> = []
    /// Per-task human-readable status text for active streams
    @Published var streamingStatuses: [String: String] = [:]

    /// The currently active TaskChatState (drives the UI)
    @Published var activeTaskState: TaskChatState?

    /// Per-task chat states — each has its own bridge process and messages
    private var taskStates: [String: TaskChatState] = [:]

    private let chatProvider: ChatProvider
    private var cancellables = Set<AnyCancellable>()
    /// Per-task Combine subscriptions for streaming observation
    private var taskCancellables: [String: Set<AnyCancellable>] = [:]

    init(chatProvider: ChatProvider) {
        self.chatProvider = chatProvider
    }

    // MARK: - Status Observation (per-task)

    /// Subscribe to a TaskChatState's streaming changes for status tracking.
    private func observeTaskState(_ state: TaskChatState) {
        var subs = Set<AnyCancellable>()
        let taskId = state.taskId

        // Track when streaming starts/stops
        state.$isSending
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isSending in
                guard let self else { return }
                if isSending {
                    self.streamingTaskIds.insert(taskId)
                } else {
                    // Streaming finished — remove from active set
                    self.streamingTaskIds.remove(taskId)
                    self.streamingStatuses.removeValue(forKey: taskId)
                    // Mark unread if panel not showing this task
                    if !self.isPanelOpen || self.activeTaskId != taskId {
                        self.unreadTaskIds.insert(taskId)
                    }
                }
            }
            .store(in: &subs)

        // Derive status text from the last AI message's content blocks
        state.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self, weak state] messages in
                guard let self, let state, state.isSending,
                      self.streamingTaskIds.contains(taskId) else { return }
                self.streamingStatuses[taskId] = self.deriveStreamingStatus(from: messages)
            }
            .store(in: &subs)

        taskCancellables[taskId] = subs
    }

    private func deriveStreamingStatus(from messages: [ChatMessage]) -> String {
        guard let lastAI = messages.last(where: { $0.sender == .ai }),
              lastAI.isStreaming else {
            return "Responding..."
        }

        for block in lastAI.contentBlocks.reversed() {
            if case .toolCall(_, let name, .running, _, _, _) = block {
                return ChatContentBlock.displayName(for: name)
            }
            if case .thinking = block {
                return "Thinking..."
            }
        }
        return "Responding..."
    }

    /// Mark a task's chat as read (clears unread dot)
    func markAsRead(_ taskId: String) {
        unreadTaskIds.remove(taskId)
    }

    // MARK: - Open / Close

    /// Open (or resume) a chat panel for a task.
    /// Gets or creates a TaskChatState, wires its system prompt, and activates it.
    func openChat(for task: TaskActionItem) async {
        log("TaskChatCoordinator: openChat for \(task.id), activeTaskId=\(activeTaskId ?? "nil"), isPanelOpen=\(isPanelOpen)")

        // Prevent duplicate open calls
        guard !isOpening else {
            log("TaskChatCoordinator: already opening, skipping")
            return
        }
        isOpening = true
        defer { isOpening = false }

        activeTaskId = task.id
        markAsRead(task.id)

        // Get or create TaskChatState
        let state: TaskChatState
        if let existing = taskStates[task.id] {
            state = existing
        } else {
            let configuredPath = TaskAgentSettings.shared.workingDirectory
            let ws = configuredPath.isEmpty ? (FileManager.default.homeDirectoryForCurrentUser.path) : configuredPath
            let useACP = UserDefaults.standard.string(forKey: "chatBridgeMode") == "claudeCode"
            state = TaskChatState(taskId: task.id, workspacePath: ws, useACPMode: useACP)
            // Wire system prompt builder to use ChatProvider's cached context (without history)
            state.systemPromptBuilder = { [weak self] in
                self?.chatProvider.buildTaskChatSystemPrompt() ?? ""
            }
            taskStates[task.id] = state
            observeTaskState(state)

            // Load persisted messages from GRDB
            await state.loadPersistedMessages()
        }

        activeTaskState = state

        // Pre-fill initial prompt if chat has no messages yet
        if state.messages.isEmpty {
            pendingInputText = buildInitialPrompt(for: task)
        } else {
            pendingInputText = ""
        }

        isPanelOpen = true
    }

    /// Switch the chat panel to a different task's session.
    func switchToTask(_ task: TaskActionItem) async {
        guard task.id != activeTaskId else { return }
        await openChat(for: task)
    }

    /// Close the task chat panel. States persist in dictionary for later resumption.
    func closeChat() {
        isPanelOpen = false
        activeTaskId = nil
        activeTaskState = nil
        pendingInputText = ""
    }

    // MARK: - Helpers

    private func buildInitialPrompt(for task: TaskActionItem) -> String {
        TaskAgentSettings.shared.buildTaskPrompt(for: task)
    }
}
