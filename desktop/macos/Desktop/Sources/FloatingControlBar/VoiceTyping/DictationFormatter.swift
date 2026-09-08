import Foundation

/// The deterministic half of turning a transcript into text worth pasting.
///
/// This runs on every dictation, online or not, and it is deliberately
/// conservative: it removes only what is never wanted in written text (spoken
/// fillers) and repairs what removing them leaves behind (doubled spaces,
/// stranded commas) or what a recognizer never wrote in the first place (a
/// capital at the start of each sentence, the pronoun "I"). Everything that
/// needs judgement —
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
    result = capitalizingSentenceStarts(result)
    if capitalizesPronounI(language: language, text: result) {
      result = capitalizingPronounI(result)
    }
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

  // MARK: - Capitalization

  /// Observed live: the backend's batch recognizer returned a whole dictation
  /// in lowercase ("first of all, i'm typing right now and i think this will
  /// work."), and with the polisher unavailable that is what was pasted. The
  /// polisher fixes case when it runs; these two rules make the text right
  /// when it does not.

  /// A capital after each sentence end. Only ". ", "! " and "? " count, and a
  /// full stop only when what precedes it is a word rather than an initial
  /// ("J. smith"), an abbreviation ("dr. smith", "e.g. this"), or the rest
  /// of an ellipsis ("wait... maybe"). A word already capitalized is left as
  /// heard. Line breaks alone do not start a sentence: a dictated "new line"
  /// may continue a list item.
  static func capitalizingSentenceStarts(_ text: String) -> String {
    var chars = Array(text)
    var word = ""
    var previous: Character?
    var sentenceEnded = false
    var spaceSeen = false
    for index in chars.indices {
      let char = chars[index]
      defer { previous = char }
      if char.isLetter || char.isNumber {
        if sentenceEnded && spaceSeen && char.isLowercase {
          let upper = String(char).uppercased()
          if upper.count == 1, let first = upper.first { chars[index] = first }
        }
        sentenceEnded = false
        spaceSeen = false
        word.append(char)
      } else if char == "." {
        sentenceEnded = endsSentence(word: word, previous: previous)
        spaceSeen = false
        word = ""
      } else if char == "!" || char == "?" {
        sentenceEnded = true
        spaceSeen = false
        word = ""
      } else if char.isWhitespace || char.isNewline {
        if sentenceEnded { spaceSeen = true }
        word = ""
      } else if char == "'" || char == "’" {
        // Inside a word ("don't"): the word goes on.
        word.append(char)
      } else if char == "," || char == ";" || char == ":" {
        sentenceEnded = false
        word = ""
      } else {
        // Quotes, brackets, dashes: neither end a sentence nor cancel one
        // that just ended ("she said \"no.\" then left").
        word = ""
      }
    }
    return String(chars)
  }

  /// Tokens a full stop belongs to rather than ends.
  private static let abbreviations: Set<String> = [
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "inc", "ltd", "approx", "dept",
  ]

  private static func endsSentence(word: String, previous: Character?) -> Bool {
    guard let previous, previous != "." else { return false }
    let lowered = word.lowercased()
    // A lone letter is an initial or half of "e.g." — except "i", which is a
    // word that ends sentences all the time ("so do i. so does he").
    if lowered.count == 1, let only = lowered.first, only.isLetter, lowered != "i" { return false }
    return !abbreviations.contains(lowered)
  }

  /// The pronoun "i" and its contractions ("i'm", "i've", "i'll", "i'd") as a
  /// standalone word. Not a letter glued into an address, a path, a hyphenated
  /// word, or "i.e.", and not a list marker "(i)".
  static func capitalizingPronounI(_ text: String) -> String {
    text.replacingOccurrences(
      of: "(?<![\\w'’@./\\-])i(?=(?:['’](?:m|ve|ll|d))?(?:[,;:!?]|\\.(?!\\w))?(?:\\s|$))",
      with: "I", options: .regularExpression)
  }

  /// English is the only language in which a lone "i" is the pronoun: in
  /// Italian it is an article ("i ragazzi"), in Catalan "and". When the
  /// transcription language is "multi" the text itself has to look English.
  static func capitalizesPronounI(language: String, text: String) -> Bool {
    let base = language.lowercased().split(separator: "-").first.map(String.init) ?? language.lowercased()
    if base == "en" { return true }
    return base == "multi" && looksEnglish(text)
  }

  /// Function words that do not occur as words in the other languages the
  /// recognizer commonly returns; two of them is enough to call a text English.
  private static let englishMarkers: Set<String> = [
    "the", "and", "is", "are", "was", "were", "you", "that", "this", "have", "has", "with", "not",
    "will", "would", "can", "think", "just", "get", "got", "gonna", "let's", "we", "they", "my",
    "your", "it", "of", "to", "i'm", "i've", "i'll", "i'd", "don't", "it's", "what", "there",
  ]

  static func looksEnglish(_ text: String) -> Bool {
    var hits = 0
    let tokens = text.lowercased().replacingOccurrences(of: "’", with: "'")
      .split(whereSeparator: { !$0.isLetter && $0 != "'" })
    for token in tokens where englishMarkers.contains(String(token)) {
      hits += 1
      if hits >= 2 { return true }
    }
    return false
  }
}
