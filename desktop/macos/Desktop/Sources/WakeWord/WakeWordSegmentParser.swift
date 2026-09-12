import Foundation

enum WakeWordSegmentParser {
  static func command(after segmentText: String, wakePhrase: String) -> String? {
    let phrase = configuredPhrase(wakePhrase)
    guard !phrase.isEmpty else { return nil }
    let candidates = self.candidates(for: phrase)
    for sentence in sentences(in: segmentText) {
      if let command = self.command(startingAt: sentence, candidates: candidates) {
        return command
      }
    }
    return nil
  }

  private static func command(startingAt text: String, candidates: [Candidate]) -> String? {
    let raw = dropLeadingPunctuationAndWhitespace(text)
    let normalized = normalize(raw)
    for candidate in candidates where normalized.hasPrefix(candidate.text) {
      guard
        hasBoundary(
          after: candidate.text,
          in: normalized,
          requiringPunctuation: candidate.corroboration == .punctuationBreak)
      else { continue }
      guard
        let commandEnd = raw.index(
          raw.startIndex, offsetBy: candidate.text.count, limitedBy: raw.endIndex)
      else { continue }
      let remainder = String(raw[commandEnd...])
      let command = dropLeadingPunctuationAndWhitespace(remainder)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !command.isEmpty else { continue }
      if candidate.corroboration == .commandHead, !opensLikeACommand(command) { continue }
      return command
    }
    return nil
  }

  /// Whether what follows the phrase is addressed to an assistant rather than continuing a
  /// sentence.
  ///
  /// This is the whole safety story for `.commandHead` renderings. "Only" is an ordinary
  /// English adverb, so the word itself proves nothing and the thing said after it has to.
  ///
  /// Two shapes qualify. An interrogative, because restrictive "only" needs something to
  /// restrict and a question word cannot be it — "Only what is on my calendar" is not a
  /// sentence a person completes. Or a request verb aimed at the speaker's own things
  /// ("show me", "open my", "remind me"), because that is the part restrictive "only"
  /// cannot reach: every imperative reads fine under a restriction — "only do that once",
  /// "only tell him if he asks", "only show the ones that passed" — but none of them are
  /// asking for the speaker's own calendar or notes.
  ///
  /// "when" and "where" are deliberately absent from the interrogatives: "only when I say
  /// so" and "only where it matters" are ordinary restrictive uses.
  static let interrogativeHeads: Set<String> = [
    "what", "what's", "whats", "how", "how's", "hows", "who", "who's", "whos", "why",
    "which", "whose", "is", "are", "was", "were", "does", "did", "can", "could", "will",
    "would", "should", "am",
  ]

  /// Request verbs, which only count when the next word is `me` or `my`.
  static let requestHeads: Set<String> = [
    "open", "show", "tell", "give", "find", "search", "remind", "read", "send", "play",
    "summarize", "summarise", "explain", "schedule", "check", "list", "add", "set",
  ]

  /// The words that make a request verb self-addressed.
  static let selfAddressedObjects: Set<String> = ["me", "my", "mine"]

  static func opensLikeACommand(_ command: String) -> Bool {
    let words = normalize(command)
      .split(whereSeparator: { $0.isWhitespace })
      .map { $0.trimmingCharacters(in: .punctuationCharacters) }
    guard let head = words.first else { return false }
    if interrogativeHeads.contains(head) { return true }
    guard requestHeads.contains(head), words.count > 1 else { return false }
    return selfAddressedObjects.contains(words[1])
  }

  /// The segment text, then each sentence inside it that a wake word could open.
  ///
  /// A segment is no longer one utterance. Windows now close on the speaker's pause rather
  /// than a fixed boundary, so whatever was said in the same breath shares the window with
  /// the command — observed live, `It's not working man. Omi what time it is?` carried a
  /// literal wake phrase and a valid command and matched nothing, because matching only
  /// looked at the start of the segment.
  ///
  /// A sentence boundary, not any position: the phrase has to *open* an utterance. That is
  /// the same class of evidence the punctuation-break rule already relies on — the
  /// recognizer's own sentence segmentation — and it keeps `I told Omi to order food` from
  /// parsing to the command "to order food".
  static func sentences(in text: String) -> [String] {
    var result: [String] = [text]
    var index = text.startIndex
    while index < text.endIndex {
      defer { index = text.index(after: index) }
      guard text[index] == "." || text[index] == "?" || text[index] == "!" else { continue }
      let next = text.index(after: index)
      guard next < text.endIndex, text[next].isWhitespace else { continue }
      let remainder = String(text[next...])
      if !dropLeadingPunctuationAndWhitespace(remainder).isEmpty {
        result.append(remainder)
      }
    }
    return result
  }

  static func configuredPhrase(_ raw: String) -> String {
    normalize(raw).trimmingCharacters(in: .punctuationCharacters.union(.whitespacesAndNewlines))
  }

