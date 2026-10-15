import XCTest

@testable import Omi_Computer

final class VoiceBargeInPolicyTests: XCTestCase {

  func testUserSpeechInterruptsActivePlayback() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "Wait, stop that",
      isSpeaking: true
    )
    XCTAssertTrue(result)
  }

  func testUserSpeechNoopWhenNotPlaying() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "Hello there",
      isSpeaking: false
    )
    XCTAssertFalse(result)
  }

  func testOtherSpeakerSpeechDoesNotInterrupt() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: false,
      speaker: 1,
      text: "Sure, let's look at the next slide",
      isSpeaking: true
    )
    XCTAssertFalse(result, "Other speakers on a call should not interrupt the user's assistant output")
  }

  func testEmptyOrWhitespaceSpeechDoesNotInterrupt() {
    let emptyResult = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "",
      isSpeaking: true
    )
    XCTAssertFalse(emptyResult)

    let whitespaceResult = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "   \n\t  ",
      isSpeaking: true
    )
    XCTAssertFalse(whitespaceResult)
  }

  func testSpeakerZeroTreatedAsUserEvenIfIsUserFlagFalse() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: false,
      speaker: 0,
      text: "Cancel that order",
      isSpeaking: true
    )
    XCTAssertTrue(result, "Speaker 0 is the primary local user and must be allowed to interrupt")
  }

  // MARK: - Re-delivery is not new speech

  /// The bug this guard exists for, from the live log. A backend segment is re-delivered
  /// as it grows, in place and under one id, and the re-delivery arrives whether or not the
  /// speaker added anything. The second turn of a conversation was cut off 4.4s into
  /// playback by a re-delivery of the very segment that asked the question — byte-identical
  /// to the copy already stored, so nothing had been said.
  func testUnchangedRedeliveryDoesNotInterrupt() {
    let heard = "I'm fine. What about you? Omi, I'm fine. What about you?"
    XCTAssertFalse(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: heard, previouslyHeard: heard, isSpeaking: true))
  }

  /// Growth that adds only punctuation or spacing is the recognizer tidying up, not speech.
  func testRedeliveryAddingOnlyPunctuationDoesNotInterrupt() {
    XCTAssertFalse(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "What about you?", previouslyHeard: "What about you",
        isSpeaking: true))
  }

  /// A real barge-in still interrupts: the segment gained words.
  func testRedeliveryWithNewWordsStillInterrupts() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "What about you? Stop talking.",
        previouslyHeard: "What about you?", isSpeaking: true))
  }

  /// A segment nobody has seen before is new in full.
  func testFirstDeliveryStillInterrupts() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Stop.", previouslyHeard: nil, isSpeaking: true))
  }

  /// A revision that no longer extends what was stored counts as new in full — there is no
  /// way to tell a rewritten prefix from a continuation.
  func testRevisedPrefixCountsAsNewSpeech() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Wait, stop talking.", previouslyHeard: "What about you?",
        isSpeaking: true))
  }

  // MARK: - Omi's own words heard back

  /// Playback as it was synthesised in the live session where the answer stopped after two words.
  private let venusAnswer = VoicePlaybackEchoPolicy.words(
    "Fun fact: A day on Venus is longer than a year on Venus—it rotates so slowly that one "
      + "rotation takes about 243 Earth days, while its orbit takes about 225.")

  /// The live failure: the microphone window closed on the answer's first two words, and
  /// `Fun fact.` stopped the answer it came from.
  func testShortRunOfTheCurrentAnswerDoesNotInterrupt() {
    XCTAssertFalse(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Fun fact.", isSpeaking: true, spokenWords: venusAnswer))
  }

  func testShortRunFromTheMiddleOfTheAnswerDoesNotInterrupt() {
    XCTAssertFalse(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Earth days,", isSpeaking: true, spokenWords: venusAnswer))
  }

  func testShortInterruptionThatIsNotInTheAnswerStillInterrupts() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Stop.", isSpeaking: true, spokenWords: venusAnswer))
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Wait, what?", isSpeaking: true, spokenWords: venusAnswer))
  }

  /// Words the answer contains, but not as a run of it, are the user talking.
  func testAnswerWordsOutOfOrderStillInterrupt() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Venus fact.", isSpeaking: true, spokenWords: venusAnswer))
  }

  /// Four words or more are `VoicePlaybackEchoPolicy.classify`'s call, made before barge-in
  /// runs; this check never widens past what that policy declines to attribute.
  func testFourWordRunIsLeftToTheEchoPolicy() {
    XCTAssertFalse(
      VoicePlaybackEchoPolicy.isShortPlaybackFragment("a day on Venus", spokenWords: venusAnswer))
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "a day on Venus", isSpeaking: true, spokenWords: venusAnswer))
  }

  /// With nothing played recently there is nothing to be an echo of.
  func testShortSpeechWithNoPlaybackHistoryStillInterrupts() {
    XCTAssertTrue(
      VoiceBargeInPolicy.shouldInterrupt(
        isUser: true, speaker: 0, text: "Fun fact.", isSpeaking: true, spokenWords: []))
  }
}
