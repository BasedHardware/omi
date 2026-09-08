import Foundation

/// Advice delivery bookkeeping shared by the floating-bar queue and presentation paths.
///
/// Keeping this policy in a small extension leaves the window/coordinator source focused on
/// presentation while preserving the exact-once terminal outcome and owner-fenced queue rules.
extension FloatingControlBarManager {
  private static let maxPendingAdviceNotifications = 20

  static func recordInsightDeliveryOutcome(
    for notification: FloatingBarNotification,
    outcome: InsightAssistantTelemetry.Outcome,
    reason: InsightAssistantTelemetry.Reason,
    surface: InsightAssistantTelemetry.Surface? = nil
  ) {
    guard let deliveryID = notification.insightDeliveryID else { return }
    AnalyticsManager.shared.insightAssistantDeliveryOutcome(
      outcome,
      reason: reason,
      deliveryID: deliveryID,
      surface: surface
    )
  }

  static func recordQueuedInsightOutcomes(
    _ notifications: [FloatingBarNotification],
    reason: InsightAssistantTelemetry.Reason
  ) {
    for notification in notifications {
      recordInsightDeliveryOutcome(for: notification, outcome: .suppressed, reason: reason)
    }
  }

  @discardableResult
  static func appendAdviceNotification(
    _ notification: FloatingBarNotification,
    to queue: inout [FloatingBarNotification]
  ) -> FloatingBarNotification? {
    var evicted: FloatingBarNotification?
    if queue.count >= Self.maxPendingAdviceNotifications {
      let removed = queue.removeFirst()
      evicted = removed
      recordQueuedInsightOutcomes([removed], reason: .queueOverflow)
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
        recordInsightDeliveryOutcome(for: nextNotification, outcome: .suppressed, reason: .staleOwner)
        continue
      }
      return nextNotification
    }
    return nil
  }

  static func recordAdvicePresentation(_ notification: FloatingBarNotification) {
    recordInsightDeliveryOutcome(
      for: notification,
      outcome: .delivered,
      reason: .floatingBarPresented,
      surface: .floatingBar
    )
  }
}
