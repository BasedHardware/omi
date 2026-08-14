import Foundation

/// What a chat turn that failed leaves behind in the transcript.
///
/// A failed turn used to leave nothing durable. The assistant row a turn stages
/// is empty until output arrives; `projectJournalTurns` deletes an empty
/// `.failed` row as a placeholder; and the only account of the failure was
/// `ChatProvider.errorMessage` / `currentError` — one slot for the whole
/// provider, dismissible, overwritten by the next turn and gone on relaunch.
/// Six consecutive failures therefore read as six consecutive questions with no
/// answers between them and one card at the bottom: the reader cannot tell
/// which question failed, and reloading loses even that.
///
/// The marker this type produces is written onto the failing turn's own
/// assistant row and journaled with it, so it is per-turn, ordered and durable.
/// The policy lives here rather than in `ChatProvider` on purpose: what counts
/// as a failure, what the reader is told, and what the row persists are
/// decisions a type can own and a test can drive without a provider, while the
/// coordinator keeps only the decision to record one.
struct ChatTurnFailureNotice: Equatable, Sendable {
  /// The one sentence the reader sees — in the transcript, and in any card
  /// that stays up beside it.
  let text: String
  /// Whether sending the same message again could succeed. Drives whether the
  /// prompt is worth keeping for a retry; never invites a retry that the
  /// classifier already knows cannot work.
  let retryable: Bool

  /// `AgentErrorClassifier` returns `.unknown` when its corpus has no rule for
  /// a string, and then echoes the provider's raw text back as the user
  /// message. A dismissible banner can afford that; a row that stays in the
  /// transcript cannot — `HTTP 402 status code (no body)` is what the reader
  /// would still be reading a month from now. The raw string keeps going to
  /// the local log and to Sentry; the row says the part a reader can act on.
  static let unclassifiedText = "Omi couldn't answer this one. Try sending it again."

  /// The marker for a turn that ended in a raw provider/transport error, or
  /// `nil` when the ending was a cancellation rather than a failure.
  ///
  /// `presentsUserError` is the provider's own cancelled-vs-failed
  /// disposition. An intentional Stop and a superseded turn are cancellations,
  /// never errors (desktop analytics-integrity contract), and neither earns a
  /// marker: nothing went wrong that the reader needs explained.
  static func forFailure(
    errorDescription: String,
    presentsUserError: Bool
  ) -> ChatTurnFailureNotice? {
    guard presentsUserError else { return nil }
    let classified = AgentErrorClassifier.classify(errorDescription)
    guard classified.code != .userInterrupted else { return nil }
    if classified.code == .unknown {
      return ChatTurnFailureNotice(text: unclassifiedText, retryable: true)
    }
    return ChatTurnFailureNotice(text: classified.userMessage, retryable: classified.retryable)
  }

  /// Recycled-worker user copy hides the provider status. Prefer the technical
  /// message so a 402 still reaches the billing rule.
  static func classificationText(for error: Error) -> String {
    guard let bridgeError = error as? BridgeError,
      case .agentRuntimeFailure(let failure) = bridgeError
    else {
      return error.localizedDescription
    }
    return [failure.technicalMessage, failure.userMessage]
      .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
      .joined(separator: "\n")
  }

  /// The marker for copy the caller already owns in user-facing form — the
  /// watchdog timeout, the provider-auth prompt, a retained card's summary.
  /// Deliberately not re-classified: those sentences were written for the
  /// reader, and running them back through the corpus would collapse them into
  /// the generic one.
  static func stating(_ userFacingMessage: String, retryable: Bool) -> ChatTurnFailureNotice? {
    let trimmed = userFacingMessage.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return ChatTurnFailureNotice(text: trimmed, retryable: retryable)
  }

  /// What the turn's assistant row persists: whatever the turn managed to
  /// produce, then why it stopped.
  ///
  /// A row that kept a partial answer must still say it did not finish, and a
  /// row that produced nothing must not be left empty — an empty `.failed` row
  /// is deleted by the journal projection as a placeholder, which is exactly
  /// how a failed turn used to leave its question orphaned.
  func transcriptContent(partialText: String) -> String {
    let partial = partialText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !partial.isEmpty else { return text }
    return partial + "\n\n" + text
  }

  /// The marker a turn that threw `error` leaves on its own row, or `nil` when
  /// the ending was a cancellation rather than a failure.
  ///
  /// This is the single decision point for "did this turn fail, and what does
  /// the reader get told". The caller supplies the two sentences it already
  /// owns in user-facing form — the watchdog timeout and the provider-auth
  /// prompt — and nothing else about the provider is needed to choose.
  static func forTurn(
    error: Error,
    watchdogFired: Bool,
    toolStallAbortFired: Bool,
    timeoutMessage: String?,
    providerAuthMessage: String
  ) -> ChatTurnFailureNotice? {
    // The watchdog reaches the send-loop catch as `.stopped` — from its own
    // interrupt — so its copy has to be chosen before `.stopped` can be read
    // as the reader pressing Stop.
    if let timeoutMessage {
      return stating(timeoutMessage, retryable: true)
    }
    guard let bridgeError = error as? BridgeError else {
      return forFailure(errorDescription: error.localizedDescription, presentsUserError: true)
    }
    if case .stopped = bridgeError { return nil }
    if case .agentRuntimeFailure(let failure) = bridgeError, failure.failureCode == .authentication {
      return stating(providerAuthMessage, retryable: false)
    }
    // A card that survives words the row, so the two surfaces cannot disagree.
    if let card = retainedCard(ChatErrorState.from(bridgeError)) {
      return stating(card.userFacingSummary, retryable: card.primaryRecovery == .retry)
    }
    return forFailure(
      errorDescription: classificationText(for: error),
      presentsUserError: ChatQueryFailureDisposition.classify(
        error,
        watchdogFired: watchdogFired,
        toolStallAbortFired: toolStallAbortFired
      ).presentsUserError
    )
  }

  /// The `ChatErrorCard` that stays up beside the row, if any.
  ///
  /// A failed turn is recorded on its own row, so a card that only repeats it
  /// is the second wording this fix exists to remove. A card survives only
  /// when it carries a recovery the transcript cannot offer — signing in, or
  /// repairing the install. Retry and dismiss are not such recoveries: the
  /// question is in the transcript with the reason under it, and the text is
  /// back in the composer ready to send again.
  ///
  /// When a card is retained, the row is worded from that same card, so the
  /// two surfaces can never disagree.
  static func retainedCard(_ card: ChatErrorState?) -> ChatErrorState? {
    guard let card else { return nil }
    switch card.primaryRecovery {
    case .signIn, .installRuntime:
      return card
    case .retry, .dismiss:
      return nil
    }
  }
}
