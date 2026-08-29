import XCTest

@testable import Omi_Computer

final class WakeWordSegmentParserTests: XCTestCase {
  func testExtractsCommandAfterWakeWord() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "Omi, let's order Maya some food", wakePhrase: "Omi"),
      "let's order Maya some food")
  }

  func testAcceptsCaseAndPunctuationVariants() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "omi, let's order pizza", wakePhrase: "Omi"),
      "let's order pizza")
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Omi let's order pizza", wakePhrase: "omi"),
      "let's order pizza")
  }

  func testBareWakeWordReturnsNil() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi.", wakePhrase: "Omi"))
  }

  func testIgnoresSegmentsWithoutWakeWord() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "We should order pizza", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omiway to the store", wakePhrase: "Omi"))
  }

  func testAcceptsGreetingVariant() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey Omi, order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  func testAcceptsConfiguredGreetingPhrase() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey Omi order pizza", wakePhrase: "hey omi"),
      "order pizza")
  }

  func testEmptyPhraseReturnsNil() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi order pizza", wakePhrase: "  "))
  }

  /// Regression: a live mic session transcribed "Omi, how are you?" as
  /// "Oh me, how are you?" (Parakeet, conf=0.92) and the wake word silently
  /// never fired. STT spells the phrase by sound, so homophones must match.
  func testAcceptsSpeechToTextHomophones() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Oh me, how are you?", wakePhrase: "Omi"),
      "how are you?")
    for rendering in ["Omie", "Omni", "Ohmi", "Oh mi", "Omee", "O me"] {
      XCTAssertEqual(
        WakeWordSegmentParser.command(after: "\(rendering), order pizza", wakePhrase: "Omi"),
        "order pizza",
        "expected \(rendering) to be treated as the wake word")
    }
  }

  /// The backend hardware-transcript scan found `omie` and `omni` in real data.
  /// Greeting-prefixed forms should work even when the recognizer omits punctuation.
  func testAcceptsEvidenceBackedHardwareTranscriptVariants() {
    for rendering in ["Omie", "Omni"] {
      XCTAssertEqual(
        WakeWordSegmentParser.command(
          after: "Hey \(rendering) order pizza", wakePhrase: "Omi"),
        "order pizza",
        "expected Hey \(rendering) to be treated as the wake word")
    }
  }

  /// Review feedback on #11801: with "oh me" accepted as the wake phrase, an ordinary
  /// sentence like "oh me and my friend went hiking" parsed to the 2-word command
  /// "and my friend went hiking" and auto-sent it. The homophones are the recognizer
  /// guessing, and its guesses are ordinary English, so a bare homophone now needs a
  /// punctuation break — the recognizer's own signal that the speaker addressed something
  /// and paused. Every homophone hit observed live carried one.
  func testBareHomophoneInOrdinarySpeechDoesNotFire() {
    for sentence in [
      "oh me and my friend went hiking",
      "o me it has been a long day",
      "oh me I forgot to reply",
      "omie is the spelling in this transcript",
      "omni is a word people use in ordinary speech",
    ] {
      XCTAssertNil(
        WakeWordSegmentParser.command(after: sentence, wakePhrase: "Omi"),
        "expected ordinary speech not to trigger: \(sentence)")
    }
  }

  /// The literal spelling is deliberate — nobody says "Omi" mid-sentence by accident — so
  /// it keeps working without a separator.
  func testLiteralPhraseStillNeedsNoPunctuation() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Omi order food", wakePhrase: "Omi"),
      "order food")
  }

  /// A greeting is corroboration in its own right, so those forms keep the ordinary
  /// word boundary.
  func testGreetingBeforeHomophoneNeedsNoPunctuation() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "hey oh me order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  func testAcceptsGreetingBeforeHomophone() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey oh me, order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  /// The wider match must not swallow ordinary speech: a homophone still needs a
  /// word boundary and a real command behind it.
  func testHomophoneWithoutBoundaryOrCommandIsIgnored() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omnibus schedule changed", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Oh me", wakePhrase: "Omi"))
  }

  // MARK: - The wake phrase later in a multi-sentence segment

  /// Captured live and missed: a literal wake phrase with a valid command, in a segment
  /// that also carried what the user said just before it. Windows now close on the
  /// speaker's pause rather than a fixed boundary, so a segment is no longer one utterance.
  func testWakePhraseOpeningALaterSentenceFires() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "It's not working man. Omi what time it is?", wakePhrase: "Omi"),
      "what time it is?")
  }

  /// The phrase has to *open* an utterance, not merely appear in one.
  func testWakePhraseMidSentenceIsIgnored() {
    XCTAssertNil(
      WakeWordSegmentParser.command(after: "I told Omi to order food", wakePhrase: "Omi"))
  }

  /// The corroboration rules still apply at a later sentence — a bare homophone there
  /// needs its punctuation break exactly as it does at the start.
  func testBareHomophoneOpeningALaterSentenceStillNeedsAPause() {
    XCTAssertNil(
      WakeWordSegmentParser.command(
        after: "That was strange. Oh me and my friend went hiking", wakePhrase: "Omi"))
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "That was strange. Oh me, what time is it?", wakePhrase: "Omi"),
      "what time is it?")
  }

  /// The first sentence that carries a command wins, so an earlier one being ordinary
  /// speech does not consume the utterance.
  func testFirstMatchingSentenceSuppliesTheCommand() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "Nothing here. Omi open my tasks. Omi close my tasks.", wakePhrase: "Omi"),
      "open my tasks. Omi close my tasks.")
  }

  /// Review note from @Git-on-my-level: "ok"/"okay" plus a homophone fired without a pause.
  /// They are discourse markers people open sentences with, unlike the vocative "hey".
  func testOkayDoesNotCorroborateABareHomophone() {
    XCTAssertNil(
      WakeWordSegmentParser.command(
        after: "okay oh me and my friend went hiking", wakePhrase: "Omi"))
    XCTAssertNil(
      WakeWordSegmentParser.command(
        after: "ok oh me and my friend went hiking", wakePhrase: "Omi"))
  }

  /// "hey" still corroborates, and both still corroborate the literal spelling.
  func testHeyStillCorroboratesAHomophoneAndGreetingsStillWorkOnTheLiteralPhrase() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "hey oh me order pizza", wakePhrase: "Omi"),
      "order pizza")
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "okay Omi order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  // MARK: - "Only", the on-device misrendering

  /// The seven live misses this recovers, verbatim from the stored local segments.
  func testOnlyOpeningACommandIsTheWakeWord() {
    let cases = [
      ("Only what is on my calendar.", "what is on my calendar."),
      ("Only how many tasks do I have?", "how many tasks do I have?"),
      ("Only open my rewind timeline.", "open my rewind timeline."),
      ("Only show me my notes.", "show me my notes."),
      ("Only remind me to call David.", "remind me to call David."),
      ("Only search my memories for JD", "search my memories for JD"),
      ("Only what is today's weather?", "what is today's weather?"),
    ]
    for (segment, expected) in cases {
      XCTAssertEqual(
        WakeWordSegmentParser.command(after: segment, wakePhrase: "Omi"), expected,
        "failed for \(segment)")
    }
  }

  /// Ordinary restrictive "only" is followed by what it restricts, never by an
  /// interrogative or a bare imperative. None of these may fire.
  func testOrdinaryOnlyDoesNotFire() {
    let cases = [
      "Only three people came to the meeting.",
      "Only the best ones made it.",
      "Only if you want to.",
      "Only when I say so.",
      "Only where it actually matters.",
      "Only a couple left.",
      "Only my manager knows.",
      "Only about half of them.",
      // Imperatives read naturally under a restriction. A request verb only counts when
      // it is aimed at the speaker's own things.
      "Only do that once.",
      "Only add salt at the end.",
      "Only read the first chapter.",
      "Only tell him if he asks.",
      "Only show the ones that passed.",
      "Only send the final version.",
      "Only open the door for guests.",
    ]
    for segment in cases {
      XCTAssertNil(
        WakeWordSegmentParser.command(after: segment, wakePhrase: "Omi"),
        "fired for \(segment)")
    }
  }

  /// Mid-sentence "only" is not a wake word at any position — the phrase has to open an
  /// utterance, same rule the homophones follow.
  func testMidSentenceOnlyNeverFires() {
    XCTAssertNil(
      WakeWordSegmentParser.command(
        after: "I can only show you what I have.", wakePhrase: "Omi"))
    XCTAssertNil(
      WakeWordSegmentParser.command(
        after: "That's the only thing I want.", wakePhrase: "Omi"))
  }

  /// The rendering opening a later sentence in the same window still counts — windows close
  /// on the speaker's pause, so the command shares the segment with earlier speech.
  func testOnlyOpeningALaterSentenceFires() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "recording active for roughly about one hour. Only show me my notes.",
        wakePhrase: "Omi"),
      "show me my notes.")
  }

  /// A greeting in front is corroboration on its own, so the command-head rule steps aside.
  func testHeyCorroboratesTheRenderingWithoutACommandHead() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "hey only order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  /// The rendering alone carries no command.
  func testBareOnlyIsNotACommand() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Only.", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Only", wakePhrase: "Omi"))
  }
}
