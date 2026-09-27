import AppKit
import SwiftUI
import XCTest

@testable import OmiTheme
@testable import Omi_Computer

/// The shared page states replaced about seven hand-built variants per state. What has to stay true
/// is that they are *one* version — one glyph, one retry — and that each placement claims the room
/// its host can give it: a status panel must not grow to the window, and a state inside a scroll
/// view must not collapse to its text.
@MainActor
final class GlassPageStatesTests: XCTestCase {

  // MARK: - The one version

  func testEveryStateSharesOneGlyphSizeOneErrorGlyphAndOneRetry() {
    XCTAssertEqual(GlassPageState.glyphSize, OmiType.title)
    XCTAssertEqual(GlassPageState.errorSymbol, "exclamationmark.triangle")
    XCTAssertEqual(GlassPageState.retryTitle, "Try Again")
    // A failed load is a recoverable pause, not the page's primary action.
    XCTAssertEqual(GlassPageState.retryStyle.kind, .secondary)
    XCTAssertEqual(GlassPageState.retryStyle.size, .compact)
  }

  // MARK: - Placement decisions

  func testPagePlacementFillsWhatItIsOfferedWithoutAFloor() {
    XCTAssertTrue(GlassPageStatePlacement.page.fillsHeight)
    XCTAssertNil(GlassPageStatePlacement.page.minHeight)
    XCTAssertEqual(GlassPageStatePlacement.page.padding, OmiSpacing.xxl)
  }

  func testScrollingPlacementKeepsTheQueryShellFloorInsteadOfFilling() {
    // A ScrollView offers no height, so "fill" would mean "collapse to the text".
    XCTAssertFalse(GlassPageStatePlacement.scrolling.fillsHeight)
    XCTAssertEqual(GlassPageStatePlacement.scrolling.minHeight, QueryShellLayout.minimumBodyHeight)
  }

  func testPanelPlacementTakesOnlyItsIntrinsicSizeAndLeavesPaddingToThePanel() {
    XCTAssertFalse(GlassPageStatePlacement.panel.fillsHeight)
    XCTAssertNil(GlassPageStatePlacement.panel.minHeight)
    XCTAssertEqual(GlassPageStatePlacement.panel.padding, 0)
  }

  // MARK: - Laid out

  func testScrollingStatesNeverCollapseBelowTheFloor() {
    let states: [AnyView] = [
      AnyView(GlassLoadingState(label: "Searching…", placement: .scrolling)),
      AnyView(GlassEmptyState(systemImage: "magnifyingglass", title: "No Apps Found", placement: .scrolling)),
      AnyView(GlassErrorState(title: "Couldn't Load Apps", placement: .scrolling, retry: {})),
    ]
    for state in states {
      let size = fittingSize(of: state, width: 600)
      XCTAssertGreaterThanOrEqual(size.height, QueryShellLayout.minimumBodyHeight - 0.5)
    }
  }

  func testPanelStateIsNarrowerThanTheWindowItSitsIn() {
    // The Rewind status panel sizes itself around this state. A state that asked for the full width
    // would stretch the panel edge to edge.
    let panel = NSHostingView(
      rootView: GlassErrorState(
        title: "Couldn't Load Screenshots", message: "Try again.", placement: .panel, retry: {})
    ).fittingSize
    XCTAssertGreaterThan(panel.width, 0)
    XCTAssertLessThan(panel.width, 600)
    XCTAssertLessThan(panel.height, 400)
  }

  func testAnErrorStateIsTallerThanItsLoadingStateBecauseItCarriesTheRetry() {
    let loading = fittingSize(of: AnyView(GlassLoadingState(label: "Loading", placement: .panel)), width: 400)
    let error = fittingSize(
      of: AnyView(GlassErrorState(title: "Couldn't Load", placement: .panel, retry: {})), width: 400)
    XCTAssertGreaterThan(error.height, loading.height + OmiButtonStyle.minHeight(.compact) - 1)
  }

  private func fittingSize(of view: AnyView, width: CGFloat) -> CGSize {
    let host = NSHostingView(rootView: view.frame(width: width))
    return host.fittingSize
  }
}
