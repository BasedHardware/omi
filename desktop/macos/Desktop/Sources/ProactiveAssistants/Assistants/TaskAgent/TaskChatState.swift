import SwiftUI
import Combine

struct TaskChatOwnerLease: Equatable, Sendable {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let generation: UInt64

    var ownerID: String { authorizationSnapshot.ownerID }
}

enum TaskChatTerminalDisposition: Equatable {
    case succeeded
    case failed
    case cancelled
    case invalid

    static func classify(_ status: AgentQueryTerminalStatus) -> TaskChatTerminalDisposition {
        switch status {
        case .succeeded:
            return .succeeded
        case .failed, .timedOut, .orphaned:
            return .failed
        case .cancelled:
            return .cancelled
        case .invalid:
            return .invalid
        }
    }
}

/// Exact run/attempt linkage for the one assistant turn admitted by the active
/// task-chat query. Runtime status is indexed by surface for display, but a
/// terminal projection may request a canonical refresh only through this
/// narrower producing-turn identity; it never writes journal state itself.
struct TaskChatProducingRunProjection: Equatable {
    private(set) var assistantMessageID: String?
    private(set) var runID: String?
    private(set) var attemptID: String?

    mutating func begin(assistantMessageID: String) {
        self.assistantMessageID = assistantMessageID
        runID = nil
        attemptID = nil
    }

    /// A returned QueryResult is already correlated to the active bridge
    /// request. Surface-keyed runtime projections are never allowed to bind this
    /// identity because a delayed R1 projection can arrive while R2 is active.
    @discardableResult
    mutating func bindResult(
        assistantMessageID: String,
        runID: String,
        attemptID: String
    ) -> Bool {
        guard self.assistantMessageID == assistantMessageID,
              let normalizedRunID = Self.normalized(runID),
              let normalizedAttemptID = Self.normalized(attemptID) else { return false }
        self.runID = normalizedRunID
        self.attemptID = normalizedAttemptID
        return true
    }

    func terminalMessageID(for projection: AgentRunProjection) -> String? {
        guard projection.status.isTerminal,
              projection.status != .succeeded,
              let assistantMessageID,
              let runID,
              let attemptID,
              Self.normalized(projection.runId) == runID,
              Self.normalized(projection.attemptId) == attemptID else { return nil }
        return assistantMessageID
    }

    mutating func clear() {
        assistantMessageID = nil
        runID = nil
        attemptID = nil
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? nil : normalized
    }
}

/// Task-scoped UI projected over one kernel-owned workstream conversation.
@MainActor
class TaskChatState: ObservableObject {
    typealias AttachJournalEventsOperation = (
        _ workstreamId: String,
        _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
        _ wake: @escaping @MainActor () -> Void
    ) async throws -> UUID
    typealias ListJournalTurnsOperation = (
        _ workstreamId: String,
        _ ownerID: String,
        _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
        _ afterTurnSeq: Int,
        _ limit: Int
    ) async throws -> AgentRuntimeProcess.JournalOperationResult
    typealias RecordJournalExchangeOperation = (
        _ workstreamId: String,
        _ ownerID: String,
        _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
        _ turns: [KernelJournalTurnWrite]
    ) async throws -> AgentRuntimeProcess.JournalOperationResult

    let workstreamId: String
    @Published private(set) var activeTaskId: String

