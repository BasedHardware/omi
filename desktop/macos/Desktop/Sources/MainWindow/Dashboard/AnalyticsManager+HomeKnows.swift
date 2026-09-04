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

  /// Scoped observation of the two emits below, in the style of
  /// `questionTelemetryCaptureForTests`: nil in production, and installed at the same boundary as
  /// PostHog so what a test or the automation bridge reads is what production emitted rather than
  /// a second guess at it.
  ///
  /// `static` on this extension rather than a stored property on `AnalyticsManager`, which is the
  /// only difference from that seam. The manager is a 1,600-line file that this event has nothing
  /// else to do with, and the two readers of this seam are the two functions directly underneath
  /// it. The isolation is identical — `AnalyticsManager` is `@MainActor`, so this is too.
  ///
  /// Why a seam at all: `rotated_out_reason` is the only place the rotation policy's verdict is
  /// ever named. It is computed inside `HomeKnowsListComposer`, consumed by this emit, and
  /// readable nowhere afterwards, so a flow that could not watch the emit could see a slot go
  /// empty and never learn whether it went empty for the reason the reader's ledger says it should.
  static var homeKnowsTelemetryCaptureForTests: (@MainActor (String, [String: Any]) -> Void)?

  /// One row rendered in the knows-list. Emitted once per visit per row, not
  /// once per re-render — the in-visit rotation timer re-renders every few
  /// seconds and would otherwise invent impressions.
  func trackHomeKnowsRowShown(kind: String, slot: HomeKnowsSlot, showsBefore: Int) {
    let properties: [String: Any] = [
      "kind": kind,
      "slot": slot.rawValue,
      "shows_before": showsBefore,
    ]
    Self.homeKnowsTelemetryCaptureForTests?(Self.homeKnowsRowEvent, properties)
    PostHogManager.shared.track(Self.homeKnowsRowEvent, properties: properties)
  }

  /// A slot that stayed empty rather than repeating a row already seen.
  func trackHomeKnowsSlotEmpty(slot: HomeKnowsSlot, reason: HomeKnowsRotationReason) {
    let properties: [String: Any] = [
      "kind": "empty",
      "slot": slot.rawValue,
      "shows_before": 0,
      "rotated_out_reason": reason.rawValue,
    ]
    Self.homeKnowsTelemetryCaptureForTests?(Self.homeKnowsRowEvent, properties)
    PostHogManager.shared.track(Self.homeKnowsRowEvent, properties: properties)
  }
}
