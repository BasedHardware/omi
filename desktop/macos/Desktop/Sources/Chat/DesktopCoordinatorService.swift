import Foundation

protocol DesktopCoordinatorRuntimeControlling {
  func directControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: [String: Any]
  ) async throws -> String
}

extension AgentRuntimeProcess: DesktopCoordinatorRuntimeControlling {}

struct DesktopCoordinatorAwarenessSnapshot: Codable {
  let generatedAt: String
  let source: String
  let runtimeControlTools: [String]
  let automation: DesktopCoordinatorAutomationProjection
  let sessions: [DesktopCoordinatorSessionProjection]
  let debugDispatches: [DesktopCoordinatorDispatchProjection]
  let runtimeError: String?
}

struct DesktopCoordinatorAutomationProjection: Codable {
  let bridgeEnabled: Bool
  let bridgePort: UInt16
  let bundleIdentifier: String
  let appState: String
  let selectedTab: String?
  let askOmiOpen: Bool
  let floatingBarVisible: Bool
}

struct DesktopCoordinatorSessionProjection: Codable {
  let sessionId: String?
  let title: String
  let surfaceKind: String?
  let externalRefKind: String?
  let externalRefId: String?
  let status: String
  let runId: String?
  let runStatus: String?
  let runMode: String?
  let attemptId: String?
  let updatedAt: String?
  let source: String
}

struct DesktopCoordinatorActionQueueItem: Codable {
  let id: String
  let rank: Int
  let kind: String
  let title: String
  let status: String
  let sessionId: String?
  let runId: String?
  let dispatchId: String?
  let source: String
}

struct DesktopCoordinatorOpenLoops: Codable {
  let generatedAt: String
  let items: [DesktopCoordinatorActionQueueItem]
}

struct DesktopCoordinatorRouteDecision: Codable {
  let generatedAt: String
  let intent: String
  let route: String
  let reason: String
  let sessionId: String?
  let runId: String?
  let requiresDispatch: Bool
}

struct DesktopCoordinatorDispatchProjection: Codable {
  let dispatchId: String
  let kind: String
  let status: String
  let title: String
  let decisionPrompt: String
  let recommendedDefault: String?
  let sourceSessionId: String?
  let sourceRunId: String?
  let createdAt: String
  let resolvedAt: String?
  let resolution: String?
  let source: String
}

@MainActor
final class DesktopCoordinatorService {
  static let shared = DesktopCoordinatorService()

  private enum ToolName {
    static let listAgentSessions = "list_agent_sessions"
    static let getAgentRun = "get_agent_run"
    static let buildAwarenessSnapshot = "build_desktop_awareness_snapshot"
    static let listActionQueue = "list_desktop_action_queue"
    static let getOpenLoops = "get_desktop_open_loops"
    static let routeIntent = "route_desktop_intent"
    static let createDispatch = "create_desktop_dispatch"
    static let resolveDispatch = "resolve_desktop_dispatch"
    static let sendAgentMessage = "send_agent_message"
    static let delegateAgent = "delegate_agent"
  }

  private let runtime: DesktopCoordinatorRuntimeControlling
  private let clientId: String
  private let harnessModeProvider: @MainActor () -> String
  private let formatter = ISO8601DateFormatter()

  init(
    runtime: DesktopCoordinatorRuntimeControlling = AgentRuntimeProcess.shared,
    clientId: String = "desktop-coordinator",
    harnessModeProvider: @escaping @MainActor () -> String = AgentControlService.currentHarnessMode
  ) {
    self.runtime = runtime
    self.clientId = clientId
    self.harnessModeProvider = harnessModeProvider
  }

