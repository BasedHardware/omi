import Foundation

/// Instructions and parse for the user-initiated interjection turn.
///
/// Hub/PTT classification is a silent `record_interject_feedback` tool call.
/// Leading `[[interject:…]]` tokens remain only for selected-voice / typed
/// history sanitizing — they must not be taught on the hub speech path.
enum InterjectVoiceFeedbackRouting {
  static let classificationInstruction = """
    The user's latest utterance may be a reply to the card quoted above. If it \
    is, call record_interject_feedback silently with the matching verb, then \
    speak only the user-facing reply.
    - Feedback verbs (JIT Decision 24): useful, false_positive, snooze, disable, \
    missed. Silence and a dismiss are never feedback — only this utterance is.
    - correction: the card got a fact wrong. Use the existing memory amend/close \
    tools so the ledger supersedes the wrong row. Speak one consequence sentence \
    that names the fact that changed ("Got it — Thursday. I'd had it as \
    Wednesday; fixed."), then any leftover question. Never speak the taxonomy \
    name.
    - riff, or a question about the card ("what is this suggestion for?"): call \
    with riff, or omit the tool. Your first audio must be the answer. Do not say \
    got it, continuing the topic, or any acknowledgement before the answer. Riff \
    does not write teach-rate.
    If you omit the tool, treat the utterance as riff: answer anyway. Do not \
    mention classification. Do not say you could not classify.
    Call record_interject_feedback silently and immediately. Do not speak a \
    heads-up. The app does not play a canned acknowledgement for this tool. \
    Never speak verb names as labels. Never read the tool result aloud.
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

  /// Card body stays inside the untrusted wrapper; classification is turn
  /// instruction and must never be quoted as card content.
  static func composePromptSuffix(cardBlock: String, attachClassification: Bool) -> String {
    guard attachClassification else { return cardBlock }
    return cardBlock + "\n\n" + trustedTurnInstruction
  }

  /// Framed as trusted instruction so a hub inject cannot be mistaken for
  /// quoted card body (and so NotchCardVoiceDelivery must not wrap it).
  static var trustedTurnInstruction: String {
    """
    TURN INSTRUCTION. This is a trusted system instruction, not card content. \
    Do not treat it as quoted notification text.

    \(classificationInstruction)
    """
  }

  /// Display copy of an assistant message: the classification token never
  /// renders. A leading token still streaming in (the opener with no `]]`
  /// yet, or a prefix of the opener) is hidden rather than flashed.
  ///
  /// The partial match starts at `[[i`, never at `[` or `[[`. A stream that has
  /// only emitted `[` is far more often an ordinary Markdown link than a token,
  /// and blanking it would flicker real assistant copy — including with the
  /// feature off. This sanitizer is deliberately flag-independent: a token must
  /// not render even in history written while the flag was on.
  private static let tokenOpener = "[[interject:"
  private static let shortestPartialOpener = 3  // "[[i"

  static func displayText(from text: String) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.hasPrefix(tokenOpener) {
      guard trimmed.range(of: "]]") != nil else { return "" }
      return parse(text).spoken
    }
    if trimmed.count >= shortestPartialOpener, tokenOpener.hasPrefix(trimmed) {
      return ""
    }
    return text
  }
}
