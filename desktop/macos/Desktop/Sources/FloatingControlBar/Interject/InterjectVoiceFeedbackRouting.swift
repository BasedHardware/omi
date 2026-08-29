import Foundation

/// Instructions and parse for the user-initiated interjection turn.
///
/// Classification rides that one turn — no extra model call. The token is
/// stripped before speech; the remainder is the spoken acknowledgment.
enum InterjectVoiceFeedbackRouting {
  static let classificationInstruction = """
    The user's latest utterance may be a reply to the card quoted above. Classify \
    it as exactly one of these and act in the same turn:
    - Feedback verbs (JIT Decision 24): useful, false_positive, snooze, disable, missed.
      Silence and a dismiss are never feedback — only this utterance is.
    - correction: the card got a fact wrong. Use the existing memory amend/close \
      tools so the ledger supersedes the wrong row. The spoken acknowledgment must \
      name exactly what changed ("Got it — Thursday. I'd had it as Wednesday; fixed.").
    - riff: they are continuing the topic. Answer in place; do not switch surfaces.
    Put exactly one token on its own first line, then the spoken reply:
    [[interject:useful]] or [[interject:false_positive]] or [[interject:snooze]] \
    or [[interject:disable]] or [[interject:missed]] or [[interject:correction]] \
    or [[interject:riff]]
    Do not read the token aloud. Do not mention the classification.
    """

  static func parse(_ text: String) -> (verb: InterjectFeedbackVerb?, spoken: String) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("[[interject:"),
      let close = trimmed.range(of: "]]")
    else {
      return (nil, text)
    }
    let tokenStart = trimmed.index(trimmed.startIndex, offsetBy: "[[interject:".count)
    let raw = String(trimmed[tokenStart..<close.lowerBound])
    let remainder = trimmed[close.upperBound...]
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return (InterjectFeedbackVerb(rawValue: raw), remainder)
  }

  static func spokenText(from text: String) -> String {
    parse(text).spoken
  }

  /// Display copy of an assistant message: the classification token never
  /// renders. A leading token still streaming in (the opener with no `]]`
  /// yet, or a prefix of the opener) is hidden rather than flashed.
  static func displayText(from text: String) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.hasPrefix("[[interject:") {
      guard trimmed.range(of: "]]") != nil else { return "" }
      return parse(text).spoken
    }
    if !trimmed.isEmpty, "[[interject:".hasPrefix(trimmed) {
      return ""
    }
    return text
  }
}