    @Published var messages: [ChatMessage] = []
    @Published var isSending = false
    @Published var isStopping = false
    @Published var draftText: String {
        didSet {
            guard !isOwnerInvalidated else { return }
            ChatDraftStore.shared.setText(
                draftText,
                for: .taskChat(workstreamId),
                ownerID: boundOwnerID
            )
        }
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
    private var producingRunProjection = TaskChatProducingRunProjection()
    private var journalEventToken: UUID?
    private var journalHighWater = 0
    private var journalGeneration = 0
    private var isRefreshingJournal = false
    private var journalRefreshRequested = false
    private var journalUpdateTasks: [String: Task<Void, Never>] = [:]
    private let boundOwnerID: String
    private let boundAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    private let ownerIDProvider: @MainActor () -> String?
    private let attachJournalEventsOperation: AttachJournalEventsOperation
    private let listJournalTurnsOperation: ListJournalTurnsOperation
    private let recordJournalExchangeOperation: RecordJournalExchangeOperation
    private var ownerGeneration: UInt64 = 0
    private var isOwnerInvalidated = false

    // MARK: - Streaming Buffer

    private let streamingBuffer = ChatStreamingBuffer(flushInterval: 0.1)

    private var hasLoadedJournal = false

    init(
        taskId: String,
        workstreamId: String,
        workspacePath: String,
        authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
        ownerIDProvider: @escaping @MainActor () -> String? = {
            RuntimeOwnerIdentity.currentOwnerId()
        },
        attachJournalEventsOperation: AttachJournalEventsOperation? = nil,
        listJournalTurnsOperation: ListJournalTurnsOperation? = nil,
        recordJournalExchangeOperation: RecordJournalExchangeOperation? = nil
    ) {
        let ownerID = Self.normalizedOwnerID(ownerIDProvider()) ?? ""
        self.activeTaskId = taskId
        self.workstreamId = workstreamId
        self.workspacePath = workspacePath
        self.boundOwnerID = ownerID
        self.boundAuthorizationSnapshot = suppliedAuthorizationSnapshot
            ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
        self.ownerIDProvider = ownerIDProvider
        self.attachJournalEventsOperation = attachJournalEventsOperation ?? {
            workstreamId, authorizationSnapshot, wake in
            try await TaskChatRuntime.attachJournalEvents(
                workstreamId: workstreamId,
                authorizationSnapshot: authorizationSnapshot,
                wake: wake
            )
        }
        self.listJournalTurnsOperation = listJournalTurnsOperation ?? {
            workstreamId, ownerID, authorizationSnapshot, after, limit in
            try await TaskChatRuntime.listJournalTurns(
                workstreamId: workstreamId,
                ownerID: ownerID,
                authorizationSnapshot: authorizationSnapshot,
                afterTurnSeq: after,
                limit: limit
            )
        }
        self.recordJournalExchangeOperation = recordJournalExchangeOperation ?? {
            workstreamId, ownerID, authorizationSnapshot, turns in
            try await TaskChatRuntime.recordJournalExchange(
                workstreamId: workstreamId,
                ownerID: ownerID,
                authorizationSnapshot: authorizationSnapshot,
                turns: turns
            )
        }
        self.draftText = ChatDraftStore.shared.text(
            for: .taskChat(workstreamId),
            ownerID: ownerID
        )
    }

    func selectTask(_ taskId: String) {
        guard hasCurrentOwner else { return }
        activeTaskId = taskId
    }

    /// Synchronous account boundary. The coordinator calls this from the
    /// MainActor owner-change notification before new-owner work is admitted.
    /// Every suspended callback retains the previous generation and becomes a
    /// no-op even if its bridge continuation resumes later.
    func invalidateOwnerState() {
        ownerGeneration &+= 1
        isOwnerInvalidated = true
        KernelJournalEventHub.shared.unsubscribe(journalEventToken)
        journalEventToken = nil
        runtimeProjectionCancellable?.cancel()
        runtimeProjectionCancellable = nil
        streamingBuffer.cancelPendingFlush()
        for task in journalUpdateTasks.values { task.cancel() }
        journalUpdateTasks.removeAll()
        messages.removeAll()
        surfacedFailureKeys.removeAll()
        activeAssistantMessageId = nil
        producingRunProjection.clear()
        journalHighWater = 0
        journalGeneration = 0
        isRefreshingJournal = false
        journalRefreshRequested = false
        hasLoadedJournal = false
        isSending = false
        isStopping = false
        errorMessage = nil
        draftText = ""
        onQueryCompleted = nil
        onAuthRequired = nil
        onAuthSuccess = nil
    }

    var ownerProjectionIsEmpty: Bool {
        messages.isEmpty
            && journalUpdateTasks.isEmpty
            && activeAssistantMessageId == nil
            && !isSending
            && !isStopping
            && errorMessage == nil
            && draftText.isEmpty
    }

    private var hasCurrentOwner: Bool {
        !isOwnerInvalidated
            && !boundOwnerID.isEmpty
            && Self.normalizedOwnerID(ownerIDProvider()) == boundOwnerID
            && boundAuthorizationSnapshot.map(RuntimeOwnerIdentity.isAuthorizationCurrent) == true
    }

    private func captureOwnerLease() -> TaskChatOwnerLease? {
        guard hasCurrentOwner, let boundAuthorizationSnapshot else { return nil }
        return TaskChatOwnerLease(
            authorizationSnapshot: boundAuthorizationSnapshot,
            generation: ownerGeneration
        )
    }

    private func isCurrent(_ lease: TaskChatOwnerLease) -> Bool {
        hasCurrentOwner
            && lease.ownerID == boundOwnerID
            && lease.generation == ownerGeneration
            && RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
    }

    private static func normalizedOwnerID(_ ownerID: String?) -> String? {
        guard let ownerID else { return nil }
        let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? nil : normalized
    }

    // MARK: - Kernel journal projection

    func loadPersistedMessages() async {
        guard let lease = captureOwnerLease() else { return }
        guard !hasLoadedJournal else { return }
        hasLoadedJournal = true
        do {
            let token = try await attachJournalEventsOperation(
                workstreamId,
                lease.authorizationSnapshot
            ) { [weak self] in
                Task { @MainActor [weak self] in
                    guard let self, self.isCurrent(lease) else { return }
                    await self.refreshJournal(lease: lease)
                }
            }
            guard isCurrent(lease) else {
                KernelJournalEventHub.shared.unsubscribe(token)
                return
            }
            journalEventToken = token
            observeRuntimeProjectionFailures()
            await refreshJournal(reset: true, lease: lease)
            guard isCurrent(lease) else { return }
            surfaceCurrentRuntimeFailureIfNeeded()
            log("TaskChatState[\(workstreamId)]: Loaded \(messages.count) kernel journal messages")
        } catch {
            if isCurrent(lease) {
                hasLoadedJournal = false
                log("TaskChatState[\(workstreamId)]: journal load failed (code=journal_load_failed)")
            }
        }
    }

    private func refreshJournal(
        reset: Bool = false,
        lease expectedLease: TaskChatOwnerLease? = nil
    ) async {
        guard let lease = expectedLease ?? captureOwnerLease(), isCurrent(lease) else { return }
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
            guard isCurrent(lease) else { return }
            journalRefreshRequested = false
            do {
                var fetchNextPage = true
                while fetchNextPage {
                    guard isCurrent(lease) else { return }
                    let page = try await listJournalTurnsOperation(
                        workstreamId,
                        lease.ownerID,
                        lease.authorizationSnapshot,
                        journalHighWater,
                        100
                    )
                    guard isCurrent(lease) else { return }
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
                        guard isCurrent(lease) else { return }
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
                if isCurrent(lease) {
                    log("TaskChatState[\(workstreamId)]: range fetch failed (code=journal_range_fetch_failed)")
                }
            }
        } while isCurrent(lease) && journalRefreshRequested
    }

    private func projectJournalTurn(_ turn: KernelJournalTurn) {
        guard hasCurrentOwner else { return }
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

    private func applyAcceptedExchange(
        _ receipt: AgentRuntimeProcess.JournalOperationResult,
        lease: TaskChatOwnerLease
    ) {
        guard isCurrent(lease) else { return }
        if journalGeneration != receipt.conversationGeneration {
            journalGeneration = receipt.conversationGeneration
            journalHighWater = receipt.generationBaseTurnSeq
            messages.removeAll()
        }
        for turn in receipt.turns.sorted(by: { $0.turnSeq < $1.turnSeq }) {
            guard isCurrent(lease) else { return }
            projectJournalTurn(turn)
        }
        let contiguous = KernelJournalReplay.contiguousTurns(
            from: receipt.turns,
            after: journalHighWater
        )
        if let last = contiguous.last { journalHighWater = last.turnSeq }
    }

    private func scheduleJournalUpdate(
        messageId: String,
        status: KernelJournalTurnStatus? = nil
    ) {
        guard let lease = captureOwnerLease() else { return }
        guard let message = messages.first(where: { $0.id == messageId }) else { return }
        let previous = journalUpdateTasks[messageId]
        journalUpdateTasks[messageId] = Task { @MainActor [weak self] in
            _ = await previous?.value
            guard let self, self.isCurrent(lease) else { return }
            _ = try? await TaskChatRuntime.updateJournalMessage(
                workstreamId: self.workstreamId,
                ownerID: lease.ownerID,
                authorizationSnapshot: lease.authorizationSnapshot,
                message: message,
                status: status
            )
        }
    }

    private func terminalizeJournalMessage(
        messageId: String,
        lease: TaskChatOwnerLease,
        producingRunId: String,
        producingAttemptId: String
    ) async throws -> KernelJournalTurn {
        _ = await journalUpdateTasks.removeValue(forKey: messageId)?.value
        guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
        guard let message = messages.first(where: { $0.id == messageId }) else {
            throw BridgeError.agentError("Producing task-chat turn is unavailable")
        }
        let turn = try await TaskChatRuntime.terminalizeJournalMessage(
            workstreamId: workstreamId,
            ownerID: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot,
            message: message,
            producingRunId: producingRunId,
            producingAttemptId: producingAttemptId
        )
        guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
        guard turn.turnId == messageId,
              turn.producingRunId == producingRunId,
              turn.producingAttemptId == producingAttemptId,
              turn.status == .completed || turn.status == .failed else {
            throw BridgeError.agentError("Kernel returned an invalid task-chat terminal receipt")
        }
        projectJournalTurn(turn)
        await refreshJournal(lease: lease)
        return turn
    }

    /// Pre-admission failures have no run/attempt capability to present. The
    /// kernel accepts this generic failure only while the turn is still
    /// unbound; once query admission links a producer, the same update is
    /// rejected and only exact terminalization may close it.
    private func failUnboundJournalMessage(
        messageId: String,
        lease: TaskChatOwnerLease
    ) async {
        _ = await journalUpdateTasks.removeValue(forKey: messageId)?.value
        guard isCurrent(lease),
              let message = messages.first(where: { $0.id == messageId }) else { return }
        if let turn = try? await TaskChatRuntime.updateJournalMessage(
            workstreamId: workstreamId,
            ownerID: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot,
            message: message,
            status: .failed
        ), isCurrent(lease) {
            projectJournalTurn(turn)
        }
        guard isCurrent(lease) else { return }
        await refreshJournal(lease: lease)
    }

    // MARK: - Send Message

    func sendMessage(_ text: String, taskContext: String? = nil) async {
        guard let lease = captureOwnerLease() else { return }
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        guard !isSending else {
            log("TaskChatState[\(workstreamId)]: sendMessage called while already sending, ignoring")
            return
        }

        isSending = true
        errorMessage = nil

        let continuityKey = UUID().uuidString
        let createdAt = Date()
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            clientTurnId: continuityKey,
            text: trimmedText,
            createdAt: createdAt,
            sender: .user,
            turnOwner: .taskChat(workstreamId)
        )
        let aiMessageId = UUID().uuidString
        let aiMessage = ChatMessage(
            id: aiMessageId,
            clientTurnId: continuityKey,
            text: "",
            createdAt: createdAt.addingTimeInterval(0.001),
            sender: .ai,
            isStreaming: true,
            turnOwner: .taskChat(workstreamId)
        )
        do {
            let writes = [
                userMessage.journalWrite(
                    origin: "workstream",
                    status: .completed,
                    continuityKey: continuityKey,
                    messageSource: "workstream"
                ),
                aiMessage.journalWrite(
                    origin: "workstream",
                    status: .streaming,
                    continuityKey: continuityKey,
                    messageSource: "workstream"
                ),
            ]
            let receipt = try await recordJournalExchangeOperation(
                workstreamId,
                lease.ownerID,
                lease.authorizationSnapshot,
                writes
            )
            guard isCurrent(lease) else { return }
            guard receipt.operation == "record_exchange",
                  receipt.turns.count == 2,
                  Set(receipt.turns.map(\.turnId)) == Set(writes.map(\.turnId)) else {
                throw BridgeError.agentError("Kernel returned an invalid task chat exchange receipt")
            }
            applyAcceptedExchange(receipt, lease: lease)
        } catch {
            if isCurrent(lease) {
                errorMessage = "Could not save this message. Try again."
                isSending = false
            }
            return
        }
        guard isCurrent(lease) else { return }
        // Signal local send only after both canonical rows are accepted.
        localSendToken = LocalSendToken(generation: localSendToken.generation + 1)
        if draftText == text { draftText = "" }
        activeAssistantMessageId = aiMessageId
        producingRunProjection.begin(assistantMessageID: aiMessageId)

        do {
            let textDeltaHandler: @Sendable (String) -> Void = { [weak self] delta in
                Task { @MainActor [weak self] in
                    guard let self, self.isCurrent(lease) else { return }
                    self.appendToMessage(id: aiMessageId, text: delta)
                }
            }
            let toolActivityHandler: @Sendable (String, String, String?, [String: Any]?) -> Void = { [weak self] name, status, toolUseId, input in
                Task { @MainActor [weak self] in
                    guard let self, self.isCurrent(lease) else { return }
                    self.addToolActivity(
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
                    guard let self, self.isCurrent(lease) else { return }
                    self.appendThinking(messageId: aiMessageId, text: text)
                }
            }
            let toolResultDisplayHandler: @Sendable (String, String, String) -> Void = { [weak self] toolUseId, name, output in
                Task { @MainActor [weak self] in
                    guard let self, self.isCurrent(lease) else { return }
                    self.addToolResult(messageId: aiMessageId, toolUseId: toolUseId, name: name, output: output)
                }
            }

            let queryResult = try await TaskChatRuntime.query(
                prompt: trimmedText,
                workstreamId: workstreamId,
                producingTurnId: aiMessageId,
                workspacePath: workspacePath,
                mode: chatMode.rawValue,
                taskContext: taskContext,
                authorizationSnapshot: lease.authorizationSnapshot,
                onTextDelta: textDeltaHandler,
                onToolActivity: toolActivityHandler,
                onThinkingDelta: thinkingDeltaHandler,
                onToolResultDisplay: toolResultDisplayHandler,
                onAuthRequired: onAuthRequired ?? { _, _ in },
                onAuthSuccess: onAuthSuccess ?? { }
            )
            guard isCurrent(lease) else { return }

            guard producingRunProjection.bindResult(
                assistantMessageID: aiMessageId,
                runID: queryResult.runId,
                attemptID: queryResult.attemptId
            ) else {
                throw BridgeError.agentError("Agent result did not match the producing task-chat turn")
            }
            let terminalDisposition = TaskChatTerminalDisposition.classify(queryResult.terminalStatus)

            // Flush remaining streaming buffers
            streamingBuffer.cancelPendingFlush()
            flushStreamingBuffer()

            // Finalize AI message
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                if terminalDisposition != .succeeded {
                    let failureText = queryResult.failure?.displayMessage
                        ?? (terminalDisposition == .cancelled
                            ? "Agent cancelled"
                            : terminalDisposition == .invalid
                                ? "Agent returned an invalid terminal status"
                                : "Agent failed")
                    Self.applyFailureTextIfNeeded(
                        to: &messages[index],
                        errorDescription: failureText)
                    messages[index].isStreaming = false
                    messages[index].resources = queryResult.artifacts.map(ChatResource.artifact)
                    completeRemainingToolCalls(messageId: aiMessageId, terminalStatus: .failed)
                } else {
                    let messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                    messages[index].text = messageText
                    messages[index].isStreaming = false
                    messages[index].resources = queryResult.artifacts.map(ChatResource.artifact)
                    completeRemainingToolCalls(messageId: aiMessageId)
                }
            }
            guard isCurrent(lease) else { return }

            let terminalTurn = try await terminalizeJournalMessage(
                messageId: aiMessageId,
                lease: lease,
                producingRunId: queryResult.runId,
                producingAttemptId: queryResult.attemptId)
            let canonicalSucceeded = terminalTurn.status == .completed
            guard (terminalDisposition == .succeeded) == canonicalSucceeded,
                  terminalDisposition != .invalid else {
                throw BridgeError.agentError("Kernel rejected the agent terminal status")
            }

            log("TaskChatState[\(workstreamId)]: response complete (cost=$\(queryResult.costUsd))")
            if !canonicalSucceeded {
                let failureText =
                    AgentRuntimeStatusStore.shared.projection(for: .workstream(workstreamId: workstreamId))
                    .flatMap(AgentFailureTranscriptFormatter.errorText(for:))
                    ?? (terminalDisposition == .cancelled
                        ? "Agent cancelled"
                        : terminalDisposition == .invalid
                            ? "Agent returned an invalid terminal status"
                            : "Agent failed")
                errorMessage = failureText
            } else {
                await onQueryCompleted?(queryResult, userMessage.id)
                guard isCurrent(lease) else { return }
            }
        } catch {
            guard isCurrent(lease) else { return }
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
                } else {
                    if !failedByUserStop {
                        Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)
                    }
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(
                        messageId: aiMessageId,
                        terminalStatus: .failed
                    )
                }
            }

