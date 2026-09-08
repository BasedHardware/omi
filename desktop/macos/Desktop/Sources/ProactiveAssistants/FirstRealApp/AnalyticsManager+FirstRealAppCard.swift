import Foundation

/// Telemetry surface for the one-time first-real-app tap-to-ask card.
///
/// The funnel this feature is judged on is one event with a phase: how many
/// installs saw the card, how many acted on it, and by which route. Splitting
/// that across several event names would make the conversion a join.
///
/// Bounded dimensions only. The card's copy names the frontmost application,
/// and that name — like every notification title and window title — never
/// leaves the machine. There is no allow-listed application-category dimension
/// on this event, so none is sent; the phase alone answers the product
/// question.
enum FirstRealAppCardTelemetry {
  static let eventName = "first_real_app_card"

  /// Where one card's life ended (or began). Closed set: `shown` is emitted at
  /// delivery, and at most one terminal phase follows it.
  enum Phase: String, Equatable, CaseIterable {
    case shown
    case tapped
    /// The user held push-to-talk while the card was up — the outcome the copy
    /// is actually asking for.
    case pttAfterCard = "ptt_after_card"
    /// Closed with ✕, or replaced before it was acted on.
    case dismissed
    case timedOut = "timed_out"
  }

  static func payload(phase: Phase) -> [String: Any] {
    ["phase": phase.rawValue]
  }

  /// The allow-list this event may never grow past without a deliberate review.
  /// Asserted by the boundary test, so a future emitter cannot quietly attach
  /// an app name or a card title.
  static let allowedKeys: Set<String> = ["phase"]

  /// Test seam: nil in production. Scoped by the test that installs it, exactly
  /// like `AnalyticsManager.setNotificationDeliveryTelemetryCaptureForTests` —
  /// it lives here rather than in `AnalyticsManager` so this feature's telemetry
  /// is entirely contained in its own file.
  @MainActor static var captureForTests: ((String, [String: Any]) -> Void)?
}

extension AnalyticsManager {
  /// One event, one bounded phase. See `FirstRealAppCardTelemetry`.
  func firstRealAppCard(phase: FirstRealAppCardTelemetry.Phase) {
    let properties = FirstRealAppCardTelemetry.payload(phase: phase)
    FirstRealAppCardTelemetry.captureForTests?(FirstRealAppCardTelemetry.eventName, properties)
    PostHogManager.shared.track(FirstRealAppCardTelemetry.eventName, properties: properties)
  }
}
