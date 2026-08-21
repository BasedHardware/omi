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
  /// wastes the evaluation on a half-typed thought. 2s proved too eager in
  /// live runs — composing pauses (recipient → subject → body) are routinely
  /// 1–3s, and a refresh fired inside the burst evaluates a half-typed
  /// question AND burns the repeat-cooldown slot, pushing the real question's
  /// evaluation past the repeat cooldown into the sparse static-screen tick
  /// cadence (~1/min), so the answer lands minutes late instead of seconds.
  static let typingSettleSeconds: TimeInterval = 5

  /// Where the anchor moves when a fired refresh ABORTS before transitioning
  /// (its required fresh capture failed): far enough back that the retry
  /// happens ~10s later instead of waiting out the full repeat cooldown, close
  /// enough that the tick loop cannot double-fire in the same breath.
  static func retryAnchor(now: Date) -> Date {
    now.addingTimeInterval(-(repeatRefreshCooldownSeconds - 10))
  }

  /// Generation-guarded retry anchor: an in-flight refresh chain from context
  /// A that aborts AFTER the user switched to context B must not backdate B's
  /// freshly reset anchor (that would grant B a premature refresh on A's
  /// schedule). The tick increments the generation on every context switch;
  /// an abort may only move the anchor when its launch generation is still
  /// current.
  static func retryAnchor(now: Date, launchGeneration: Int, currentGeneration: Int) -> Date? {
    guard launchGeneration == currentGeneration else { return nil }
    return retryAnchor(now: now)
  }

  /// One re-extraction per typing burst when an evaluation went silent with no
  /// forced lookup: the extraction model stochastically omits the typed
  /// question (~1 in 4 live runs), and without a second look the user's
  /// question dies unanswered. Bounded on purpose — recent typing required, and
  /// the burst stamp (wall time of the last key-down) may only be spent once,
  /// so an idle screen or a repeat silence for the same burst never buys more
  /// model calls.
  static func questionRescueGrant(
    lastRescueBurstStamp: Date?, currentBurstStamp: Date, keyboardIdleSeconds: TimeInterval
  ) -> Bool {
    guard keyboardIdleSeconds < 120 else { return false }
    if let last = lastRescueBurstStamp,
      abs(currentBurstStamp.timeIntervalSince(last)) < 3
    {
      return false
    }
    return true
  }

  /// One grace follow-up per typing burst: after the first fired refresh the
  /// anchor moves to the fire time, so "typed since the anchor" could never
  /// re-trigger without NEW typing — and a refresh whose extraction returned
  /// zero facts (nano does this) lost its question with no second chance. The
  /// second refresh may therefore look this far past the anchor for the burst
  /// that armed the first one. Third and later refreshes require fresh typing.
  static let followUpTypingGraceSeconds: TimeInterval = 45

  static func shouldRefresh(
    secondsSinceAnchor: TimeInterval,
    firedRefreshesThisContext: Int,
    keyboardIdleSeconds: TimeInterval
  ) -> Bool {
    let required =
      firedRefreshesThisContext == 0 ? initialRefreshDwellSeconds : repeatRefreshCooldownSeconds
    guard secondsSinceAnchor >= required else { return false }
    let typingWindow =
      firedRefreshesThisContext == 1
      ? secondsSinceAnchor + followUpTypingGraceSeconds : secondsSinceAnchor
    guard keyboardIdleSeconds < typingWindow else { return false }
    return keyboardIdleSeconds >= typingSettleSeconds
  }
}
