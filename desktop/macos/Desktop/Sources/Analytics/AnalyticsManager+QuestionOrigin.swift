import Foundation

// Where a question came from, on top of which surface it was asked on.
//
// `question_asked` already answers "chat window or push-to-talk". It could not
// answer "did Omi invite this question, or did the user arrive with it" — which
// is the whole measurement for the grounded follow-up chip. 57% of asker-days
// are exactly one question; a chip that works shows up as `followup` questions
// with a continuation rate of its own, not as a bump in an undifferentiated
// total.

extension AnalyticsManager {
  /// What prompted a question. `unprompted` is the default and covers every
  /// question the user typed or spoke on their own.
  enum QuestionOrigin: String, Sendable {
    /// Tapped the grounded follow-up chip under an answer.
    case followUp = "followup"
    /// Typed or spoken with nothing offering it.
    case unprompted
    /// A suggestion chip that is not an answer's follow-up.
    case chip
    /// A card action (notch, dashboard, notification).
    case card
  }

  /// Arm the origin for the next accepted question.
  ///
  /// A chip cannot pass the origin down the send path: the send funnels through
  /// `chatMessageSent` / `floatingBarQuerySent`, which every other caller shares.
  /// Arming it immediately before the send that emits keeps the attribution at
  /// the tap, and consuming it on the first emit means a send the provider
  /// rejects can never mislabel a later, unrelated question.
  func questionOriginating(_ origin: QuestionOrigin) {
    QuestionOriginContext.arm(origin)
  }

  /// The origin for the question being emitted right now, consumed so it
  /// applies to exactly one event.
  func consumeQuestionOrigin() -> QuestionOrigin {
    QuestionOriginContext.consume()
  }

  /// Drop an armed origin whose dispatch never reached a question at all.
  ///
  /// The arm is one-shot but it does not expire: a dispatch that returns before
  /// anything is sent — no floating window, no provider, a voice turn already
  /// handed off — emits no `question_asked` to consume it, so the arm survives
  /// and stamps `followup` on the next, unrelated question the user asks. The
  /// surface that armed it is the one that knows the send never happened.
  func questionOriginationAborted() {
    QuestionOriginContext.clear()
  }
}

/// One-shot main-actor store for the armed origin. Deliberately not a mutable
/// global outside the actor: `AnalyticsManager` is `@MainActor`, and both the
/// arm (a tap) and the emit (the provider's acceptance callback) run there.
@MainActor
enum QuestionOriginContext {
  private static var armed: AnalyticsManager.QuestionOrigin?

  static func arm(_ origin: AnalyticsManager.QuestionOrigin) {
    armed = origin
  }

  static func consume() -> AnalyticsManager.QuestionOrigin {
    defer { armed = nil }
    return armed ?? .unprompted
  }

  /// Drop a previously armed origin without emitting.
  static func clear() {
    armed = nil
  }

  /// Test seam.
  static func resetForTests() {
    clear()
  }
}
