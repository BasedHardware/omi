import Foundation

/// Stylometric features of how the user texts one specific contact, computed
/// algorithmically from the real message history (never inferred by an LLM).
/// These drive three things:
///   1. a "measured style" card injected into the clone's system prompt,
///   2. deterministic candidate scoring when the clone generates multiple replies,
///   3. honest constraints (length/burst/punctuation) grounded in real distributions.
struct StyleFeatures: Codable, Sendable {
  var sampleCount: Int = 0

  // Per-bubble length distribution (words).
  var wordP25: Int = 1
  var wordP50: Int = 4
  var wordP75: Int = 8
  var wordP90: Int = 12

  // Burst (consecutive from-me bubbles per reply turn) distribution, index 1...6 (6 = "6+").
  // Values are fractions of all reply turns.
  var burstShare: [Double] = [0, 0, 0, 0, 0, 0, 0]

  // Casing / punctuation rates over from-me bubbles (0–1).
  var lowercaseStartRate: Double = 0
  var uppercaseStartRate: Double = 0
  var terminalPeriodRate: Double = 0
  var questionMarkRate: Double = 0
  var exclamationRate: Double = 0
  var allCapsRate: Double = 0

  // Emoji habits.
  var emojiBubbleRate: Double = 0
  var topEmoji: [String] = []

  // Vocabulary fingerprint: distinctive tokens (stopwords removed) with counts.
  var characteristicTokens: [(token: String, count: Int)] {
    get { zip(tokenNames, tokenCounts).map { ($0, $1) } }
    set {
      tokenNames = newValue.map(\.token)
      tokenCounts = newValue.map(\.count)
    }
  }
  private var tokenNames: [String] = []
  private var tokenCounts: [Int] = []

  private enum CodingKeys: String, CodingKey {
    case sampleCount, wordP25, wordP50, wordP75, wordP90, burstShare
    case lowercaseStartRate, uppercaseStartRate, terminalPeriodRate
    case questionMarkRate, exclamationRate, allCapsRate
    case emojiBubbleRate, topEmoji, tokenNames, tokenCounts
  }
}

enum AICloneStyleAnalyzer {

  /// Words too common in English to characterize anyone's voice.
  private static let stopwords: Set<String> = [
    "i", "a", "the", "to", "and", "it", "is", "in", "on", "of", "for", "that", "this",
    "was", "are", "be", "we", "he", "she", "they", "you", "me", "my", "at", "so", "do",
    "if", "or", "as", "an", "but", "not", "no", "yes", "have", "has", "had", "his",
    "her", "with", "what", "when", "how", "who", "why", "where", "can", "will", "just",
    "get", "got", "did", "does", "im", "its", "were", "there", "then", "them", "than",
    "from", "your", "our", "out", "all", "one", "some", "him", "her", "up", "down",
    "about", "would", "could", "should", "s", "t", "m", "re", "ll", "d", "ve", "dont",
    "didnt", "cant", "go", "going", "know", "like", "think", "want", "make", "made",
    "been", "being", "am", "us", "now", "too", "also", "more", "much", "very",
  ]

  private static let emojiPattern = try! NSRegularExpression(
    pattern:
      "[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{27BF}\\x{2190}-\\x{21FF}\\x{2B00}-\\x{2BFF}\\x{FE0F}\\x{2764}]"
  )

