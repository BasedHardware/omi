import Foundation

/// Client-side copy of W1 §1.7. Pure: same input, same title; the only clock
/// is `startedAt`. This is the fail-closed result when no local engine can run.
/// Overview stays empty — never a fabricated summary that looks like content.
struct DeterministicConversationMinimum: Sendable, Equatable, Codable {
  var title: String
  var overview: String
  var category: String
  var processingState: String

  static let emptyOverview = ""
  static let requiredCategory = "other"
  static let terminalProcessingState = "none"
  static let titleCharacterBudget = 60

  static func make(from input: DeterministicMinimumInput) -> DeterministicConversationMinimum {
    DeterministicConversationMinimum(
      title: Self.title(from: input),
      overview: emptyOverview,
      category: requiredCategory,
      processingState: terminalProcessingState
    )
  }

  static func title(from input: DeterministicMinimumInput) -> String {
    let sentence = firstNonEmptySentence(input.transcript)
    if sentence.isEmpty {
      return fallbackTitle(sourceLabel: input.sourceLabel, startedAt: input.startedAt, timeZone: input.timeZone)
    }
    return truncateToWordBoundary(sentence, maxCharacters: titleCharacterBudget)
  }
}

struct DeterministicMinimumInput: Sendable, Equatable {
  var transcript: String
  var startedAt: Date
  var sourceLabel: String
  var timeZone: TimeZone

  init(
    transcript: String,
    startedAt: Date,
    sourceLabel: String = "Recording",
    timeZone: TimeZone = .current
  ) {
    self.transcript = transcript
    self.startedAt = startedAt
    self.sourceLabel = sourceLabel
    self.timeZone = timeZone
  }
}

private func firstNonEmptySentence(_ transcript: String) -> String {
  let collapsed =
    transcript
    .replacingOccurrences(of: "\r\n", with: "\n")
    .components(separatedBy: .newlines)
    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    .filter { !$0.isEmpty }
    .joined(separator: " ")
  guard !collapsed.isEmpty else { return "" }

  var sentence = ""
  for character in collapsed {
    sentence.append(character)
    if character == "." || character == "!" || character == "?" {
      break
    }
  }
  return sentence.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func truncateToWordBoundary(_ text: String, maxCharacters: Int) -> String {
  if text.count <= maxCharacters { return text }
  let end = text.index(text.startIndex, offsetBy: maxCharacters)
  let prefix = String(text[..<end])
  guard let lastSpace = prefix.lastIndex(of: " "), lastSpace > prefix.startIndex else {
    return prefix
  }
  return String(prefix[..<lastSpace]).trimmingCharacters(in: .whitespaces)
}

private func fallbackTitle(sourceLabel: String, startedAt: Date, timeZone: TimeZone) -> String {
  let formatter = DateFormatter()
  formatter.locale = Locale(identifier: "en_US_POSIX")
  formatter.timeZone = timeZone
  formatter.dateFormat = "h:mm a"
  let label = sourceLabel.trimmingCharacters(in: .whitespacesAndNewlines)
  let source = label.isEmpty ? "Recording" : label
  return "\(source) · \(formatter.string(from: startedAt))"
}
