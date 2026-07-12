import SwiftUI
import Combine

/// Task-scoped UI projected over one kernel-owned workstream conversation.
@MainActor
class TaskChatState: ObservableObject {
    let workstreamId: String
    @Published private(set) var activeTaskId: String

    @Published var messages: [ChatMessage] = []
    @Published var isSending = false
    @Published var isStopping = false
    @Published var draftText: String {
        didSet { ChatDraftStore.shared.setText(draftText, for: .taskChat(workstreamId)) }
    }
    @Published var errorMessage: String?
    @Published var chatMode: ChatMode = .act
    /// Monotonic token that increments each time the local user sends a message
    /// in this task chat. ChatMessagesView observes this for turn anchoring.
    @Published var localSendToken: LocalSendToken = LocalSendToken(generation: 0)

    /// Workspace path for file-system tools
    let workspacePath: String
    var onQueryCompleted: ((AgentBridge.QueryResult, String) async -> Void)?

    /// Auth callbacks for ACP mode
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?

    private var runtimeProjectionCancellable: AnyCancellable?
    private var surfacedFailureKeys: Set<String> = []
    private var activeAssistantMessageId: String?
    private var journalEventToken: UUID?
    private var journalHighWater = 0
    private var journalGeneration = 0
    private var isRefreshingJournal = false
    private var journalRefreshRequested = false
    private var journalUpdateTasks: [String: Task<Void, Never>] = [:]

    // MARK: - Streaming Buffer

    private let streamingBuffer = ChatStreamingBuffer(flushInterval: 0.1)

    private var hasLoadedJournal = false

    init(taskId: String, workstreamId: String, workspacePath: String) {
        self.activeTaskId = taskId
        self.workstreamId = workstreamId
        self.workspacePath = workspacePath
        self.draftText = ChatDraftStore.shared.text(for: .taskChat(workstreamId))
    }

    func selectTask(_ taskId: String) {
        activeTaskId = taskId
    }

    // MARK: - Kernel journal projection

    func loadPersistedMessages() async {
        guard !hasLoadedJournal else { return }
        hasLoadedJournal = true
        do {
            journalEventToken = try await TaskChatRuntime.attachJournalEvents(
                workstreamId: workstreamId
            ) { [weak self] in
                Task { @MainActor [weak self] in await self?.refreshJournal() }
            }
            observeRuntimeProjectionFailures()
            await refreshJournal(reset: true)
            surfaceCurrentRuntimeFailureIfNeeded()
            log("TaskChatState[\(workstreamId)]: Loaded \(messages.count) kernel journal messages")
        } catch {
            log("TaskChatState[\(workstreamId)]: journal load failed (code=journal_load_failed)")
        }
    }

    private func refreshJournal(reset: Bool = false) async {
        if reset {
            journalHighWater = 0
            journalGeneration = 0
            messages = []
        }
        if isRefreshingJournal {
            journalRefreshRequested = true
            return
        }
        isRefreshingJournal = true
        defer { isRefreshingJournal = false }
        repeat {
            journalRefreshRequested = false
            do {
                var fetchNextPage = true
                while fetchNextPage {
                    let page = try await TaskChatRuntime.listJournalTurns(
                        workstreamId: workstreamId,
                        afterTurnSeq: journalHighWater
                    )
                    if journalGeneration != page.conversationGeneration {
                        journalGeneration = page.conversationGeneration
                        journalHighWater = page.generationBaseTurnSeq
                        messages = []
                    }
                    let checkpointBeforePage = journalHighWater
                    let contiguousPage = KernelJournalReplay.contiguousTurns(
                        from: page.turns,
                        after: journalHighWater
                    )
                    for turn in contiguousPage {
                        projectJournalTurn(turn)
                        journalHighWater = turn.turnSeq
                    }
                    if let firstUnapplied = page.turns
                        .filter({ $0.turnSeq > journalHighWater })
                        .min(by: { $0.turnSeq < $1.turnSeq })
                    {
                        log("TaskChatState[\(workstreamId)]: journal gap (expected=\(journalHighWater + 1), got=\(firstUnapplied.turnSeq))")
                        fetchNextPage = false
                    }
                    if journalHighWater >= page.highWaterTurnSeq || journalHighWater == checkpointBeforePage {
                        fetchNextPage = false
                    }
                }
            } catch {
                log("TaskChatState[\(workstreamId)]: range fetch failed (code=journal_range_fetch_failed)")
            }
        } while journalRefreshRequested
    }

