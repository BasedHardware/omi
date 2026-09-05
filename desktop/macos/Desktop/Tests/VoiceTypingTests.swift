import XCTest

@testable import Omi_Computer

final class VoiceTypeCommandParserTests: XCTestCase {

  func testWakeWordFollowedByTextDictatesTheRemainder() {
    XCTAssertEqual(
      VoiceTypeCommandParser.decide("Type hello world"),
      .typing(payload: "Hello world"))
    XCTAssertEqual(
      VoiceTypeCommandParser.decide("type, hello world"),
      .typing(payload: "Hello world"))
    XCTAssertEqual(
      VoiceTypeCommandParser.decide("Type: meeting notes for Q3."),
      .typing(payload: "Meeting notes for Q3."))
  }

  func testDictatedTextOpensWithACapital() {
    // Dictation starts a sentence; the recognizer hears the first word mid-utterance
    // and lowercases it.
    XCTAssertEqual(VoiceTypeCommandParser.decide("type hello"), .typing(payload: "Hello"))
    // An already-capitalized word (a name) is left exactly as heard.
    XCTAssertEqual(VoiceTypeCommandParser.decide("type Nathan is here"), .typing(payload: "Nathan is here"))
  }

  func testGrowingPrefixOfTheWakeWordIsUndecided() {
    // A mid-hold probe hears only the opening of the turn. Its fragments must
    // not be rejected as chat, or the turn is routed before the user has
    // finished the first word.
    for fragment in ["T", "Ty", "typ", "type", "type o", "Type th"] {
      XCTAssertEqual(
        VoiceTypeCommandParser.decide(fragment), .undecided,
        "\(fragment) should still be undecided")
    }
  }

  func testWakeWordAsAPrefixOfALongerWordIsNotACommand() {
    // The regression this guards: "type" inside an ordinary question hijacking
    // the turn and dictating the question into the user's editor.
    XCTAssertEqual(VoiceTypeCommandParser.decide("typescript generics, explain"), .rejected)
    XCTAssertEqual(VoiceTypeCommandParser.decide("typing indicator is broken"), .rejected)
    XCTAssertEqual(VoiceTypeCommandParser.decide("what type of bird is this"), .rejected)
  }

  func testLongerWakeWordWinsOverItsOwnPrefix() {
    XCTAssertEqual(
      VoiceTypeCommandParser.decide("type out the address"),
      .typing(payload: "The address"))
    XCTAssertEqual(
      VoiceTypeCommandParser.decide("type this: buy milk"),
      .typing(payload: "Buy milk"))
  }

  func testAClaimedTurnReadsAMisheardWakeWordLeniently() {
    // The closing transcript comes from a stronger recognizer than the probe
    // that claimed the turn, and it may spell the wake word its own way.
    // Losing the whole dictation over that would be far worse than one stray
    // word, so a leading mishearing is dropped.
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("Type hello world"), "Hello world")
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("Tie, hello world"), "Hello world")
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("Typed hello"), "Hello")
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("tape - send it"), "Send it")
  }

  func testAProbeMishearingOfTheWakeWordStillOpensLikeDictation() {
    // The on-device probe mishears "type" from a short opening clip. These are
    // the misses observed live; each must claim the turn mid-hold so the notch
    // turns red while talking, not only at key-up.
    for opening in ["Tie, hello world", "Typed the report", "tape - send it"] {
      XCTAssertTrue(VoiceTypeCommandParser.opensLikeDictation(opening), "\(opening) should open like a dictation")
    }
  }

  func testAWakeWordFollowedByAPauseClaimsInstantlyWithoutANextWord() {
    // "Type." the instant it is heard, before the next word, so the dots turn
    // red immediately. A separator (pause or space) after the wake word is the
    // signal.
    // The exact wake word claims on the pause alone.
    for opening in ["Type.", "Type,", "type: hello"] {
      XCTAssertTrue(VoiceTypeCommandParser.opensLikeDictation(opening), "\(opening) should claim instantly")
    }
    // A mishearing still needs the next word (it is weaker evidence).
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("Two."))
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("Two. Okay"))
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("Two plus two"))
  }

  func testOpensLikeDictationDoesNotClaimAnOrdinaryQuestionOrPrefixWord() {
    // No separator after the wake token → a longer word that merely starts
    // with it, never a claim.
    for opening in [
      "what is on my calendar", "tell me a joke", "typescript generics", "typing is broken", "hello there",
    ] {
      XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation(opening), "\(opening) must not open like a dictation")
    }
    // A bare token still growing (no separator yet) waits.
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("Type"))
    XCTAssertTrue(VoiceTypeCommandParser.opensLikeDictation("Type hello"))
    // Real words that happen to be mishearings never claim mid-hold.
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("types of birds"))
    XCTAssertFalse(VoiceTypeCommandParser.opensLikeDictation("typo in the file"))
  }

  func testAClaimedTurnWithNoWakeWordAtAllKeepsEveryWord() {
    // No mishearing to drop: the whole transcript is the dictation. A word
    // that merely begins with the wake word is never cut in half.
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("hello world"), "Hello world")
    XCTAssertEqual(VoiceTypeCommandParser.payloadAssumingDictation("typescript rocks"), "Typescript rocks")
  }
}

