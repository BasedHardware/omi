import SwiftUI
import Combine

/// Per-task chat UI state. Execution uses the shared `TaskChatRuntime` bridge and
/// kernel-owned `task_chat` sessions — no per-task bridge or session identity.
@MainActor
class TaskChatState: ObservableObject {
    let taskId: String

    @Published var messages: [ChatMessage] = []
    @Published var isSending = false
    @Published var isStopping = false
    @Published var draftText: String {
        didSet { ChatDraftStore.shared.setText(draftText, for: .taskChat(taskId)) }
    }
    @Published var errorMessage: String?
    @Published var chatMode: ChatMode = .act
    /// Monotonic token that increments each time the local user sends a message
    /// in this task chat. ChatMessagesView observes this for turn anchoring.
    @Published var localSendToken: LocalSendToken = LocalSendToken(generation: 0)

    /// Workspace path for file-system tools
    let workspacePath: String
    var systemPromptBuilder: (() -> String)?

    /// Auth callbacks for ACP mode
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?

    private var runtimeProjectionCancellable: AnyCancellable?
    private var surfacedFailureKeys: Set<String> = []
    private var activeAssistantMessageId: String?

    // MARK: - Streaming Buffer

    private let streamingBuffer = ChatStreamingBuffer(flushInterval: 0.1)

    /// Whether persisted messages have been loaded from GRDB
    private var hasLoadedFromStorage = false

    init(taskId: String, workspacePath: String) {
        self.taskId = taskId
        self.workspacePath = workspacePath
        self.draftText = ChatDraftStore.shared.text(for: .taskChat(taskId))
    }

    // MARK: - Persistence

    /// Load persisted messages from GRDB (called once when chat is opened)
    func loadPersistedMessages() async {
        guard !hasLoadedFromStorage else { return }
        hasLoadedFromStorage = true

        do {
            let records = try await TaskChatMessageStorage.shared.getMessages(forTaskId: taskId)
            observeRuntimeProjectionFailures()
            guard !records.isEmpty else {
                surfaceCurrentRuntimeFailureIfNeeded()
                return
            }

            messages = records.map { $0.toChatMessage() }

            surfaceCurrentRuntimeFailureIfNeeded()
            log("TaskChatState[\(taskId)]: Loaded \(records.count) persisted messages")
        } catch {
            logError("TaskChatState[\(taskId)]: Failed to load persisted messages", error: error)
        }
    }

