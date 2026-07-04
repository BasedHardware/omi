import XCTest

@testable import Omi_Computer

final class AICloneArchitectureTests: XCTestCase {

  // MARK: - Candidate JSON parsing

  func testParseCandidatesWellFormed() {
    let text = #"{"candidates": [["nah", "nah fr"], ["lol what"], ["bro 😭", "stop"]]}"#
    let parsed = AIClonePersonaService.parseCandidates(from: text)
    XCTAssertEqual(parsed?.count, 3)
    XCTAssertEqual(parsed?[0], ["nah", "nah fr"])
    XCTAssertEqual(parsed?[2], ["bro 😭", "stop"])
  }

  func testParseCandidatesWithFencesAndTrailingProse() {
    let text = """
      ```json
      {"candidates": [["yeah alr"]]}
      ```
      Hope that helps!
      """
    let parsed = AIClonePersonaService.parseCandidates(from: text)
    XCTAssertEqual(parsed, [["yeah alr"]])
  }

  func testParseCandidatesFlatArrayTolerated() {
    let text = #"{"candidates": ["one", "two"]}"#
    XCTAssertEqual(AIClonePersonaService.parseCandidates(from: text), [["one", "two"]])
  }

  func testLenientExtractionFromMalformedJSON() {
    // Unterminated final array — JSONSerialization fails, lenient path must still
    // recover the first candidate's bubbles and never return JSON syntax as content.
    let text = #"{"candidates": [["bro 💔", "is it wraps"], ["so she a bop", "ts makes"#
    XCTAssertNil(AIClonePersonaService.parseCandidates(from: text))
    let extracted = AIClonePersonaService.extractFirstCandidateStrings(from: text)
    XCTAssertEqual(extracted, ["bro 💔", "is it wraps"])
  }

  func testLenientExtractionHandlesEscapes() {
    let text = #"{"candidates": [["she said \"no\"", "line\nbreak"]]}"#
    let extracted = AIClonePersonaService.extractFirstCandidateStrings(from: text)
    XCTAssertEqual(extracted, ["she said \"no\"", "line\nbreak"])
  }

  func testSanitizeBubblesDropsPlaceholdersAndSplitsNewlines() {
    let bubbles = AIClonePersonaService.sanitizeBubbles([
      "first\nsecond", "  ", "[attachment]", "third",
    ])
    XCTAssertEqual(bubbles, ["first", "second", "third"])
  }

  // MARK: - Style features

  private func message(_ text: String, fromMe: Bool, minutesAgo: Double) -> ImportedMessage {
    ImportedMessage(isFromMe: fromMe, text: text, date: Date(timeIntervalSinceNow: -minutesAgo * 60))
  }

  private func lowercaseBurstyHistory() -> [ImportedMessage] {
    // Oldest-first: contact asks, user replies in 2-bubble lowercase bursts, no periods.
    var messages: [ImportedMessage] = []
    for i in 0..<30 {
      let t = Double(300 - i * 10)
      messages.append(message("question \(i)", fromMe: false, minutesAgo: t + 2))
      messages.append(message("nah bro", fromMe: true, minutesAgo: t + 1))
      messages.append(message("ts crazy fr", fromMe: true, minutesAgo: t))
    }
    return messages
  }

  func testExtractMeasuresBurstsAndCasing() {
    let features = AICloneStyleAnalyzer.extract(from: lowercaseBurstyHistory())
    XCTAssertEqual(features.sampleCount, 60)
    XCTAssertGreaterThan(features.burstShare[2], 0.9, "every reply turn is a 2-bubble burst")
    XCTAssertGreaterThan(features.lowercaseStartRate, 0.9)
    XCTAssertEqual(features.terminalPeriodRate, 0, accuracy: 0.001)
  }

  func testStyleScorePrefersInStyleCandidate(){
    let features = AICloneStyleAnalyzer.extract(from: lowercaseBurstyHistory())
    let inStyle = AICloneStyleAnalyzer.styleScore(bubbles: ["nah fr", "ts wild"], features: features)
    let offStyle = AICloneStyleAnalyzer.styleScore(
      bubbles: ["That sounds like a really interesting opportunity, and I think we should definitely consider all the angles before committing to anything."],
      features: features)
    XCTAssertGreaterThan(inStyle, offStyle)
  }

  // MARK: - Preview bubble rendering

