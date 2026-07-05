import Combine
import Foundation

struct AgentSurfaceReference: Hashable, Sendable {
  let surfaceKind: String
  let externalRefKind: String
  let externalRefId: String

  var key: String { "\(surfaceKind)|\(externalRefKind)|\(externalRefId)" }
  var displayRef: String { "\(externalRefKind):\(externalRefId)" }

  static func mainChat(chatId: String?) -> AgentSurfaceReference {
    AgentSurfaceReference(
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: chatId?.isEmpty == false ? chatId! : "default"
    )
  }

  static func taskChat(taskId: String) -> AgentSurfaceReference {
    AgentSurfaceReference(surfaceKind: "task_chat", externalRefKind: "task", externalRefId: taskId)
  }

  /// Notch / floating "Omi Chat" text conversation. Used as an independent
  /// completed-agent-delta consumer so a finished sub-agent's artifacts can be
  /// delivered to the floating bar separately from the main chat.
  static func floatingChat(chatId: String? = nil) -> AgentSurfaceReference {
    AgentSurfaceReference(
      surfaceKind: "floating_chat",
      externalRefKind: "chat",
      externalRefId: chatId?.isEmpty == false ? chatId! : "default"
    )
  }

  static func floatingPill(pillId: UUID) -> AgentSurfaceReference {
    AgentSurfaceReference(surfaceKind: "background_agent", externalRefKind: "pill", externalRefId: pillId.uuidString)
  }
}

enum AgentLegacyClientScope {
  static let floatingPill = "floating-pill"
}

enum AgentRunProjectionStatus: String, Sendable {
  case idle
  case queued
  case starting
  case running
  case waitingInput = "waiting_input"
  case waitingApproval = "waiting_approval"
  case cancelling
  case succeeded
  case failed
  case cancelled
  case timedOut = "timed_out"
  case orphaned

  var isActive: Bool {
    switch self {
    case .queued, .starting, .running, .waitingInput, .waitingApproval, .cancelling:
      return true
    case .idle, .succeeded, .failed, .cancelled, .timedOut, .orphaned:
      return false
    }
  }

  var isTerminal: Bool {
    switch self {
    case .succeeded, .failed, .cancelled, .timedOut, .orphaned:
      return true
    case .idle, .queued, .starting, .running, .waitingInput, .waitingApproval, .cancelling:
      return false
    }
  }

  static func fromWire(_ value: String?) -> AgentRunProjectionStatus? {
    guard let value else { return nil }
    switch value {
    case "idle": return .idle
    case "queued": return .queued
    case "starting": return .starting
    case "running": return .running
    case "waiting_input": return .waitingInput
    case "waiting_approval": return .waitingApproval
    case "cancelling": return .cancelling
    case "succeeded": return .succeeded
    case "failed": return .failed
    case "cancelled": return .cancelled
    case "timed_out": return .timedOut
    case "orphaned": return .orphaned
    default: return nil
    }
  }
}

struct AgentRunProjection: Identifiable, Sendable {
  var id: String { runId ?? surface.key }
  let surface: AgentSurfaceReference
  var sessionId: String?
  var runId: String?
  var attemptId: String?
  var adapterSessionId: String?
  var status: AgentRunProjectionStatus
  var statusText: String?
  var errorMessage: String?
  var failure: AgentRuntimeFailure?
  var updatedAt: Date
  var completedAt: Date?
  var costUsd: Double?
  var inputTokens: Int?
  var outputTokens: Int?
}

@MainActor
final class AgentRuntimeStatusStore: ObservableObject {
  static let shared = AgentRuntimeStatusStore()

  @Published private(set) var projectionsBySurface: [String: AgentRunProjection] = [:]
  @Published private(set) var sessionIdBySurface: [String: String] = [:]
  @Published private(set) var runIdBySurface: [String: String] = [:]

  private var projectionByRunId: [String: AgentRunProjection] = [:]
  private var projectionBySessionId: [String: AgentRunProjection] = [:]

  init() {}

