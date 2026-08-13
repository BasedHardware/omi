import Foundation

extension ChatProvider {
  /// Rate a message (thumbs up/down).
  /// - Parameters:
  ///   - messageId: The message ID to rate
  ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
  func rateMessage(_ messageId: String, rating: Int?) async {
    switch queueMessageRating(messageId, rating: rating) {
    case .persistNow:
      await persistMessageRating(messageId, rating: rating)
    case .waitForSync, .localOnly, nil:
      break
    }
  }

  /// Apply the rating locally and decide whether a backend PATCH can run yet.
  @discardableResult
  func queueMessageRating(_ messageId: String, rating: Int?) -> ChatMessageRatingPersistence? {
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }
    messages[index].rating = rating
    let decision = ChatMessageRatingPersistence.of(messages[index])
    switch decision {
    case .persistNow:
      pendingMessageRatings.cancel(messageId: messageId)
    case .waitForSync:
      pendingMessageRatings.enqueue(messageId: messageId, rating: rating)
    case .localOnly:
      pendingMessageRatings.cancel(messageId: messageId)
    }
    return decision
  }

  func flushPendingMessageRatings() {
    let ready = pendingMessageRatings.drain(using: messages)
    for item in ready {
      Task { await persistMessageRating(item.messageId, rating: item.rating) }
    }
  }

  func persistMessageRating(_ messageId: String, rating: Int?) async {
    do {
      if let persistMessageRatingHandler {
        try await persistMessageRatingHandler(messageId, rating)
      } else {
        try await APIClient.shared.rateMessage(messageId: messageId, rating: rating)
      }
      log("Rated message \(messageId) with rating: \(String(describing: rating))")
      if let rating {
        AnalyticsManager.shared.messageRated(rating: rating)
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
