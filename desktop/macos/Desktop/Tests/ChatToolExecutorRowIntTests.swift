import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatToolExecutor.rowInt`. GRDB decodes SQLite
/// INTEGER columns (including COUNT/MIN/MAX aggregates) to `Int64`, and
/// `Int64 as? Int` is ALWAYS nil in Swift — no numeric bridging. So the daily
/// recap / file-scan tools that read row integers with a bare `row["col"] as? Int`
/// silently reported 0 captures, unchecked ("done") tasks as not done, 0m focus
/// durations, and "0 files" per type. `rowInt` reads the value correctly.
final class ChatToolExecutorRowIntTests: XCTestCase {
  func testDailyRecapTypedResultCarriesFiftyConversationItems() throws {
    let conversations: [[String: Any]] = (1...50).map { index in
      ["title": "Conversation \(index)", "summary": "Overview \(index)"]
    }
    let result = ChatToolExecutor.typedReadToolResult(
      toolName: "get_daily_recap",
      sections: [["name": "conversations", "total": 50, "items": conversations]],
      totals: ["conversations": 50])
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
    XCTAssertEqual(object["ok"] as? Bool, true)
    XCTAssertEqual(object["tool"] as? String, "get_daily_recap")
    let totals = try XCTUnwrap(object["totals"] as? [String: Int])
    XCTAssertEqual(totals["conversations"], 50)
    let sections = try XCTUnwrap(object["sections"] as? [[String: Any]])
    let section = try XCTUnwrap(sections.first { ($0["name"] as? String) == "conversations" })
    let items = try XCTUnwrap(section["items"] as? [[String: Any]])
    XCTAssertEqual(items.count, 50)
    XCTAssertEqual(items.first?["title"] as? String, "Conversation 1")
    XCTAssertEqual(items.last?["title"] as? String, "Conversation 50")
  }

  func testInt64AsIntNeverBridges() {
    // The exact defect the helper exists to work around. Cast from an `Any`
    // box (as production does with a GRDB row value) — spelling `Int64 as? Int`
    // directly is diagnosed as an always-failing cast under -warnings-as-errors.
    let boxed: Any = Int64(7)
    XCTAssertNil(boxed as? Int)
  }

  func testRowIntExtractsInt64Value() {
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(7)), 7)
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(0)), 0)
    XCTAssertEqual(ChatToolExecutor.rowInt(Int64(-3)), -3)
  }

  func testRowIntFallsBackToPlainInt() {
    // Defensive: an already-`Int` value still reads.
    XCTAssertEqual(ChatToolExecutor.rowInt(Int(42)), 42)
  }

  func testRowIntReturnsNilForMissingOrNonInteger() {
    XCTAssertNil(ChatToolExecutor.rowInt(nil))
    XCTAssertNil(ChatToolExecutor.rowInt("123"))
    XCTAssertNil(ChatToolExecutor.rowInt(3.5))
  }
}
