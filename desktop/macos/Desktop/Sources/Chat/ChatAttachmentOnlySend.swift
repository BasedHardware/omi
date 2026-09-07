import Foundation

/// **A file dropped in with no words is a message.** These are the three decisions an
/// attachment-only send needs: whether a composer has anything to send, what the user row says,
/// and what the model is asked. They live beside `attachmentContextPrompt`'s caller in spirit but
/// outside `ChatProvider.swift`, whose size is capped by the agent-runtime convergence ratchet.
extension ChatProvider {
  /// Whether a composer holding `text` plus these staged items has a message to send. A file or a
  /// referenced conversation dropped in with no words *is* the message — "what do you make of this"
  /// is implied — so return on an attachment-only composer sends rather than doing nothing.
  nonisolated static func hasSendableSubject(text: String, attachmentCount: Int, referenceCount: Int) -> Bool {
    !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || attachmentCount > 0 || referenceCount > 0
  }

  /// The user text an attachment-only send carries. The kernel journal tombstones an empty user turn
  /// and the backend rejects one, and the transcript needs a row the reader recognises above the
  /// attachment cards, so the row says what was attached rather than pretending the reader typed.
  nonisolated static func attachmentOnlyCaption(attachmentCount: Int, referenceCount: Int) -> String {
    var parts: [String] = []
    if attachmentCount > 0 {
      parts.append(attachmentCount == 1 ? "1 file" : "\(attachmentCount) files")
    }
    if referenceCount > 0 {
      parts.append(referenceCount == 1 ? "1 conversation" : "\(referenceCount) conversations")
    }
    guard !parts.isEmpty else { return "" }
    return parts.joined(separator: " and ") + " attached"
  }

  /// What the model is asked on an attachment-only send. The caption above is a label, not a
  /// request; handed only "1 file attached", the model asks the reader what they want — the very
  /// question they skipped typing on purpose.
  nonisolated static func attachmentOnlyModelPrompt(attachmentCount: Int, referenceCount: Int) -> String {
    let what = attachmentOnlyCaption(attachmentCount: attachmentCount, referenceCount: referenceCount)
    return """
      [The user sent this message with no text — only the attached content (\(what)).]
      Respond to the attachment(s) directly. Inspect their contents first, then give the most useful \
      response for what they are: summarize a document and surface what matters in it, describe and \
      interpret an image, review code, or pull the key points, decisions and action items out of a \
      conversation. Finish with one or two concrete things you can do next with it. Do not ask what the \
      user wants unless the content is genuinely ambiguous.
      """
  }
}