  /// Extract features from a contact's full (chronological or not) message history.
  static func extract(from messages: [ImportedMessage]) -> StyleFeatures {
    let chronological = messages.count > 1 && messages.first!.date > messages.last!.date
      ? Array(messages.reversed()) : messages
    let mine = chronological.filter { $0.isFromMe && $0.text != "[attachment]" }
    var features = StyleFeatures()
    features.sampleCount = mine.count
    guard mine.count >= 20 else { return features }

    // Length percentiles.
    let wordCounts = mine.map { wordCount($0.text) }.sorted()
    func pct(_ p: Double) -> Int { wordCounts[min(wordCounts.count - 1, Int(Double(wordCounts.count) * p))] }
    features.wordP25 = pct(0.25)
    features.wordP50 = pct(0.50)
    features.wordP75 = pct(0.75)
    features.wordP90 = pct(0.90)

    // Burst distribution over reply runs.
    var runs: [Int] = []
    var current = 0
    for message in chronological {
      if message.isFromMe {
        current += 1
      } else if current > 0 {
        runs.append(current)
        current = 0
      }
    }
    if current > 0 { runs.append(current) }
    if !runs.isEmpty {
      var share = [Double](repeating: 0, count: 7)
      for run in runs { share[min(run, 6)] += 1 }
      features.burstShare = share.map { $0 / Double(runs.count) }
    }

    // Casing / punctuation.
    let n = Double(mine.count)
    var lowerStart = 0
    var upperStart = 0
    var endPeriod = 0
    var hasQuestion = 0
    var hasExclamation = 0
    var allCaps = 0
    for message in mine {
      let text = message.text
      if text.first?.isLowercase == true { lowerStart += 1 }
      if text.first?.isUppercase == true { upperStart += 1 }
      if text.hasSuffix(".") && text.count > 2 { endPeriod += 1 }
      if text.contains("?") { hasQuestion += 1 }
      if text.contains("!") { hasExclamation += 1 }
      if text.count > 2, text == text.uppercased(),
        text.rangeOfCharacter(from: .letters) != nil
      {
        allCaps += 1
      }
    }
    features.lowercaseStartRate = Double(lowerStart) / n
    features.uppercaseStartRate = Double(upperStart) / n
    features.terminalPeriodRate = Double(endPeriod) / n
    features.questionMarkRate = Double(hasQuestion) / n
    features.exclamationRate = Double(hasExclamation) / n
    features.allCapsRate = Double(allCaps) / n

    // Emoji.
    var emojiCounts: [String: Int] = [:]
    var bubblesWithEmoji = 0
    for message in mine {
      let found = emojiMatches(in: message.text)
      if !found.isEmpty { bubblesWithEmoji += 1 }
      for e in found where e != "\u{FE0F}" { emojiCounts[e, default: 0] += 1 }
    }
    features.emojiBubbleRate = Double(bubblesWithEmoji) / n
    features.topEmoji = emojiCounts.sorted { $0.value > $1.value }.prefix(5).map(\.key)

    // Vocabulary fingerprint.
    var tokenCounts: [String: Int] = [:]
    for message in mine {
      for token in tokens(in: message.text) where !stopwords.contains(token) {
        tokenCounts[token, default: 0] += 1
      }
    }
    features.characteristicTokens = tokenCounts
      .filter { $0.value >= 4 && $0.key.count <= 12 }
      .sorted { $0.value > $1.value }
      .prefix(18)
      .map { ($0.key, $0.value) }

    return features
  }

  // MARK: - Style card (prompt block)

  /// Render the measured features as a compact prompt block. Every number is computed
  /// from real data, so the model gets ground truth instead of its own impressions.
  static func renderStyleCard(_ f: StyleFeatures, contactName: String) -> String {
    guard f.sampleCount >= 20 else { return "" }
    let pctf: (Double) -> String = { "\(Int(($0 * 100).rounded()))%" }

    let burst1 = pctf(f.burstShare[1])
    let burst2 = pctf(f.burstShare[2])
    let burst3plus = pctf(f.burstShare[3...].reduce(0, +))
    let multiShare = f.burstShare.count > 1 ? 1 - f.burstShare[1] : 0

    let emojiLine: String
    if f.emojiBubbleRate < 0.01 {
      emojiLine = "Emoji: almost never (\(pctf(f.emojiBubbleRate)) of messages). Do not use emoji."
    } else {
      emojiLine =
        "Emoji: in \(pctf(f.emojiBubbleRate)) of messages — rare. When used, it is "
        + f.topEmoji.prefix(3).joined(separator: " ") + " (never any other)."
    }

    let vocab = f.characteristicTokens.prefix(14).map { "\($0.token)" }.joined(separator: ", ")

    return """
      MEASURED STYLE — computed from \(f.sampleCount) of your real messages to \(contactName). \
      These are hard statistical facts about how you text; every reply must fit them:
      - Message length: median \(f.wordP50) words per message (25th pct \(f.wordP25), 75th \(f.wordP75), \
      90th \(f.wordP90)). Keep messages SHORT — a message longer than \(max(f.wordP90 + 4, 12)) words \
      is out of character.
      - Splitting into separate messages: \(burst1) of your replies are a single message, \(burst2) are \
      two messages, \(burst3plus) are three or more. \(multiShare > 0.5 ? "Splitting a reply into several short messages is your NORM." : "You usually answer in one message.")
      - First character casing: \(pctf(f.lowercaseStartRate)) of your messages start lowercase, \
      \(pctf(f.uppercaseStartRate)) uppercase (phone auto-caps). Mix accordingly; lowercase dominates.
      - Punctuation: only \(pctf(f.terminalPeriodRate)) of messages end with a period — almost never end \
      with "." Questions get a "?" only \(pctf(f.questionMarkRate)) of the time — usually you ask \
      questions with no question mark. "!" appears in \(pctf(f.exclamationRate)) of messages.
      - \(emojiLine)
      - Words you actually use often here: \(vocab)
      """
  }

