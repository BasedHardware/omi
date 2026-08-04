import XCTest

@testable import Omi_Computer

/// Regression: a search whose query contained a single-character word produced an empty
/// FTS5 group `()`, which made the whole MATCH invalid — `fts5: syntax error near ")"` —
/// so the entire search failed rather than that one word matching nothing.
///
/// Found live: a Cursor window titled `2.1.220` tokenizes to `2`, `1`, `220`; the `2` and
/// `1` each expanded to `()`. This affects every caller of `RewindDatabase.search`.
final class RewindSearchQueryExpansionTests: XCTestCase {
  private let db = RewindDatabase.shared

  /// The exact input that failed in production.
  func testSingleCharacterWordsDoNotProduceAnEmptyGroup() {
    let expanded = db.expandSearchQuery("2 1 220")
    XCTAssertFalse(expanded.contains("()"), "empty group in \"\(expanded)\" makes FTS5 MATCH invalid")
    XCTAssertEqual(expanded, "220*")
  }

  func testAllSingleCharacterWordsExpandToEmptyRatherThanInvalidSyntax() {
    // `search` guards on an empty expansion and returns [] — an invalid group would instead throw.
    let expanded = db.expandSearchQuery("a 1 x")
    XCTAssertTrue(expanded.isEmpty, "expected empty expansion, got \"\(expanded)\"")
  }

  func testNoExpansionEverEmitsUnbalancedOrEmptyGroups() {
    let inputs = [
      "2.1.220", "2 1 220", "a", "a b", "1", "", "   ",
      "Start Page Private Browsing", "ActivityPerformance", "test123",
      "Sarah Chen Messages", "PR 10581 fix the thing", "v2 1 0 release",
    ]
    for input in inputs {
      let expanded = db.expandSearchQuery(input)
      XCTAssertFalse(expanded.contains("()"), "\"\(input)\" produced an empty group: \"\(expanded)\"")
      XCTAssertEqual(
        expanded.filter { $0 == "(" }.count,
        expanded.filter { $0 == ")" }.count,
        "\"\(input)\" produced unbalanced parens: \"\(expanded)\""
      )
    }
  }

  /// The expansion behavior that already worked must not regress.
  func testCamelCaseStillExpandsToAnOrGroup() {
    let expanded = db.expandSearchQuery("ActivityPerformance")
    XCTAssertTrue(expanded.hasPrefix("("), "expected an OR group, got \"\(expanded)\"")
    XCTAssertTrue(expanded.contains("Activity*"))
    XCTAssertTrue(expanded.contains("Performance*"))
    XCTAssertTrue(expanded.contains(" OR "))
  }

  func testSingleUsableWordGetsPrefixMatchingWithoutAGroup() {
    XCTAssertEqual(db.expandSearchQuery("Telegram"), "Telegram*")
  }

  func testEmptyAndWhitespaceQueriesExpandToEmpty() {
    XCTAssertEqual(db.expandSearchQuery(""), "")
    XCTAssertEqual(db.expandSearchQuery("   "), "")
  }

  /// Mixed input must keep the usable words and silently drop the unusable ones.
  func testUsableWordsSurviveAlongsideDroppedSingleCharacters() {
    let expanded = db.expandSearchQuery("a Telegram 1")
    XCTAssertEqual(expanded, "Telegram*")
  }
}
