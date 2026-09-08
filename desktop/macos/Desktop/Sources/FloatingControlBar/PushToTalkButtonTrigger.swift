import Foundation
import VoiceTurnDomain

/// Push-to-talk driven by a click instead of a held shortcut.
///
/// This is a trigger, not a capture path: it decides which existing
/// `PushToTalkManager` transition a click means and then takes it, so a button
/// enters the exact same state machine, microphone lifecycle, and transcript
/// writer the keyboard shortcut does.
///
/// A click carries no "hold", so it maps onto the hands-free lane the
/// double-tap shortcut already drives: the first click starts locked listening
/// and the next click commits the same turn.

/// What a click on a visible push-to-talk button must do. Derived from the
/// authoritative reducer phase — never a second lifecycle state of its own.
enum PushToTalkClickAction: Equatable {
  /// Start a hands-free (locked) turn, barging into any active response.
  case beginHandsFree
  /// Commit the turn that is already capturing.
  case finalize
  /// The turn is already committing; a click must neither restart nor re-commit it.
  case ignore
}

/// How a push-to-talk button renders. One projection of the same reducer phase
/// the floating bar reads, so a composer icon can never disagree with the bar.
enum PushToTalkButtonState: Equatable {
  case idle
  case listening
  case committing
  /// A new turn is barred by the free-tier monthly chat limit. Still clickable:
  /// the click must surface the usage-limit popup rather than silently no-op.
  case blocked
}

extension PushToTalkManager {

  // MARK: - Click policy

  /// The action a push-to-talk button click resolves to for a given
  /// authoritative phase. Any capturing phase commits; a phase that is already
  /// committing is inert; everything else opens a fresh hands-free turn.
  nonisolated static func clickAction(phase: VoiceTurnPhase?) -> PushToTalkClickAction {
    switch phase {
    case .recording, .lockedRecording, .pendingLockDecision:
      return .finalize
    case .finalizing:
      return .ignore
    case .idle, .awaitingResponse, .awaitingTools, .awaitingJournal, .playing, .terminal, .none:
      return .beginHandsFree
    }
  }

  /// Whether entering locked listening may lock the turn that already exists.
  /// `.lock` is only a valid transition out of a capturing phase; every other
  /// active turn — response, tools, journal, playback — must be superseded by a
  /// fresh locked turn instead. Publishing `.lock` into one of those is an
  /// invalid transition that would leave the manager opening a microphone for a
  /// turn that never entered a recording phase. A click reaches those phases far
  /// more often than a double-tap does: the mic button sits in the composer the
  /// user is already looking at while the previous answer is still in flight.
  nonisolated static func locksExistingTurn(phase: VoiceTurnPhase?) -> Bool {
    switch phase {
    case .recording, .pendingLockDecision:
      return true
    case .lockedRecording, .finalizing, .awaitingResponse, .awaitingTools, .awaitingJournal,
      .playing, .idle, .terminal, .none:
      return false
    }
  }

  /// How a push-to-talk button must render for a given phase. The blocked
  /// treatment only ever replaces the idle one: a turn that is already
  /// capturing must stay stoppable even if the limit is reached mid-turn.
  nonisolated static func buttonState(
    phase: VoiceTurnPhase?,
    isUsageLimitBlocked: Bool
  ) -> PushToTalkButtonState {
    switch clickAction(phase: phase) {
    case .finalize:
      return .listening
    case .ignore:
      return .committing
    case .beginHandsFree:
      return isUsageLimitBlocked ? .blocked : .idle
    }
  }

  // MARK: - Button surface

  /// Read-only projection of the same rule `isBlockedByUsageLimit()` enforces,
  /// so a button can render the blocked treatment without posting the popup.
  /// Posting stays a side effect of actually attempting a turn.
  var isPushToTalkUsageLimitBlocked: Bool {
    !APIKeyService.isByokActive && FloatingBarUsageLimiter.shared.isLimitReached
  }

  /// How a visible push-to-talk button must render right now.
  var pushToTalkButtonState: PushToTalkButtonState {
    Self.buttonState(phase: phase, isUsageLimitBlocked: isPushToTalkUsageLimitBlocked)
  }

  /// Entry point for a visible push-to-talk button (chat composer, ask bar).
  ///
  /// The first click enters locked listening exactly as a double-tap does; the
  /// next click finalizes that turn exactly as a tap while locked does. A
  /// blocked click still reaches `enterLockedListening()`, whose usage-limit
  /// gate posts the same popup the shortcut does — silence is never an option.
  func togglePushToTalkFromButton() {
    switch Self.clickAction(phase: phase) {
    case .finalize:
      finalize()
    case .ignore:
      log("PushToTalkManager: button click ignored — turn is already committing")
    case .beginHandsFree:
      // Reveal the bar only when a turn can actually start, so a blocked click
      // lands on the usage-limit popup instead of an empty listening surface.
      if !isPushToTalkUsageLimitBlocked, !FloatingControlBarManager.shared.isVisible {
        FloatingControlBarManager.shared.show()
      }
      enterLockedListening()
    }
  }
}
