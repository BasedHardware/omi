import XCTest

@testable import OmiTheme
@testable import Omi_Computer

/// The compact page chrome has one owner for each vertical gap. These tests
/// keep child pages from reintroducing the old stacked padding while they are
/// migrated onto the shared toolbar contract.
@MainActor
final class PagePanelVerticalRhythmTests: XCTestCase {
  func testFirstRowOnlyOwnsThePanelTopInset() {
    XCTAssertEqual(
      PagePanelFirstRowMetrics.topPadding,
      PagePanelVerticalRhythm.panelTopPadding,
      "the first row must align with the panel's shared top inset")
    XCTAssertEqual(
      PagePanelFirstRowMetrics.bottomPadding,
      0,
      "the first row must not add a second gap before its content")
  }

  func testSubsequentRowsUseTheSharedHorizontalLane() {
    XCTAssertEqual(
      PagePanelFirstRowMetrics.horizontalPadding,
      PagePanelVerticalRhythm.horizontalPadding)
    XCTAssertEqual(
      PagePanelVerticalRhythm.rowGap,
      QueryShellLayout.panelHeaderSpacing,
      "adjacent control rows must share one compact gap")
    XCTAssertEqual(
      PagePanelVerticalRhythm.contentGap,
      OmiSpacing.sm,
      "content owns the one gap after its toolbar")
  }

  func testBrainNavigationUsesTheSameFirstRowAndSubsequentRowRhythm() {
    XCTAssertEqual(
      BrainSectionPageMetrics.navigationTopPadding,
      PagePanelVerticalRhythm.panelTopPadding)
    XCTAssertEqual(
      BrainSectionPageMetrics.navigationBottomPadding,
      PagePanelVerticalRhythm.rowGap)
    XCTAssertEqual(
      BrainSectionPageMetrics.navigationHeight,
      QueryShellLayout.chipHeight
        + PagePanelVerticalRhythm.panelTopPadding
        + PagePanelVerticalRhythm.rowGap)
  }

  func testSearchAndDestinationPanelsShareTheSingleInterPanelGap() {
    XCTAssertEqual(QueryShellLayout.panelGap, 8)
    XCTAssertEqual(
      QueryShellLayout.panelGap,
      RewindSearchLayout.panelGap,
      "all destination surfaces must use the same search-to-content gap")
  }

  func testPageListsStartFullyOpaqueAndKeepOnlyTheOverflowCueBelow() {
    XCTAssertEqual(
      PageGlass.topFade,
      0,
      "the first visible row must not be faded when a page loads at its resting scroll position")
    XCTAssertGreaterThan(
      PageGlass.bottomFade,
      0,
      "the bottom edge may still signal that additional content continues below the viewport")
  }
}
