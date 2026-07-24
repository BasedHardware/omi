import XCTest

@testable import Omi_Computer

final class AICloneModelsTests: XCTestCase {
  // MARK: Reply decision parsing

  func testParsesPlainJSONDecision() {
    let raw = #"{"should_reply": true, "confidence": 0.9, "suspected_injection": false, "reply": "on my way!"}"#
    let decision = AICloneReplyDecision.parse(raw)
    XCTAssertEqual(decision?.shouldReply, true)
    XCTAssertEqual(decision?.confidence, 0.9)
    XCTAssertEqual(decision?.suspectedInjection, false)
    XCTAssertEqual(decision?.reply, "on my way!")
  }

  func testParsesFencedJSONDecision() {
    let raw = """
      Here is the verdict:
      ```json
      {"should_reply": false, "confidence": 0.2, "suspected_injection": false, "reply": null}
      ```
      """
    let decision = AICloneReplyDecision.parse(raw)
    XCTAssertEqual(decision?.shouldReply, false)
    XCTAssertNil(decision?.reply)
  }

  func testRejectsNonJSONVerdict() {
    XCTAssertNil(AICloneReplyDecision.parse("I think you should reply with hello"))
  }

  // MARK: Trust ladder

  private func decision(
    shouldReply: Bool = true,
    confidence: Double = 0.9,
    injection: Bool = false,
    reply: String? = "sure, 7pm works"
  ) -> AICloneReplyDecision {
    AICloneReplyDecision(
      shouldReply: shouldReply, confidence: confidence,
      suspectedInjection: injection, reply: reply)
  }

  func testInjectionAlwaysBlocksRegardlessOfMode() {
    for mode in AICloneChatMode.allCases {
      XCTAssertEqual(
        decision(injection: true).plannedOutcome(mode: mode, autoConfidenceThreshold: 0.75),
        .declinedInjection)
    }
  }

  func testSilenceIsFirstClassWhenEngineDeclines() {
    XCTAssertEqual(
      decision(shouldReply: false, reply: nil).plannedOutcome(mode: .auto, autoConfidenceThreshold: 0.5),
      .stayedSilent)
    XCTAssertEqual(
      decision(reply: "  ").plannedOutcome(mode: .draft, autoConfidenceThreshold: 0.5),
      .stayedSilent)
  }

  func testTrustLadderMapsModesToOutcomes() {
    XCTAssertEqual(decision().plannedOutcome(mode: .off, autoConfidenceThreshold: 0.75), .stayedSilent)
    XCTAssertEqual(decision().plannedOutcome(mode: .draft, autoConfidenceThreshold: 0.75), .drafted)
    XCTAssertEqual(decision().plannedOutcome(mode: .ask, autoConfidenceThreshold: 0.75), .askedApproval)
    XCTAssertEqual(decision().plannedOutcome(mode: .auto, autoConfidenceThreshold: 0.75), .sentAutomatically)
  }

  func testAutoDowngradesToDraftBelowConfidenceGate() {
    XCTAssertEqual(
      decision(confidence: 0.5).plannedOutcome(mode: .auto, autoConfidenceThreshold: 0.75),
      .drafted)
  }

  // MARK: Configuration store

  func testConfigurationRoundTripsThroughStore() {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("ai-clone-store-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let store = AICloneConfigurationStore(directory: dir)

    var config = AICloneConfiguration()
    config.enabled = true
    config.chatModes["chat-1"] = .ask
    config.appendActivity(
      AICloneActivityEntry(
        chatID: "chat-1", chatTitle: "Mom", network: "WhatsApp",
        inboundPreview: "how was the trip?", replyText: "amazing!",
        outcome: .drafted, confidence: 0.8))
    store.save(config)

    let loaded = store.load()
    XCTAssertTrue(loaded.enabled)
    XCTAssertEqual(loaded.mode(for: "chat-1"), .ask)
    XCTAssertEqual(loaded.activityLog.first?.chatTitle, "Mom")
    XCTAssertEqual(loaded.activityLog.first?.outcome, .drafted)
  }

  func testMissingStoreLoadsDefaultsWithEverythingOff() {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("ai-clone-missing-\(UUID().uuidString)", isDirectory: true)
    let config = AICloneConfigurationStore(directory: dir).load()
    XCTAssertFalse(config.enabled)
    XCTAssertEqual(config.mode(for: "anything"), .off)
    XCTAssertTrue(config.activityLog.isEmpty)
  }

  func testActivityLogStaysBounded() {
    var config = AICloneConfiguration()
    for index in 0..<(AICloneConfiguration.activityLogLimit + 25) {
      config.appendActivity(
        AICloneActivityEntry(
          chatID: "c", chatTitle: "t", network: "n",
          inboundPreview: "\(index)", replyText: nil,
          outcome: .stayedSilent, confidence: nil))
    }
    XCTAssertEqual(config.activityLog.count, AICloneConfiguration.activityLogLimit)
    XCTAssertEqual(config.activityLog.first?.inboundPreview, "\(AICloneConfiguration.activityLogLimit + 24)")
  }

  // MARK: Auto-mode benchmark gate

  func testAutoModeRequiresPassingBenchmark() {
    var config = AICloneConfiguration()
    XCTAssertFalse(config.canEnableAuto(for: "chat-1"), "no benchmark → no auto")
    config.benchmarkResults["chat-1"] = AICloneBenchmarkResult(
      chatID: "chat-1", chatTitle: "Mom", sampleCount: 6, matchScore: 45, generatedAt: Date())
    XCTAssertFalse(config.canEnableAuto(for: "chat-1"), "failing score → no auto")
    config.benchmarkResults["chat-1"] = AICloneBenchmarkResult(
      chatID: "chat-1", chatTitle: "Mom", sampleCount: 6, matchScore: 82, generatedAt: Date())
    XCTAssertTrue(config.canEnableAuto(for: "chat-1"))
  }
}
