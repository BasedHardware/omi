import Foundation

/// The grounded closing question a typed answer ends with.
///
/// The realtime voice lane already ends about two thirds of its answers with a
/// question, and those sessions run about four turns. The typed lanes — the chat
/// window and the floating bar — end with one 4-9% of the time, and recall
/// answers never do, even though most of them have an obvious next hop into the
/// same source. This type is the typed lanes' half of closing that gap: the
/// model writes the question after a delimiter on its own final line, and the
/// client lifts it off the visible text into one tappable chip.
///
/// The delimiter, not a heuristic, is what makes the tail separable. Guessing
/// which trailing sentence of a free-form answer was "the follow-up" would
/// mis-fire on answers that legitimately end in a question, and would leave the
/// chip and the prose saying the same thing twice. Kept byte-identical to the
/// backend's `utils/chat_followup.py` so both lanes produce the same block.
enum ChatFollowUpTail {
  /// Chosen so it cannot occur in prose, Markdown, or code the model quotes.
  static let delimiter = "<<<FOLLOWUP>>>"
  static let blockType = "followUp"

  /// A chip has to read in one glance. The prompt asks for under ~15 words;
  /// these are the outer bounds a malformed generation cannot cross.
  static let maxWords = 18
  static let maxCharacters = 160

  /// A generic tail is worse than no tail: it teaches the reader the chip is
  /// filler. Matched against the lowercased, punctuation-trimmed question.
  private static let genericPrefixes = [
    "anything else",
    "is there anything else",
    "want more detail",
    "want any more detail",
    "do you want more detail",
    "want more info",
    "want more information",
    "want me to go on",
    "want me to continue",
    "want me to keep going",
    "want me to elaborate",
    "want me to explain more",
    "would you like to know more",
    "do you want to know more",
    "does that help",
    "did that help",
    "does that make sense",
    "does that answer",
    "any questions",
    "any other questions",
    "got any questions",
    "let me know",
    "can i help",
    "could i help",
    "how can i help",
    "sound good",
    "sounds good",
    "shall i continue",
    "shall i go on",
    "need anything else",
    "want anything else",
    "what else",
  ]

  /// Split a raw model answer into its visible text and its follow-up question.
  ///
  /// The delimiter and everything after it leave the visible text either way — a
  /// half-formed tail must never reach the transcript. `question` is `nil` when
  /// the model wrote no tail, or wrote one that cannot be a chip: empty, not a
  /// question, over-long, or generic.
  static func split(_ text: String) -> (visible: String, question: String?) {
    guard let range = text.range(of: delimiter) else { return (text, nil) }
    var visible = String(text[text.startIndex..<range.lowerBound])
    while let last = visible.last, last.isWhitespace { visible.removeLast() }
    let tail = String(text[range.upperBound...])
    let firstLine =
      tail.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false)
      .first.map(String.init) ?? ""
    guard let question = validatedQuestion(firstLine) else { return (visible, nil) }
    return (visible, question)
  }

  /// The question a raw candidate can become, or `nil` when it cannot be a chip.
  static func validatedQuestion(_ candidate: String) -> String? {
    let question =
      candidate
      .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !question.isEmpty, question.hasSuffix("?") else { return nil }
    guard question.count <= maxCharacters else { return nil }
    guard question.split(separator: " ").count <= maxWords else { return nil }
    guard !isGeneric(question) else { return nil }
    return question
  }

  static func isGeneric(_ question: String) -> Bool {
    let probe = question.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: " ?!."))
    guard !probe.isEmpty else { return true }
    return genericPrefixes.contains { probe.hasPrefix($0) }
  }

  /// What the reader should see while the answer is still streaming.
  ///
  /// The tail streams in like any other token, so without this the chip's words
  /// appear in the prose first and are removed when the turn finalizes. Any
  /// completed delimiter (and everything after it) is dropped, and so is a
  /// trailing partial delimiter — but only once it is unambiguous (`<<<` or
  /// longer), so ordinary text ending in `<` is never eaten.
  static func strippingPendingTail(_ text: String) -> String {
    if let range = text.range(of: delimiter) {
      return String(text[text.startIndex..<range.lowerBound])
    }
    let characters = Array(text)
    let delimiterCharacters = Array(delimiter)
    let maxHold = min(characters.count, delimiterCharacters.count - 1)
    if maxHold >= 3 {
      for length in stride(from: maxHold, through: 3, by: -1) {
        if Array(characters.suffix(length)) == Array(delimiterCharacters.prefix(length)) {
          return String(characters.prefix(characters.count - length))
        }
      }
    }
    return text
  }

  /// Whether a finished turn may carry a chip at all.
  ///
  /// A failed turn never invites the reader one hop further into an answer they
  /// did not get, and an answer that is itself a clarifying question would ask
  /// two questions at once — the chip being the one nobody needed.
  static func shouldAttach(question: String?, visibleText: String, failed: Bool) -> Bool {
    guard !failed, let question, !question.isEmpty else { return false }
    let trimmed = visibleText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    guard let lastLine = trimmed.split(separator: "\n").last?.trimmingCharacters(in: .whitespacesAndNewlines) else {
      return false
    }
    return !lastLine.hasSuffix("?")
  }

  /// The block id both lanes mint for a message, matching the backend's shape.
  static func blockID(messageID: String) -> String { "\(messageID):followup" }
}
