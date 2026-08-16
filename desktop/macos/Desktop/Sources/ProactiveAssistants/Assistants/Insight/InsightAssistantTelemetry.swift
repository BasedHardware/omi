import Foundation

/// Closed, privacy-safe telemetry for the Advice assistant's generated-to-delivery funnel.
///
/// The delivery ID is intentionally opaque and per-advice. No advice text, app/window name,
/// screenshot, or error string is accepted by these payload builders.
enum InsightAssistantTelemetry {
  static let deliveryOutcomeEventName = "Advice Delivery Outcome"

  enum Outcome: String, CaseIterable, Sendable {
    case delivered
    case suppressed
    case failed
  }

  enum Reason: String, CaseIterable, Sendable {
    case assistantNotificationsDisabled = "assistant_notifications_disabled"
    case masterNotificationsDisabled = "master_notifications_disabled"
    case frequencyOff = "frequency_off"
    case frequencyThrottled = "frequency_throttled"
    case floatingBarPresented = "floating_bar_presented"
    case floatingBarUnavailable = "floating_bar_unavailable"
    case queueCancelled = "queue_cancelled"
    case queueOverflow = "queue_overflow"
    case noDeliverySurface = "no_delivery_surface"
    case systemAuthorizationDenied = "system_authorization_denied"
    case systemBannerDelivered = "system_banner_delivered"
    case systemDeliveryFailed = "system_delivery_failed"
    case staleOwner = "stale_owner"
  }

  enum Surface: String, CaseIterable, Sendable {
    case floatingBar = "floating_bar"
    case systemNotification = "system_notification"
  }

  struct DeliveryIdentity: Equatable, Sendable {
    let deliveryID: UUID

    init(deliveryID: UUID = UUID()) {
      self.deliveryID = deliveryID
    }
  }

  static func deliveryOutcomePayload(
    _ outcome: Outcome,
    reason: Reason,
    identity: DeliveryIdentity,
    surface: Surface? = nil
  ) -> [String: Any] {
    var payload: [String: Any] = [
      "assistant_id": "insight",
      "delivery_id": identity.deliveryID.uuidString,
      "outcome": outcome.rawValue,
      "reason": reason.rawValue,
    ]
    if outcome == .delivered, let surface {
      payload["notification_surface"] = surface.rawValue
    }
    return payload
  }

  /// Advice categories are model output, so map them to a finite contract before analytics.
  static func boundedCategory(_ category: String?) -> String? {
    guard let category else { return nil }
    switch category {
    case "productivity", "communication", "learning", "other", "health":
      return category
    default:
      return "other"
    }
  }
}
