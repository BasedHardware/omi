import XCTest

@testable import Omi_Computer

final class SubscriptionPlanNamesTests: XCTestCase {
  func testNamesNeverConfuseProWithArchitectOrUnlimitedWithNeo() {
    let names = [
      "Plus": "plus", "Pro": "operator", "Operator": "operator",
      "Architect": "architect", "Omi Pro": "architect", "Neo": "unlimited",
      "Unlimited (legacy)": "unlimited", "Unlimited": "unlimited_v2",
    ]
    for (name, id) in names {
      XCTAssertEqual(SubscriptionPlanNames.planId(from: name), id)
    }
    XCTAssertNil(SubscriptionPlanNames.planId(from: "future_plan_123"))
  }

  func testCanonicalDisplayNames() {
    let names = [
      "basic": "Free", "plus": "Plus", "operator": "Pro",
      "architect": "Architect", "pro": "Architect", "unlimited": "Neo",
      "unlimited_v2": "Unlimited",
    ]
    for (id, name) in names {
      XCTAssertEqual(SubscriptionPlanType(rawValue: id).displayName, name)
    }
  }
}
