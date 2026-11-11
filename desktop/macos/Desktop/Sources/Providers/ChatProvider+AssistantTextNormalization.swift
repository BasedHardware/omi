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
  /// into `pd. DataFrame`. The scanner mirrors the renderer's
  /// `OmiMarkdownInlineCode` semantics — inline spans match by whole backtick
  /// runs (a double-backtick span like ``foo.Bar`` is one span) and may cross
  /// a line break the way the renderer's own span search does — with one
  /// deliberate streaming difference: an unterminated span treats its tail as
  /// code, because the run that would close it has not arrived yet. Fenced
  /// blocks close only on a bare run of their own fence character at least as
  /// long as the opener, so a `~~~` line inside a ``` block stays code.
  /// Applied on every streaming flush, so it is one linear scan: fences are
  /// line-shaped, and each non-fenced region between them is scanned once.
  static func normalizeAssistantSentenceSpacing(_ text: String) -> String {
    guard text.contains("`") || text.contains("~") else { return applySentenceSpacing(text) }

    let lines = text.components(separatedBy: "\n")
    var output: [String] = []
    output.reserveCapacity(lines.count)
    // The open fenced block, held as its fence character and run length.
    var openFence: (character: Character, length: Int)?
    var proseLines: [String] = []

    func flushProseRegion() {
      guard !proseLines.isEmpty else { return }
      output.append(Self.normalizeProseRegion(proseLines.joined(separator: "\n")))
      proseLines.removeAll(keepingCapacity: true)
    }

    for line in lines {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      let run = Self.fenceRun(of: trimmed)
      if let fence = openFence {
        // Only a bare run of the fence's own character at least as long as
        // its opener closes the block; anything else is fenced code content.
        if let run, run.character == fence.character, run.length >= fence.length, run.bare {
          openFence = nil
        }
        output.append(line)
      } else if let run, run.length >= 3 {
        flushProseRegion()
        openFence = (run.character, run.length)
        output.append(line)
      } else {
        proseLines.append(line)
      }
    }
    flushProseRegion()

    return output.joined(separator: "\n")
  }

  /// Sentence spacing for one contiguous non-fenced region, leaving the
  /// renderer's inline code spans untouched.
  private static func normalizeProseRegion(_ region: String) -> String {
    guard region.contains("`") else { return applySentenceSpacing(region) }

    var result = String()
    result.reserveCapacity(region.count)
    var cursor = region.startIndex
    var proseStart = region.startIndex

    func appendProse(_ upperBound: String.Index) {
      guard proseStart < upperBound else { return }
      // Both spacing patterns look at a single character of lookahead, so
      // normalizing each prose run in isolation cannot corrupt a boundary
      // that falls outside it.
      result += applySentenceSpacing(String(region[proseStart..<upperBound]))
    }

    while cursor < region.endIndex {
      guard region[cursor] == "`" else {
        cursor = region.index(after: cursor)
        continue
      }
      let runEnd = Self.backtickRunEnd(at: cursor, in: region)
      let run = String(region[cursor..<runEnd])
      // The renderer's own match rule: the same run, searched for anywhere
      // later in the region — across line breaks, as a span may wrap a line.
      if let closer = region.range(of: run, range: runEnd..<region.endIndex) {
        appendProse(cursor)
        result += String(region[cursor..<closer.upperBound])
        cursor = closer.upperBound
        proseStart = cursor
      } else {
        // Unterminated span: mid-stream the closing run has not arrived, so
        // the tail is treated as code rather than normalized as prose.
        appendProse(cursor)
        result += String(region[cursor...])
        cursor = region.endIndex
        proseStart = cursor
      }
    }
    appendProse(region.endIndex)
    return result
  }

  private static func backtickRunEnd(at index: String.Index, in text: String) -> String.Index {
    var end = index
    while end < text.endIndex, text[end] == "`" {
      end = text.index(after: end)
    }
    return end
  }

  /// A fence candidate at the start of an already-trimmed line: a run of at
  /// least three backticks or tildes. `bare` records whether nothing but
  /// whitespace follows, which is what a closing fence must be.
  private static func fenceRun(of trimmedLine: String) -> (character: Character, length: Int, bare: Bool)? {
    guard let first = trimmedLine.first, first == "`" || first == "~" else { return nil }
    var length = 0
    for character in trimmedLine {
      guard character == first else { break }
      length += 1
    }
    guard length >= 3 else { return nil }
    let rest = trimmedLine.dropFirst(length)
    let bare = rest.allSatisfy { $0 == " " || $0 == "\t" }
    return (first, length, bare)
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
