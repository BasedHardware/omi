import XCTest

@testable import Omi_Computer

final class InsightSQLPrivacyTests: XCTestCase {
  func testExcludedAppsBecomeAQuotedPredicate() {
    let query = InsightSQLPrivacy.filtered(
      "SELECT * FROM screenshots", excludedApps: ["Password's"])
    XCTAssertTrue(query.contains("appName NOT IN ('Password''s')"))
  }

  func testOnlyTableReferencesAreRewrittenAndAliasesRemainValid() {
    let query = """
      SELECT s.id, 'screenshots literal' AS note
      FROM main.screenshots AS s
      JOIN screenshots other ON other.id = s.id
      WHERE s.appName = 'screenshots'
      """
    let filtered = InsightSQLPrivacy.filtered(query, excludedApps: ["Secrets"])

    XCTAssertTrue(filtered.contains("FROM (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS s"))
    XCTAssertTrue(filtered.contains("JOIN (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS other"))
    XCTAssertTrue(filtered.contains("'screenshots literal'"))
    XCTAssertTrue(filtered.contains("s.appName = 'screenshots'"))
  }

  func testClauseKeywordIsNotConsumedAsAnAlias() {
    let filtered = InsightSQLPrivacy.filtered(
      "SELECT screenshots.id FROM screenshots WHERE screenshots.id = 1",
      excludedApps: ["Secrets"])

    XCTAssertTrue(filtered.contains("AS screenshots WHERE screenshots.id = 1"))
  }

  func testQuotedTableReferencesAreFilteredAcrossSchemasAndSpacing() {
    for table in ["\"screenshots\"", "`screenshots`", "[screenshots]"] {
      let filtered = InsightSQLPrivacy.filtered(
        "SELECT s.id FROM main /* schema */ . \(table) AS s",
        excludedApps: ["Secrets"])

      XCTAssertTrue(
        filtered.contains("FROM (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS s"),
        "quoted table was not filtered: \(filtered)")
    }
  }

  func testLiteralsCommentsAndQualifiedColumnsAreNotRewritten() {
    let query = """
      SELECT s.id, 'FROM \"screenshots\"' AS note /* JOIN [screenshots] */
      FROM \"screenshots\" s
      WHERE s.appName = 'screenshots'
      """
    let filtered = InsightSQLPrivacy.filtered(query, excludedApps: ["Secrets"])

    XCTAssertTrue(filtered.contains("'FROM \"screenshots\"'"))
    XCTAssertTrue(filtered.contains("/* JOIN [screenshots] */"))
    XCTAssertTrue(filtered.contains("WHERE s.appName = 'screenshots'"))
    XCTAssertTrue(filtered.contains("AS s"))
  }

  func testUnsafeTableValuedReferenceFailsClosed() {
    XCTAssertEqual(
      InsightSQLPrivacy.filtered("SELECT * FROM `screenshots`(1)", excludedApps: ["Secrets"]),
      "SELECT 1 WHERE 0")
  }

  func testDirectScreenshotsFTSAccessFailsClosedWhileScreenshotsJoinsRemainFiltered() {
    XCTAssertEqual(
      InsightSQLPrivacy.filtered(
        "SELECT ocrText, appName FROM screenshots_fts WHERE screenshots_fts MATCH 'password'",
        excludedApps: ["Secrets"]),
      "SELECT 1 WHERE 0")
    XCTAssertEqual(
      InsightSQLPrivacy.filtered(
        "SELECT * FROM main.screenshots_fts",
        excludedApps: ["Secrets"]),
      "SELECT 1 WHERE 0")

    let joined = InsightSQLPrivacy.filtered(
      """
      SELECT s.id, f.ocrText FROM screenshots s
      JOIN screenshots_fts f ON f.rowid = s.id
      WHERE f MATCH 'password'
      """,
      excludedApps: ["Secrets"])
    XCTAssertEqual(joined, "SELECT 1 WHERE 0")

    let safeScreenshots = InsightSQLPrivacy.filtered(
      "SELECT id FROM screenshots JOIN other ON other.id = screenshots.id",
      excludedApps: ["Secrets"])
    XCTAssertTrue(
      safeScreenshots.contains("FROM (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS screenshots"))
    XCTAssertFalse(safeScreenshots.contains("SELECT 1 WHERE 0"))
  }

  func testIntersectAndExceptAreClauseBoundariesNotAliases() {
    for keyword in ["INTERSECT", "EXCEPT"] {
      let filtered = InsightSQLPrivacy.filtered(
        "SELECT id FROM screenshots \(keyword) SELECT id FROM other",
        excludedApps: ["Secrets"])
      XCTAssertTrue(
        filtered.contains(
          "FROM (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS screenshots \(keyword)"),
        "\(keyword) was consumed as an alias: \(filtered)")
      XCTAssertFalse(filtered.contains("AS \(keyword)"), "\(keyword) became an alias: \(filtered)")
    }
  }
}