  func reset() {
    projectionsBySurface.removeAll()
    sessionIdBySurface.removeAll()
    runIdBySurface.removeAll()
    projectionByRunId.removeAll()
    projectionBySessionId.removeAll()
  }

  func projection(for surface: AgentSurfaceReference) -> AgentRunProjection? {
    projectionsBySurface[surface.key]
  }

  func knownSessionId(for surface: AgentSurfaceReference) -> String? {
    sessionIdBySurface[surface.key]
  }

  func clear(surface: AgentSurfaceReference) {
    if let existing = projectionsBySurface.removeValue(forKey: surface.key) {
      if let runId = existing.runId {
        projectionByRunId.removeValue(forKey: runId)
      }
      if let sessionId = existing.sessionId {
        projectionBySessionId.removeValue(forKey: sessionId)
      }
    }
    if let runId = runIdBySurface.removeValue(forKey: surface.key) {
      projectionByRunId.removeValue(forKey: runId)
    }
    if let sessionId = sessionIdBySurface.removeValue(forKey: surface.key) {
      projectionBySessionId.removeValue(forKey: sessionId)
    }
  }

  func beginRequest(surface: AgentSurfaceReference, statusText: String? = "Starting...") {
    clearTerminalProjectionForNewRun(surface: surface)
    update(surface: surface, status: .starting, statusText: statusText, terminal: false)
  }

  func updateActivity(surface: AgentSurfaceReference, statusText: String?) {
    if projectionsBySurface[surface.key]?.status.isTerminal == true {
      return
    }
    update(surface: surface, status: .running, statusText: statusText, terminal: false)
  }

  func recordLocalFailure(surface: AgentSurfaceReference, error: String) {
    let failure = AgentRuntimeFailure(
      code: "local_failure",
      userMessage: error,
      technicalMessage: nil,
      source: "runtime",
      adapterId: nil,
      provider: nil,
      retryable: nil
    )
    update(surface: surface, status: .failed, statusText: nil, errorMessage: error, failure: failure, terminal: true)
  }

  func recordLocalCancellation(surface: AgentSurfaceReference, message: String? = nil) {
    update(surface: surface, status: .cancelled, statusText: nil, errorMessage: message, terminal: true)
  }

  func recordAcceptedRun(surface: AgentSurfaceReference, sessionId: String, runId: String, attemptId: String?, statusText: String?) {
    var payload: [String: Any] = [
      "sessionId": sessionId,
      "runId": runId,
    ]
    if let attemptId, !attemptId.isEmpty {
      payload["attemptId"] = attemptId
    }
    update(surface: surface, status: .running, statusText: statusText, terminal: false, payload: payload)
  }

