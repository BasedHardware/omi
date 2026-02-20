import SwiftUI
import Combine

/// Per-task chat state with its own bridge process and message history.
/// Each task chat is fully independent — no shared state with the sidebar chat.
/// Uses Claude SDK's native `resume: sessionId` for conversation persistence.
@MainActor
class TaskChatState: ObservableObject {
    let taskId: String

    @Published var messages: [ChatMessage] = []
    @Published var isSending = false
    @Published var isStopping = false
    @Published var draftText = ""
    @Published var errorMessage: String?
    @Published var chatMode: ChatMode = .act

    /// Bridge mode — determines which bridge process to use
    let useACPMode: Bool

    /// Own bridge process — completely independent from sidebar chat
    private var claudeBridge: ClaudeAgentBridge?
    private var acpBridge: ACPBridge?
    private var bridgeStarted = false

    /// Claude SDK session ID for resume (conversation continuity, Mode A only)
    var claudeSessionId: String?

    /// Workspace path for file-system tools
    let workspacePath: String

    /// Closure to build system prompt from ChatProvider's cached data
    var systemPromptBuilder: (() -> String)?

    /// Auth callbacks for ACP mode
    var onAuthRequired: ACPBridge.AuthRequiredHandler?
    var onAuthSuccess: ACPBridge.AuthSuccessHandler?

    /// Follow-up chaining
    private var pendingFollowUpText: String?

    // MARK: - Streaming Buffers (mirrored from ChatProvider)

    private var streamingTextBuffer: String = ""
    private var streamingThinkingBuffer: String = ""
    private var streamingBufferMessageId: String?
    private var streamingFlushWorkItem: DispatchWorkItem?
    private let streamingFlushInterval: TimeInterval = 0.1

    /// Whether persisted messages have been loaded from GRDB
    private var hasLoadedFromStorage = false

    init(taskId: String, workspacePath: String, useACPMode: Bool = false) {
        self.taskId = taskId
        self.workspacePath = workspacePath
        self.useACPMode = useACPMode
    }

    // MARK: - Persistence

    /// Load persisted messages from GRDB (called once when chat is opened)
    func loadPersistedMessages() async {
        guard !hasLoadedFromStorage else { return }
        hasLoadedFromStorage = true

        do {
            let records = try await TaskChatMessageStorage.shared.getMessages(forTaskId: taskId)
            guard !records.isEmpty else { return }

            messages = records.map { $0.toChatMessage() }

            // Restore ACP session ID from stored messages
            if claudeSessionId == nil {
                claudeSessionId = try? await TaskChatMessageStorage.shared.getACPSessionId(forTaskId: taskId)
            }

            log("TaskChatState[\(taskId)]: Loaded \(records.count) persisted messages")
        } catch {
            logError("TaskChatState[\(taskId)]: Failed to load persisted messages", error: error)
        }
    }

    /// Persist a message to GRDB (fire-and-forget)
    private func persistMessage(_ message: ChatMessage) {
        let taskId = self.taskId
        let sessionId = self.claudeSessionId
        Task.detached {
            do {
                try await TaskChatMessageStorage.shared.saveMessage(message, taskId: taskId, acpSessionId: sessionId)
            } catch {
                logError("TaskChatState[\(taskId)]: Failed to persist message \(message.id)", error: error)
            }
        }
    }

    /// Update a persisted message (for finalizing AI streaming)
    private func updatePersistedMessage(_ message: ChatMessage) {
        let taskId = self.taskId
        Task.detached {
            do {
                let blocksJson: String?
                if message.sender == .ai && !message.contentBlocks.isEmpty {
                    // Re-encode through the record's serialization
                    let record = TaskChatMessageRecord.from(message, taskId: taskId)
                    blocksJson = record.contentBlocksJson
                } else {
                    blocksJson = nil
                }
                try await TaskChatMessageStorage.shared.updateMessage(
                    messageId: message.id,
                    text: message.text,
                    contentBlocksJson: blocksJson
                )
            } catch {
                logError("TaskChatState[\(taskId)]: Failed to update persisted message \(message.id)", error: error)
            }
        }
    }

    deinit {
        if let bridge = claudeBridge {
            Task { await bridge.stop() }
        }
        if let bridge = acpBridge {
            Task { await bridge.stop() }
        }
    }

    // MARK: - Bridge Lifecycle

    private func ensureBridgeStarted() async -> Bool {
        if bridgeStarted {
            let alive: Bool
            if useACPMode {
                alive = await acpBridge?.isAlive ?? false
            } else {
                alive = await claudeBridge?.isAlive ?? false
            }
            if !alive {
                log("TaskChatState[\(taskId)]: Bridge process died, will restart")
                bridgeStarted = false
                claudeSessionId = nil
            }
        }
        guard !bridgeStarted else { return true }
        do {
            if useACPMode {
                let bridge = ACPBridge()
                try await bridge.start()
                acpBridge = bridge
            } else {
                let bridge = ClaudeAgentBridge()
                try await bridge.start()
                claudeBridge = bridge
            }
            bridgeStarted = true
            log("TaskChatState[\(taskId)]: Bridge started (mode=\(useACPMode ? "ACP" : "Claude"))")
            return true
        } catch {
            logError("TaskChatState[\(taskId)]: Failed to start bridge", error: error)
            errorMessage = "AI not available: \(error.localizedDescription)"
            return false
        }
    }

