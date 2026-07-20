import XCTest

@testable import Omi_Computer

final class RealtimeSpawnFailureContinuationPolicyTests: XCTestCase {
  func testFirstSpawnFailureContinuesTheTurnAndSecondTerminates() {
    var policy = RealtimeSpawnFailureContinuationPolicy()
    let turn = UUID()

    XCTAssertTrue(policy.beginContinuationIfAllowed(turnID: turn, failedProvider: "codex"))
    XCTAssertFalse(
      policy.beginContinuationIfAllowed(turnID: turn, failedProvider: "hermes"),
      "the second spawn failure in the same turn must terminate it — no retry loops")
  }

  func testDistinctTurnsEachGetOneContinuation() {
    var policy = RealtimeSpawnFailureContinuationPolicy()

    XCTAssertTrue(policy.beginContinuationIfAllowed(turnID: UUID(), failedProvider: nil))
    XCTAssertTrue(policy.beginContinuationIfAllowed(turnID: UUID(), failedProvider: "openclaw"))
  }

  func testTakeFailedProviderConsumesTheFallbackFromLabelOnce() {
    var policy = RealtimeSpawnFailureContinuationPolicy()
    let turn = UUID()
    _ = policy.beginContinuationIfAllowed(turnID: turn, failedProvider: "codex")

    XCTAssertEqual(policy.takeFailedProvider(turnID: turn), "codex")
    XCTAssertNil(
      policy.takeFailedProvider(turnID: turn),
      "consuming twice would double-report the same fallback")
  }

  func testNoFailedProviderIsRecordedForDefaultAgentFailures() {
    var policy = RealtimeSpawnFailureContinuationPolicy()
    let turn = UUID()
    _ = policy.beginContinuationIfAllowed(turnID: turn, failedProvider: nil)

    XCTAssertNil(policy.takeFailedProvider(turnID: turn))
  }
}
