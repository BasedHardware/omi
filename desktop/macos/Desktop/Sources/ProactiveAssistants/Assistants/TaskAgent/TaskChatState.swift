import SwiftUI
import Combine

/// Per-task chat state with its own bridge process and message history.
/// Each task chat is fully independent — no shared state with the sidebar chat.
/// Uses canonical Omi sessions for continuity and preserves legacy ACP IDs only
/// for transitional adapter-native resume compatibility.
@MainActor
class TaskChatState: ObservableObject {
    let taskId: String

    @Published var messages: [ChatMessage] = []
    @Published var isSending = false
    @Published var isStopping = false
    @Published var draftText = ""
    @Published var errorMessage: String?
    @Published var chatMode: ChatMode = .act
    /// Monotonic token that increments each time the local user sends a message
    /// in this task chat. ChatMessagesView observes this for turn anchoring.
    @Published var localSendToken: LocalSendToken = LocalSendToken(generation: 0)

    /// Own bridge process — completely independent from sidebar chat
    private var agentBridge: AgentBridge?
    private var bridgeStarted = false

    /// Harness mode of the currently active bridge, set when the bridge starts.
    /// Used to decide whether adapter-native IDs are valid for legacy resume.
    private var currentHarness: String?

    /// Workspace path for file-system tools
    let workspacePath: String

    /// Adapter-native ACP session used only for legacy resume/adoption.
    /// Canonical Omi runtime sessions are tracked separately in currentOmiSessionId.
    @Published var legacyAcpSessionId: String?
    @Published var currentOmiSessionId: String?

    /// Closure to build system prompt from ChatProvider's cached data
    var systemPromptBuilder: (() -> String)?

    /// Auth callbacks for ACP mode
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?

    /// Follow-up chaining
    private var pendingFollowUpText: String?

    private var runtimeProjectionCancellable: AnyCancellable?
    private var surfacedFailureKeys: Set<String> = []
    private var activeAssistantMessageId: String?

    // MARK: - Streaming Buffers (mirrored from ChatProvider)

    private var streamingTextBuffer: String = ""
    private var streamingThinkingBuffer: String = ""
    private var streamingBufferMessageId: String?
    private var streamingFlushWorkItem: DispatchWorkItem?
    private let streamingFlushInterval: TimeInterval = 0.1

    /// Whether persisted messages have been loaded from GRDB
    private var hasLoadedFromStorage = false

