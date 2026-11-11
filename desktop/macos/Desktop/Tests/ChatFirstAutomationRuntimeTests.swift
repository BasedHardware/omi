import XCTest

@testable import Omi_Computer

final class ChatFirstAutomationRuntimeTests: XCTestCase {
  func testQuestionAutomationSelectsOnlyBoundedFirstOrDeferralOptions() {
    let options: [[String: Any]] = [
      ["optionId": "later", "defer": true],
      ["optionId": "continue", "defer": false],
      ["optionId": "  ", "defer": false],
    ]

    XCTAssertEqual(
      ChatFirstQuestionAutomationSelectionPolicy.optionID(in: options, selection: .first),
      "continue"
    )
    XCTAssertEqual(
      ChatFirstQuestionAutomationSelectionPolicy.optionID(in: options, selection: .deferred),
      "later"
    )
  }

  func testQuestionAutomationNeverFallsBackToCallerSuppliedOrMalformedOptionID() {
    XCTAssertNil(
      ChatFirstQuestionAutomationSelectionPolicy.optionID(
        in: [["optionId": "  ", "defer": true]],
        selection: .deferred
      )
    )
    XCTAssertNil(
      ChatFirstQuestionAutomationSelectionPolicy.optionID(
        in: [["optionId": "continue", "defer": false]],
        selection: .deferred
      )
    )
  }
}
