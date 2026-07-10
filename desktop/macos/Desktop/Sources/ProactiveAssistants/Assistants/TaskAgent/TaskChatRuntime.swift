import Foundation

/// Shared agent bridge for task-backed workstream surfaces. Session identity and
/// execution truth live in the kernel; this bridge is transport only.
@MainActor
enum TaskChatRuntime {
    private static var agentBridge: AgentBridge?
    private static var bridgeStarted = false
    private static var activeWorkstreamId: String?

    static func query(
        prompt: String,
        systemPrompt: String,
        workstreamId: String,
        workspacePath: String,
        mode: String,
        surfaceContextJson: String?,
        model: String? = nil,
        onTextDelta: @escaping AgentBridge.TextDeltaHandler,
        onToolCall: @escaping AgentBridge.ToolCallHandler,
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
        return try await bridge.query(
            prompt: prompt,
            systemPrompt: systemPrompt,
            surface: .workstream(workstreamId: workstreamId),
            cwd: workspacePath.isEmpty ? nil : workspacePath,
            mode: mode,
            model: model,
            surfaceContextJson: surfaceContextJson,
            onTextDelta: onTextDelta,
            onToolCall: onToolCall,
            onToolActivity: onToolActivity,
            onThinkingDelta: onThinkingDelta,
            onToolResultDisplay: onToolResultDisplay,
            onAuthRequired: onAuthRequired,
            onAuthSuccess: onAuthSuccess
        )
    }

    static func importLegacyHistory(
        workstreamId: String,
        messages: [ChatMessage]
    ) async throws {
        guard !messages.isEmpty else { return }
        let bridge = try await sharedBridge()
        await bridge.importConversationTurns(
            surface: .workstream(workstreamId: workstreamId),
            turns: messages.suffix(100).map {
                (
                    role: $0.sender == .user ? "user" : "assistant",
                    content: $0.text,
                    createdAtMs: Int($0.createdAt.timeIntervalSince1970 * 1_000)
                )
            }
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
        await bridge.importConversationTurns(
            surface: .taskChat(taskId: taskId),
            turns: [(role: "user", content: "Draft the launch email", createdAtMs: 1_783_669_600_000)]
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
