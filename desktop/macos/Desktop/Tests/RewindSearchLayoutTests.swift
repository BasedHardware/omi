import XCTest

@testable import Omi_Computer

/// The search surface's arithmetic, held as values.
///
/// Everything here is a decision a `body` would otherwise make invisibly: how wide a card is, how
/// tall the panel may grow, whether the bottom edge fades. A screenshot proves one of these once; a
/// test proves them after the next padding change.
final class RewindSearchLayoutTests: XCTestCase {

  // MARK: - The grid

  func testThreeColumnsFitTheContentWidthExactly() {
    let content = RewindSearchLayout.contentWidth()
    XCTAssertEqual(
      content,
      RewindSearchLayout.panelWidth - RewindSearchLayout.panelPaddingHorizontal * 2,
      accuracy: 0.001,
      "the content lane is the panel less its shared horizontal padding")

    let card = RewindSearchLayout.cardWidth()
    let gutters = RewindSearchLayout.cardGutter * CGFloat(RewindSearchLayout.resultColumns - 1)
    XCTAssertEqual(
      card * CGFloat(RewindSearchLayout.resultColumns) + gutters, content, accuracy: 0.001,
      "three cards plus two gutters are the content width — no column is clipped")
  }

  func testACardIsAsTallAsTheLayoutSays() {
    let card = RewindSearchLayout.cardWidth()
    let gutters = RewindSearchLayout.cardGutter * CGFloat(RewindSearchLayout.resultColumns - 1)
    XCTAssertEqual(
      card,
      (RewindSearchLayout.contentWidth() - gutters) / CGFloat(RewindSearchLayout.resultColumns),
      accuracy: 0.001)
    XCTAssertEqual(
      RewindSearchLayout.cardHeight(),
      card / RewindSearchLayout.thumbnailAspect + RewindSearchLayout.cardCaptionHeight,
      accuracy: 0.001)
  }

  func testCardsStayLegibleAtThePanelWidth() {
    XCTAssertGreaterThan(
      RewindSearchLayout.cardWidth(), RewindSearchLayout.minimumCardWidth,
      "a card under the minimum has no room to say anything before it truncates")
  }

