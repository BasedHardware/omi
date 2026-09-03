import Foundation

// MARK: - Home knows-list rotation telemetry
//
// The repetition this event exists to measure: over 14 days the owner's hub
// showed the same four commitments 8–12 times each, and the only engagement was
// asking the card to explain itself. `shows_before` makes that rate readable —
// a healthy list is dominated by 0, a repeating one by 3+. `rotated_out_reason`
// says why a slot went empty instead of repeating.
//
// Bounded dimensions only: kind, slot, and reason are closed enum rawValues and
// `shows_before` is a small integer. The row's text is the reader's own tasks
// and questions and never leaves the device (desktop `AGENTS.md` → product
// analytics integrity).

extension AnalyticsManager {
  static let homeKnowsRowEvent = "desktop_home_knows_row"

  /// One row rendered in the knows-list. Emitted once per visit per row, not
  /// once per re-render — the in-visit rotation timer re-renders every few
  /// seconds and would otherwise invent impressions.
  func trackHomeKnowsRowShown(kind: String, slot: HomeKnowsSlot, showsBefore: Int) {
    PostHogManager.shared.track(
      Self.homeKnowsRowEvent,
      properties: [
        "kind": kind,
        "slot": slot.rawValue,
        "shows_before": showsBefore,
      ])
  }

  /// A slot that stayed empty rather than repeating a row already seen.
  func trackHomeKnowsSlotEmpty(slot: HomeKnowsSlot, reason: HomeKnowsRotationReason) {
    PostHogManager.shared.track(
      Self.homeKnowsRowEvent,
      properties: [
        "kind": "empty",
        "slot": slot.rawValue,
        "shows_before": 0,
        "rotated_out_reason": reason.rawValue,
      ])
  }
}
