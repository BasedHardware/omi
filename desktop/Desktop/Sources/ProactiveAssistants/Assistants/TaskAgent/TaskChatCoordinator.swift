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

    /// The workspace path used for file-system tools in task chat
    @Published var workspacePath: String = TaskAgentSettings.shared.workingDirectory

    private let chatProvider: ChatProvider

    /// Saved state from before we switched to task chat
    private var savedSession: ChatSession?
    private var savedMessages: [ChatMessage] = []
    private var savedIsInDefaultChat = true
    private var savedWorkingDirectory: String?
    private var savedOverrideAppId: String?

    /// App ID used to isolate task chat messages from the default chat
    static let taskChatAppId = "task-chat"

    init(chatProvider: ChatProvider) {
        self.chatProvider = chatProvider
    }

    /// Open (or resume) a chat panel for a task.
    /// Creates a new Firestore ChatSession if the task doesn't have one yet.
    func openChat(for task: TaskActionItem) async {
        // If already viewing this task's chat, just ensure panel is open
        if activeTaskId == task.id {
            isPanelOpen = true
            return
        }

        // Prevent duplicate open calls while one is in progress
        guard !isOpening else { return }
        isOpening = true
        defer { isOpening = false }

        // Save current ChatProvider state on first open
        if activeTaskId == nil {
            savedSession = chatProvider.currentSession
            savedMessages = chatProvider.messages
            savedIsInDefaultChat = chatProvider.isInDefaultChat
            savedWorkingDirectory = chatProvider.workingDirectory
            savedOverrideAppId = chatProvider.overrideAppId
        }

        activeTaskId = task.id

        // Set workspace path for file-system tools (only if explicitly configured)
        let configuredPath = TaskAgentSettings.shared.workingDirectory
        if !configuredPath.isEmpty {
            workspacePath = configuredPath
            chatProvider.workingDirectory = workspacePath
        }
        // Isolate task messages from the default chat
        chatProvider.overrideAppId = Self.taskChatAppId

        // Check if task already has a chat session
        if let sessionId = task.chatSessionId {
            // Resume existing session
            let session = ChatSession(id: sessionId, title: taskChatTitle(for: task))
            await chatProvider.selectSession(session)
        } else {
            // Create a new session for this task
            if let session = await chatProvider.createNewSession(title: taskChatTitle(for: task), skipGreeting: true, appId: "task-chat") {
                // Persist the session ID to the task's local storage
                try? await ActionItemStorage.shared.updateChatSessionId(
                    taskId: task.id,
                    sessionId: session.id
                )
                // Also update the in-memory task in the store
                TasksStore.shared.updateChatSessionId(taskId: task.id, sessionId: session.id)

                // Send initial context message about the task (fire-and-forget so panel opens immediately)
                let contextMessage = buildInitialPrompt(for: task)
                let provider = chatProvider
                Task { await provider.sendMessage(contextMessage) }
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
        isPanelOpen = false
        activeTaskId = nil

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
    /// Uses task.chatContext which lives on the model itself — add new fields there.
    private func buildInitialPrompt(for task: TaskActionItem) -> String {
        var prompt = "I'd like help with this task.\n\n\(task.chatContext)"

        // Live agent output (from running/completed session, not persisted on the model)
        if let session = TaskAgentManager.shared.getSession(for: task.id),
           let output = session.output, !output.isEmpty {
            let truncated = String(output.prefix(2000))
            prompt += "\n\nAgent output so far:\n\(truncated)"
        }

        return prompt
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
