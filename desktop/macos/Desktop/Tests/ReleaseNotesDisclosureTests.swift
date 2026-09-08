import XCTest

@testable import Omi_Computer

@MainActor
final class ReleaseNotesDisclosureTests: XCTestCase {
  func testNewestReleaseIsOpenAndCannotBeClosed() {
    let disclosure = ReleaseNotesDisclosure()

    XCTAssertTrue(disclosure.isExpanded("0.12.322", isNewest: true))
    disclosure.toggle("0.12.322", isNewest: true)
    XCTAssertTrue(disclosure.isExpanded("0.12.322", isNewest: true))
    XCTAssertTrue(disclosure.expandedVersions.isEmpty)
  }

  func testOlderReleaseOpensAndClosesOnToggle() {
    let disclosure = ReleaseNotesDisclosure()

    XCTAssertFalse(disclosure.isExpanded("0.12.321", isNewest: false))
    disclosure.toggle("0.12.321")
    XCTAssertTrue(disclosure.isExpanded("0.12.321", isNewest: false))
    disclosure.toggle("0.12.321")
    XCTAssertFalse(disclosure.isExpanded("0.12.321", isNewest: false))
  }

  func testEachReleaseOpensIndependently() {
    let disclosure = ReleaseNotesDisclosure()

    disclosure.toggle("0.12.321")
    disclosure.toggle("0.12.320")
    XCTAssertEqual(disclosure.expandedVersions, ["0.12.321", "0.12.320"])

    disclosure.toggle("0.12.321")
    XCTAssertEqual(disclosure.expandedVersions, ["0.12.320"])
  }

  func testListStartsAtOnePageAndGrowsByOnePage() {
    let disclosure = ReleaseNotesDisclosure()

    XCTAssertEqual(disclosure.visibleCount, ReleaseNotesDisclosure.pageSize)
    XCTAssertTrue(disclosure.canShowMore(total: 25))

    disclosure.showMore(total: 25)
    XCTAssertEqual(disclosure.visibleCount, ReleaseNotesDisclosure.pageSize * 2)
  }

  func testShowMoreStopsAtTheEndOfTheListAndThenOffersNothingMore() {
    let disclosure = ReleaseNotesDisclosure()

    disclosure.showMore(total: 7)
    XCTAssertEqual(disclosure.visibleCount, 7)
    XCTAssertFalse(disclosure.canShowMore(total: 7))

    // A second request cannot walk past the end.
    disclosure.showMore(total: 7)
    XCTAssertEqual(disclosure.visibleCount, 7)
  }

  func testEmptyCatalogNeverOffersMore() {
    let disclosure = ReleaseNotesDisclosure()

    XCTAssertFalse(disclosure.canShowMore(total: 0))
    disclosure.showMore(total: 0)
    XCTAssertEqual(disclosure.visibleCount, 0)
  }
}