  func testReplySplitsIntoSeparatePreviewBubbles() {
    XCTAssertEqual(
      AICloneReplyPresentation.bubbles(from: "nah\njs forgot abt it\nu done it"),
      ["nah", "js forgot abt it", "u done it"])
    XCTAssertEqual(AICloneReplyPresentation.bubbles(from: "single"), ["single"])
    XCTAssertEqual(AICloneReplyPresentation.bubbles(from: "a\n\n  \nb"), ["a", "b"])
  }

  // MARK: - Live chat: latest incoming burst

  func testLatestIncomingBurstJoinsConsecutiveIncomingAndTakesContext() {
    let turns: [(isFromMe: Bool, text: String)] = [
      (true, "yo"),
      (false, "hey"),
      (true, "what's up"),
      (false, "did you see the game"),
      (false, "insane ending"),
    ]
    let burst = AICloneLiveChat.latestIncomingBurst(in: turns)
    XCTAssertEqual(burst?.incoming, "did you see the game\ninsane ending")
    XCTAssertEqual(burst?.context.map(\.text), ["yo", "hey", "what's up"])
    XCTAssertEqual(burst?.context.map(\.isFromMe), [true, false, true])
  }

  func testLatestIncomingBurstIgnoresTrailingFromMeMessages() {
    // My messages after the last incoming burst: the burst still targets that incoming.
    let turns: [(isFromMe: Bool, text: String)] = [
      (false, "you free tmrw"),
      (true, "let me check"),
    ]
    let burst = AICloneLiveChat.latestIncomingBurst(in: turns)
    XCTAssertEqual(burst?.incoming, "you free tmrw")
    XCTAssertEqual(burst?.context.count, 0)
  }

  func testLatestIncomingBurstNilWithoutIncoming() {
    XCTAssertNil(AICloneLiveChat.latestIncomingBurst(in: [(true, "hello?"), (true, "u there")]))
    XCTAssertNil(AICloneLiveChat.latestIncomingBurst(in: []))
  }

  func testLatestIncomingBurstCapsContextAtEightTurns() {
    var turns: [(isFromMe: Bool, text: String)] = []
    for i in 0..<20 {
      turns.append((i % 2 == 1, "turn \(i)"))
    }
    turns.append((false, "newest"))
    let burst = AICloneLiveChat.latestIncomingBurst(in: turns)
    XCTAssertEqual(burst?.incoming, "newest")
    XCTAssertEqual(burst?.context.count, 8)
    XCTAssertEqual(burst?.context.last?.text, "turn 19")
  }

  // MARK: - Pair extraction (session gap)

  func testBuildPairsSkipsRepliesAcrossLongGaps() {
    let now = Date()
    let messages: [ImportedMessage] = [
      ImportedMessage(isFromMe: false, text: "you up?", date: now.addingTimeInterval(-10 * 3600)),
      // 9 hours later — a new conversation started by me, NOT a reply.
      ImportedMessage(isFromMe: true, text: "yo", date: now.addingTimeInterval(-3600)),
      ImportedMessage(isFromMe: false, text: "what did she say", date: now.addingTimeInterval(-1800)),
      ImportedMessage(isFromMe: true, text: "nothing yet", date: now.addingTimeInterval(-1700)),
    ]
    let pairs = AICloneBacktestService.buildPairs(from: messages)
    XCTAssertEqual(pairs.count, 1)
    XCTAssertEqual(pairs.first?.contactMessage, "what did she say")
    XCTAssertEqual(pairs.first?.actualReply, "nothing yet")
  }

  func testBuildPairsJoinsBurstsAndKeepsContext() {
    let now = Date()
    let messages: [ImportedMessage] = [
      ImportedMessage(isFromMe: true, text: "earlier", date: now.addingTimeInterval(-500)),
      ImportedMessage(isFromMe: false, text: "one", date: now.addingTimeInterval(-400)),
      ImportedMessage(isFromMe: false, text: "two", date: now.addingTimeInterval(-350)),
      ImportedMessage(isFromMe: true, text: "reply a", date: now.addingTimeInterval(-300)),
      ImportedMessage(isFromMe: true, text: "reply b", date: now.addingTimeInterval(-250)),
    ]
    let pairs = AICloneBacktestService.buildPairs(from: messages)
    XCTAssertEqual(pairs.count, 1)
    XCTAssertEqual(pairs.first?.contactMessage, "one\ntwo")
    XCTAssertEqual(pairs.first?.actualReply, "reply a\nreply b")
    XCTAssertEqual(pairs.first?.context.map(\.text), ["earlier"])
  }
}
