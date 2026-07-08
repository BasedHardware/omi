import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubBargeInContinuityTests: XCTestCase {

  func testPrepareReplacementSessionPersistsInterruptedTurnBeforeSeedAndSession() async {
    var steps: [String] = []
    let interrupted = InterruptedTurnPayload(
      userText: "hold on",
      assistantText: "partial reply",
      idempotencyKey: "turn-interrupted"
    )

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      interruptedTurn: interrupted,
      recordInterruptedTurn: { turn in
        steps.append("record:\(turn.idempotencyKey)")
      },
      refreshVoiceSeed: {
        steps.append("seed")
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(steps, ["record:turn-interrupted", "seed", "session"])
  }

  func testPrepareReplacementSessionSkipsRecordWhenNoInterruptedTurn() async {
    var steps: [String] = []

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      interruptedTurn: nil,
      recordInterruptedTurn: { _ in
        steps.append("record")
      },
      refreshVoiceSeed: {
        steps.append("seed")
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(steps, ["seed", "session"])
  }

  func testInterruptedTurnVisibleAssistantTextKeepsPartialReplyOnly() {
    XCTAssertEqual(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: "  Partial reply  "),
      "Partial reply"
    )
    XCTAssertEqual(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: ""),
      ""
    )
    XCTAssertFalse(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: "Still streaming…")
        .localizedCaseInsensitiveContains("interrupted")
    )
  }

  func testFreshSessionBargeInDefersSeedPrefetchUntilContinuityCompletes() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("deferredFreshSessionSeedPrefetch"))
    XCTAssertTrue(source.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(source.contains("await self.refreshVoiceSeedContext()") || source.contains("await refreshVoiceSeedContext()"))
    XCTAssertTrue(source.contains("reconnectWarmSessionIfSeedStale()"))
    XCTAssertTrue(source.contains("sessionVoiceSeedContextSnapshot"))
    XCTAssertTrue(source.contains("recordTurnToKernelAwaiting("))
    XCTAssertTrue(source.contains("RealtimeHubBargeInContinuity.prepareReplacementSession("))
    XCTAssertFalse(source.contains("preserveInterruptedTurnForContinuity()"))
  }

  func testBeginTurnWaitsForActiveSessionBeforeActivityStart() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("inputTurnInProgress = true"))
    XCTAssertTrue(source.contains("await self.waitUntilActive(timeout: 15)"))
    XCTAssertTrue(source.contains("inputTurnActivityStartPending = true"))
  }

  func testHubDidConnectRetriesActivityStartDuringOpenTurn() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("if inputTurnInProgress"))
    XCTAssertTrue(
      source.contains("inputTurnActivityStartPending || sessionProvider == .gemini"))
    XCTAssertTrue(source.contains("session?.beginInputTurn(interrupting: pendingInputTurnInterrupting)"))
  }

  func testSeedStaleReconnectDefersUntilTurnCompletion() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("reconnectWarmSessionWhenTurnCompletes = true"))
    XCTAssertTrue(source.contains("private func reconnectDeferredWarmSessionIfNeeded()"))
    XCTAssertTrue(source.contains("deferred voice seed reconnect after turn completion"))
    XCTAssertGreaterThanOrEqual(
      source.components(separatedBy: "reconnectDeferredWarmSessionIfNeeded()").count - 1,
      3,
      "deferred reconnect should be checked by helper definition plus cancel and turn-done paths")
  }

  func testPTTArmsVoiceSeedPrefetchBeforeMicCapture() throws {
    let pttSource = try pushToTalkManagerSource()
    let prefetchRange = try XCTUnwrap(pttSource.range(of: "prefetchVoiceSeedContextIfNeeded()"))
    let captureRange = try XCTUnwrap(pttSource.range(of: "captureContextAndStartAudio(preOverlayImage: preOverlayImage)"))
    XCTAssertLessThan(prefetchRange.lowerBound, captureRange.lowerBound)
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