@MainActor
final class VoiceTypeSessionTests: XCTestCase {

  private final class RecordingSink: TextInsertionSink {
    var pasted: [String] = []
    var copied: [String] = []
    var pasteSucceeds = true
    var caretAfterWord = false
    var focus: String? = "1:com.example.editor"

    func paste(_ text: String) -> Bool {
      guard pasteSucceeds else { return false }
      pasted.append(text)
      return true
    }
    func copy(_ text: String) { copied.append(text) }
    func caretNeedsSeparatingSpace() -> Bool { caretAfterWord }
    func focusTarget() -> String? { focus }
  }

  private func makeSession(trusted: Bool = true) -> (VoiceTypeSession, RecordingSink) {
    let sink = RecordingSink()
    let session = VoiceTypeSession(sink: sink, isAccessibilityTrusted: { trusted })
    session.begin()
    session.noteRelease()
    return (session, sink)
  }

  func testAClosingTranscriptThatOpensWithTheWakeWordIsPastedWhole() {
    let (session, sink) = makeSession()
    XCTAssertEqual(session.payload(from: "Type hello world."), "Hello world.")
    XCTAssertTrue(session.claimsTurn)
    XCTAssertEqual(session.deliver("Hello world."), .pasted("Hello world."))
    XCTAssertEqual(sink.pasted, ["Hello world."])
    XCTAssertTrue(sink.copied.isEmpty)
    XCTAssertFalse(session.claimsTurn, "delivery ends the turn")
  }

  func testAQuestionIsLeftToChatAndNothingIsPasted() {
    let (session, sink) = makeSession()
    XCTAssertNil(session.payload(from: "what's on my calendar tomorrow"))
    XCTAssertFalse(session.claimsTurn)
    XCTAssertEqual(session.deliver("what's on my calendar tomorrow"), .none)
    XCTAssertTrue(sink.pasted.isEmpty)
    XCTAssertTrue(sink.copied.isEmpty)
  }

  func testAProbeClaimLatchesAndTheClosingTranscriptIsReadLeniently() {
    // The mid-hold probe heard the wake word; the closing transcript, from the
    // backend, spelled it differently. The turn stays a dictation and the
    // stray word is dropped rather than pasted.
    let (session, sink) = makeSession()
    XCTAssertTrue(session.claim(transcript: "Type hello wor"))
    XCTAssertEqual(session.payload(from: "Tie, hello world, how are you?"), "Hello world, how are you?")
    XCTAssertEqual(session.deliver("Hello world, how are you?"), .pasted("Hello world, how are you?"))
    XCTAssertEqual(sink.pasted, ["Hello world, how are you?"])
  }

  func testALenientClaimLatchesOnAMisheardWakeWordButStrictDoesNot() {
    let (strict, _) = makeSession()
    XCTAssertFalse(strict.claim(transcript: "Tie, hello world"), "strict claim rejects a mishearing")
    let (lenient, _) = makeSession()
    XCTAssertTrue(lenient.claim(transcript: "Tie, hello world", lenient: true))
    XCTAssertTrue(lenient.claimsTurn)
    // The closing transcript then strips the misheard token from the paste.
    XCTAssertEqual(lenient.payload(from: "Tie, hello world"), "Hello world")
  }

  func testAProbeThatHearsAQuestionDoesNotLatch() {
    // Not-typing never latches: the probe heard two seconds of an utterance
    // the user had barely started, and the closing transcript still decides.
    let (session, _) = makeSession()
    XCTAssertFalse(session.claim(transcript: "what is the weather"))
    XCTAssertFalse(session.claimsTurn)
    XCTAssertEqual(session.payload(from: "Type hello"), "Hello")
  }

  func testWithoutAccessibilityTheTurnIsReleasedToChat() {
    let (session, sink) = makeSession(trusted: false)
    XCTAssertFalse(session.claim(transcript: "Type hello"))
    XCTAssertNil(session.payload(from: "Type hello again"), "one denied turn stays denied")
    XCTAssertEqual(session.deliver("Hello"), .none)
    XCTAssertTrue(sink.pasted.isEmpty)
  }

  func testADictationThatContinuesALineOpensWithASpace() {
    let (session, sink) = makeSession()
    sink.caretAfterWord = true
    XCTAssertNotNil(session.payload(from: "Type I think so"))
    // The space is on screen but not part of what the turn dictated.
    XCTAssertEqual(session.deliver("I think so"), .pasted("I think so"))
    XCTAssertEqual(sink.pasted, [" I think so"])
  }

  func testTheSeparatingSpaceFollowsWordsAndClosingPunctuationOnly() {
    // Continuing a line: after a word, or after the punctuation that ended
    // one. Never after whitespace or something that opens what follows — a
    // rule on all non-whitespace put "( hello" and "\" hello" on screen.
    for character: Character in ["a", "Z", "9", "é", ".", ",", "?", ")", "”", "%"] {
      XCTAssertTrue(PasteboardTextInsertionSink.needsSeparatingSpace(after: character), "after \(character)")
    }
    for character: Character in [" ", "\n", "\t", "(", "[", "\"", "“", "/", "-", "@", "_"] {
      XCTAssertFalse(PasteboardTextInsertionSink.needsSeparatingSpace(after: character), "after \(character)")
    }
  }

