import Foundation

enum WakeWordSegmentParser {
  static func command(after segmentText: String, wakePhrase: String) -> String? {
    let phrase = configuredPhrase(wakePhrase)
    guard !phrase.isEmpty else { return nil }
    let raw = dropLeadingPunctuationAndWhitespace(segmentText)
    let normalized = normalize(raw)
    for candidate in candidates(for: phrase) where normalized.hasPrefix(candidate.text) {
      guard
        hasBoundary(
          after: candidate.text,
          in: normalized,
          requiringPunctuation: candidate.requiresPunctuationBreak)
      else { continue }
      guard
        let commandEnd = raw.index(
          raw.startIndex, offsetBy: candidate.text.count, limitedBy: raw.endIndex)
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
      // wake phrase would fire on real speech. The fix for on-device misses is
      // keyword boosting on the recognizer, not a longer list here.
      "homi", "hommi",
    ]
  ]

  /// A phrase that may open a wake-word utterance, and how much corroboration it needs.
  struct Candidate: Equatable {
    let text: String
    /// Whether a punctuation break must follow the phrase for it to count.
    let requiresPunctuationBreak: Bool
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
    var result: [Candidate] = [Candidate(text: phrase, requiresPunctuationBreak: false)]
    for greeting in ["hey", "ok", "okay"] {
      result.append(Candidate(text: "\(greeting) \(phrase)", requiresPunctuationBreak: false))
    }
    for homophone in sttHomophones[phrase] ?? [] {
      result.append(Candidate(text: homophone, requiresPunctuationBreak: true))
      for greeting in ["hey", "ok", "okay"] {
        result.append(
          Candidate(text: "\(greeting) \(homophone)", requiresPunctuationBreak: false))
      }
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
