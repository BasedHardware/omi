import XCTest

@testable import Omi_Computer

/// Every echo string below was captured live on a named dev bundle with the wake word
/// answering out loud: the microphone heard Omi and ambient capture returned it as the
/// primary speaker. Before this policy, barge-in halted playback on them — three times in
/// one six-turn session, which is why a long answer stopped partway.
final class VoicePlaybackEchoPolicyTests: XCTestCase {
  private func classify(_ transcript: String, spoken: String) -> VoicePlaybackEchoDecision {
    VoicePlaybackEchoPolicy.classify(
      transcript: transcript,
      spokenWords: VoicePlaybackEchoPolicy.words(spoken))
  }

  private func isEcho(_ transcript: String, spoken: String) -> Bool {
    classify(transcript, spoken: spoken) == .drop
  }

  // MARK: - Real echoes

  /// Speech-to-text does not return what the synthesiser was handed: "8:57 PM" came back
  /// as "8 57 p.m." and "August 23" as "August 23rd".
  func testAnswerHeardBackWithTimeAndDateRewrittenIsEcho() {
    XCTAssertTrue(
      isEcho(
        "It's 8 57 p.m. on Sunday, August 23rd, 2026, in India, IST.",
        spoken: "It's 8:57 PM on Sunday, August 23, 2026, in India, IST."))
  }

  func testAnswerHeardBackWithPunctuationRewrittenIsEcho() {
    XCTAssertTrue(
      isEcho(
        "Sure. What would you like to order? And where should it be delivered?",
        spoken: "Sure, what would you like to order, and where should it be delivered?"))
  }

  /// The wake phrase inside the assistant's own answer is the loop this closes: without
  /// it, Omi commands itself with its own words.
  func testAnswerCarryingTheWakePhraseIsEcho() {
    XCTAssertTrue(
      isEcho(
        "Only open my tasks now.",
        spoken: "Omi open my tasks now."))
  }

  /// Ambient capture returns a partial window while the rest is still playing.
  func testPartialAnswerStillPlayingIsEcho() {
    XCTAssertTrue(
      isEcho(
        "I can help, but I need two details first.",
        spoken: "I can help, but I need two details first. 1. Maya's delivery address or saved location."))
  }

  // MARK: - Real speech that must survive

  /// The whole point of barge-in. An interruption shares almost no run of words with what
  /// is playing, so it must reach the policy's callers untouched.
  func testUserInterruptingWithSomethingElseIsNotEcho() {
    XCTAssertFalse(
      isEcho(
        "actually make it Thai instead please",
        spoken: "Sure, what would you like to order, and where should it be delivered?"))
  }

  func testUnrelatedConversationIsNotEcho() {
    XCTAssertFalse(
      isEcho(
        "we should leave for the airport around six tomorrow",
        spoken: "It's 8:57 PM on Sunday, August 23, 2026, in India, IST."))
  }

  /// Nothing has been spoken recently, so nothing can be an echo of it. Guards the
  /// history's expiry: once playback is old enough, the caller passes an empty list.
  func testNothingSpokenRecentlyIsNeverEcho() {
    XCTAssertEqual(
      VoicePlaybackEchoPolicy.classify(
        transcript: "It's 8 57 p.m. on Sunday, August 23rd, 2026.",
        spokenWords: []),
      .keep)
  }

  /// Short utterances are too generic to attribute — "yes" and "okay" appear in the
  /// assistant's speech and in ordinary conversation alike. A false echo deletes
  /// something the user said, so these stay.
  func testShortAcknowledgementIsNotEchoEvenWhenItAppearsInPlayback() {
    XCTAssertFalse(isEcho("okay sure", spoken: "Okay, sure, I can do that for you right now."))
  }

  /// A command the user issues while Omi happens to be speaking similar words must still
  /// get through — the run of shared words is short relative to the utterance.
  func testCommandDuringPlaybackWithIncidentalWordOverlapIsNotEcho() {
    XCTAssertFalse(
      isEcho(
        "order pizza from the place near my office instead",
        spoken: "Sure, what would you like to order, and where should it be delivered?"))
  }

  // MARK: - The user talking over playback

  /// Captured live. While Omi is speaking there is no pause to close the transcription
  /// window on, so the barge-in landed inside the same 9-second window as the answer.
  /// Dropping the segment would eat the interruption — the one utterance that must never
  /// be lost — so the playback is consumed and the user's words survive.
  func testBargeInInsideAPlaybackWindowKeepsOnlyTheUsersWords() {
    XCTAssertEqual(
      classify(
        "1. Ganges Ganga, India's most sacred river, and a vital water source. "
          + "Omi, stop that and tell me the time is.",
        spoken: "1. Ganges (Ganga), India's most sacred river, and a vital water source."),
      .keepResidue("Omi, stop that and tell me the time is."))
  }

  /// The residue is sliced from the original string, not rebuilt from normalized words:
  /// the wake-word parser requires a punctuation break after a homophone, so losing the
  /// comma would silently change whether the command fires.
  func testResiduePreservesPunctuationTheWakeWordParserReads() {
    guard
      case .keepResidue(let residue) = classify(
        "I can help, but I need two details first. Oh me, order pizza from Mumbai instead.",
        spoken: "I can help, but I need two details first.")
    else {
      return XCTFail("expected the user's words to survive")
    }
    XCTAssertEqual(residue, "Oh me, order pizza from Mumbai instead.")
  }

