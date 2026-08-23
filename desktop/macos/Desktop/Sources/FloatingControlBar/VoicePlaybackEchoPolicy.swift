import Foundation

enum VoicePlaybackEchoDecision: Equatable {
  /// Nothing to do with playback — ordinary speech.
  case keep
  /// Entirely the assistant's own voice.
  case drop
  /// Playback with the user talking over the end of it. Carries the user's words alone.
  case keepResidue(String)
}

/// Pure policy separating the assistant's own spoken output — heard back through the
/// microphone — from what a person actually said.
///
/// Omi speaks into a room Omi is also recording. Ambient capture returns the playback as a
/// transcript segment attributed to the primary speaker; observed live,
/// `Transcript [ADD] Speaker 0: It's 8 57 p.m. on Sunday...` was Omi, not a person. Four
/// consumers then act on it as if the user had spoken: barge-in halts the very playback
/// that produced it (three times in one six-turn session, which is why a long answer stops
/// partway), the wake word can be commanded by an answer carrying the wake phrase, and the
/// conversation record and memory extraction gain speech nobody said.
///
/// Dropping the whole segment is not enough. While Omi is talking there is no pause to
/// close the transcription window on, so a barge-in lands *inside* the same window as the
/// playback — measured: `1. Ganges Ganga, India's most sacred river, and a vital water
/// source. Omi, stop that and tell me the time is.` One 9-second window, two speakers.
/// Discarding it would eat the interruption, which is the one utterance that must never be
/// lost. So the match is consumed as a prefix and whatever the user said after it survives.
///
/// A prefix rather than a scattered match because that is the physical situation: the user
/// starts talking after Omi has already been talking. It is also far safer — deleting
/// matched words wherever they occur would shred an interruption against the common words
/// ("the", "and", "a") in several sentences of playback history.
///
/// Errs toward *not* echo throughout. A missed echo costs what the app already does today;
/// a false echo deletes something the user said.
enum VoicePlaybackEchoPolicy {
  /// Below this, an utterance is too generic to attribute. "Yes", "okay" and "sure" all
  /// appear in the assistant's own speech and in ordinary conversation. Applied to the
  /// matched run and to the surviving residue alike.
  static let minimumWordCount = 4

  /// Share of an utterance the matched run must cover before the whole thing is discarded.
  /// Measured on captured echoes: 0.80–1.00.
  static let minimumCoverageToDrop = 0.8

  /// How far ahead in the playback history a word may be found and still continue the run.
  /// Absorbs words speech-to-text drops or splits — "8:57 PM" came back as "8 57 p.m."
  static let alignmentLookahead = 5

  /// Consecutive unmatched words that end the run.
  ///
  /// Four, not fewer, because speech-to-text produces mismatch runs *inside* an echo as
  /// well as at its edge: "9:29 PM" came back as "929 p.m.", three unmatched tokens two
  /// words into the answer. At three the walk stopped there and the rest of Omi's own
  /// sentence read as a barge-in and reached the transcript. Raising it is close to free —
  /// unmatched words never advance the split point, so the user's words are kept whether
  /// the walk stops at them or scans past them.
  static let mismatchesEndingEcho = 4

  static func classify(transcript: String, spokenWords: [String]) -> VoicePlaybackEchoDecision {
    let tokens = self.tokens(transcript)
    guard !tokens.isEmpty, !spokenWords.isEmpty else { return .keep }
    let incoming = tokens.map(\.word)

    let leading = matchedPrefixLength(incoming, against: spokenWords)
    guard leading >= minimumWordCount else { return .keep }
    guard tokens.count - leading >= minimumWordCount else {
      // Discarding the whole segment needs the match to actually account for the whole
      // segment. Several sentences of playback history contain enough ordinary words that
      // a short utterance can align with four of them by chance — live, "Sorry, my mistake
      // it's taking" was deleted that way, which is the failure this policy must never
      // have. A real echo covers essentially all of itself: measured 0.80–1.00.
      return Double(leading) / Double(tokens.count) >= minimumCoverageToDrop ? .drop : .keep
    }

    // Playback continues past the interruption, so it bookends the user's words as often
    // as it precedes them — measured, the same sentence appeared on both sides of a
    // barge-in in one window. Strip the far end the same way.
    let remaining = Array(incoming[leading...])
    let trailing = matchedPrefixLength(remaining.reversed(), against: spokenWords.reversed())
    let end = tokens.count - trailing
    guard end - leading >= minimumWordCount else { return .drop }

    // Nothing stripped from the far end means the utterance ends where the segment does,
    // so keep its closing punctuation — the wake-word parser reads punctuation.
    let upperBound = trailing == 0 ? transcript.endIndex : tokens[end - 1].end
    return .keepResidue(String(transcript[tokens[leading].start..<upperBound]))
  }

  static func words(_ text: String) -> [String] {
    tokens(text).map(\.word)
  }

  /// Normalized words paired with their bounds in the original string, so a residue can be
  /// sliced out with its original casing and punctuation intact. The wake-word parser reads
  /// punctuation, so rebuilding from normalized words would change whether a command fires.
  private static func tokens(_ text: String) -> [(word: String, start: String.Index, end: String.Index)] {
    var result: [(String, String.Index, String.Index)] = []
    var index = text.startIndex
    var wordStart: String.Index?
    while index < text.endIndex {
      let character = text[index]
      if character.isLetter || character.isNumber {
        if wordStart == nil { wordStart = index }
      } else if let start = wordStart {
        result.append((normalize(text[start..<index]), start, index))
        wordStart = nil
      }
      index = text.index(after: index)
    }
    if let start = wordStart {
      result.append((normalize(text[start..<text.endIndex]), start, text.endIndex))
    }
    return result
  }

  /// The synthesiser reads digits aloud and speech-to-text writes them back as words, so
  /// the same numbered list is "1." going out and "One." coming back. Unifying them keeps
  /// a numbered answer — the common shape for anything Omi lists — matchable.
  private static let spokenNumbers: [String: String] = {
    let names = [
      "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
      "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
      "nineteen", "twenty",
    ]
    var map: [String: String] = [:]
    for (value, name) in names.enumerated() { map[name] = String(value) }
    return map
  }()

  private static func normalize(_ word: Substring) -> String {
    let lowered = word.lowercased()
    return spokenNumbers[lowered] ?? lowered
  }

  /// How many leading words of `incoming` are accounted for by `spoken`, scanning forward
  /// only. Returns the length up to — not including — the run of mismatches that ended it.
  /// Called with both sequences reversed to measure a trailing run instead.
  private static func matchedPrefixLength<S: Sequence<String>>(
    _ incoming: S,
    against spoken: S
  ) -> Int {
    matchedPrefixLength(Array(incoming), against: Array(spoken))
  }

  private static func matchedPrefixLength(_ incoming: [String], against spoken: [String]) -> Int {
    var spokenIndex = 0
    var mismatches = 0
    var lastMatched = 0
    for (offset, word) in incoming.enumerated() {
      let limit = min(spokenIndex + alignmentLookahead, spoken.count)
      if spokenIndex < limit, let hit = (spokenIndex..<limit).first(where: { spoken[$0] == word }) {
        spokenIndex = hit + 1
        mismatches = 0
        lastMatched = offset + 1
        continue
      }
      mismatches += 1
      if mismatches >= mismatchesEndingEcho { break }
    }
    return lastMatched
  }
}