    private func projectJournalTurn(_ turn: KernelJournalTurn) {
        guard turn.surfaceKind == "workstream", turn.externalRefId == workstreamId else { return }
        let projected = turn.chatMessage()
        let emptyFailure = turn.status == .failed
            && projected.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && projected.contentBlocks.isEmpty
            && projected.resources.isEmpty
        if emptyFailure {
            messages.removeAll { $0.id == projected.id }
            return
        }
        if let index = messages.firstIndex(where: { $0.id == projected.id }) {
            messages[index] = projected
        } else {
            messages.append(projected)
        }
        messages.sort {
            if $0.createdAt == $1.createdAt { return $0.id < $1.id }
            return $0.createdAt < $1.createdAt
        }
    }

    private func scheduleJournalUpdate(messageId: String, status: KernelJournalTurnStatus? = nil) {
        guard let message = messages.first(where: { $0.id == messageId }) else { return }
        let previous = journalUpdateTasks[messageId]
        journalUpdateTasks[messageId] = Task { @MainActor [weak self] in
            _ = await previous?.value
            guard let self else { return }
            _ = try? await TaskChatRuntime.updateJournalMessage(
                workstreamId: self.workstreamId,
                message: message,
                status: status
            )
        }
    }

    private func finishJournalUpdate(
        messageId: String,
        status: KernelJournalTurnStatus
    ) async {
        _ = await journalUpdateTasks.removeValue(forKey: messageId)?.value
        guard let message = messages.first(where: { $0.id == messageId }) else { return }
        _ = try? await TaskChatRuntime.updateJournalMessage(
            workstreamId: workstreamId,
            message: message,
            status: status
        )
        await refreshJournal()
    }

    // MARK: - Send Message

    func sendMessage(_ text: String, taskContext: String? = nil) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        guard !isSending else {
            log("TaskChatState[\(workstreamId)]: sendMessage called while already sending, ignoring")
            return
        }

        isSending = true
        errorMessage = nil
        // Signal local send for turn anchoring.
        localSendToken = LocalSendToken(generation: localSendToken.generation + 1)