  func ingest(message: AgentRuntimeProcess.RuntimeMessage, surface: AgentSurfaceReference) {
    switch message.kind {
    case .textDelta, .thinkingDelta:
      update(surface: surface, status: .running, statusText: nil, terminal: false, payload: message.payload)
    case .toolActivity:
      let name = message.payload["name"] as? String
      let status = message.payload["status"] as? String
      let text = status == "completed" ? nil : name.map { ChatContentBlock.displayName(for: $0) }
      update(surface: surface, status: .running, statusText: text, terminal: false, payload: message.payload)
    case .toolResultDisplay:
      let name = message.payload["name"] as? String
      let displayName = name.map { ChatContentBlock.displayName(for: $0) }
      if projectionsBySurface[surface.key]?.status == .cancelling {
        return
      }
      // Ambient status surfaces are visible outside the chat transcript; never
      // echo raw tool output here because it may contain secrets or local paths.
      update(surface: surface, status: .running, statusText: displayName, terminal: false, payload: message.payload)
    case .cancelAck:
      let accepted = message.payload["accepted"] as? Bool ?? false
      update(surface: surface, status: accepted ? .cancelling : .running, statusText: nil, terminal: false, payload: message.payload)
    case .result:
      let terminalStatus = AgentRunProjectionStatus.fromWire(message.payload["terminalStatus"] as? String) ?? .succeeded
      let text = (message.payload["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
      let failure = AgentRuntimeFailure.parse(from: message.payload["failure"])
      update(
        surface: surface,
        status: terminalStatus,
        statusText: text?.isEmpty == false ? text : nil,
        errorMessage: failure?.displayMessage,
        failure: failure,
        terminal: true,
        payload: message.payload
      )
    case .error:
      let failure = AgentRuntimeFailure.parse(from: message.payload["failure"])
      update(
        surface: surface,
        status: .failed,
        statusText: nil,
        errorMessage: failure?.displayMessage ?? message.payload["message"] as? String,
        failure: failure,
        terminal: true,
        payload: message.payload
      )
    case .initMessage, .toolUse, .authRequired, .authSuccess, .controlToolResult, .unknown:
      break
    }
  }

  func taskProjections(limit: Int = 20) -> [AgentRunProjection] {
    projectionsBySurface.values
      .filter { $0.surface.surfaceKind == "task_chat" }
      .sorted { $0.updatedAt > $1.updatedAt }
      .prefix(limit)
      .map { $0 }
  }

  func floatingPillProjection(pillId: UUID) -> AgentRunProjection? {
    projection(for: .floatingPill(pillId: pillId))
  }

  private func update(
    surface: AgentSurfaceReference,
    status: AgentRunProjectionStatus,
    statusText: String?,
    errorMessage: String? = nil,
    failure: AgentRuntimeFailure? = nil,
    terminal: Bool,
    payload: [String: Any] = [:]
  ) {
    if !terminal, projectionsBySurface[surface.key]?.status.isTerminal == true {
      return
    }

    var projection = projectionsBySurface[surface.key] ?? AgentRunProjection(
      surface: surface,
      sessionId: nil,
      runId: nil,
      attemptId: nil,
      adapterSessionId: nil,
      status: .idle,
      statusText: nil,
      errorMessage: nil,
      failure: nil,
      updatedAt: Date(),
      completedAt: nil,
      costUsd: nil,
      inputTokens: nil,
      outputTokens: nil
    )

    projection.sessionId = (payload["sessionId"] as? String) ?? projection.sessionId
    projection.runId = (payload["runId"] as? String) ?? projection.runId
    projection.attemptId = (payload["attemptId"] as? String) ?? projection.attemptId
    projection.adapterSessionId =
      (payload["adapterSessionId"] as? String)
      ?? (payload["legacyAdapterSessionId"] as? String)
      ?? projection.adapterSessionId
    projection.status = status
    projection.statusText = statusText
    projection.failure = failure ?? (terminal || status.isActive ? nil : projection.failure)
    projection.errorMessage = projection.failure?.displayMessage ?? errorMessage ?? (terminal || status.isActive ? nil : projection.errorMessage)
    projection.updatedAt = Date()
    projection.completedAt = terminal ? projection.updatedAt : nil
    projection.costUsd = (payload["costUsd"] as? Double) ?? projection.costUsd
    projection.inputTokens = (payload["inputTokens"] as? Int) ?? projection.inputTokens
    projection.outputTokens = (payload["outputTokens"] as? Int) ?? projection.outputTokens

    projectionsBySurface[surface.key] = projection
    if let sessionId = projection.sessionId {
      sessionIdBySurface[surface.key] = sessionId
      projectionBySessionId[sessionId] = projection
    }
    if let runId = projection.runId {
      runIdBySurface[surface.key] = runId
      projectionByRunId[runId] = projection
    }
  }

  private func clearTerminalProjectionForNewRun(surface: AgentSurfaceReference) {
    guard let existing = projectionsBySurface[surface.key], existing.status.isTerminal else { return }
    projectionsBySurface.removeValue(forKey: surface.key)
    if let runId = existing.runId {
      projectionByRunId.removeValue(forKey: runId)
      if runIdBySurface[surface.key] == runId {
        runIdBySurface.removeValue(forKey: surface.key)
      }
    }
    if let sessionId = existing.sessionId {
      projectionBySessionId.removeValue(forKey: sessionId)
    }
  }
}