  /// A tail too short to be a command is speech-to-text drift at the window edge, not an
  /// interruption — observed as a trailing "2." while the next item was still playing.
  func testShortTailAfterPlaybackIsStillDropped() {
    XCTAssertEqual(
      classify(
        "1. Mumbai, India's financial capital and home to Bollywood. 2.",
        spoken: "1. Mumbai, India's financial capital and home to Bollywood. 2. Delhi, the national capital."),
      .drop)
  }

  /// Captured live: playback continues past the interruption, so the same sentence
  /// appeared on both sides of the user's words in one window. Both ends are stripped.
  func testPlaybackOnBothSidesOfTheBargeInIsStripped() {
    XCTAssertEqual(
      classify(
        "One. Ganges, Ganga. India's most sacred river. "
          + "Omi, stop that and tell me the time instead. "
          + "One. Ganges, Ganga. India's most sacred river, a vital water source.",
        spoken: "1. Ganges (Ganga), India's most sacred river, a vital water source."),
      .keepResidue("Omi, stop that and tell me the time instead"))
  }

  /// Captured live and initially leaked into the transcript: "9:29 PM" came back as
  /// "929 p.m.", three unmatched tokens in a row two words into the answer, which ended
  /// the forward walk early and left the rest looking like a barge-in. It is not one.
  func testEchoSplitEarlyByMisheardDigitsIsStillDropped() {
    XCTAssertEqual(
      classify(
        "It's 929 p.m. on Sunday, August 23rd, 2026, in India, IST.",
        spoken: "It's 9:29 PM on Sunday, August 23, 2026, in India, IST."),
      .drop)
  }

  // MARK: - Word matching

  /// The synthesiser reads "1." aloud as "one" and speech-to-text writes "One." back, so a
  /// numbered answer would not match itself without this.
  func testSpokenNumbersMatchTheirDigits() {
    XCTAssertEqual(
      VoicePlaybackEchoPolicy.words("One. Ganges. Two. Yamuna."),
      VoicePlaybackEchoPolicy.words("1. Ganges. 2. Yamuna."))
  }

  func testMatchingIgnoresCaseAndPunctuation() {
    XCTAssertEqual(
      VoicePlaybackEchoPolicy.words("It's 8:57 PM, in India!"),
      ["it", "s", "8", "57", "pm", "in", "india"])
  }

  /// Order-preserving: the same words in a different order are not the same sentence.
  func testReorderedWordsDoNotCountAsAFullMatch() {
    XCTAssertFalse(
      isEcho(
        "delivered be should where and order",
        spoken: "and where should it be delivered, what would you like to order"))
  }

  // MARK: - Anchoring and residue plausibility

  /// Captured live: Parakeet returned the same sentence twice in one segment. The second
  /// copy survived as if the user had said it, because the backward walk started at the end
  /// of the playback history instead of at the sentence — Omi had kept talking past it.
  func testRepeatedSentenceInOneSegmentIsEntirelyEcho() {
    XCTAssertEqual(
      classify(
        "Your current save task appears to be testing the protocol product. "
          + "Your current save task appears to be testing the protocol product.",
        spoken: "Your current save task appears to be testing the protocol product, "
          + "including the project."),
      .drop)
  }

  /// Captured live: speech-to-text mangled the tail of a long answer, so it no longer
  /// matched what was synthesised and was kept as the user's words. A garbled continuation
  /// runs straight on from the matched text; a person interrupting starts a new sentence.
  func testGarbledTailOfTheAnswerIsNotMistakenForTheUser() {
    XCTAssertEqual(
      classify(
        "I can't reliably tell how long you've been working because screen recording "
          + "permission isn't enabled. Based on today's recording active for roughly about one hour.",
        spoken: "I can't reliably tell how long you've been working because screen recording "
          + "permission isn't enabled. Based on today's recording we've been active for roughly about one hour."),
      .drop)
  }

  /// The echo can start partway through the history when Omi has been talking a while.
  func testEchoOfALaterSentenceInTheHistoryIsStillMatched() {
    XCTAssertEqual(
      classify(
        "Delhi, the national capital known for historic landmarks.",
        spoken: "1. Mumbai, India's financial capital and home to Bollywood. "
          + "2. Delhi, the national capital known for historic landmarks. "
          + "3. Bengaluru, a major technology and startup hub."),
      .drop)
  }

  /// A barge-in buried between playback on both sides is still recovered.
  func testUserSpeechBetweenTwoStretchesOfPlaybackSurvives() {
    XCTAssertEqual(
      classify(
        "1. Mumbai, India's financial capital and home to Bollywood. "
          + "Omi, stop and tell me the time. "
          + "3. Bengaluru, a major technology and startup hub.",
        spoken: "1. Mumbai, India's financial capital and home to Bollywood. "
          + "2. Delhi, the national capital. 3. Bengaluru, a major technology and startup hub."),
      .keepResidue("Omi, stop and tell me the time"))
  }
}
