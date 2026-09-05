import Foundation

extension ChatProvider {
  /// Rate a message (thumbs up/down).
  /// - Parameters:
  ///   - messageId: The message ID to rate
  ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
  ///   - surface: which response surface was rated — "text" (main-window
  ///     chat) or "voice" (floating-bar responses). Telemetry-only dimension.
  ///   - reason: why the answer was rated down; nil when not asked or skipped
  func rateMessage(
    _ messageId: String, rating: Int?, surface: String = "text",
    reason: ChatFeedbackReason? = nil
  ) async {
    let resolvedSurface = Self.ratingSurface(
      for: messages.first(where: { $0.id == messageId }), requested: surface)
    switch queueMessageRating(
      messageId, rating: rating, surface: resolvedSurface, reason: reason)
    {
    case .persistNow:
      await persistMessageRating(
        messageId, rating: rating, surface: resolvedSurface, reason: reason)
    case .waitForSync, .localOnly, nil:
      break
    }
  }

  /// Thumbs on proactive-notification messages (focus/insight/task/memory
  /// cards in the transcript) rate the notification, not a general Omi
  /// answer — tag them "notification" so response-quality % excludes them,
  /// whichever surface the caller rated from.
  static func ratingSurface(for message: ChatMessage?, requested: String) -> String {
    guard let message, ChatContinuityInvariants.isProactiveNotification(message) else {
      return requested
    }
    return "notification"
  }

  /// Apply the rating locally and decide whether a backend PATCH can run yet.
  @discardableResult
  func queueMessageRating(
    _ messageId: String, rating: Int?, surface: String = "text",
    reason: ChatFeedbackReason? = nil
  ) -> ChatMessageRatingPersistence? {
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }
    messages[index].rating = rating
    let decision = ChatMessageRatingPersistence.of(messages[index])
    switch decision {
    case .persistNow:
      pendingMessageRatings.cancel(messageId: messageId)
    case .waitForSync:
      pendingMessageRatings.enqueue(
        messageId: messageId, rating: rating, surface: surface, reason: reason)
    case .localOnly:
      pendingMessageRatings.cancel(messageId: messageId)
    }
    return decision
  }

  func flushPendingMessageRatings() {
    let ready = pendingMessageRatings.drain(using: messages)
    guard !ready.isEmpty else { return }
    // Fence against an account/owner transition: if the owner changes while a
    // drained PATCH is in flight, `resetSessionStateForAuthChange` clears the
    // queue and messages, so the stale owner captured here no longer matches
    // and the PATCH is dropped instead of mutating the new owner's session.
    let ownerAtFlush = RuntimeOwnerIdentity.currentOwnerId()
    for item in ready {
      Task { [weak self] in
        await self?.persistMessageRating(
          item.messageId, rating: item.rating, surface: item.surface, reason: item.reason,
          expectedOwner: ownerAtFlush)
      }
    }
  }

  /// Write a rating to the backend, serialized against any other write for the
  /// same message.
  ///
  /// A reasoned thumbs-down produces two writes — the bare rating on tap, then
  /// the rating carrying the reason — and the backend persists each with a full
  /// document `set`. Left concurrent, the bare write can land second and erase
  /// the reason the user just picked, which is the one part of the interaction
  /// we asked them for. Chaining per message makes the last write the last
  /// *sent*, which is the order the user actually acted in.
  func persistMessageRating(
    _ messageId: String, rating: Int?, surface: String = "text",
    reason: ChatFeedbackReason? = nil, expectedOwner: String? = nil
  ) async {
    let previous = messageRatingWriteChain[messageId]
    let task = Task { @MainActor [weak self] in
      await previous?.value
      await self?.sendMessageRating(
        messageId, rating: rating, surface: surface, reason: reason,
        expectedOwner: expectedOwner)
    }
    messageRatingWriteChain[messageId] = task
    await task.value
    if messageRatingWriteChain[messageId] == task {
      messageRatingWriteChain[messageId] = nil
    }
  }

  private func sendMessageRating(
    _ messageId: String, rating: Int?, surface: String,
    reason: ChatFeedbackReason?, expectedOwner: String?
  ) async {
    if let expectedOwner, RuntimeOwnerIdentity.currentOwnerId() != expectedOwner { return }
    let message = messages.first(where: { $0.id == messageId })
    do {
      if let message, ChatContinuityInvariants.isProactiveNotification(message), rating == -1 {
        await InterjectSuggestionFeedbackMutation.recordFromChatRating(
          continuityKey: message.clientTurnId, reason: reason)
      }
      if let persistMessageRatingHandler {
        try await persistMessageRatingHandler(messageId, rating)
      } else {
        try await APIClient.shared.rateMessage(
          messageId: messageId, rating: rating, reason: reason, surface: surface)
      }
      log("Rated message \(messageId) with rating: \(String(describing: rating))")
      if let rating {
        AnalyticsManager.shared.messageRated(rating: rating, surface: surface)
      }
    } catch {
      logError("Failed to rate message", error: error)
      if let index = messages.firstIndex(where: { $0.id == messageId }),
        messages[index].rating == rating
      {
        messages[index].rating = nil
      }
    }
  }
}
