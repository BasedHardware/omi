import Foundation

/// Telemetry for the daily summary card in Chat.
///
/// Phases only. The summary's headline, overview, highlights, and action items are the user's own
/// day; none of it goes to PostHog (desktop `AGENTS.md` → product analytics integrity). What we
/// need to know is whether the card is seen, opened, and acted on — five bounded values answer
/// that.
enum DailySummaryTelemetryPhase: String {
  /// The card rendered at the top of the thread.
  case shown
  /// The reader opened "More".
  case expanded
  /// The reader tapped the follow-up chip (which prefills the composer and sends nothing).
  case followUpTapped = "follow_up_tapped"
  /// A notch card was posted for a summary the reader had not seen.
  case cardShown = "card_shown"
  /// That notch card was opened.
  case cardTapped = "card_tapped"
}

extension AnalyticsManager {
  static let dailySummaryEvent = "desktop_daily_summary"

  func trackDailySummary(_ phase: DailySummaryTelemetryPhase) {
    PostHogManager.shared.track(Self.dailySummaryEvent, properties: ["phase": phase.rawValue])
  }
}
