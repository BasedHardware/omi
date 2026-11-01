import XCTest

@testable import Omi_Computer

/// Fallback billing copy shown only when the backend catalog omits a plan's
/// subtitle/description (`SettingsContentView.planSubtitle`/`planDescription`).
/// These shipped disagreeing for the "unlimited" (Neo) plan id — the subtitle
/// said 200 questions/month while the description said 100 — so a user could
/// see either number depending which card region they read.
@MainActor
final class SettingsContentViewBillingFallbackTests: XCTestCase {
  private func leadingQuestionCount(in text: String?) -> String? {
    guard let first = text?.split(separator: " ").first, first.allSatisfy({ $0.isNumber || $0 == "," }) else {
      return nil
    }
    return String(first)
  }

  func testUnlimitedFallbackSubtitleAndDescriptionAgreeOnQuestionCount() {
    let subtitle = SettingsContentView.planSubtitle(for: "unlimited")
    let description = SettingsContentView.planDescription(for: "unlimited")
    XCTAssertEqual(leadingQuestionCount(in: subtitle), leadingQuestionCount(in: description))
    XCTAssertEqual(leadingQuestionCount(in: description), "200")
  }

  func testOperatorFallbackSubtitleAndDescriptionAgreeOnQuestionCount() {
    let subtitle = SettingsContentView.planSubtitle(for: "operator")
    let description = SettingsContentView.planDescription(for: "operator")
    XCTAssertEqual(leadingQuestionCount(in: subtitle), leadingQuestionCount(in: description))
    XCTAssertEqual(leadingQuestionCount(in: description), "500")
  }

  func testOmiProFallbackCopyAgreesOnQuestionCount() {
    let subtitle = SettingsContentView.planSubtitle(for: "unlimited_v2")
    let description = SettingsContentView.planDescription(for: "unlimited_v2")
    XCTAssertEqual(leadingQuestionCount(in: subtitle), leadingQuestionCount(in: description))
    XCTAssertEqual(leadingQuestionCount(in: description), "1,000")
    XCTAssertTrue(SettingsContentView.fallbackFeatures(for: "unlimited_v2").contains("1,000 chat questions per month"))
  }

  func testOnlyOmiProIsOfferedAndRetiredPlansNeverRender() {
    let catalog = ["architect", "operator", "unlimited", "plus", "unlimited_v2"].map {
      SubscriptionPlanOption(id: $0, title: $0)
    }
    let offered = SettingsContentView.purchasablePlans(catalog) { _ in false }
    XCTAssertEqual(offered.map(\.id), ["unlimited_v2"])
    XCTAssertEqual(offered.first?.displayTitle, "Omi Pro")
    XCTAssertTrue(SettingsContentView.purchasablePlans(catalog) { $0.id == "unlimited_v2" }.isEmpty)
  }

  func testAvailablePlanPricesPreferBackendPlanId() throws {
    let json =
      #"{"id":"price_1","plan_id":"unlimited_v2","title":"Pro Monthly","price_string":"$29.99/month","interval":"month","unit_amount":2999,"is_active":true}"#
    let price = try JSONDecoder().decode(AvailablePlanPriceOption.self, from: Data(json.utf8))
    XCTAssertEqual(price.planId, "unlimited_v2")
  }
}
