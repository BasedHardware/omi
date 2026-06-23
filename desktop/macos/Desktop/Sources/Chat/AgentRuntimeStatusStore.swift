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

  static func floatingPill(pillId: UUID) -> AgentSurfaceReference {
    AgentSurfaceReference(surfaceKind: "floating_pill", externalRefKind: "pill", externalRefId: pillId.uuidString)
  }
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

  func beginRequest(surface: AgentSurfaceReference, statusText: String? = "Starting...") {
    update(surface: surface, status: .starting, statusText: statusText, terminal: false)
  }

  func updateActivity(surface: AgentSurfaceReference, statusText: String?) {
    update(surface: surface, status: .running, statusText: statusText, terminal: false)
  }

  func recordLocalFailure(surface: AgentSurfaceReference, error: String) {
    update(surface: surface, status: .failed, statusText: nil, errorMessage: error, terminal: true)
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
    case .cancelAck:
      let accepted = message.payload["accepted"] as? Bool ?? false
      update(surface: surface, status: accepted ? .cancelling : .running, statusText: nil, terminal: false, payload: message.payload)
    case .result:
      let terminalStatus = AgentRunProjectionStatus.fromWire(message.payload["terminalStatus"] as? String) ?? .succeeded
      update(surface: surface, status: terminalStatus, statusText: nil, terminal: true, payload: message.payload)
    case .error:
      update(
        surface: surface,
        status: .failed,
        statusText: nil,
        errorMessage: message.payload["message"] as? String,
        terminal: true,
        payload: message.payload
      )
    case .initMessage, .toolUse, .toolResultDisplay, .authRequired, .authSuccess, .unknown:
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
    terminal: Bool,
    payload: [String: Any] = [:]
  ) {
    var projection = projectionsBySurface[surface.key] ?? AgentRunProjection(
      surface: surface,
      sessionId: nil,
      runId: nil,
      attemptId: nil,
      adapterSessionId: nil,
      status: .idle,
      statusText: nil,
      errorMessage: nil,
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
    if let statusText {
      projection.statusText = statusText
    } else if terminal {
      projection.statusText = nil
    }
    projection.errorMessage = errorMessage ?? (terminal ? nil : projection.errorMessage)
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
}
