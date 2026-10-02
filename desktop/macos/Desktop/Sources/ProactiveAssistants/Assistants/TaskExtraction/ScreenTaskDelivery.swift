import Foundation

struct ScreenTaskExtraction {
  let results: [TaskExtractionResult]
  let searchCount: Int
  var admission: ScreenTaskAdmission? = nil
}

struct ScreenTaskAuditEvent {
  let taskCount: Int
  let candidateCount: Int
  let gateOutcome = "rejected"
  let auditSample = true
}

enum ScreenTaskDelivery {
  /// Audit results use the same staging handler as admitted frames. Count only
  /// successful staging writes, including a zero-count event for empty audits.
  static func deliver(
    _ extraction: ScreenTaskExtraction,
    isolation: isolated (any Actor)? = #isolation,
    stage: (TaskExtractionResult) async -> Bool,
    recordAudit: @MainActor (ScreenTaskAuditEvent) -> Void
  ) async {
    var staged = 0
    for result in extraction.results {
      if await stage(result) { staged += 1 }
    }
    if extraction.admission?.auditSample == true {
      await recordAudit(
        ScreenTaskAuditEvent(taskCount: staged, candidateCount: extraction.results.filter { $0.hasNewTask }.count))
    }
  }
}