    // MARK: - Send Message

    func sendMessage(_ text: String, isFollowUp: Bool = false) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        guard !isSending else {
            log("TaskChatState[\(taskId)]: sendMessage called while already sending, ignoring")
            return
        }

        guard await ensureBridgeStarted() else { return }

        isSending = true
        errorMessage = nil

        // Add user message to local messages and persist
        // Skip for follow-ups — sendFollowUp() already added and persisted it
        if !isFollowUp {
            let userMessage = ChatMessage(
                id: UUID().uuidString,
                text: trimmedText,
                sender: .user
            )
            messages.append(userMessage)
            persistMessage(userMessage)
        }

        // Create placeholder AI message
        let aiMessageId = UUID().uuidString
        let aiMessage = ChatMessage(
            id: aiMessageId,
            text: "",
            sender: .ai,
            isStreaming: true
        )
        messages.append(aiMessage)

        do {
            let systemPrompt = systemPromptBuilder?() ?? ""

            let textDeltaHandler: @Sendable (String) -> Void = { [weak self] delta in
                Task { @MainActor [weak self] in
                    self?.appendToMessage(id: aiMessageId, text: delta)
                }
            }
            let toolCallHandler: @Sendable (String, String, [String: Any]) async -> String = { callId, name, input in
                let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
                let result = await ChatToolExecutor.execute(toolCall)
                log("TaskChat OMI tool \(name) executed for callId=\(callId)")
                return result
            }
            let toolActivityHandler: @Sendable (String, String, String?, [String: Any]?) -> Void = { [weak self] name, status, toolUseId, input in
                Task { @MainActor [weak self] in
                    self?.addToolActivity(
                        messageId: aiMessageId,
                        toolName: name,
                        status: status == "started" ? .running : .completed,
                        toolUseId: toolUseId,
                        input: input
                    )
                }
            }
            let thinkingDeltaHandler: @Sendable (String) -> Void = { [weak self] text in
                Task { @MainActor [weak self] in
                    self?.appendThinking(messageId: aiMessageId, text: text)
                }
            }
            let toolResultDisplayHandler: @Sendable (String, String, String) -> Void = { [weak self] toolUseId, name, output in
                Task { @MainActor [weak self] in
                    self?.addToolResult(messageId: aiMessageId, toolUseId: toolUseId, name: name, output: output)
                }
            }

            let queryResult: ACPBridge.QueryResult
            if useACPMode, let bridge = acpBridge {
                // ACP mode — session reuse handled internally by the bridge
                queryResult = try await bridge.query(
                    prompt: trimmedText,
                    systemPrompt: systemPrompt,
                    cwd: workspacePath.isEmpty ? nil : workspacePath,
                    mode: chatMode.rawValue,
                    onTextDelta: textDeltaHandler,
                    onToolCall: toolCallHandler,
                    onToolActivity: toolActivityHandler,
                    onThinkingDelta: thinkingDeltaHandler,
                    onToolResultDisplay: toolResultDisplayHandler,
                    onAuthRequired: onAuthRequired ?? { _ in },
                    onAuthSuccess: onAuthSuccess ?? { }
                )
            } else if let bridge = claudeBridge {
                // Claude SDK mode — use resume for conversation continuity
                let claudeResult = try await bridge.query(
                    prompt: trimmedText,
                    systemPrompt: systemPrompt,
                    cwd: workspacePath.isEmpty ? nil : workspacePath,
                    mode: chatMode.rawValue,
                    resume: claudeSessionId,
                    onTextDelta: textDeltaHandler,
                    onToolCall: toolCallHandler,
                    onToolActivity: toolActivityHandler,
                    onThinkingDelta: thinkingDeltaHandler,
                    onToolResultDisplay: toolResultDisplayHandler
                )
                queryResult = ACPBridge.QueryResult(
                    text: claudeResult.text,
                    costUsd: claudeResult.costUsd,
                    sessionId: claudeResult.sessionId
                )
            } else {
                throw BridgeError.notRunning
            }

            // Flush remaining streaming buffers
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            // Capture session ID for resume on next message
            if !queryResult.sessionId.isEmpty {
                claudeSessionId = queryResult.sessionId
                log("TaskChatState[\(taskId)]: captured sessionId=\(queryResult.sessionId)")
            }

            // Finalize AI message
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                let messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                messages[index].text = messageText
                messages[index].isStreaming = false
                completeRemainingToolCalls(messageId: aiMessageId)
                persistMessage(messages[index])
            }