  func testADictationAtALineStartAddsNoSpace() {
    let (session, sink) = makeSession()
    sink.caretAfterWord = false
    XCTAssertNotNil(session.payload(from: "Type hello"))
    _ = session.deliver("Hello")
    XCTAssertEqual(sink.pasted, ["Hello"])
  }

  func testFocusThatMovedAfterReleaseCopiesInsteadOfPasting() {
    // Observed live before this existed: a dock click brought Omi's own window
    // forward and the dictation landed in it instead of the document.
    let (session, sink) = makeSession()
    XCTAssertNotNil(session.payload(from: "Type hello world"))
    sink.focus = "2:com.omi.desktop-dev"
    XCTAssertEqual(session.deliver("Hello world"), .copied("Hello world"))
    XCTAssertTrue(sink.pasted.isEmpty)
    XCTAssertEqual(sink.copied, ["Hello world"])
  }

  func testAnUnreadableFocusAtReleaseStillPastes() {
    let sink = RecordingSink()
    sink.focus = nil
    let session = VoiceTypeSession(sink: sink, isAccessibilityTrusted: { true })
    session.begin()
    session.noteRelease()
    XCTAssertNotNil(session.payload(from: "Type hello"))
    XCTAssertEqual(session.deliver("Hello"), .pasted("Hello"))
    XCTAssertEqual(sink.pasted, ["Hello"])
  }

  func testFocusThatBecameUnreadableAfterReleaseCopies() {
    let (session, sink) = makeSession()
    XCTAssertNotNil(session.payload(from: "Type hello"))
    sink.focus = nil
    XCTAssertEqual(session.deliver("Hello"), .copied("Hello"))
    XCTAssertTrue(sink.pasted.isEmpty)
    XCTAssertEqual(sink.copied, ["Hello"])
  }

  func testAFailedPasteFallsBackToTheClipboard() {
    let (session, sink) = makeSession()
    sink.pasteSucceeds = false
    XCTAssertNotNil(session.payload(from: "Type hello"))
    XCTAssertEqual(session.deliver("Hello"), .copied("Hello"))
    XCTAssertEqual(sink.copied, ["Hello"])
  }

  func testEmptyTextDeliversNothing() {
    let (session, sink) = makeSession()
    XCTAssertEqual(session.payload(from: "Type."), "")
    XCTAssertEqual(session.deliver("   "), .none)
    XCTAssertTrue(sink.pasted.isEmpty)
    XCTAssertTrue(sink.copied.isEmpty)
  }

  func testTextWithNothingInItDeliversNothing() {
    // A breath decoded as "." or "…" is not a dictation: nothing is pasted
    // and nothing is left on the clipboard.
    for text in [".", "…", ", ,", "?!"] {
      let (session, sink) = makeSession()
      XCTAssertNotNil(session.payload(from: "Type hello"))
      XCTAssertEqual(session.deliver(text), .none, text)
      XCTAssertTrue(sink.pasted.isEmpty)
      XCTAssertTrue(sink.copied.isEmpty)
    }
  }

  func testANewTurnForgetsThePreviousClaim() {
    let (session, sink) = makeSession()
    XCTAssertTrue(session.claim(transcript: "Type hello"))
    session.begin()
    XCTAssertFalse(session.claimsTurn)
    XCTAssertEqual(session.deliver("Hello"), .none)
    XCTAssertTrue(sink.pasted.isEmpty)
  }

  func testAbandonEndsTheTurnWithoutDelivering() {
    let (session, sink) = makeSession()
    XCTAssertTrue(session.claim(transcript: "Type hello"))
    session.abandon()
    XCTAssertFalse(session.claimsTurn)
    XCTAssertEqual(session.deliver("Hello"), .none)
    XCTAssertTrue(sink.pasted.isEmpty)
  }
}

final class DictationFormatterTests: XCTestCase {

  func testFillersAreRemovedWithThePunctuationHungOnThem() {
    XCTAssertEqual(DictationFormatter.format("Um, hello there"), "Hello there")
    XCTAssertEqual(DictationFormatter.format("so uh yeah, that works."), "So yeah, that works.")
    XCTAssertEqual(DictationFormatter.format("I think, um, we should go"), "I think, we should go")
    XCTAssertEqual(DictationFormatter.format("hello uh."), "Hello.")
  }

  func testWordsThatMerelyContainAFillerAreKept() {
    XCTAssertEqual(
      DictationFormatter.format("the hummer and the umbrella"),
      "The hummer and the umbrella")
  }

  func testAFillerSpellingInsideStructuredTextIsNotAFiller() {
    // Only a standalone spoken token is a filler: not a piece of an address,
    // a hyphenated word, a unit, or a path.
    XCTAssertEqual(DictationFormatter.format("mail john@um.com today"), "Mail john@um.com today")
    XCTAssertEqual(DictationFormatter.format("she said uh-huh and left"), "She said uh-huh and left")
    XCTAssertEqual(DictationFormatter.format("the bolt is 10 mm long"), "The bolt is 10 mm long")
    XCTAssertEqual(DictationFormatter.format("open /tmp/um/notes"), "Open /tmp/um/notes")
  }

