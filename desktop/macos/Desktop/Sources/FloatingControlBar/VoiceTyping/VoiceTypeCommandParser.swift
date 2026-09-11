import Foundation

/// Decides whether a push-to-talk utterance is a *typing* command — "type <text>" —
/// and extracts the text to be typed.
///
/// The parser runs on partial transcripts too (a mid-hold probe hears the first
/// seconds of the turn), so it is deliberately tri-state. Committing to "not a
/// type command" on a fragment would reject the feature outright (`"Ty"`
/// arrives before `"Type hello"`), and committing to "is a type command" on a
/// bare `"type"` would hijack a turn that turns out to be `"typescript
/// generics, explain them"`. Only a wake word followed by a word boundary, which
/// no longer wake word could still absorb, is decidable.
enum VoiceTypeCommandParser {

  enum Decision: Equatable {
    /// The transcript is still a viable prefix of a type command. Type nothing
    /// yet, but do not route the turn to chat either.
    case undecided
    /// This turn types `payload` instead of asking Omi. `payload` may be empty
    /// while the user has said only the wake word.
    case typing(payload: String)
    /// Not a type command. The turn routes to chat as usual.
    case rejected
  }

  /// Spoken openings that start a typing turn. `"type"` is the documented one;
  /// the others are what ASR reliably returns for the same intent, and they are
  /// matched longest-first so "type out hello" dictates "hello", not "out hello"
  /// — except where `phrasesNeedingInstructionBoundary` says the last word may
  /// belong to the speaker instead.
  static let wakeWords = ["type out", "type this", "type"]

  /// Wake phrases whose last word is also an ordinary first word of dictated
  /// text, so the phrase may only take that word when punctuation — or the end
  /// of the utterance — marks it as the instruction it is.
  ///
  /// "this" is about the commonest word an English sentence opens with, and
  /// nobody speaks the instruction as "type this hello there": they say "type
  /// this: hello there", or just "type hello there". Taking it on a plain
  /// space turned "type this is a test" into "Is a test" — the speaker's own
  /// first word deleted, silently, inside their text. "type out" is not in
  /// this set because it *is* spoken straight through ("type out an email"),
  /// and dictation rarely opens on "out".
  private static let phrasesNeedingInstructionBoundary: Set<String> = ["type this"]

  /// Punctuation ASR attaches to the wake word ("Type, hello") or that opens the
  /// dictated text. Stripped from the front of the payload, never from its body.
  private static let separators = CharacterSet(charactersIn: " \t\n,:;.-–—")

  /// The subset of `separators` that marks the end of a spoken instruction
  /// rather than an ordinary gap between words: the pause or colon a speaker
  /// puts after "type this". A space is not one.
  private static let instructionBoundary = CharacterSet(charactersIn: ",:;.-–—")

  /// Whether what follows a wake phrase marks the phrase as an instruction:
  /// punctuation, once any spaces are skipped, or nothing left to dictate.
  private static func opensAnInstruction(_ rest: Substring) -> Bool {
    let afterSpaces = rest.drop(while: { $0 == " " || $0 == "\t" })
    guard let first = afterSpaces.unicodeScalars.first else { return true }
    return instructionBoundary.contains(first)
  }

  static func decide(_ transcript: String) -> Decision {
    let trimmed = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .undecided }
    let lowered = trimmed.lowercased()

    // A transcript that is still a prefix of any wake word decides nothing yet.
    // This covers both the first fragments ("ty") and the ambiguous overlap
    // between wake words ("type o" may still become "type out"), so a longer
    // wake word is never stolen by a shorter one mid-stream.
    if wakeWords.contains(where: { $0.hasPrefix(lowered) }) {
      return .undecided
    }

