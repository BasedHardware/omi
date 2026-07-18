import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatToolExecutor.rowInt`. GRDB decodes SQLite
/// INTEGER columns (including COUNT/MIN/MAX aggregates) to `Int64`, and
/// `Int64 as? Int` is ALWAYS nil in Swift — no numeric bridging. So the daily
/// recap / file-scan tools that read row integers with a bare `row["col"] as? Int`
/// silently reported 0 captures, unchecked ("done") tasks as not done, 0m focus
/// durations, and "0 files" per type. `rowInt` reads the value correctly.
final class ChatToolExecutorRowIntTests: XCTestCase {

  func testInt64AsIntNeverBridges() {
    // The exact defect the helper exists to work around.
    XCTAssertNil(Int64(7) as? Int)
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
