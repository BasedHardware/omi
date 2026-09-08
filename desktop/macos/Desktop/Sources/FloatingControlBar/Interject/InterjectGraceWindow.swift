import Foundation

/// ~10s post-dismiss window where hover on the pill or PTT-start re-shows
/// the last card. The card payload lives with the manager; this type only
/// owns the arm/consume/expiry machine.
struct InterjectGraceWindow: Equatable, Sendable {
  static let duration: TimeInterval = 10

  private(set) var expiresAt: Date?

  var isArmed: Bool { expiresAt != nil }

  mutating func arm(now: Date, duration: TimeInterval = Self.duration) {
    expiresAt = now.addingTimeInterval(duration)
  }

  mutating func clear() {
    expiresAt = nil
  }

  func isActive(at now: Date) -> Bool {
    guard let expiresAt else { return false }
    return now < expiresAt
  }

  /// Hover or PTT-start. Returns true once; later calls see a cleared window.
  mutating func consume(at now: Date) -> Bool {
    guard isActive(at: now) else {
      if let expiresAt, now >= expiresAt {
        self.expiresAt = nil
      }
      return false
    }
    expiresAt = nil
    return true
  }

  mutating func expireIfNeeded(at now: Date) {
    guard let expiresAt, now >= expiresAt else { return }
    self.expiresAt = nil
  }
}
