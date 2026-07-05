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

  func testFreshSessionBargeInDefersSeedPrefetchUntilContinuityCompletes() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("deferredFreshSessionSeedPrefetch"))
    XCTAssertTrue(source.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(source.contains("await refreshVoiceSeedContext()"))
    XCTAssertTrue(source.contains("recordTurnToKernelAwaiting("))
    XCTAssertTrue(source.contains("RealtimeHubBargeInContinuity.prepareReplacementSession("))
    XCTAssertFalse(source.contains("preserveInterruptedTurnForContinuity()"))
  }

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