  func awarenessSnapshot() async -> DesktopCoordinatorAwarenessSnapshot {
    let automationSnapshot = DesktopAutomationStateStore.shared.current()
    do {
      let raw = try await callRuntimeControlTool(ToolName.listAgentSessions, input: [:])
      return DesktopCoordinatorAwarenessSnapshot(
        generatedAt: nowString(),
        source: "swift_projection",
        runtimeControlTools: [ToolName.listAgentSessions],
        automation: DesktopCoordinatorAutomationProjection(snapshot: automationSnapshot),
        sessions: parseSessions(from: raw),
        debugDispatches: [],
        runtimeError: nil
      )
    } catch {
      return DesktopCoordinatorAwarenessSnapshot(
        generatedAt: nowString(),
        source: "swift_projection",
        runtimeControlTools: [ToolName.listAgentSessions],
        automation: DesktopCoordinatorAutomationProjection(snapshot: automationSnapshot),
        sessions: [],
        debugDispatches: [],
        runtimeError: error.localizedDescription
      )
    }
  }

  func awarenessSnapshotJSON(limit: Int = 50) async throws -> String {
    try await callRuntimeControlTool(ToolName.buildAwarenessSnapshot, input: ["limit": limit])
  }

  func actionQueueJSON(limit: Int = 50) async throws -> String {
    try await callRuntimeControlTool(ToolName.listActionQueue, input: ["limit": limit])
  }

  func openLoopsJSON(limit: Int = 50) async throws -> String {
    try await callRuntimeControlTool(ToolName.getOpenLoops, input: ["limit": limit])
  }

  func routeIntentJSON(intent: String, surfaceKind: String? = nil, taskId: String? = nil) async throws -> String {
    var input: [String: Any] = [
      "utterance": intent,
      "surfaceKind": surfaceKind?.isEmpty == false ? surfaceKind! : "main_chat",
    ]
    if let taskId, !taskId.isEmpty {
      input["taskId"] = taskId
    }
    return try await callRuntimeControlTool(ToolName.routeIntent, input: input)
  }

  func createDispatchJSON(
    kind: String,
    title: String,
    decisionPrompt: String,
    recommendedDefault: String? = nil,
    sourceSessionId: String? = nil,
    sourceRunId: String? = nil
  ) async throws -> String {
    var input: [String: Any] = [
      "kind": kind.isEmpty ? "routing_choice" : kind,
      "priority": 50,
      "title": title.isEmpty ? "Coordinator attention" : title,
      "decisionPrompt": decisionPrompt.isEmpty ? "Review this coordinator attention item." : decisionPrompt,
    ]
    if let recommendedDefault, !recommendedDefault.isEmpty { input["recommendedDefault"] = recommendedDefault }
    if let sourceSessionId, !sourceSessionId.isEmpty { input["sourceSessionId"] = sourceSessionId }
    if let sourceRunId, !sourceRunId.isEmpty { input["sourceRunId"] = sourceRunId }
    return try await callRuntimeControlTool(ToolName.createDispatch, input: input)
  }

  func resolveDispatchJSON(dispatchId: String, resolution: String) async throws -> String {
    try await callRuntimeControlTool(
      ToolName.resolveDispatch,
      input: [
        "dispatchId": dispatchId,
        "status": resolution == "cancelled" ? "cancelled" : "resolved",
        "resolution": ["decision": resolution.isEmpty ? "resolved" : resolution],
      ]
    )
  }

  func actionQueue() async -> [DesktopCoordinatorActionQueueItem] {
    let snapshot = await awarenessSnapshot()
    return deriveActionQueue(from: snapshot)
  }

  func openLoops() async -> DesktopCoordinatorOpenLoops {
    let queue = await actionQueue()
    let items = queue.filter { item in
      ["approval", "failed_run", "stale_or_active_run", "debug_dispatch"].contains(item.kind)
    }
    return DesktopCoordinatorOpenLoops(generatedAt: nowString(), items: items)
  }

  func inspectRun(sessionId: String?, runId: String?) async throws -> String {
    var input: [String: Any] = [:]
    if let sessionId, !sessionId.isEmpty { input["sessionId"] = sessionId }
    if let runId, !runId.isEmpty { input["runId"] = runId }
    return try await callRuntimeControlTool(ToolName.getAgentRun, input: input)
  }

