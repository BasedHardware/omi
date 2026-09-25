import Foundation
@preconcurrency import UserNotifications

/// Closed, privacy-safe telemetry contract for a proactive notification that
/// `NotificationService` dropped because the app was not authorized to show it.
///
/// `UNUserNotificationCenter.add(request:)` does not surface an error when
/// authorization is `.notDetermined` or `.denied` — it silently no-ops. That
/// silence was the whole bug: 49 macOS users sat at `notDetermined` (never
/// asked, and — before the onboarding step this file ships alongside — never
/// asked again) while every proactive notification the app tried to send them
/// failed with nothing anywhere to say so. This event exists to make that drop
/// observable, not to fix delivery — the caller does not request permission and
/// does not change whether `add(request:)` still runs.
///
/// Mirrors the `IntegrationConnectTelemetry` / `IntegrationNudgeTelemetry`
/// contract style: a closed schema, an allow-list filter, bounded enum values
/// only. `surface` reuses `ProactiveNotificationKind.from(assistantId:)` — the
/// same closed classification INV-6 chat continuity already derives from
/// `assistantId` — rather than inventing a second taxonomy for the same string.
enum NotificationDeliveryTelemetry {
  /// PostHog event name. Stable identifier — do not rename.
  static let skippedEventName = "Notification Delivery Skipped"

  /// Closed projection of `UNAuthorizationStatus`. Never emit the raw
  /// `UNAuthorizationStatus` rawValue — this is the bounded string PostHog sees.
  enum AuthStatus: String, CaseIterable {
    case notDetermined = "not_determined"
    case denied
    case authorized
    case provisional
    case ephemeral
    case unknown

    init(_ status: UNAuthorizationStatus) {
      switch status {
      case .notDetermined: self = .notDetermined
      case .denied: self = .denied
      case .authorized: self = .authorized
      case .provisional: self = .provisional
      case .ephemeral: self = .ephemeral
      @unknown default: self = .unknown
      }
    }
  }

  /// Keys permitted in any emitted payload. Anything else is dropped by the
  /// allow-list filter, so a caller cannot accidentally thread notification
  /// title/body, an assistant id, a window title, or any other content through
  /// as an extra property.
  static let allowedKeys: Set<String> = ["auth_status", "surface"]

  /// `Notification Delivery Skipped` payload. `surface` is a
  /// `ProactiveNotificationKind` raw value (already a closed, bounded set) —
  /// never the free-text `assistantId` it was derived from.
  static func skippedPayload(authStatus: AuthStatus, surface: ProactiveNotificationKind) -> [String: Any] {
    allowListOnly([
      "auth_status": authStatus.rawValue,
      "surface": surface.rawValue,
    ])
  }

  private static func allowListOnly(_ properties: [String: Any]) -> [String: Any] {
    properties.filter { allowedKeys.contains($0.key) }
  }
}
