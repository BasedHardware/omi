import Foundation

/// Telemetry for the daily summary card in Chat.
///
/// Phases only. The summary's headline, overview, highlights, and action items are the user's own
/// day; none of it goes to PostHog (desktop `AGENTS.md` → product analytics integrity). What we
/// need to know is whether the card is seen, opened, acted on, and cleared — six bounded values
/// answer that.
enum DailySummaryTelemetryPhase: String {
  /// The recap pill rendered at the top of the thread.
  case shown
  /// The reader opened the dedicated recap page (from the Chat pill or the Activity day).
  case expanded
  /// The reader tapped the follow-up chip (which prefills the composer and sends nothing).
  case followUpTapped = "follow_up_tapped"
  /// A notch card was posted for a summary the reader had not seen.
  case cardShown = "card_shown"
  /// That notch card was opened.
  case cardTapped = "card_tapped"
  /// The reader cleared Chat and the card went with the thread.
  case cardDismissed = "card_dismissed"
}

extension AnalyticsManager {
  static let dailySummaryEvent = "desktop_daily_summary"

  func trackDailySummary(_ phase: DailySummaryTelemetryPhase) {
    PostHogManager.shared.track(Self.dailySummaryEvent, properties: ["phase": phase.rawValue])
  }
}

// MARK: - Memory review card telemetry
//
// What the card exists to move is the rate at which a claim about the owner gets answered rather
// than only read, so the two events are "it was seen" and "it was acted on, and did the mutation
// land". Bounded dimensions only (desktop `AGENTS.md` → product analytics integrity): the memory's
// text is the owner's own life and never leaves the device, and no memory id is sent — a verdict
// keyed to an id would make PostHog a second, weaker copy of the memory store's own review state.

extension AnalyticsManager {
  static let memoryReviewActionEvent = "memory_review_action"
  static let memoryReviewCardShownEvent = "memory_review_card_shown"

  /// One completed ✓ / ✗ / Fix, reported at the request's own outcome so a failure is never
  /// counted as a correction the owner made.
  func trackMemoryReviewAction(
    source: MemoryReviewSource,
    action: MemoryReviewAction,
    succeeded: Bool,
    category: String
  ) {
    PostHogManager.shared.track(
      Self.memoryReviewActionEvent,
      properties: [
        "source": source.rawValue,
        "action": action.rawValue,
        "outcome": succeeded ? "ok" : "error",
        "memory_category": Self.boundedMemoryCategory(category),
      ])
  }

  /// The card rendered with rows in it. Emitted once per mount, not once per re-render.
  func trackMemoryReviewCardShown(source: MemoryReviewSource, itemCount: Int) {
    PostHogManager.shared.track(
      Self.memoryReviewCardShownEvent,
      properties: [
        "source": source.rawValue,
        "item_count": itemCount,
      ])
  }

  /// Closed set. An unrecognised backend category becomes `other` rather than travelling as a
  /// free-form string that could widen over time into an unbounded dimension.
  nonisolated static func boundedMemoryCategory(_ category: String) -> String {
    let trimmed = category.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty { return "unknown" }
    return MemoryCategory(rawValue: trimmed) != nil ? trimmed : "other"
  }
}