  func testAFillerAtASentenceBoundaryKeepsTheSentencePunctuation() {
    // ", um." carried the full stop: the filler goes, the sentence still ends.
    XCTAssertEqual(DictationFormatter.format("I think, um. Next point"), "I think. Next point")
    XCTAssertEqual(DictationFormatter.format("really, uh? Sure"), "Really? Sure")
    XCTAssertEqual(DictationFormatter.format("Um. Hello there"), "Hello there")
  }

  func testEnglishOnlyFillersAreKeptInOtherLanguages() {
    // "er" is a German pronoun; stripping it would rewrite the sentence.
    XCTAssertEqual(DictationFormatter.format("er kommt morgen", language: "de"), "Er kommt morgen")
    XCTAssertEqual(DictationFormatter.format("er, it works", language: "en"), "It works")
    // Universal fillers still go.
    XCTAssertEqual(DictationFormatter.format("um, er kommt", language: "de"), "Er kommt")
  }

  func testWhitespaceAndStrandedPunctuationAreRepaired() {
    XCTAssertEqual(DictationFormatter.format("hello ,  world ."), "Hello, world.")
    XCTAssertEqual(DictationFormatter.format("  hello   world  "), "Hello world")
  }

  func testLineBreaksSurvive() {
    XCTAssertEqual(DictationFormatter.format("line one \n line two"), "Line one\nline two")
  }

  func testNamesKeepTheirCapitalsAndEmptyStaysEmpty() {
    XCTAssertEqual(DictationFormatter.format("Nathan is here"), "Nathan is here")
    XCTAssertEqual(DictationFormatter.format("   "), "")
  }
}

final class DictationPolisherTests: XCTestCase {

  func testACleanRewriteIsAccepted() {
    XCTAssertEqual(
      DictationPolisher.accept(
        "Let's meet at 4pm tomorrow to go over the Q3 numbers.",
        for: "let's meet at three, no, four pm tomorrow to go over the q3 numbers"),
      "Let's meet at 4pm tomorrow to go over the Q3 numbers.")
  }

  func testQuotesTheModelWrappedAroundItsAnswerAreStripped() {
    XCTAssertEqual(DictationPolisher.accept("\"Hello world.\"", for: "hello world"), "Hello world.")
    XCTAssertEqual(DictationPolisher.accept("“Hello world.”", for: "hello world"), "Hello world.")
    // A dictation that genuinely opens with a quote keeps it.
    XCTAssertEqual(DictationPolisher.accept("\"Hello,\" she said.", for: "\"hello\" she said"), "\"Hello,\" she said.")
  }

  func testAnEmptyOrNarratedAnswerIsRefused() {
    XCTAssertNil(DictationPolisher.accept("", for: "hello world"))
    XCTAssertNil(DictationPolisher.accept("Sure, here is the cleaned text: hello world", for: "hello world"))
    XCTAssertNil(DictationPolisher.accept("I'm sorry, I can't help with that.", for: "hello world"))
    // …unless the dictation itself opens that way.
    XCTAssertEqual(
      DictationPolisher.accept("I'm sorry I missed your call.", for: "I'm sorry I missed your call"),
      "I'm sorry I missed your call.")
  }

  func testARewriteThatIsNotRecognisablyTheSameTextIsRefused() {
    let original = "please send the report to the team by friday and copy me on it"
    XCTAssertNil(
      DictationPolisher.accept(
        "Please send the report to the team by Friday and copy me on it. Also, remember that reports are "
          + "important for keeping everyone aligned and informed about progress.",
        for: original))
    XCTAssertNil(DictationPolisher.accept("Report Friday.", for: original))
    // A short dictation cannot be judged by ratio, but it still cannot grow
    // into a paragraph.
    XCTAssertNil(DictationPolisher.accept("Hello there, how are you doing today my friend", for: "hello"))
    XCTAssertEqual(DictationPolisher.accept("Hello!", for: "hello"), "Hello!")
  }

  func testAPlaceholderAboutTheTextIsRefused() {
    // Observed live: a near-empty dictation came back as "(No text provided)"
    // and the placeholder was pasted into the document.
    XCTAssertNil(DictationPolisher.accept("(No text provided)", for: "so"))
    XCTAssertNil(DictationPolisher.accept("[inaudible]", for: "hm so"))
    XCTAssertNil(DictationPolisher.accept("...", for: "so"))
    // A dictation that itself opens with a bracket keeps it.
    XCTAssertEqual(DictationPolisher.accept("(See attached.)", for: "(see attached)"), "(See attached.)")
  }

  func testARewriteOfTheSameLengthButDifferentWordsIsRefused() {
    // Word count alone let an answer, a summary, or a hallucination of a
    // similar length through. The rewrite must be made of the speaker's words.
    let original = "please send the report to the team by friday and copy me on it"
    XCTAssertNil(
      DictationPolisher.accept("The weather this weekend looks sunny with a light breeze from the west.", for: original)
    )
    XCTAssertNil(DictationPolisher.accept("Sure! I have sent the report to the team and copied you.", for: original))
  }

