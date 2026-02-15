import SwiftUI
import Combine

/// Manages task-scoped chat sessions using the shared ChatProvider.
/// Saves/restores ChatProvider state when entering/leaving task chat
/// so the main Chat tab remains unaffected.
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

    /// Which task currently has an active AI stream
    @Published var streamingTaskId: String?
    /// Tasks with unseen AI responses (finished while user wasn't viewing)
    @Published var unreadTaskIds: Set<String> = []
    /// Human-readable status text for the active stream (e.g. "Thinking...", "Querying database")
    @Published var streamingStatus: String = ""

    private let chatProvider: ChatProvider
    private var cancellables = Set<AnyCancellable>()

    /// Saved state from before we switched to task chat
    private var savedSession: ChatSession?
    private var savedMessages: [ChatMessage] = []
    private var savedIsInDefaultChat = true
    private var savedWorkingDirectory: String?
    private var savedOverrideAppId: String?

    /// Per-task message cache so we don't lose in-flight streaming messages
    private var taskMessagesCache: [String: [ChatMessage]] = [:]

    /// App ID used to isolate task chat messages from the default chat
    static let taskChatAppId = "task-chat"

    init(chatProvider: ChatProvider) {
        self.chatProvider = chatProvider
        observeChatStatus()
    }

    // MARK: - Status Observation

    private func observeChatStatus() {
        // Track when streaming starts/stops (only for task chat sessions)
        chatProvider.$isSending
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isSending in
                guard let self else { return }
                // Only track when we're in task chat mode
                guard self.chatProvider.overrideAppId == Self.taskChatAppId else { return }
                if isSending {
                    // Streaming started — record which task is streaming
                    self.streamingTaskId = self.activeTaskId
                } else if let taskId = self.streamingTaskId {
                    // Streaming finished — mark unread if panel not showing this task
                    if !self.isPanelOpen || self.activeTaskId != taskId {
                        self.unreadTaskIds.insert(taskId)
                    }
                    self.streamingTaskId = nil
                    self.streamingStatus = ""
                }
            }
            .store(in: &cancellables)

        // Derive status text from the last AI message's content blocks
        chatProvider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self] messages in
                guard let self,
                      self.chatProvider.isSending,
                      self.streamingTaskId != nil else { return }
                self.streamingStatus = self.deriveStreamingStatus(from: messages)
            }
            .store(in: &cancellables)
    }

    private func deriveStreamingStatus(from messages: [ChatMessage]) -> String {
        guard let lastAI = messages.last(where: { $0.sender == .ai }),
              lastAI.isStreaming else {
            return "Responding..."
        }

        // Check content blocks in reverse for most recent activity
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

    /// Open (or resume) a chat panel for a task.
    /// Creates a new Firestore ChatSession if the task doesn't have one yet.
    /// The initial prompt is placed in `pendingInputText` for the user to review before sending.
    func openChat(for task: TaskActionItem) async {
        log("TaskChatCoordinator: openChat for \(task.id), activeTaskId=\(activeTaskId ?? "nil"), isPanelOpen=\(isPanelOpen), isOpening=\(isOpening)")

        // If already viewing this task's chat, re-establish ChatProvider state
        // (another page may have changed the shared provider while we were away)
        if activeTaskId == task.id {
            log("TaskChatCoordinator: same task, restoring provider state")
            markAsRead(task.id)
            chatProvider.overrideAppId = Self.taskChatAppId

            // If bridge is still streaming for this task, restore cached messages
            // so the live updates continue showing. Otherwise reload from backend.
            if chatProvider.isSending, let cached = taskMessagesCache[task.id] {
                log("TaskChatCoordinator: restoring cached messages (bridge still streaming)")
                chatProvider.messages = cached
                taskMessagesCache.removeValue(forKey: task.id)
            } else if let sessionId = task.chatSessionId {
                let session = ChatSession(id: sessionId, title: taskChatTitle(for: task))
                await chatProvider.selectSession(session, force: true)
            }
            isPanelOpen = true
            return
        }

        // Prevent duplicate open calls while one is in progress
        guard !isOpening else {
            log("TaskChatCoordinator: already opening, skipping")
            return
        }
        isOpening = true
        defer { isOpening = false }

        // Cache current task's messages before switching (preserves in-flight streaming)
        if let currentTaskId = activeTaskId, !chatProvider.messages.isEmpty {
            taskMessagesCache[currentTaskId] = chatProvider.messages
        }

        // Save current ChatProvider state on first open
        if activeTaskId == nil {
            savedSession = chatProvider.currentSession
            savedMessages = chatProvider.messages
            savedIsInDefaultChat = chatProvider.isInDefaultChat
            savedWorkingDirectory = chatProvider.workingDirectory
            savedOverrideAppId = chatProvider.overrideAppId
        }

        activeTaskId = task.id
        markAsRead(task.id)

        // Set workspace path for file-system tools (only if explicitly configured)
        let configuredPath = TaskAgentSettings.shared.workingDirectory
        if !configuredPath.isEmpty {
            workspacePath = configuredPath
            chatProvider.workingDirectory = workspacePath
        }
        // Isolate task messages from the default chat
        chatProvider.overrideAppId = Self.taskChatAppId

        // Check if we have cached messages for this task (e.g. switching back while streaming)
        if let cached = taskMessagesCache[task.id] {
            log("TaskChatCoordinator: restoring \(cached.count) cached messages for task \(task.id)")
            chatProvider.messages = cached
            if let sessionId = task.chatSessionId {
                chatProvider.currentSession = ChatSession(id: sessionId, title: taskChatTitle(for: task))
                chatProvider.isInDefaultChat = false
            }
            taskMessagesCache.removeValue(forKey: task.id)
            isPanelOpen = true
            return
        }

        // Check if task already has a chat session with messages
        var needsNewSession = true
        if let sessionId = task.chatSessionId {
            // Try to resume existing session
            let session = ChatSession(id: sessionId, title: taskChatTitle(for: task))
            await chatProvider.selectSession(session)

            if !chatProvider.messages.isEmpty {
                // Session has messages, resume it
                needsNewSession = false
            } else {
                log("TaskChatCoordinator: session \(sessionId) is empty (previous attempt failed), creating new session")
            }
        }

        if needsNewSession {
            // Create a fresh session for this task
            if let session = await chatProvider.createNewSession(title: taskChatTitle(for: task), skipGreeting: true, appId: "task-chat") {
                // Persist the session ID to the task's local storage
                try? await ActionItemStorage.shared.updateChatSessionId(
                    taskId: task.id,
                    sessionId: session.id
                )
                // Also update the in-memory task in the store
                TasksStore.shared.updateChatSessionId(taskId: task.id, sessionId: session.id)

                // Pre-fill the input with context so the user can review before sending
                pendingInputText = buildInitialPrompt(for: task)
            }
        }

        isPanelOpen = true
    }

    /// Switch the chat panel to a different task's session.
    func switchToTask(_ task: TaskActionItem) async {
        guard task.id != activeTaskId else { return }
        await openChat(for: task)
    }

    /// Close the task chat panel and restore previous ChatProvider state.
    func closeChat() async {
        // Cache current task's messages (preserves in-flight streaming)
        if let currentTaskId = activeTaskId, !chatProvider.messages.isEmpty {
            taskMessagesCache[currentTaskId] = chatProvider.messages
        }

        isPanelOpen = false
        activeTaskId = nil
        pendingInputText = ""

        // Restore previous ChatProvider state
        chatProvider.workingDirectory = savedWorkingDirectory
        chatProvider.overrideAppId = savedOverrideAppId
        if savedIsInDefaultChat {
            await chatProvider.switchToDefaultChat()
        } else if let saved = savedSession {
            await chatProvider.selectSession(saved)
        }

        savedSession = nil
        savedMessages = []
        savedIsInDefaultChat = true
        savedWorkingDirectory = nil
        savedOverrideAppId = nil
    }

    /// Build the initial context prompt for a task chat session.
    /// Uses the same shared prompt as the tmux agent (TaskAgentSettings.buildTaskPrompt).
    private func buildInitialPrompt(for task: TaskActionItem) -> String {
        TaskAgentSettings.shared.buildTaskPrompt(for: task)
    }

    private func taskChatTitle(for task: TaskActionItem) -> String {
        let desc = task.description
        let maxLen = 40
        if desc.count > maxLen {
            return String(desc.prefix(maxLen)) + "..."
        }
        return desc
    }
}
