import Foundation

/// One-shot handoff from the Home filmstrip to the Rewind page: Home stores
/// the tapped frame's timestamp, navigates, and Rewind consumes the request
/// after its screenshots load, seeking to the nearest frame.
@MainActor
final class RewindSeekRequestStore {
  static let shared = RewindSeekRequestStore()

  private(set) var pendingDate: Date?

  func request(_ date: Date) {
    pendingDate = date
  }

  func consume() -> Date? {
    defer { pendingDate = nil }
    return pendingDate
  }
}
