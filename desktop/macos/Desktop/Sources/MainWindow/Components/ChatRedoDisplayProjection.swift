import Foundation

/// **Where a redone answer is drawn.** Redo asks the same question again, and
/// the reader is owed the new answer *where the old one was* — not a second
/// copy of their question with a second answer at the bottom of the thread.
///
/// The journal cannot give that by rewriting history: it is append-only, and
/// the kernel refuses every content mutation of a completed, run-linked turn
/// (`assertPublicJournalUpdatePolicy`). A delivered answer stays a fact. So the
/// redo is an ordinary new turn, durable like any other, and this projection is
/// what the transcript *shows*: the replacement takes the superseded answer's
/// place, and the turn's own two rows — the repeated question and the answer at
/// the end — are not drawn a second time.
///
/// Nothing is invented and nothing is lost: every row still exists in
/// `ChatProvider.messages`, in the journal, and on the backend. This decides
/// only which of them the thread renders, and where.
enum ChatRedoDisplayProjection {
  /// Guards against a malformed key chain pointing at itself.
  private static let maximumChainDepth = 64

  static func project(_ messages: [ChatMessage]) -> [ChatMessage] {
    /// Row id → the id its turn supersedes (both halves of a redo turn carry it).
    var supersededByRow: [String: String] = [:]
    for message in messages {
      guard
        let superseded = ChatContinuityInvariants.supersededMessageID(
          fromContinuityKey: message.clientTurnId)
      else { continue }
      supersededByRow[message.id] = superseded
    }
    guard !supersededByRow.isEmpty else { return messages }

    let presentIDs = Set(messages.map(\.id))

    /// The ORIGINAL row a redo ultimately stands in for. Redoing a redo chains
    /// (A → A′ → A″), and every link in that chain belongs in the first row's
    /// slot. A chain whose original is not in this window — history that has not
    /// been paged in — resolves to nil, and the redo then renders where it
    /// actually is rather than vanishing with nothing in its place.
    func originalSlot(for rowID: String) -> String? {
      guard var target = supersededByRow[rowID] else { return nil }
      var depth = 0
      while let next = supersededByRow[target], depth < maximumChainDepth {
        target = next
        depth += 1
      }
      return presentIDs.contains(target) ? target : nil
    }

    /// The newest answer standing in for each original slot. Later rows win, so
    /// redoing three times shows the third answer. A failed redo's assistant row
    /// carries the failure notice, not an answer — admitting it here would draw
    /// the error text over the answer it tried to replace.
    var replacement: [String: ChatMessage] = [:]
    for message in messages where message.sender == .ai && message.journalStatus != .failed {
      guard let slot = originalSlot(for: message.id) else { continue }
      replacement[slot] = message
    }
    // Deliberately no `replacement.isEmpty` early return: a redo whose answer
    // never arrived (the turn failed, so the journal projection dropped its
    // empty assistant row) still hides its repeated question. The reader is
    // left with the answer they already had and the failure's own error card,
    // rather than their question stranded under it with nothing beneath.

    var projected: [ChatMessage] = []
    projected.reserveCapacity(messages.count)
    for message in messages {
      if originalSlot(for: message.id) != nil {
        // Drawn in the slot it replaces (assistant), or not drawn at all (the
        // question the reader already asked once).
        continue
      }
      projected.append(replacement[message.id] ?? message)
    }
    return projected
  }
}