  func testNumbersAddressesAndSelfCorrectionsStillPassTheWordCheck() {
    // The words the model is meant to rewrite are not held against it.
    XCTAssertEqual(
      DictationPolisher.accept(
        "Call me on extension 4512 around 4pm.", for: "call me on extension four five one two around four pm"),
      "Call me on extension 4512 around 4pm.")
    XCTAssertEqual(
      DictationPolisher.accept("My email is john@example.com.", for: "my email is john at example dot com"),
      "My email is john@example.com.")
    XCTAssertEqual(
      DictationPolisher.accept("Meet at four, then dinner.", for: "um meet at three no four uh then dinner"),
      "Meet at four, then dinner.")
    // Spoken punctuation becomes punctuation; the words are unchanged.
    XCTAssertEqual(
      DictationPolisher.accept("Hello, how are you?", for: "hello comma how are you question mark"),
      "Hello, how are you?")
  }

  func testOrdinaryOnScreenWordsAreNotOfferedAsSpellingHints() {
    // Live: the OCR of a terminal put "There" on the keyword list, and the
    // model capitalized "hello there" to match it.
    let known: Set<String> = ["there", "current", "friday", "report", "check"]
    let hints = DictationPolisher.spellingHints(
      from: ["There", "Velma", "Nathan", "Current", "iPhone", "Q3", "GPT-5", "there", "a", "Report"],
      isKnownWord: { known.contains($0) })
    XCTAssertEqual(hints, ["Velma", "Nathan", "iPhone", "Q3", "GPT-5"])
  }

  func testThePromptTellsTheModelHintsAreForSpellingOnly() {
    let prompt = DictationPolisher.systemPrompt(
      context: DictationPolisher.Context(appName: nil, keywords: ["Velma"], language: "en"))
    XCTAssertTrue(prompt.contains("Use them only for spelling."))
    // Live: the lite model rewrote "hello there" as "hello then".
    XCTAssertTrue(prompt.contains("Never substitute one word for another."))
  }

  func testThePromptCarriesTheTargetAppAndSpellingHints() {
    let prompt = DictationPolisher.systemPrompt(
      context: DictationPolisher.Context(appName: "Slack", keywords: ["Nathan", "Velma"], language: "en"))
    XCTAssertTrue(prompt.contains("\"Slack\""))
    XCTAssertTrue(prompt.contains("Nathan, Velma"))
    XCTAssertTrue(prompt.contains("never a request to you"))
    let bare = DictationPolisher.systemPrompt(context: DictationPolisher.Context(appName: nil))
    XCTAssertTrue(bare.contains("a text field"))
    XCTAssertFalse(bare.contains("to help spell them"))
  }
}

final class DictationTranscriberTests: XCTestCase {

