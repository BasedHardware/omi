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

  func testPendingCancelPurchaseUsesTheCurrentPriceOnly() {
    XCTAssertEqual(
      SubscriptionPlanPresentation.purchase(
        cancelAtPeriodEnd: true, currentPriceId: "price_plus_month", priceId: "price_plus_month"),
      .resubscribe
    )
    XCTAssertEqual(
      SubscriptionPlanPresentation.purchase(
        cancelAtPeriodEnd: true, currentPriceId: "price_plus_month", priceId: "price_plus_year"),
      .blocked
    )
    XCTAssertEqual(
      SubscriptionPlanPresentation.purchase(
        cancelAtPeriodEnd: false, currentPriceId: "price_plus_month", priceId: "price_plus_year"),
      .proceed
    )
    XCTAssertEqual(
      SubscriptionPlanPresentation.endsLine(plan: "Plus", date: "Nov 3, 2026"),
      "Your Plus plan ends Nov 3, 2026."
    )
    XCTAssertEqual(
      SubscriptionPlanPresentation.renewsLine(plan: "Plus", date: "Nov 3, 2026"),
      "Your Plus plan will renew on Nov 3, 2026."
    )
    XCTAssertEqual(SubscriptionPlanPresentation.resubscribeFirst, "Resubscribe first to change plans.")
  }

  func testUnknownPlanUsesNeutralCopyAndNoPaidCapability() {
    let plan = SubscriptionPlanType(rawValue: "future_plan_123")

    XCTAssertEqual(plan.displayName, "Plan unavailable")
    XCTAssertFalse(plan.hasPaidCapability)
  }
}
