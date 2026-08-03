import XCTest

@testable import Omi_Computer

@MainActor
final class ChatToolExecutorCanonicalGoalTests: XCTestCase {
  func testCanonicalGoalCreationInputRequiresIntentAndNormalizesOptionalFields() {
    let input = ChatToolExecutor.canonicalGoalCreationInput([
      "title": "  Finish launch  ",
      "desired_outcome": "  Ship the first release  ",
      "why_it_matters": "  Customers are waiting  ",
      "success_criteria": ["  Release submitted ", "", " Feedback collected "],
    ])

    XCTAssertEqual(
      input,
      ChatToolExecutor.CanonicalGoalCreationInput(
        title: "Finish launch",
        desiredOutcome: "Ship the first release",
        whyItMatters: "Customers are waiting",
        successCriteria: ["Release submitted", "Feedback collected"]
      )
    )
  }

  func testCanonicalGoalCreationInputRejectsMissingRequiredIntent() {
    XCTAssertNil(ChatToolExecutor.canonicalGoalCreationInput(["title": "Goal"]))
    XCTAssertNil(ChatToolExecutor.canonicalGoalCreationInput(["title": " ", "desired_outcome": "Outcome"]))
  }
}
