import Foundation

struct ScreenTaskExtraction: Sendable {
  let results: [TaskExtractionResult]
  let searchCount: Int
  var admission: ScreenTaskAdmission? = nil
  var extractor = "gemini_3_8"
}

struct ScreenTaskDeliveryCounts: Sendable {
  var policyRejected = 0
  var outboxSaved = 0
  var coalesced = 0
  var pendingDelivered = 0
  var failed = 0
  static let failure = Self(failed: 1)

  mutating func add(_ other: Self) {
    policyRejected += other.policyRejected
    outboxSaved += other.outboxSaved
    coalesced += other.coalesced
    pendingDelivered += other.pendingDelivered
    failed += other.failed
  }
}

struct ScreenTaskAuditEvent {
  let taskCount: Int
  let candidateCount: Int
  let extractor: String
  let gateOutcome = "rejected"
  let auditSample = true
}

enum ScreenTaskDelivery {
  /// A local outbox write, policy rejection or coalescence is not a delivered suggestion.
  static func deliver(
    _ extraction: ScreenTaskExtraction,
    isolation: isolated (any Actor)? = #isolation,
    stage: (TaskExtractionResult) async -> ScreenTaskDeliveryCounts,
    recordAudit: @MainActor (ScreenTaskAuditEvent) -> Void
  ) async -> ScreenTaskDeliveryCounts {
    var counts = ScreenTaskDeliveryCounts()
    for result in extraction.results { counts.add(await stage(result)) }
    if extraction.admission?.auditSample == true {
      await recordAudit(
        ScreenTaskAuditEvent(
          taskCount: counts.pendingDelivered, candidateCount: extraction.results.filter { $0.hasNewTask }.count,
          extractor: extraction.extractor))
    }
    return counts
  }
}

/// Persist only a closed vocabulary beside content-bearing outbox metadata.
struct ScreenTaskDeliveryProvenance: Equatable, Sendable {
  let extractor: String
  let gateOutcome: String
  let auditSample: Bool

  init(extractor: String, gateOutcome: String = "none", auditSample: Bool = false) {
    self.extractor = ["gemini_3_8", "legacy"].contains(extractor) ? extractor : "unknown"
    self.gateOutcome = ["passed", "rejected", "fail_open"].contains(gateOutcome) ? gateOutcome : "none"
    self.auditSample = auditSample && self.gateOutcome == "rejected"
  }
  init(extraction: ScreenTaskExtraction) {
    self.init(
      extractor: extraction.extractor, gateOutcome: extraction.admission?.gateOutcome ?? "none",
      auditSample: extraction.admission?.auditSample ?? false)
  }
  init(metadata: [String: Any]) {
    let stored = metadata["screen_task_delivery_provenance"] as? [String: Any] ?? [:]
    self.init(
      extractor: stored["extractor"] as? String ?? "unknown",
      gateOutcome: stored["gate_outcome"] as? String ?? "none",
      auditSample: stored["audit_sample"] as? Bool ?? false)
  }
  func store(in metadata: inout [String: Any]) {
    metadata["screen_task_delivery_provenance"] = [
      "extractor": extractor, "gate_outcome": gateOutcome, "audit_sample": auditSample,
    ]
  }
}

/// Returned only by the first committed receipt, never by coalesced/replayed receipts.
struct ScreenTaskDeliveryCompletion: Equatable, Sendable {
  let provenance: ScreenTaskDeliveryProvenance
  let status: String
  init(provenance: ScreenTaskDeliveryProvenance, status: String) {
    self.provenance = provenance
    self.status = ["pending", "accepted", "rejected", "expired"].contains(status) ? status : "unknown"
  }
  func properties(deferred: Bool) -> [String: Any] {
    [
      "schema_version": 1, "extractor": provenance.extractor, "gate_outcome": provenance.gateOutcome,
      "audit_sample": provenance.auditSample, "delivery_status": status,
      "pending_delivered": status == "pending" ? 1 : 0, "delivery_path": deferred ? "deferred" : "immediate",
    ]
  }
}

/// Common receipt producer for immediate delivery and outbox retries; offline tests use the same emitter path.
enum ScreenTaskReceiptDelivery {
  static func complete(
    id: Int64, candidateID: String, status: String, taskID: String?,
    ownerID: String, deferred: Bool, authorization: LocalMutationAuthorization = .unrestricted,
    emit: @MainActor (String, ScreenTaskDeliveryCompletion, Bool) -> Void = {
      PostHogManager.shared.screenTaskDeliveryCompleted(ownerID: $0, completion: $1, deferred: $2)
    }
  ) async throws -> ScreenTaskDeliveryCompletion? {
    let completion = try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id, candidateID: candidateID, status: status, taskID: taskID, authorization: authorization)
    if let completion { await emit(ownerID, completion, deferred) }
    return completion
  }
}
