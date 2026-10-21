import Foundation

/// When a finished assistant reply can persist a thumbs rating to the backend.
///
/// The live tail shows rating actions as soon as there is copyable text
/// (`ChatBubbleMetadataBand.actions`). The backend row is keyed by the kernel
/// turn id and only exists after journal sync (`isSynced`). A PATCH before that
/// 404s and used to revert the optimistic local rating.
enum ChatMessageRatingPersistence: Equatable {
  /// Backend row exists; PATCH immediately.
  case persistNow
  /// Journal sync is still in flight; queue the PATCH.
  case waitForSync
  /// The journal failed, so a backend row will never appear. Keep the local rating.
  case localOnly

  static func of(_ message: ChatMessage) -> Self {
    if message.journalStatus == .failed { return .localOnly }
    return message.isSynced ? .persistNow : .waitForSync
  }
}

/// Last-write-wins queue of ratings that must wait for journal sync.
struct ChatMessageRatingQueue: Equatable {
  struct Entry: Equatable {
    let rating: Int?
    /// Telemetry dimension carried with the rating so a queued floating-bar
    /// thumb still reports source=voice after sync (it must never silently
    /// default back to text at flush time).
    let surface: String
    /// Why the user rated it down. Carried through the queue for the same
    /// reason as `surface`: a reason picked before journal sync must reach the
    /// backend after it, not be dropped on the way.
    let reason: ChatFeedbackReason?
  }

  private var pending: [String: Entry] = [:]

  var isEmpty: Bool { pending.isEmpty }

  mutating func enqueue(
    messageId: String, rating: Int?, surface: String = "text", reason: ChatFeedbackReason? = nil
  ) {
    pending.updateValue(Entry(rating: rating, surface: surface, reason: reason), forKey: messageId)
  }

  mutating func cancel(messageId: String) {
    pending.removeValue(forKey: messageId)
  }

  mutating func removeAll() {
    pending.removeAll()
  }

  func contains(_ messageId: String) -> Bool {
    pending.keys.contains(messageId)
  }

  /// Drain ratings whose messages can persist now. Failed-journal and missing
  /// rows are dropped without a persist payload so a 404 cannot revert them.
  /// A queued `nil` is a clear-rating and must persist after sync; do not
  /// collapse it with a missing key.
  ///
  /// A queued rating is keyed by the live-tail message id (the in-memory id at
  /// tap time). Journal projection can later replace that row with a projected
  /// message whose `id` is the kernel `turnId`, while the original id survives
  /// only as `clientTurnId`. Match on either so the rating survives the remap,
  /// and PATCH with the projected (remote) id so the backend row is found.
  mutating func drain(
    using messages: [ChatMessage]
  ) -> [(messageId: String, rating: Int?, surface: String, reason: ChatFeedbackReason?)] {
    var persist: [(messageId: String, rating: Int?, surface: String, reason: ChatFeedbackReason?)] = []
    let snapshot = pending
    for (messageId, entry) in snapshot {
      guard let message = messages.first(where: { $0.id == messageId || $0.clientTurnId == messageId }) else {
        pending.removeValue(forKey: messageId)
        continue
      }
      switch ChatMessageRatingPersistence.of(message) {
      case .persistNow:
        pending.removeValue(forKey: messageId)
        persist.append((message.id, entry.rating, entry.surface, entry.reason))
      case .localOnly:
        pending.removeValue(forKey: messageId)
      case .waitForSync:
        break
      }
    }
    return persist
  }
}
