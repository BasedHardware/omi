import XCTest

@testable import Omi_Computer

final class SubscriptionInfoDecoderTests: XCTestCase {

  // MARK: - Baseline decoding (no deprecation fields)

  func testDecodeBasicSubscription() throws {
    let json = """
      {
        "plan": "basic",
        "status": "active",
        "current_period_end": null,
        "stripe_subscription_id": null,
        "current_price_id": null,
        "features": [],
        "cancel_at_period_end": false,
        "limits": {
          "transcription_seconds": 3600,
          "words_transcribed": 10000,
          "insights_gained": 50,
          "memories_created": 100
        }
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.plan, .basic)
    XCTAssertEqual(info.status, .active)
    XCTAssertNil(info.deprecated)
    XCTAssertNil(info.deprecationMessage)
  }

  func testDecodeOperatorPlan() throws {
    let json = """
      {
        "plan": "operator",
        "status": "active",
        "current_period_end": 1700000000,
        "stripe_subscription_id": "sub_abc",
        "current_price_id": "price_xyz",
        "features": ["chat_500"],
        "cancel_at_period_end": false,
        "limits": {
          "transcription_seconds": null,
          "words_transcribed": null,
          "insights_gained": null,
          "memories_created": null
        }
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.plan, .operator)
    XCTAssertEqual(info.status, .active)
    XCTAssertNil(info.deprecated)
  }

  // MARK: - Deprecation fields

  func testDecodeDeprecatedUnlimited() throws {
    let json = """
      {
        "plan": "unlimited",
        "status": "active",
        "current_period_end": 1700000000,
        "stripe_subscription_id": "sub_old",
        "current_price_id": "price_old",
        "features": ["chat_500"],
        "cancel_at_period_end": false,
        "limits": {
          "transcription_seconds": null,
          "words_transcribed": null,
          "insights_gained": null,
          "memories_created": null
        },
        "deprecated": true,
        "deprecation_message": "Your Unlimited plan is being retired. Try the Operator plan."
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.plan, .unlimited)
    XCTAssertEqual(info.deprecated, true)
    XCTAssertEqual(
      info.deprecationMessage, "Your Unlimited plan is being retired. Try the Operator plan.")
  }

  func testDecodeDeprecatedFalse() throws {
    let json = """
      {
        "plan": "operator",
        "status": "active",
        "current_period_end": 1700000000,
        "stripe_subscription_id": "sub_new",
        "current_price_id": "price_new",
        "features": [],
        "cancel_at_period_end": false,
        "limits": {
          "transcription_seconds": null,
          "words_transcribed": null,
          "insights_gained": null,
          "memories_created": null
        },
        "deprecated": false
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.deprecated, false)
    XCTAssertNil(info.deprecationMessage)
  }

  func testDecodeArchitectPlan() throws {
    let json = """
      {
        "plan": "architect",
        "status": "active",
        "current_period_end": 1700000000,
        "stripe_subscription_id": "sub_architect",
        "current_price_id": "price_architect",
        "features": ["automations"],
        "cancel_at_period_end": true,
        "limits": {
          "transcription_seconds": null,
          "words_transcribed": null,
          "insights_gained": null,
          "memories_created": null
        }
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.plan, .architect)
    XCTAssertTrue(info.cancelAtPeriodEnd)
    XCTAssertNil(info.deprecated)
  }

  func testDecodeProPlanBackwardCompat() throws {
    let json = """
      {
        "plan": "pro",
        "status": "active",
        "current_period_end": 1700000000,
        "stripe_subscription_id": "sub_pro",
        "current_price_id": "price_pro",
        "features": ["automations"],
        "cancel_at_period_end": false,
        "limits": {
          "transcription_seconds": null,
          "words_transcribed": null,
          "insights_gained": null,
          "memories_created": null
        }
      }
      """
    let info = try JSONDecoder().decode(UserSubscriptionInfo.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(info.plan, .pro)
  }

  func testDecodePlusPlan() throws {
    let plan = try JSONDecoder().decode(SubscriptionPlanType.self, from: Data(#""plus""#.utf8))
    XCTAssertEqual(plan, .plus)
    XCTAssertEqual(plan.rawValue, "plus")
    XCTAssertTrue(plan.hasPaidCapability)
  }

  func testDecodeUnlimitedV2Plan() throws {
    let plan = try JSONDecoder().decode(SubscriptionPlanType.self, from: Data(#""unlimited_v2""#.utf8))
    XCTAssertEqual(plan, .unlimitedV2)
    XCTAssertEqual(plan.rawValue, "unlimited_v2")
    XCTAssertTrue(plan.hasPaidCapability)
  }

  func testDecodeUnknownPlanPreservesIdentityAndDeniesPaidCapability() throws {
    let rawValue = "future_plan_123"
    let plan = try JSONDecoder().decode(SubscriptionPlanType.self, from: Data(#""future_plan_123""#.utf8))

    guard case .unknown(let decodedRawValue) = plan else {
      return XCTFail("future plan should retain an unknown representation")
    }
    XCTAssertEqual(decodedRawValue, rawValue)
    XCTAssertEqual(plan.rawValue, rawValue)
    XCTAssertEqual(plan.displayName, "Plan unavailable")
    XCTAssertFalse(plan.hasPaidCapability)

    let encoded = try JSONEncoder().encode(plan)
    XCTAssertEqual(String(data: encoded, encoding: .utf8), #""future_plan_123""#)
  }
}
