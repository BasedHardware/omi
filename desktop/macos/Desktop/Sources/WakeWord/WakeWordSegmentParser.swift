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

  /// Speech-to-text spells the wake word by sound, not by brand. "Omi" is
  /// acoustically "oh-mee", so recognizers routinely emit "oh me", "omni", or
  /// "ohmi" instead. Matching only the literal spelling makes the wake word fail
  /// for reasons the user cannot see or correct, so known renderings are accepted
  /// as the same phrase. Downstream guards (user speech only, 2+ word command,
  /// cooldown, dedup) still bound the false-positive cost of the wider match.
  static let sttHomophones: [String: [String]] = [
    "omi": ["oh me", "ohmi", "omni", "oh mi", "omee", "o me", "oh-me"]
  ]

  static func candidatePhrases(for phrase: String) -> [String] {
    var phrases: [String] = []
    for base in [phrase] + (sttHomophones[phrase] ?? []) {
      phrases.append(base)
      for greeting in ["hey", "ok", "okay"] {
        phrases.append("\(greeting) \(base)")
      }
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
