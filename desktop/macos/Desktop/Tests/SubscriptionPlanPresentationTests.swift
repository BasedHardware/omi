import XCTest

@testable import Omi_Computer

final class SubscriptionPlanPresentationTests: XCTestCase {
  func testSelectionLabelIncludesTheStartingPrice() {
    XCTAssertEqual(
      SubscriptionPlanPresentation.selectionLabel(
        planTitle: "Operator", startingPrice: "$49.00/month"),
      "Select Operator · $49.00/month"
    )
  }

  func testSelectionLabelOmitsTheSeparatorWhenNoPriceIsAvailable() {
    XCTAssertEqual(
      SubscriptionPlanPresentation.selectionLabel(planTitle: "Operator", startingPrice: nil),
      "Select Operator"
    )
  }

  func testUnknownPlanUsesNeutralCopyAndNoPaidCapability() {
    let plan = SubscriptionPlanType(rawValue: "future_plan_123")

    XCTAssertEqual(plan.displayName, "Plan unavailable")
    XCTAssertFalse(plan.hasPaidCapability)
  }
}