  func routeIntent(intent: String, surfaceKind: String? = nil, taskId: String? = nil) async -> DesktopCoordinatorRouteDecision {
    let normalized = intent.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let snapshot = await awarenessSnapshot()
    let queue = deriveActionQueue(from: snapshot)

    if let blocking = queue.first(where: { $0.kind == "approval" || $0.kind == "debug_dispatch" }) {
      return DesktopCoordinatorRouteDecision(
        generatedAt: nowString(),
        intent: intent,
        route: "review_attention",
        reason: "A pending attention item should be resolved before dispatching more work.",
        sessionId: blocking.sessionId,
        runId: blocking.runId,
        requiresDispatch: false
      )
    }

    if shouldCreateDispatch(for: normalized) {
      return DesktopCoordinatorRouteDecision(
        generatedAt: nowString(),
        intent: intent,
        route: "create_dispatch",
        reason: "The intent crosses an approval or privacy boundary.",
        sessionId: nil,
        runId: nil,
        requiresDispatch: true
      )
    }

    if let taskId, let match = snapshot.sessions.first(where: {
      $0.surfaceKind == "task_chat" && $0.externalRefKind == "task" && $0.externalRefId == taskId
    }) {
      return DesktopCoordinatorRouteDecision(
        generatedAt: nowString(),
        intent: intent,
        route: "resume_session",
        reason: "A canonical task-chat session is already associated with this task surface.",
        sessionId: match.sessionId,
        runId: match.runId,
        requiresDispatch: false
      )
    }

    if let active = snapshot.sessions.first(where: { isActive($0.runStatus ?? $0.status) }) {
      return DesktopCoordinatorRouteDecision(
        generatedAt: nowString(),
        intent: intent,
        route: "resume_or_inspect_session",
        reason: "There is existing active coordinator-relevant work.",
        sessionId: active.sessionId,
        runId: active.runId,
        requiresDispatch: false
      )
    }

    let route = normalized.count > 140 || normalized.contains("build") || normalized.contains("implement")
      ? "delegate_agent"
      : "answer_or_start_session"
    return DesktopCoordinatorRouteDecision(
      generatedAt: nowString(),
      intent: intent,
      route: route,
      reason: "No blocking attention item or reusable active run was found.",
      sessionId: nil,
      runId: nil,
      requiresDispatch: false
    )
  }

  func runtimeControlManifest() -> [String] {
    [
      ToolName.listAgentSessions,
      ToolName.getAgentRun,
      ToolName.buildAwarenessSnapshot,
      ToolName.listActionQueue,
      ToolName.getOpenLoops,
      ToolName.routeIntent,
      ToolName.createDispatch,
      ToolName.resolveDispatch,
      ToolName.sendAgentMessage,
      ToolName.delegateAgent,
    ]
  }

  private func callRuntimeControlTool(_ name: String, input: [String: Any]) async throws -> String {
    try await runtime.directControlTool(
      clientId: clientId,
      harnessMode: harnessModeProvider(),
      name: name,
      input: input
    )
  }

  private func deriveActionQueue(from snapshot: DesktopCoordinatorAwarenessSnapshot) -> [DesktopCoordinatorActionQueueItem] {
    var items: [DesktopCoordinatorActionQueueItem] = []

    for dispatch in snapshot.debugDispatches {
      items.append(
        DesktopCoordinatorActionQueueItem(
          id: dispatch.dispatchId,
          rank: 1,
          kind: "debug_dispatch",
          title: dispatch.title,
          status: dispatch.status,
          sessionId: dispatch.sourceSessionId,
          runId: dispatch.sourceRunId,
          dispatchId: dispatch.dispatchId,
          source: dispatch.source
        )
      )
    }

    for session in snapshot.sessions {
      let status = session.runStatus ?? session.status
      let id = session.runId ?? session.sessionId ?? UUID().uuidString
      if status == "waiting_approval" {
        items.append(queueItem(id: id, rank: 1, kind: "approval", session: session, status: status))
      } else if ["failed", "orphaned", "timed_out"].contains(status) {
        items.append(queueItem(id: id, rank: 2, kind: "failed_run", session: session, status: status))
      } else if isActive(status) {
        items.append(queueItem(id: id, rank: 4, kind: "stale_or_active_run", session: session, status: status))
      } else if ["succeeded", "completed"].contains(status) {
        items.append(queueItem(id: id, rank: 5, kind: "completed_run_review", session: session, status: status))
      }
    }

    return items.sorted {
      if $0.rank == $1.rank { return $0.id < $1.id }
      return $0.rank < $1.rank
    }
  }

