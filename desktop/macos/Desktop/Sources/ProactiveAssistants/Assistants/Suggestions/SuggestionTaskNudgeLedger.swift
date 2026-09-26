import Foundation

struct SuggestionCommitment: Sendable, Equatable {
  let id: String
  let text: String
}

struct SuggestionTaskNudgeRecord: Codable, Equatable, Sendable {
  var lastNudgedAt: Date?
  var nudgeCount: Int
  var suppressedUntil: Date?
}

struct SuggestionTaskNudgeLedger: Codable, Equatable, Sendable {
  var records: [String: SuggestionTaskNudgeRecord] = [:]
}

protocol SuggestionTaskNudgeLedgerPersisting: AnyObject {
  func load() -> SuggestionTaskNudgeLedger
  func save(_ ledger: SuggestionTaskNudgeLedger)
}

final class SuggestionTaskNudgeLedgerDefaults: SuggestionTaskNudgeLedgerPersisting {
  private let defaults: UserDefaults
  private let fixedOwnerID: String?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
  }

  private var key: ScopedDefaultsKey {
    let dynamicOwner =
      defaults === UserDefaults.standard
      ? RuntimeOwnerIdentity.currentOwnerId()
      : defaults.string(forKey: .authUserId)
    let owner = fixedOwnerID ?? dynamicOwner ?? "signed-out"
    return .suggestionTaskNudgeLedger(ownerID: owner)
  }

  func load() -> SuggestionTaskNudgeLedger {
    guard let data = defaults.data(forKey: key) else { return SuggestionTaskNudgeLedger() }
    return (try? JSONDecoder().decode(SuggestionTaskNudgeLedger.self, from: data))
      ?? SuggestionTaskNudgeLedger()
  }

  func save(_ ledger: SuggestionTaskNudgeLedger) {
    defaults.set(try? JSONEncoder().encode(ledger), forKey: key)
  }
}

enum SuggestionTaskNudgePolicy {
  static let freshnessLookback: TimeInterval = 2 * 24 * 60 * 60
  static let engagementSuppression: TimeInterval = 7 * 24 * 60 * 60
  static let backoff: [TimeInterval] = [4 * 60 * 60, 24 * 60 * 60, 72 * 60 * 60]

  static func isDueFresh(_ dueAt: Date?, now: Date, calendar: Calendar = .current) -> Bool {
    guard let dueAt else { return false }
    let start = now.addingTimeInterval(-freshnessLookback)
    let endOfToday = calendar.date(bySettingHour: 23, minute: 59, second: 59, of: now) ?? now
    return dueAt >= start && dueAt <= endOfToday
  }

  static func isEligible(taskId: String, dueAt: Date?, ledger: SuggestionTaskNudgeLedger, now: Date)
    -> Bool
  {
    guard isDueFresh(dueAt, now: now) else { return false }
    let suppressedUntil = ledger.records[taskId]?.suppressedUntil ?? .distantPast
    return suppressedUntil <= now
  }

  static func recordingDelivery(taskId: String, in ledger: inout SuggestionTaskNudgeLedger, now: Date) {
    var record = ledger.records[taskId] ?? SuggestionTaskNudgeRecord(lastNudgedAt: nil, nudgeCount: 0)
    record.nudgeCount += 1
    record.lastNudgedAt = now
    if record.nudgeCount >= 3 {
      record.suppressedUntil = .distantFuture
    } else {
      let delay = backoff[min(record.nudgeCount, backoff.count) - 1]
      record.suppressedUntil = now.addingTimeInterval(delay)
    }
    ledger.records[taskId] = record
  }

  static func recordingEngagement(taskId: String, in ledger: inout SuggestionTaskNudgeLedger, now: Date) {
    var record = ledger.records[taskId] ?? SuggestionTaskNudgeRecord(lastNudgedAt: nil, nudgeCount: 0)
    record.suppressedUntil = now.addingTimeInterval(engagementSuppression)
    ledger.records[taskId] = record
  }

  static func clearing(taskId: String, in ledger: inout SuggestionTaskNudgeLedger) {
    ledger.records.removeValue(forKey: taskId)
  }

  static func taskId(fromNotificationDetail detail: String?) -> String? {
    guard let detail else { return nil }
    guard detail.hasPrefix("task_id=") else { return nil }
    let rest = detail.dropFirst("task_id=".count)
    let value: Substring
    if let newline = rest.firstIndex(of: "\n") {
      value = rest[..<newline]
    } else {
      value = rest
    }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}

/// Engagement (thumbs-down, dismiss, reply) suppresses the named task for 7 days.
enum SuggestionTaskNudgeEngagement {
  @MainActor
  static func record(
    taskId: String?, persisting: SuggestionTaskNudgeLedgerPersisting = SuggestionTaskNudgeLedgerDefaults(),
    now: Date = Date()
  ) {
    guard NegativeFeedbackRemediationFeature.isEnabled, let taskId, !taskId.isEmpty else { return }
    var ledger = persisting.load()
    SuggestionTaskNudgePolicy.recordingEngagement(taskId: taskId, in: &ledger, now: now)
    persisting.save(ledger)
  }

  @MainActor
  static func record(from notification: FloatingBarNotification) {
    record(taskId: SuggestionTaskNudgePolicy.taskId(fromNotificationDetail: notification.context?.detail))
  }

  @MainActor
  static func record(fromContinuityKey key: String?) {
    record(
      taskId: SuggestionTaskNudgePolicy.taskId(
        fromNotificationDetail: FloatingControlBarManager.shared.notificationDetail(
          forContinuityKey: key)))
  }
}
