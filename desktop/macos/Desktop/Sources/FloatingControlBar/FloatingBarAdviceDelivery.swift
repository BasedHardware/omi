import Foundation

/// Advice delivery bookkeeping shared by the floating-bar queue and presentation paths.
///
/// Keeping this policy in a small extension leaves the window/coordinator source focused on
/// presentation while preserving the exact-once terminal outcome and owner-fenced queue rules.
extension FloatingControlBarManager {
  private static let maxPendingAdviceNotifications = 20

  @discardableResult
  static func appendAdviceNotification(
    _ notification: FloatingBarNotification,
    to queue: inout [FloatingBarNotification]
  ) -> FloatingBarNotification? {
    var evicted: FloatingBarNotification?
    if queue.count >= Self.maxPendingAdviceNotifications {
      let removed = queue.removeFirst()
      evicted = removed
    }
    queue.append(notification)
    return evicted
  }

  static func dequeueCurrentOwnerAdviceNotification(
    from queue: inout [FloatingBarNotification],
    currentOwnerID: String?
  ) -> FloatingBarNotification? {
    while !queue.isEmpty {
      let nextNotification = queue.removeFirst()
      guard let currentOwnerID, nextNotification.ownerID == currentOwnerID else {
        log("FloatingControlBarManager: dropping queued notification from stale runtime owner")
        continue
      }
      return nextNotification
    }
    return nil
  }

}