  /// Speech-to-text spells the wake word by sound, not by brand. The backend's
  /// read-only scan of 25,329 real transcript segments found "omie" and "omni"
  /// alongside "omi"; desktop live runs also observed split and aspirated forms.
  /// Matching only the literal spelling makes the wake word fail for reasons the
  /// user cannot see or correct, so measured renderings are accepted as the same
  /// phrase. Downstream guards (user speech only, 2+ word command, cooldown,
  /// dedup) still bound the false-positive cost of the wider match.
  static let sttHomophones: [String: [String]] = [
    "omi": [
      // Shared with backend EVIDENCE_BACKED_WAKE_WORD_VARIANTS.
      "omie", "omni",
      // Additional renderings observed during desktop microphone testing.
      "oh me", "ohmi", "oh mi", "omee", "o me", "oh-me",
      // On-device recognition has no keyword list, so it also fronts the vowel
      // with an aspirate ("Homi what's the weather?", observed live). Deliberately
      // excludes "homie": it is an ordinary English word, and accepting it as the
      // wake phrase would fire on real speech.
      "homi", "hommi",
    ]
  ]

  /// Renderings that are ordinary English words, and therefore need the *next* word as
  /// evidence rather than a punctuation break.
  ///
  /// "Only" is the single biggest on-device miss: across a 20-utterance battery on the
  /// on-device lane, the phrase was usable in 12, and 7 of the 8 misses came back as
  /// "Only". The cloud lane does not produce it — `/v4/listen` prepends "Omi" to the STT
  /// keyword vocabulary server-side (`backend/utils/listen_session_bootstrap.py`), and the
  /// on-device manager has no equivalent (see `STTSessionState.resolveMode`). So this is
  /// the only thing that raises recognition on the default path.
  ///
  /// It cannot ride the punctuation-break rule: a scan of 1,919 stored local segments found
  /// 15 sentence-initial "Only", every one of them a misrendered wake word, and *not one*
  /// carried a break after it — they read "Only what is on my calendar", "Only open my
  /// rewind timeline". The same scan found 8 ordinary uses of "only", all mid-sentence,
  /// none sentence-initial. Hence `.commandHead`: sentence position plus an assistant-shaped
  /// next word, which is what actually separates the two populations.
  static let commandShapedRenderings: [String: [String]] = [
    "omi": ["only"]
  ]

  /// What a phrase needs beyond itself before it counts as the wake word.
  enum Corroboration: Equatable {
    /// The phrase is its own evidence — nobody says "Omi" mid-conversation by accident.
    case none
    /// A punctuation break must follow: the recognizer's own signal that the speaker
    /// addressed something and then paused.
    case punctuationBreak
    /// The remainder must open like a command. For renderings that are ordinary English
    /// words, the phrase proves nothing and the thing said after it has to.
    case commandHead
  }

  /// A phrase that may open a wake-word utterance, and how much corroboration it needs.
  struct Candidate: Equatable {
    let text: String
    let corroboration: Corroboration
  }

  /// The literal spelling is a deliberate act: nobody says "Omi" mid-sentence by accident,
  /// so `"Omi order food"` needs no further evidence. A homophone is the recognizer
  /// guessing, and the guesses are ordinary English — `"oh me and my friend went hiking"`
  /// would otherwise parse to the command "and my friend went hiking" and auto-send it.
  ///
  /// A bare homophone therefore has to be followed by a punctuation break, which is the
  /// recognizer's own signal that the speaker addressed something and then paused. Every
  /// homophone hit observed live carried one ("Oh me, how are you?"). A greeting prefix is
  /// corroboration in its own right — "hey oh me" is not something a person says by
  /// accident — so those forms keep the ordinary word boundary.
  static func candidates(for phrase: String) -> [Candidate] {
    var result: [Candidate] = [Candidate(text: phrase, corroboration: .none)]
    for greeting in ["hey", "ok", "okay"] {
      result.append(Candidate(text: "\(greeting) \(phrase)", corroboration: .none))
    }
    for homophone in sttHomophones[phrase] ?? [] {
      result.append(Candidate(text: homophone, corroboration: .punctuationBreak))
      // Only "hey" corroborates a homophone. It is a vocative — "hey <name>" addresses
      // someone, and nobody produces it before a misheard word by accident. "ok" and
      // "okay" are discourse markers people open sentences with constantly, so
      // "okay oh me and my friend went hiking" would have fired with the command
      // "and my friend went hiking". They still corroborate the literal spelling above,
      // where the phrase itself is already the evidence.
      result.append(Candidate(text: "hey \(homophone)", corroboration: .none))
    }
    for rendering in commandShapedRenderings[phrase] ?? [] {
      result.append(Candidate(text: rendering, corroboration: .commandHead))
      // A greeting in front is already corroboration, same as for the homophones above.
      result.append(Candidate(text: "hey \(rendering)", corroboration: .none))
    }
    return result
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

  private static func hasBoundary(
    after prefix: String,
    in text: String,
    requiringPunctuation: Bool
  ) -> Bool {
    guard
      let boundaryIndex = text.index(
        text.startIndex, offsetBy: prefix.count, limitedBy: text.endIndex)
    else { return false }
    // A phrase at the very end carries no command, so the caller rejects it either way.
    guard boundaryIndex < text.endIndex else { return true }
    let next = text[boundaryIndex]
    if requiringPunctuation {
      return next.isPunctuation
    }
    return !next.isLetter && !next.isNumber
  }
}
