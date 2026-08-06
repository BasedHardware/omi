import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class TopNavigationBarLayoutTests: XCTestCase {
  func testExpandedNavigationUsesLaneLeadingEdgeAndPinsPersistentControlsToTrailingEdge() {
    let laneWidth = TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400)
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 420, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 150, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: laneWidth, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: laneWidth, height: 44)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .expanded),
      let persistentControls = recorder.frame(of: .persistentControls),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("expected expanded navigation and persistent controls to be placed")
    }
    XCTAssertEqual(navigation.minX, 0, accuracy: 0.5)
    XCTAssertEqual(settings.maxX, laneWidth, accuracy: 0.5)
    XCTAssertEqual(persistentControls.maxX, settings.minX - OmiSpacing.md, accuracy: 0.5)
  }

  func testCompactNavigationIsPlacedWhenTheFullTopBarWouldOverflow() {
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 420, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 150, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: 300, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: 300, height: 44)
    host.layoutSubtreeIfNeeded()

    XCTAssertNil(recorder.frame(of: .expanded))
    guard let compact = recorder.frame(of: .compact) else {
      return XCTFail("the compact navigation was never placed")
    }
    XCTAssertEqual(compact.minX, 0, accuracy: 0.5)
    XCTAssertLessThanOrEqual(compact.maxX, 300.5)

    guard
      let persistentControls = recorder.frame(of: .persistentControls),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("the persistent controls were never placed")
    }
    XCTAssertGreaterThan(persistentControls.minX, compact.maxX)
    XCTAssertEqual(persistentControls.maxX, settings.minX - OmiSpacing.md, accuracy: 0.5)
    XCTAssertGreaterThanOrEqual(settings.maxX, 299)
    XCTAssertLessThanOrEqual(settings.maxX, 300.5)
  }

  func testNavigationIsClippedRatherThanOverlappingPersistentControlsWhenCompactRowOverflows() {
    // Expanded = 500pt nav, compact = 200pt nav, controls = 200pt, settings = 32pt.
    // At a 300pt host the compact row (200 + spacing*3 + 200 + spacing + 32 ≈ 642)
    // still overflows. Verify navigation does not overlap the persistent controls.
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 500, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 200, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 200, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: 300, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: 300, height: 44)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .compact),
      let controls = recorder.frame(of: .persistentControls)
    else {
      return XCTFail("expected compact navigation and persistent controls to be placed")
    }
    // Navigation's proposed width must not cause it to overlap the controls.
    XCTAssertLessThanOrEqual(
      navigation.maxX,
      controls.minX,
      "compact navigation must not overlap persistent controls even when the row overflows"
    )
  }

  /// The bar now carries two pills because Home became a search surface and a `Memory` destination
  /// beside a field that returns memories is a contradiction. The claim worth holding is not the pill
  /// count — it is that **nothing was stranded by shrinking it** (INV-NAV-1).
  func testLibraryCarriesEveryDestinationThePillsUsedToReach() {
    XCTAssertEqual(
      TopNavigationRoutes.primaryItems.map(\.index),
      [SidebarNavItem.conversations.rawValue, SidebarNavItem.apps.rawValue]
    )
    XCTAssertEqual(TopNavigationRoutes.memoryDestinations, [.memories, .conversations, .brainMap])

    let reachable = Set(LibraryDestination.allCases.map(\.navItem))
    for stranded in [SidebarNavItem.conversations, .tasks, .rewind, .focus, .insight] {
      XCTAssertTrue(
        reachable.contains(stranded),
        "\(stranded.title) lost its pill and must still be reachable from Library")
    }
    XCTAssertEqual(
      LibraryDestination.allCases.compactMap(\.memoryDestination),
      [.conversations, .memories, .brainMap],
      "the Memory hub's three destinations must all survive inside Library")
  }

  func testLibraryPillReadsAsCurrentOnEveryPageItRoutesTo() {
    for destination in LibraryDestination.allCases {
      XCTAssertTrue(
        LibraryDestination.contains(selectedIndex: destination.navItem.rawValue),
        "\(destination.title) must light the Library pill")
    }
    XCTAssertFalse(LibraryDestination.contains(selectedIndex: SidebarNavItem.dashboard.rawValue))
    XCTAssertFalse(LibraryDestination.contains(selectedIndex: SidebarNavItem.apps.rawValue))
  }

  func testLibrarySelectionDistinguishesTheThreeMemoryHubDestinations() {
    let hub = SidebarNavItem.conversations.rawValue
    XCTAssertTrue(
      LibraryDestination.brainMap.isCurrent(
        selectedIndex: hub, memoryDestinationRawValue: MemoryHubDestination.brainMap.rawValue))
    XCTAssertFalse(
      LibraryDestination.brainMap.isCurrent(
        selectedIndex: hub, memoryDestinationRawValue: MemoryHubDestination.memories.rawValue),
      "Brain Map must not read as current while the hub is showing Memories")
    XCTAssertTrue(
      LibraryDestination.tasks.isCurrent(
        selectedIndex: SidebarNavItem.tasks.rawValue, memoryDestinationRawValue: 0),
      "a destination with no hub sub-page is current on its page alone")
  }

  func testNavigationLaneMatchesFullChatWidthAndPageInsets() {
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400), 900)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 800), 768)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 40), 8)
  }

  /// The bar's *glass* is the lane and its controls are inset inside it — so the inset has to leave a
  /// real row behind at the narrowest window the shell allows.
  ///
  /// The failure this guards is silent: `.padding` then `.frame(width:)` clamps a negative inner width
  /// to zero rather than complaining, so an inset grown past the lane produces an empty bar and a
  /// clean build.
  func testTheBarsContentSurvivesItsInsetAtTheNarrowestWindow() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: DesktopWindowLayoutPolicy.width)
    let row = lane - TopNavigationLayoutMetrics.barContentInset * 2

    XCTAssertGreaterThan(row, 0, "the bar's inset swallowed its own row")
    // Enough for the compact fallback: the menu, the status icons and the gear with their spacings.
    XCTAssertGreaterThan(
      row, 300,
      "at the minimum window width the bar must still fit its compact row without clipping")
  }

  /// The row is laid out inside the inset, not inside the glass — so the leading pill starts one
  /// spacing token in from the panel edge rather than flush against the corner.
  func testTheRowIsPlacedInsideTheBarsInsetRatherThanAgainstItsCorner() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400)
    let inset = TopNavigationLayoutMetrics.barContentInset
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 420, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 150, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      // Exactly what `DesktopTopBar` builds: the inset, then the lane, then the glass.
      .padding(.horizontal, inset)
      .frame(width: lane, height: TopNavigationLayoutMetrics.barHeight)
    )
    host.frame = NSRect(
      x: 0, y: 0, width: lane, height: TopNavigationLayoutMetrics.barHeight)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .expanded),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("expected the expanded row to be placed inside the bar")
    }
    // Measured leading-to-trailing rather than against an absolute origin: what has to be true is
    // that the row is the lane *minus its inset on both sides*, whatever coordinate space SwiftUI
    // hands the layout. Drop the padding and this is `lane`.
    XCTAssertEqual(
      settings.maxX - navigation.minX, lane - inset * 2, accuracy: 0.5,
      "the row must be laid out inside the bar's inset, not against its corner")
  }
}

private enum TopNavigationLayoutSlot: Hashable {
  case expanded
  case compact
  case persistentControls
  case settings
}

private final class TopNavigationLayoutRecorder: @unchecked Sendable {
  private var frames: [TopNavigationLayoutSlot: CGRect] = [:]

  func record(_ slot: TopNavigationLayoutSlot, _ frame: CGRect) {
    frames[slot] = frame
  }

  func frame(of slot: TopNavigationLayoutSlot) -> CGRect? {
    frames[slot]
  }
}

private struct TopNavigationLayoutProbe: Layout {
  let recorder: TopNavigationLayoutRecorder
  let slot: TopNavigationLayoutSlot

  func sizeThatFits(
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) -> CGSize {
    subviews.first?.sizeThatFits(proposal) ?? .zero
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(slot, bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}
