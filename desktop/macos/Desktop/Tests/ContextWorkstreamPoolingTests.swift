import XCTest

@testable import Omi_Computer

final class ContextWorkstreamPoolingTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  private func item(
    _ factID: String, bucket: String = "bucket-a", worthiness: Double = 0.7,
    ageMinutes: Double = 5, statement: String = "a concrete fact"
  ) -> ContextWorkstreamPoolItem {
    ContextWorkstreamPoolItem(
      factID: factID,
      bucketID: bucket,
      appName: "App",
      statement: statement,
      notifyWorthiness: worthiness,
      createdAt: now.addingTimeInterval(-ageMinutes * 60))
  }

  func testTagSanitizationConvergesVariantsAndRejectsAbstentionAndNoise() {
    XCTAssertEqual(ContextWorkstreamTag.sanitize("Omi App"), "omi-app")
    XCTAssertEqual(ContextWorkstreamTag.sanitize("omi_app"), "omi-app")
    XCTAssertEqual(ContextWorkstreamTag.sanitize("  OMI--app  "), "omi-app")
    XCTAssertEqual(ContextWorkstreamTag.sanitize("dtrinity"), "dtrinity")
    XCTAssertNil(ContextWorkstreamTag.sanitize(nil))
    XCTAssertNil(ContextWorkstreamTag.sanitize(""))
    XCTAssertNil(ContextWorkstreamTag.sanitize("unknown"))
    XCTAssertNil(ContextWorkstreamTag.sanitize("UNKNOWN"))
    XCTAssertNil(ContextWorkstreamTag.sanitize("x"), "single characters carry no identity")
    XCTAssertNil(
      ContextWorkstreamTag.sanitize(String(repeating: "a", count: 40)),
      "over-length labels are rejected rather than truncated into collisions")
    XCTAssertNil(ContextWorkstreamTag.sanitize("!!!"), "symbol-only proposals reduce to nothing")
  }

  func testSelectionEnforcesFloorScaffoldFilterDiversityCapAndSize() {
    var candidates: [ContextWorkstreamPoolItem] = [
      item("below-floor", worthiness: 0.2),
      item("scaffold", statement: "Identifier proposal: visit:18"),
      item("narrative", statement: "Ambient narrative: a quiet scene unfolds"),
      item("proposed-fact", statement: "Proposed fact 1 — The board was lying"),
    ]
    // Four eligible facts in one bucket: the per-bucket cap keeps three.
    for index in 0..<4 {
      candidates.append(item("chatty-\(index)", bucket: "chatty", worthiness: 0.9, ageMinutes: 1))
    }
    // Ten other buckets, one eligible fact each, older than the chatty ones.
    for index in 0..<10 {
      candidates.append(
        item("spread-\(index)", bucket: "bucket-\(index)", worthiness: 0.5, ageMinutes: 30))
    }
    let selected = ContextWorkstreamPooling.select(candidates, now: now)
    XCTAssertEqual(selected.count, ContextWorkstreamPooling.maximumItems)
    XCTAssertFalse(selected.contains { $0.factID == "below-floor" })
    XCTAssertFalse(selected.contains { $0.factID == "scaffold" })
    XCTAssertFalse(selected.contains { $0.factID == "narrative" })
    XCTAssertFalse(selected.contains { $0.factID == "proposed-fact" })
    XCTAssertEqual(
      selected.filter { $0.bucketID == "chatty" }.count, ContextWorkstreamPooling.maximumPerBucket)
  }

  func testSelectionRanksWorthinessPlusRecencyDeterministically() {
    // Equal worthiness: the fresher fact outranks the stale one. Equal
    // everything: factID breaks the tie so the ranking is stable.
    let fresh = item("fresh", worthiness: 0.5, ageMinutes: 1)
    let stale = item("stale", worthiness: 0.5, ageMinutes: 60 * 24)
    let selected = ContextWorkstreamPooling.select([stale, fresh], now: now)
    XCTAssertEqual(selected.map(\.factID), ["fresh", "stale"])
    let tied = ContextWorkstreamPooling.select(
      [item("b", ageMinutes: 3), item("a", ageMinutes: 3)], now: now)
    XCTAssertEqual(tied.map(\.factID), ["a", "b"])
  }

  func testRecentContextWindowIncludesTheBoundaryAndDropsOlderFacts() {
    let inside = item("inside", bucket: "b-inside", ageMinutes: 14)
    let boundary = item("boundary", bucket: "b-boundary", ageMinutes: 15)
    let justOutside = ContextWorkstreamPoolItem(
      factID: "just-outside",
      bucketID: "b-outside",
      appName: "App",
      statement: "a concrete fact",
      notifyWorthiness: 0.7,
      createdAt: now.addingTimeInterval(-(15 * 60 + 1)))
    let weak = item("weak", bucket: "b-weak", worthiness: 0.59, ageMinutes: 1)
    let selected = ContextWorkstreamPooling.selectRecent(
      [inside, boundary, justOutside, weak], now: now)
    XCTAssertEqual(Set(selected.map(\.factID)), ["inside", "boundary"])
    XCTAssertFalse(selected.contains { $0.factID == "just-outside" })
    XCTAssertFalse(selected.contains { $0.factID == "weak" })
  }

  func testRecentContextCapsOneFactPerBucketAndThreeTotal() {
    var candidates: [ContextWorkstreamPoolItem] = []
    for bucket in 0..<6 {
      candidates.append(
        item("new-\(bucket)", bucket: "b-\(bucket)", worthiness: 0.9, ageMinutes: 1))
      candidates.append(
        item("old-\(bucket)", bucket: "b-\(bucket)", worthiness: 0.8, ageMinutes: 2))
    }
    let selected = ContextWorkstreamPooling.selectRecent(candidates, now: now)
    XCTAssertEqual(selected.count, 3)
    XCTAssertEqual(Set(selected.map(\.bucketID)).count, 3)
    XCTAssertTrue(selected.allSatisfy { $0.factID.hasPrefix("new-") })
  }

  func testRecentContextPromptSectionUsesTheSpecifiedHeaderAndIsNotCitable() throws {
    let section = try XCTUnwrap(
      ContextWorkstreamPooling.recentContextPromptSection(
        items: [item("fact-id-9", statement: "Hermes PR is blocked on review")], now: now))
    XCTAssertTrue(section.contains("RECENT CONTEXT FROM OTHER WINDOWS (last 15 min)"))
    XCTAssertTrue(section.contains("not citable"))
    XCTAssertTrue(section.contains("Hermes PR is blocked"))
    XCTAssertFalse(section.contains("fact-id-9"))
    XCTAssertNil(ContextWorkstreamPooling.recentContextPromptSection(items: [], now: now))
  }
}