    for wake in wakeWords.sorted(by: { $0.count > $1.count }) {
      guard trimmed.prefix(wake.count).lowercased() == wake else { continue }
      let rest = String(trimmed.dropFirst(wake.count))
      guard let first = rest.unicodeScalars.first, separators.contains(first) else {
        // "typescript", "typing", "typed" — the wake word is only a prefix of a
        // longer word, so this was never a command.
        continue
      }
      // A phrase that would swallow an ordinary opening word needs the speaker
      // to have marked it as an instruction. Falling through leaves the word to
      // the shorter wake word's payload: "type this is a test" is "type" plus
      // "this is a test", not "type this" plus "is a test".
      if phrasesNeedingInstructionBoundary.contains(wake), !opensAnInstruction(rest[...]) { continue }
      let payload = String(
        rest.drop(while: { $0.unicodeScalars.allSatisfy(separators.contains) })
      )
      return .typing(payload: capitalizingFirstWord(payload))
    }
    return .rejected
  }

  /// Spellings a recognizer gives the spoken word "type" when it does not hear
  /// it as "type". Consulted only once the turn is already known to dictate.
  private static let wakeWordMishearings = [
    "typed", "types", "typing", "tie", "tied", "tight", "tape", "typo", "tap", "two",
  ]

  /// The subset of mishearings safe to claim a dictation from *mid-hold*, before
  /// the whole utterance is known. Excludes the ones that are also ordinary
  /// words ("typing", "types", "typo", "two") — "typing is broken" and "two plus
  /// two" are real questions, not dictations — so an early claim on them cannot
  /// hijack a spoken query. Closing `payloadAssumingDictation` can still drop
  /// a leading "two" once the turn is already claimed.
  private static let probeClaimMishearings = ["typed", "tie", "tied", "tight", "tape", "tap"]

  /// Whether the opening of a still-growing transcript plausibly begins a
  /// dictation — the documented wake word, or a close mishearing of it.
  ///
  /// The mid-hold probe decodes the first seconds of the hold with the
  /// on-device model, which regularly mishears "type" from a short clip with
  /// no preceding context ("Two", "Tie", "Typed"). `decide` is deliberately
  /// strict and rejects those, so the turn was never recognised as a dictation
  /// *during* the hold and the notch never turned red until the key came up.
  /// This matcher is the looser test used only to claim the turn early: a
  /// leading mishearing followed by a word boundary and at least one more
  /// word. A real question rarely opens with one of these tokens, and the
  /// closing decode still governs the pasted text.
  static func opensLikeDictation(_ transcript: String) -> Bool {
    if case .typing = decide(transcript) { return true }
    let trimmed = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    let lowered = trimmed.lowercased()

    // The exact wake word followed by a separator — a pause ("Type.") or a
    // space ("Type hello") — claims the instant it is heard, before the next
    // word, so the notch turns red immediately. The separator is what tells
    // the wake word apart from a longer word that merely starts with it
    // ("typescript" has no separator after "type", so it never claims).
    for token in wakeWords.sorted(by: { $0.count > $1.count }) where lowered.hasPrefix(token) {
      let rest = lowered.dropFirst(token.count)
      if let first = rest.unicodeScalars.first, separators.contains(first) { return true }
    }

    // A close mishearing of "type" claims only with a following word — more
    // evidence, because the on-device model produces these from a short clip
    // and some are near ordinary words.
    for token in probeClaimMishearings.sorted(by: { $0.count > $1.count }) where lowered.hasPrefix(token) {
      let rest = trimmed.dropFirst(token.count)
      guard let first = rest.unicodeScalars.first, separators.contains(first) else { continue }
      let payload = rest.drop(while: { $0.unicodeScalars.allSatisfy(separators.contains) })
      if !payload.isEmpty { return true }
    }
    return false
  }

  /// The text to type from a transcript of a turn that is already known to be
  /// a dictation.
  ///
  /// The closing transcript comes from a stronger recognizer than the probe
  /// that claimed the turn, and it may render the wake word another way. When
  /// the strict parse fails, a leading word that reads as a mishearing of
  /// "type" is dropped; failing that, the whole transcript is the dictation.
  /// One stray word at the front is recoverable; a dictation that never
  /// arrives is not.
  static func payloadAssumingDictation(_ transcript: String) -> String {
    if case .typing(let payload) = decide(transcript) { return payload }
    let trimmed = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    let separatorClass = "[\\s,:;.\\-–—]*"
    // Boundary-requiring phrases are deliberately absent: `decide` has already
    // settled them, and this looser pass must not take back the opening word it
    // decided to keep.
    let openings = wakeWords.filter { !phrasesNeedingInstructionBoundary.contains($0) } + wakeWordMishearings
    let alternatives = openings.map(NSRegularExpression.escapedPattern(for:))
    let pattern = "^(?i)(?:" + alternatives.joined(separator: "|") + ")\\b" + separatorClass
    if let range = trimmed.range(of: pattern, options: .regularExpression) {
      return capitalizingFirstWord(String(trimmed[range.upperBound...]))
    }
    return capitalizingFirstWord(trimmed)
  }

  /// Dictation starts a sentence. The recognizer lowercases the first word
  /// because it heard it mid-utterance, right after the wake word, so it is
  /// restored here.
  static func capitalizingFirstWord(_ payload: String) -> String {
    guard let first = payload.first, first.isLowercase else { return payload }
    return payload.prefix(1).uppercased() + payload.dropFirst()
  }
}
