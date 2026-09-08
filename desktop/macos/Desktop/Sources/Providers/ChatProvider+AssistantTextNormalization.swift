import Foundation

/// The projection of a streaming assistant answer: the follow-up tail
/// withheld and sentence spacing normalized. Applied on every streaming
/// flush over the whole accumulated answer, so it is kept regex-cached and
/// allocation-light. Split out of `ChatProvider.swift`, which is bounded by
/// the agent-runtime convergence ratchet.
extension ChatProvider {
  /// What a streaming assistant message shows right now.
  ///
  /// The grounded follow-up tail streams in like any other token, so without
  /// stripping it here the chip's words appear in the prose first and are
  /// removed only when the turn finalizes. Composed with sentence spacing
  /// because both are projections of the same accumulated text.
  static func normalizeStreamingAssistantText(_ text: String) -> String {
    normalizeAssistantSentenceSpacing(ChatFollowUpTail.strippingPendingTail(text))
  }

  /// Normalize missing spaces after sentence punctuation in assistant messages.
  /// Example: "Hello.World" -> "Hello. World", "Great!Lets go" -> "Great! Lets go"
  ///
  /// Code spans are preserved verbatim so identifiers, file paths, and method
  /// chains like `pd.DataFrame`, `System.IO`, or `foo.Bar()` are never mangled
  /// into `pd. DataFrame`. Both fenced code blocks (``` / ~~~) and inline
  /// backtick spans are skipped. Applied on every streaming flush, so it must
  /// treat an unterminated span (fence or backtick still open mid-stream) as
  /// code to avoid corrupting code that is still arriving.
  static func normalizeAssistantSentenceSpacing(_ text: String) -> String {
    let lines = text.components(separatedBy: "\n")
    var output: [String] = []
    output.reserveCapacity(lines.count)
    var inFencedBlock = false

    for line in lines {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
        inFencedBlock.toggle()
        output.append(line)  // fence marker line, verbatim
      } else if inFencedBlock {
        output.append(line)  // code content, verbatim
      } else {
        output.append(normalizeInlinePreservingCode(line))
      }
    }

    return output.joined(separator: "\n")
  }

  /// Apply sentence-spacing normalization to a single line, leaving inline
  /// backtick code spans untouched. An odd number of backticks (an unterminated
  /// span) leaves its trailing content treated as code.
  private static func normalizeInlinePreservingCode(_ line: String) -> String {
    guard line.contains("`") else { return applySentenceSpacing(line) }

    let parts = line.split(separator: "`", omittingEmptySubsequences: false)
    let normalizedParts = parts.enumerated().map { index, part -> String in
      // Even segments are outside inline code; odd segments are inside.
      index.isMultiple(of: 2) ? applySentenceSpacing(String(part)) : String(part)
    }
    return normalizedParts.joined(separator: "`")
  }

  /// Compiled once. Both used to be compiled inside this function, which runs
  /// per line of the whole accumulated answer on every streaming flush — two
  /// pattern compiles per line per flush, for two patterns that never change.
  private static let sentencePunctuationBeforeUpper =
    try? NSRegularExpression(pattern: #"([.!?])(?=[A-Z])"#)
  private static let sentencePunctuationBeforeQuotedUpper =
    try? NSRegularExpression(pattern: #"([.!?])(?=[\"“'‘][A-Z])"#)

  private static func applySentenceSpacing(_ text: String) -> String {
    // Both patterns need sentence punctuation; most lines of prose end with it
    // exactly once and most Markdown structure has none at all.
    guard text.contains(where: { $0 == "." || $0 == "!" || $0 == "?" }) else { return text }
    var normalized = text

    if let punctuationUpper = sentencePunctuationBeforeUpper {
      let range = NSRange(normalized.startIndex..., in: normalized)
      normalized = punctuationUpper.stringByReplacingMatches(
        in: normalized, options: [], range: range, withTemplate: "$1 ")
    }

    if let punctuationQuotedUpper = sentencePunctuationBeforeQuotedUpper {
      let range = NSRange(normalized.startIndex..., in: normalized)
      normalized = punctuationQuotedUpper.stringByReplacingMatches(
        in: normalized, options: [], range: range, withTemplate: "$1 ")
    }

    return normalized
  }
}
