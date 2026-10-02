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