    /// Persist a message to GRDB (fire-and-forget)
    private func persistMessage(_ message: ChatMessage) {
        let taskId = self.taskId
        Task.detached {
            do {
                try await TaskChatMessageStorage.shared.saveMessage(message, taskId: taskId)
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

    // MARK: - Send Message

    func sendMessage(_ text: String, taskContext: String? = nil) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        guard !isSending else {
            log("TaskChatState[\(taskId)]: sendMessage called while already sending, ignoring")
            return
        }

        isSending = true
        errorMessage = nil
        TaskAgentStatusRegistry.shared.markRunning(taskId: taskId)
        // Signal local send for turn anchoring.
        localSendToken = LocalSendToken(generation: localSendToken.generation + 1)

        // Add user message to local messages and persist
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            text: trimmedText,
            sender: .user
        )
        messages.append(userMessage)
        persistMessage(userMessage)
        if draftText == text {
            draftText = ""
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
        activeAssistantMessageId = aiMessageId

        do {
            let systemPrompt = systemPromptBuilder?() ?? ""
            let currentChatMode = chatMode

            let textDeltaHandler: @Sendable (String) -> Void = { [weak self] delta in
                Task { @MainActor [weak self] in
                    self?.appendToMessage(id: aiMessageId, text: delta)
                }
            }
            let toolCallHandler: @Sendable (String, String, [String: Any]) async -> String = { callId, name, input in
                let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
                let result = await ChatToolExecutor.execute(toolCall, originatingChatMode: currentChatMode)
                log("TaskChat OMI tool \(name) executed for callId=\(callId)")
                return result
            }
            let toolActivityHandler: @Sendable (String, String, String?, [String: Any]?) -> Void = { [weak self] name, status, toolUseId, input in
                Task { @MainActor [weak self] in
                    self?.addToolActivity(
                        messageId: aiMessageId,
                        toolName: name,
                        status: ToolCallStatus.fromBridgeStatus(status),
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

            let queryResult = try await TaskChatRuntime.query(
                prompt: trimmedText,
                systemPrompt: systemPrompt,
                taskId: taskId,
                workspacePath: workspacePath,
                mode: chatMode.rawValue,
                surfaceContextJson: taskContext,
                onTextDelta: textDeltaHandler,
                onToolCall: toolCallHandler,
                onToolActivity: toolActivityHandler,
                onThinkingDelta: thinkingDeltaHandler,
                onToolResultDisplay: toolResultDisplayHandler,
                onAuthRequired: onAuthRequired ?? { _, _ in },
                onAuthSuccess: onAuthSuccess ?? { }
            )

            // Flush remaining streaming buffers
            streamingBuffer.cancelPendingFlush()
            flushStreamingBuffer()

            // Finalize AI message
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                let terminalStatus = AgentRunProjectionStatus.fromWire(queryResult.terminalStatus) ?? .succeeded
                if terminalStatus == .failed || terminalStatus == .timedOut || terminalStatus == .orphaned {
                    surfaceCurrentRuntimeFailureIfNeeded(fallbackMessage: "Agent failed")
                    if let currentIndex = messages.firstIndex(where: { $0.id == aiMessageId }) {
                        let shouldPersistPartial =
                            messages[currentIndex].isStreaming
                            && (
                                !messages[currentIndex].text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                || !messages[currentIndex].contentBlocks.isEmpty
                                || !queryResult.artifacts.isEmpty
                            )
                        messages[currentIndex].isStreaming = false
                        messages[currentIndex].resources = queryResult.artifacts.map(ChatResource.artifact)
                        completeRemainingToolCalls(messageId: aiMessageId, terminalStatus: .failed)
                        if shouldPersistPartial {
                            persistMessage(messages[currentIndex])
                        }
                    }
                } else {
                    let messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                    messages[index].text = messageText
                    messages[index].isStreaming = false
                    messages[index].resources = queryResult.artifacts.map(ChatResource.artifact)
                    completeRemainingToolCalls(messageId: aiMessageId)
                    persistMessage(messages[index])
                }
            }

            log("TaskChatState[\(taskId)]: response complete (cost=$\(queryResult.costUsd))")
            let terminalStatus = AgentRunProjectionStatus.fromWire(queryResult.terminalStatus) ?? .succeeded
            if terminalStatus == .failed || terminalStatus == .timedOut || terminalStatus == .orphaned {
                let failureText =
                    AgentRuntimeStatusStore.shared.projection(for: .taskChat(taskId: taskId))
                    .flatMap(AgentFailureTranscriptFormatter.errorText(for:))
                    ?? "Agent failed"
                errorMessage = failureText
                TaskAgentStatusRegistry.shared.markFailed(taskId: taskId, error: failureText)
            } else {
                TaskAgentStatusRegistry.shared.markCompleted(taskId: taskId)
            }
        } catch {
            streamingBuffer.cancelPendingFlush()
            flushStreamingBuffer()

            let failedByUserStop: Bool
            if let bridgeError = error as? BridgeError, case .stopped = bridgeError {
                failedByUserStop = true
            } else {
                failedByUserStop = false
            }

            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                if failedByUserStop && messages[index].text.isEmpty && messages[index].contentBlocks.isEmpty {
                    messages.remove(at: index)
                } else {
                    if !failedByUserStop {
                        Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)
                    }
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(
                        messageId: aiMessageId,
                        terminalStatus: failedByUserStop ? .completed : .failed
                    )
                    persistMessage(messages[index])
                }
            }

            if failedByUserStop {
                TaskAgentStatusRegistry.shared.markStopped(taskId: taskId)
            } else {
                errorMessage = error.localizedDescription
                TaskAgentStatusRegistry.shared.markFailed(taskId: taskId, error: error.localizedDescription)
            }
            logError("TaskChatState[\(taskId)]: query failed", error: error)
        }

        activeAssistantMessageId = nil
        isSending = false
        isStopping = false
    }

    // MARK: - Failure Formatting

    static func applyFailureTextIfNeeded(to message: inout ChatMessage, errorDescription: String) {
        let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorDescription) ?? "Failed: Agent failed"
        let existingText = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if existingText.isEmpty {
            message.text = failureText
        } else if !existingText.contains(failureText) {
            message.text += "\n\n\(failureText)"
        }

        guard !message.contentBlocks.isEmpty else { return }

        if !existingText.isEmpty && !Self.contentBlocks(message.contentBlocks, containText: existingText) {
            message.contentBlocks.insert(.text(id: UUID().uuidString, text: existingText), at: 0)
        }

        let hasFailureTextBlock = message.contentBlocks.contains { block in
            if case .text(_, let text) = block {
                return text.trimmingCharacters(in: .whitespacesAndNewlines) == failureText
            }
            return false
        }
        if !hasFailureTextBlock {
            message.contentBlocks.append(.text(id: UUID().uuidString, text: failureText))
        }
    }

    private static func contentBlocks(_ blocks: [ChatContentBlock], containText needle: String) -> Bool {
        let combinedText = blocks.compactMap { block in
            if case .text(_, let text) = block {
                return text
            }
            return nil
        }
        .joined()

        if combinedText.contains(needle) {
            return true
        }

        return blocks.contains { block in
            if case .text(_, let text) = block {
                return text.contains(needle)
            }
            return false
        }
    }

    func surfaceRuntimeFailure(_ projection: AgentRunProjection, fallbackMessage: String? = nil, persist: Bool = true) {
        guard projection.surface == .taskChat(taskId: taskId) else { return }
        guard let errorText = AgentFailureTranscriptFormatter.errorText(for: projection) ?? fallbackMessage else { return }
        let failureKey = [
            projection.runId,
            projection.attemptId,
            projection.sessionId,
            projection.completedAt.map { String($0.timeIntervalSinceReferenceDate) },
            errorText,
        ]
        .compactMap { $0 }
        .joined(separator: "|")
        guard surfacedFailureKeys.insert(failureKey).inserted else { return }

        appendFailureTranscriptMessage(errorText, persist: persist)
        errorMessage = errorText
    }

    private func observeRuntimeProjectionFailures() {
        guard runtimeProjectionCancellable == nil else { return }
        let surface = AgentSurfaceReference.taskChat(taskId: taskId)
        runtimeProjectionCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
            .dropFirst()
            .sink { [weak self] projections in
                guard let self, let projection = projections[surface.key] else { return }
                self.surfaceRuntimeFailure(projection)
            }
    }

    private func surfaceCurrentRuntimeFailureIfNeeded(fallbackMessage: String? = nil) {
        if let projection = AgentRuntimeStatusStore.shared.projection(for: .taskChat(taskId: taskId)) {
            surfaceRuntimeFailure(projection, fallbackMessage: fallbackMessage)
        } else if let fallbackMessage {
            appendFailureTranscriptMessage(fallbackMessage)
            errorMessage = fallbackMessage
        }
    }

    private func appendFailureTranscriptMessage(_ errorText: String, persist: Bool = true) {
        guard let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) else { return }
        if messages.contains(where: { message in
            message.sender == .ai
                && message.text.trimmingCharacters(in: .whitespacesAndNewlines) == failureText
        }) {
            return
        }

        if let activeAssistantMessageId,
           let index = messages.firstIndex(where: { $0.id == activeAssistantMessageId }),
           messages[index].text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: errorText)
            messages[index].isStreaming = false
            completeRemainingToolCalls(messageId: activeAssistantMessageId, terminalStatus: .failed)
            if persist {
                persistMessage(messages[index])
            }
            return
        }

        if let index = messages.lastIndex(where: { message in
            message.sender == .ai
                && message.isStreaming
                && message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }) {
            Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: errorText)
            messages[index].isStreaming = false
            completeRemainingToolCalls(messageId: messages[index].id, terminalStatus: .failed)
            if persist {
                persistMessage(messages[index])
            }
            return
        }

        let failureMessage = ChatMessage(text: failureText, sender: .ai)
        messages.append(failureMessage)
        if persist {
            persistMessage(failureMessage)
        }
    }

    // MARK: - Stop

    func stopAgent() {
        guard isSending else { return }
        isStopping = true
        Task {
            await TaskChatRuntime.interrupt(taskId: taskId)
        }
    }

    // MARK: - Streaming Helpers

    private func appendToMessage(id: String, text: String) {
        streamingBuffer.appendText(messageId: id, text: text) { [weak self] in
            self?.flushStreamingBuffer()
        }
    }

    private func flushStreamingBuffer() {
        streamingBuffer.flush(messages: &messages)
    }

    private func addToolActivity(messageId: String, toolName: String, status: ToolCallStatus, toolUseId: String? = nil, input: [String: Any]? = nil) {
        streamingBuffer.applyToolActivity(
            messageId: messageId,
            toolName: toolName,
            status: status,
            toolUseId: toolUseId,
            input: input,
            messages: &messages
        )
    }

    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        streamingBuffer.applyToolResult(
            messageId: messageId,
            toolUseId: toolUseId,
            name: name,
            output: output,
            messages: &messages
        )
    }

    private func appendThinking(messageId: String, text: String) {
        streamingBuffer.appendThinking(messageId: messageId, text: text) { [weak self] in
            self?.flushStreamingBuffer()
        }
    }

    /// Matches any in-flight state (`.running`, `.slow`, `.stalled`) so
    /// detector-promoted blocks resolve when the turn ends.
    private func completeRemainingToolCalls(messageId: String, terminalStatus: ToolCallStatus = .completed) {
        streamingBuffer.completeRemainingToolCalls(
            messageId: messageId,
            terminalStatus: terminalStatus,
            messages: &messages
        )
    }
}
