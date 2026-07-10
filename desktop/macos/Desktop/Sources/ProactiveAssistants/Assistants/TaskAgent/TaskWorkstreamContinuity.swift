import Foundation

struct TaskKernelArtifactVersion: Decodable {
  struct Artifact: Decodable {
    let artifactId: String
    let kind: String
    let uri: String
    let contentHash: String?
  }

  let sourceArtifactId: String?
  let logicalKey: String
  let version: Int
  let supersedesArtifactId: String?
  let evidenceRefs: [OmiAPI.EvidenceRef]
  let artifact: Artifact
}

struct TaskKernelCheckpoint: Decodable {
  let checkpointId: String
  let sourceRuntimeId: String
  let canonicalSummary: String
  let evidenceRefs: [OmiAPI.EvidenceRef]
  let lastEventSequence: Int
}

struct TaskKernelContinuityReceipt: Decodable {
  let artifactVersions: [TaskKernelArtifactVersion]
  let checkpoint: TaskKernelCheckpoint
  let deliveries: [TaskKernelDelivery]
}

struct TaskKernelPrepareReceipt: Decodable {
  let deliveries: [TaskKernelDelivery]
}

struct TaskKernelPreparedArtifactReceipt: Decodable {
  let artifactVersion: TaskKernelArtifactVersion
  let deliveries: [TaskKernelDelivery]
}

struct TaskKernelContinuityProjection: Decodable {
  let agentSessionId: String?
  let artifactVersions: [TaskKernelArtifactVersion]
  let checkpoint: TaskKernelCheckpoint?
}

struct TaskKernelDelivery: Decodable, Identifiable {
  struct Payload: Decodable {
    let kind: String
    let sourceArtifactId: String?
    let logicalKey: String?
    let artifactKind: String?
    let uri: String?
    let contentHash: String?
    let sourceRunId: String?
    let evidenceRefs: [OmiAPI.EvidenceRef]?
    let checkpoint: TaskKernelCheckpoint?
  }

  var id: String { deliveryId }
  let deliveryId: String
  let artifactId: String
  let status: String
  let attemptCount: Int
  let payload: Payload
}

@MainActor
enum TaskWorkstreamContinuity {
  typealias Control = @MainActor (String, [String: Any]) async throws -> String
  private struct PrepareResponse: Decodable {
    struct Session: Decodable { let agentSessionId: String }
    struct Run: Decodable {
      let runId: String
      let status: String
      let statusText: String?
      let errorMessage: String?
      let updatedAtMs: Int
      let completedAtMs: Int?
    }
    let ok: Bool
    let session: Session
    let run: Run?
    let deliveries: [TaskKernelDelivery]
  }
  private struct PersistResponse: Decodable {
    let ok: Bool
    let artifactVersions: [TaskKernelArtifactVersion]
    let checkpoint: TaskKernelCheckpoint
    let deliveries: [TaskKernelDelivery]
  }

  static func prepare(
    workstreamId: String,
    taskIds: [String],
    checkpoints: [OmiAPI.ContinuationCheckpoint],
    control: Control = { name, input in
      try await TaskChatRuntime.controlTool(name: name, input: input)
    }
  ) async throws -> TaskKernelPrepareReceipt {
    var input: [String: Any] = [
      "workstreamId": workstreamId,
      "taskIds": Array(Set(taskIds)).sorted(),
    ]
    if let checkpoint = checkpoints.max(by: { $0.lastEventSequence < $1.lastEventSequence }) {
      input["checkpoint"] = [
        "checkpointId": checkpoint.checkpointId,
        "runtimeId": checkpoint.runtimeId,
        "lastEventSequence": checkpoint.lastEventSequence,
        "contextSummary": checkpoint.contextSummary,
        "evidenceRefs": try jsonArray(checkpoint.evidenceRefs ?? []),
        "updatedAtMs": epochMilliseconds(checkpoint.updatedAt),
      ]
    }
    let raw = try await control("prepare_workstream_continuity", input)
    guard let data = raw.data(using: .utf8) else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    let response = try JSONDecoder().decode(PrepareResponse.self, from: data)
    guard response.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    if let run = response.run,
      let status = AgentRunProjectionStatus.fromWire(run.status)
    {
      AgentRuntimeStatusStore.shared.restoreKernelProjection(
        surface: .workstream(workstreamId: workstreamId),
        sessionId: response.session.agentSessionId,
        runId: run.runId,
        status: status,
        statusText: run.statusText,
        errorMessage: run.errorMessage,
        updatedAt: Date(timeIntervalSince1970: Double(run.updatedAtMs) / 1_000),
        completedAt: run.completedAtMs.map { Date(timeIntervalSince1970: Double($0) / 1_000) }
      )
    }
    return TaskKernelPrepareReceipt(deliveries: response.deliveries)
  }