  private final class Calls: @unchecked Sendable {
    private let lock = NSLock()
    private var _backend = 0
    private var _onDevice = 0
    private var _fallbacks: [String] = []
    func backend() {
      lock.lock()
      _backend += 1
      lock.unlock()
    }
    func onDevice() {
      lock.lock()
      _onDevice += 1
      lock.unlock()
    }
    func fallback(_ reason: String) {
      lock.lock()
      _fallbacks.append(reason)
      lock.unlock()
    }
    var backendCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _backend
    }
    var onDeviceCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _onDevice
    }
    var fallbacks: [String] {
      lock.lock()
      defer { lock.unlock() }
      return _fallbacks
    }
  }

  private enum Failure: Error { case boom }

  private func makeTranscriber(
    online: Bool,
    backendText: String? = "type hello from the backend",
    backendThrows: Bool = false,
    onDeviceText: String? = "type hello from the device",
    calls: Calls
  ) -> DictationTranscriber {
    DictationTranscriber(
      isOnline: online,
      backend: { _ in
        calls.backend()
        if backendThrows { throw Failure.boom }
        return backendText
      },
      onDevice: { _ in
        calls.onDevice()
        return onDeviceText
      },
      didFallBack: { calls.fallback($0) })
  }

  private let audio = Data(count: 32_000)

  func testOnlineTheBackendTranscriptWinsAndTheDeviceIsNotAsked() async {
    let calls = Calls()
    let result = await makeTranscriber(online: true, calls: calls).transcribe(audio)
    XCTAssertEqual(result, DictationTranscriber.Result(text: "type hello from the backend", source: .backend))
    XCTAssertEqual(calls.backendCalls, 1)
    XCTAssertEqual(calls.onDeviceCalls, 0)
    XCTAssertTrue(calls.fallbacks.isEmpty)
  }

  func testABackendFailureFallsBackToTheDeviceAndSaysWhy() async {
    let calls = Calls()
    let result = await makeTranscriber(online: true, backendThrows: true, calls: calls).transcribe(audio)
    XCTAssertEqual(result, DictationTranscriber.Result(text: "type hello from the device", source: .onDevice))
    XCTAssertEqual(calls.fallbacks, ["other"])
  }

  func testAnEmptyBackendTranscriptFallsBackToTheDevice() async {
    let calls = Calls()
    let result = await makeTranscriber(online: true, backendText: "  ", calls: calls).transcribe(audio)
    XCTAssertEqual(result?.source, .onDevice)
    XCTAssertEqual(calls.fallbacks, ["empty"])
  }

  func testOfflineTheBackendIsNeverTried() async {
    let calls = Calls()
    let result = await makeTranscriber(online: false, calls: calls).transcribe(audio)
    XCTAssertEqual(result, DictationTranscriber.Result(text: "type hello from the device", source: .onDevice))
    XCTAssertEqual(calls.backendCalls, 0)
    XCTAssertTrue(calls.fallbacks.isEmpty, "no fallback was taken when there was never a backend to fall from")
  }

  func testWhenNeitherRecognizerAnswersTheTurnHasNoTranscript() async {
    let calls = Calls()
    let result = await makeTranscriber(online: true, backendThrows: true, onDeviceText: nil, calls: calls)
      .transcribe(audio)
    XCTAssertNil(result)
    let empty = await makeTranscriber(online: true, calls: calls).transcribe(Data())
    XCTAssertNil(empty, "no audio, no transcript")
  }

  /// A request that never completes on its own and only ends when the
  /// enclosing task is cancelled — the shape of a stalled network call.
  private final class StalledRequest: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<String?, Error>?
    private var cancelled = false

    func run() async throws -> String? {
      try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String?, Error>) in
          lock.lock()
          if cancelled {
            lock.unlock()
            continuation.resume(throwing: CancellationError())
            return
          }
          self.continuation = continuation
          lock.unlock()
        }
      } onCancel: {
        cancel()
      }
    }

    private func cancel() {
      lock.lock()
      cancelled = true
      let pending = continuation
      continuation = nil
      lock.unlock()
      pending?.resume(throwing: CancellationError())
    }
  }

  func testCancellingTheTurnStopsTranscriptionWithoutFallingBack() async {
    // A superseded turn must not keep working towards a paste: no on-device
    // fallback, no fallback record, just nothing.
    let calls = Calls()
    let stalled = StalledRequest()
    let transcriber = DictationTranscriber(
      isOnline: true,
      backend: { _ in
        calls.backend()
        return try await stalled.run()
      },
      onDevice: { _ in
        calls.onDevice()
        return "type hello from the device"
      },
      didFallBack: { calls.fallback($0) })
    let audio = self.audio
    let task = Task { await transcriber.transcribe(audio) }
    // The backend has been asked (its call is synchronous up to the stall).
    while calls.backendCalls == 0 { await Task.yield() }
    task.cancel()
    let result = await task.value
    XCTAssertNil(result)
    XCTAssertEqual(calls.onDeviceCalls, 0)
    XCTAssertTrue(calls.fallbacks.isEmpty)
  }

  func testABackendThatNeverAnswersIsTimedOutOntoTheDevice() async {
    let calls = Calls()
    let stalled = StalledRequest()
    var transcriber = DictationTranscriber(
      isOnline: true,
      backend: { _ in
        calls.backend()
        return try await stalled.run()
      },
      onDevice: { _ in
        calls.onDevice()
        return "type hello from the device"
      },
      didFallBack: { calls.fallback($0) })
    transcriber.backendTimeout = 0.01
    let result = await transcriber.transcribe(audio)
    XCTAssertEqual(result?.source, .onDevice)
    XCTAssertEqual(calls.fallbacks, ["timeout"])
    XCTAssertEqual(calls.backendCalls, 1)
  }
}

final class DeadlinedOperationTests: XCTestCase {

  /// An operation that does not observe cancellation at all — the shape of a
  /// request stuck in a token refresh or a decoder mid-buffer.
  private final class Uncooperative: @unchecked Sendable {
    private var continuation: CheckedContinuation<String, Error>?
    private let lock = NSLock()
    func run() async throws -> String {
      try await withCheckedThrowingContinuation { continuation in
        lock.lock()
        self.continuation = continuation
        lock.unlock()
      }
    }
    func finish(_ value: String) {
      lock.lock()
      let pending = continuation
      continuation = nil
      lock.unlock()
      pending?.resume(returning: value)
    }
  }

  func testTheDeadlineDoesNotWaitForAnOperationThatIgnoresCancellation() async {
    let stuck = Uncooperative()
    let started = Date()
    do {
      _ = try await DeadlinedOperation.run(seconds: 0.02) { try await stuck.run() }
      XCTFail("expected a timeout")
    } catch DeadlinedOperation.Failure.timedOut {
      // The cap is the promise: the return did not wait on the stuck work.
      XCTAssertLessThan(Date().timeIntervalSince(started), 2)
    } catch {
      XCTFail("unexpected \(error)")
    }
    // A late answer is dropped, not delivered.
    stuck.finish("too late")
  }

  func testAResultInsideTheDeadlineIsReturned() async throws {
    let value = try await DeadlinedOperation.run(seconds: 5) { "prompt" }
    XCTAssertEqual(value, "prompt")
  }

  func testCancellingTheCallerSurfacesAsCancellationNotTimeout() async {
    let stuck = Uncooperative()
    let task = Task { () throws -> String in
      try await DeadlinedOperation.run(seconds: 5) { try await stuck.run() }
    }
    task.cancel()
    do {
      _ = try await task.value
      XCTFail("expected cancellation")
    } catch is CancellationError {
      // Correct: the caller was cancelled, nothing timed out.
    } catch {
      XCTFail("unexpected \(error)")
    }
    stuck.finish("too late")
  }
}

