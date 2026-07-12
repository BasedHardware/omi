import Foundation

/// Shared agent bridge for task-backed workstream surfaces. Session identity and
/// execution truth live in the kernel; this bridge is transport only.
@MainActor
enum TaskChatRuntime {
    private static var agentBridge: AgentBridge?
    private static var bridgeStarted = false
    private static var activeWorkstreamId: String?

    static func attachJournalEvents(
        workstreamId: String,
        wake: @escaping @MainActor () -> Void
    ) async throws -> UUID {
        let bridge = try await sharedBridge()
        await KernelJournalEventHub.shared.attach(bridge: bridge)
        return KernelJournalEventHub.shared.subscribe(
            surface: .workstream(workstreamId: workstreamId),
            wake: wake
        )
    }

    static func listJournalTurns(
        workstreamId: String,
        afterTurnSeq: Int,
        limit: Int = 100
    ) async throws -> AgentRuntimeProcess.JournalOperationResult {
        let bridge = try await sharedBridge()
        return try await bridge.listJournalTurns(
            surface: .workstream(workstreamId: workstreamId),
            afterTurnSeq: afterTurnSeq,
            limit: limit
        )
    }

    static func recordJournalMessage(
        workstreamId: String,
        message: ChatMessage,
        status: KernelJournalTurnStatus,
        continuityKey: String? = nil
    ) async throws -> KernelJournalTurn {
        let bridge = try await sharedBridge()
        return try await bridge.recordJournalTurn(
            surface: .workstream(workstreamId: workstreamId),
            turn: message.journalWrite(
                origin: "workstream",
                status: status,
                delivery: .local,
                continuityKey: continuityKey,
                messageSource: "workstream"
            )
        )
    }

    static func updateJournalMessage(
        workstreamId: String,
        message: ChatMessage,
        status: KernelJournalTurnStatus? = nil
    ) async throws -> KernelJournalTurn {
        let bridge = try await sharedBridge()
        return try await bridge.updateJournalTurn(
            surface: .workstream(workstreamId: workstreamId),
            update: message.journalUpdate(status: status)
        )
    }

    static func importLegacyMessages(
        workstreamId: String,
        messages: [ChatMessage]
    ) async throws {
        guard !messages.isEmpty else { return }
        guard messages.count <= TaskChatLegacyCompatibilityMetadata.pageSize else {
            throw BridgeError.agentError("Legacy task chat import page exceeds compatibility bound")
        }
        for message in messages {
            _ = try await recordJournalMessage(
                workstreamId: workstreamId,
                message: message,
                status: .completed
            )
        }
    }

