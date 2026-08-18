import Foundation

enum WakeWordSegmentParser {
  static func command(after segmentText: String, wakePhrase: String) -> String? {
    let phrase = configuredPhrase(wakePhrase)
    guard !phrase.isEmpty else { return nil }
    let raw = dropLeadingPunctuationAndWhitespace(segmentText)
    let normalized = normalize(raw)
    for candidate in candidatePhrases(for: phrase) where normalized.hasPrefix(candidate) {
      guard hasWordBoundary(after: candidate, in: normalized) else { continue }
      guard
        let commandEnd = raw.index(
          raw.startIndex, offsetBy: candidate.count, limitedBy: raw.endIndex)
      else { continue }
      let remainder = String(raw[commandEnd...])
      let command = dropLeadingPunctuationAndWhitespace(remainder)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !command.isEmpty else { continue }
      return command
    }
    return nil
  }

  static func configuredPhrase(_ raw: String) -> String {
    normalize(raw).trimmingCharacters(in: .punctuationCharacters.union(.whitespacesAndNewlines))
  }

  static func candidatePhrases(for phrase: String) -> [String] {
    var phrases = [phrase]
    for greeting in ["hey", "ok", "okay"] {
      phrases.append("\(greeting) \(phrase)")
    }
    return phrases
  }

  private static func normalize(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }

  private static func dropLeadingPunctuationAndWhitespace(_ value: String) -> String {
    var index = value.startIndex
    while index < value.endIndex {
      guard let scalar = value[index].unicodeScalars.first else { break }
      guard
        CharacterSet.punctuationCharacters.contains(scalar)
          || CharacterSet.whitespacesAndNewlines.contains(scalar)
      else { break }
      index = value.index(after: index)
    }
    return String(value[index...])
  }

  private static func hasWordBoundary(after prefix: String, in text: String) -> Bool {
    guard
      let boundaryIndex = text.index(
        text.startIndex, offsetBy: prefix.count, limitedBy: text.endIndex)
    else { return false }
    guard boundaryIndex < text.endIndex else { return true }
    let next = text[boundaryIndex]
    return !next.isLetter && !next.isNumber
  }
}
