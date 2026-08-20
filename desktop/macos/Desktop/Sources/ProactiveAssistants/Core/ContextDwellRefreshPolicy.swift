import Foundation

/// Decides when a long dwell in one context earns a content-refresh transition.
///
/// The director evaluates a bucket once, ~2s after ENTERING a context, grounded
/// on the frame at that instant. Content the user creates later in the same
/// visit — most importantly a question they are typing — was never in any
/// evaluated frame, so the pipeline structurally could not react to it until
/// the next app switch. Worse, single-page apps (Superhuman, Gmail, Linear)
/// often never change the window title, so "the next app switch" can be hours
/// away and the whole session is one never-re-evaluated visit.
///
/// A content-refresh transition closes and reopens the active visit through
/// the ordinary machinery (departure extraction of the current frame,
/// departure evaluation, fresh entry evaluation), so every existing quota,
/// cooldown, dedup, and budget gate still applies.
///
/// Cost bound: the first refresh of a context needs 20s of dwell; each
/// further refresh needs at least 90s since the previous one; and every
/// refresh requires the screen to have actually changed since the last
/// evaluated frame — a static screen never buys a model call. Worst case is
/// a continuously-changing screen at ~40 refreshes/hour, the same order as
/// ordinary app-switch evaluations, and the per-operation server quotas
/// still cap the day.
enum ContextDwellRefreshPolicy {
  /// Dwell before the FIRST refresh of a context: long enough to type a
  /// question, short enough that its answer lands within ~30s of typing.
  static let initialRefreshDwellSeconds: TimeInterval = 20

  /// Minimum spacing between refreshes within one continuous context dwell.
  static let repeatRefreshCooldownSeconds: TimeInterval = 90

  /// Preview-scale dHash similarity (1 - hamming/64, the metric the capture
  /// preview-skip path uses) at or above which the screen counts as unchanged
  /// since the last evaluated frame.
  static let unchangedSimilarityFloor: Double = 0.97

  static func shouldRefresh(
    secondsSinceAnchor: TimeInterval,
    firedRefreshesThisContext: Int,
    lastEvaluatedHash: UInt64?,
    currentHash: UInt64
  ) -> Bool {
    let required =
      firedRefreshesThisContext == 0 ? initialRefreshDwellSeconds : repeatRefreshCooldownSeconds
    guard secondsSinceAnchor >= required else { return false }
    guard let lastEvaluatedHash else { return true }
    let distance = (currentHash ^ lastEvaluatedHash).nonzeroBitCount
    let similarity = 1.0 - Double(distance) / Double(UInt64.bitWidth)
    return similarity < unchangedSimilarityFloor
  }
}
