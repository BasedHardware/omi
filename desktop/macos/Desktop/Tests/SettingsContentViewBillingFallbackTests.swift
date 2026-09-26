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
    guard let first = text?.split(separator: " ").first, first.allSatisfy(\.isNumber) else {
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
}
