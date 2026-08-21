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
/// The trigger is KEYBOARD activity, not frame similarity: typing one line
/// into a large window flips at most a bit or two of a preview-scale dHash —
/// the same near-identity that makes the capture preview-skip path starve
/// full captures while the user types — so pixel similarity structurally
/// cannot see the exact events this exists for. A key-down since the anchor,
/// followed by a short settle, is precise, free, and fires for nothing else.
///
/// A content-refresh transition closes and reopens the active visit through
/// the ordinary machinery (departure extraction of the current frame,
/// departure evaluation, fresh entry evaluation), so every existing quota,
/// cooldown, dedup, and budget gate still applies.
///
/// Cost bound: the first refresh of a context needs 12s of dwell; repeats
/// need at least 40s since the previous one; and every refresh requires
/// typing to have happened since the last one. Reading, watching, or an idle
/// screen never buys a model call. Worst case is a continuous typist at ~90
/// refreshes/hour, and each refresh fans out to up to three or four model
/// calls (departure extraction, departure evaluation, entry evaluation, a
/// possible forced retrieval), all still bounded by the per-tier server
/// quotas and delivery-level cooldowns — and remotely stoppable on its own
/// via `ContextBucketsFeature.isDwellRefreshEnabled`.
enum ContextDwellRefreshPolicy {
  /// Dwell before the FIRST refresh of a context: long enough to type a
  /// question, short enough that its answer lands within ~30s of typing.
  static let initialRefreshDwellSeconds: TimeInterval = 12

  /// Minimum spacing between refreshes within one continuous context dwell.
  static let repeatRefreshCooldownSeconds: TimeInterval = 40

  /// The keyboard must have been quiet at least this long: mid-word capture
  /// wastes the evaluation on a half-typed thought.
  static let typingSettleSeconds: TimeInterval = 2

  /// Where the anchor moves when a fired refresh ABORTS before transitioning
  /// (its required fresh capture failed): far enough back that the retry
  /// happens ~10s later instead of waiting out the full repeat cooldown, close
  /// enough that the tick loop cannot double-fire in the same breath.
  static func retryAnchor(now: Date) -> Date {
    now.addingTimeInterval(-(repeatRefreshCooldownSeconds - 10))
  }

  static func shouldRefresh(
    secondsSinceAnchor: TimeInterval,
    firedRefreshesThisContext: Int,
    keyboardIdleSeconds: TimeInterval
  ) -> Bool {
    let required =
      firedRefreshesThisContext == 0 ? initialRefreshDwellSeconds : repeatRefreshCooldownSeconds
    guard secondsSinceAnchor >= required else { return false }
    // Typed since the anchor: the last key-down is younger than the anchor.
    guard keyboardIdleSeconds < secondsSinceAnchor else { return false }
    return keyboardIdleSeconds >= typingSettleSeconds
  }
}