  func testTheSharedRewindLaneReflowsItsGridWithoutChangingTheThreeColumnContract() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400)
    let card = RewindSearchLayout.cardWidth(panelWidth: lane)
    let gutters = RewindSearchLayout.cardGutter * CGFloat(RewindSearchLayout.resultColumns - 1)
    XCTAssertEqual(
      card * CGFloat(RewindSearchLayout.resultColumns) + gutters,
      RewindSearchLayout.contentWidth(panelWidth: lane),
      accuracy: 0.001)
    XCTAssertGreaterThan(card, RewindSearchLayout.cardWidth(), "the widened lane has room for readable cards")
  }

  func testNarrowingThePanelEventuallyClipsACard() {
    // The claim the minimum exists to make: it is a real boundary, not decoration.
    XCTAssertLessThan(RewindSearchLayout.cardWidth(panelWidth: 480), RewindSearchLayout.minimumCardWidth)
  }

  // MARK: - The height clamp

  func testAnEmptyPanelIsShortAndAFullOneStopsAtTheCeiling() {
    XCTAssertEqual(RewindSearchLayout.resultsBodyHeight(contentHeight: 0), 40)
    XCTAssertEqual(RewindSearchLayout.resultsBodyHeight(contentHeight: 200), 200)
    XCTAssertEqual(RewindSearchLayout.resultsBodyHeight(contentHeight: 9_000), 545)
  }

  func testTheCeilingLeavesRoomForAWholeCard() {
    XCTAssertGreaterThan(
      RewindSearchLayout.maximumResultsBodyHeight,
      RewindSearchLayout.cardHeight() + RewindSearchLayout.panelPaddingVertical,
      "a ceiling under one whole card slices the first row the user sees")
  }

  /// The regression this surface actually shipped with: the reference's ceiling was measured for a
  /// floating window, and inside Rewind's tab the room is smaller, so the bottom row was cut by the
  /// window edge rather than by the clamp.
  func testTheRoomAvailableBoundsThePanelBelowTheReferenceCeiling() {
    let available: CGFloat = 380
    XCTAssertEqual(
      RewindSearchLayout.resultsBodyHeight(contentHeight: 9_000, available: available), available,
      "with less room than the ceiling, the room wins")
    XCTAssertEqual(
      RewindSearchLayout.resultsBodyHeight(contentHeight: 9_000, available: 4_000), 545,
      "with more room than the ceiling, the ceiling still wins")
    XCTAssertEqual(
      RewindSearchLayout.resultsBodyHeight(contentHeight: 120, available: available), 120,
      "content shorter than both is untouched")
  }

  func testTheFloorSurvivesAContainerWithNoRoomAtAll() {
    XCTAssertEqual(RewindSearchLayout.resultsBodyHeight(contentHeight: 900, available: 0), 40)
  }

  // MARK: - The bottom edge

  func testTheEdgeOnlyFadesWhenThereIsMoreBelowIt() {
    XCTAssertFalse(RewindSearchLayout.bodyScrolls(contentHeight: 200))
    XCTAssertEqual(
      RewindSearchLayout.scrollFade(contentHeight: 200), 0,
      "a fade over content that fits promises content that is not there")

    XCTAssertTrue(RewindSearchLayout.bodyScrolls(contentHeight: 9_000))
    XCTAssertEqual(RewindSearchLayout.scrollFade(contentHeight: 9_000), 26)
  }

  func testAContentHeightExactlyOnTheCeilingDoesNotFlickerTheFade() {
    XCTAssertFalse(
      RewindSearchLayout.bodyScrolls(contentHeight: RewindSearchLayout.maximumResultsBodyHeight))
  }

  func testTheEdgeFadesWhenTheTabIsTheBoundEvenThoughTheCeilingIsNot() {
    XCTAssertTrue(RewindSearchLayout.bodyScrolls(contentHeight: 500, available: 300))
    XCTAssertEqual(RewindSearchLayout.scrollFade(contentHeight: 500, available: 300), 26)
  }

  func testTheFadeNeverSwallowsAWholeCaption() {
    XCTAssertLessThanOrEqual(
      RewindSearchLayout.scrollFadeHeight, RewindSearchLayout.cardCaptionHeight,
      "a fade deeper than the caption makes the last row unreadable to fix the next row's slice")
  }

  // MARK: - The query chip

  func testAnEmptyQueryHasNoChipAtAll() {
    XCTAssertEqual(RewindSearchMetrics.chipWidth(for: "", available: 400), 0)
  }

  func testTheChipHugsItsTextAndStopsAtTheBarsEdge() {
    let short = RewindSearchMetrics.chipWidth(for: "hi", available: 400)
    let long = RewindSearchMetrics.chipWidth(for: "a much longer query than that", available: 400)
    XCTAssertGreaterThan(long, short, "the chip is sized from the text, not fixed")
    XCTAssertLessThanOrEqual(long, 400, "and it never grows past the room it has")

    XCTAssertGreaterThanOrEqual(
      short, RewindSearchMetrics.minimumChipWidth,
      "a chip narrower than the minimum is a smudge rather than a chip")
  }

  func testTheQueryStaysReadingTypeRatherThanTheDisplayFace() {
    XCTAssertLessThan(
      RewindSearchMetrics.queryFontSize, 22,
      "a search field is reading type; over the display threshold it resolves to the display face")
    XCTAssertGreaterThan(
      RewindSearchMetrics.queryLineHeight, RewindSearchMetrics.queryFontSize,
      "a row shorter than its own font clips the placeholder's ascenders")
  }

  // MARK: - What the header says

  @MainActor
  func testTheCountIsNilUntilSomethingHasBeenAsked() {
    XCTAssertNil(
      RewindSearchResultsPanel.countLabel(groups: 0, screenshots: 0),
      "\"No results\" over an untouched surface answers a search nobody ran")
    XCTAssertEqual(RewindSearchResultsPanel.countLabel(groups: 0, screenshots: 12), "No results")
    XCTAssertEqual(RewindSearchResultsPanel.countLabel(groups: 1, screenshots: 3), "1 result")
    XCTAssertEqual(RewindSearchResultsPanel.countLabel(groups: 41, screenshots: 48), "41 results")
  }

  @MainActor
  func testTheFilterDisclosureNamesTheNarrowingItHolds() {
    XCTAssertEqual(RewindSearchResultsPanel.filterDisclosureLabel(app: nil), "Filter")
    XCTAssertEqual(RewindSearchResultsPanel.filterDisclosureLabel(app: "Arc"), "Filter — Arc")
  }

  // MARK: - When

  func testTimeReadsRelativeInsideADayAndAbsoluteBeyondIt() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    XCTAssertEqual(RewindSearchTime.describe(now.addingTimeInterval(-30), now: now), "just now")
    XCTAssertEqual(RewindSearchTime.describe(now.addingTimeInterval(-600), now: now), "10m ago")
    XCTAssertEqual(RewindSearchTime.describe(now.addingTimeInterval(-7_200), now: now), "2h ago")

    // Older than a day stops being relative — "30h ago" is not how anyone reads their own week.
    let older = RewindSearchTime.describe(now.addingTimeInterval(-60 * 60 * 24 * 9), now: now)
    XCTAssertFalse(older.hasSuffix("ago"), "got \(older)")
    XCTAssertFalse(older.isEmpty)
  }
}
