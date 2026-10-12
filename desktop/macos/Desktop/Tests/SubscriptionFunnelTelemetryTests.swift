import XCTest

@testable import Omi_Computer

final class SubscriptionFunnelTelemetryTests: XCTestCase {
  func testPlanIntervalAndSourceCollapseOntoTheClosedVocabulary() {
    XCTAssertEqual(SubscriptionFunnelWire.plan("pro"), "architect")
    XCTAssertEqual(SubscriptionFunnelWire.plan("free"), "basic")
    XCTAssertEqual(SubscriptionFunnelWire.plan("not-a-plan"), "unknown")
    XCTAssertEqual(SubscriptionFunnelWire.interval("Monthly"), "month")
    XCTAssertEqual(SubscriptionFunnelWire.interval("Annual"), "year")
    XCTAssertEqual(SubscriptionFunnelWire.source("Usage Page Plan Sheet"), "unknown")
  }

  func testPaywallAndUpgradePropertiesUseTheRegisteredNames() {
    XCTAssertEqual(
      SubscriptionFunnelWire.paywallProperties(source: "macos_usage_limit", currentPlan: "plus"),
      ["source": "macos_usage_limit", "current_plan": "plus"]
    )
    XCTAssertEqual(
      SubscriptionFunnelWire.planSelectedProperties(
        plan: "operator",
        billingInterval: "yearly",
        source: "macos_billing"
      ),
      ["plan": "operator", "billing_interval": "year", "source": "macos_billing"]
    )
    XCTAssertEqual(
      SubscriptionFunnelWire.upgradeSucceededProperties(plan: "plus", billingInterval: "month"),
      ["plan": "plus", "billing_interval": "month"]
    )
  }
}