    init(taskId: String, workspacePath: String) {
        self.taskId = taskId
        self.workspacePath = workspacePath
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

            if let legacyAcpSessionId = try? await TaskChatMessageStorage.shared.getACPSessionId(forTaskId: taskId) {
                self.legacyAcpSessionId = legacyAcpSessionId
            }

            surfaceCurrentRuntimeFailureIfNeeded()
            log("TaskChatState[\(taskId)]: Loaded \(records.count) persisted messages")
        } catch {
            logError("TaskChatState[\(taskId)]: Failed to load persisted messages", error: error)
        }
    }

    /// Persist a message to GRDB (fire-and-forget)
    private func persistMessage(_ message: ChatMessage) {
        let taskId = self.taskId
        let legacyAcpSessionId = self.legacyAcpSessionId
        Task.detached {
            do {
                try await TaskChatMessageStorage.shared.saveMessage(message, taskId: taskId, acpSessionId: legacyAcpSessionId)
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
        if let bridge = agentBridge {
            Task { await bridge.stop() }
        }
    }

    // MARK: - Bridge Lifecycle

    private func ensureBridgeStarted() async -> Bool {
        if bridgeStarted {
            let alive = await agentBridge?.isAlive ?? false
            if !alive {
                log("TaskChatState[\(taskId)]: Bridge process died, will restart")
                bridgeStarted = false
            }
        }
        guard !bridgeStarted else { return true }
        do {
            let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? "piMono"
            let harness = ChatProvider.harnessMode(for: ChatProvider.BridgeMode(rawValue: mode) ?? .piMono)
            let bridge = AgentBridge(harnessMode: harness)
            try await bridge.start()
            agentBridge = bridge
            bridgeStarted = true
            currentHarness = harness

            // Legacy resume IDs are only valid for the ACP/pi-mono adapters that
            // created them. Hermes and OpenClaw advertise native resume but would
            // adopt a foreign session ID, causing session/resume on the wrong
            // backend before falling back or failing. Clear it on adapter switch.
            let supportsLegacyResume = (harness == "acp" || harness == "piMono")
            if !supportsLegacyResume, legacyAcpSessionId != nil {
                log("TaskChatState[\(taskId)]: clearing legacy resume ID for harness \(harness)")
                legacyAcpSessionId = nil
            }

            log("TaskChatState[\(taskId)]: agent bridge started")
            return true
        } catch {
            logError("TaskChatState[\(taskId)]: Failed to start bridge", error: error)
            errorMessage = "AI not available: \(error.localizedDescription)"
            TaskAgentStatusRegistry.shared.markFailed(taskId: taskId, error: errorMessage ?? error.localizedDescription)
            return false
        }
    }

    // MARK: - Send Message

    func sendMessage(_ text: String, isFollowUp: Bool = false, taskContext: String? = nil) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        guard !isSending else {
            log("TaskChatState[\(taskId)]: sendMessage called while already sending, ignoring")
            return
        }

        guard await ensureBridgeStarted() else { return }

        // Re-check isSending after the async bridge start — another sendMessage call
        // could have slipped through the initial guard while the bridge was starting.
        guard !isSending else {
            log("TaskChatState[\(taskId)]: sendMessage racing after bridge start, ignoring")
            return
        }

        isSending = true
        errorMessage = nil
        TaskAgentStatusRegistry.shared.markRunning(taskId: taskId)
        // Signal local send for turn anchoring.
        localSendToken = LocalSendToken(generation: localSendToken.generation + 1)

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

            guard let bridge = agentBridge else {
                throw BridgeError.notRunning
            }
            let contextPacketSummary = await buildContextPacketSummary(
                bridge: bridge,
                taskContext: taskContext,
                userMessage: trimmedText
            )

            let fullPrompt: String
            if let contextPacketSummary {
                if let taskContext, !taskContext.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    fullPrompt = "\(contextPacketSummary)\n\n# Task Context\n\n\(taskContext)\n\n---\n\n# User Message\n\n\(trimmedText)"
                } else {
                    fullPrompt = "\(contextPacketSummary)\n\n# User Message\n\n\(trimmedText)"
                }
            } else {
                fullPrompt = trimmedText
            }

            let queryResult = try await bridge.query(
                prompt: fullPrompt,
                systemPrompt: systemPrompt,
                sessionKey: taskId,
                omiSessionId: currentOmiSessionId ?? AgentRuntimeStatusStore.shared.knownSessionId(for: .taskChat(taskId: taskId)),
                surfaceKind: "task_chat",
                externalRefKind: "task",
                externalRefId: taskId,
                legacyClientScope: "task-chat",
                cwd: workspacePath.isEmpty ? nil : workspacePath,
                mode: chatMode.rawValue,
                resume: legacyAcpSessionId,
                onTextDelta: textDeltaHandler,
                onToolCall: toolCallHandler,
                onToolActivity: toolActivityHandler,
                onThinkingDelta: thinkingDeltaHandler,
                onToolResultDisplay: toolResultDisplayHandler,
                onAuthRequired: onAuthRequired ?? { _, _ in },
                onAuthSuccess: onAuthSuccess ?? { }
            )

            // Store canonical and adapter-native IDs separately. The persisted
            // acpSessionId column remains a legacy adapter binding only.
            currentOmiSessionId = queryResult.omiSessionId
            if let adapterSessionId = queryResult.adapterSessionId {
                // Only persist adapter-native IDs for adapters that support the
                // legacy resume protocol (ACP/pi-mono). Hermes/OpenClaw native IDs
                // are not interchangeable — storing them would pollute the resume
                // field and cause a different backend to attempt resuming the
                // wrong session after an adapter switch.
                let supportsLegacyResume = (currentHarness == "acp" || currentHarness == "piMono")
                if supportsLegacyResume {
                    legacyAcpSessionId = adapterSessionId
                } else if legacyAcpSessionId != nil {
                    log("TaskChatState[\(taskId)]: not persisting adapter ID \(adapterSessionId) for non-legacy harness \(currentHarness ?? "?")")
                    legacyAcpSessionId = nil
                }
            }

            // Flush remaining streaming buffers
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
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
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
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
                    Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)
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

        // Chain follow-up if queued
        if let followUp = pendingFollowUpText {
            pendingFollowUpText = nil
            await sendMessage(followUp, isFollowUp: true)
        }
    }

    private func buildContextPacketSummary(
        bridge: AgentBridge,
        taskContext: String?,
        userMessage: String
    ) async -> String? {
        guard let taskContext, !taskContext.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        let redactedPreview = String(taskContext.prefix(1_200))
        let input: [String: Any] = [
            "surfaceKind": "task_chat",
            "objective": userMessage,
            "retentionClass": "ephemeral",
            "ttlMs": 15 * 60 * 1_000,
            "packetJson": [
                "snippets": [
                    [
                        "snippetId": "task_context",
                        "sourceKind": "task_chat",
                        "operation": "selected_task_context",
                        "provenance": ["taskId": taskId],
                        "content": taskContext,
                        "redactedContent": redactedPreview,
                        "sensitivityTier": "local_private",
                    ],
                    [
                        "snippetId": "current_user_message",
                        "sourceKind": "task_chat",
                        "operation": "current_user_message",
                        "provenance": ["taskId": taskId],
                        "content": userMessage,
                        "redactedContent": userMessage,
                        "sensitivityTier": "low",
                    ],
                ],
                "selectedToolBundles": ["desktop.context.local_read", "desktop.tasks.readwrite"],
                "constraints": ["Use the persisted context packet and the model-visible task context; cite task evidence before claiming completion."],
                "evidenceRequired": ["Cite task state or artifact evidence before claiming completion."],
                "boundaryPolicy": ["taskMutations": "candidate_or_dispatch"],
            ],
        ]

        do {
            let raw = try await bridge.controlTool(name: "build_desktop_context_packet", input: input)
            guard let data = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  object["ok"] as? Bool == true,
                  let packet = object["packet"] as? [String: Any],
                  let packetId = packet["packetId"] as? String,
                  let preview = packet["redactedPreviewJson"] as? [String: Any] else {
                return "# Context Packet\n\nA scoped task-chat context packet was requested but could not be parsed."
            }
            let previewData = try? JSONSerialization.data(withJSONObject: preview, options: [.sortedKeys])
            let previewText = previewData.flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
            return """
            # Context Packet

            Persisted DesktopContextPacket `\(packetId)` audits the scoped task context. The full task context is included below in the prompt. Redacted preview:

            \(previewText)
            """
        } catch {
            logError("TaskChatState[\(taskId)]: failed to build context packet", error: error)
            return nil
        }
    }

    // MARK: - Follow-Up

    static func applyFailureTextIfNeeded(to message: inout ChatMessage, errorDescription: String) {
        if message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            message.text = AgentFailureTranscriptFormatter.transcriptText(for: errorDescription) ?? "Failed: Agent failed"
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
        await agentBridge?.interrupt()
        log("TaskChatState[\(taskId)]: follow-up queued, interrupt sent")
    }

    // MARK: - Stop

    func stopAgent() {
        guard isSending else { return }
        isStopping = true
        Task {
            await agentBridge?.interrupt()
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
        ToolCallBlockUpdater.applyToolActivity(
            to: &messages[index].contentBlocks,
            toolName: toolName,
            status: status,
            toolUseId: toolUseId,
            input: input
        )
    }

    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        ToolCallBlockUpdater.applyToolOutput(
            to: &messages[index].contentBlocks,
            toolUseId: toolUseId,
            name: name,
            output: output
        )
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

    /// Mirrors ChatProvider.completeRemainingToolCalls — matches any
    /// in-flight state (`.running`, `.slow`, `.stalled`) so detector-
    /// promoted blocks resolve when the turn ends.
    private func completeRemainingToolCalls(messageId: String, terminalStatus: ToolCallStatus = .completed) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        ToolCallBlockUpdater.completeRemainingToolCalls(
            in: &messages[index].contentBlocks,
            terminalStatus: terminalStatus
        )
    }
}