            log("TaskChatState[\(taskId)]: response complete (cost=$\(queryResult.costUsd))")
        } catch {
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                if messages[index].text.isEmpty && messages[index].contentBlocks.isEmpty {
                    messages.remove(at: index)
                } else {
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(messageId: aiMessageId)
                    persistMessage(messages[index])
                }
            }

            if let bridgeError = error as? BridgeError, case .stopped = bridgeError {
                // User stopped — no error
            } else {
                errorMessage = error.localizedDescription
            }
            logError("TaskChatState[\(taskId)]: query failed", error: error)
        }

        isSending = false
        isStopping = false

        // Chain follow-up if queued
        if let followUp = pendingFollowUpText {
            pendingFollowUpText = nil
            await sendMessage(followUp, isFollowUp: true)
        }
    }

    // MARK: - Follow-Up

    func sendFollowUp(_ text: String) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty, isSending else { return }

        // Add user message locally and persist
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            text: trimmedText,
            sender: .user
        )
        messages.append(userMessage)
        persistMessage(userMessage)

        // Queue follow-up and interrupt current query
        pendingFollowUpText = trimmedText
        if useACPMode {
            await acpBridge?.interrupt()
        } else {
            await claudeBridge?.interrupt()
        }
        log("TaskChatState[\(taskId)]: follow-up queued, interrupt sent")
    }

    // MARK: - Stop

    func stopAgent() {
        guard isSending else { return }
        isStopping = true
        Task {
            if useACPMode {
                await acpBridge?.interrupt()
            } else {
                await claudeBridge?.interrupt()
            }
        }
    }

    // MARK: - Streaming Helpers (mirrored from ChatProvider)

    private func appendToMessage(id: String, text: String) {
        streamingBufferMessageId = id
        streamingTextBuffer += text

        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    private func flushStreamingBuffer() {
        streamingFlushWorkItem = nil

        guard let id = streamingBufferMessageId,
              let index = messages.firstIndex(where: { $0.id == id }) else {
            streamingTextBuffer = ""
            streamingThinkingBuffer = ""
            return
        }

        if !streamingTextBuffer.isEmpty {
            let buffered = streamingTextBuffer
            streamingTextBuffer = ""

            messages[index].text += buffered

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .text(let blockId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                messages[index].contentBlocks[lastBlockIndex] = .text(id: blockId, text: existing + buffered)
            } else {
                messages[index].contentBlocks.append(.text(id: UUID().uuidString, text: buffered))
            }
        }

        if !streamingThinkingBuffer.isEmpty {
            let buffered = streamingThinkingBuffer
            streamingThinkingBuffer = ""

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .thinking(let thinkId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                messages[index].contentBlocks[lastBlockIndex] = .thinking(id: thinkId, text: existing + buffered)
            } else {
                messages[index].contentBlocks.append(.thinking(id: UUID().uuidString, text: buffered))
            }
        }
    }

    private func addToolActivity(messageId: String, toolName: String, status: ToolCallStatus, toolUseId: String? = nil, input: [String: Any]? = nil) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }

        let toolInput = input.flatMap { ChatContentBlock.toolInputSummary(for: toolName, input: $0) }

        if status == .running {
            if let toolUseId = toolUseId, toolInput != nil {
                for i in stride(from: messages[index].contentBlocks.count - 1, through: 0, by: -1) {
                    if case .toolCall(let id, let name, let st, let existingTuid, _, let output) = messages[index].contentBlocks[i],
                       (existingTuid == toolUseId || (existingTuid == nil && name == toolName && st == .running)) {
                        messages[index].contentBlocks[i] = .toolCall(
                            id: id, name: name, status: st,
                            toolUseId: toolUseId, input: toolInput, output: output
                        )
                        return
                    }
                }
            }
            messages[index].contentBlocks.append(
                .toolCall(id: UUID().uuidString, name: toolName, status: .running,
                          toolUseId: toolUseId, input: toolInput)
            )
        } else {
            for i in stride(from: messages[index].contentBlocks.count - 1, through: 0, by: -1) {
                if case .toolCall(let id, let name, .running, let existingTuid, let existingInput, let output) = messages[index].contentBlocks[i] {
                    let matches = (toolUseId != nil && existingTuid == toolUseId) || (toolUseId == nil && name == toolName)
                    if matches {
                        messages[index].contentBlocks[i] = .toolCall(
                            id: id, name: name, status: .completed,
                            toolUseId: toolUseId ?? existingTuid,
                            input: toolInput ?? existingInput,
                            output: output
                        )
                        break
                    }
                }
            }
        }
    }

    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }

        for i in messages[index].contentBlocks.indices {
            if case .toolCall(let id, let blockName, let status, let tuid, let input, _) = messages[index].contentBlocks[i],
               (tuid == toolUseId || (tuid == nil && blockName == name)) {
                messages[index].contentBlocks[i] = .toolCall(
                    id: id, name: blockName, status: status,
                    toolUseId: toolUseId, input: input, output: output
                )
                return
            }
        }
    }

    private func appendThinking(messageId: String, text: String) {
        streamingBufferMessageId = messageId
        streamingThinkingBuffer += text

        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    private func completeRemainingToolCalls(messageId: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        for i in messages[index].contentBlocks.indices {
            if case .toolCall(let id, let name, .running, let toolUseId, let input, let output) = messages[index].contentBlocks[i] {
                messages[index].contentBlocks[i] = .toolCall(
                    id: id, name: name, status: .completed,
                    toolUseId: toolUseId, input: input, output: output
                )
            }
        }
    }
}
