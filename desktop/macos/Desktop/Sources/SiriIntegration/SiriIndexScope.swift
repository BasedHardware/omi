import Foundation

enum SiriIndexScope {
  static let conversationLimit = 2_000
  static let memoryLimit = 5_000
  static let conversationAge: TimeInterval = 180 * 24 * 60 * 60
  static let completedTaskAge: TimeInterval = 30 * 24 * 60 * 60

  static func conversation(_ record: TranscriptionSessionRecord, now: Date) -> Bool {
    record.backendSynced && record.backendId != nil && !record.deleted && !record.discarded
      && record.conversationStatus == .completed
      && record.startedAt >= now.addingTimeInterval(-conversationAge)
  }

  static func memory(
    backendId: String?, deleted: Bool, dismissed: Bool, expiresAt: Date?, now: Date
  ) -> Bool {
    backendId != nil && !deleted && !dismissed && (expiresAt.map { $0 > now } ?? true)
  }

  static func task(
    backendId: String?, deleted: Bool, completed: Bool, completedAt: Date?,
    taskStatus: String? = nil, now: Date
  ) -> Bool {
    backendId != nil && !deleted && taskStatus != "cancelled" && taskStatus != "superseded"
      && (!completed || completedAt.map { $0 >= now.addingTimeInterval(-completedTaskAge) } == true)
  }

  static func capped<T>(_ items: [T], at limit: Int) -> [T] {
    Array(items.prefix(limit))
  }
}