            await failUnboundJournalMessage(messageId: aiMessageId, lease: lease)

            if !failedByUserStop {
                errorMessage = error.localizedDescription
            }
            logError("TaskChatState[\(workstreamId)]: query failed", error: error)
        }

        guard isCurrent(lease) else { return }
        activeAssistantMessageId = nil
        producingRunProjection.clear()
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
        guard hasCurrentOwner else { return }
        guard projection.surface == .workstream(workstreamId: workstreamId) else { return }
        guard let producingMessageID = producingRunProjection.terminalMessageID(for: projection)
        else { return }
        guard let errorText = AgentFailureTranscriptFormatter.errorText(for: projection) ?? fallbackMessage else { return }
        let failureKey = [projection.runId, projection.attemptId, producingMessageID, errorText]
            .compactMap { $0 }
            .joined(separator: "|")
        guard surfacedFailureKeys.insert(failureKey).inserted else { return }

        requestJournalRefreshForRuntimeFailure(producingMessageID: producingMessageID)
        errorMessage = errorText
    }

    private func observeRuntimeProjectionFailures() {
        guard runtimeProjectionCancellable == nil else { return }
        let surface = AgentSurfaceReference.workstream(workstreamId: workstreamId)
        runtimeProjectionCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
            .dropFirst()
            .sink { [weak self] projections in
                guard let self, self.hasCurrentOwner,
                      let projection = projections[surface.key] else { return }
                self.surfaceRuntimeFailure(projection)
            }
    }

    private func surfaceCurrentRuntimeFailureIfNeeded(fallbackMessage: String? = nil) {
        guard hasCurrentOwner else { return }
        if let projection = AgentRuntimeStatusStore.shared.projection(for: .workstream(workstreamId: workstreamId)) {
            surfaceRuntimeFailure(projection, fallbackMessage: fallbackMessage)
        } else if let fallbackMessage {
            errorMessage = fallbackMessage
        }
    }

    private func requestJournalRefreshForRuntimeFailure(producingMessageID: String) {
        guard messages.contains(where: { $0.id == producingMessageID }),
              let lease = captureOwnerLease() else { return }
        Task { @MainActor [weak self] in
            guard let self, self.isCurrent(lease) else { return }
            await self.refreshJournal(lease: lease)
        }
    }

    // MARK: - Stop

    func stopAgent() {
        guard let lease = captureOwnerLease() else { return }
        guard isSending else { return }
        isStopping = true
        Task {
            await TaskChatRuntime.interrupt(
                workstreamId: workstreamId,
                authorizationSnapshot: lease.authorizationSnapshot
            )
        }
    }

    // MARK: - Streaming Helpers

    private func appendToMessage(id: String, text: String) {
        guard hasCurrentOwner else { return }
        streamingBuffer.appendText(messageId: id, text: text) { [weak self] in
            self?.flushStreamingBuffer()
        }
    }

    private func flushStreamingBuffer() {
        guard hasCurrentOwner else { return }
        streamingBuffer.flush(messages: &messages)
        if let activeAssistantMessageId {
            scheduleJournalUpdate(messageId: activeAssistantMessageId, status: .streaming)
        }
    }

    private func addToolActivity(messageId: String, toolName: String, status: ToolCallStatus, toolUseId: String? = nil, input: [String: Any]? = nil) {
        guard hasCurrentOwner else { return }
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
        guard hasCurrentOwner else { return }
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
        guard hasCurrentOwner else { return }
        streamingBuffer.appendThinking(messageId: messageId, text: text) { [weak self] in
            self?.flushStreamingBuffer()
        }
    }

    /// Matches any in-flight state (`.running`, `.slow`, `.stalled`) so
    /// detector-promoted blocks resolve when the turn ends.
    private func completeRemainingToolCalls(messageId: String, terminalStatus: ToolCallStatus = .completed) {
        guard hasCurrentOwner else { return }
        streamingBuffer.completeRemainingToolCalls(
            messageId: messageId,
            terminalStatus: terminalStatus,
            messages: &messages
        )
        scheduleJournalUpdate(messageId: messageId)
    }
}
