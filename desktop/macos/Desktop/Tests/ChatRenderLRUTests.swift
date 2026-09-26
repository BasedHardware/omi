import XCTest

@testable import Omi_Computer

@MainActor
final class ChatRenderLRUTests: XCTestCase {
  func testHitPromotesEntryAndEvictsOnlyLeastRecentlyUsed() {
    let cache = ChatRenderLRU<String, String>(capacity: 2)
    XCTAssertEqual(cache.value(for: "a") { "A" }, "A")
    XCTAssertEqual(cache.value(for: "b") { "B" }, "B")
    XCTAssertEqual(
      cache.value(for: "a") {
        XCTFail("must hit")
        return nil
      }, "A")
    XCTAssertEqual(cache.value(for: "c") { "C" }, "C")
    XCTAssertEqual(cache.count, 2)
    XCTAssertNil(cache.value(for: "b") { nil })
    XCTAssertEqual(cache.value(for: "a") { nil }, "A")
    XCTAssertEqual(cache.value(for: "c") { nil }, "C")
  }

  func testSingleEntryReplacementAndClearReleaseValues() {
    final class Value {}
    let cache = ChatRenderLRU<Int, Value>(capacity: 1)
    weak var first: Value?
    first = cache.value(for: 1) { Value() }
    XCTAssertNotNil(first)
    weak var second: Value?
    second = cache.value(for: 2) { Value() }
    XCTAssertNil(first)
    XCTAssertNotNil(second)
    cache.removeAll()
    XCTAssertNil(second)
    XCTAssertEqual(cache.count, 0)
    XCTAssertNotNil(cache.value(for: 3) { Value() })
  }

  func testFailedProductionDoesNotEvictUsefulContent() {
    let cache = ChatRenderLRU<Int, String>(capacity: 1)
    _ = cache.value(for: 1) { "kept" }
    XCTAssertNil(cache.value(for: 2) { nil })
    XCTAssertEqual(cache.value(for: 1) { nil }, "kept")
  }

  func testCachedMarkdownMatchesParserAcrossPartialAndCompleteRichText() {
    let answer = "A **bold** answer\n\n```swift\nlet x = 1\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n---\nDone."
    for length in 0...answer.count {
      let partial = String(answer.prefix(length))
      XCTAssertEqual(ChatMarkdownRenderCache.document(for: partial), OmiMarkdownDocument(markdown: partial))
      XCTAssertEqual(ChatMarkdownRenderCache.document(for: partial), OmiMarkdownDocument(markdown: partial))
    }
  }
}
