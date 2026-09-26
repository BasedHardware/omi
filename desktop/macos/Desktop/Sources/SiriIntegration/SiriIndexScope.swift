import Foundation

enum SiriIndexScope {
  static let conversationLimit = 2_000
  static let memoryLimit = 5_000
  static let conversationAge: TimeInterval = 180 * 24 * 60 * 60
  static let completedTaskAge: TimeInterval = 30 * 24 * 60 * 60

  static func conversation(_ record: TranscriptionSessionRecord, now: Date) -> Bool {
    record.backendSynced && record.backendId?.isEmpty == false && !record.deleted && !record.discarded
      && !record.isLocked && ["private", "shared", "public"].contains(record.visibility)
      && record.conversationStatus == .completed
      && record.startedAt > now.addingTimeInterval(-conversationAge)
  }

  static func memory(_ record: MemoryRecord, now: Date) -> Bool {
    let metadata = record.siriLedgerMetadata
    let status = metadata["status"]
    let supersededBy = metadata["superseded_by"]
    let invalidAt = metadata["invalid_at"]
    let validInvalidAt: Bool
    if let invalidAt, !invalidAt.isEmpty {
      validInvalidAt = parseLedgerDate(invalidAt).map { $0 > now } ?? false
    } else {
      validInvalidAt = true
    }
    return record.backendSynced && record.tierIsExplicit
      && memory(
        backendId: record.backendId, deleted: record.deleted, dismissed: record.isDismissed,
        tier: record.tier, expiresAt: record.expiresAt, userReview: record.userReview,
        visibility: record.visibility, unlocked: record.isLocked == false,
        ledgerActive: status == nil || status == "active",
        unsuperseded: supersededBy == nil || supersededBy?.isEmpty == true,
        uninvalidated: validInvalidAt, now: now)
  }

  static func parseLedgerDate(_ raw: String?) -> Date? {
    guard let raw, !raw.isEmpty else { return nil }
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let standard = ISO8601DateFormatter()
    return fractional.date(from: raw) ?? standard.date(from: raw)
  }

  static func memoryNextCutoff(expiresAt: Date?, invalidAt: String?) -> Date? {
    [expiresAt, parseLedgerDate(invalidAt)].compactMap { $0 }.min()
  }

  static func eligibleConversations(
    _ records: [TranscriptionSessionRecord], now: Date, limit: Int = conversationLimit
  ) -> [TranscriptionSessionRecord] {
    Array(records.lazy.filter { conversation($0, now: now) }.prefix(limit))
  }

  static func memory(
    backendId: String?, deleted: Bool, dismissed: Bool, tier: String, expiresAt: Date?,
    userReview: Bool? = nil, visibility: String = "private", unlocked: Bool = true,
    ledgerActive: Bool = true, unsuperseded: Bool = true, uninvalidated: Bool = true, now: Date
  ) -> Bool {
    backendId?.isEmpty == false && !deleted && !dismissed && userReview != false && unlocked
      && ["private", "shared", "public"].contains(visibility)
      && ledgerActive && unsuperseded && uninvalidated
      && (tier == MemoryLayer.shortTerm.rawValue || tier == MemoryLayer.longTerm.rawValue)
      && (expiresAt.map { $0 > now } ?? true)
  }

  static func task(
    backendId: String?, deleted: Bool, completed: Bool, completedAt: Date?,
    taskStatus: String? = nil, supersededBy: String? = nil, isLocked: Bool = false, now: Date
  ) -> Bool {
    backendId?.isEmpty == false && !deleted && !isLocked
      && (taskStatus == nil || taskStatus == "active" || taskStatus == "completed")
      && (supersededBy == nil || supersededBy?.isEmpty == true)
      && (!completed || completedAt.map { $0 > now.addingTimeInterval(-completedTaskAge) } == true)
  }

  static func task(_ record: ActionItemRecord, now: Date) -> Bool {
    record.backendSynced && record.isLocked == false
      && task(
        backendId: record.backendId, deleted: record.deleted, completed: record.completed,
        completedAt: record.completedAt, taskStatus: record.taskStatus,
        supersededBy: record.supersededBy, now: now)
  }

  static func nextCutoff(_ deadlines: [Date]) -> Date? { deadlines.min() }

  static func capped<T>(_ items: [T], at limit: Int) -> [T] {
    Array(items.prefix(limit))
  }
}

enum SiriMemoryExpirySweep {
  static func nextExpiry(_ indexed: [String: Date]) -> Date? { indexed.values.min() }

  @discardableResult
  static func deleteDue(
    _ indexed: [String: Date], now: Date,
    deletion: ([String]) async throws -> Void
  ) async throws -> [String] {
    let due = indexed.filter { $0.value <= now }.map(\.key).sorted()
    if !due.isEmpty { try await deletion(due) }
    return due
  }
}
