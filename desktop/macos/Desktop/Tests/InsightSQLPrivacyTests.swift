import XCTest

@testable import Omi_Computer

final class InsightSQLPrivacyTests: XCTestCase {
  func testExcludedAppsBecomeAQuotedPredicate() {
    let query = InsightSQLPrivacy.filtered(
      "SELECT * FROM screenshots", excludedApps: ["Password's"])
    XCTAssertTrue(query.contains("appName NOT IN ('Password''s')"))
  }
}