final class VoiceTypeWakeWordProbeScheduleTests: XCTestCase {

  private static func chunk(voiced: Bool, bytes: Int = 3_200) -> Data {
    var samples = [Int16](repeating: 0, count: bytes / 2)
    if voiced {
      for index in samples.indices { samples[index] = index % 2 == 0 ? 6_000 : -6_000 }
    }
    return samples.withUnsafeMutableBufferPointer { Data(buffer: $0) }
  }

  func testRoomToneNeverSchedulesAProbe() {
    // A locked hold can open with seconds of silence; probing it would decode
    // invented words.
    var schedule = VoiceTypeWakeWordProbeSchedule()
    for _ in 0..<200 {
      XCTAssertFalse(schedule.observe(chunk: Self.chunk(voiced: false)))
    }
    XCTAssertEqual(schedule.probesTaken, 0)
  }

  /// Feeds voiced chunks the way the manager does — starting every probe the
  /// moment it is due — and returns the 1-based chunk index each probe started on.
  private static func probeStarts(chunkBytes: Int, chunks: Int) -> (VoiceTypeWakeWordProbeSchedule, [Int]) {
    var schedule = VoiceTypeWakeWordProbeSchedule()
    var starts: [Int] = []
    for index in 1...chunks where schedule.observe(chunk: chunk(voiced: true, bytes: chunkBytes)) {
      schedule.beginProbe()
      starts.append(index)
    }
    return (schedule, starts)
  }

  func testTheFirstProbeFiresUnderASecondOfVoiceAndThenRetries() {
    let (schedule, probeChunks) = Self.probeStarts(chunkBytes: 3_200, chunks: 100)
    // 3,200 voiced bytes per chunk. The first probe must land well under a
    // second of voice so the dots turn red right after "type"; there are
    // several quick retries and then no more.
    XCTAssertEqual(schedule.probesTaken, VoiceTypeWakeWordProbeSchedule.voicedByteThresholds.count)
    guard let firstProbeChunk = probeChunks.first else { return XCTFail("no probe was ever due") }
    XCTAssertLessThan(Double(firstProbeChunk * 3_200) / 32_000, 0.55)
  }

  func testRealMicrophoneChunksSmallerThanAWindowStillScheduleProbes() {
    // Live: the 48 kHz IOProc buffer resampled to 16 kHz arrives as ~342-byte
    // chunks, smaller than one 20 ms window, so no chunk ever measured as
    // voice and no probe ever ran on a real hold.
    let (_, probeChunks) = Self.probeStarts(chunkBytes: 342, chunks: 600)
    // The first probe still lands under a second of voice with real-sized
    // chunks; all the configured retries fire and then no more.
    XCTAssertEqual(probeChunks.count, VoiceTypeWakeWordProbeSchedule.voicedByteThresholds.count)
    guard let firstProbeChunk = probeChunks.first else { return XCTFail("no probe was ever due") }
    XCTAssertLessThan(Double(firstProbeChunk * 342) / 32_000, 0.6)
  }

  func testADueProbeWaitsForABusyDecoderInsteadOfBeingSpent() {
    // A slow model load can hold one decode across several thresholds. The
    // slots that fall meanwhile are not consumed: the probe stays due until
    // the caller can start it, so the wake word is still listened for.
    var schedule = VoiceTypeWakeWordProbeSchedule()
    for _ in 0..<5 { _ = schedule.observe(chunk: Self.chunk(voiced: true)) }
    XCTAssertTrue(schedule.isProbeDue)
    schedule.beginProbe()
    XCTAssertEqual(schedule.probesTaken, 1)
    // The decoder is busy through the next two thresholds (0.7 s, 1.0 s).
    var dueWhileBusy = 0
    for _ in 0..<8 where schedule.observe(chunk: Self.chunk(voiced: true)) { dueWhileBusy += 1 }
    XCTAssertGreaterThan(dueWhileBusy, 1, "the due probe is reported on every chunk until taken")
    XCTAssertEqual(schedule.probesTaken, 1, "nothing was spent while the decoder was busy")
    // Free again: the pending probe starts on the next chunk, and one only.
    XCTAssertTrue(schedule.observe(chunk: Self.chunk(voiced: true)))
    schedule.beginProbe()
    XCTAssertEqual(schedule.probesTaken, 2)
    XCTAssertTrue(schedule.isProbeDue, "the 1.0 s slot is still owed")
    schedule.beginProbe()
    XCTAssertEqual(schedule.probesTaken, 3)
    XCTAssertFalse(schedule.isProbeDue)
    schedule.beginProbe()
    XCTAssertEqual(schedule.probesTaken, 3, "beginProbe without a due probe spends nothing")
  }

  func testSilenceBetweenWordsDoesNotCountTowardsTheThreshold() {
    var schedule = VoiceTypeWakeWordProbeSchedule()
    var probed = false
    // Below the first threshold (0.45 s ≈ 5 voiced chunks), then a long pause.
    for _ in 0..<3 { probed = schedule.observe(chunk: Self.chunk(voiced: true)) || probed }
    for _ in 0..<50 { probed = schedule.observe(chunk: Self.chunk(voiced: false)) || probed }
    XCTAssertFalse(probed, "silence must not push voiced audio over the threshold")
    // Enough further voice does cross it.
    var crossed = false
    for _ in 0..<5 { crossed = schedule.observe(chunk: Self.chunk(voiced: true)) || crossed }
    XCTAssertTrue(crossed)
  }

