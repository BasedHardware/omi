import Foundation

/// Shared agent bridge for all task-chat surfaces. Session identity and execution
/// truth live in the kernel (`surfaceKind = task_chat`); this bridge is transport only.
@MainActor
enum TaskChatRuntime {
    private static var agentBridge: AgentBridge?
    private static var bridgeStarted = false
    private static var activeTaskId: String?

    static func query(
        prompt: String,
        systemPrompt: String,
        taskId: String,
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
        if let activeTaskId, activeTaskId != taskId {
            throw BridgeError.requestAlreadyActive
        }
        activeTaskId = taskId
        defer {
            if activeTaskId == taskId {
                activeTaskId = nil
            }
        }
        return try await bridge.query(
            prompt: prompt,
            systemPrompt: systemPrompt,
            surface: .taskChat(taskId: taskId),
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

    static func interrupt(taskId: String) async {
        guard activeTaskId == taskId else { return }
        await agentBridge?.interrupt()
    }

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

        let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? "piMono"
        let harness = ChatProvider.harnessMode(for: ChatProvider.BridgeMode(rawValue: mode) ?? .piMono)
        let bridge = AgentClient.makeBridge(harnessMode: harness)
        try await bridge.start()
        agentBridge = bridge
        bridgeStarted = true
        log("TaskChatRuntime: shared task-chat bridge started")
        return bridge
    }
}
