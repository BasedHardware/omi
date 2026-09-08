import OmiSupport
import XCTest

final class DictionaryDeduplicationTests: XCTestCase {
  func testLastWriteWinsForDuplicateExternalIdentifiers() {
    let records = [
      ("shared-id", "stale"),
      ("other-id", "other"),
      ("shared-id", "fresh"),
    ]

    let indexed = Dictionary(lastWriteWins: records)

    XCTAssertEqual(indexed.count, 2)
    XCTAssertEqual(indexed["shared-id"], "fresh")
    XCTAssertEqual(indexed["other-id"], "other")
  }

  func testEmptyInputProducesEmptyDictionary() {
    let records: [(String, Int)] = []
    let indexed = Dictionary(lastWriteWins: records)

    XCTAssertTrue(indexed.isEmpty)
  }
}
