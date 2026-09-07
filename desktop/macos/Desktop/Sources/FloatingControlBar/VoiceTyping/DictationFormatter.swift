import Foundation

/// The deterministic half of turning a transcript into text worth pasting.
///
/// This runs on every dictation, online or not, and it is deliberately
/// conservative: it removes only what is never wanted in written text (spoken
/// fillers) and repairs what removing them leaves behind (doubled spaces,
/// stranded commas, a lowercase first word). Everything that needs judgement —
/// self-corrections, spoken formatting commands, how a number or an email
/// address is written — belongs to `DictationPolisher`, which can be skipped
/// when there is no network without leaving the text broken.
enum DictationFormatter {

  /// Fillers that are fillers in any language the recognizer returns.
  private static let universalFillers = ["um", "umm", "uhm", "uh", "uhh"]
  /// Fillers that are only fillers in English: "er" is a German pronoun, "ah"
  /// opens sentences in several languages, so these are stripped only when
  /// the transcript is known to be English.
  /// "mm" is deliberately absent: it is a unit ("10 mm") far more often than
  /// it is a transcribed murmur.
  private static let englishFillers = ["er", "erm", "ehm", "hmm", "mhm"]

  static func format(_ text: String, language: String = "en") -> String {
    var result = text.replacingOccurrences(of: "\r\n", with: "\n")
    result = removingFillers(result, language: language)
    result = normalizingWhitespace(result)
    result = VoiceTypeCommandParser.capitalizingFirstWord(result)
    return result
  }

  static func fillers(for language: String) -> [String] {
    let base = language.lowercased().split(separator: "-").first.map(String.init) ?? language.lowercased()
    return base == "en" ? universalFillers + englishFillers : universalFillers
  }

  /// A filler is only a filler when it stands alone as a spoken token: not a
  /// piece of an address ("john@um.com"), a hyphenated word ("uh-huh"), or a
  /// path. These are the characters that glue a token to its neighbours.
  private static let glue = "[\\w'@.\\-/]"

  private static func removingFillers(_ text: String, language: String) -> String {
    let words = fillers(for: language).map(NSRegularExpression.escapedPattern(for:)).joined(separator: "|")
    guard !words.isEmpty else { return text }
    var result = text
    // ", um." at a sentence boundary: the filler and its comma go, the
    // sentence punctuation the recognizer hung on the filler is kept.
    result = result.replacingOccurrences(
      of: "(?i),\\s*\\b(?:\(words))\\b([.!?])(?=\\s|$)", with: "$1", options: .regularExpression)
    // ", um, " between two clauses: the filler and one of its commas go, the
    // clause boundary stays.
    result = result.replacingOccurrences(
      of: "(?i),\\s*\\b(?:\(words))\\b,?(?=\\s|$)", with: ",", options: .regularExpression)
    // A filler that closes a sentence ("hello uh.") goes, but the full stop
    // it was hung on is the sentence's, and stays.
    result = result.replacingOccurrences(
      of: "(?i)(?<=\\S)\\s+(?:\(words))(?=[.!?](?:\\s|$))", with: "", options: .regularExpression)
    // A standalone filler anywhere else goes with the comma or full stop the
    // recognizer hung on it ("Um, hello" → "hello").
    result = result.replacingOccurrences(
      of: "(?i)(?<!\(glue))(?:\(words))(?:[,.](?=\\s|$)|(?=\\s|$))\\s*", with: "", options: .regularExpression)
    return result
  }

  private static func normalizingWhitespace(_ text: String) -> String {
    var result = text
    // Spaces before punctuation, doubled punctuation from a removed filler.
    result = result.replacingOccurrences(of: "\\s+([,.;:!?])", with: "$1", options: .regularExpression)
    result = result.replacingOccurrences(of: ",\\s*,", with: ",", options: .regularExpression)
    result = result.replacingOccurrences(of: "[ \\t]{2,}", with: " ", options: .regularExpression)
    // A line that now opens with the comma a filler left behind.
    result = result.replacingOccurrences(of: "(^|\\n)[ \\t]*[,;:]\\s*", with: "$1", options: .regularExpression)
    result = result.replacingOccurrences(of: "[ \\t]+\\n", with: "\n", options: .regularExpression)
    result = result.replacingOccurrences(of: "\\n[ \\t]+", with: "\n", options: .regularExpression)
    return result.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
