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
    for opening in ["Two. Okay. So hello.", "Tie, hello world", "Typed the report", "tape - send it"] {
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
    XCTAssertTrue(VoiceTypeCommandParser.opensLikeDictation("Two. Okay"))
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
    func caretFollowsWordCharacter() -> Bool { caretAfterWord }
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
    XCTAssertFalse(strict.claim(transcript: "Two. Okay. So hello."), "strict claim rejects a mishearing")
    let (lenient, _) = makeSession()
    XCTAssertTrue(lenient.claim(transcript: "Two. Okay. So hello.", lenient: true))
    XCTAssertTrue(lenient.claimsTurn)
    // The closing transcript then strips the misheard token from the paste.
    XCTAssertEqual(lenient.payload(from: "Two. Okay. So hello."), "Okay. So hello.")
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

  func testAnUnreadableFocusStillPastes() {
    let sink = RecordingSink()
    sink.focus = nil
    let session = VoiceTypeSession(sink: sink, isAccessibilityTrusted: { true })
    session.begin()
    session.noteRelease()
    XCTAssertNotNil(session.payload(from: "Type hello"))
    XCTAssertEqual(session.deliver("Hello"), .pasted("Hello"))
    XCTAssertEqual(sink.pasted, ["Hello"])
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

  func testTheFirstProbeFiresUnderASecondOfVoiceAndThenRetries() {
    var schedule = VoiceTypeWakeWordProbeSchedule()
    var probeChunks: [Int] = []
    for index in 1...100 where schedule.observe(chunk: Self.chunk(voiced: true)) {
      probeChunks.append(index)
    }
    // 3,200 voiced bytes per chunk. The first probe must land well under a
    // second of voice so the dots turn red right after "type"; there are
    // several quick retries and then no more.
    XCTAssertEqual(schedule.probesTaken, VoiceTypeWakeWordProbeSchedule.voicedByteThresholds.count)
    let firstProbeVoicedSeconds = Double(probeChunks[0] * 3_200) / 32_000
    XCTAssertLessThan(firstProbeVoicedSeconds, 0.55)
  }

  func testRealMicrophoneChunksSmallerThanAWindowStillScheduleProbes() {
    // Live: the 48 kHz IOProc buffer resampled to 16 kHz arrives as ~342-byte
    // chunks, smaller than one 20 ms window, so no chunk ever measured as
    // voice and no probe ever ran on a real hold.
    var schedule = VoiceTypeWakeWordProbeSchedule()
    var probeChunks: [Int] = []
    for index in 1...600 where schedule.observe(chunk: Self.chunk(voiced: true, bytes: 342)) {
      probeChunks.append(index)
    }
    // The first probe still lands under a second of voice with real-sized
    // chunks; all the configured retries fire and then no more.
    XCTAssertEqual(probeChunks.count, VoiceTypeWakeWordProbeSchedule.voicedByteThresholds.count)
    let firstProbeVoicedSeconds = Double(probeChunks[0] * 342) / 32_000
    XCTAssertLessThan(firstProbeVoicedSeconds, 0.6)
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
