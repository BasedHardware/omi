import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationProcessingTelemetryTests: XCTestCase {
  func testCompletedPayloadCarriesElapsedAndOutcome() {
    let properties = PostHogManager.conversationProcessingProperties(elapsedSeconds: 87, outcome: "completed")
    XCTAssertEqual(properties["elapsed_seconds"] as? Int, 87)
    XCTAssertEqual(properties["outcome"] as? String, "completed")
    XCTAssertEqual(Set(properties.keys), ["elapsed_seconds", "outcome"])
  }

  func testStalledPayloadOmitsOutcome_andClampsNegativeElapsed() {
    let properties = PostHogManager.conversationProcessingProperties(elapsedSeconds: -3, outcome: nil)
    XCTAssertEqual(properties["elapsed_seconds"] as? Int, 0)
    XCTAssertEqual(Set(properties.keys), ["elapsed_seconds"])
  }
}