  static func persist(
    workstream: TaskThreadProjection,
    queryResult: AgentBridge.QueryResult,
    chatMessageId: String,
    control: Control = { name, input in
      try await TaskChatRuntime.controlTool(name: name, input: input)
    }
  ) async throws -> TaskKernelContinuityReceipt {
    let artifacts = (queryResult.completionDeltaArtifacts.isEmpty
      ? queryResult.artifacts
      : queryResult.completionDeltaArtifacts)
      .filter(\.isUserFacingResult)

    let evidenceRefs = continuityEvidence(
      projection: workstream,
      chatMessageId: chatMessageId
    )
    let encodedEvidence = try jsonArray(evidenceRefs)
    let artifactInputs: [[String: Any]] = artifacts.map { artifact in
      var input: [String: Any] = [
        "logicalKey": logicalKey(for: artifact),
        "evidenceRefs": encodedEvidence,
        "kind": artifact.kind,
        "role": artifact.role,
        "uri": artifact.uri,
        "sourceArtifactId": artifact.artifactId,
      ]
      if let value = artifact.displayName { input["displayName"] = value }
      if let value = artifact.mimeType { input["mimeType"] = value }
      if let value = artifact.contentHash { input["contentHash"] = value }
      if let value = artifact.sizeBytes { input["sizeBytes"] = value }
      if let value = artifact.runId { input["runId"] = value }
      if let value = artifact.attemptId { input["attemptId"] = value }
      return input
    }
    let input: [String: Any] = [
      "workstreamId": workstream.workstreamID,
      "context": try kernelContext(projection: workstream),
      "artifacts": artifactInputs,
    ]
    let raw = try await control("persist_workstream_continuity", input)
    guard let data = raw.data(using: .utf8) else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    let response = try JSONDecoder().decode(PersistResponse.self, from: data)
    guard response.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    return TaskKernelContinuityReceipt(
      artifactVersions: response.artifactVersions,
      checkpoint: response.checkpoint,
      deliveries: response.deliveries
    )
  }

  /// Persists a policy-approved proactive payload through the same kernel
  /// session, version, checkpoint, and delivery authority as agent output.
  static func persistPreparedArtifact(
    workstreamId: String,
    logicalKey: String,
    kind: String,
    fileURL: URL,
    contentHash: String,
    evidenceRefs: [OmiAPI.EvidenceRef],
    grantId: String,
    control: Control = { name, input in
      try await TaskChatRuntime.controlTool(name: name, input: input)
    }
  ) async throws -> TaskKernelPreparedArtifactReceipt {
    guard !evidenceRefs.isEmpty else { throw TaskWorkstreamContinuityError.missingRevisionEvidence }
    let input: [String: Any] = [
      "workstreamId": workstreamId,
      "logicalKey": logicalKey,
      "evidenceRefs": try jsonArray(evidenceRefs),
      "kind": kind,
      "uri": fileURL.absoluteString,
      "contentHash": contentHash,
      "sourceArtifactId": "proactive-prepared:\(contentHash)",
      "grantId": grantId,
    ]
    let raw = try await control("persist_prepared_workstream_artifact", input)
    guard let data = raw.data(using: .utf8) else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    struct Response: Decodable {
      let ok: Bool
      let artifactVersion: TaskKernelArtifactVersion
      let deliveries: [TaskKernelDelivery]
    }
    let response = try JSONDecoder().decode(Response.self, from: data)
    guard response.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    return TaskKernelPreparedArtifactReceipt(
      artifactVersion: response.artifactVersion,
      deliveries: response.deliveries
    )
  }

  static func resolveDelivery(
    id: String,
    delivered: Bool,
    receipt: [String: Any]? = nil,
    error: Error? = nil,
    control: Control = { name, input in
      try await TaskChatRuntime.controlTool(name: name, input: input)
    }
  ) async throws {
    var input: [String: Any] = [
      "deliveryId": id,
      "status": delivered ? "delivered" : "failed",
    ]
    if let receipt { input["receipt"] = receipt }
    if let error {
      input["error"] = [
        "type": String(describing: type(of: error)),
        "message": error.localizedDescription,
      ]
    }
    _ = try await control("resolve_workstream_continuity_delivery", input)
  }

  static func project(
    workstreamId: String,
    control: Control = { name, input in
      try await TaskChatRuntime.controlTool(name: name, input: input)
    }
  ) async throws -> TaskKernelContinuityProjection {
    struct Response: Decodable {
      let ok: Bool
      let projection: TaskKernelContinuityProjection
    }
    let raw = try await control("project_workstream_continuity", ["workstreamId": workstreamId])
    guard let data = raw.data(using: .utf8) else {
      throw TaskWorkstreamContinuityError.invalidRuntimeResponse
    }
    let response = try JSONDecoder().decode(Response.self, from: data)
    guard response.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    return response.projection
  }

