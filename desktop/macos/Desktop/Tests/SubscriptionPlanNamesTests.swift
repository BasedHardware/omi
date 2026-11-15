import XCTest

@testable import Omi_Computer

final class SubscriptionPlanNamesTests: XCTestCase {
  func testNamesMapOmiProToUnlimitedV2AndNeverConfuseRetiredPlans() {
    let names = [
      "Plus": "plus", "Pro": "operator", "Operator": "operator",
      "Architect": "architect", "Omi Pro": "unlimited_v2", "Neo": "unlimited",
      "Unlimited (legacy)": "unlimited", "Unlimited Plan": "unlimited", "Unlimited": "unlimited_v2",
    ]
    for (name, id) in names {
      XCTAssertEqual(SubscriptionPlanNames.planId(from: name), id)
    }
    for interval in ["Monthly", "Annual"] {
      for (name, id) in names {
        XCTAssertEqual(SubscriptionPlanNames.planId(from: "\(name) \(interval)"), id)
      }
    }
    XCTAssertNil(SubscriptionPlanNames.planId(from: "future_plan_123"))
  }

  func testCanonicalDisplayNames() {
    let names = [
      "basic": "Free", "plus": "Plus", "operator": "Operator",
      "architect": "Architect", "pro": "Architect", "unlimited": "Neo",
      "unlimited_v2": "Omi Pro",
    ]
    for (id, name) in names {
      XCTAssertEqual(SubscriptionPlanType(rawValue: id).displayName, name)
      XCTAssertEqual(SubscriptionPlanOption(id: id, title: "Stale title").displayTitle, name)
    }
  }
}