  private func queueItem(
    id: String,
    rank: Int,
    kind: String,
    session: DesktopCoordinatorSessionProjection,
    status: String
  ) -> DesktopCoordinatorActionQueueItem {
    DesktopCoordinatorActionQueueItem(
      id: id,
      rank: rank,
      kind: kind,
      title: session.title,
      status: status,
      sessionId: session.sessionId,
      runId: session.runId,
      dispatchId: nil,
      source: session.source
    )
  }

  private func parseSessions(from raw: String) -> [DesktopCoordinatorSessionProjection] {
    guard let object = jsonObject(from: raw), object["ok"] as? Bool != false else {
      return []
    }
    let sessions = object["sessions"] as? [[String: Any]] ?? []
    return sessions.map { summary in
      let session = summary["session"] as? [String: Any] ?? [:]
      let latestRun = summary["latestRun"] as? [String: Any] ?? [:]
      let activeRun = summary["activeRun"] as? [String: Any] ?? [:]
      let selectedRun = activeRun.isEmpty ? latestRun : activeRun
      let latestAttempt = summary["latestAttempt"] as? [String: Any] ?? [:]
      let activeAttempt = summary["activeAttempt"] as? [String: Any] ?? [:]
      let selectedAttempt = activeRun.isEmpty ? latestAttempt : activeAttempt
      let sessionStatus = stringValue(session["status"]) ?? "unknown"
      let title = stringValue(session["title"])
        ?? stringValue(session["surfaceKind"])
        ?? stringValue(session["omiSessionId"])
        ?? "Untitled agent"

      return DesktopCoordinatorSessionProjection(
        sessionId: stringValue(session["omiSessionId"]) ?? stringValue(session["sessionId"]),
        title: title,
        surfaceKind: stringValue(session["surfaceKind"]),
        externalRefKind: stringValue(session["externalRefKind"]),
        externalRefId: stringValue(session["externalRefId"]),
        status: sessionStatus,
        runId: stringValue(selectedRun["runId"]),
        runStatus: stringValue(selectedRun["status"]),
        runMode: stringValue(selectedRun["mode"]),
        attemptId: stringValue(selectedAttempt["attemptId"]),
        updatedAt: stringValue(session["updatedAt"]) ?? stringValue(selectedRun["updatedAt"]),
        source: "runtime_control_tool:list_agent_sessions"
      )
    }
  }

  private func shouldCreateDispatch(for normalizedIntent: String) -> Bool {
    let dispatchTerms = [
      "approve",
      "send",
      "share",
      "post",
      "delete",
      "remove",
      "screenshot",
      "screen history",
      "remember that",
      "save this memory",
    ]
    return dispatchTerms.contains { normalizedIntent.contains($0) }
  }

  private func isActive(_ status: String) -> Bool {
    ["queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling"].contains(status)
  }

  private func nowString() -> String {
    formatter.string(from: Date())
  }

  private func jsonObject(from raw: String) -> [String: Any]? {
    guard let data = raw.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  }

  private func stringValue(_ value: Any?) -> String? {
    guard let text = value as? String else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}

extension DesktopCoordinatorAutomationProjection {
  init(snapshot: DesktopAutomationSnapshot) {
    self.init(
      bridgeEnabled: snapshot.bridgeEnabled,
      bridgePort: snapshot.bridgePort,
      bundleIdentifier: snapshot.bundleIdentifier,
      appState: snapshot.appState,
      selectedTab: snapshot.selectedTab,
      askOmiOpen: snapshot.askOmiOpen,
      floatingBarVisible: snapshot.floatingBarVisible
    )
  }
}

extension Encodable {
  func desktopCoordinatorJSONString() -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(self),
      let string = String(data: data, encoding: .utf8)
    else {
      return "{}"
    }
    return string
  }
}