        let continuityKey = UUID().uuidString
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            clientTurnId: continuityKey,
            text: trimmedText,
            sender: .user,
            turnOwner: .taskChat(workstreamId)
        )
        do {
            _ = try await TaskChatRuntime.recordJournalMessage(
                workstreamId: workstreamId,
                message: userMessage,
                status: .completed,
                continuityKey: continuityKey
            )
            await refreshJournal()
        } catch {
            errorMessage = "Could not save this message. Try again."
            isSending = false
            return
        }
        if draftText == text {
            draftText = ""
        }

        // Create placeholder AI message
        let aiMessageId = UUID().uuidString
        let aiMessage = ChatMessage(
            id: aiMessageId,
            clientTurnId: continuityKey,
            text: "",
            sender: .ai,
            isStreaming: true,
            turnOwner: .taskChat(workstreamId)
        )
        do {
            _ = try await TaskChatRuntime.recordJournalMessage(
                workstreamId: workstreamId,
                message: aiMessage,
                status: .streaming,
                continuityKey: continuityKey
            )
            await refreshJournal()
        } catch {
            errorMessage = "Could not start this response. Try again."
            isSending = false
            return
        }
        activeAssistantMessageId = aiMessageId

        do {
            let textDeltaHandler: @Sendable (String) -> Void = { [weak self] delta in
                Task { @MainActor [weak self] in
                    self?.appendToMessage(id: aiMessageId, text: delta)
                }
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
                workstreamId: workstreamId,
                workspacePath: workspacePath,
                mode: chatMode.rawValue,
                taskContext: taskContext,
                onTextDelta: textDeltaHandler,
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
                        messages[currentIndex].isStreaming = false
                        messages[currentIndex].resources = queryResult.artifacts.map(ChatResource.artifact)
                        completeRemainingToolCalls(messageId: aiMessageId, terminalStatus: .failed)
                        await finishJournalUpdate(messageId: aiMessageId, status: .failed)
                    }
                } else {
                    let messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                    messages[index].text = messageText
                    messages[index].isStreaming = false
                    messages[index].resources = queryResult.artifacts.map(ChatResource.artifact)
                    completeRemainingToolCalls(messageId: aiMessageId)
                    await finishJournalUpdate(messageId: aiMessageId, status: .completed)
                }
            }

            log("TaskChatState[\(workstreamId)]: response complete (cost=$\(queryResult.costUsd))")
            let terminalStatus = AgentRunProjectionStatus.fromWire(queryResult.terminalStatus) ?? .succeeded
            if terminalStatus == .failed || terminalStatus == .timedOut || terminalStatus == .orphaned {
                let failureText =
                    AgentRuntimeStatusStore.shared.projection(for: .workstream(workstreamId: workstreamId))
                    .flatMap(AgentFailureTranscriptFormatter.errorText(for:))
                    ?? "Agent failed"
                errorMessage = failureText
            } else {
                await onQueryCompleted?(queryResult, userMessage.id)
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
                    messages[index].isStreaming = false
                    await finishJournalUpdate(messageId: aiMessageId, status: .failed)
                } else {
                    if !failedByUserStop {
                        Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)
                    }
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(
                        messageId: aiMessageId,
                        terminalStatus: failedByUserStop ? .completed : .failed
                    )
                    await finishJournalUpdate(
                        messageId: aiMessageId,
                        status: failedByUserStop ? .completed : .failed
                    )
                }
            }

            if !failedByUserStop {
                errorMessage = error.localizedDescription
            }
            logError("TaskChatState[\(workstreamId)]: query failed", error: error)
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

    func surfaceRuntimeFailure(_ projection: AgentRunProjection, fallbackMessage: String? = nil) {
        guard projection.surface == .workstream(workstreamId: workstreamId) else { return }
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

        appendFailureTranscriptMessage(errorText)
        errorMessage = errorText
    }

    private func observeRuntimeProjectionFailures() {
        guard runtimeProjectionCancellable == nil else { return }
        let surface = AgentSurfaceReference.workstream(workstreamId: workstreamId)
        runtimeProjectionCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
            .dropFirst()
            .sink { [weak self] projections in
                guard let self, let projection = projections[surface.key] else { return }
                self.surfaceRuntimeFailure(projection)
            }
    }

    private func surfaceCurrentRuntimeFailureIfNeeded(fallbackMessage: String? = nil) {
        if let projection = AgentRuntimeStatusStore.shared.projection(for: .workstream(workstreamId: workstreamId)) {
            surfaceRuntimeFailure(projection, fallbackMessage: fallbackMessage)
        } else if let fallbackMessage {
            appendFailureTranscriptMessage(fallbackMessage)
            errorMessage = fallbackMessage
        }
    }

    private func appendFailureTranscriptMessage(_ errorText: String) {
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
            scheduleJournalUpdate(messageId: activeAssistantMessageId, status: .failed)
            return
        }

        if let index = messages.lastIndex(where: { message in
            message.sender == .ai
                && message.isStreaming
                && message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }) {
            Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: errorText)
            messages[index].isStreaming = false
            let messageId = messages[index].id
            completeRemainingToolCalls(messageId: messageId, terminalStatus: .failed)
            scheduleJournalUpdate(messageId: messageId, status: .failed)
            return
        }

        let failureMessage = ChatMessage(
            text: failureText,
            sender: .ai,
            turnOwner: .taskChat(workstreamId)
        )
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                _ = try await TaskChatRuntime.recordJournalMessage(
                    workstreamId: self.workstreamId,
                    message: failureMessage,
                    status: .failed
                )
                await self.refreshJournal()
            } catch {
                log("TaskChatState[\(self.workstreamId)]: failure transcript record failed (code=journal_record_failed)")
            }
        }
    }

    // MARK: - Stop

    func stopAgent() {
        guard isSending else { return }
        isStopping = true
        Task {
            await TaskChatRuntime.interrupt(workstreamId: workstreamId)
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
        if let activeAssistantMessageId {
            scheduleJournalUpdate(messageId: activeAssistantMessageId, status: .streaming)
        }
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
        scheduleJournalUpdate(messageId: messageId, status: .streaming)
    }

    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        streamingBuffer.applyToolResult(
            messageId: messageId,
            toolUseId: toolUseId,
            name: name,
            output: output,
            messages: &messages
        )
        scheduleJournalUpdate(messageId: messageId, status: .streaming)
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
        scheduleJournalUpdate(messageId: messageId)
    }
}