  static func continuityEvidence(
    projection: TaskThreadProjection,
    chatMessageId: String
  ) -> [OmiAPI.EvidenceRef] {
    let canonical = projection.recentEvents
      .filter { $0.sensitivity == .normal }
      .flatMap { $0.evidenceRefs ?? [] }
    let task = projection.scopedTasks
      .first(where: { $0.id == projection.activeTaskID })?
      .provenance ?? []
    let localTurn = OmiAPI.EvidenceRef(
      deviceId: ClientDeviceService.shared.clientDeviceId,
      excerptHash: nil,
      id: chatMessageId,
      kind: .chat_message,
      scope: .device_local,
      version: "task-thread.v1"
    )
    var seen = Set<String>()
    return (canonical + task + [localTurn]).filter {
      seen.insert("\($0.kind.rawValue)|\($0.id)|\($0.scope.rawValue)").inserted
    }.prefix(20).map { $0 }
  }

  static func logicalKey(for artifact: AgentArtifactProjection) -> String {
    if let metadataKey = artifact.metadataRows
      .first(where: { $0.hasPrefix("logicalKey: ") })?
      .dropFirst("logicalKey: ".count),
      !metadataKey.isEmpty
    {
      return sanitizeLogicalKey(String(metadataKey))
    }
    let candidate = artifact.displayName?.isEmpty == false
      ? artifact.displayName!
      : URL(string: artifact.uri)?.lastPathComponent ?? artifact.kind
    return sanitizeLogicalKey(candidate)
  }

  private static func sanitizeLogicalKey(_ value: String) -> String {
    let mapped = value.lowercased().map { character -> Character in
      character.isLetter || character.isNumber ? character : "-"
    }
    let collapsed = String(mapped).replacingOccurrences(of: "-+", with: "-", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return String((collapsed.isEmpty ? "artifact" : collapsed).prefix(256))
  }

  private static func kernelContext(projection: TaskThreadProjection) throws -> [String: Any] {
    let currentTask = projection.scopedTasks.first(where: { $0.id == projection.activeTaskID })
    let events = try projection.recentEvents.filter { $0.sensitivity == .normal }.map { event -> [String: Any] in
      [
        "eventId": event.eventId,
        "type": event.kind.rawValue,
        "summary": event.summary,
        "occurredAtMs": epochMilliseconds(event.createdAt),
        "evidenceRefs": try jsonArray(event.evidenceRefs ?? []),
        "sensitivityTier": "low",
      ]
    }
    let heads = try projection.artifactHeads.map { artifact -> [String: Any] in
      [
        "logicalKey": artifact.logicalKey,
        "artifactId": artifact.artifactId,
        "version": artifact.version,
        "contentHash": artifact.contentHash,
        "evidenceRefs": try jsonArray(artifact.evidenceRefs ?? []),
        "sensitivityTier": "low",
      ]
    }
    var context: [String: Any] = [
      "canonicalSummary": projection.currentSummary,
      "redactedCanonicalSummary": projection.currentSummary,
      "summarySensitivityTier": "private",
      "latestEventSequence": projection.detail.workstream.latestEventSequence ?? 0,
      "selectedEvents": events,
      "artifactHeads": heads,
      "provenance": [
        "snapshotVersion": "workstream:\(projection.detail.workstream.latestEventSequence ?? 0)",
        "fetchedAtMs": Int(Date().timeIntervalSince1970 * 1_000),
        "source": "canonical_backend",
      ],
    ]
    if let currentTask {
      context["currentTask"] = [
        "taskId": currentTask.id,
        "title": currentTask.description_,
        "status": (currentTask.status ?? (currentTask.completed ? .completed : .active)).rawValue,
      ]
    }
    return context
  }

  private static func jsonArray<T: Encodable>(_ values: [T]) throws -> [[String: Any]] {
    let data = try JSONEncoder().encode(values)
    return try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
  }

  private static func epochMilliseconds(_ iso8601: String) -> Int {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let date = formatter.date(from: iso8601) ?? ISO8601DateFormatter().date(from: iso8601) ?? Date()
    return Int(date.timeIntervalSince1970 * 1_000)
  }
}

enum TaskWorkstreamContinuityError: LocalizedError {
  case invalidRuntimeResponse
  case missingRevisionEvidence
  case missingRestartProjection

  var errorDescription: String? {
    switch self {
    case .invalidRuntimeResponse:
      "The task thread runtime returned an invalid continuity receipt."
    case .missingRevisionEvidence:
      "Artifact revisions wait until the material workstream evidence is canonical."
    case .missingRestartProjection:
      "The prior task thread is not present in the restarted kernel."
    }
  }
}