    static func query(
        prompt: String,
        workstreamId: String,
        workspacePath: String,
        mode: String,
        taskContext: String?,
        onTextDelta: @escaping AgentBridge.TextDeltaHandler,
        onToolActivity: @escaping AgentBridge.ToolActivityHandler,
        onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
        onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
        onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
        onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
    ) async throws -> AgentBridge.QueryResult {
        let bridge = try await sharedBridge()
        if activeWorkstreamId != nil {
            throw BridgeError.requestAlreadyActive
        }
        activeWorkstreamId = workstreamId
        defer {
            if activeWorkstreamId == workstreamId {
                activeWorkstreamId = nil
            }
        }
        let surface = AgentSurfaceReference.workstream(workstreamId: workstreamId)
        let mode = UserDefaults.standard.string(forKey: .chatBridgeMode) ?? "piMono"
        let harness = ChatProvider.harnessMode(for: ChatProvider.BridgeMode(rawValue: mode) ?? .piMono)
        guard let adapterId = AgentRuntimeProcess.adapterId(forHarnessMode: harness) else {
            throw BridgeError.agentError("Unknown AI runtime mode: \(harness)")
        }
        let usesNativeModelChoice = harness == "hermes" || harness == "openclaw"
        let creationProfile = AgentSessionCreationProfile(
            adapterId: adapterId,
            modelProfile: usesNativeModelChoice ? nil : ModelQoS.Claude.chat,
            workingDirectory: workspacePath.isEmpty
                ? AgentRuntimeProcess.defaultArtifactsDirectory()
                : workspacePath
        )
        let session = try await bridge.resolveSurfaceSession(
            surface,
            creationProfile: creationProfile
        )
        var snapshot = try await bridge.getContextSnapshot(
            sessionId: session.sessionId,
            surfaceKind: surface.surfaceKind
        )
        let contextInputs: [(AgentContextSource, AgentContextSourceOutcome, [String: Any])] = [
            (
                .workspace,
                workspacePath.isEmpty ? .empty : .available,
                workspacePath.isEmpty ? [:] : ["workingDirectory": workspacePath]
            ),
            (
                .surface,
                taskContext?.isEmpty == false ? .available : .empty,
                taskContext?.isEmpty == false ? ["taskContext": taskContext!] : [:]
            ),
        ]
        for (source, outcome, payload) in contextInputs {
            let revision = try AgentContextRevision.make(source: source, payload: payload, outcome: outcome)
            guard snapshot.sourceRevision(for: source) != revision else { continue }
            _ = try await bridge.updateContextSource(
                sessionId: session.sessionId,
                surfaceKind: surface.surfaceKind,
                source: source,
                sourceRevision: revision,
                outcome: outcome,
                capturedAtMs: Int(Date().timeIntervalSince1970 * 1_000),
                payload: payload
            )
            snapshot = try await bridge.getContextSnapshot(
                sessionId: session.sessionId,
                surfaceKind: surface.surfaceKind
            )
        }
        await bridge.warmupSession(session)
        return try await bridge.query(
            prompt: prompt,
            session: session,
            surface: surface,
            mode: mode,
            expectedContext: snapshot.freshness,
            onTextDelta: onTextDelta,
            onToolActivity: onToolActivity,
            onThinkingDelta: onThinkingDelta,
            onToolResultDisplay: onToolResultDisplay,
            onAuthRequired: onAuthRequired,
            onAuthSuccess: onAuthSuccess
        )
    }

    static func interrupt(workstreamId: String) async {
        guard activeWorkstreamId == workstreamId else { return }
        await agentBridge?.interrupt()
    }

    static func controlTool(name: String, input: [String: Any]) async throws -> String {
        let bridge = try await sharedBridge()
        return try await bridge.controlTool(name: name, input: input)
    }

#if DEBUG
    static func debugAutomationControlTool(name: String, input: [String: Any]) async throws -> String {
        let bridge = try await sharedBridge()
        return try await bridge.debugAutomationControlTool(name: name, input: input)
    }

    static func debugImportLegacyTurn(taskId: String) async throws {
        let bridge = try await sharedBridge()
        let message = ChatMessage(
            id: "debug-legacy-task-turn",
            text: "Draft the launch email",
            createdAt: Date(timeIntervalSince1970: 1_783_669_600),
            sender: .user,
            turnOwner: .taskChat(taskId)
        )
        _ = try await bridge.recordJournalTurn(
            surface: .taskChat(taskId: taskId),
            turn: message.journalWrite(
                origin: "task_chat",
                status: .completed,
                delivery: .local,
                messageSource: "task_chat"
            )
        )
    }
#endif

    private static func sharedBridge() async throws -> AgentBridge {
        if bridgeStarted {
            let alive = await agentBridge?.isAlive ?? false
            if !alive {
                log("TaskChatRuntime: bridge process died, will restart")
                bridgeStarted = false
            }
        }
        if let bridge = agentBridge, bridgeStarted {
            return bridge
        }

        let mode = UserDefaults.standard.string(forKey: .chatBridgeMode) ?? "piMono"
        let harness = ChatProvider.harnessMode(for: ChatProvider.BridgeMode(rawValue: mode) ?? .piMono)
        let bridge = AgentClient.makeBridge(harnessMode: harness)
        try await bridge.start()
        agentBridge = bridge
        bridgeStarted = true
        log("TaskChatRuntime: shared task-chat bridge started")
        return bridge
    }
}
