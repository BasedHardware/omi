import Foundation

/// Decides when a long dwell in one context earns a content-refresh transition.
///
/// The director evaluates a bucket once, ~2s after ENTERING a context, grounded
/// on the frame at that instant. Content the user creates later in the same
/// visit — most importantly a question they are typing — was never in any
/// evaluated frame, so the pipeline structurally could not react to it until
/// the next app switch. A content-refresh transition closes and reopens the
/// active visit through the ordinary machinery (departure extraction of the
/// current frame, departure evaluation, fresh entry evaluation), so every
/// existing quota, cooldown, dedup, and budget gate still applies.
///
/// Cost bound: at most `refreshDwellMilestones.count` refreshes per continuous
/// context dwell, and only when the screen actually changed since the last
/// evaluated frame — a static screen never buys a model call.
enum ContextDwellRefreshPolicy {
  /// Dwell seconds at which refresh N (0-based) becomes eligible. Two chances:
  /// one soon enough that a typed question is answered within ~30s, one later
  /// for slow writers. Never more per dwell.
  static let refreshDwellMilestones: [TimeInterval] = [20, 45]

  /// Preview-scale dHash similarity (1 - hamming/64, the metric the capture
  /// preview-skip path uses) at or above which the screen counts as unchanged
  /// since the last evaluated frame.
  static let unchangedSimilarityFloor: Double = 0.97

  static func shouldRefresh(
    dwellSeconds: TimeInterval,
    completedRefreshes: Int,
    lastEvaluatedHash: UInt64?,
    currentHash: UInt64
  ) -> Bool {
    guard completedRefreshes >= 0, completedRefreshes < refreshDwellMilestones.count else {
      return false
    }
    guard dwellSeconds >= refreshDwellMilestones[completedRefreshes] else { return false }
    guard let lastEvaluatedHash else { return true }
    let distance = (currentHash ^ lastEvaluatedHash).nonzeroBitCount
    let similarity = 1.0 - Double(distance) / Double(UInt64.bitWidth)
    return similarity < unchangedSimilarityFloor
  }
}
