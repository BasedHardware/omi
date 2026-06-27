import Foundation

/// Time thresholds the `StallDetector` uses to promote inter-event gaps
/// and per-tool durations between `.running`, `.slow`, and `.stalled`.
///
/// Values here are first-pass defaults intended to be tuned later
/// against real inter-event-gap and per-tool-duration distributions.
/// The struct is fully `Sendable` + `Equatable` so future tuning is a
/// trivial constants update with no behavioral churn.
struct StallThresholds: Sendable, Equatable {
  /// A gap (inter-event or per-tool) reaching this length promotes to
  /// `.slow`. The UI surfaces a "still working…" annotation.
  let slowGapMs: Int

  /// A gap reaching this length promotes to `.stalled`. The UI surfaces
  /// a message-level banner offering Cancel, wired to
  /// `AgentBridge.interrupt()`.
  let stalledGapMs: Int

  init(slowGapMs: Int, stalledGapMs: Int) {
    precondition(
      slowGapMs > 0 && stalledGapMs > slowGapMs,
      "stalledGapMs must be > slowGapMs > 0"
    )
    self.slowGapMs = slowGapMs
    self.stalledGapMs = stalledGapMs
  }

  /// Ship defaults: slow at 8s, stalled at 20s. Intended to be tuned
  /// later against real inter-event-gap and per-tool-duration data.
  static let v1Defaults = StallThresholds(slowGapMs: 8_000, stalledGapMs: 20_000)
}