  // MARK: - Deterministic candidate scoring

  /// Score how well `bubbles` (one candidate reply, one string per message bubble)
  /// fits the measured distributions. 0…1, higher = more in-style. This is a shape
  /// check (length, casing, punctuation, emoji, burst) — semantic fit is the LLM's job.
  static func styleScore(bubbles: [String], features f: StyleFeatures) -> Double {
    guard !bubbles.isEmpty, f.sampleCount >= 20 else { return 0.5 }
    var score = 1.0

    // Length: penalize bubbles beyond the 90th percentile (scaled by how far).
    for bubble in bubbles {
      let words = wordCount(bubble)
      if words > f.wordP90 {
        score -= min(0.25, Double(words - f.wordP90) * 0.02)
      }
    }
    // Reply-total length sanity: total words shouldn't dwarf a typical turn.
    let total = bubbles.reduce(0) { $0 + wordCount($1) }
    let typicalTurn = max(f.wordP50 * 3, f.wordP90 + 6)
    if total > typicalTurn * 2 { score -= 0.2 }

    // Burst-count likelihood: probability of this burst size, scaled.
    let burstIndex = min(bubbles.count, 6)
    let burstProbability = f.burstShare.indices.contains(burstIndex) ? f.burstShare[burstIndex] : 0
    if burstProbability < 0.03 { score -= 0.2 } else if burstProbability < 0.10 { score -= 0.08 }

    // Terminal periods.
    if f.terminalPeriodRate < 0.10 {
      let withPeriod = bubbles.filter { $0.hasSuffix(".") && $0.count > 2 }.count
      score -= Double(withPeriod) * 0.12
    }

    // Casing: compare uppercase-start share to measured.
    let upperStarts = Double(bubbles.filter { $0.first?.isUppercase == true }.count)
    let upperShare = upperStarts / Double(bubbles.count)
    if f.lowercaseStartRate > 0.55 && upperShare > 0.67 { score -= 0.12 }

    // Emoji: using emoji when the person basically never does, or foreign emoji.
    let usedEmoji = bubbles.flatMap { emojiMatches(in: $0) }.filter { $0 != "\u{FE0F}" }
    if !usedEmoji.isEmpty {
      if f.emojiBubbleRate < 0.01 {
        score -= 0.2
      } else if !usedEmoji.allSatisfy({ f.topEmoji.contains($0) }) {
        score -= 0.1
      }
    }

    // Small bonus for using this person's characteristic vocabulary (capped).
    let vocabulary = Set(f.characteristicTokens.prefix(14).map(\.token))
    let usedVocabulary = Set(bubbles.flatMap { tokens(in: $0) }).intersection(vocabulary)
    score += min(0.08, Double(usedVocabulary.count) * 0.03)

    return max(0, min(1, score))
  }

  // MARK: - Helpers

  private static func wordCount(_ text: String) -> Int {
    text.split { $0.isWhitespace }.count
  }

  private static func tokens(in text: String) -> [String] {
    text.lowercased()
      .components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty && Int($0) == nil }
  }

  private static func emojiMatches(in text: String) -> [String] {
    let range = NSRange(text.startIndex..., in: text)
    return emojiPattern.matches(in: text, range: range).compactMap {
      Range($0.range, in: text).map { String(text[$0]) }
    }
  }
}
