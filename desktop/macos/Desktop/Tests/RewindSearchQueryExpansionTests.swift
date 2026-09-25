import GRDB
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

  /// The sibling of the `()` defect above, and the reason every test here now runs its own
  /// output through FTS5 instead of only inspecting its shape.
  ///
  /// FTS5 accepts implicit AND between bare terms — `a* b*` is fine — but not once a word
  /// expands into a parenthesised group: `a* (b* OR c*)` is `fts5: syntax error near "("`.
  /// Expansion joined with a space, so any multi-word title where one word split on camelCase
  /// or a number boundary failed the entire search rather than matching less. Observed 45
  /// times across 13 sessions, silently emptying both screen-history grounding and the Rewind
  /// search UI.
  func testGroupsAreJoinedWithAnExplicitAnd() throws {
    let expanded = db.expandSearchQuery("ActivityPerformance QuarterlyReport")
    XCTAssertTrue(
      expanded.contains(") AND ("),
      "space-joined groups are invalid FTS5, got \"\(expanded)\"")
    try assertValidFTS5(expanded)
  }

  func testBareTermJoinedToAGroupIsValid() throws {
    try assertValidFTS5(db.expandSearchQuery("Telegram ActivityPerformance"))
  }

  /// Real window titles, each run through a real FTS5 matcher. Shape assertions did not catch
  /// this class; executing the query does.
  func testRealWindowTitlesProduceExecutableQueries() throws {
    for title in [
      "ActivityPerformance QuarterlyReport",
      "Telegram ActivityPerformance",
      "Cursor 2.1.220 SuggestionModels swift",
      "GitHub PullRequest 11864 BasedHardware omi",
      "2 1 220",
      "a Telegram 1",
      "Telegram",
    ] {
      try assertValidFTS5(db.expandSearchQuery(title), title: title)
    }
  }

  /// Runs the expansion against a real FTS5 table. An empty expansion is legitimate — `search`
  /// guards on it — so only a non-empty one has to parse.
  private func assertValidFTS5(_ expanded: String, title: String? = nil) throws {
    guard !expanded.isEmpty else { return }
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(sql: "CREATE VIRTUAL TABLE t USING fts5(body)")
      try db.execute(sql: "INSERT INTO t VALUES ('activity performance quarterly report')")
    }
    let label = title.map { " (from \"\($0)\")" } ?? ""
    XCTAssertNoThrow(
      try queue.read { db in
        try Row.fetchAll(db, sql: "SELECT * FROM t WHERE t MATCH ?", arguments: [expanded])
      },
      "expansion \"\(expanded)\"\(label) is not a valid FTS5 query")
  }
}