  func testADecisionEndsProbingAndResetStartsOver() {
    var schedule = VoiceTypeWakeWordProbeSchedule()
    // Just past the first threshold (0.45 s ≈ 5 voiced chunks), before the next.
    for _ in 0..<5 { _ = schedule.observe(chunk: Self.chunk(voiced: true)) }
    schedule.beginProbe()
    XCTAssertEqual(schedule.probesTaken, 1)
    schedule.decide()
    for _ in 0..<50 {
      XCTAssertFalse(schedule.observe(chunk: Self.chunk(voiced: true)))
    }
    schedule.reset()
    XCTAssertEqual(schedule, VoiceTypeWakeWordProbeSchedule())
  }
}

final class PTTRoutePolicyTests: XCTestCase {

  func testNoNetworkDictatesOnDeviceInsteadOfWaitingForAHubItCannotReach() {
    // The bug this guards: offline, every remote route (hub, omni, batch STT) is
    // unreachable, so a turn spent its whole warm deadline before failing and
    // pasted nothing — while the model that could have transcribed it was
    // already loaded on-device.
    XCTAssertEqual(
      PTTRoutePolicy.decide(isOnline: false, admitsImmediately: false), .onDeviceDictation)
  }

  func testNoNetworkWinsOverAHubThatClaimsToBeAdmitted() {
    // An admitted hub is a socket that was admitted, not one that can still
    // carry the turn. With no path, believing it costs the user the turn.
    XCTAssertEqual(
      PTTRoutePolicy.decide(isOnline: false, admitsImmediately: true), .onDeviceDictation)
  }

  func testOnlineKeepsTheExistingHubRouting() {
    XCTAssertEqual(
      PTTRoutePolicy.decide(isOnline: true, admitsImmediately: true), .hubImmediate)
    XCTAssertEqual(
      PTTRoutePolicy.decide(isOnline: true, admitsImmediately: false), .hubWarmWait)
  }
}

final class VoiceTypeAudioTrimTests: XCTestCase {

  private func pcm(_ samples: [Int16]) -> Data {
    var copy = samples.map { $0.littleEndian }
    return copy.withUnsafeMutableBufferPointer { Data(buffer: $0) }
  }

  private var speech: [Int16] {
    (0..<16_000).map { Int16(truncatingIfNeeded: ($0 % 2 == 0 ? 6_000 : -6_000)) }
  }

  func testLeadingSilenceIsDroppedBeforeTheFirstSpeech() {
    // A locked hold starts when the key is tapped, not when the user speaks.
    // Live, 9s of room tone decoded as 43 characters of invented words.
    let silence = [Int16](repeating: 0, count: 16_000)
    let trimmed = VoiceTypeAudioTrim.trimmingLeadingSilence(pcm(silence + speech))
    let trimmedSamples = trimmed.count / 2
    // The speech survives, plus at most the 100ms pre-roll in front of it.
    XCTAssertGreaterThanOrEqual(trimmedSamples, 16_000)
    XCTAssertLessThanOrEqual(trimmedSamples, 16_000 + 1_600)
  }

  func testAnEntirelyQuietBufferTrimsToNothing() {
    let quiet = [Int16](repeating: 3, count: 32_000)
    XCTAssertTrue(VoiceTypeAudioTrim.trimmingLeadingSilence(pcm(quiet)).isEmpty)
  }

  func testSpeechFromTheFirstSampleIsKeptWhole() {
    XCTAssertEqual(VoiceTypeAudioTrim.trimmingLeadingSilence(pcm(speech)).count, 32_000)
  }

  func testTheOpeningIsBoundedAndZeroIndexed() {
    // A wake-word decode reads the first seconds however long the hold; the
    // slice must index from zero because every consumer does.
    let silence = [Int16](repeating: 0, count: 16_000)
    let opening = VoiceTypeAudioTrim.opening(of: pcm(silence + speech + speech), maxBytes: 20_000)
    XCTAssertEqual(opening.count, 20_000)
    XCTAssertEqual(opening.startIndex, 0)
    // The 100 ms pre-roll (3,200 bytes) leads; the rest is speech, counted in
    // whole 20 ms windows (640 bytes).
    XCTAssertEqual(VoiceTypeAudioTrim.speechBytes(in: opening), ((20_000 - 3_200) / 640) * 640)
  }

  func testSpeechBytesCountOnlyTheVoicedWindows() {
    let silence = [Int16](repeating: 0, count: 16_000)
    XCTAssertEqual(VoiceTypeAudioTrim.speechBytes(in: pcm(silence)), 0)
    XCTAssertEqual(VoiceTypeAudioTrim.speechBytes(in: pcm(speech)), 32_000)
    XCTAssertEqual(VoiceTypeAudioTrim.speechBytes(in: pcm(silence + speech)), 32_000)
  }
}
