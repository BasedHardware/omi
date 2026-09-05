import AppKit
import XCTest

@testable import Omi_Computer

/// The prose memo's contract: a hit must be indistinguishable from a
/// recompute, keys must be sensitive to every input that changes the output,
/// and the two maps that grow (entries, per-entry heights) must stay bounded.
@MainActor
final class ChatProseRenderCacheTests: XCTestCase {

  /// XCTest's `setUp` is nonisolated and cannot reach the MainActor cache
  /// directly, so every test begins by emptying it here.
  private func beginFresh() {
    ChatProseRenderCache.removeAll()
  }

  // MARK: - Hit identity

  func testTheSameKeyReturnsTheSameEntryWithoutReproducing() {
    beginFresh()
    var productions = 0
    let key = Self.key(markdown: "Hello **world**")
    let first = ChatProseRenderCache.entry(for: key) {
      productions += 1
      return NSAttributedString(string: "Hello world")
    }
    let second = ChatProseRenderCache.entry(for: key) {
      productions += 1
      return NSAttributedString(string: "Hello world")
    }

    XCTAssertNotNil(first)
    XCTAssertTrue(first === second, "a hit must return the cached entry itself")
    XCTAssertEqual(productions, 1, "a hit must not run produce again")
  }

  func testEveryKeyInputThatChangesTheOutputProducesAMiss() {
    beginFresh()
    let inputs: [(name: String, key: ChatProseRenderCache.Key)] = [
      ("text", Self.key(markdown: "one")),
      ("markdown", Self.key(markdown: "one **two**")),
      ("style", Self.key(markdown: "same", style: .user)),
      ("fontSize", Self.key(markdown: "same", fontSize: 17)),
      ("fontScaleMilli", Self.key(markdown: "same", fontScaleMilli: 1_100)),
      ("citationOrdinals", Self.key(markdown: "same", citationOrdinals: [3])),
      ("citationOrder", Self.key(markdown: "same", citationOrdinals: [3, 1])),
    ]

    for (index, input) in inputs.enumerated() {
      let base = inputs[max(0, index - 1)].key
      // Distinct pairs only: two neighbours can name the same input if the
      // list above ever repeats one.
      guard base != input.key else { continue }
      var producedForChangedInput = false
      // The base lookup may hit or miss depending on earlier iterations; only
      // the changed key matters — it must never hit.
      _ = ChatProseRenderCache.entry(for: base) { NSAttributedString(string: "x") }
      let second = ChatProseRenderCache.entry(for: input.key) {
        producedForChangedInput = true
        return NSAttributedString(string: "x")
      }
      XCTAssertTrue(producedForChangedInput, "changing \(input.name) must re-run produce")
      XCTAssertNotNil(second)
    }
  }

  // MARK: - Unproducible blocks

  func testNilFromProduceIsNeverCached() {
    beginFresh()
    var productions = 0
    let key = Self.key(markdown: "| a table |")
    let first = ChatProseRenderCache.entry(for: key) {
      productions += 1
      return nil
    }
    let second = ChatProseRenderCache.entry(for: key) {
      productions += 1
      return nil
    }

    XCTAssertNil(first)
    XCTAssertNil(second)
    XCTAssertEqual(productions, 2, "a nil produce must be tried again, not remembered")

    let third = ChatProseRenderCache.entry(for: key) {
      productions += 1
      return NSAttributedString(string: "now it renders")
    }
    XCTAssertNotNil(third)
    XCTAssertEqual(productions, 3)
    XCTAssertEqual(ChatProseRenderCache.entryCount, 1)
  }

  // MARK: - LRU bound

  func testEvictionHoldsTheBoundAndTurnsOldestKeysOver() {
    beginFresh()
    let capacity = 192
    var produced = Set<String>()
    func produce(_ text: String) -> NSAttributedString {
      produced.insert(text)
      return NSAttributedString(string: text)
    }

    for index in 0..<(capacity + 10) {
      _ = ChatProseRenderCache.entry(for: Self.key(markdown: "row-\(index)")) {
        produce("row-\(index)")
      }
    }
    XCTAssertEqual(
      ChatProseRenderCache.entryCount, capacity,
      "the cache must not grow past its bound no matter how many keys arrive")

    // The oldest key was evicted: asking for it runs produce again.
    produced.removeAll()
    _ = ChatProseRenderCache.entry(for: Self.key(markdown: "row-0")) { produce("row-0") }
    XCTAssertEqual(produced, ["row-0"], "the oldest key must have been evicted")

    // The newest key survived: it hits without producing.
    produced.removeAll()
    let newest = ChatProseRenderCache.entry(for: Self.key(markdown: "row-\(capacity + 9)")) {
      produce("row-\(capacity + 9)")
    }
    XCTAssertTrue(produced.isEmpty, "a recently inserted key must not be evicted by later inserts")
    XCTAssertNotNil(newest)
    XCTAssertEqual(ChatProseRenderCache.entryCount, capacity)
  }

  // MARK: - Height memo

  func testHeightMemoizesPerWidthAndMeasuresNewWidths() {
    beginFresh()
    let entry = ChatProseRenderCache.Entry(attributed: NSAttributedString(string: "prose"))
    var measures = 0

    let first = ChatProseRenderCache.height(for: entry, width: 320) {
      measures += 1
      return 42
    }
    let again = ChatProseRenderCache.height(for: entry, width: 320) {
      measures += 1
      return 999
    }
    let otherWidth = ChatProseRenderCache.height(for: entry, width: 480) {
      measures += 1
      return 87
    }
    let otherWidthAgain = ChatProseRenderCache.height(for: entry, width: 480) {
      measures += 1
      return 12
    }

    XCTAssertEqual(first, 42)
    XCTAssertEqual(again, 42, "the same width must reuse the measured height")
    XCTAssertEqual(otherWidth, 87)
    XCTAssertEqual(otherWidthAgain, 87)
    XCTAssertEqual(measures, 2, "one measure per distinct width, none more")
  }

  func testTheHeightMapDropsStaleWidthsAtTheBound() {
    beginFresh()
    let entry = ChatProseRenderCache.Entry(attributed: NSAttributedString(string: "prose"))
    var measures = 0
    func measure() -> CGFloat {
      measures += 1
      return CGFloat(measures)
    }

    // Fill the bound with distinct widths.
    for width in 1...8 {
      _ = ChatProseRenderCache.height(for: entry, width: CGFloat(width), measure: measure)
    }
    XCTAssertEqual(measures, 8)

    // A ninth width evicts the map rather than growing it, so the first width
    // — memoized above — has to measure again.
    _ = ChatProseRenderCache.height(for: entry, width: 9, measure: measure)
    let heightAfterDrop = ChatProseRenderCache.height(for: entry, width: 1, measure: measure)
    XCTAssertEqual(measures, 10, "width 1 must have been re-measured after the drop")
    XCTAssertEqual(heightAfterDrop, 10)
  }

  // MARK: - Helpers

  private static func key(
    markdown: String,
    style: OmiMarkdown.Style = .assistant,
    fontSize: Int = 14,
    fontScaleMilli: Int = 1_000,
    citationOrdinals: [Int] = []
  ) -> ChatProseRenderCache.Key {
    ChatProseRenderCache.Key(
      markdown: markdown,
      style: style,
      fontSize: fontSize,
      fontScaleMilli: fontScaleMilli,
      citationOrdinals: citationOrdinals)
  }
}
